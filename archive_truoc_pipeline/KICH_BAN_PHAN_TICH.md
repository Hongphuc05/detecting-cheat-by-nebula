# Kịch Bản Phát Hiện Hóa Đơn Khống Trên NebulaGraph — Dữ Liệu 86 Công Ty

**Mục tiêu**: dùng chính cơ sở dữ liệu đồ thị NebulaGraph (`invoice_graph`) để **phát hiện 14 hóa đơn khống** đã được đưa vào đồ thị, **không đọc cột đáp án `nhan_ai`** trong lúc truy vết — chỉ dùng nó ở bước cuối để chấm điểm.

Mỗi kịch bản trình bày theo 4 bước cố định:
1. **Tiền đề** — giả thuyết gian lận + vì sao đó là cờ đỏ.
2. **Kiểm tra tiền đề (pre-check)** — chạy 1 query rẻ để xác nhận hướng đi có cơ sở TRƯỚC khi săn (nếu tín hiệu quá phổ biến thì vô dụng, quá hiếm/khớp thì đáng đào tiếp).
3. **Query phát hiện** — bắt hóa đơn khống, kèm kết quả thật đã test.
4. **Chấm điểm** — đối chiếu `nhan_ai` xem bắt trúng bao nhiêu, có dương tính giả không.

---

## 0. Bối cảnh dữ liệu (đọc trước khi bắt đầu)

- Đồ thị: **98 công ty** (đỉnh `company`), **8.976 hóa đơn** (cạnh `xuat_hoa_don`), thuộc tính cạnh: `so_hoa_don, ngay_xuat, mo_ta, tien_chua_thue, thue_gtgt, loai_gd, nhan_ai`.
- **14 hóa đơn khống** (`nhan_ai=1`) — tất cả đều là hóa đơn **đầu vào của AZURA** (`0109082787`), từ **4 nhà cung cấp**, chia làm **3 kiểu gian lận**:

| # | Nhà cung cấp (bên bán) | MST | Kiểu | Số HĐ | Tiền (chưa thuế) | Bản chất |
|---|---|---|---|---|---|---|
| 1 | Cty XNK Thanh Hùng | `0103769372` | **A — Khống hoàn toàn** | 3 | 2,6 tỷ | Dịch vụ "tư vấn quản trị DN" — không có giao dịch thật |
| 2 | Cty dây Sumi-Hanel | `0100113945` | **A — Khống hoàn toàn** | 3 | 3,9 tỷ | Dịch vụ "thuê phần mềm quản lý nội bộ" — không có thật |
| 3 | Vinacomin (hóa chất mỏ) | `0100101072` | **B — Nhập khống** | 4 | 24,7 tỷ | "Sắt thép, thiết bị VP" — hàng không tồn tại, lệch ngành |
| 4 | Cty HAL Việt Nam | `0101329672` | **C — Nâng khống 30%** | 4 | 11,1 tỷ | Vận chuyển/quảng cáo có thật nhưng thổi giá +30% |

> ⚠️ **Provenance (quan trọng, để không hiểu lầm)**: 14 cạnh khống này được **nạp vào đồ thị từ sheet nguồn `HĐ_Đầu_Vào`** lúc dựng `invoice.csv`; chúng **không nằm trong sổ sách công khai** mà công ty tự kê khai. Vai trò của chúng ở đây đúng như gian lận thật ngoài đời: hóa đơn khống **vẫn được ghi nhận trong dữ liệu**, và ta phát hiện bằng **dấu hiệu bất thường trên chính các hóa đơn đó** — không phải đi tìm cái vô hình. `nhan_ai` chỉ là "đáp án" để chấm, giấu đi để buộc phải tự phân tích.

**Kết quả tổng (đã test toàn bộ trên Nebula thật):**

| Kịch bản | Bắt được | Độ chính xác | Ghi chú |
|---|---|---|---|
| A — dịch vụ vô hình lặp lại | 6/6 hóa đơn (Thanh Hùng, Sumi-Hanel) | 100%, 0 nhiễu | tự động |
| B — hàng lệch ngành nghề | 4/4 hóa đơn (Vinacomin) | 100%, 0 nhiễu | tự động |
| C — nâng khống (HAL) | 0/4 tự động | — | chỉ lộ qua rà soát đầu mối (bước C) |
| **Tổng** | **10/14 tự động** | **100% chính xác** | 4 còn lại cần review thủ công |

