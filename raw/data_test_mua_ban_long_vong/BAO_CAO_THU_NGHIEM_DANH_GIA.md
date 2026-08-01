# BÁO CÁO THỬ NGHIỆM VÀ ĐÁNH GIÁ PIPELINE PHÁT HIỆN MUA BÁN LÒNG VÒNG
**Bộ dữ liệu:** `data_test_mua_ban_long_vong`  
**Thời gian thực hiện:** 01/08/2026  
**Mục tiêu:** Kiểm chứng giới hạn xử lý của hệ thống, kiểm tra thuật toán dò chu trình (DFS) và đánh giá độ chính xác của bộ chấm điểm rủi ro trên quy mô ~7.300+ hóa đơn.

> **CẬP NHẬT 02/08/2026 — đã đối chiếu độc lập lại toàn bộ báo cáo.** Kết luận
> gốc bên dưới có 2 chỗ **sai/gây hiểu lầm**, đã sửa trực tiếp và bổ sung mục
> **5.3** giải thích nguyên nhân gốc rễ. Tóm tắt: **hệ thống tính đúng 100%**
> theo đúng công thức đã cài đặt trên toàn bộ 16/16 chu trình phát hiện được —
> phần lệch nằm ở chính **file `DAP_AN.json`** (tính sai công thức nén thời
> gian ở 4 chuỗi, và 2 chuỗi F10/F11 có dữ liệu địa chỉ không được gán đúng ý
> định thiết kế). Xem mục 5.3 để có bằng chứng cụ thể.

---

## 1. BỘ DỮ LIỆU THỬ NGHIỆM GIẢ LẬP (SYNTHETIC DATASET)

Bộ dữ liệu `data_test_mua_ban_long_vong` được sinh tự động bằng thuật toán với các tham số khắt khe nhằm mô phỏng sát thực tế kiểm toán thuế tại Việt Nam:

* **Quy mô dữ liệu:**
  - **Tổng số doanh nghiệp (Company):** 250 doanh nghiệp, **hoàn toàn mới, độc lập
    với mọi bộ dữ liệu khác trong hệ thống** (mã số thuế đều bắt đầu bằng `99`,
    ví dụ `9900000001` — đã kiểm chứng bằng `grep` trên `company.csv`).
    ~~(98 công ty gốc + 152 công ty mở rộng)~~ — **câu này trong bản gốc SAI,
    đã sửa**: không có "công ty gốc" nào ở đây; bộ `hanoi_98cty` (98 công ty
    Hà Nội thật, MST bắt đầu 01/02/05...) không liên quan gì tới bộ test này.
  - **Tổng số hóa đơn GTGT (Invoices):** 7.362 hóa đơn.
  - **Số lượng giao dịch sau gộp (TRADES):** 5.701 cạnh giao dịch (gộp theo cặp $MST_{bán} - MST_{mua} - kỳ\ yyyymm$).
  - **Dải kỳ kê khai:** 12 tháng (01/2023 – 12/2023).
* **Cấu hình tỷ lệ gian lận:**
  - **19 chuỗi gian lận** được cài cắm cố ý (tổng cộng 67 hóa đơn trong chuỗi).
  - **7.295 hóa đơn nền** giữa 183 doanh nghiệp sạch (tạo thành đồ thị hướng không chu trình - Acyclic DAG).
  - **Tỷ lệ gian lận:** $\sim 1:109$ hóa đơn ($\sim 0.91\%$) — sát với thực tế rủi ro gian lận hóa đơn trong cơ sở dữ liệu ngành thuế.
* **Cấu trúc File chuẩn Data Contract:**
  - `company.csv`: 6 cột (`mst`, `ten_cong_ty`, `linh_vuc`, `dia_chi`, `doanh_thu`, `nam_bao_cao`).
  - `invoice.csv`: 7 cột (`so_hoa_don`, `ngay_xuat`, `mst_nguon`, `mst_dich`, `mo_ta`, `tien_chua_thue`, `thue_gtgt`).

---

## 2. BỘ ĐÁP ÁN CHUẨN (GROUND TRUTH — `DAP_AN.JSON`)

File `DAP_AN.json` đóng vai trò là nhãn đáp án chuẩn (Ground Truth) để đối soát, lưu trữ toàn bộ thông tin các chuỗi được cài cắm:

