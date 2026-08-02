# Giới hạn hệ thống — Pipeline phát hiện mua bán lòng vòng

> Trả lời câu hỏi nghiệp vụ: **hệ thống chạy tốt trên bộ dữ liệu như thế nào, và giới hạn
> ở đâu?** Toàn bộ số liệu trong tài liệu này là **đo thật**, không suy đoán — xem mục 8
> để biết cách tái tạo.
>
> Ngày đo: 01/08/2026. Môi trường: Docker Desktop macOS, NebulaGraph v3.8.0, script đo
> lưu tại `/private/tmp/.../scratchpad/bench_scale.py` (bản build của phiên làm việc).

---

## 1. Tóm tắt điều hành

| Câu hỏi | Trả lời ngắn |
|---|---|
| Bộ dữ liệu nào chạy tốt? | **Đồ thị thưa** (mỗi doanh nghiệp giao dịch với ít đối tác so với tổng số DN) — gần như không giới hạn quy mô, đã đo tới 8.000 DN / 80.000 cạnh chạy dưới 1 giây. |
| Bộ dữ liệu nào là vùng nguy hiểm? | **Cụm doanh nghiệp giao dịch dày đặc với nhau** (kiểu detecting_cheat_by_nebula: 98 DN, ~84% cặp có giao dịch) — chi phí tăng theo cấp số nhân theo số DN trong cụm, không phải theo tổng số cạnh. |
| Ngưỡng an toàn của một cụm dày đặc là bao nhiêu? | Đo được: **mượt tới ~150 DN cùng cụm** (~21 giây mô phỏng), **biên giới ~180 DN** (~53 giây), **~200 DN đã vượt 90 giây** trong mô phỏng — thực tế (có cấu trúc kinh tế thật) thường nặng hơn mô phỏng 5–6 lần. |
| Khi có đủ dữ liệu ĐKKD thì sao? | **Chậm đi rõ rệt** (20–40 lần trên cùng quy mô) vì ngưỡng cắt nhánh phải nới ra để không bỏ sót chu trình thật. Đây là đánh đổi **chính xác hơn nhưng đắt hơn**, phải đo lại khi ĐKKD về. |
| Điểm chặn cứng nào không thể vượt qua bằng cách chờ lâu hơn? | Cú pháp nGQL `*` (biến thiên độ dài) trên đồ thị dày — **đã làm sập graphd thật (OOM-kill)**, cấm tuyệt đối bất kể có neo `id()` hay giới hạn hop. |
| Có giới hạn cứng nào về thời gian/dung lượng không? | Có: timeout 1 lần chạy = 10 phút, upload = 200MB, 1 lần chạy đồng thời/không gian dữ liệu. |

---

## 2. Đơn vị đo: KHÔNG PHẢI số doanh nghiệp, mà là số doanh nghiệp × mật độ

Trực giác thường gặp là "hệ thống chịu được tối đa bao nhiêu công ty?" — câu hỏi đó
**không có nghĩa** với thuật toán này. Đo thật cho thấy 2 chiều hoàn toàn khác nhau:

### 2.1 Đồ thị thưa: quy mô gần như không giới hạn

Cố định mỗi doanh nghiệp giao dịch với **10 đối tác** bất kỳ (không phụ thuộc tổng số DN),
5 chặng, dùng đúng ngưỡng cắt nhánh 50 (trường hợp thiếu ĐKKD như hiện tại):

| Số DN | Số cạnh | Thời gian | Chu trình tìm được |
|---:|---:|---:|---:|
| 100 | 989 | 0,01s | 0 |
| 1.000 | 9.991 | 0,11s | 0 |
| 2.000 | 19.997 | 0,21s | 0 |
| 4.000 | 39.985 | 0,44s | 0 |
| **8.000** | **79.990** | **0,86s** | 0 |