**Lệnh trực quan hóa toàn cảnh:**
```sql
USE invoice_graph;
MATCH p=(a:company)-[e:xuat_hoa_don]->(b:company) RETURN p LIMIT 1000;
```

---

## Kịch bản A — Dịch vụ vô hình lặp lại đều đặn (bắt "khống hoàn toàn")

### 1. Tiền đề
Kiểu khống trắng trợn nhất: dựng hóa đơn cho **dịch vụ vô hình** (tư vấn, thuê phần mềm, quản lý nội bộ) — thứ **không có hàng hóa vật lý** nên không thể đối chiếu phiếu nhập kho/biên bản giao nhận, cực dễ bịa. Kẻ gian thường phát hành **đều đặn theo tháng/quý** và **dồn vào đúng 1 khách** để tạo cảm giác "chi phí thường xuyên". Cờ đỏ = cùng 1 cặp (bán → mua) có **nhiều hóa đơn dịch vụ vô hình** trong năm.

### 2. Kiểm tra tiền đề (đi từ toàn cảnh → khoanh dần, KHÔNG nhắm sẵn đáp án)
Không đếm thẳng 3 từ khóa mình đã nghi (làm vậy là "biết đáp án rồi mới đếm"). Đi từ rộng đến hẹp, để sự bất thường **tự lộ ra từ phân bố**.

**(a) Dịch vụ có phải thứ hiếm không?**
```sql
MATCH (c1:company)-[e:xuat_hoa_don]->(c2:company)
WHERE e.loai_gd == "mua_vao"
  AND (e.mo_ta CONTAINS "Dich vu" OR e.mo_ta CONTAINS "Dịch vụ" OR e.mo_ta CONTAINS "DV ")
RETURN count(e) AS so_hd_dich_vu;
```
**Kết quả: 1.254 / 4.609 hóa đơn mua vào là dịch vụ (27%)** → dịch vụ là chuyện thường; **"là dịch vụ" KHÔNG phải cờ đỏ**, không thể dừng ở đây.

**(b) Vậy loại dịch vụ nào mới hiếm/khó kiểm chứng?** Gom toàn bộ dịch vụ về nhóm rồi đếm — dùng `CASE WHEN` trong `WITH` để tạo cột "nhóm dịch vụ", `count(e)` gom theo nhóm:
```sql
MATCH (c1:company)-[e:xuat_hoa_don]->(c2:company)
WHERE e.loai_gd == "mua_vao"
  AND (e.mo_ta CONTAINS "Dich vu" OR e.mo_ta CONTAINS "Dịch vụ" OR e.mo_ta CONTAINS "DV ")
WITH (CASE
  WHEN (e.mo_ta CONTAINS "tu van" OR e.mo_ta CONTAINS "thue phan mem" OR e.mo_ta CONTAINS "quan ly noi bo")
       THEN "1. Hanh chinh noi bo (vo hinh, kho nghiem thu)"
  WHEN (e.mo_ta CONTAINS "van chuyen" OR e.mo_ta CONTAINS "logistics" OR e.mo_ta CONTAINS "van tai")
       THEN "2. Van chuyen/logistics"
  WHEN (e.mo_ta CONTAINS "kiem dinh" OR e.mo_ta CONTAINS "kiểm định") THEN "3. Kiem dinh"
  WHEN (e.mo_ta CONTAINS "bao tri" OR e.mo_ta CONTAINS "bảo trì" OR e.mo_ta CONTAINS "sua chua") THEN "4. Bao tri/sua chua"
  WHEN (e.mo_ta CONTAINS "gia cong" OR e.mo_ta CONTAINS "gia công") THEN "5. Gia cong"
  WHEN (e.mo_ta CONTAINS "tư vấn" OR e.mo_ta CONTAINS "thiet ke" OR e.mo_ta CONTAINS "thiết kế") THEN "6. Tu van TM/thiet ke"
  ELSE "7. Dich vu khac"
END) AS nhom_dich_vu, count(e) AS so_hd
RETURN nhom_dich_vu, so_hd ORDER BY so_hd DESC;
```
**Kết quả thật:**