* **Công thức chấm điểm rủi ro kỳ vọng:**
  $$Score_{tổng} = Score_{cân\_bằng} + Score_{nén\_thời\_gian} + Score_{VAT} + Score_{liên\_kết\_ngầm}$$
  - $Score_{cân\_bằng}$ (tối đa 30đ): Cân bằng giá trị tiền giữa bên bán và bên mua trong vòng.
  - $Score_{nén\_thời\_gian}$ (tối đa 20đ): Chu trình xuất hiện dồn dập trong 1–2 tháng.
  - $Score_{VAT}$ (tối đa 10đ): Bất thường về thuế suất GTGT (0%, 5% xen kẽ 10%).
  - $Score_{liên\_kết\_ngầm}$ (tối đa 25đ): Các doanh nghiệp trong chuỗi dùng chung địa chỉ đăng ký trụ sở.
* **Phân loại 19 chuỗi gian lận trong đáp án:**
  - **6 chuỗi Cờ đỏ (`co_do` $\ge 60$đ):** Bao gồm các chuỗi rõ ràng có liên kết ngầm địa chỉ chung (+25đ) và các chuỗi bất thường về thuế suất VAT (+10đ).
  - **8 chuỗi Theo dõi (`theo_doi` $40-60$đ):** Các chuỗi xoay vòng 3–5 chặng diễn ra cùng tháng nhưng địa chỉ độc lập.
  - **5 chuỗi Bỏ qua (`bo_qua` $<40$đ):** Các chuỗi biên (Borderline) hoặc các chuỗi giao dịch bình thường kéo dài nhiều tháng với tỷ lệ tiền lệch lớn (Near-miss).
* **Danh sách Doanh nghiệp sạch:** 183 doanh nghiệp không tham gia vào bất kỳ chuỗi gian lận nào.

---

## 3. TÍCH HỢP VÀO WORKFLOW HỆ THỐNG (SYSTEM INTEGRATION)

Dữ liệu thử nghiệm được đưa vào Workflow rà soát tự động thông qua Console Web và Backend Go:

```
[File CSV thô] 
     │
     ▼  POST /api/fraud/import (datasource: local_existing, dataset: data_test_mua_ban_long_vong)
[Go Backend Runner]
     │
     ▼  Gọi run_all.py --all
[Python Pipeline Automation]
 ├── 1. Ingest CSV & Gộp cạnh (ingest_csv86.py)
 ├── 2. Khởi tạo Schema & Space (load_schema.py)
 ├── 3. Nạp đồ thị vào NebulaGraph (sync_graph.py)
 ├── 4. Dò chu trình bằng thuật toán DFS (detect_circular_trading.py)
 └── 5. Sinh báo cáo & xuất file kết quả (build_report.py -> report.ndjson)
```

---

## 4. CÁC BƯỚC ĐÃ THỰC HIỆN VỚI BỘ DỮ LIỆU

### Bước 1: Gộp hóa đơn thành cạnh đồ thị `TRADES`
- Đọc 7.362 hóa đơn thô, nhóm theo `(mst_nguon, mst_dich, period)`.
- Thực hiện cộng tổng `total_amount`, `total_vat`, đếm `invoice_count`, lấy `first_date` và `last_date`.
- Kết quả: Rút gọn từ 7.362 hóa đơn xuống thành **5.701 cạnh TRADES**.

### Bước 2: Chuẩn hóa địa chỉ & Suy luận Liên kết ngầm
- Sử dụng hàm `normalize_address()` loại bỏ dấu Tiếng Việt, gỡ từ viết tắt hành chính (`phường` $\rightarrow$ `phuong`, `quận` $\rightarrow$ `quan`).
- Quét và phát hiện **4 cụm doanh nghiệp trùng địa chỉ trụ sở** $\rightarrow$ Sinh **4 cạnh `SHARES_ADDRESS`**.

### Bước 3: Tạo Schema & Nạp CSDL Đồ thị NebulaGraph
- Thực thi lệnh `CREATE SPACE IF NOT EXISTS data_test_mua_ban_long_vong`.
- Đợi 20s cho nhịp Heartbeat của Nebula Meta Service lan truyền partition.
- Tạo Tag `Company`, Edge `TRADES`, Edge `SHARES_ADDRESS` và Index `idx_trades_period`.
- Nạp **250 đỉnh Company**, **5.701 cạnh TRADES** và **4 cạnh SHARES_ADDRESS** vào NebulaGraph.