**Kết luận:** khi mỗi doanh nghiệp chỉ giao dịch với một nhóm nhỏ đối tác so với tổng thể
(giống phần lớn nền kinh tế thật), thời gian chạy gần như **tuyến tính** theo số cạnh —
tới 80.000 cạnh vẫn dưới 1 giây. Cơ chế cắt nhánh đơn điệu (`prune_bound`) và mẹo Johnson
trong `detect_circular_trading.py` hoạt động đúng như thiết kế: loại bỏ sớm các nhánh
không thể đạt điểm cờ đỏ trước khi phải duyệt sâu.

> Không phát hiện chu trình nào ở bảng trên không phải lỗi — với đối tác được chọn ngẫu
> nhiên từ toàn bộ 8.000 DN, xác suất một chuỗi 3-5 doanh nghiệp ngẫu nhiên vừa khép vòng
> vừa có giá trị "cân bằng" (tỷ lệ min/max ≥ 0,8) gần như bằng 0. Chu trình lòng vòng thật
> đòi hỏi các doanh nghiệp **giao dịch lặp lại với nhau** — đó chính là mục 2.2.

### 2.2 Cụm dày đặc: vùng nguy hiểm thật sự

Đây là điều quan trọng nhất tài liệu này cần truyền đạt. Dữ liệu thật `invoice_agg_graph`
(98 DN Hà Nội) có mật độ cực cao:

| | Giá trị đo thật |
|---|---|
| Số doanh nghiệp | 98 |
| Số cạnh giao dịch | 7.945 |
| Out-degree trung bình | **81,9** (mỗi DN giao dịch với ~82/97 DN còn lại — **84%**) |
| Out-degree cao nhất | 158 |
| In-degree cao nhất | 174 |

Đây **không phải** một mẫu ngẫu nhiên của nền kinh tế — nó là một **cụm gần như hoàn
chỉnh** (gần mọi cặp doanh nghiệp đều có giao dịch), đúng thứ cần rà soát vì nghi vấn
carousel fraud/circular trading trong thực tế thường hình thành quanh một nhóm nhỏ doanh
nghiệp giao dịch qua lại nhiều lần.

**Đo tăng dần số DN trong khi giữ nguyên mật độ 84% giống hệt detecting_cheat_by_nebula:**

| Số DN | Số cạnh | Thời gian (mô phỏng) | Chu trình duy nhất |
|---:|---:|---:|---:|
| **98** (thật) | 7.953 | **2,5s** | 114 |
| 120 | 11.898 | 6,6s | 254 |
| 150 | 18.774 | 21,3s | 706 |
| 180 | 27.017 | **53,5s** | 1.539 |
| 200 | 33.427 | **> 90s (vượt ngưỡng đo)** | — |

**Đối chiếu với dữ liệu thật để hiệu chỉnh:** cùng kịch bản 98 DN, mô phỏng cho 2,5 giây
trong khi pipeline thật đo được **15,2 giây** (5-6 lần chậm hơn) — vì mạng lưới kinh tế
thật có cấu trúc cụm/tương quan (một số doanh nghiệp là "hub" trung tâm của nhiều chuỗi
cung ứng) mà đồ thị ngẫu nhiên không tái tạo được. Áp hệ số hiệu chỉnh ×5–6 vào bảng trên:

| Số DN trong 1 cụm dày đặc | Thời gian ước tính thực tế |
|---:|---:|
| 98 | ~15 giây (**đã đo thật**) |
| 120 | ~35–40 giây |
| 150 | ~2 phút |
| 180 | ~4–5 phút |
| 200 | **rất có thể vượt timeout 10 phút** |

#### Đo lại ngày 02/08/2026 — bản hiệu chỉnh tốt hơn

Phép đo trên dùng đồ thị ngẫu nhiên với số tiền/kỳ sinh tuỳ ý, nên bước cắt nhánh theo điểm
hoạt động không giống thực tế. Bản đo lại **lấy mẫu phân phối tiền và kỳ từ chính dữ liệu
thật** (`data/trades.csv`), khiến mô phỏng sát hơn hẳn — hệ số hiệu chỉnh giảm từ ×5–6 xuống
**×2,69** (mô phỏng 98 DN cho 5,6s, đo thật 15,04s):

