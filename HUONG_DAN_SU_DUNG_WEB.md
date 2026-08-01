# Hướng dẫn sử dụng — Bàn làm việc rà soát gian lận

Giao diện web tách thành **2 đường dẫn riêng biệt**:

| Đường dẫn | Là gì |
|---|---|
| **`localhost:8080/`** | **Bàn làm việc rà soát gian lận** — nghiệp vụ theo 5 bước, toàn màn hình |
| **`localhost:8080/studio`** | **Console truy vấn nGQL** — trang cũ giữ nguyên 100%: editor, lịch sử, AI Copilot, kịch bản |

Hai trang có link qua lại ở header.

> **Điểm quan trọng của thiết kế:** ở trang rà soát, **đồ thị không chiếm chỗ** cho tới
> khi bấm "Xem sơ đồ" ở bước cuối. Bốn bước đầu dùng trọn màn hình cho nghiệp vụ.

---

## Khởi động

```bash
# 1) NebulaGraph
cd nebula_demo && docker compose up -d

# 2) Máy chủ web (macOS)
cd nebula_demo && ./server_mac
# Windows: go build -o server.exe main.go && .\server.exe
```

Mở `http://localhost:8080` — vào thẳng bàn làm việc rà soát.

Máy chủ tự tìm pipeline ở `../detecting_cheat_by_nebula/pipeline`. Đổi bằng biến môi trường:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `PIPELINE_DIR` | `../detecting_cheat_by_nebula/pipeline` | Nơi chứa script Python |
| `PYTHON_BIN` | `python3` | Trình thông dịch Python |
| `RUN_TIMEOUT_MIN` | `10` | Giới hạn cứng cho 1 lần chạy (phút) |

---

## 5 bước trên giao diện

Thanh bước nằm ngang trên đầu, hiện số liệu chốt của từng bước. Bấm quay lại bước
đã xong bất cứ lúc nào. Nút **Tiếp tục** ở thanh đáy chỉ mở khi bước hiện tại đủ điều kiện.

### Bước ① Dữ liệu

Ba vùng, tất cả dùng hết chiều ngang:

**Kiểm kê** — bảng liệt kê mọi không gian dữ liệu trong hệ thống: số doanh nghiệp,
số giao dịch, dải kỳ, có liên kết ngầm không, có ĐKKD không, **trần điểm**, lần chạy
gần nhất. Bấm một dòng để chọn. Không gian thiếu Company/TRADES bị làm mờ, không chọn được.

**Mô tả & xem trước** — tab cho từng bảng (`Doanh nghiệp` · `Giao dịch` · `Liên kết địa chỉ`
· `Người đại diện` · `Sở hữu vốn`), mỗi tab có 3 chế độ xem:

- *Dữ liệu* — **lưới kiểu bảng tính**: số dòng bên trái, tiêu đề cột cố định khi cuộn,
  bấm tiêu đề để sắp xếp, phân trang 50 dòng, số căn phải có phân cách nghìn.
  Mã số thuế giữ nguyên số 0 đầu (không bị đổi thành số). Cột mã/khoá (kỳ kê khai,
  số thứ tự cạnh) hiển thị nguyên số, **không** chèn dấu phân cách nghìn — kỳ
  `202101` không phải là một con số tiền tệ.
- *Mô tả cột* — tên cột, kiểu dữ liệu, ý nghĩa nghiệp vụ.
- *Chất lượng* — số DN, số cạnh, mật độ, giao dịch tự bán cho mình, DN thiếu tên,
  dải kỳ, và 3 loại liên kết ĐKKD có/không.

Khung này có nút **Mở rộng** (góc phải thanh tab) để bung thành popup toàn màn
hình — hữu ích khi bảng có nhiều cột phải cuộn ngang. Đóng bằng nút **Thu nhỏ**,
bấm ra ngoài, hoặc phím **Esc**.

**Nhập dữ liệu mới** — bấm `＋ Nhập dữ liệu mới`. Chọn nguồn:

