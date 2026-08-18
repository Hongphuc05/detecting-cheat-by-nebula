# N4 — Nâng Data Contract từ 60/100 lên tối đa

> Nguồn yêu cầu: giao việc N1-N5 của Phúc (18/08/2026), N4 là 1 trong 5 việc, ưu tiên làm sớm.
> File này viết TRƯỚC khi code — mọi khẳng định đều đã đọc trực tiếp code/tài liệu thật, không
> suy đoán. Phần nào chưa xác nhận được sẽ ghi rõ "CẦN HỎI PHÚC", không tự bịa.

## 1. Yêu cầu gốc (nguyên văn)

- Sửa `ingest_trino_gotix.py` đọc `tier2.company_industry` (lọc `nganh_chinh = true`) đổ vào
  `sector`.
- Rà 3 cột rủi ro của node Company (đang thiếu) — cột nào lấy được từ feature Tier3 hiện có
  (`t2_tax_risk`, `t2_invoice_risk`) thì nối luôn.
- Tiêu chí xong: Company có `sector` thật (không phải placeholder) + báo cáo chấm lại điểm data
  contract, ghi rõ mục nào còn thiếu và vì sao.

## 2. ⚠️ Phát hiện quan trọng — hiện trạng KHÁC với mô tả trong ticket

Đọc trực tiếp `pipeline/ingest_trino_gotix.py` (không suy đoán): **việc nối `sector` từ
`company_industry` đã được VIẾT trong code từ 12/08/2026** (CTE `latest_sector`, dòng 203-214 —
ưu tiên `nganh_chinh=true` bằng `ORDER BY CASE WHEN nganh_chinh THEN 0 ELSE 1 END`), đúng chính
xác yêu cầu ở mục 1. Dòng comment đầu file cũng ghi rõ: *"domain company da co du lieu that nen
KHONG con hardcode 'Chua ro' nua"*.

Nguồn gây hiểu nhầm trong ticket — 2 tài liệu đang **lệch pha với code**:
1. `gotix-datalake/docs/BAO_CAO_TICH_HOP_GOTIX_NEBULA.md` §4/§7 — viết **05/08/2026**, tức là
   TRƯỚC khi sửa code 12/08. Vẫn còn dòng "sector: placeholder... hiện đang hard-code 'Chưa rõ'"
   — đây là bản cũ, chưa cập nhật theo code mới.
2. `gotix-datalake/data/domains/company/README.md:38` — ghi *"việc sửa ingest_trino_gotix.py để
   đọc bảng này là task riêng, chưa làm trong domain này"* — câu này đúng theo nghĩa "domain
   company không tự làm", nhưng gây hiểu lầm là chưa ai làm ở đâu cả — thực ra phía
   `detecting_cheat_by_nebula` đã làm.

**Nhưng có 1 việc thật sự CHƯA xong**: chính comment trong code (dòng 24-27) tự ghi *"ban SQL
merge nay [SQL_COMPANIES] van CHUA duoc chay thuc te tren Trino, can chay 1 lan de xac nhan truoc
khi coi la 'da hoat dong'"*. Tức là: **code đã viết đúng, nhưng chưa từng chạy thử trên Trino
thật để xác nhận nó hoạt động** (khác "viết sai" — là "viết xong nhưng chưa kiểm chứng").

**Ảnh hưởng đến việc N4 lần này**:
- Mục 1 của ticket ("sửa code đọc company_industry") — **không cần sửa gì thêm**, chỉ cần
  **chạy thử + xác nhận thật** trên Trino, rồi cập nhật lại 2 tài liệu đang lệch pha ở trên.
  Việc chính chuyển từ "viết code" sang "kiểm chứng + đính chính tài liệu".
- Trọng tâm thật của N4 dồn vào mục 2 (3 cột rủi ro) — đây mới là phần code thật sự chưa có.

## 3. "3 cột rủi ro" là gì — chưa có định nghĩa sẵn, cần chốt trong lúc làm N4 này

Đã tìm khắp workspace (README, data contract, schema `.ngql`, `validate_contract.py`) — **không
có nơi nào định nghĩa sẵn tên 3 cột rủi ro cụ thể**. Dòng "3 cột rủi ro: thiếu" trong
`BAO_CAO_TICH_HOP_GOTIX_NEBULA.md` §4 chỉ là 1 ghi chú ngắn, không kèm danh sách.

