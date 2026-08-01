# Kế hoạch: Import "Mua vào bán ra 86 công ty.xlsx" vào NebulaGraph

Nguồn: [Mua vào bán ra 86 công ty.xlsx](./Mua%20v%C3%A0o%20b%C3%A1n%20ra%2086%20c%C3%B4ng%20ty.xlsx) (91 sheet, đã khảo sát toàn bộ).

---

# ⭐ QUY TRÌNH IMPORT A→Z (tái lập từ đầu, chỉ với file `.xlsx`)

Làm tuần tự từ Bước 0 đến Bước 6. Kết quả cuối: NebulaGraph space `invoice_graph` có **98 đỉnh `company` + 8.976 cạnh `xuat_hoa_don`** (trong đó 14 cạnh `nhan_ai=1`).

> **Tổng quan luồng dữ liệu**:
> `.xlsx` → (Python `script.py`) → `company.csv` + `invoice.csv` → (`nebula-importer` + `invoice_graph_import.yaml`) → NebulaGraph.
> Toàn bộ file trung gian nằm trong `d:\Bigdata\detecting_cheat_by_nebula\`.

## Bước 0 — Chuẩn bị môi trường

1. **Bật NebulaGraph** (chạy trong WSL, cần mật khẩu sudo — gõ tay, không tự động được):
   ```powershell
   wsl sudo /usr/local/nebula/scripts/nebula.service start all
   ```
   Kiểm tra graphd/metad/storaged đều "Running/Listening" trên 9669/9559/9779.

2. **Python + thư viện**:
   ```powershell
   pip install openpyxl pandas
   ```

3. **nebula-importer**: cần bản tương thích config `version: v2` (dòng nebula-importer ~v3.x cũ, dùng `clientSettings`/`files`). Kiểm tra: `nebula-importer --version`.

4. **Công cụ chạy nGQL**: dùng web console tự viết (`nebula_demo\server.exe` → `http://localhost:8080`) **hoặc** `nebula-console`. Các câu DDL dưới đây chạy ở đây.

## Bước 1 — Tạo Space + Schema (chạy 1 lần)

Chạy trong nGQL (mỗi câu 1 lần; sau `CREATE SPACE` phải **đợi ~10–20 giây** cho schema đồng bộ qua heartbeat rồi mới `USE` được):
```sql
CREATE SPACE IF NOT EXISTS invoice_graph (partition_num = 10, replica_factor = 1, vid_type = FIXED_STRING(20));
-- đợi 10-20s...
USE invoice_graph;
CREATE TAG IF NOT EXISTS company (
  ten_cong_ty string, linh_vuc string, dia_chi string, doanh_thu int, nam_bao_cao string
);
CREATE EDGE IF NOT EXISTS xuat_hoa_don (
  so_hoa_don string, ngay_xuat string, mo_ta string,
  tien_chua_thue int, thue_gtgt int, loai_gd string, nhan_ai int
);
```
- `vid_type = FIXED_STRING(20)`: VID là MST (chuỗi 10 số, đã zero-pad) → 20 ký tự dư an toàn (đúng cấu hình space đang chạy).
- `replica_factor = 1`: chạy 1 node standalone.
- Đợi thêm ~10s sau `CREATE TAG/EDGE` trước khi import (schema cần lan tới storaged).

## Bước 2 — Sinh `company.csv` gốc (86 công ty) từ sheet `2021`

`script.py` (Bước 3) **đọc và mở rộng** `company.csv`, nên phải có bản gốc trước. Sheet `2021` là danh bạ 86 công ty. Chạy đoạn này trong `d:\Bigdata\detecting_cheat_by_nebula\` để sinh bản gốc (map cột: D=MST, C=tên, E=lĩnh vực, F=địa chỉ, I=doanh thu, G=ngày báo cáo):
```python
# tao_company_goc.py  — chay: py tao_company_goc.py
import glob, openpyxl, csv
ws = openpyxl.load_workbook(glob.glob("*.xlsx")[0], read_only=True, data_only=True)["2021"]
rows = []
for r in ws.iter_rows(min_row=2, values_only=True):   # bo dong header
    if r[3] is None:                                   # cot D = MST
        continue
    mst = "".join(ch for ch in str(r[3]) if ch.isdigit()).zfill(10)
    rows.append([mst, r[2], r[4], r[5], r[8] or 0, r[6]])  # mst, ten, linh_vuc, dia_chi, doanh_thu, nam