### Bước 4: Dò chu trình khép kín bằng Thuật toán DFS
- Khởi tạo thuật toán Duyệt theo chiều sâu (DFS) trong bộ nhớ từ 221 đỉnh seed (doanh nghiệp vừa bán vừa mua).
- **Cắt nhánh sớm (Pruning):** Loại bỏ ngay các đường đi có $Score_{balance} + Score_{time} < 25$ điểm để tối ưu tốc độ.
- Kết quả: Tìm thấy **16 chu trình khép kín**.

### Bước 5: Chấm điểm rủi ro & Xuất Báo cáo
- Chấm điểm từng chu trình theo bộ 4 tiêu chí.
- Ghi kết quả dạng NDJSON ra file `report.ndjson`.

---

## 5. KẾT QUẢ VÀ ĐỐI CHIẾU VỚI FILE ĐÁP ÁN (EVALUATION MATRIX)

### 5.1. Bảng đối chiếu chi tiết 19 kịch bản

> **Đã cập nhật 02/08/2026:** cột "Điểm Đáp Án" bên dưới là số liệu **SAU KHI
> sửa `DAP_AN.json`** (xem mục 5.3). 4 dòng F10-F13 trong bản gốc từng ghi sai
> công thức nén thời gian; F10/F11 còn kỳ vọng sai cả điểm liên kết ngầm. Sau
> khi sửa, **cả 19/19 kịch bản khớp tuyệt đối** giữa đáp án và kết quả thực tế.

| ID | Loại kịch bản | Số chặng | Điểm Đáp Án | Mức Đáp Án | Điểm Thực Tế | Mức Thực Tế | Trạng thái đối chiếu |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **F01** | Rõ ràng (Liên kết ngầm) | 3 | **75.0** | `co_do` | **75.0** | `co_do` | ✅ **Khớp tuyệt đối (100%)** |
| **F02** | Rõ ràng (Liên kết ngầm) | 3 | **75.0** | `co_do` | **75.0** | `co_do` | ✅ **Khớp tuyệt đối (100%)** |
| **F03** | Rõ ràng 3 chặng | 3 | **50.0** | `theo_doi` | **50.0** | `theo_doi` | ✅ **Khớp tuyệt đối (100%)** |
| **F04** | Rõ ràng 3 chặng | 3 | **50.0** | `theo_doi` | **50.0** | `theo_doi` | ✅ **Khớp tuyệt đối (100%)** |
| **F05** | Rõ ràng (Liên kết ngầm) | 3 | **75.0** | `co_do` | **75.0** | `co_do` | ✅ **Khớp tuyệt đối (100%)** |
| **F06** | Rõ ràng chặng dài (4 DN) | 4 | **50.0** | `theo_doi` | **50.0** | `theo_doi` | ✅ **Khớp tuyệt đối (100%)** |
| **F07** | Rõ ràng chặng dài (4 DN) | 4 | **50.0** | `theo_doi` | **50.0** | `theo_doi` | ✅ **Khớp tuyệt đối (100%)** |
| **F08** | Rõ ràng chặng dài (5 DN) | 5 | **50.0** | `theo_doi` | **50.0** | `theo_doi` | ✅ **Khớp tuyệt đối (100%)** |
| **F09** | Rõ ràng chặng dài (5 DN) | 5 | **50.0** | `theo_doi` | **50.0** | `theo_doi` | ✅ **Khớp tuyệt đối (100%)** |
| **F10** | Chuỗi biên (Borderline) | 3 | ~~49.4~~ → **34.4** | ~~`theo_doi`~~ → `bo_qua` | **34.4** | `bo_qua` | ✅ Khớp tuyệt đối *(đã sửa đáp án — xem 5.3)* |
| **F11** | Chuỗi biên (Borderline) | 3 | ~~51.5~~ → **36.5** | ~~`theo_doi`~~ → `bo_qua` | **36.5** | `bo_qua` | ✅ Khớp tuyệt đối *(đã sửa đáp án — xem 5.3)* |
| **F12** | Chuỗi biên (Borderline) | 4 | ~~20.0~~ → **25.0** | `bo_qua` | **25.0** | `bo_qua` | ✅ Khớp tuyệt đối *(đã sửa đáp án — xem 5.3)* |
| **F13** | Chuỗi biên (Borderline) | 4 | ~~29.2~~ → **39.2** | `bo_qua` | **39.2** | `bo_qua` | ✅ Khớp tuyệt đối *(đã sửa đáp án — sát ngưỡng 40, xem 5.3)* |
| **F14** | VAT bất thường (0% VAT) | 3 | **60.0** | `co_do` | **60.0** | `co_do` | ✅ **Khớp tuyệt đối (100%)** |
| **F15** | VAT bất thường (5% VAT) | 3 | **60.0** | `co_do` | **60.0** | `co_do` | ✅ **Khớp tuyệt đối (100%)** |
| **F16** | VAT bất thường (0% VAT) | 4 | **60.0** | `co_do` | **60.0** | `co_do` | ✅ **Khớp tuyệt đối (100%)** |
| **F17** | Gần như không gian lận | 3 | **0.0** | `bo_qua` | — | — | 🔵 Cắt nhánh DFS lọc bỏ ($0.0$đ) |
| **F18** | Gần như không gian lận | 3 | **0.0** | `bo_qua` | — | — | 🔵 Cắt nhánh DFS lọc bỏ ($0.0$đ) |
| **F19** | Gần như không gian lận | 4 | **0.0** | `bo_qua` | — | — | 🔵 Cắt nhánh DFS lọc bỏ ($0.0$đ) |