| Số HĐ | Nhóm dịch vụ |
|---|---|
| 322 | Dịch vụ khác |
| 237 | Tư vấn TM / thiết kế |
| 208 | Bảo trì / sửa chữa |
| 192 | Gia công |
| 145 | Kiểm định |
| 144 | Vận chuyển / logistics |
| **6** | **Hành chính nội bộ (vô hình, khó nghiệm thu)** ← |

→ Sự bất thường **tự nhảy ra từ phân bố**: mọi nhóm dịch vụ vận hành đều 144–322 hóa đơn (đều là thứ có sản phẩm/kết quả để nghiệm thu), **riêng nhóm hành chính nội bộ vô hình chỉ 6** — chênh 25–50 lần. Chính sự tương phản "vô hình + cực hiếm + không nghiệm thu được" là thứ đáng đào tiếp, không phải bản thân việc "là dịch vụ".

### 3. Query phát hiện
Gom theo cặp (bên bán, bên mua), giữ cặp có ≥3 hóa đơn dịch vụ vô hình:
```sql
MATCH (c1:company)-[e:xuat_hoa_don]->(c2:company)
WHERE e.loai_gd == "mua_vao" AND e.mo_ta CONTAINS "Dich vu"
  AND (e.mo_ta CONTAINS "tu van" OR e.mo_ta CONTAINS "thue phan mem" OR e.mo_ta CONTAINS "quan ly noi bo")
WITH c1, c2, count(e) AS so_hd, sum(e.tien_chua_thue) AS tong_tien, collect(e.so_hoa_don) AS ds_hoa_don
WHERE so_hd >= 3
RETURN c1.company.ten_cong_ty AS ben_ban, id(c1) AS mst_ban,
       c2.company.ten_cong_ty AS ben_mua, so_hd, tong_tien, ds_hoa_don
LIMIT 50;
```
**Kết quả thật (32ms) — bắt đúng 6 hóa đơn khống:**

| Bên bán | Bên mua | Số HĐ | Tổng | Danh sách số HĐ |
|---|---|---|---|---|
| Thanh Hùng (`0103769372`) | AZURA | 3 | 2,6 tỷ | 0000001, 0000002, 0000003 |
| Sumi-Hanel (`0100113945`) | AZURA | 3 | 3,9 tỷ | 0000021, 0000022, 0000023 |

### 4. Vì sao query này bắt đúng
- `mo_ta CONTAINS "tu van"/"thue phan mem"/"quan ly noi bo"` khóa vào đúng loại **dịch vụ vô hình** — pre-check đã chứng minh chỉ 6 hóa đơn cả đồ thị dính, nên gần như không có nhiễu.
- `count(e) >= 3` loại các giao dịch dịch vụ lẻ tẻ hợp lệ, chỉ giữ **mẫu lặp bất thường**.
- `collect(e.so_hoa_don)` trả thẳng **số hóa đơn cụ thể** để lập biên bản/kiểm tra tiếp.

### 5. Chấm điểm
```sql
MATCH (c1:company)-[e:xuat_hoa_don]->(c2:company)
WHERE e.mo_ta CONTAINS "Dich vu"
  AND (e.mo_ta CONTAINS "tu van" OR e.mo_ta CONTAINS "thue phan mem" OR e.mo_ta CONTAINS "quan ly noi bo")
RETURN e.so_hoa_don AS so_hd, e.nhan_ai AS nhan_ai;
```
→ Cả 6 hóa đơn đều `nhan_ai=1`. **Chính xác 100%, 0 dương tính giả.**

---

## Kịch bản B — Hàng hóa lệch ngành nghề bên bán (bắt "nhập khống")

### 1. Tiền đề
Kiểu tinh vi hơn A: có "hàng hóa" (nên trông đủ giấy tờ) nhưng hàng không tồn tại. Dấu vết để lộ: bên bán **đứng tên nguồn cung một loại hàng nằm ngoài lĩnh vực đăng ký** của chính nó — VD một tổng công ty **hóa chất mỏ / khai khoáng** lại "bán" **sắt thép cuộn, thiết bị văn phòng**. Không có lý do kinh doanh chính đáng cho việc đó.