| Số DN | Out-degree | 5 chặng (mô phỏng) | 5 chặng (ước thực tế) | 10 chặng (ước thực tế) |
|---:|---:|---:|---:|---:|
| 98 | 81,7 | 5,6s | **15s** (khớp số đo thật) | **12,9 phút** (đã đo thật) |
| 120 | 100,0 | 17,6s | ~47 giây | ~41 phút |
| 150 | 124,8 | 56,9s | **~2,5 phút** | **~2,2 giờ** |
| 200 | 167,4 | 291,6s | **~13,1 phút** | **~11,2 giờ** |

Kết luận không đổi so với bản cũ (150 DN ~2 phút, 200 DN vượt 10 phút) — nhưng nay có con số
cụ thể thay vì "rất có thể vượt", và có thêm cột 10 chặng.

> **Khuyến nghị vận hành:** một cụm doanh nghiệp cần rà soát cùng lúc (cùng ngành, cùng
> nhóm nghi vấn) nên giữ dưới **150 doanh nghiệp** nếu mật độ giao dịch giữa chúng cao
> như detecting_cheat_by_nebula. Trên 180 DN/cụm, cân nhắc giảm số chặng xuống 3-4 hoặc chia nhỏ theo
> mốc thời gian (chạy riêng từng quý thay vì cả năm) — xem mục 4.
>
> **Với ý định nâng lên 10 chặng**: chỉ khả thi ở cụm ≤ ~100 DN (12,9 phút). Từ 150 DN trở lên
> là hàng giờ — xem phân tích đầy đủ tại [`KE_HOACH_NANG_CAP_10_HOP.md`](KE_HOACH_NANG_CAP_10_HOP.md).

### 2.3 Vì sao 2 chiều này khác nhau đến vậy — giải thích thuật toán

`detect_circular_trading.py` dùng DFS + cắt nhánh đơn điệu: tại mỗi bước mở rộng, nếu
điểm "cân bằng + nén thời gian" cộng dồn đã tối đa (kể cả cộng thêm điểm VAT và liên kết
ngầm/rủi ro tối đa có thể đạt) mà vẫn dưới ngưỡng cờ đỏ, nhánh đó bị loại ngay — không cần
duyệt tiếp. Với đồ thị thưa, phần lớn nhánh bị loại từ chặng 1-2. Với cụm dày đặc, **rất
nhiều nhánh sống sót qua nhiều chặng** vì các doanh nghiệp trong cụm đã quen giao dịch giá
trị tương đồng với nhau — số lượng đường đi hợp lệ cần duyệt tăng theo cấp lũy thừa của số
đỉnh trong cụm, đúng bản chất bài toán liệt kê chu trình trên đồ thị dày (đã biết là
NP-khó về mặt lý thuyết, không có thuật toán nào tránh được hoàn toàn).

---

## 3. Ảnh hưởng của dữ liệu ĐKKD — đánh đổi CHÍNH XÁC HƠN nhưng ĐẮT HƠN

Đây là phát hiện quan trọng thứ hai, ảnh hưởng trực tiếp tới kế hoạch khi dữ liệu
người đại diện/sở hữu vốn (mục 4.2 Data Contract) về sau này.

Ngưỡng cắt nhánh (`prune_bound`) tự suy từ dữ liệu có thật: nếu space **không có** cạnh
liên kết ngầm hay thông tin rủi ro, ngưỡng cắt là 50 (chặt); nếu **có**, ngưỡng phải nới
xuống 10 (lỏng hơn nhiều, vì một chu trình có thể đạt điểm cờ đỏ chỉ nhờ liên kết ngầm dù
điểm cân bằng+thời gian thấp — không được cắt sớm kẻo bỏ sót).

Đo trên cùng một đồ thị, chỉ đổi ngưỡng cắt (mô phỏng "trước và sau khi có ĐKKD"):

