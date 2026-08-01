# Báo Cáo Kiểm Thử NebulaGraph — Space `invoice_graph` (86 công ty)

Nhật ký thử nghiệm thực tế query trên Space `invoice_graph` (dữ liệu hóa đơn mua/bán 86 công ty + 12 đối tác ngoài). Mỗi lần thử query mới, thêm 1 mục vào **Phần 3 — Nhật Ký Thử Nghiệm** theo mẫu có sẵn.

---

## 1. Thông tin nền (đo đạc thật)

| Chỉ số | Giá trị |
|---|---|
| Số đỉnh (`company`) | 98 |
| Số cạnh (`xuat_hoa_don`) | 8.976 |
| Số cặp công ty-công ty duy nhất có giao dịch | 4.604 / 9.506 cặp có thể (~48% mật độ) |
| Bậc trung bình (out-degree) | ~91 cạnh/đỉnh |
| Đỉnh "hub" bậc cao nhất | AZURA (MST `0109082787`) — ~196 cạnh trực tiếp |
| Tổng số vòng lặp 2-4 hop (đo bằng networkx offline) | **2.259.398** |
| Số công ty tham gia ≥1 vòng lặp | 95 / 98 |
| Số vòng lặp 1-hop (tự xuất hóa đơn cho chính mình) | 42 |
| Số vòng lặp 2-hop (cặp mua bán qua lại) | 1.729 |
| Số vòng lặp 3-hop | 54.332 |
| Số vòng lặp 4-hop | 2.203.295 |

**Kết luận nền tảng**: đây là đồ thị RẤT DÀY so với số đỉnh. Mọi query đa chặng (2+ hop) đều có nguy cơ nổ tổ hợp nếu không kiểm soát chặt.

---

## 2. Quy tắc an toàn đã rút ra (bắt buộc tuân theo)

| # | Quy tắc | Vì sao |
|---|---|---|
| 1 | Luôn khai báo `rank` khi import cạnh nhiều-quan-hệ giữa cùng 1 cặp đỉnh | Thiếu `rank` → NebulaGraph coi mọi cạnh cùng (src,dst) là 1 cạnh duy nhất (rank=0 mặc định), ghi đè lẫn nhau, mất dữ liệu |
| 2 | **Cấm cú pháp biến thiên độ dài `*`** (`*1..`, `*2..4`...) trên Space này, dù có neo hay giới hạn hop | Đã crash server NHIỀU LẦN kể cả khi có neo — đỉnh hub bậc cao làm nổ tổ hợp ngay cả khi giới hạn hop |
| 3 | Chỉ dùng chuỗi hop **cố định** (liệt kê tường minh từng `-[:e]->`, không dùng `*`) | Engine chỉ mở đúng số lớp cần thiết, không phải dò+lưu nhiều độ dài cùng lúc |
| 4 | Query đa chặng (2+ hop) **luôn phải neo** ít nhất 1 đỉnh bằng `WHERE id(x) == "..."` | Không neo = thử từ cả 98 đỉnh cùng lúc → nổ tổ hợp |
| 5 | Muốn tìm/khám phá điều gì đó **mới** trên toàn đồ thị (VD "tìm tất cả vòng lặp") → làm bằng script Python/networkx offline trên CSV, KHÔNG dùng query trực tiếp trên Nebula | Nebula tối ưu cho truy vấn có phạm vi rõ ràng, không phải thuật toán toàn đồ thị |
| 6 | Sau khi NebulaGraph crash & restart, **luôn phải tắt và chạy lại `server.exe`** | Pool kết nối cũ trong `server.exe` không tự phục hồi, mọi query sau đó treo tới khi restart |
| 7 | Luôn có `LIMIT` trên mọi query trả về path/node/edge | Chặn kết quả tràn, dù không chặn được chi phí tính toán |

---

## 3. Nhật Ký Thử Nghiệm

> Mẫu để copy khi thêm thử nghiệm mới:
> ```
> ### [Ngày giờ] — [Tên ngắn gọn]
> **Query:**
> ```sql
> ...
> ```
> **Kỳ vọng:** ...
> **Kết quả thực tế:** ...
> **Thời gian chạy:** ...
> **Kết luận / rule rút ra:** ...
> ```

### 24/07/2026 12:04 — Import thiếu `rank`
**Query/hành động:** Chạy `nebula-importer` với `invoice.csv` không có cột `rank`.
**Kỳ vọng:** 8.976 cạnh.
**Kết quả thực tế:** Chỉ ra 4.608 cạnh — nhiều hóa đơn cùng cặp công ty bị ghi đè lẫn nhau.
**Kết luận:** Thêm cột `rank` (số thứ tự tăng dần) vào CSV + khai báo trong YAML. Phải `CLEAR SPACE` trước khi import lại.

### 24/07/2026 12:2x — Vòng lặp 3-hop cố định, KHÔNG neo
```sql
MATCH p=(c1:company)-[:xuat_hoa_don]->(c2:company)-[:xuat_hoa_don]->(c3:company)-[:xuat_hoa_don]->(c1)
RETURN p LIMIT 5;
```
**Kỳ vọng:** Danh sách vòng lặp 3-hop.
**Kết quả thực tế:** **CRASH graphd** (treo rồi chết hẳn tiến trình, để lại PID file cũ).
**Kết luận:** Cần `stop all` + xóa `/usr/local/nebula/pids/*.pid` + `start all` để phục hồi. → Rule #4 (bắt buộc neo).