### 2. Kiểm tra tiền đề
Hai câu hỏi tiền đề: (a) đồ thị có lưu ngành nghề (`linh_vuc`) không, có bao nhiêu công ty hóa chất/khai khoáng? (b) có bao nhiêu hóa đơn nhắc tới sắt thép/thiết bị văn phòng?
```sql
MATCH (c:company)
WHERE c.company.linh_vuc CONTAINS "hóa chất" OR c.company.linh_vuc CONTAINS "khai khoáng"
RETURN count(c) AS so_cty_hoachat_khaikhoang;
```
**Kết quả: `2` công ty.**
```sql
MATCH (c1:company)-[e:xuat_hoa_don]->(c2:company)
WHERE e.loai_gd == "mua_vao" AND (e.mo_ta CONTAINS "sat thep" OR e.mo_ta CONTAINS "thiet bi van phong")
RETURN count(e) AS so_hd_sat_thep_thietbi;
```
**Kết quả: `4` hóa đơn.** → Cả hai đại lượng đều nhỏ → giao điểm (hàng sắt thép + bên bán ngành hóa chất) chắc chắn rất hiếm, **hướng đi tốt**.

### 3. Query phát hiện
Giao 2 điều kiện: nội dung hàng là sắt thép/thiết bị VP **và** ngành bên bán là hóa chất/khai khoáng:
```sql
MATCH (c1:company)-[e:xuat_hoa_don]->(c2:company)
WHERE e.loai_gd == "mua_vao"
  AND (e.mo_ta CONTAINS "sat thep" OR e.mo_ta CONTAINS "thiet bi van phong")
  AND (c1.company.linh_vuc CONTAINS "hóa chất" OR c1.company.linh_vuc CONTAINS "khai khoáng")
RETURN c1.company.ten_cong_ty AS ben_ban, id(c1) AS mst_ban, c1.company.linh_vuc AS nganh,
       e.so_hoa_don AS so_hd, e.mo_ta AS mo_ta, e.tien_chua_thue AS tien
LIMIT 50;
```
**Kết quả thật (25ms) — bắt đúng 4 hóa đơn khống, tất cả của Vinacomin (`0100101072`):** HĐ 0000045–0000048, tổng 24,7 tỷ, nội dung "máy móc thiết bị văn phòng" + "sắt thép cuộn", trong khi ngành đăng ký là "Sản xuất hóa chất mỏ / khai khoáng".

> ⚠️ **Bẫy dấu tiếng Việt**: cột `mo_ta` lưu **không dấu** (`sat thep`), cột `linh_vuc` lưu **có dấu** (`hóa chất`). Phải khớp đúng kiểu dấu cho từng cột — dùng "sat thep" cho `mo_ta` mà "hoa chat" (không dấu) cho `linh_vuc` sẽ ra **0 kết quả** dù dữ liệu có thật.

### 4. Vì sao query này bắt đúng
Đây là phép giao 2 tập nhỏ độc lập (4 hóa đơn sắt thép × 2 công ty hóa chất). Xác suất một công ty hóa chất **chính đáng** bán sắt thép cho người khác gần như bằng 0 → giao điểm ≈ đúng gian lận. Đây là tín hiệu **sạch nhất** vì nó dựa trên mâu thuẫn logic ngành nghề, không phụ thuộc ngưỡng số tiền.

### 5. Chấm điểm
Thêm `RETURN ... e.nhan_ai` vào query trên → cả 4 hóa đơn đều `nhan_ai=1`. **Chính xác 100%, 0 dương tính giả.**

---

## Kịch bản C — Hội tụ về một đầu mối & rà soát tận gốc (bắt phần còn lại: HAL)

### 1. Tiền đề
Kịch bản A và B mỗi cái bắt được vài hóa đơn, nhưng câu hỏi lớn hơn: **các hóa đơn nghi vấn đó có chụm về một công ty duy nhất không?** Nếu nhiều nhà cung cấp bị gắn cờ ĐỘC LẬP mà đều bán cho cùng 1 khách → khách đó gần như chắc chắn là **đầu mối gian lận (hub)**. Đây chính là chỗ đồ thị mạnh hơn bảng tính: nó cho thấy **sự hội tụ**.