Đối chiếu công thức chấm điểm thật (`validate_contract.py`, dòng 45): điểm tối đa 100 = 30 (cân
bằng dòng tiền) + 20 (thời gian) + 10 (VAT) + 25 (liên kết ngầm) + 15 (thành viên rủi ro). Trong
5 phần này, **chỉ "thành viên rủi ro" (15đ, dựa vào `status`/`established_date`) và "VAT" (10đ,
dựa vào `TRADES.total_vat` — đã có đủ) tồn tại trong công thức đang chạy** — không có phần nào
tên là "3 cột rủi ro thuế/hoá đơn". Kết luận: **3 cột rủi ro trong ticket là đề xuất MỚI**, chưa
từng được đưa vào công thức chấm điểm — N4 vừa phải chọn cột, vừa phải quyết định có tính điểm
hay chỉ hiển thị thêm thông tin.

**3 ứng viên ban đầu** (đọc trực tiếp `compute_gtgt_tndn_t2.py` + `compute_invoice_risk.py`, đều
tính theo `(mst, năm)` — cần chọn năm mới nhất/mst):

| # | Nguồn | formula_id | Ý nghĩa |
|---|---|---|---|
| 1 | `t2_tax_risk` | `TTHN-T2-D08-002` | Book-Tax gap (thu nhập tính thuế − lợi nhuận kế toán) |
| 2 | `t2_tax_risk` | `TTHN-T2-D06-001` | Tỷ lệ VAT đầu ra/đầu vào |
| 3 | `t2_invoice_risk` | `TTHN-T2-D07-001`/`D07-002` | Tỷ lệ hoá đơn điều chỉnh / độ lệch Benford |

> **Kiểm tra thật trên Trino (18/08/2026, không đoán từ code) phát hiện #2 không dùng được**:
> `SELECT DISTINCT feature_name FROM tier3.tax_declaration_gtgt_tndn_t2_feature_value` — **không
> có dòng nào tên `TTHN-T2-D06-001`** (0 dòng, không phải null) vì công thức này (`compute_t2_from_gtgt`,
> dòng 474-514 file gốc) cần tờ khai GTGT (842) mà domain `tax_declaration` **chưa bootstrap dữ
> liệu GTGT thật** trong sandbox này — khớp đúng cảnh báo đã có trong `ingest_trino_gotix.py`
> dòng 22-23. Đếm thật (đối chiếu `count(DISTINCT mst)`):
>
> | feature_name | Nguồn | Số dòng | Số MST có giá trị thật |
> |---|---|---|---|
> | `TTHN-T2-D08-002` (Book-Tax gap) | `t2_tax_risk` | 2 | **1/350** |
> | `TTHN-T2-D06-001` (VAT tỷ lệ) | `t2_tax_risk` | 0 | **0/350** — chưa tồn tại |
> | `TTHN-T2-D07-001` (Tỷ lệ hoá đơn điều chỉnh) | `t2_invoice_risk` | 77 | **13/350** |
> | `TTHN-T2-D07-002` (Benford χ²) | `t2_invoice_risk` | 77 (19 non-null) | ít hơn 13/350 (cần ≥100 hoá đơn/mst) |
>
> **Đổi ứng viên #2** → bỏ `D06-001` (0 dòng thật, join sẽ luôn ra NULL 100% — không phải "nối
> được" theo nghĩa ticket dùng, mà là domain nguồn chưa có dữ liệu), thay bằng **`D07-002`**
> (Benford χ², vẫn thuộc `t2_invoice_risk` — đã có ở ứng viên #3, dùng cả 2 mã của cùng bảng để
> đủ 3 cột với dữ liệu thật hiện có).

**3 cột chốt cuối (18/08/2026, có dữ liệu thật hôm nay, không chỉ có code)**:

| # | Nguồn | formula_id | Ý nghĩa | Độ phủ toàn bảng tier3 | Độ phủ THẬT sau khi chạy `SQL_COMPANIES` (lọc `transacting_mst`) |
|---|---|---|---|---|---|
| 1 | `t2_tax_risk` | `TTHN-T2-D08-002` | Book-Tax gap (VND) | 1 mst | **0/350** — mst duy nhất có dữ liệu KHÔNG nằm trong 350 công ty có giao dịch |
| 2 | `t2_invoice_risk` | `TTHN-T2-D07-001` | Tỷ lệ hoá đơn điều chỉnh | 13 mst | **5/350** |
| 3 | `t2_invoice_risk` | `TTHN-T2-D07-002` | Độ lệch Benford (χ²) | 13 mst (19 dòng non-null) | **2/350** (cần ≥100 hoá đơn/mst) |

