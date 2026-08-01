# Đưa NebulaGraph vào dự án Gotix — Nghiên cứu khả thi

> Tài liệu nghiên cứu nội bộ. Mọi nhận định về Gotix đều dẫn nguồn file trong `d:\Bigdata\hanoiTax\`.
> Chỗ nào tài liệu không nói, ghi rõ **"tài liệu không đề cập"** hoặc **"(suy luận)"** — không bịa.
> Cập nhật: 2026-07-28.
>
> ⚠️ **Ranh giới quan trọng — đọc trước:** `detecting_cheat_by_nebula` (98 công ty, 8.976 hóa đơn) là **dữ liệu mô phỏng/kiểm thử tự tạo** để luyện tập NebulaGraph — **KHÔNG phải dữ liệu của Gotix, không nằm trong lakehouse Gotix**. Nó chỉ được dùng làm **bằng chứng năng lực kỹ thuật** (import pipeline chạy được, query pattern nào an toàn, thuật toán phát hiện nào hiệu quả) — KHÔNG phải "dữ liệu hóa đơn có sẵn của Gotix" hay tiền đề cho một domain cụ thể. Việc tích hợp Nebula vào Gotix là cho **toàn bộ dữ liệu lakehouse thật** (9 domain, xem mục 1.2–1.4), không giới hạn ở hóa đơn.

---

## 1. Gotix hiện tại

### 1.1 Hệ thống là gì
Gotix là nền tảng **AI + Data + Decision Engine** phục vụ Thuế Hà Nội (~600.000 người nộp thuế, ~4.000 cán bộ thuế). Lakehouse là **tầng dữ liệu nền** (`data/`). Nguyên tắc cốt lõi: *pipeline chỉ chuẩn bị dữ liệu, không chứa business logic; quyết định nghiệp vụ thuộc về **Risk Engine** (rule-based), AI chỉ hỗ trợ.* (nguồn: `guide.md` §1)

### 1.2 Kiến trúc lakehouse & tech stack (nguồn: `guide.md` §2–3)

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| Object storage | **MinIO** (S3) | File raw (bronze) + data file Iceberg (warehouse) + phát event `s3:ObjectCreated` |
| Table format | **Apache Iceberg** | Bảng ACID trên S3, schema/partition evolution |
| Catalog | **Nessie** | Metadata Iceberg, versioning kiểu git (branch/commit/time-travel) |
| Query engine | **Trino** | SQL trên `nessie.tier1/2/3.*` — cửa duy nhất app đọc lake |
| Orchestration | **Airflow** | Chuỗi DAG T1→T2→T3 (`schedule=None`, event/manual) |
| Event ingest | **Event Bridge** (FastAPI) | MinIO event → trigger DAG, dedup theo `sha1(bucket\|key)` |
| Notebook/QC | **JupyterHub + Spark (PySpark)** | Browse/QC/đối soát |
| Serving cache | **Redis** (qua taxpayer360 API) | Feature Tier3 write-through, đọc ~1ms |
| CDC/Streaming | Kafka + Debezium + Postgres/pgvector | Đã dựng nhưng **batch chưa dùng** |

Mô hình **Medallion 3 tier**, dữ liệu **long-format** (thêm chỉ tiêu = thêm dòng, không `ALTER TABLE`):
- **Tier1/Bronze**: raw immutable, 1 dòng = 1 file XML (manifest).
- **Tier2/Silver**: parse & chuẩn hoá, mỗi form 2 bảng `header` (1 tờ khai) + `item_value` (1 chỉ tiêu).
- **Tier3/Gold**: feature/mart, 1 dòng = 1 feature.

**Khóa dữ liệu** (nguồn: `guide.md` §5): `mst` (join key xuyên domain, **KHÔNG phải PK**), `ictrl_dt` (ngày logic GMT+7, trục partition), `filing_key`, `<form>_filing_id` (row-id chuẩn T2/T3). Ví dụ dữ liệu thật (nguồn: `mock_lakehouse/`): filing_id `0108313992|402|Y|2023|1|f16288baea`; feature Tier3 dạng `{mst, filing_id, feature_name, feature_value_num}` như `TY_SO_THANH_TOAN=4.16`, `BIEN_LOI_NHUAN_RONG=0.1875`.

### 1.3 Luồng dữ liệu hiện tại (E2E, event-driven) (nguồn: `guide.md` §6, `system_flow_analysis.md`)

```
(1) Client upload XML
      s3://bronze-<env>/tax_declaration/<type>/ictrl_dt=YYYY-MM-DD/<file>.xml
        │  MinIO bắn s3:ObjectCreated
        ▼
(2) EVENT BRIDGE (FastAPI :8799)  ── parse key → {env,type,ictrl_dt}
        │  run_id = minio-sha1(bucket|key)  (dedup; trùng → 409)
        │  POST Airflow REST
        ▼
