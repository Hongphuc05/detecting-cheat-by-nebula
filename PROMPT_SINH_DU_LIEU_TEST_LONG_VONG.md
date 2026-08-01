# Prompt — Sinh bộ dữ liệu test `data_test_mua_ban_long_vong` (dùng cho Google Antigravity)

> Dán nguyên văn phần **"NỘI DUNG PROMPT"** bên dưới vào Google Antigravity. Phần
> trên là bối cảnh để anh hiểu vì sao prompt được viết như vậy — không cần dán.
>
> Prompt được viết **tự chứa** (self-contained): không giả định Antigravity đã
> đọc code của dự án này. Mọi định dạng file, công thức chấm điểm, ràng buộc dữ
> liệu đều nêu tường minh, trích đúng từ mã nguồn đang chạy.

---

## Vì sao prompt viết như vậy (bối cảnh, không cần dán)

1. **Định dạng file phải đúng tuyệt đối theo vị trí cột** — `ingest_csv86.py` đọc
   theo index cố định, không đoán theo tên cột. Sai thứ tự sẽ không báo lỗi mà
   **đảo ngược âm thầm** chiều mua-bán (xem `CAU_TRUC_DU_AN.md` mục 3) — nên
   prompt liệt kê thứ tự cột rất tường minh, nhiều lần.
2. **Trần điểm chỉ 60/100** — bộ test này (giống `detecting_cheat_by_nebula` thật) sẽ không có
   dữ liệu ĐKKD, nên 2 tín hiệu "liên kết ngầm" (25đ) và "thành viên rủi ro" (15đ)
   luôn bằng 0. Prompt nói rõ để Antigravity không cố nhúng các tín hiệu vô dụng
   này, và tính điểm kỳ vọng đúng thang 60, không phải 100.
3. **Quy mô lấy từ số đo thật** (`GIOI_HAN_HE_THONG.md`) — không phải đoán. Mật
   độ nền phải thấp (out-degree ~10) để chắc chắn không rơi vào vùng nguy hiểm
   (cụm dày như `detecting_cheat_by_nebula` thật chỉ an toàn tới ~150-180 DN cùng mật độ cao);
   các cụm gian lận thì cố ý dày (đó chính là tín hiệu cần phát hiện).
4. **MST bắt đầu bằng `99`** — để không trùng với `hanoi_98cty` (dùng đầu số
   thật 01/02/05/25/52...) hay `tax_graph` (dùng đầu số 09), tránh nhầm lẫn nếu
   sau này có ai gộp chung để đối chiếu.
5. **File đáp án phải kèm điểm kỳ vọng theo đúng công thức** — để tự
   Antigravity kiểm tra lại trước khi giao, tránh tình trạng "cài chu trình
   nhưng tính sai nên không đạt ngưỡng như ý định".

---

## NỘI DUNG PROMPT (dán từ đây)

