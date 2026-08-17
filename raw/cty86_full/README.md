# `cty86_full` — bộ 53 công ty đủ trường (test trần điểm 100)

> Sinh 07/08/2026, từ `raw/output.xlsx` (DKKD thật, 53 MST) + `raw/hanoi_98cty/company.csv`
> + `raw/hanoi_98cty/invoice.csv` (dữ liệu mua-bán thật, 98 công ty gốc).
>
> **Đổi tên 07/08/2026**: thư mục vốn tên `cty86_full`, đổi sang `cty86_full` vì NebulaGraph
> KHÔNG cho phép tên space bắt đầu bằng số (`SyntaxError: syntax error near '86'` — đã tự kiểm
> chứng trực tiếp trên Nebula, không phải giới hạn tự đặt ra). UI import hiện tại dùng ĐÚNG tên
> thư mục trong `raw/` làm tên space luôn, không có ô nhập tên space riêng — nên tên thư mục PHẢI
> hợp lệ làm tên space Nebula (bắt đầu bằng chữ hoặc gạch dưới).

## Nguồn & phạm vi

- **53 công ty** — đúng bằng số MST khớp được trong `output.xlsx` (không phải 56 như ước tính
  ban đầu — đã đối chiếu trực tiếp, cả 53 đều khớp `raw/hanoi_98cty/company.csv`).
- **5.089 hoá đơn** — lọc từ 8.976 hoá đơn gốc, giữ lại đúng những dòng có **CẢ 2 phía** (bên bán
  và bên mua) đều nằm trong 53 công ty này (quan hệ NỘI BỘ của tập 53, không kéo theo 45 công ty
  còn lại của bộ 98 gốc). Gộp theo tháng ra 4.351 cạnh TRADES.

## Cột trong `company.csv` (7 cột, không có header, đọc theo vị trí)

```
mst, ten_cong_ty, linh_vuc, dia_chi, doanh_thu, nam_bao_cao, trang_thai
```

6 cột đầu giống hệt format `hanoi_98cty/company.csv`. Cột thứ 7 (`trang_thai`) là **MỚI** — lấy
từ cột "Trạng thái" của `output.xlsx` (DKKD thật, tratencongty.com), để trống nếu không có dữ
liệu (KHÔNG suy diễn "đang hoạt động" khi không biết).

## Đâu là THẬT, đâu là GIẢ LẬP — đọc kỹ trước khi dùng bộ này cho báo cáo/demo

**53 công ty, tên/địa chỉ/ngành/doanh thu/trạng thái ĐKKD, 5.089 hoá đơn mua-bán: TẤT CẢ THẬT.**

Chỉ **3 công ty** bị chỉnh sửa thủ công để bộ dữ liệu có đủ tín hiệu test trần điểm 100/100
(dữ liệu thật vốn dĩ **không có** công ty nào trùng địa chỉ hay ở trạng thái bất thường — đã
kiểm chứng trên toàn bộ 53 công ty trước khi sửa):

| MST | Trường bị đổi | Giá trị thật trước đó | Giá trị GIẢ LẬP đã gán |
|---|---|---|---|
| `0100100590` | `trang_thai` | (trống — không có dữ liệu) | `Tạm ngừng kinh doanh` |
| `0100373485` | `dia_chi` | `Số 19 Lê Văn Hưu, Phường Phạm Đình Hổ, Quận Hai Bà Trưng, TP Hà Nội` | `Số 99 phố Test Giả Lập, Phường Đồng Bộ, Quận Hoàn Kiếm, Hà Nội` |
| `0101437981` | `dia_chi` | `336 tổ 7 xóm Mới, phường Thanh Xuân Trung, Thanh Xuân, Hà Nội` | `Số 99 phố Test Giả Lập, Phường Đồng Bộ, Quận Hoàn Kiếm, Hà Nội` (giống hệt `0100373485`) |

Cả 3 công ty này đều là thành viên của cùng 1 chu trình 5 chặng THẬT (điểm 60/100 với đúng dữ
liệu thật — cân bằng giá trị + nén thời gian + VAT bất thường đều đạt tối đa): `0100100590 →
0100373485 → 0101437981 → 0102625829 → 0100113494 → 0100100590`. Sau khi thêm 2 chỉnh sửa trên,
chu trình này đạt đủ 100/100 — dùng để kiểm chứng thuật toán chấm điểm hoạt động đúng khi có đủ
5 tín hiệu, KHÔNG phải bằng chứng 3 công ty trên có hành vi gian lận thật.

**Không dùng bộ dữ liệu này để kết luận về 3 công ty trên trong bất kỳ báo cáo/demo ra bên
ngoài nào** — địa chỉ/trạng thái của họ trong bộ này là dữ liệu giả lập cho mục đích kiểm thử.

## Bug đã fix kèm theo (không thuộc riêng bộ data này)

`pipeline/detect_circular_trading.py::load_risky_companies()` trước đây so sánh `status !=
"active"` (literal tiếng Anh) — dữ liệu ĐKKD thật ghi tiếng Việt (`"Đang hoạt động"`), nên MỌI
công ty có trạng thái bình thường đều bị tính nhầm là rủi ro. Đã sửa sang đối chiếu danh sách
trạng thái BẤT THƯỜNG đã biết (`_RISKY_STATUSES`), áp dụng cho mọi bộ dữ liệu có `status` tiếng
Việt, không riêng `cty86_full`.

## Cách import test

```bash
cd detecting_cheat_by_nebula/pipeline
DATASET=cty86_full python3 ingest_csv86.py
SPACE=<ten_space_test> python3 load_schema.py   # tao tag Company co them cot `status`
SPACE=<ten_space_test> python3 sync_graph.py
SPACE=<ten_space_test> PERIOD_FROM=202101 PERIOD_TO=202112 MAX_HOPS=5 python3 detect_circular_trading.py
```

⚠️ KHÔNG dùng chung space `invoice_agg_graph` đã có sẵn — tag `Company` ở đó được tạo TRƯỚC khi
thêm cột `status`, và `CREATE TAG IF NOT EXISTS` không tự thêm cột vào tag đã tồn tại. Dùng 1
space MỚI (chưa từng tạo) để tag được tạo đầy đủ 6 thuộc tính ngay từ đầu.
