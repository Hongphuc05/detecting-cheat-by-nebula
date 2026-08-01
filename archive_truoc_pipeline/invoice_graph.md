# Workspace Data Dictionary: invoice_graph

Mô hình dữ liệu Đồ thị Quản lý Hóa đơn Doanh nghiệp & Mạng lưới Xuất Hóa đơn.

## 📌 Các Đỉnh (Tags / Nodes)

### Tag `company` (Doanh nghiệp xuất / nhận hóa đơn)
- `ten_cong_ty` (string): Tên đầy đủ của công ty.
- `linh_vuc` (string): Lĩnh vực hoạt động kinh doanh (ví dụ: "Thương mại", "Xây dựng", "Dịch vụ").
- `dia_chi` (string): Địa chỉ trụ sở công ty.
- `doanh_thu` (int): Doanh thu báo cáo.
- `nam_bao_cao` (string): Năm tài chính báo cáo.

---

## 🔗 Các Cạnh (Edges / Relationships)

### Edge `xuat_hoa_don` (Hành vi Xuất Hóa đơn: Company -> Company)
- `so_hoa_don` (string): Mã số serie / số hóa đơn GTGT.
- `ngay_xuat` (string): Ngày phát hành hóa đơn (ví dụ: "2024-03-15").
- `mo_ta` (string): Nội dung dịch vụ / hàng hóa trên hóa đơn.
- `tien_chua_thue` (int): Số tiền trước thuế.
- `thue_gtgt` (int): Số tiền thuế giá trị gia tăng.
- `loai_gd` (string): Loại hình giao dịch.
- `nhan_ai` (int): Nhãn cảnh báo rủi ro AI (1 = Bất thường/Khống, 0 = Bình thường).

---

## ⚠️ CẢNH BÁO MẬT ĐỘ DỮ LIỆU — BẮT BUỘC ĐỌC TRƯỚC KHI SINH QUERY ĐA CHẶNG

Space này có 98 đỉnh nhưng **8.976 cạnh** (trung bình ~91 cạnh/đỉnh — RẤT DÀY), và có các đỉnh "hub" bậc cực cao (ví dụ công ty MST `0109082787` có ~196 cạnh trực tiếp). Đã crash server NebulaGraph THẬT NHIỀU LẦN từ các query đa chặng trên Space này. Vì vậy:

- **CẤM TUYỆT ĐỐI cú pháp biến thiên độ dài `*` (variable-length)** trên Space này — ví dụ `*1..`, `*2..4`, `*..3` đều CẤM, **kể cả khi đã neo điểm bắt đầu bằng `id(x) == "..."` và đã giới hạn số hop**. Neo + giới hạn hop KHÔNG đủ an toàn ở đây vì các đỉnh hub có quá nhiều cạnh, dò biến thiên độ dài từ 1 hub vẫn nổ tổ hợp và crash server.
- **CHỈ ĐƯỢC dùng chuỗi hop CỐ ĐỊNH** (liệt kê tường minh từng cạnh, không dùng `*`), ví dụ 3-hop cố định:
  `MATCH p=(c1:company)-[:xuat_hoa_don]->(c2:company)-[:xuat_hoa_don]->(c3:company)-[:xuat_hoa_don]->(c1) WHERE id(c1) == "0109082787" RETURN p LIMIT 50;`
  (Query này đã test thật, chạy ~1.6 giây.)
- Với truy vấn đa chặng cố định (2 chặng trở lên), **luôn bắt buộc neo** ít nhất 1 đỉnh bằng `WHERE id(x) == "..."` — không neo cũng đã từng crash server.
- Nếu người dùng hỏi "tìm vòng lặp mấy chặng cũng được" / không nêu rõ số chặng: sinh MỘT chuỗi cố định với số chặng cụ thể (khuyên dùng 3 hoặc 4), neo vào 1 MST ví dụ, và giải thích rõ trong câu trả lời là đã chọn số chặng cố định + 1 công ty mẫu vì lý do an toàn hiệu năng trên Space này.

## 💡 Cú pháp nGQL tham chiếu chuẩn cho Space này:
- Xem danh sách doanh nghiệp:
  `MATCH (c:company) RETURN c LIMIT 50;`
- Tìm hóa đơn giữa các công ty (1 chặng, an toàn, không cần neo):
  `MATCH p=(c1:company)-[:xuat_hoa_don]->(c2:company) RETURN p LIMIT 50;`
- Tìm vòng lặp gian lận 3-hop (đã test, an toàn — LUÔN neo + LUÔN cố định số hop, không dùng `*`):
  `MATCH p=(c1:company)-[:xuat_hoa_don]->(c2:company)-[:xuat_hoa_don]->(c3:company)-[:xuat_hoa_don]->(c1) WHERE id(c1) == "0109082787" RETURN p LIMIT 50;`