(3) AIRFLOW  ── TriggerDagRunOperator chain ──►
        ┌───────────────┐   ┌───────────────┐   ┌──────────────────────┐
        │ TIER1 ingest  │──►│ TIER2 parse   │──►│ TIER3 compute        │
        │ manifest      │   │ header+item   │   │ ~15 financial ratios │
        └──────┬────────┘   └──────┬────────┘   └──────────┬───────────┘
               │ Python runner (data.pipelines.runner)     │
               ▼                    ▼                       ▼
(4) ICEBERG (catalog nessie)  nessie.tier1.* / tier2.* / tier3.*
        │  ghi bằng PyIceberg (KHÔNG Spark), overwrite_filter theo (ictrl_dt,row_id)
        ▼
(5) TIÊU THỤ
      • apps/api/taxpayer360  ── Trino over HTTP ──► nessie.tier2/tier3.*
      • Tier3 write-through  ── POST /v1/cache/upsert ──► Redis (đọc ~1ms)
      • JupyterHub (PySpark)  ── browse/QC
```

Điểm đặc biệt: khi tờ **TNDN(892)** về, Event Bridge lookback tìm **BCTC(402)** cùng `mst` để tính lại feature liên-file (`EVENT_BRIDGE_CROSSFILE_ENABLED`) — đây là **liên kết chéo duy nhất** hiện có, và nó ở mức 1-hop theo `mst` (nguồn: `guide.md` §6).

### 1.4 Các bài toán nghiệp vụ chính
- **Phân tích rủi ro / anti-fraud thuế**: domain `risk_feature`, `risk_scoring`, `compliance` — **nhưng tất cả đang là scaffold rỗng**, chỉ `tax_declaration` được triển khai đầy đủ (nguồn: `guide.md` §4, §13; `explanation.md` §4).
- **Tính feature tài chính per-taxpayer**: ~15 chỉ số T1 (thanh toán, lợi nhuận, đòn bẩy) từ BCTC (nguồn: `system_flow_analysis.md` Bước 5).
- **Serving**: dashboard Taxpayer360 cho cán bộ thuế + chatbot tra cứu chỉ tiêu cho người nộp thuế (nguồn: `lakehouse_compaction_upgrade_plan.md` mục SLA).

> ⚠️ **Ghi nhận quan trọng cho phần sau**: toàn bộ nghiệp vụ hiện tại, ở **cả 9 domain** (kể cả `tax_declaration` — domain thật duy nhất), là **per-taxpayer / per-filing** (một MST, một tờ khai). Liên kết chéo duy nhất đang có (TNDN↔BCTC, mục 1.3) vẫn là **nội bộ 1 MST**, không nối 2 pháp nhân khác nhau. Tài liệu Gotix **không đề cập** bất kỳ phân tích **quan hệ liên-MST** nào (mạng lưới hóa đơn, sở hữu chéo, người đại diện chung, vòng lặp mua-bán...) — ở **bất kỳ domain nào**, không riêng gì hóa đơn. Đây chính là khoảng trắng mà đồ thị nhắm tới (mục 3), và nó sâu hơn "thiếu dữ liệu hóa đơn": **toàn bộ lakehouse hiện chưa có khái niệm "quan hệ giữa 2 pháp nhân"**.

---

## 2. Điểm đau của luồng hiện tại

### 2.1 Small files → query chậm (điểm đau đã đo, số liệu thật)
Nguồn: `query_performance_report.md`.

| Chỉ số | Trước | Sau |
|---|---|---|
| Số file Parquet vật lý (1 bảng Tier3) | **19.467 file**, TB **~8,3 KB/file** (~13 dòng/file) | **35 file** (giảm 99,8%) |
| Query 251.730 dòng (lặp phân vùng) | **~228 s (3,8 phút)** | — |
| Query bằng `toLocalIterator()` | **~783 s (13 phút)** | — |
| Sau Compaction + PyArrow | — | **5,99 s** (~38× nhanh hơn) |

Nguyên nhân gốc: ETL gia tăng ghi `overwrite_filter` liên tục cho từng tờ khai/DN → mỗi lần sinh file Parquet nhỏ; tổng bảng chỉ ~165 MB nhưng phải thực hiện **~20.000 HTTP GET** tới MinIO (nguồn: `query_performance_report.md` §2).

### 2.2 Mô hình per-file → pod churn hạ tầng
- Trigger 1 DAG/1 file XML → **~20.000 Pod Spark/ngày** trên K8s, nghẽn Airflow Scheduler (nguồn: `lakehouse_compaction_upgrade_plan.md` Phương án A).
- Sự cố thật **pod churn 2026-06-29**: hàng trăm pod chết liên tục do nhiều task commit song song vào cùng bảng (nguồn: `DATALAKE_RISK_NOTES.md` A2).

### 2.3 Nessie khóa commit ở cấp BẢNG
Hai job ghi 2 partition khác nhau của **cùng bảng** vẫn đụng 409 `CommitFailedException` → phải qua `_commit_with_retry` (nguồn: `DATALAKE_RISK_NOTES.md` A2). Hệ quả: không thể tùy tiện song song hóa ghi.

### 2.4 Trino/columnar yếu ở truy vấn quét rộng & quan hệ nhiều bước
- Query **không filter partition** hôm nay chạy được, vài tháng sau treo (nguồn: `DATALAKE_RISK_NOTES.md` F5).
- Lineage traceback hiện có (Tier2 item → Tier1 file) chỉ là **JOIN 1-hop** theo `tier1_file_id` — Trino làm tốt (nguồn: `guide.md` §11).
- **(suy luận, tài liệu Gotix không đề cập trực tiếp)**: bài toán **quan hệ nhiều bước** giữa các DN (A bán cho B, B bán cho C, C quay lại A) trên Iceberg/Trino sẽ là chuỗi **self-join đệ quy** — mỗi hop là 1 lần scan + join toàn bảng cạnh. Với mô hình columnar + small-files sẵn có, đây là kiểu truy vấn tệ nhất: không prune được partition theo quan hệ, chi phí bùng nổ theo số hop. Bằng chứng gián tiếp: hệ Nebula `detecting_cheat_by_nebula` thống kê đồ thị hóa đơn có **~2,26 triệu vòng lặp 2–4 hop** trên chỉ 98 đỉnh (nguồn: `KICH_BAN_PHAN_TICH.md` §G) — quy mô tổ hợp mà SQL quét bảng không kham nổi.

### 2.5 Dữ liệu rơi rớt im lặng & độ trễ serving
- Event Bridge chết = file nằm bronze nhưng **không gì xử lý, không báo đỏ** (nguồn: `DATALAKE_RISK_NOTES.md` G1).
- Micro-batching để trị small files kéo độ trễ dữ liệu lên **30–60 phút** — buộc phải phân tầng SLA (Silver ≤5', Gold ≤1h) (nguồn: `lakehouse_compaction_upgrade_plan.md` mục SLA).
- Redis TTL ~1h → bot có thể trả số cũ (nguồn: `DATALAKE_RISK_NOTES.md` H1).

---

## 3. NebulaGraph giải quyết được gì cho Gotix

Map điểm đau/khoảng trắng → khả năng đồ thị. Cột bằng chứng dẫn từ `detecting_cheat_by_nebula` — **nhắc lại: đây là dữ liệu mô phỏng để kiểm thử kỹ thuật, không phải dữ liệu Gotix** — nên đọc cột đó là *"kỹ thuật này đã chứng minh chạy được, có thể áp dụng lại trên bất kỳ domain Gotix nào có dữ liệu tương ứng"*, không phải *"Gotix đã có sẵn cái này"*:

| Khoảng trắng Gotix (áp dụng cho mọi domain, không riêng hóa đơn) | Khả năng NebulaGraph | Bằng chứng kỹ thuật (`detecting_cheat_by_nebula`, dữ liệu mô phỏng) |
|---|---|---|
| Không có phân tích **quan hệ liên-MST** ở bất kỳ domain nào (mục 1.4, 2.4) | Multi-hop traversal có neo điểm | Vòng lặp `AZURA→VINACO→CMS Vina→AZURA` tìm ra ~1,6s khi neo `WHERE id(c1)==...` (`KE_HOACH_IMPORT.md` §7) |
| Truy vết chuỗi quan hệ nhiều bước (dù là hóa đơn, sở hữu, hay bất kỳ liên kết nào khác) tệ trên Trino | `MATCH` pattern cố định hop, `FIND SHORTEST PATH` | Kịch bản C: gom cạnh gắn cờ → **hội tụ về 1 đầu mối AZURA** (51ms) (`KICH_BAN_PHAN_TICH.md` §C) |
| Phát hiện bất thường trên thuộc tính giao dịch/hồ sơ (gian lận, lệch chuẩn) | Pattern-matching trên thuộc tính cạnh + phân loại đỉnh | Kịch bản A bắt 6/6 (dịch vụ vô hình lặp lại, 32ms); B bắt 4/4 (hàng lệch ngành, 25ms) — **100% chính xác trên dữ liệu mô phỏng** (`KICH_BAN_PHAN_TICH.md`) |
| Rủi ro tín dụng / danh tính dùng chung (CCCD, SĐT, địa chỉ, người đại diện) — *chưa có trường liên-MST này ở bất kỳ domain Gotix nào* | Node chung → 2-hop giữa hồ sơ | (suy luận — kỹ thuật cùng dạng với "hub" ở kịch bản C, nhưng Gotix hiện không có domain nào chứa dữ liệu định danh dùng chung) |
| "2 pháp nhân X, Y có liên hệ không" (khi đã có quan hệ để duyệt) | `FIND SHORTEST PATH FROM X TO Y OVER ... UPTO 5 STEPS` | Có sẵn trong bộ kịch bản (`KICH_BAN_PHAN_TICH.md` §E) |

**Điểm mấu chốt**: Gotix hiện chấm rủi ro **theo từng DN cô lập** (feature per-mst), ở **mọi** domain, không riêng gì hóa đơn. Đồ thị bổ sung chiều **quan hệ giữa các pháp nhân** — chiều dữ liệu mà Gotix **hoàn toàn chưa có ở bất kỳ domain nào**. `detecting_cheat_by_nebula` chỉ chứng minh: MỘT KHI có dữ liệu quan hệ liên-MST (hóa đơn hay bất cứ gì khác), kỹ thuật đồ thị phát hiện được gian lận (hub, vòng lặp, dịch vụ khống) mà bảng phẳng không thấy — *"đây chính là chỗ đồ thị mạnh hơn bảng tính: nó cho thấy sự hội tụ"* (`KICH_BAN_PHAN_TICH.md` §C). Điều Gotix cần làm trước là **tạo ra dữ liệu quan hệ liên-MST đó** (xem 4.1.1 mục 1) — Nebula không tự sinh ra quan hệ nếu domain nguồn chưa có.

**Trung thực về giới hạn**: nâng khống giá giao dịch có thật (kiểu C — HAL, trong dữ liệu mô phỏng) đồ thị **không tự bắt được** (0/4), cần giá thị trường tham chiếu ngoài (`KICH_BAN_PHAN_TICH.md` §C.4). Đồ thị đưa nghi phạm **vào tầm ngắm**, không thay thế điều tra.

---

## 4. Hai hướng kiến trúc tích hợp

### 4.1 (a) Bổ sung song song — Nebula là lớp graph bên cạnh lakehouse (KHUYẾN NGHỊ)

Lakehouse **vẫn là source of truth cho toàn bộ dữ liệu**; chỉ đồng bộ sang Nebula phần **quan hệ liên-MST** khi domain nào đó sinh ra được nó (đỉnh = pháp nhân theo `mst`, cạnh = bất kỳ liên kết nào giữa 2 MST — hóa đơn, sở hữu, đại diện chung... tùy domain, KHÔNG cố định vào 1 loại). Việc này áp dụng chung cho **mọi domain hiện có và tương lai** (`tax_declaration`, `einvoice`, `risk_feature`, `compliance`, `reference_data`...), không phải một pipeline riêng cho hóa đơn.

```
┌───────────────────────────────────────────────────────────────┐
│ SOURCE OF TRUTH  —  giữ nguyên, KHÔNG đụng luồng cũ           │
│ MinIO/bronze → Airflow T1→T2→T3 → Iceberg (Nessie)            │
│ → Trino → taxpayer360 / Redis                                 │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                │   thêm 1 nhánh append — KHÔNG sửa luồng cũ
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ GRAPH SYNC JOB  —  DAG Airflow mới, batch theo ictrl_dt       │
│ 1) đọc Trino : tier2/tier3 của BẤT KỲ domain nào đã có dữ liệu│
│                thật VÀ chứa quan hệ liên-MST                  │
│ 2) map       : đỉnh taxpayer(mst) + cạnh quan hệ (+ rank)     │
│ 3) nạp       : nebula-importer / client                       │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ NebulaGraph  —  space: gotix_*   ·   graphd:9669              │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ SERVING GRAPH  —  API risk-network · dashboard "mạng lưới DN" │
└───────────────────────────────────────────────────────────────┘
```

> Bước 1 (đọc Trino) **không neo cứng vào domain `einvoice`/hóa đơn** — job này generic: chạy được với domain nào cũng được, miễn domain đó (a) có dữ liệu thật trên Trino và (b) có ít nhất 1 cặp trường định danh 2 MST khác nhau để làm 2 đầu cạnh. Xem mục 4.1.1 #1 — hiện **chưa domain nào** thỏa cả 2 điều kiện.

### 4.1.1 Yêu cầu tiên quyết — cần gì TRƯỚC KHI bắt đầu (Definition of Ready cho POC)

Sơ đồ trên giả định đã có ở đâu đó trong lakehouse dữ liệu **quan hệ liên-MST** để đọc — **thực tế Gotix chưa có, ở BẤT KỲ domain nào**. 10 yêu cầu dưới đây phải giải quyết trước khi viết dòng sync đầu tiên:

1. **Có dữ liệu nguồn chứa quan hệ liên-MST (blocker lớn nhất, sâu hơn "thiếu 1 domain").** Đây không phải chuyện riêng domain `einvoice` chưa có dữ liệu — vấn đề gốc rễ là: trong **cả 9 domain** (kể cả `tax_declaration`, domain thật duy nhất), **không bảng nào có 2 cột MST khác nhau trên cùng 1 dòng** để làm 2 đầu 1 cạnh. Liên kết chéo duy nhất hiện có (TNDN↔BCTC lookback, mục 1.3) là **nội bộ 1 MST**, không nối 2 pháp nhân. Vậy cần 2 việc, không chỉ 1:
   - (a) **Chọn domain sẽ mang dữ liệu quan hệ liên-MST đầu tiên.** `einvoice` là ứng viên tự nhiên nhất (hóa đơn luôn có MST bán + MST mua) nếu được xây, nhưng **không bắt buộc phải là nó** — domain khác cũng đủ điều kiện nếu được thiết kế thêm trường liên-MST, VD `reference_data` (người đại diện pháp luật dùng chung giữa các DN) hay mở rộng `tax_declaration` (cổ đông/công ty mẹ-con nếu tờ khai có trường đó). Business + kiến trúc dữ liệu phải **chốt domain nào đi trước**.
   - (b) **Dựng domain đó thành thật** theo khuôn `tax_declaration` (domain mẫu duy nhất có code thật): Tier1 ingest → Tier2 parse → có dữ liệu chạy qua Trino, kèm trường liên-MST rõ ràng (VD với hóa đơn: `mst_ben_ban`, `mst_ben_mua` trên cùng 1 dòng).
   - (Nguồn: `guide.md` §9 domain — 8/9 domain *"🚧 scaffold"*; `explanation.md` §"Chỉ có tax_declaration là thật".)

2. **DDL + Contract cho domain mới, đúng 2 chỗ.** Theo quy ước Gotix, thêm domain/form phải viết DDL 3 tier trong `data/domains/<domain>/schemas/` (theo mẫu `tax_declaration/schemas/README.md`). ⚠️ Contract thực tế nằm ở **2 nơi phải sửa đồng thời**: DDL (`ddl.sql`) **và** schema PyArrow hardcode trong `data/pipelines/io/iceberg.py` (`_expected_schema`) — quên 1 trong 2 là lệch schema (`guide.md` §"Contracts").

3. **Khóa cạnh ổn định (idempotency key).** Cần một trường tương đương `content_sha256`/`filing_key` cho mỗi bản ghi quan hệ để dùng làm khóa cạnh khi sync lặp lại (Airflow retry, event trùng — `DATALAKE_RISK_NOTES.md` A3). Bắt buộc có cột đóng vai trò như `rank` khi 2 MST có **nhiều bản ghi quan hệ** trong kỳ (nhiều hóa đơn, nhiều lần cùng đại diện...) — thiếu cái này từng làm mất ~50% cạnh thật trong dữ liệu mô phỏng `detecting_cheat_by_nebula` (4.608/8.976, xem mục 5.1) — bài học kỹ thuật áp dụng cho **bất kỳ domain nào** được chọn ở mục 1.

4. **DAG mới đúng convention, KHÔNG per-file.** Đặt tên `tier3_sync_graph_<domain>.py` (domain nào được chọn ở mục 1) trong `data/orchestration/airflow/dags/<domain>/` (hoặc thư mục graph riêng), trigger theo **batch `ictrl_dt`** (30–60 phút). Tuyệt đối không trigger per-file — mô hình per-file hiện tại đã gây ~20.000 pod Spark/ngày (mục 2.2); lặp lại kiểu đó cho graph sync là tự tạo thêm sự cố đã biết.

5. **Hạ tầng Nebula thật, không phải WSL demo.** Instance hiện tại (`nebula_demo`) chỉ chạy WSL2 standalone `replica_factor=1` trên máy cá nhân — không dùng được cho pipeline Airflow production. Cần 1 Nebula instance/cluster nội bộ mà Airflow worker tiếp cận được qua network (không phải qua WSL localhost).

6. **Quản lý credential kết nối.** Airflow cần 1 **Connection/Variable** riêng lưu host/port/user/pass Nebula — hiện chưa có gì tương đương (khác với Trino/MinIO đã có sẵn cấu hình).

7. **Đối soát + cảnh báo khi lệch.** Theo đúng tinh thần DQ tối thiểu Gotix đang áp cho BCTC, cần job đối soát `count(Trino tier2/tier3 của domain nguồn) == count(Nebula edges)` theo từng `ictrl_dt`, và báo lỗi rõ ràng khi lệch — tránh lặp lại kiểu "dữ liệu rơi rớt im lặng, không báo đỏ" đã ghi nhận ở Event Bridge (`DATALAKE_RISK_NOTES.md` G1).

8. **Lớp API chặn giữa người dùng và Nebula (guardrail bắt buộc).** Không cho phép gõ nGQL tự do vào production. Cần 1 API serving (giống `taxpayer360`) **ép cứng** mọi truy vấn phải neo điểm (`WHERE id(x)==...`) + cấm `*` biến thiên độ dài — bỏ qua sẽ lặp lại crash graphd đã xảy ra thật khi kiểm thử với dữ liệu mô phỏng `detecting_cheat_by_nebula` (mục 5.3).

9. **Quyết định phạm vi quan hệ ban đầu (tránh over-modeling).** Vì mục 1 xác nhận **chưa có domain nào** sẵn dữ liệu liên-MST, đây thực chất là quyết định thiết kế từ đầu, không phải "mở rộng thêm": chốt rõ domain đầu tiên chỉ mang **1 loại quan hệ** (VD chỉ "xuất hóa đơn giữa 2 MST" nếu chọn `einvoice`), chưa vội cộng dồn nhiều loại quan hệ khác nhau (sở hữu, đại diện, hóa đơn...) vào cùng 1 lần — tránh phá tính tối giản khuyến nghị ở mục 5.2.

10. **Ít nhất 1 người biết nGQL.** Đội hiện mạnh Python/Iceberg/Trino/Airflow, chưa ai quen tư duy đồ thị. Tài sản có sẵn để giảm chi phí học: `nebula_demo` console + `schemas/invoice_graph.md` (mục 5.6) — lưu ý đây là tài liệu học kỹ thuật Nebula nói chung, không phải schema sẽ dùng cho Gotix (xem mục 6).

**Vì sao khả thi cao**:
- Không sửa `iceberg.py`, không đổi DAG hiện có — chỉ **thêm 1 DAG tier3-graph** dạng batch (đúng định hướng gom lô của hệ thống, tránh pod churn — `DATALAKE_RISK_NOTES.md` D3).
- Nebula chỉ giữ **quan hệ**, không giữ bảng lớn → tránh đúng điểm yếu của Nebula (đồ thị dày dễ nổ query).
- Sync theo `ictrl_dt` batch (30–60') khớp SLA Gold hiện tại — không tạo yêu cầu real-time mới.

**Chi phí/rủi ro**: thêm 1 hệ cần vận hành; dữ liệu graph **eventually-consistent** (trễ so với lake); phải quản lý idempotency sync (dùng `content_sha256`/`filing_id` làm khóa cạnh — có sẵn trong lake).

### 4.2 (b) Thay thế hoàn toàn — đánh giá thẳng thắn

**KHÔNG khả thi và không nên.** Lý do cụ thể:

| Phần việc Gotix | Thay bằng Nebula được? | Vì sao |
|---|---|---|
| Lưu XML raw immutable (bằng chứng đối soát) | ❌ Không | Bronze là chứng cứ pháp lý, object storage; đồ thị không phải nơi lưu file (`DATALAKE_RISK_NOTES.md` F2) |
| Bảng chỉ tiêu/feature lớn, long-format, hàng trăm nghìn dòng | ❌ Không | Đây là **analytics/columnar** — Trino quét cột nhanh; Nebula là property graph, không tối ưu quét toàn bảng tính toán (`query_performance_report.md`) |
| BI/dashboard, tính 15 tỷ số tài chính per-DN | ❌ Không | Bài toán aggregate/scan, không phải traversal |
| ACID versioning / time-travel / audit lineage | ❌ Không | Nessie + Iceberg đang lo; kiến trúc audit gắn chặt `run_id`/snapshot (`DATALAKE_RISK_NOTES.md` A6) |
| Phân tích quan hệ nhiều bước, hub, vòng lặp | ✅ Có — **và chỉ phần này** | Bằng chứng kỹ thuật `detecting_cheat_by_nebula` (dữ liệu mô phỏng) |

**Kết luận mục 4**: **Chọn hướng (a) — bổ sung song song.** Lý do một câu: Nebula chỉ vượt trội đúng ở chiều **quan hệ giữa các thực thể**, còn phần lõi của Gotix (lưu raw immutable, analytics columnar per-taxpayer, ACID/time-travel/lineage) là thế mạnh của lakehouse mà đồ thị không thay được — nên đặt Nebula làm **lớp truy vết bên cạnh**, không phải thay thế.

---

## 5. Khó khăn & rủi ro

1. **Đồng bộ lakehouse→Nebula**: phải idempotent (Airflow retry, event trùng — `DATALAKE_RISK_NOTES.md` A3). Dùng khóa cạnh ổn định `(id_ban_ghi_quan_he, mst_src, mst_dst, content_sha256)` — cụ thể hóa tùy domain nguồn (VD `so_hoa_don` nếu là hóa đơn); đặc biệt **cạnh song song** giữa cùng cặp MST bắt buộc có `rank` — bài học kỹ thuật từ dữ liệu mô phỏng: thiếu `rank` mất ~50% dữ liệu (4.608/8.976 cạnh) (`KE_HOACH_IMPORT.md` §7).
2. **Mô hình hóa đồ thị**: chọn cái gì làm đỉnh/cạnh, và **chọn domain nguồn nào trước** (mục 4.1.1 #1). Nguy cơ over-modeling. Bắt đầu tối giản: đỉnh = `taxpayer (mst)`, cạnh = **1 loại quan hệ duy nhất** của domain đầu tiên được chọn — không cộng dồn nhiều loại quan hệ ngay từ đầu.
3. **Giới hạn Nebula trên đồ thị dày** (bằng chứng thật, phải tôn trọng): `MATCH` đa chặng **không neo điểm** hoặc dùng `*` biến thiên độ dài → **treo/crash graphd** trên đồ thị ~91 cạnh/đỉnh (`KE_HOACH_IMPORT.md` §6–7; `KICH_BAN_PHAN_TICH.md` §G). Ràng buộc vận hành: luôn `WHERE id(x)=="..."`, chuỗi hop cố định, cấm `*`.
4. **Vận hành**: Nebula mẫu chạy WSL2 standalone `replica_factor=1` — production cần cluster HA, backup, monitor graphd/storaged/metad (`CLAUDE.md`). Sau crash phải dọn `pids/*.pid` + restart (`KE_HOACH_IMPORT.md` §6).
5. **Đồng bộ trạng thái "mới nhất"**: DN nộp lại tờ khai (`so_lan` tăng) → cạnh cũ phải superseded, không nhân đôi. Quy tắc latest cố định của lake (`max(so_lan)→ngày→load_ts`) phải áp cả khi sync (`DATALAKE_RISK_NOTES.md` B2).
6. **Chi phí & kỹ năng**: đội đang mạnh Python/Iceberg/Trino/Airflow; nGQL + tư duy đồ thị là kỹ năng mới. Có sẵn tài sản nội bộ (`nebula_demo` console + schema `invoice_graph.md`) giảm chi phí học.
7. **Consistency**: graph trễ so với lake (eventually-consistent) — không dùng cho tra cứu tức thời của người nộp thuế (đó là việc của Silver ≤5', `lakehouse_compaction_upgrade_plan.md`).

---

## 6. Ý tưởng ứng dụng — kỹ thuật đã chứng minh (A) vs áp dụng khi Gotix có dữ liệu thật (B)

Vì Gotix hiện **không có domain nào** chứa quan hệ liên-MST (mục 4.1.1 #1), phần này tách rõ 2 lớp — đừng lẫn:
- **(A) Đã chứng minh** — chạy thật trên `detecting_cheat_by_nebula`, **dữ liệu mô phỏng 86 công ty giả lập**, chỉ để kiểm chứng kỹ thuật.
- **(B) Áp dụng cho Gotix** — cùng kỹ thuật đó, diễn giải tổng quát cho **bất kỳ domain thật nào** Gotix chọn mang dữ liệu quan hệ liên-MST tới (không cố định là hóa đơn).

### Schema tổng quát (không cố định vào 1 domain)

```
TAG taxpayer { mst(VID), ten_nnt, linh_vuc, dia_chi, ... }   // đỉnh = pháp nhân, khóa mst đã dùng xuyên Gotix

EDGE <quan_he_lien_mst> { ...thuộc tính tùy domain nguồn..., rank }
     // ví dụ cụ thể theo từng domain khi có dữ liệu thật:
     //   domain einvoice        → EDGE xuat_hoa_don   {so_hoa_don, ngay_xuat, mo_ta, tien_chua_thue, loai_gd, rank}
     //   domain reference_data  → EDGE dai_dien_chung  {mst_nguoi_dai_dien, tu_ngay, rank}
     //   domain risk_feature    → EDGE co_dong_chung   {ty_le_so_huu, rank}
```
`TAG taxpayer` dùng `mst` làm VID — nhất quán với khóa `mst` Gotix đã dùng xuyên mọi domain (mục 1.2). `EDGE` cụ thể **chỉ tồn tại khi domain tương ứng có dữ liệu thật** — không có sẵn hôm nay.

### (A) Kỹ thuật đã chứng minh trên `detecting_cheat_by_nebula` (dữ liệu mô phỏng, TAG/EDGE khác tên: `company`/`xuat_hoa_don`)

1. **Vòng lặp khép kín (circular loop)** — cờ đỏ kinh điển cho giao dịch lòng vòng.
   `MATCH p=(a)-[:xuat_hoa_don]->(b)-[:xuat_hoa_don]->(c)-[:xuat_hoa_don]->(a) WHERE id(a)=="<mst nghi vấn>" RETURN p LIMIT 50;`
   → đã chạy thật trên dữ liệu mô phỏng, ra vòng AZURA→VINACO→CMS Vina→AZURA.

2. **Hub gian lận (hội tụ nhiều đầu mối đáng ngờ về 1 đích)** — kịch bản C.
   Gom cạnh gắn cờ → `WITH c2, count(e), collect(DISTINCT id(c1))` → đích có nhiều nguồn bị cờ độc lập = đầu mối.

3. **Mẫu lặp lại bất thường giữa 1 cặp thực thể** — kịch bản A (dịch vụ vô hình lặp ≥3 lần cùng 1 cặp bán-mua). Bắt tự động, 100% chính xác trên dữ liệu mô phỏng.

4. **Thuộc tính cạnh mâu thuẫn với phân loại đỉnh** — kịch bản B (hàng sắt thép/thiết bị VP nhưng bên bán đăng ký ngành hóa chất/khai khoáng). Lưu ý bẫy dấu tiếng Việt khi lọc theo mô tả và ngành (`KICH_BAN_PHAN_TICH.md` §B).

### (B) Áp dụng cho Gotix khi có dữ liệu thật tương ứng (suy luận — chưa có domain nào sẵn sàng)

- **Nếu domain `einvoice` thành thật** (kịch bản gần nhất với `detecting_cheat_by_nebula`): áp trực tiếp kỹ thuật (1)–(4) ở trên lên `EDGE xuat_hoa_don`, đổi tên TAG/EDGE cho khớp namespace Gotix (`tier2.einvoice_...`) — vòng lặp khép kín, hub, dịch vụ lặp lại, lệch ngành đều dùng lại được nguyên xi.
- **Nếu domain `reference_data`/`taxpayer` bổ sung "người đại diện pháp luật"**: TAG `nguoi_dai_dien` + `EDGE dai_dien_chung` → phát hiện sở hữu chéo / nhiều DN dùng chung 1 người đại diện, kỹ thuật giống hệt "hub" ở (2) nhưng đổi loại cạnh.
- **Thanh toán/dòng tiền giá trị lớn**: chỉ khả thi nếu domain nguồn có trường hình thức thanh toán — hiện **không domain nào có trường này** (kể cả trong dữ liệu mô phỏng `detecting_cheat_by_nebula`, xem `KICH_BAN_PHAN_TICH.md` cuối §G).
- Tài liệu Gotix hiện **không đề cập** bất kỳ dữ liệu định danh dùng chung (CCCD/SĐT/địa chỉ đại diện) nào — mọi ý ở mục (B) là **suy luận**, cần business Gotix xác nhận trước khi thiết kế domain.

---

## 7. Kế hoạch triển khai theo giai đoạn

⚠️ Tách rõ **GĐ 0** (đã xong, dùng dữ liệu mô phỏng — chỉ chứng minh kỹ thuật) khỏi các giai đoạn sau (dùng dữ liệu Gotix thật — chưa thể bắt đầu tới khi có domain nguồn, mục 4.1.1 #1). Đừng nhầm GĐ 0 là "đã có POC trên Gotix".

| GĐ | Mục tiêu | Việc làm | Tiêu chí thành công |
|---|---|---|---|
| **GĐ 0 — Chứng minh kỹ thuật** (đã hoàn thành) | Xác nhận NebulaGraph + pipeline import + query pattern chạy đúng, an toàn | Dựng `detecting_cheat_by_nebula` (98 đỉnh/8.976 cạnh, **dữ liệu mô phỏng**), chạy 4 kỹ thuật phát hiện mục 6(A) | Đã đạt: bắt 10/14 hóa đơn khống tự động, 100% chính xác; query neo điểm <2s; không crash graphd khi tuân thủ guardrail |
| **POC Gotix thật** (2–4 tuần, **chỉ bắt đầu SAU khi có domain nguồn** — mục 4.1.1 #1) | Chứng minh giá trị trên dữ liệu Gotix thật (lần đầu tiên, domain bất kỳ) | Chốt domain nguồn (VD `einvoice`) + dựng dữ liệu thật (mục 4.1.1 #1); viết script export Trino tier2/tier3 của domain đó → CSV → `nebula-importer`; áp lại kỹ thuật tương ứng ở mục 6(B) | Đồ thị dựng được từ dữ liệu Gotix thật (không phải mô phỏng); tìm ra ≥1 phát hiện có ý nghĩa nghiệp vụ; query neo điểm <2s |
| **Pilot** (1–2 tháng) | Tự động hóa sync + serving nội bộ | Thêm 1 DAG Airflow batch `tier3_sync_graph_<domain>` (đúng chuẩn gom lô, idempotent theo khóa cạnh + `rank`); dựng Nebula HA nhỏ (thoát WSL standalone); API/dashboard "mạng lưới DN" cho 1 nhóm cán bộ | Sync đối soát khớp count Trino↔Nebula theo `ictrl_dt`; cán bộ tìm ra ≥1 hub thật; không crash graphd (query đều neo điểm) |
| **Production** (quý tiếp) | Vận hành ổn định, mở rộng sang domain khác | Cluster Nebula HA + backup + monitor; đưa bảng graph vào lịch bảo trì; guardrail nGQL (cấm `*`, bắt buộc neo — nhúng vào layer API); lần lượt mở rộng thêm domain/loại quan hệ khác khi có dữ liệu | Đối soát tự động Bronze→T1→T2→T3→Graph không lệch (kiểu `DATALAKE_RISK_NOTES.md` G1); SLA graph ≤1h khớp Gold; runbook sự cố graphd |

Nguyên tắc xuyên suốt: **không đụng luồng lake hiện có**, graph là nhánh append thêm cho **toàn bộ lakehouse** (không riêng 1 domain); mọi truy vấn traversal đều **neo điểm + hop cố định** để tránh giới hạn Nebula đã biết; và **không lẫn GĐ 0 (mô phỏng) với các giai đoạn dùng dữ liệu Gotix thật**.

---

### Nguồn tham chiếu
- Gotix lakehouse: `hanoiTax/guide.md`, `hanoiTax/system_flow_analysis.md`, `hanoiTax/explanation.md`
- Điểm đau/vận hành: `hanoiTax/query_performance_report.md`, `hanoiTax/lakehouse_compaction_upgrade_plan.md`, `hanoiTax/DATALAKE_RISK_NOTES.md`
- Dữ liệu mẫu lake: `hanoiTax/mock_lakehouse/{bronze,silver,gold}/*`
- Bằng chứng kỹ thuật (dữ liệu mô phỏng, KHÔNG phải dữ liệu Gotix): `detecting_cheat_by_nebula/KE_HOACH_IMPORT.md`, `detecting_cheat_by_nebula/KICH_BAN_PHAN_TICH.md`
- Nền tảng Nebula: `CLAUDE.md`, `nebula_demo/schemas/invoice_graph.md`