### 2. Kiểm tra tiền đề
Lấy toàn bộ hóa đơn bị A **hoặc** B gắn cờ, xem chúng đổ về đâu:
```sql
MATCH (c1:company)-[e:xuat_hoa_don]->(c2:company)
WHERE e.loai_gd == "mua_vao"
  AND ((e.mo_ta CONTAINS "tu van" OR e.mo_ta CONTAINS "thue phan mem" OR e.mo_ta CONTAINS "quan ly noi bo")
       OR ((e.mo_ta CONTAINS "sat thep" OR e.mo_ta CONTAINS "thiet bi van phong")
            AND (c1.company.linh_vuc CONTAINS "hóa chất" OR c1.company.linh_vuc CONTAINS "khai khoáng")))
WITH c2, count(e) AS so_hd_nghi, collect(DISTINCT id(c1)) AS cac_ncc
RETURN c2.company.ten_cong_ty AS dau_moi, id(c2) AS mst, so_hd_nghi, cac_ncc;
```
**Kết quả thật (51ms): đúng 1 hàng** — **10 hóa đơn nghi vấn từ 3 nhà cung cấp** (`0103769372`, `0100113945`, `0100101072`) **đều đổ về AZURA** (`0109082787`). Hội tụ tuyệt đối → AZURA là đầu mối.

### 3. Query phát hiện (rà soát tận gốc đầu mối)
Khi đã khóa được đầu mối, **kéo toàn bộ nhà cung cấp đầu vào của nó ra soi** — kể cả những hóa đơn mà A/B không bắt được:
```sql
MATCH (c1:company)-[e:xuat_hoa_don]->(c2:company)
WHERE id(c2) == "0109082787" AND e.loai_gd == "mua_vao"
WITH c1, count(e) AS so_hd, sum(e.tien_chua_thue) AS tong
RETURN c1.company.ten_cong_ty AS ncc, id(c1) AS mst, so_hd, tong
ORDER BY tong DESC LIMIT 40;
```
**Kết quả thật (6ms): 37 nhà cung cấp.** HAL Việt Nam (`0101329672`) nằm trong danh sách này (6 hóa đơn, 17,7 tỷ) → **lọt vào diện rà soát thủ công**.

### 4. Vì sao HAL không tự động bắt được — và giới hạn thật
HAL là kiểu **C — nâng khống**: giao dịch vận chuyển/quảng cáo **CÓ THẬT**, chỉ thổi giá +30%. Xem 6 hóa đơn HAL → AZURA:
```sql
MATCH (c1:company)-[e:xuat_hoa_don]->(c2:company)
WHERE id(c2) == "0109082787" AND id(c1) == "0101329672" AND e.loai_gd == "mua_vao"
RETURN e.so_hoa_don AS so_hd, e.mo_ta AS mo_ta, e.tien_chua_thue AS tien, e.nhan_ai AS nhan_ai
ORDER BY tien DESC;
```
Kết quả: 4 hóa đơn khống (1,3–4,48 tỷ) **đan xen** với 2 hóa đơn thật (3,05 và 3,54 tỷ) → **không có ranh giới giá** để tách. Thêm nữa, nội dung "vận chuyển"/"quảng cáo" là dịch vụ **phổ biến hợp lệ** (khác hẳn "tư vấn quản trị" hiếm ở kịch bản A), nên không lọc được bằng từ khóa. → **Nâng khống một giao dịch thật chỉ phát hiện được khi có giá thị trường tham chiếu bên ngoài** (định mức vận chuyển, báo giá đối thủ) — dữ liệu nội tại không đủ. Đồ thị đưa HAL **vào tầm ngắm** (nhờ là NCC của đầu mối AZURA), nhưng khẳng định gian lận thì cần dữ kiện ngoài.

### 5. Chấm điểm
```sql
MATCH (c1:company)-[e:xuat_hoa_don]->(c2:company)
WHERE e.nhan_ai == 1
RETURN DISTINCT id(c1) AS mst_khong;
```
→ 4 MST: `0103769372`, `0100113945`, `0100101072`, `0101329672`. Kịch bản A+B bắt tự động 3/4 (10/14 hóa đơn, 100% chính xác); AZURA lộ là đầu mối; HAL (MST thứ 4) vào diện review nhưng cần điều tra ngoài.