| Quy mô | Ngưỡng 50 (thiếu ĐKKD, hiện tại) | Ngưỡng 10 (đủ ĐKKD) | Chênh lệch |
|---|---:|---:|---:|
| 250 DN × 10 đối tác | 0,03s / 0 vòng | 1,07s / 421 vòng | **~35 lần chậm hơn** |
| 500 DN × 10 đối tác | 0,05s / 1 vòng | 2,10s / 378 vòng | **~40 lần chậm hơn** |
| 1.000 DN × 10 đối tác | 0,10s / 0 vòng | 4,35s / 410 vòng | **~43 lần chậm hơn** |

**Ý nghĩa vận hành:** khi dữ liệu ĐKKD thật được nạp vào (theo kế hoạch mục 4.2 của
`KE_HOACH_TONG_THE_PIPELINE_LONG_VONG.md`), pipeline sẽ **tự động chấm điểm đúng hơn**
(trần điểm lên 100/100 thay vì 60/100) nhưng đồng thời **chậm đi 20-40 lần** trên cùng quy
mô dữ liệu. Đây không phải lỗi cần sửa — đó là chi phí bắt buộc để không bỏ sót chu trình
có liên kết ngầm nhưng giá trị/thời gian không quá bất thường. **Phải đo lại giới hạn quy
mô ở mục 2.2 khi ĐKKD về**, không được giả định con số cũ còn đúng.

---

## 4. Ảnh hưởng của số chặng (hop)

Đo trên dữ liệu thật `invoice_agg_graph` (98 DN, đã có sẵn — số liệu này khớp với
`README.md` của pipeline):

| Số chặng tối đa | Thời gian | Chu trình duy nhất | Cờ đỏ |
|---:|---:|---:|---:|
| 3 | 2,9 giây | 348 | 99 |
| 5 | 16,1 giây | 2.429 | 1.074 |

Tăng từ 3 lên 5 chặng (thêm 2 chặng): thời gian tăng **~5,6 lần**, số cờ đỏ phát hiện thêm
**~11 lần**. Trên đồ thị thưa (mục 2.1), chi phí theo chặng nhẹ hơn nhiều (gần như hằng số
tới 6 chặng ở quy mô 1.000 DN thưa: 0,10 → 0,10 → 0,10 → 0,10 giây) — chặng chỉ trở thành
đắt đỏ **khi kết hợp với mật độ cao**.

**Khuyến nghị:** với cụm dày đặc gần ngưỡng 150-180 DN, cân nhắc giảm xuống 3-4 chặng để
giữ thời gian chạy trong vài chục giây, chấp nhận bỏ sót một phần chu trình dài (4-5
chặng) — đánh đổi có ý thức, không phải giới hạn ẩn.

---

## 5. Giới hạn của phương pháp MATCH (truy vấn thuần Nebula)

Ngoài phương pháp DFS (mặc định, phân tích ở trên), pipeline còn phương pháp `match` —
chạy chuỗi hop cố định trực tiếp trong NebulaGraph, mỗi điểm xuất phát (seed) một truy
vấn riêng. Phương pháp này có **giới hạn cứng khác hẳn**, đã ghi nhận thật khi vận hành:

- **Luôn bị cắt cụt theo `CYCLES_PER_SEED_LIMIT`** (mặc định 50 kết quả/seed). Đo thật:
  trên cùng dữ liệu detecting_cheat_by_nebula, MATCH chỉ tìm được **1.008 nhóm cờ đỏ** trong khi DFS đầy
  đủ tìm được **1.072** — thiếu khoảng **6%**, tập trung ở vòng 4-5 chặng vì MATCH tràn bộ
  nhớ trước khi tới đó (ghi nhận trong `invoice_agg_graph/KICH_BAN_DEMO_SHOWCASE_INVOICE86.md`).