> Đã CHẠY THẬT `ingest_trino_gotix.py` sau khi sửa code (18/08/2026, không chỉ đọc SQL suy đoán)
> — kết quả đúng như cột cuối bảng trên. Số "độ phủ toàn bảng" (1, 13 mst) đo TRƯỚC khi áp bộ lọc
> `transacting_mst`; sau khi lọc đúng theo thiết kế pipeline (chỉ nạp công ty CÓ giao dịch —
> mục "CHỐT 12/08/2026" trong file), độ phủ thực tế còn thấp hơn nữa, kể cả về 0/350 với cột 1.

**Cần ghi rõ trong báo cáo N4** (không che số liệu): độ phủ hiện tại RẤT THẤP (0-5/350 công ty)
— đúng bản chất "để trống thật hơn suy diễn" đã dùng cho `sector`, KHÔNG phải bug. Cột 1
(`book_tax_gap`) hiện **0/350 công ty có giá trị** vì công ty duy nhất có dữ liệu thuế không
giao dịch qua hoá đơn điện tử trong sandbox này — code đúng, join đúng, chỉ là dữ liệu 2 nguồn
(tax_declaration vs einvoice) chưa giao nhau. Domain `tax_declaration`/`einvoice` càng bootstrap
thêm dữ liệu thật (đặc biệt cho các mst đang giao dịch) thì 3 cột này tự động phủ rộng hơn,
không cần sửa code lần sau.

> **Đã hỏi lại Phúc: "3 cột này là tier2 hay tier3?"** — đã kiểm tra lại (grep trực tiếp
> `feature_set` trong `compute_gtgt_tndn_t2.py`/`compute_invoice_risk.py`): tiền tố `t2_` KHÔNG
> có nghĩa "lưu ở tier2" — đó là tên gọi feature_set, đặt theo **nguồn dữ liệu ĐẦU VÀO** (tờ khai
> GTGT/TNDN + hoá đơn ở tier2), còn **kết quả tính ra vẫn ghi vào bảng tier3**
> (`tier3.tax_declaration_gtgt_tndn_t2_feature_value`, `tier3.einvoice_invoice_risk_feature_value`
> — đã xác nhận ở mục 4). File này cũng có `feature_set = "t3_network_invoice"` (tính từ chiều
> MUA, nhìn sang nhà cung cấp) nằm CÙNG bảng tier3 đó — xác nhận tier2/tier3 trong tên chỉ là quy
> ước đặt tên nguồn, không phải vị trí lưu trữ. **Kết luận: 3 ứng viên đúng là dữ liệu tier3, phù
> hợp với ticket ("feature tier3 hiện có").**

**Đã chốt (Phúc duyệt 18/08/2026): dùng đúng 3 ứng viên trên** — không cần chọn khác.

**Đã chốt câu hỏi thứ 2 — có tính vào điểm chấm 0-100 không?** Quyết định: **KHÔNG tính điểm,
chỉ nối vào Company node để hiển thị thêm thông tin.** Lý do (đọc kỹ `validate_contract.py`
dòng 47/272-293/340-347 để cân đánh đổi thật, không đoán):