```
Bạn là một kỹ sư dữ liệu. Nhiệm vụ: sinh một bộ dữ liệu THỬ NGHIỆM cho hệ thống
phát hiện gian lận "mua bán lòng vòng" (circular trading / carousel VAT fraud)
chạy trên NebulaGraph. Bộ dữ liệu phải đủ lớn, đủ dày, có cài sẵn nhiều chuỗi
gian lận với độ khó khác nhau, và phải kèm 1 file đáp án đối chiếu được.

===========================================================================
1. BỐI CẢNH HỆ THỐNG (đọc kỹ trước khi sinh dữ liệu)
===========================================================================

Pipeline gộp mọi hoá đơn giữa 1 cặp (bên bán, bên mua) trong CÙNG 1 THÁNG thành
1 "cạnh giao dịch". Sau đó dò mọi chu trình khép kín 3-6 cạnh (A→B→C→A, hoặc
dài hơn) trong đồ thị, và chấm điểm 0-100 mỗi chu trình theo 5 tín hiệu:

  (1) Cân bằng giá trị — 30 điểm
      ratio = min(giá trị các cạnh trong vòng) / max(giá trị các cạnh trong vòng)
      - ratio >= 0.8  → đủ 30 điểm
      - ratio <  0.8  → điểm = max(0, 30 * (ratio - 0.3) / 0.5)
      - ratio <= 0.3  → 0 điểm
      (Ý nghĩa nghiệp vụ: tiền đi hết 1 vòng gần như nguyên vẹn = dấu hiệu dòng
      tiền ảo, không phải giao dịch thương mại thật có lãi/lỗ khác nhau.)

  (2) Nén thời gian — 20 điểm
      span = số tháng từ giao dịch sớm nhất đến muộn nhất trong vòng
      - span <= 1 tháng → đủ 20 điểm
      - span >  1 tháng → điểm = max(0, 20 - span * 5)
      (Ý nghĩa: cả vòng diễn ra dồn dập trong thời gian ngắn = dấu hiệu dàn
      dựng, giao dịch thật thường trải dài tự nhiên hơn.)

  (3) Bất thường VAT — 10 điểm (tất cả hoặc không)
      Tính tỷ lệ (tiền thuế / tiền trước thuế) cho từng cạnh trong vòng, lấy
      trung vị. Nếu cạnh nào lệch trung vị > 0,03 (3 điểm phần trăm) → đủ 10
      điểm cho cả vòng. Nếu không → 0 điểm.

  (4) Liên kết ngầm — 25 điểm — LUÔN BẰNG 0 cho bộ dữ liệu này (không có dữ
      liệu người đại diện pháp luật / sở hữu vốn / địa chỉ trùng — không cần
      sinh các trường này).

  (5) Thành viên rủi ro — 15 điểm — LUÔN BẰNG 0 cho bộ dữ liệu này (không có
      dữ liệu ngày thành lập / trạng thái hoạt động doanh nghiệp).

  => TRẦN ĐIỂM của bộ dữ liệu này là 30 + 20 + 10 = 60/100 (không phải 100).
  Ngưỡng phân loại: >= 60 điểm = "cờ đỏ", 40-59,9 = "cần theo dõi", < 40 = bỏ qua.

===========================================================================
2. ĐỊNH DẠNG FILE — TUÂN THỦ TUYỆT ĐỐI, KHÔNG ĐƯỢC SAI THỨ TỰ CỘT
===========================================================================

Tạo đúng 2 file CSV trong thư mục `data_test_mua_ban_long_vong/` (đặt tên thư
mục CHÍNH XÁC như vậy):

--- company.csv ---
KHÔNG có dòng tiêu đề. Đúng 6 cột theo thứ tự:
  1. mst            — mã số thuế, chuỗi 10 chữ số, BẮT ĐẦU BẰNG "99"
                       (ví dụ: 9900000001, 9900000002, ...) — để không trùng
                       với MST của các bộ dữ liệu khác trong hệ thống
  2. ten_cong_ty    — tên doanh nghiệp tiếng Việt có dấu (nếu chứa dấu phẩy
                       phải bọc trong dấu ngoặc kép theo chuẩn CSV)
  3. linh_vuc       — ngành nghề (ví dụ: Thương mại, Xây dựng, Sản xuất, Vận
                       tải, Xuất nhập khẩu, Dịch vụ, Công nghệ...)
  4. dia_chi        — địa chỉ Việt Nam hợp lý (bọc ngoặc kép nếu có dấu phẩy)
  5. doanh_thu      — số nguyên VNĐ (KHÔNG dấu phân cách, không thập phân)
  6. nam_bao_cao    — định dạng dd/mm/yyyy, ví dụ "31/12/2023"

--- invoice.csv ---
KHÔNG có dòng tiêu đề. TỐI THIỂU 7 cột theo ĐÚNG thứ tự (có thể thêm cột phía
sau nếu muốn, sẽ bị bỏ qua an toàn, nhưng 7 cột đầu bắt buộc đúng vị trí):
  1. so_hoa_don      — số hoá đơn, không cần duy nhất toàn cục
  2. ngay_xuat       — ngày xuất, định dạng yyyy-mm-dd, TRONG khoảng
                       2023-01-01 đến 2023-12-31
  3. mst_nguon       — MST bên BÁN (chiều mũi tên đi RA) — phải khớp 1 MST
                       có trong company.csv
  4. mst_dich        — MST bên MUA (chiều mũi tên đi VÀO) — phải khớp 1 MST
                       có trong company.csv, và PHẢI KHÁC mst_nguon (một
                       doanh nghiệp không được tự bán cho chính mình — dòng
                       như vậy sẽ bị hệ thống tự động loại bỏ, đừng tạo ra vì
                       sẽ lãng phí)
  5. mo_ta           — mô tả ngắn hàng hoá/dịch vụ
  6. tien_chua_thue  — số nguyên VNĐ, tiền trước thuế
  7. thue_gtgt       — số nguyên VNĐ, tiền thuế GTGT (thường ~8% hoặc ~10%
                       của cột 6, TRỪ KHI đang cố tình tạo bất thường VAT
                       theo mục 4.4 bên dưới)

===========================================================================
3. QUY MÔ TỔNG THỂ
===========================================================================

- Số doanh nghiệp: 200 đến 300.
- Dữ liệu NỀN (không phải gian lận, đóng vai trò nhiễu thực tế): mỗi doanh
  nghiệp giao dịch ngẫu nhiên với khoảng 8-15 đối tác khác nhau trong suốt
  năm 2023, rải đều theo tháng — KHÔNG được tạo chu trình khép kín ở phần
  nền (chỉ là mạng lưới thương mại B2B thông thường, một chiều, không quay
  vòng). Đây là "nhiễu" để kiểm tra hệ thống không báo động nhầm tràn lan.
- Tổng số hoá đơn nền nên NHIỀU HƠN 5-10 lần so với số hoá đơn nằm trong các
  chuỗi gian lận — để việc phát hiện thực sự phải "tìm kim trong đống rơm",
  không phải vì gian lận chiếm phần lớn dữ liệu nên dễ thấy.

QUAN TRỌNG — KHÔNG được làm mật độ TOÀN CỤC quá cao. Không nối tất cả 200-300
doanh nghiệp với nhau như một mạng lưới gần-hoàn-chỉnh (đã đo thật: mật độ đó
với quy mô này sẽ khiến bước dò chu trình chạy hàng phút đến không kết thúc).
Chỉ các CỤM GIAN LẬN nêu ở mục 4 mới được phép dày đặc cục bộ.

===========================================================================
4. CÁC CHUỖI GIAN LẬN CẦN CÀI SẴN (đa dạng độ khó)
===========================================================================

Cài tổng cộng 15-20 chuỗi, chia theo 5 loại sau. Mỗi chuỗi là một nhóm nhỏ
doanh nghiệp (3 đến 6 công ty) CHỈ giao dịch qua lại với nhau tạo thành đúng 1
vòng khép kín (A bán cho B, B bán cho C, ..., cuối cùng bán ngược lại A).

4.1 "Rõ ràng, 3 chặng, điểm cao" — 5 chuỗi
    - 3 doanh nghiệp, vòng A→B→C→A
    - Tất cả giao dịch trong CÙNG 1 tháng
    - Giá trị từng cạnh chênh nhau dưới 5% (để ratio min/max >= 0.95)
    - Tỷ lệ VAT/tiền giống hệt nhau giữa các cạnh (ví dụ đều đúng 10%)
    - Điểm kỳ vọng: 30 (cân bằng) + 20 (nén thời gian) + 0 (VAT) = 50/60

4.2 "Rõ ràng, chặng dài (4-5 công ty)" — 4 chuỗi
    - Giống 4.1 nhưng vòng gồm 4-5 doanh nghiệp
    - Điểm kỳ vọng: tương tự ~50/60, dùng để kiểm tra hệ thống bắt được cả
      vòng dài, không chỉ vòng 3 chặng

4.3 "Biên/borderline" — 4 chuỗi
    - Giá trị từng cạnh chênh nhau nhiều hơn (ratio quanh 0,5-0,6 → khoảng
      15-18 điểm cân bằng thay vì 30)
    - Trải dài 2-3 tháng thay vì 1 tháng (nén thời gian ~5-10 điểm thay vì 20)
    - Điểm kỳ vọng: rơi vào khoảng 25-38/60 — dùng để kiểm tra ranh giới
      ngưỡng "cần theo dõi" (40-59,9) và "bỏ qua" (<40)

4.4 "VAT bất thường rõ" — 3 chuỗi
    - Cân bằng giá trị tốt (ratio >= 0.8) và nén trong 1 tháng (giống 4.1)
    - NHƯNG có ít nhất 1 cạnh trong vòng áp tỷ lệ VAT khác hẳn các cạnh còn
      lại (ví dụ 1 cạnh 0% hoặc 5% trong khi các cạnh khác đều 10%) để chắc
      chắn kích hoạt +10 điểm VAT
    - Điểm kỳ vọng: 30 + 20 + 10 = 60/60 (đúng ngưỡng cờ đỏ)

4.5 "Gần như không phải gian lận" (near-miss, để test KHÔNG báo động nhầm)
    — 3 chuỗi
    - Vẫn là 1 vòng khép kín về mặt CẤU TRÚC (A→B→C→A có thật)
    - NHƯNG giá trị từng cạnh chênh lệch rất lớn (ratio < 0,3 → 0 điểm cân
      bằng) VÀ trải dài trên 4 tháng (0 điểm nén thời gian)
    - Điểm kỳ vọng: 0 + 0 + (0 hoặc 10) = dưới 15/60 — PHẢI rơi vào mức "bỏ
      qua" dù cấu trúc vẫn là một vòng khép kín thật. Đây là chuỗi quan
      trọng nhất để kiểm tra hệ thống không báo động chỉ vì thấy cấu trúc
      vòng, mà phải xét cả tín hiệu tài chính.

===========================================================================
4.5. TỰ KIỂM TRA TRƯỚC KHI GIAO NỘP
===========================================================================

Viết một đoạn script ngắn tự tính lại điểm cho TỪNG chuỗi đã cài theo ĐÚNG 3
công thức ở mục 1, so khớp với điểm kỳ vọng đã ghi ở mục 4. Nếu lệch, chỉnh
lại số liệu (giá trị tiền, ngày tháng, tỷ lệ VAT) cho tới khi khớp. Đây là bước
bắt buộc — không giao nộp nếu chưa tự kiểm chứng khớp công thức.

===========================================================================
5. FILE ĐÁP ÁN — BẮT BUỘC
===========================================================================

Tạo thêm file `data_test_mua_ban_long_vong/DAP_AN.json` (cùng thư mục với 2
file CSV — hệ thống chỉ đọc đúng tên `company.csv`/`invoice.csv` nên file này
không bị nhầm lẫn) với cấu trúc:

{
  "tao_luc": "<thời điểm sinh dữ liệu>",
  "seed_ngau_nhien": <số nguyên dùng làm seed, để tái tạo lại y hệt được>,
  "tong_so_doanh_nghiep": <số>,
  "tong_so_hoa_don": <số>,
  "chuoi_gian_lan": [
    {
      "id": "F01",
      "loai": "ro_rang_3_chang | ro_rang_dai | bien | vat_bat_thuong | gan_nhu_khong_phai",
      "thanh_vien": ["9900000001", "9900000002", "9900000003"],
      "ghi_chu_thu_tu": "dung THU TU chieu ban: phan tu 0 ban cho phan tu 1, ... cuoi cung ban nguoc lai phan tu 0",
      "cac_canh": [
        {"ban": "9900000001", "mua": "9900000002", "ky": "2023-05",
         "tien_truoc_thue": 5000000000, "thue_gtgt": 500000000},
        ...
      ],
      "diem_ky_vong": {"can_bang": 30, "nen_thoi_gian": 20, "vat": 0, "tong": 50},
      "muc_ky_vong": "co_do | theo_doi | bo_qua"
    },
    ...
  ],
  "doanh_nghiep_sach": ["9900000123", "9900000124", ...]
}

`doanh_nghiep_sach` liệt kê MST của các doanh nghiệp KHÔNG tham gia bất kỳ
chuỗi gian lận nào (chỉ có trong dữ liệu nền) — dùng để kiểm tra hệ thống
không báo động sai (false positive) trên các doanh nghiệp này.

===========================================================================
6. RÀNG BUỘC KỸ THUẬT KHÁC (bắt buộc)
===========================================================================

- Cả 2 file CSV: encoding UTF-8, KHÔNG có dòng tiêu đề.
- Không dòng invoice.csv nào có mst_nguon == mst_dich.
- Mọi MST xuất hiện trong invoice.csv phải tồn tại trong company.csv.
- Số tiền là số nguyên thuần (không dấu phẩy/chấm phân cách, không ký hiệu
  tiền tệ, không phần thập phân).
- Toàn bộ ngày trong khoảng 2023-01-01 đến 2023-12-31.
- Tên thư mục chứa 2 file phải đúng là `data_test_mua_ban_long_vong`.

===========================================================================
7. BÀN GIAO
===========================================================================

Đưa ra:
  data_test_mua_ban_long_vong/company.csv
  data_test_mua_ban_long_vong/invoice.csv
  data_test_mua_ban_long_vong/DAP_AN.json
  (kèm script/công thức đã dùng để tự kiểm tra điểm ở bước 4.5, để có thể
   chạy lại và xác nhận độc lập)

Kèm theo một đoạn tóm tắt ngắn: tổng số doanh nghiệp, tổng số hoá đơn, số cạnh
sau khi gộp theo tháng (ước tính), danh sách 15-20 chuỗi đã cài kèm mức điểm
kỳ vọng của từng chuỗi (bảng ngắn, không cần lặp lại toàn bộ JSON).
```