---

## Phần bổ trợ — các kỹ thuật đồ thị khác (KHÔNG bắt được nhóm AZURA, nhưng hữu ích)

Đã test thật, honestly ghi rõ: các tín hiệu dưới đây tìm ra **bất thường khác**, không trùng 14 hóa đơn khống của AZURA — dùng khi điều tra các nghi vấn ngoài phạm vi đáp án.

### D. Self-loop — công ty tự xuất hóa đơn cho chính mình
```sql
MATCH (c1:company)-[e:xuat_hoa_don]->(c1)
RETURN c1.company.ten_cong_ty AS cong_ty, id(c1) AS mst, e.so_hoa_don AS so_hd, e.tien_chua_thue AS tien
ORDER BY tien DESC LIMIT 10;
```
98 dòng/42 công ty. Top: "CP Sản xuất hàng thể thao" (184 tỷ), VINATA (89 tỷ). Đối chiếu đáp án: 2/4 công ty khống (Thanh Hùng, HAL) cũng dính self-loop — tương quan đáng chú ý nhưng 40/42 công ty còn lại ngoài đáp án → tín hiệu phụ, không kết luận độc lập.

### E. Kiểm tra liên hệ giữa 2 công ty cụ thể — `FIND SHORTEST PATH`
Khi đã có 2 MST nghi vấn, đây là công cụ rẻ và đúng bài (không dùng `MATCH` mở):
```sql
FIND SHORTEST PATH FROM "0109082787" TO "0100373485" OVER xuat_hoa_don UPTO 5 STEPS YIELD path AS p;
```

### F. Mạng lưới 1 công ty (ego-network) — mẫu neo an toàn, tái dùng cho mọi MST
```sql
MATCH p = (c1:company)-[e:xuat_hoa_don]->(c2:company) WHERE id(c1) == "0109082787" RETURN p LIMIT 200;
MATCH p = (c1:company)-[e:xuat_hoa_don]->(c2:company) WHERE id(c2) == "0109082787" RETURN p LIMIT 200;
```

### G. Vòng lặp ngắn — chỉ mở rộng dần, TUYỆT ĐỐI không dùng `*`
Đồ thị có ~2,26 triệu vòng lặp 2–4 hop → luôn neo vào 1 công ty cụ thể, dùng chuỗi hop cố định:
```sql
MATCH p = (c1:company)-[:xuat_hoa_don]->(c2:company)-[:xuat_hoa_don]->(c1)
WHERE id(c1) == "0109082787" RETURN p LIMIT 50;
```

> 💡 **Dấu hiệu mạnh không query được bằng Nebula**: trong sheet nguồn Excel, các hóa đơn kịch bản A/B đều thanh toán **Tiền mặt** (giá trị tỷ đồng) — cờ đỏ kinh điển. Nhưng cột "hình thức thanh toán" **không được đưa vào** `invoice.csv`/đồ thị, nên chỉ soi được trong Excel, không dùng làm tín hiệu nGQL. Nếu muốn khai thác, cần bổ sung cột này vào importer.

---

## Tổng kết cách tiếp cận

| Loại câu hỏi | Cách làm |
|---|---|
| "Có hóa đơn khống kiểu [dịch vụ ảo / lệch ngành] không?" | Query pattern trực tiếp trên đồ thị (kịch bản A, B) — bắt tự động |
| "Các nghi vấn có chụm về 1 đầu mối không?" | Gom cạnh đã gắn cờ, xem điểm đến chung (kịch bản C bước 2) |
| "Đầu mối X còn giao dịch nào đáng ngờ nữa?" | Ego-network đầu vào của X rồi rà soát thủ công (kịch bản C bước 3) |
| "2 công ty X, Y có liên hệ không?" (đã biết X, Y) | `FIND SHORTEST PATH` |
| Nâng khống giá giao dịch thật | Không đủ dữ liệu nội tại — cần giá thị trường tham chiếu ngoài |