1. **Ngôn ngữ ticket dùng "nối", không dùng "chấm điểm"/"trọng số"** — giống đúng cách ticket
   nói về `sector` ("đổ vào sector", cũng không tính điểm). Tiêu chí hoàn thành ("Node Company có
   sector thật... báo cáo chấm lại điểm... ghi rõ mục nào còn thiếu và vì sao") chỉ yêu cầu BÁO
   CÁO điểm thật, không bắt điểm phải chạm 100.
2. **Gap 40 điểm hiện tại (60/100) không liên quan tới rủi ro thuế/hoá đơn** — đọc code:
   `max_score = 100`, trừ đúng khi 1 trong 2 `SIGNAL_GROUPS` không có probe nào `pass`:
   `hidden_link` (-25, cần 1/4 trong legal_rep/owns/shares_address/shares_phone) và
   `risky_member` (-15, cần `status_date`). `100 − 25 − 15 = 60` — khớp chính xác con số "60/100"
   trong tên ticket. Tức là: **40 điểm đang mất nằm ở dữ liệu ĐKKD (liên kết ngầm + trạng thái
   doanh nghiệp), không phải ở thiếu dữ liệu thuế/hoá đơn.** Dù có tính điểm cho 3 cột rủi ro mới
   hay không, điểm 60/100 hiện tại **không nhích lên được** nhờ việc N4 — muốn lên tối đa phải xử
   lý đúng 2 nhóm ĐKKD đó (nằm ngoài phạm vi N4). Đây là điều **phải ghi rõ trong báo cáo**, không
   che đi — tên ticket ("60/100 lên tối đa") đặt kỳ vọng sai so với cơ chế chấm điểm thật.
3. **Đánh đổi nếu chọn tính điểm**: phải thêm 1 `SIGNAL_GROUP` mới vào **2 nơi** — cả
   `validate_contract.py` VÀ `detect_circular_trading.py` (nơi giữ công thức 0-100 thật, có
   comment tự nhắc "phải KHỚP"). Phải tự đặt trọng số mới (bao nhiêu điểm hợp lý? lấy từ đâu bù
   vào 100?) — không có cơ sở khách quan để chọn số, tự bịa số là vi phạm rule trung thực. Nặng
   hơn: sửa `detect_circular_trading.py` là sửa **nguồn chân lý duy nhất** của thuật toán chấm
   điểm chu trình — ảnh hưởng tới xếp hạng nguy cơ của MỌI công ty, MỌI lần chạy trước/sau N4,
   không chỉ hiển thị thêm. Đúng loại rủi ro đã tránh ở mục 6 (không sửa `compute_gtgt_tndn_t2.py`
   /`compute_invoice_risk.py`) — nay áp dụng luôn cho `detect_circular_trading.py`.
4. **Đánh đổi nếu KHÔNG tính điểm**: không có — chỉ thêm thuộc tính hiển thị, không đụng công
   thức lõi, không rủi ro lệch 2 nơi giữ điểm. Đây là lựa chọn an toàn hơn và đúng phạm vi ticket
   mô tả ("nối luôn" — không nói "chấm điểm lại").

→ **Quyết định cuối: không tính điểm.** Chỉ sửa `ingest_trino_gotix.py` + schema `.ngql`, KHÔNG
đụng `validate_contract.py`/`detect_circular_trading.py`. Báo cáo N4 sẽ nêu rõ: 3 cột rủi ro đã
nối thành công nhưng không đổi `max_achievable_score`, và giải thích đúng lý do (mục 2 trên) để
Phúc không hiểu nhầm N4 "chưa làm xong" khi thấy điểm không đổi.

> **Đã CHẠY THẬT `validate_contract.py` trên space test (18/08/2026, Bước 3)** — kết quả đo được:
> **100/100**, KHÔNG phải 60/100 như tên ticket. Lý do: `legal_rep` (86 cặp công ty chung người
> đại diện) và `status_date` (342/350 công ty có `established_date`/`status`) đều đang `pass`
> trong dữ liệu trino_gotix hiện tại — 2 nhóm ĐKKD gây mất điểm ở mục 3 KHÔNG bị mất trong môi
> trường đo hôm nay. Con số "60/100" trong tên ticket là **số cũ, đo ở thời điểm/môi trường khác**
> (có thể trước 12/08/2026 khi `legal_rep`/`status_date` chưa có nguồn dữ liệu thật) — giống đúng
> kiểu lệch pha đã phát hiện ở mục 2 với `sector`. Báo cáo N4 phải nêu số đo THẬT hôm nay (100/100)
> thay vì lặp lại "60/100" của ticket — không tự suy diễn N4 "nâng điểm từ 60 lên 100" khi thực tế
> điểm đã ở mức tối đa từ trước khi N4 bắt đầu.

## 4. Phạm vi kỹ thuật — nối được không, và bằng cách nào

- Cả 2 nguồn (`tier2.*` và `tier3.*`) đều nằm trong **cùng 1 Trino, cùng catalog `nessie`** —
  chỉ khác schema (`tier2` vs `tier3`). `ingest_trino_gotix.py` đang mở kết nối với
  `schema="tier2"` (dòng 309) nhưng Trino cho phép chỉ định catalog.schema đầy đủ trong câu SQL
  (`nessie.tier3.<bảng>`) mà không cần đổi schema kết nối — nối được, không cần hạ tầng mới.
- 2 bảng nguồn: `tier3.tax_declaration_gtgt_tndn_t2_feature_value` (cột `mst`, `fiscal_year`,
  `feature_name`, `feature_value_num`) và `tier3.einvoice_invoice_risk_feature_value` (cột `mst`,
  `fiscal_year`, `feature_name`, `feature_value_num`) — dạng long-format (1 dòng/1 chỉ tiêu), cần
  lọc đúng `feature_name` + lấy `fiscal_year` mới nhất mỗi `mst` (giống mẫu `latest_sector` đã có
  trong file — 1 CTE `ROW_NUMBER() OVER (PARTITION BY mst ORDER BY fiscal_year DESC)`).
- Rủi ro cần lưu ý: bảng `t2_tax_risk`/`t2_invoice_risk` **không phải mọi `mst` đều có** (chỉ
  công ty có tờ khai GTGT/TNDN hoặc hoá đơn điện tử mới được tính) — cột rủi ro trên Company sẽ
  `NULL` cho công ty không có dữ liệu, đúng tinh thần "để trống thật hơn suy diễn" đã dùng nhất
  quán trong file này (không tự bịa số 0).

## 5. Việc liên quan tới báo cáo chấm lại điểm

`BAO_CAO_TICH_HOP_GOTIX_NEBULA.md` §4/§7 cần viết lại theo đúng hiện trạng (không chỉ vì N4, mà
vì đang lệch pha với code sẵn có trước cả N4):
- `sector`: từ "placeholder" → "có nguồn thật, chờ chạy xác nhận lần đầu trên Trino thật".
- 3 cột rủi ro: từ "thiếu" → tuỳ kết quả mục 3-4 (nối được bao nhiêu/3, cột nào không nối được
  và lý do — VD thiếu dữ liệu nguồn cho phần lớn `mst`).
- Không tự nâng số điểm tổng (60/100 → X/100) nếu 3 cột rủi ro KHÔNG được đưa vào công thức chấm
  điểm thật (`validate_contract.py`/`detect_circular_trading.py`) — nếu chỉ hiển thị thêm thông
  tin, điểm tối đa hợp đồng dữ liệu (data contract) không đổi, chỉ đổi mục "trạng thái".

## 6. Phạm vi ĐỤNG tới — chỉ những chỗ này, không hơn

- `detecting_cheat_by_nebula/pipeline/ingest_trino_gotix.py` — thêm SQL đọc `tier3.*`, thêm cột
  vào `fetch_companies()`.
- `detecting_cheat_by_nebula/schemas/detecting_cheat_by_nebula.ngql` — thêm thuộc tính vào
  `CREATE TAG Company`.
- `detecting_cheat_by_nebula/pipeline/validate_contract.py` — **KHÔNG sửa** (đã chốt mục 3: 3 cột
  rủi ro không tính điểm, chỉ hiển thị) — chỉ CHẠY để lấy điểm thật cho báo cáo, không đổi code.
- `gotix-datalake/docs/BAO_CAO_TICH_HOP_GOTIX_NEBULA.md` — cập nhật lại điểm/trạng thái.
- `gotix-datalake/data/domains/company/README.md:38` — sửa câu đang gây hiểu lầm "chưa làm".
- KHÔNG đụng: `compute_gtgt_tndn_t2.py`/`compute_invoice_risk.py` (chỉ ĐỌC feature có sẵn, không
  sửa công thức tính — tránh đúng rủi ro đã ghi nhận ở việc 1.6 trước đó: viết lại công thức có
  rủi ro lệch bản gốc).

## 7. Đã chốt với Phúc (18/08/2026) — không còn việc phải hỏi trước khi code

1. Dùng đúng 3 ứng viên ở mục 3 (Book-Tax gap, tỷ lệ VAT đầu ra/đầu vào, tỷ lệ hoá đơn điều
   chỉnh/Benford) — đã xác nhận đều là dữ liệu tier3 thật.
2. Không tính vào điểm 0-100 — chỉ hiển thị thêm thuộc tính trên Company node. Lý do + đánh đổi
   đã phân tích đầy đủ ở mục 3.

## 8. Nhánh/PR (đã chốt với Phúc 18/08/2026)

- `detecting_cheat_by_nebula` — **không tạo nhánh riêng**, sửa trực tiếp trên `main`.
- `gotix-datalake` — **tạo nhánh riêng**, có PR. Đã tạo qua `git worktree` (không đụng nhánh
  `feat/1.6-reconciliation-lineage` đang có nhiều thay đổi chưa commit của việc khác):
  - Nhánh: `feat/n4-company-sector-risk-contract`, base `dev`.
  - Thư mục làm việc riêng: `/Users/hongphuc/Documents/01_congViec/Bigdata/gotix-datalake-n4`
    (worktree — cùng 1 repo `.git`, khác thư mục, không xung đột với thư mục `gotix-datalake/`
    đang dở việc khác).

## 9. Kế hoạch triển khai

**Bước 0 — đã chốt (mục 7), không còn gate.**

**Bước 1 — xác nhận `sector` (nhẹ, làm được ngay)**
1. Cài `trino` (chưa có trong dependency của `detecting_cheat_by_nebula`, xem mục "PHU THUOC
   THEM" đầu file `ingest_trino_gotix.py`).
2. Chạy thật `ingest_trino_gotix.py` trên Trino thật (dùng đúng `TRINO_PORT=18082` như comment
   trong file, hoặc port thật của môi trường lúc chạy) → xem `companies.csv` có cột `sector` với
   giá trị ngành nghề thật (không phải toàn "Chưa rõ").
3. Đối chiếu vài `mst` mẫu: so `sector` trong CSV với `SELECT ten_nganh FROM
   nessie.tier2.company_industry WHERE mst=... AND nganh_chinh=true` qua Trino trực tiếp — khớp
   thì coi là xác nhận xong.
4. Không sửa code ở bước này (code đã đúng) — nếu bước 3 lệch mới quay lại đọc kỹ SQL để tìm bug.

**Bước 2 — nối 3 cột rủi ro (không tính điểm, chỉ hiển thị — đã chốt mục 3/7)**
1. Viết SQL đọc `tier3.tax_declaration_gtgt_tndn_t2_feature_value` +
   `tier3.einvoice_invoice_risk_feature_value`, lọc đúng `feature_name` đã chốt, lấy
   `fiscal_year` mới nhất/`mst` (1 CTE/nguồn, giống mẫu `latest_sector`).
2. Gộp vào `SQL_COMPANIES` (LEFT JOIN theo `mst` — LEFT vì không phải `mst` nào cũng có, đúng
   mục 4) + thêm cột vào `fetch_companies()`/header `companies.csv`.
3. Thêm thuộc tính vào `CREATE TAG Company` (`detecting_cheat_by_nebula.ngql`).
4. **Không sửa** `validate_contract.py`/`detect_circular_trading.py` (đã chốt không tính điểm).

**Bước 3 — kiểm chứng thật (không chỉ đọc code, phải chạy)**
1. Chạy `run_all.py --all --skip-detect --datasource trino_gotix` (nạp lại data, không detect)
   trên 1 space test — xác nhận Company node có đủ `sector` + cột rủi ro mới qua `DESCRIBE TAG
   Company` + `FETCH PROP ON Company <mst> YIELD properties(vertex)` vài mst mẫu.
2. Chạy `validate_contract.py` (không sửa code, chỉ chạy) — lấy điểm thật cho báo cáo, xác nhận
   đúng như phân tích mục 3 (điểm không đổi nếu ĐKKD vẫn thiếu).
3. Dọn sạch space test sau khi xong (không để lại dữ liệu test trong Nebula dùng chung).

**Bước 4 — cập nhật tài liệu + báo cáo**
1. Sửa `gotix-datalake/docs/BAO_CAO_TICH_HOP_GOTIX_NEBULA.md` §4/§7 (mục 5 phía trên) — làm trên
   worktree `gotix-datalake-n4`.
2. Sửa câu gây hiểu lầm ở `gotix-datalake/data/domains/company/README.md:38`.
3. Viết `N4/N4_BAO_CAO.md` (cùng khung mục đã thấy ở `docs/2/2.x/*_BAO_CAO.md` bên
   `gotix-datalake`: vấn đề+quyết định chốt → giải pháp → thay đổi cụ thể → kết quả kiểm chứng
   chạy thật → đánh đổi/rủi ro còn lại → việc chưa làm) — dùng làm báo cáo test bắt buộc trước
   khi merge (yêu cầu #3 của Phúc), chung cho cả 2 phía sửa (code + tài liệu), vì cùng 1 việc N4.

**Bước 5 — PR**
- `gotix-datalake`: PR từ `feat/n4-company-sector-risk-contract` → `dev`, đính kèm
  `N4_BAO_CAO.md`.
- `detecting_cheat_by_nebula`: sửa trực tiếp trên `main` (đã chốt mục 8), không mở PR.