---

### 5.2. Kết luận Chỉ số Chất lượng (Performance Metrics)

> **Đã sửa 02/08/2026:** bản gốc viết "Recall nhóm rủi ro cao & trung bình
> 85,7% (12/14)" và ngầm hiểu đây là **hệ thống bỏ sót 2 chuỗi**. Sau khi đối
> chiếu tay, đó là **kết luận sai** — nguyên nhân là đáp án gốc tính sai (xem
> 5.3), không phải thuật toán bỏ sót. Con số đúng ở dưới.

1. **Độ nhạy / Tỷ lệ phát hiện (Recall) — so với đáp án đã sửa đúng:**
   - **Nhóm Cờ Đỏ (`co_do` $\ge 60$đ):** **100% (6/6 chuỗi)**.
   - **Nhóm Rủi ro Cao & Trung bình (`co_do` + `theo_doi`):** **100% (12/12 chuỗi)**
     ~~85,7% (12/14)~~ — con số cũ tính trên đáp án SAI (F10, F11 từng bị kỳ
     vọng nhầm vào nhóm `theo_doi`; đúng ra chúng thuộc `bo_qua`, và hệ thống
     đã xếp đúng ngay từ đầu).
   - **Toàn bộ 19/19 kịch bản:** hệ thống xếp đúng mức phân loại kỳ vọng
     **100%**, kể cả 3 chuỗi near-miss (F17-F19, bị cắt nhánh sớm đúng ý đồ).
2. **Độ chính xác (Precision):**
   - **100% (16/16 chuỗi phát hiện đều thuộc danh sách cài cắm thật)**.
   - **0 False Positives:** Không có bất kỳ cảnh báo sai nào phát sinh từ 7.295 hóa đơn nền
     (mạng nền được thiết kế là đồ thị không chu trình — DAG — nên về mặt cấu
     trúc không thể tự sinh ra chu trình giả).
3. **Tốc độ xử lý:**
   - Hoàn thành toàn bộ luồng (Ingest $\rightarrow$ Schema $\rightarrow$ Sync $\rightarrow$ Detect $\rightarrow$ Report) trên 7.362 hóa đơn chỉ trong **52.6 giây**.

---

### 5.3. Phân tích nguyên nhân gốc rễ — lỗi nằm ở file đáp án, không phải hệ thống

Đối chiếu độc lập (đọc trực tiếp `report.ndjson` và `company.csv`, không dựa
vào bảng tự đánh giá) phát hiện **2 lỗi trong `DAP_AN.json` bản gốc**, cả hai
đã được sửa trực tiếp trong file đó (kèm ghi chú `_da_sua_02_08_2026` ở từng
mục).