### 24/07/2026 13:4x — Vòng lặp 3-hop cố định, CÓ neo AZURA
```sql
MATCH p=(c1:company)-[:xuat_hoa_don]->(c2:company)-[:xuat_hoa_don]->(c3:company)-[:xuat_hoa_don]->(c1)
WHERE id(c1) == "0109082787"
RETURN p LIMIT 5;
```
**Kỳ vọng:** Vòng lặp 3-hop bắt đầu/kết thúc tại AZURA.
**Kết quả thực tế:** ✅ THÀNH CÔNG — ~1.6 giây, tìm được vòng lặp thật: AZURA → VINACO (0102712091) → CMS Vina (0104380966) → AZURA.
**Kết luận:** Đây là mẫu AN TOÀN chuẩn — neo + cố định hop.

### 24/07/2026 ~14:00 — AI Copilot tự sinh `*1..` không neo
```sql
MATCH p = (c1:company)-[:xuat_hoa_don*1..]->(c2:company) WHERE id(c1) == id(c2) RETURN p LIMIT 50;
```
**Kỳ vọng:** (Gemini tự sinh từ prompt "tìm công ty có mối quan hệ nhiều hop mà vẫn quay lại").
**Kết quả thực tế:** **CRASH graphd** — hop không giới hạn trên (`*1..`) + không neo.
**Kết luận:** Vá rule AI Copilot (`ai_service.go`): cấm `*` không giới hạn trên, bắt buộc neo.

### 24/07/2026 ~14:07 — Vòng lặp `*2..4` CÓ giới hạn hop nhưng KHÔNG neo cụ thể
```sql
MATCH p = (c1:company)-[:xuat_hoa_don*2..4]->(c2:company) WHERE id(c1) == id(c2) RETURN p LIMIT 50;
```
**Kỳ vọng:** Test xem giới hạn hop có đủ an toàn không khi chưa neo 1 công ty cụ thể.
**Kết quả thực tế:** **CRASH graphd lần nữa.**
**Kết luận:** Giới hạn hop KHÔNG đủ nếu không neo — quá nhiều điểm xuất phát (98 công ty) vẫn nổ tổ hợp.

### 24/07/2026 ~14:07 (bản neo AZURA cụ thể)
```sql
MATCH p = (c1:company)-[:xuat_hoa_don*2..4]->(c2:company) WHERE id(c1) == id(c2) AND id(c1) == "0109082787" RETURN p LIMIT 5;
```
**Kỳ vọng:** An toàn vì đã neo cụ thể.
**Kết quả thực tế:** **VẪN CRASH** — vì AZURA là hub bậc cao (~196 cạnh), dò biến thiên độ dài (`*`) từ 1 hub vẫn quá nặng.
**Kết luận:** → Rule #2: cấm hẳn `*` trên Space này, không chỉ "neo là đủ".

### 24/07/2026 ~14:1x — Connection pool treo sau crash
**Hiện tượng:** Sau khi NebulaGraph crash+restart, `server.exe` (đang chạy từ trước) khiến MỌI query (kể cả `SHOW EDGES;`, `USE invoice_graph;`) treo "Executing..." rất lâu.
**Kết luận:** Không phải lỗi Nebula — pool kết nối cũ trong `server.exe` không tự nhận ra Nebula đã đổi tiến trình. Tắt + chạy lại `server.exe` là hết ngay (test lại `SHOW TAGS;` chỉ mất 1.17ms sau khi restart). → Rule #6.

### 24/07/2026 ~14:2x — Phân tích offline bằng networkx (không đụng Nebula)
**Hành động:** Load toàn bộ `invoice.csv` vào `networkx.DiGraph`, chạy `nx.simple_cycles(G, length_bound=4)`.
**Kết quả:** 2.259.398 vòng lặp (2-4 hop), 95/98 công ty tham gia ≥1 vòng lặp — xác nhận vì sao mọi query mở trên Nebula đều nổ tổ hợp. Số liệu chi tiết ở Phần 1.
**Kết luận:** Khám phá toàn đồ thị nên làm offline bằng thuật toán chuyên dụng, không ép Nebula làm việc này. → Rule #5.

### [Chưa chạy] — Đề xuất tiếp theo: 1-hop tự vòng lặp (an toàn, chưa test thật)
```sql
MATCH (c1:company)-[:xuat_hoa_don]->(c1)
RETURN c1.company.ten_cong_ty AS cong_ty LIMIT 50;
```
**Kỳ vọng:** 42 công ty (khớp số đếm offline ở Phần 1).
**Kết quả thực tế:** _(điền sau khi chạy thật)_
**Kết luận:** _(điền sau)_

---

## 4. Việc cần làm tiếp

- [ ] Chạy thử query 1-hop tự vòng lặp ở trên, xác nhận ra đúng 42 kết quả
- [ ] Thử query 2-hop mua bán qua lại (không neo) — xem có an toàn không (ước tính ~812K đường đi cần dò, cùng cấp độ với query 3-hop-có-neo đã thành công)
- [ ] Ghi lại kết quả vào mục 3 theo mẫu