---

## Sau khi có kết quả từ Antigravity — cách đưa vào hệ thống để test

```bash
# 1) Đặt đúng vị trí (thư mục con của raw/, ngang hàng với raw/hanoi_98cty/)
cp -r <đường_dẫn_antigravity_xuất_ra>/data_test_mua_ban_long_vong \
      /Users/hongphuc/Documents/01_congViec/Bigdata/detecting_cheat_by_nebula/raw/

# 2) Kiểm tra Go/web tự nhận diện bộ mới (không cần khai báo gì thêm)
curl -s localhost:8080/api/fraud/raw-datasets | python3 -m json.tool
# phải thấy "data_test_mua_ban_long_vong" xuất hiện trong danh sách

# 3) Chạy CLI trực tiếp để xem kết quả thô trước khi vào web
cd detecting_cheat_by_nebula/pipeline
DATASET=data_test_mua_ban_long_vong python3 ingest_csv86.py
python3 run_all.py --all --dataset data_test_mua_ban_long_vong \
  --hops 5 --method dfs --run-id test_long_vong_v1
```

Sau đó đối chiếu `detecting_cheat_by_nebula/output/runs/test_long_vong_v1/graph_risk_flags.jsonl`
(hoặc `top.json`) với `data_test_mua_ban_long_vong/DAP_AN.json`:

- Mỗi chuỗi trong `DAP_AN.json` có xuất hiện trong kết quả với đúng mức điểm
  kỳ vọng (chênh lệch nhỏ do làm tròn là bình thường) không?
- Các doanh nghiệp trong `doanh_nghiep_sach` có bị báo động nhầm (xuất hiện
  trong danh sách cờ đỏ/theo dõi) không — nếu có, đó là **false positive**
  cần xem lại thuật toán hoặc dữ liệu nền có vô tình tạo chu trình không mong
  muốn.
- Chuỗi loại "gần như không phải gian lận" (mục 4.5) có đúng bị xếp "bỏ qua"
  không — nếu bị báo cờ đỏ/theo dõi, đó là **false positive** nghiêm trọng
  hơn (hệ thống báo động chỉ vì thấy cấu trúc vòng, bỏ qua tín hiệu tài chính).

Trên giao diện web: bước 1 chọn bộ `data_test_mua_ban_long_vong`, bước 2 chọn
"Mua bán lòng vòng", bước 3 sẽ báo trần điểm 60/100 (đúng như thiết kế), bước
4 chạy, bước 5 xem bảng top chu trình và đối chiếu bằng mắt với `DAP_AN.json`.