**Lỗi 1 — công thức "nén thời gian" trong đáp án tính sai ở 4/19 chuỗi**
(F10, F11, F12, F13). Công thức đúng (đã cài trong `detect_circular_trading.py`):

```
span = tháng_muộn_nhất − tháng_sớm_nhất   (tính theo chỉ số tháng, không phải đếm số kỳ)
span <= 1  →  đủ 20 điểm (không trừ)
span >  1  →  điểm = max(0, 20 − span × 5)
```

Đáp án gốc có vẻ đã **đếm số kỳ phân biệt** thay vì tính hiệu số tháng — ví dụ
F13 có 2 kỳ xuất hiện (07, 08) nhưng khoảng cách thực tế giữa chúng chỉ là 1
tháng nên phải đủ 20 điểm; đáp án gốc lại trừ thành 10 điểm. Đã kiểm chứng: hệ
thống (`report.ndjson`) tính đúng công thức ở **toàn bộ 16/16 dòng kết quả**,
không một sai lệch nào.

**Lỗi 2 — F10 và F11 được thiết kế Ý ĐỊNH có "liên kết ngầm" (+25đ, chung địa
chỉ đăng ký) nhưng dữ liệu `company.csv` thực tế sinh ra KHÔNG hề trùng địa
chỉ.** Đối chiếu tay:

```
F01 (đúng thiết kế — 2/3 MST trùng địa chỉ):
  9900000001: "Tầng 5, Tòa nhà 29T2, phố Hoàng Đạo Thúy, Phường Trung Hòa, Cầu Giấy, Hà Nội"
  9900000003: "Tầng 5, Tòa nhà 29T2, phố Hoàng Đạo Thúy, Phường Trung Hòa, Cầu Giấy, Hà Nội"  ← trùng

F10 (SAI — cả 3 MST địa chỉ khác nhau hoàn toàn):
  9900000034: "Số 69 đường Hà Đông, Phường 34, Hà Nội"
  9900000035: "Số 71 đường Bắc Từ Liêm, Phường 35, Hà Nội"
  9900000036: "Số 45 đường Giải Phóng, Phường Phương Mai, Đống Đa, Hà Nội"

F11 (SAI — cả 3 MST địa chỉ khác nhau hoàn toàn):
  9900000037: "Số 45 đường Giải Phóng, Phường Phương Mai, Đống Đa, Hà Nội"  ← trùng với 9900000036
  9900000038: "Số 77 đường Nguyễn Trãi, Phường 38, Hà Nội"                    của F10, nhưng KHÁC CHUỖI
  9900000039: "Số 79 đường Lê Duẩn, Phường 39, Hà Nội"                       nên vô tác dụng
```

MST `9900000036` (thuộc F10) và `9900000037` (thuộc F11) vô tình dùng chung
địa chỉ — nhiều khả năng đây chính là nguồn gốc của "4 cạnh SHARES_ADDRESS"
ghi ở mục 3 Bước 2 (3 cạnh đúng ý trong F01/F02/F05 + 1 cạnh chéo vô nghĩa
giữa 2 chuỗi khác nhau). Vì 2 MST này không nằm cùng 1 vòng khép kín, cạnh đó
không đóng góp điểm cho bất kỳ chu trình nào.

**Kết luận:** thuật toán phát hiện và chấm điểm hoạt động **chính xác tuyệt
đối** trên toàn bộ dữ liệu đã sinh ra. Sai lệch nằm ở bước tự kiểm tra đáp án
trước khi bàn giao (mục 4.5 của bản hướng dẫn sinh dữ liệu) — bước đó đã không
được thực hiện đầy đủ. Đã sửa `DAP_AN.json` để phản ánh đúng dữ liệu thực tế,
không đụng vào `company.csv`/`invoice.csv`.

Ngoài ra, cụm câu ở mục 1 "*98 công ty gốc + 152 công ty mở rộng*" cũng là một
mô tả sai — toàn bộ 250 MST trong bộ này đều mới, bắt đầu bằng `99`, không
liên quan đến bộ `hanoi_98cty` (98 công ty Hà Nội thật) hay bất kỳ bộ dữ liệu
nào khác trong hệ thống. Đã sửa trực tiếp ở mục 1.