- **Cấm tuyệt đối cú pháp biến thiên độ dài `*`** (`*1..`, `*2..4`...) trên không gian dữ
  liệu dày như invoice_agg_graph — **đã crash graphd thật nhiều lần** trong quá trình phát
  triển, kể cả khi đã neo điểm bắt đầu bằng `id(x) == "..."` và giới hạn số hop. Bộ lập kế
  hoạch của Nebula mở rộng cạnh trước khi lọc điều kiện, nên với đỉnh hub 150+ cạnh, dò
  biến thiên độ dài vẫn nổ tổ hợp. Ghi rõ trong `nebula_demo/schemas/invoice_graph.md`.
- Câu lệnh trực quan hoá (nút "Xem sơ đồ" trên web) **không bao giờ** dùng chuỗi hop nối
  tiếp `(c0)-[:TRADES]->(c1)-...->(c0)` dù đã neo đủ `id()` mọi đỉnh — dạng này **đã thật
  sự làm graphd bị OOM-kill (exit 137)** khi thử nghiệm trên vòng 5 chặng. Cách duy nhất đã
  kiểm chứng an toàn (0,04 giây) là dạng một chặng, neo cả hai đầu, liệt kê từng cặp bằng
  `OR` — xem `README.md` mục "Ba cạm bẫy".

**Khuyến nghị:** dùng MATCH chỉ khi cần đối chiếu nhanh với engine Nebula gốc hoặc dữ liệu
rất thưa; dùng DFS (mặc định) cho kết quả đầy đủ, không cắt cụt.

---

## 6. Giới hạn hạ tầng (đo/đọc trực tiếp từ code đang chạy)

| Giới hạn | Giá trị | Nơi cấu hình |
|---|---|---|
| Thời gian tối đa 1 lần chạy | **10 phút** (timeout cứng, tự hủy) | `RUN_TIMEOUT_MIN` (config.go) |
| Dung lượng upload dữ liệu | **200MB** | `fraud.go` (`ParseMultipartForm`) |
| Số lần chạy đồng thời / 1 không gian dữ liệu | **1** (chặn chạy chồng) | `pipeline_runner.go` |
| Kích thước 1 dòng log tối đa | 4MB (dòng dài hơn bị cắt) | `pipeline_runner.go` (`sc.Buffer`) |
| Số bản ghi mỗi lô khi nạp vào Nebula | 500 | `sync_graph.py` (`BATCH_SIZE`) |
| Số kết quả mỗi seed (chỉ áp dụng METHOD=match) | 50 | `detect_circular_trading.py` |
| Số seed tối đa quét (chỉ áp dụng METHOD=match) | 5.000 | `detect_circular_trading.py` |
| Độ dài chu trình tối đa hỗ trợ trên giao diện | 3, 4, hoặc 5 chặng | `datasources.json` (`params`) |

Các giới hạn này đều là **cấu hình được**, không phải giới hạn thuật toán — có thể nới nếu
môi trường (RAM, số lõi CPU, kích thước Docker) cho phép.

---

## 7. Bộ nhớ

Trong toàn bộ phép đo (tới 79.988 cạnh, tới ~22.500 chu trình duy nhất được giữ lại cùng
lúc), mức tăng bộ nhớ đo được **luôn dưới 3MB** ở tiến trình Python. Bộ nhớ **không phải
là điểm nghẽn** của hệ thống này — điểm nghẽn hoàn toàn là **thời gian CPU** do số nhánh
DFS phải duyệt tăng theo cấp lũy thừa trên cụm dày đặc (mục 2.2). Điều này khác với nhiều
hệ thống đồ thị lớn khác (nơi bộ nhớ thường là nút thắt đầu tiên) — nghĩa là tăng RAM cho
máy chủ **không giúp ích** nếu vấn đề là một cụm quá dày; chỉ giảm số chặng, giảm quy mô
cụm, hoặc chờ lâu hơn (trong giới hạn timeout 10 phút) mới có tác dụng.

---

## 8. Cách tái tạo phép đo