- *Dùng dữ liệu có sẵn trong detecting_cheat_by_nebula/raw* — mỗi bộ dữ liệu nằm trong 1 thư mục
  con riêng (`raw/<tên_bộ>/`), nên trước khi bấm **Nhập dữ liệu** phải **chọn đúng
  1 bộ** trong danh sách hiện ra (mỗi thẻ ghi số DN/số hoá đơn của bộ đó). Nút Nhập
  bị mờ nếu chưa chọn bộ nào.
- *Tải lên cặp CSV chuẩn* — xem bảng yêu cầu định dạng từng cột, rồi chọn file.
  **Ngay khi chọn file, hệ thống đọc thử 20 dòng đầu và hiện lên lưới** để tự đối
  chiếu cột — nếu số cột không khớp sẽ cảnh báo đỏ ngay, trước khi nhập thật.

### Bước ② Nghiệp vụ

Lưới thẻ cho từng loại rà soát (hiện 1 loại dùng được, 3 loại để sẵn khung).
Chọn xong hiện panel tham số: kỳ từ/đến (có nút lấy toàn bộ dải kỳ thật), số chặng,
phương pháp dò.

Bên dưới là khối **Cách chấm điểm**: 5 tín hiệu với thanh tỷ lệ theo trọng số.
Tín hiệu nào không có dữ liệu nguồn thì bị gạch ngang và tô xám ngay tại đây.

### Bước ③ Kiểm tra

Tự quét khi vào bước. Hai cột:

- **Trái** — checklist đầy đủ, mỗi mục có mô tả chi tiết (không cắt ngắn) và dòng
  **"Cần gì để khắc phục"** cho mục đang thiếu.
- **Phải** — thanh 100 điểm chia 5 khúc theo trọng số. Khúc không đạt được tô xám.
  Nhìn một giây là hiểu vì sao trần chỉ 60.

### Bước ④ Chạy

Gom các bước kỹ thuật thành **3 quá trình nghiệp vụ**, mỗi quá trình có thanh tiến trình riêng:

1. *Chuẩn bị dữ liệu* — đọc nguồn, gộp cạnh, nạp đồ thị
2. *Dò chu trình khép kín* — khoanh vùng, duyệt đồ thị, khử trùng lặp
3. *Chấm điểm & lập báo cáo*

Số liệu hiện bằng tiếng Việt (`raw_cycles=2581` → "2.581 lượt xuất hiện chu trình").
**Nhật ký kỹ thuật thu gọn mặc định**, mở ra khi cần.

### Bước ⑤ Kết quả

Dải 5 thẻ số liệu, rồi bảng dùng hết chiều ngang với 3 tab:

- **Chu trình** — lọc theo mức (cờ đỏ/theo dõi), theo số chặng, tìm theo MST hoặc tên,
  sắp xếp theo cột. Bấm tên chuỗi để bung chi tiết từng cạnh (bên bán, bên mua, giá trị, kỳ).
- **Doanh nghiệp** — top MST xuất hiện trong nhiều cờ đỏ nhất.
- **File kết quả** — `report.txt` / `cycles.ngql` / `progress.log`, copy hoặc tải `.jsonl`.

**Trực quan hoá:** bấm **Xem sơ đồ** ở bất kỳ dòng nào → mở **ngăn trượt chiếm ~62%
màn hình từ bên phải**, chứa canvas đồ thị + Element Inspector. Doanh nghiệp trong chu
trình có viền đỏ dày. Đóng bằng nút ×, bấm ra ngoài, hoặc phím **Esc** — bảng kết quả
phía sau giữ nguyên bộ lọc.

Trong ngăn có nút **Xem câu lệnh nGQL** để đối chiếu chính xác câu đang chạy.

---

## API (dùng được độc lập, không cần giao diện)