with open("company.csv", "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows(rows)
print(len(rows), "cong ty -> company.csv")   # ky vong: 86
```
> Nếu `company.csv` đã có sẵn (86 hoặc 98 dòng) thì **bỏ qua bước này** — `script.py` tự chuẩn hóa lại.

## Bước 3 — Chạy `script.py`: sinh `invoice.csv` + mở rộng `company.csv`

```powershell
cd d:\Bigdata\detecting_cheat_by_nebula
py script.py
```
Script làm 3 phần (xem chi tiết mục 3 bên dưới):
- **Phần 1**: đọc 2 sheet ẩn `HĐ_Đầu_Vào`/`HĐ_Bán_Ra` → 77 hóa đơn của AZURA **có nhãn `nhan_ai` thật** (đây là bằng chứng giao dịch + nhãn — bắt buộc nạp thì mới có gian lận trong đồ thị để phát hiện; xem ghi chú "vì sao nạp cả sheet ẩn" ở mục 7).
- **Phần 2**: duyệt 86 sheet công ty, trích cạnh từ "Hóa đơn đầu vào"/"Hóa đơn đầu ra", gộp với Phần 1, **chuẩn hóa MST** (zero-pad 10 số), **khử 48 dòng trùng lặp 2 chiều**, **thêm cột `rank`** (số thứ tự — BẮT BUỘC, xem mục 7) → ghi `invoice.csv`.
- **Phần 3**: bổ sung 12 công ty đối tác ngoài danh sách 86 (chỉ có MST + tên) vào `company.csv`.

**Output kỳ vọng trên màn hình:**
```
Số hoá đơn có nhãn AI thật (...): 77
Số sheet công ty tìm thấy: 86
Đã khử 48 dòng trùng lặp 2 chiều
Tổng số cạnh hoá đơn cuối cùng: 8976
Tổng công ty sau mở rộng: 98
```

## Bước 4 — Import vào NebulaGraph

Chạy **từ trong thư mục `detecting_cheat_by_nebula`** (các path trong YAML là tương đối `./company.csv`, `./invoice.csv`):
```powershell
cd d:\Bigdata\detecting_cheat_by_nebula
nebula-importer --config ./invoice_graph_import.yaml
```
> ⚠️ **Nếu import lại lần 2** (đã có dữ liệu cũ): xóa sạch trước để tránh lẫn dữ liệu / lỗi rank cũ:
> ```sql
> USE invoice_graph;
> CLEAR SPACE invoice_graph;
> ```
> rồi chạy lại `nebula-importer`. Kiểm tra `./err/` và `import_log.log` nếu có dòng lỗi.

## Bước 5 — Kiểm tra sau import

```sql
USE invoice_graph;
SHOW TAGS;                                   -- phải có: company
SHOW EDGES;                                  -- phải có: xuat_hoa_don
MATCH (c:company) RETURN count(c) AS so_cty; -- ky vong: 98
MATCH ()-[e:xuat_hoa_don]->() RETURN count(e) AS so_hd;        -- ky vong: 8976
MATCH ()-[e:xuat_hoa_don]->() WHERE e.nhan_ai == 1 RETURN count(e); -- ky vong: 14
```
Query mẫu an toàn (neo điểm, 1 hop):
```sql
MATCH p=(c1:company)-[e:xuat_hoa_don]->(c2:company) WHERE id(c1) == "0109082787" RETURN p LIMIT 50;
```

## Bước 6 — Sự cố thường gặp & cách xử lý (đã gặp thật)

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Import ra ~4.608 cạnh thay vì 8.976 | Thiếu `rank` → mọi hóa đơn cùng cặp (src,dst) ghi đè nhau (Nebula định danh cạnh = src+edge+dst+**rank**) | Đảm bảo `invoice.csv` có cột `rank` (index 9) + YAML khai `rank: {index: 9}`. `CLEAR SPACE` rồi import lại |
| `FileNotFoundError` khi chạy script | Tên file tiếng Việt lưu Unicode NFD, literal gõ tay là NFC → lệch byte | Script đã dùng `glob.glob("*.xlsx")` thay vì gõ tên — đừng hardcode tên tiếng Việt |
| MST không khớp (cạnh mất 1 đầu) | Sheet ẩn lưu MST thiếu số 0 đầu (`103769372`), sheet khác có (`0103769372`) | Đã `normalize_mst()` zero-pad về 10 số ở mọi nguồn |
| Query đa chặng làm **treo/crash graphd** | Đồ thị dày (~91 cạnh/đỉnh), MATCH nhiều hop không neo điểm hoặc dùng `*` | CẤM `*` biến thiên độ dài; luôn neo `WHERE id(x)=="..."`; chỉ chuỗi hop cố định. Nếu crash: `stop all` → xóa `/usr/local/nebula/pids/*.pid` → `start all` |
| Sau khi Nebula crash, **mọi query treo 20s+** dù Nebula đã chạy lại | `server.exe` giữ connection pool cũ đã chết | Kill + khởi động lại `server.exe` (connection mới) → query về lại ~ms |
| `CREATE TAG` xong import báo "tag not found" | Import quá sớm, schema chưa lan tới storaged | Đợi ~10s sau khi tạo tag/edge rồi mới import |

---

## 1. Cấu trúc file nguồn (đã xác nhận bằng script đọc thật trực tiếp từ file, không đoán)

Tổng cộng **91 sheet**, chia 2 nhóm.

### Nhóm 1: 5 sheet tổng hợp (không phải dữ liệu quan hệ đơn lẻ)

⚠️ **4/5 sheet trong nhóm này bị ẨN (`sheet_state=hidden`) trong Excel** — không hiện trong tab bar hay hộp thoại "Activate" của Excel, chỉ thấy được qua script (`openpyxl`) hoặc bằng cách chuột phải vào 1 tab bất kỳ → **Unhide...**. Chỉ có `2021` là hiện (visible).

| Sheet | Ẩn? | Kích thước | Nội dung thật (đọc trực tiếp) |
|---|---|---|---|
| `100MST` | Ẩn | 411 dòng × 11 cột | Header: `STT, File nguồn, Tên người nộp thuế, Mã số thuế, Lĩnh vực hoạt động, Địa chỉ, Ngày báo cáo, Thông tư, Doanh thu bán hàng, Giá vốn hàng bán, Tổng LN kế toán trước thuế`. Mỗi công ty lặp lại 4 dòng (2021, 2022, 2023, 2024) — dữ liệu tài chính nhiều năm. Lưu ý: cột MST ở đây là **số nguyên** (`100100590`, không có số 0 đầu). |
| `2021` | **Hiện** | 87 dòng × 11 cột | Y hệt cột của `100MST` nhưng chỉ lọc năm 2021 (86 công ty + 1 dòng header). Ở đây MST lại là **chuỗi có số 0 đầu** (`'0100100590'`) — khác kiểu dữ liệu với sheet `100MST` dù cùng nội dung. Đây là nguồn của `company.csv`. |
| `BCTC_2021` | Ẩn | 72 dòng × 4 cột | Báo cáo tài chính dạng bảng so sánh **① Số liệu DN nộp / ② Sau khi loại bỏ chi phí khống / ③ Chênh lệch** — chỉ 1 công ty: AZURA (MST `0109082787`). |
| `HĐ_Đầu_Vào` | Ẩn | 48 dòng × 15 cột | Header: `STT, Kịch bản, Số hóa đơn, Ngày xuất HĐ, MST người bán, Tên NCC, Nội dung hóa đơn, Tiền chưa thuế, Thuế suất GTGT, Tiền thuế GTGT, Tổng tiền thanh toán, Hình thức TT, Trạng thái HĐ (thực tế), **Nhãn AI (label)**, Loại khống`. Chỉ hóa đơn mua vào của AZURA — ghi chú màu "đỏ=khống, vàng=nâng khống, không tô=thực". |
| `HĐ_Bán_Ra` | Ẩn | 50 dòng × 14 cột | Header: `STT, Số hóa đơn, Ngày xuất HĐ, Quý, MST Khách hàng, Tên khách hàng, Nội dung hàng hóa/dịch vụ, Loại, Tiền chưa thuế, Thuế suất GTGT, Tiền thuế GTGT, Tổng tiền thanh toán, Hình thức TT, **Nhãn AI**`. Chỉ hóa đơn bán ra của AZURA — ghi chú "tất cả hóa đơn bán ra đều hợp lệ (Label=0)". |

### Nhóm 2: 86 sheet công ty (tên sheet = MST, ví dụ `0100101072`)

Mỗi sheet có cấu trúc giống hệt nhau:
- 4 dòng đầu: `NNT:` (tên), `MST:`, `Doanh thu:`, `Năm:`
- Mục **"Hóa đơn đầu vào"**: header `STT, Số hóa đơn, Ngày hóa đơn, MST người bán, Tên người bán, Nội dung hóa đơn, Tiền chưa thuế, Thuế suất GTGT, Tiền thuế GTGT, Tổng tiền thanh toán, Hình thức TT` (11 cột) — **KHÔNG có cột nhãn AI**
- Mục **"Hóa đơn đầu ra"**: cùng 11 cột, chỉ đổi "MST người bán/Tên người bán" → "MST người mua/Tên người mua"
- Kết mỗi mục bằng dòng `Tổng cộng`

Đã quét toàn bộ 86 sheet công ty bằng script — **xác nhận không sheet nào trong số này có cột "Nhãn AI"**. `nhan_ai` thật chỉ tồn tại ở `HĐ_Đầu_Vào`/`HĐ_Bán_Ra`, và luôn xoay quanh AZURA.

### Vai trò của từng sheet trong Nhóm 1 — đây là bộ "câu hỏi + đáp án" kiểu bài tập tình huống

**Ý tưởng thiết kế tổng thể**: 86 sheet công ty (Nhóm 2) là "đống cỏ khô" — dữ liệu giao dịch bình thường, KHÔNG có nhãn, giống hệt data thật ngoài đời (không biết trước ai gian lận). Còn 5 sheet Nhóm 1 chia làm 3 vai trò:

1. **`2021` — Danh bạ công ty gốc (công khai)**: bảng tra cứu chính cho cả 86 công ty (tên, MST, ngành, địa chỉ, doanh thu). Sheet DUY NHẤT hiện trong nhóm 1 — vì chỉ là metadata, không tiết lộ gì về gian lận.
2. **`100MST` — Dữ liệu nền nhiều năm (ẩn)**: mở rộng `2021` sang 4 năm (2021-2024) — dùng để phân tích xu hướng dài hạn nếu cần đào sâu hơn. Không phải "đáp án" gian lận, chỉ là background data cho toàn bộ nhóm công ty.
3. **`HĐ_Đầu_Vào` + `HĐ_Bán_Ra` — "Tang chứng" chi tiết từng hóa đơn của AZURA (ẩn)**: đáp án ở mức chi tiết nhất — từng dòng hóa đơn gắn nhãn `nhan_ai` + `Kịch bản` + `Loại khống`.
4. **`BCTC_2021` — Đáp án ở mức hậu quả tài chính (ẩn)**: không phải dữ liệu giao dịch, mà là bảng tổng kết tác động — loại bỏ hết hóa đơn khống thì BCTC AZURA thay đổi ra sao.

**Vì sao 4 sheet bị ẩn — suy luận có cơ sở**: việc ẩn đúng 4 sheet chứa đáp án (nhãn khống, kịch bản, tác động tài chính) trong khi để lộ 86 sheet "cỏ khô" + `2021` (danh bạ trung tính) — rất giống chủ đích: người phân tích được yêu cầu tự tìm ra AZURA gian lận từ 86 sheet thô trước, rồi mới "mở khóa" (Unhide) sheet đáp án để đối chiếu kết quả.

## 2. Đã có sẵn — không làm lại

| File | Trạng thái |
|---|---|
| `nebula_demo/schemas/invoice_graph.md` | Schema Space `invoice_graph` đã định nghĩa Tag `company` + Edge `xuat_hoa_don` (đã có sẵn field `nhan_ai`) |
| `company.csv` (86 dòng) | Đủ toàn bộ 86 công ty, khớp sheet `2021` |
| `invoice_graph_import.yaml` | Config nebula-importer sẵn, trỏ đúng `company.csv` + `invoice.csv` |
| `invoice.csv` (59 dòng / 18 công ty) | **Chỉ là mẫu demo** trích từ `HĐ_Đầu_Vào`/`HĐ_Bán_Ra` — xoay quanh 1 mình AZURA, CHƯA phải toàn bộ mạng lưới 86 công ty |

→ Việc cần làm thực chất chỉ là **mở rộng `invoice.csv`** để phủ hết 86 công ty, không cần đổi schema hay YAML.

## 3. Việc cần làm

### 3.1 Script trích xuất (Python + openpyxl)
Duyệt cả 86 sheet công ty, với mỗi sheet:
- Đọc section `Hóa đơn đầu vào` → edge: `MST người bán -> MST sheet hiện tại`
- Đọc section `Hóa đơn đầu ra` → edge: `MST sheet hiện tại -> MST người mua`

### 3.2 Chuẩn hóa MST
Một số MST thiếu số 0 đầu (`"103769372"` thay vì `"0103769372"`) → zero-pad về đúng độ dài chuẩn cho khớp `company.csv`.

### 3.3 Khử trùng lặp 2 chiều
1 giao dịch giữa 2 công ty nằm trong danh sách 86 sẽ xuất hiện ở **cả 2 sheet** (bên bán ghi "đầu ra", bên mua ghi "đầu vào"). Dedupe theo khóa `(số hóa đơn, mst_nguon, mst_dich)`, chỉ giữ 1 bản ghi.

### 3.4 Công ty ngoài danh sách 86
Nhiều MST đối tác (nhà cung cấp/khách hàng) không nằm trong 86 sheet (VD Honda Trading, Sumi-Hanel). Cần bổ sung các đỉnh `company` tối giản (chỉ có `mst` + tên, các field còn lại để trống) vào `company.csv` để cạnh có đủ 2 đầu.

### 3.5 Gắn nhãn AI cho các hóa đơn đã biết là khống
Đối chiếu `(số hóa đơn, MST)` với `HĐ_Đầu_Vào`/`HĐ_Bán_Ra` để gắn đúng `nhan_ai` + mô tả loại khống cho các cạnh liên quan AZURA. Các hóa đơn không có trong 2 sheet này → mặc định `nhan_ai = 0`.

## 4. Đầu ra

- `company.csv` mở rộng (86 + N công ty ngoài danh sách)
- `invoice.csv` mở rộng (ước lượng vài trăm dòng, thay cho bản 59 dòng hiện tại)
- **Không đổi** `invoice_graph_import.yaml` — cột đã khớp sẵn

## 5. Import & kiểm tra

```powershell
# Từ d:\Bigdata, sau khi có company.csv + invoice.csv mới
nebula-importer --config ./invoice_graph_import.yaml
```

Kiểm tra sau import:
- `SHOW TAGS;` / `SHOW EDGES;` — xác nhận schema
- Đếm đỉnh/cạnh: `MATCH (c:company) RETURN count(c);` / đếm cạnh tương tự
- Chạy lại **Kịch bản 1** (Circular Fraud Loop) trong [nebula_testing_power.md](../hanoiTax/nebula_testing_power.md) trên dữ liệu thật thay vì dữ liệu giả lập

## 6. Không làm (ngoài phạm vi)

- Không đưa `BCTC_2021` vào graph — đó là báo cáo tài chính dạng bảng so sánh, không phải dữ liệu quan hệ
- Không xử lý sâu hơn `100MST`/`2021` — `company.csv` hiện tại đã đủ dùng

---

## Checklist thực hiện

- [x] Viết script `script.py` (đặt cạnh file này trong `detecting_cheat_by_nebula/`)
- [x] Chạy full 86 sheet → xuất `company.csv` + `invoice.csv` mới
- [x] Backup `company.csv`/`invoice.csv` cũ trước khi ghi đè (`.bak`)
- [x] Chạy `nebula-importer`
- [x] Query kiểm tra + chạy lại Kịch bản 1 (vòng lặp gian lận)

---

## 7. Kết quả thực tế & bài học (sau khi chạy thật)

### Số liệu cuối cùng
- `company.csv`: **98 công ty** (86 gốc + 12 đối tác ngoài danh sách, tự phát hiện qua MST xuất hiện trong hóa đơn)
- `invoice.csv`: **8.976 cạnh hóa đơn** (8.965 từ 86 sheet công ty, đã khử 48 dòng trùng lặp 2 chiều, cộng thêm 77 hóa đơn có nhãn AI thật của AZURA)
- Đã xác nhận trong NebulaGraph: `company` = 98 đỉnh, `xuat_hoa_don` = 8.976 cạnh, 14 cạnh mang `nhan_ai = 1` (khống)

### ⚠️ Đính chính: AZURA CÓ sheet riêng (đã ghi sai trước đó)
Trước đó tài liệu này ghi nhầm "AZURA không có sheet công ty riêng" — **sai**. Đã kiểm tra lại trực tiếp: sheet `0109082787` tồn tại trong 86 sheet công ty (112 dòng), có đầy đủ "Hóa đơn đầu vào"/"Hóa đơn đầu ra" như 85 sheet còn lại (nhà cung cấp ví dụ: CMS Vina, HAL VN, IPADSHOP VN...). AZURA thực ra có **2 lớp dữ liệu riêng biệt**:
1. Sheet công ty `0109082787` — giao dịch kinh doanh bình thường (như mọi công ty khác, không nhãn)
2. `HĐ_Đầu_Vào`/`HĐ_Bán_Ra` (ẩn) — **34 hóa đơn được chọn lọc riêng kèm nhãn `nhan_ai` thật** (14 khống + 20 hợp lệ), dùng làm bộ đáp án cho bài toán phát hiện gian lận

Ban đầu định đối chiếu `(mst_nguon, mst_dich, ngay_xuat)` giữa 2 lớp này để "lan" nhãn AI sang các cạnh trích từ sheet riêng — nhưng 2 lớp gần như không trùng dữ liệu nhau (khác cách đánh số hóa đơn), nên bỏ hướng "đối chiếu", thay bằng **union thẳng 77 hóa đơn từ `HĐ_Đầu_Vào`/`HĐ_Bán_Ra` vào làm cạnh riêng** (đã tự mang đúng nhãn `nhan_ai`), cộng thêm ~119 cạnh khác từ sheet riêng `0109082787` (không nhãn, mặc định `nhan_ai=0`).

### Bug nghiêm trọng: thiếu `rank` làm mất ~50% dữ liệu
NebulaGraph định danh 1 cạnh bằng `(src, edge_type, dst, rank)` — mặc định `rank = 0` nếu không khai báo. Vì nhiều cặp công ty giao dịch **nhiều lần trong năm**, lần import đầu chỉ ra **4.608 cạnh thay vì 8.976** (mỗi hóa đơn sau ghi đè hóa đơn trước cùng cặp công ty).

**Fix**: thêm cột `rank` (số thứ tự tăng dần, không mang ý nghĩa nghiệp vụ) vào cuối `invoice.csv`, khai báo `rank: {index: 9}` trong `invoice_graph_import.yaml`. Phải `CLEAR SPACE invoice_graph;` trước khi import lại để xóa dữ liệu bị lỗi cũ.

### Cảnh báo: MATCH vòng lặp không neo điểm có thể làm sập NebulaGraph
Câu test ban đầu:
```sql
MATCH p=(c1:company)-[:xuat_hoa_don]->(c2:company)-[:xuat_hoa_don]->(c3:company)-[:xuat_hoa_don]->(c1) RETURN p LIMIT 5;
```
Không có `WHERE` neo điểm bắt đầu → NebulaGraph phải dò tam giác trên toàn đồ thị 98 đỉnh/8.976 cạnh (khá dày, ~91 cạnh/đỉnh trung bình) → **treo rồi crash graphd** (tiến trình chết hẳn, để lại file PID cũ gây lỗi khi khởi động lại — phải `stop all` + xóa `/usr/local/nebula/pids/*.pid` + `start all` mới phục hồi được).

**Luôn dùng bản có neo điểm** khi test trên đồ thị dày:
```sql
MATCH p=(c1:company)-[:xuat_hoa_don]->(c2:company)-[:xuat_hoa_don]->(c3:company)-[:xuat_hoa_don]->(c1)
WHERE id(c1) == "0109082787"
RETURN p LIMIT 5;
```
Câu này chạy ~1.6s, an toàn, và **tìm ra 1 vòng lặp thật**: `AZURA (0109082787) → VINACO (0102712091) → CMS Vina (0104380966) → AZURA`.