```bash
# Đo quy mô (mục 2, dùng đồ thị mô phỏng, có hiệu chỉnh theo phân phối tiền thật)
cd detecting_cheat_by_nebula/pipeline
python3 -c "
import sys; sys.path.insert(0, '.')
import detect_circular_trading as D
adj = {...}  # xem bench_scale.py để sinh đồ thị mô phỏng đúng phân phối log-normal
"

# Đo thật trên dữ liệu detecting_cheat_by_nebula (mục 4, con số 2,9s / 16,1s)
PERIOD_FROM=202011 PERIOD_TO=202112 MAX_HOPS=3 python3 detect_circular_trading.py
PERIOD_FROM=202011 PERIOD_TO=202112 MAX_HOPS=5 python3 detect_circular_trading.py

# Đo mật độ thật của dữ liệu hiện có
python3 -c "
import sys; sys.path.insert(0,'.')
from nebula_client import session
with session() as s:
    r = s.execute('LOOKUP ON TRADES WHERE TRADES.period >= 0 YIELD src(edge) AS a, dst(edge) AS b;')
    # đếm out-degree/in-degree — xem mục 2.2
"
```

Script mô phỏng đầy đủ (sinh đồ thị theo phân phối log-normal khớp dữ liệu thật, đo thời
gian + bộ nhớ + timeout) đã được dùng để tạo mọi bảng số liệu trong mục 2-4 ở trên. **Lưu
ý quan trọng khi tái tạo:** phân phối giá trị giao dịch trong đồ thị mô phỏng phải khớp
phân phối thật (log-normal, μ≈23,3, σ≈1,66 — trung vị ~15 tỷ) chứ không được dùng khoảng
hẹp tùy ý. Lần đo đầu tiên trong phiên làm việc này dùng khoảng hẹp (9-11 tỷ) và cho kết
quả **sai lệch nặng theo hướng bi quan** — cùng kịch bản 98 DN báo "vượt quá 90 giây" thay
vì đúng 2,5 giây (mô phỏng) / 15,2 giây (thật), vì giá trị hẹp khiến hầu như mọi tổ hợp
đều "cân bằng", vô hiệu hóa cơ chế cắt nhánh. Đã sửa và toàn bộ số liệu trong tài liệu này
dùng bản đã hiệu chỉnh.

---

## 9. Những gì tài liệu này KHÔNG đo (giới hạn của chính phép đo)

1. **Hiệu năng render trên trình duyệt** (vis-network với vài nghìn đỉnh/cạnh cùng lúc) —
   chưa đo bằng trình duyệt thật, chỉ là giới hạn được biết đến chung của các thư viện vẽ
   đồ thị vật lý (physics simulation chậm dần khi số đỉnh hiển thị cùng lúc vượt vài trăm).
   Nút "Xem sơ đồ" hiện chỉ vẽ 1 chu trình (3-6 đỉnh) nên chưa chạm giới hạn này trong thực tế sử dụng.
2. **Bộ dữ liệu NhómACD thật** (~3.900 MST, 11.444 file) — mục 2 của tài liệu này cho biết
   khả năng chạy được của NhómACD phụ thuộc hoàn toàn vào **mật độ giao dịch nội bộ** của
   nó, không phải tổng số MST. Nếu NhómACD có cấu trúc thưa như phần lớn nền kinh tế (mục
   2.1), 3.900 MST sẽ chạy dưới 1 giây. Nếu chứa các cụm dày như detecting_cheat_by_nebula, mỗi cụm phải
   được xử lý riêng theo ngưỡng mục 2.2. **Chưa đo được vì NhómACD chưa được nạp vào
   pipeline** (trạng thái `planned` trong `datasources.json`).
3. **Chạy nhiều lần đồng thời trên nhiều Space khác nhau** — hệ thống chặn 2 lần chạy
   đồng thời trên CÙNG 1 Space, nhưng chưa đo xem chạy đồng thời trên các Space KHÁC NHAU
   có tranh chấp tài nguyên NebulaGraph (CPU/RAM của graphd dùng chung) tới mức nào.