| Endpoint | Method | Việc |
|---|---|---|
| `/api/fraud/manifest` | GET | Danh sách loại truy vấn + cách nhập dữ liệu |
| `/api/fraud/import` | POST | Nhập dữ liệu (JSON hoặc multipart) |
| `/api/fraud/validate` | POST | Quét Data Contract → checklist + trần điểm |
| `/api/fraud/run` | POST | Chạy pipeline → trả `run_id` ngay, chạy nền |
| `/api/fraud/stream?run_id=` | GET | **SSE** — tiến trình theo thời gian thực |
| `/api/fraud/stop` | POST | Hủy giữa chừng |
| `/api/fraud/runs` | GET | Danh sách lần chạy trong phiên |
| `/api/fraud/result?run_id=` | GET | Số liệu + top chu trình/doanh nghiệp |
| `/api/fraud/report?run_id=&file=` | GET | Tải `report.txt`/`cycles.ngql`/`progress.log`/`.jsonl` |
| `/api/fraud/cycle-ngql` | POST | Sinh nGQL vẽ chu trình từ danh sách MST |
| `/api/fraud/datasets` | GET | Kiểm kê mọi space: số DN, cạnh, dải kỳ, trần điểm, lần chạy gần nhất |
| `/api/fraud/schema?space=` | GET | Mô tả các bảng + ý nghĩa từng cột |
| `/api/fraud/preview?space=&table=&page=` | GET | Xem trước dữ liệu dạng lưới, có phân trang |
| `/api/fraud/quality?space=` | GET | Thống kê chất lượng dữ liệu |
| `/api/fraud/preview-upload` | POST | Đọc thử 20 dòng đầu file vừa chọn (chưa nhập thật) |
| `/api/fraud/raw-datasets` | GET | Liệt kê các bộ dữ liệu trong `raw/<tên_bộ>/` (số DN, số hoá đơn, cập nhật lần cuối) |

Ví dụ chạy trọn bằng dòng lệnh:

```bash
RUN=$(curl -s -XPOST localhost:8080/api/fraud/run \
  -d '{"space":"invoice_agg_graph","max_hops":5,"method":"dfs"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")

curl -N "localhost:8080/api/fraud/stream?run_id=$RUN"   # xem tiến trình
curl -s "localhost:8080/api/fraud/result?run_id=$RUN"   # lấy kết quả
curl -s "localhost:8080/api/fraud/report?run_id=$RUN"   # đọc report.txt
```

---

## Các lớp bảo vệ đã cài

| Rủi ro | Cách chặn |
|---|---|
| Chèn lệnh qua tên script | Danh sách trắng cố định trong Go; tên script chỉ lấy từ `datasources.json` |
| Chèn lệnh qua tham số | Truyền đối số dạng mảng (không qua shell); số bị ép kiểu; tên space đối chiếu với `SHOW SPACES` thật |
| Đọc file ngoài vùng | Danh sách trắng 4 tên file; `run_id` chặn bằng biểu thức chính quy; kiểm tra đường dẫn tuyệt đối nằm trong `output/runs/` |
| Tải file lên đè đường dẫn | `filepath.Base()` cắt hết thành phần đường dẫn; giới hạn 200MB |
| Chạy song song tranh chấp | Mỗi Space chỉ 1 lần chạy cùng lúc |
| Tiến trình treo vĩnh viễn | Timeout cứng 10 phút + nút Hủy |
| Mất kết quả khi restart | `run_id` của Go dùng luôn làm tên thư mục → đọc lại được từ đĩa |

---

## Sự cố thường gặp

**"space đang có lần chạy khác"** — đợi xong hoặc bấm Hủy.

**graphd chết (OOM)** — `docker start nebula-graphd`, chờ ~40 giây. Nếu tái diễn khi
bấm *Xem đồ thị*, kiểm tra xem nGQL sinh ra có bị đổi sang dạng chuỗi hop nối tiếp không.

**Nút "Chạy phát hiện" mờ** — phải quét dữ liệu ở bước 3 và kết quả phải hợp lệ.

**Sửa giao diện xong không thấy đổi** — phải build lại:
```bash
cd nebula_demo/frontend && npm run build
```

**Gõ `/studio` báo 404** — server chưa build lại sau khi thêm định tuyến SPA:
```bash
cd nebula_demo && go build -o server_mac main.go
```

**Ngăn sơ đồ mở ra trắng trơn** — vis-network đo kích thước vùng chứa ngay lúc khởi tạo,
nên ngăn phải được *mount khi mở* chứ không phải ẩn/hiện bằng CSS. Nếu sửa `GraphDrawer`
thành luôn mount rồi `hidden`, đồ thị sẽ khởi tạo với kích thước 0 và không vẽ được gì.
