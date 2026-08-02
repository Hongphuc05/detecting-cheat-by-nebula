# Kế hoạch nâng cấp: dò chu trình lên 10 chặng

> **Câu hỏi cần trả lời**: nâng giới hạn dò chu trình từ 5 lên 10 chặng có khả thi không,
> xét cả **quy mô/hiệu năng** lẫn **độ chính xác**?
>
> Tài liệu này dựa trên **số đo thật** chạy trên chính thuật toán của hệ thống
> (`enumerate_cycles_dfs`), không phải ước lượng lý thuyết. Ngày đo: 02/08/2026.

---

## 1. Kết luận nhanh

**Khả thi có điều kiện — nhưng nếu chỉ nâng số chặng mà không sửa gì khác thì sẽ HỎNG.**

| Mặt | Kết luận | Lý do ngắn |
|---|---|---|
| **Quy mô** | ⚠️ Khả thi trên đồ thị **thưa**, KHÔNG khả thi trên cụm **dày** | Chi phí nhân **×2,1–2,7 mỗi chặng**. Mật độ quyết định, không phải số doanh nghiệp |
| **Độ chính xác** | ❌ Sẽ **giảm** nếu giữ nguyên cách chấm điểm | Số chu trình cũng tăng ×2,1–2,7 mỗi chặng → ngập báo động, phần lớn là trùng hợp ngẫu nhiên |
| **Giá trị nghiệp vụ** | ✅ Có thật, đáng làm | 39% chu trình rửa tiền thật (theo nhãn gốc IBM) dài ≥6 chặng — hiện đang **mù hoàn toàn** |

**Khuyến nghị**: làm, nhưng **không phải bằng cách đổi `[3,4,5]` thành `[3..10]`**. Phải kèm 3 thay
đổi bắt buộc: (1) chấm điểm theo độ dài chu trình, (2) giới hạn thích ứng theo mật độ, (3) ngân sách
thời gian cứng. Chi tiết ở mục 5.

---

## 2. Bằng chứng đo thật

### 2.1 Đường cong tăng trưởng theo số chặng

Chạy `enumerate_cycles_dfs` (hàm thật của hệ thống, không mô phỏng) trên bộ `hanoi_98cty`:
**97 đỉnh · 7.945 cạnh · out-degree trung bình 81,9** (mỗi DN giao dịch với ~84% số DN còn lại).

| Số chặng | Thời gian | Số lần xuất hiện | Chu trình duy nhất | Hệ số tăng |
|---:|---:|---:|---:|---:|
| 3 | 2,30s | 366 | 346 | — |
| 4 | 6,11s | 1.131 | 1.072 | ×2,7 |
| **5** (hiện tại) | **15,04s** | **2.581** | **2.418** | ×2,5 |
| 6 | 35,60s | 5.411 | 5.049 | ×2,4 |
| 7 | 80,17s | 10.604 | 9.820 | ×2,3 |
| 8 | **177,03s** (~3 phút) | 20.812 | **19.089** | ×2,2 |
| 9 | **374,85s** (~6,3 phút) | 39.865 | **36.218** | ×2,1 |
| **10** | **773,99s (12,9 phút)** | **75.349** | **67.814** | ×2,1 |

**Toàn bộ bảng là số đo thật, không có ngoại suy.**

**Điểm mấu chốt**: hệ số tăng rất ổn định (×2,1–2,7), nghĩa là chi phí **tăng theo hàm mũ** theo số
chặng. Đi từ 5 → 10 chặng:

- **Thời gian: ×51,5** (15,04s → 773,99s)
- **Số chu trình phải rà soát: ×28** (2.418 → 67.814)

…và đây mới chỉ là **98 doanh nghiệp**.

### 2.2 Mật độ mới là yếu tố quyết định, KHÔNG phải số doanh nghiệp

Đối chiếu 2 bộ dữ liệu ở **cùng 5 chặng**:

| Bộ dữ liệu | Số DN | Out-degree TB | Thời gian dò (5 chặng) |
|---|---:|---:|---:|
| `hanoi_98cty` (cụm dày, dữ liệu thật) | 98 | **81,9** | **15,0s** |
| `ibm_aml_hi_small` (thưa) | 515.080 | **1,5** | **3,6s** |

**98 doanh nghiệp dày đặc tốn gấp ~4 lần 515.080 doanh nghiệp thưa.** Đây là điều phản trực giác
nhưng đúng bản chất bài toán liệt kê chu trình: chi phí bám theo **số đường đi hợp lệ**, mà số đường
đi bùng nổ theo mật độ chứ không theo số đỉnh.

Hệ quả trực tiếp: **không thể trả lời "10 chặng có khả thi không" một cách chung chung** — câu trả lời
khác nhau hoàn toàn tùy bộ dữ liệu. Mục tiếp theo lượng hoá điều này.

### 2.2.1 Chi phí theo kích thước cụm dày — đo thật

Câu hỏi hay gặp: *"IBM có 515.000 doanh nghiệp mà chạy chưa tới 1 phút, sao lại bảo 150-200 doanh
nghiệp mất vài phút?"* — vì **chi phí không tỉ lệ với số doanh nghiệp, mà tỉ lệ với số ĐƯỜNG ĐI phải
duyệt** ≈ `số_đỉnh × (out-degree)^số_chặng`:

| | Phép tính | Số đường đi độ dài 5 |
|---|---|---:|
| IBM AML (515K DN, out-degree 1,53) | 422.726 × 1,53⁵ | **3.576.307** |
| `hanoi_98cty` (98 DN, out-degree 81,9) | 97 × 81,9⁵ | **357.587.698.984** |

Bộ 98 doanh nghiệp phải duyệt **nhiều hơn 100.000 lần** bộ 515.000 doanh nghiệp. Cách hình dung:
không phải "phòng có bao nhiêu người", mà là "có bao nhiêu chuỗi bắt tay dài 5 bước trong phòng".

**Đo thật trên cụm dày tổng hợp** (sinh ở đúng mật độ 84% của `hanoi_98cty`, lấy mẫu phân phối tiền/kỳ
từ dữ liệu thật, chạy chính `enumerate_cycles_dfs`):

| Số DN | Out-degree | 5 chặng (mô phỏng) | 5 chặng (ước thực tế) | 10 chặng (ước thực tế) |
|---:|---:|---:|---:|---:|
| 98 | 81,7 | 5,6s | **15s** ✓ | **12,9 phút** ✓ |
| 120 | 100,0 | 17,6s | ~47s | ~41 phút |
| 150 | 124,8 | 56,9s | **~2,5 phút** | **~2,2 giờ** |
| 200 | 167,4 | 291,6s | **~13,1 phút** | **~11,2 giờ** |

*Hệ số hiệu chỉnh mô phỏng → thực tế là **×2,69**, suy ra từ chính bộ `hanoi_98cty`: mô phỏng 98 DN cho
5,6s trong khi đo thật cho 15,04s. Hai ô đánh ✓ là số đo trực tiếp, dùng để kiểm chứng hệ số — khớp.
Mạng lưới kinh tế thật có cấu trúc hub mà đồ thị ngẫu nhiên không tái tạo được, nên mô phỏng luôn nhẹ hơn.*

> **Lưu ý về ước tính 10 chặng ở 150/200 DN**: dùng hệ số ×51,5 đo được trên cụm 98 DN. Với cụm dày hơn
> (out-degree 125-167), hệ số tăng mỗi chặng sẽ **cao hơn** — nên các con số 2,2 giờ / 11,2 giờ là
> **cận dưới**, thực tế còn tệ hơn.

**Kết luận theo loại đồ thị:**

| Loại đồ thị | 10 chặng khả thi? |
|---|---|
| Thưa (out-degree < 5), kể cả hàng trăm nghìn DN | ✅ Rất khả thi, chi phí không đáng kể |
| Cụm dày ~98 DN (out-degree ~82) | ⚠️ Được nhưng 12,9 phút — sát trần chịu đựng |
| Cụm dày ~150 DN (out-degree ~125) | ❌ ~2,2 giờ — vượt xa mọi timeout hợp lý |
| Cụm dày ~200 DN (out-degree ~167) | ❌ ~11,2 giờ — bất khả thi hoàn toàn. Ngay cả **5 chặng** đã mất ~13 phút |

### 2.3 Lý do nghiệp vụ ủng hộ việc nâng chặng

Phân bố độ dài chu trình rửa tiền **thật** (54 nhóm `CYCLE` do IBM gắn nhãn trong `HI-Small`):

| Độ dài | Số nhóm | Tỉ lệ | Hệ thống hiện tại |
|---:|---:|---:|---|
| 2 chặng | 14 | 25,9% | ❌ Bị loại bởi `min_len = 3` |
| 3–5 chặng | 19 | 35,2% | ✅ Bắt được |
| 6–12 chặng | 21 | **38,9%** | ❌ **Mù hoàn toàn** |

Gần **39% chu trình rửa tiền thật dài từ 6 chặng trở lên** — hệ thống hiện không thể thấy. Điều này
khớp với lý thuyết AML: giai đoạn **layering** (phân tầng) của rửa tiền *có chủ đích* kéo dài chuỗi
trung gian để cắt đứt dấu vết. Chuỗi càng dài càng khó truy — đó chính là mục đích của kẻ gian.

> **Phát hiện phụ đáng chú ý**: 26% chu trình thật chỉ có **2 chặng** (A→B→A) và đang bị loại cứng bởi
> `min_len = 3`. Đây là khoảng trống **rẻ hơn nhiều** để lấp so với 6-10 chặng (chi phí gần bằng 0,
> vì chu trình 2 chặng ít hơn hẳn), mà lại phủ được 26% thay vì 39%. Xem Giai đoạn 0 ở mục 5.

---

## 3. Vì sao "chỉ nâng số chặng" sẽ làm GIẢM độ chính xác

Đây là rủi ro lớn nhất, và nó **không hiển nhiên** nếu chỉ nhìn thời gian chạy.

### 3.1 Số báo động tăng cùng tốc độ với chi phí

Từ 98 doanh nghiệp, số chu trình duy nhất: **2.418** (5 chặng) → **19.089** (8 chặng) → **67.814**
(10 chặng — tất cả đều là số đo thật). Ở lần chạy thật gần nhất, riêng 5 chặng đã cho **1.074 chu trình cờ đỏ** —
đã vượt xa năng lực rà soát của con người. Ở 10 chặng, con số này sẽ lên hàng chục nghìn.

**Nhiều báo động hơn ≠ phát hiện được nhiều gian lận hơn.** Trong một cụm mà 84% cặp doanh nghiệp có
giao dịch với nhau, các vòng khép kín dài **xuất hiện ngẫu nhiên với số lượng khổng lồ** — chúng là
đặc tính cấu trúc của đồ thị dày, không phải bằng chứng gian lận.

### 3.2 Lỗi thiết kế cốt lõi: điểm số không xét độ dài

Công thức chấm điểm hiện tại (`score_components`) **không quan tâm chu trình dài bao nhiêu**:

```
chu trình 3 chặng, cân bằng 30 + thời gian 20  =  50 điểm
chu trình 10 chặng, cân bằng 30 + thời gian 20 =  50 điểm   ← điểm y hệt
```

Nhưng **xác suất tiên nghiệm** của hai trường hợp này chênh nhau hàng nghìn lần: trong đồ thị dày, số
đường đi 10 chặng nhiều hơn số đường đi 3 chặng theo cấp lũy thừa, nên chu trình 10 chặng "đẹp" ngẫu
nhiên dễ gặp hơn rất nhiều. Chấm điểm ngang nhau nghĩa là:

> **Càng nâng số chặng, bảng xếp hạng "top rủi ro" càng bị chu trình dài ngẫu nhiên chiếm chỗ, đẩy
> chu trình ngắn thật sự đáng ngờ xuống dưới.**

Đây là lý do **bắt buộc** phải sửa cách chấm điểm cùng lúc với nâng số chặng, không được làm riêng lẻ.

### 3.3 Cắt nhánh hiện tại không cứu được

Ngưỡng cắt nhánh hiện là 50 (= cân bằng 30 + thời gian 20, khi không có dữ liệu ĐKKD). Nó **không mất
mát** (không bỏ sót chu trình đạt ngưỡng cờ đỏ) nhưng cũng **không siết chặt theo độ dài** — nên số
nhánh sống sót vẫn nhân lên đều đặn ×2,1–2,7 mỗi chặng, đúng như số đo cho thấy.

---

## 4. Nhược điểm & rủi ro (drawbacks)

| # | Nhược điểm | Mức độ | Ghi chú |
|---|---|---|---|
| 1 | **Chi phí hàm mũ trên cụm dày** — ×51,5 khi đi từ 5→10 chặng | 🔴 Nghiêm trọng | Đo thật: cụm 150 DN ~2,2 giờ · cụm 200 DN ~11,2 giờ (mục 2.2.1) — vượt xa mọi timeout hợp lý |
| 2 | **Ngập báo động (alert flood)** — 67.814 chu trình từ 98 DN | 🔴 Nghiêm trọng | Không thể rà soát thủ công; làm giảm giá trị thực tế của hệ thống |
| 3 | **Xếp hạng bị nhiễu** — chu trình dài ngẫu nhiên chiếm top | 🔴 Nghiêm trọng | Xem mục 3.2. Đây là mất mát *chất lượng*, khó thấy hơn mất mát *tốc độ* |
| 4 | **Mất khả năng đối chiếu chéo 2 phương pháp** | 🟡 Trung bình | Phương pháp `match` (chạy trong Nebula) đã cảnh báo tràn bộ nhớ từ 4 chặng; ở 10 chặng là bất khả thi. Mất cơ chế kiểm chứng độc lập hiện có |
| 5 | **Báo cáo & giao diện chưa chịu được quy mô đó** | 🟡 Trung bình | `top.json` hiện 19KB cho 2.418 chu trình → ~530KB cho 67.814; giao diện tải toàn bộ vào trình duyệt |
| 6 | **Phương án phân cụm (SCC/Louvain) đã đo là KHÔNG an toàn** | 🟡 Trung bình | Đây là cách giảm chi phí hiển nhiên nhất, nhưng `invoice_agg_graph/benchmark/measure_community_prefilter_safety.py` đo thật: Louvain **làm mất 85,35% chu trình thật** trên dữ liệu dày (chu trình cắt ngang ranh giới cụm). Chỉ an toàn trên dữ liệu thưa → **không dùng được cho đúng trường hợp cần nó nhất** |
| 7 | **Bộ nhớ tăng theo số chu trình giữ trong RAM** | 🟢 Thấp | Đo thật ở 8 chặng: 35MB — chưa đáng lo, nhưng cần đo lại ở 10 chặng |
| 8 | **Timeout 30 phút hiện tại sẽ thành điểm nghẽn** | 🟢 Thấp | 10 chặng trên cụm 98 DN 12,9 phút — còn trong ngưỡng, nhưng không còn biên an toàn |

---

## 5. Kế hoạch nâng cấp

Chia 6 giai đoạn, **có thể dừng sau bất kỳ giai đoạn nào** mà hệ thống vẫn ở trạng thái tốt hơn trước.

### Giai đoạn 0 — Lấp khoảng trống 2 chặng trước (rẻ nhất, hiệu quả cao nhất)

**Vì sao làm trước**: phủ 26% chu trình thật với chi phí gần bằng 0, trong khi 10 chặng tốn ×51,5 chi phí
để phủ 39%. Đây là "quả ngọt ở cành thấp".

- Đổi `min_len` từ 3 → 2 (tham số hoá, mặc định vẫn 3 để không đổi hành vi cũ đột ngột).
- Kiểm tra tác dụng phụ: chu trình 2 chặng (A→B→A) rất phổ biến trong thương mại thật (mua đi bán lại
  hợp pháp) → **bắt buộc** đo tỉ lệ báo động giả trước khi bật mặc định.
- Đối chiếu với 14 nhóm 2-chặng trong `ground_truth_cycle.json` để đo recall thật.

**Tiêu chí nghiệm thu**: bắt được ≥10/14 nhóm 2-chặng của IBM, và số chu trình 2-chặng trên
`hanoi_98cty` không vượt quá 3× số chu trình 3-chặng hiện có.

---

### Giai đoạn 1 — Đo & rào chắn (bắt buộc, làm trước khi nâng chặng)

Không nâng chặng ngay. Trước hết phải **nhìn thấy** chi phí trước khi trả nó.

1. **Đo mật độ trước khi chạy**: tính out-degree trung bình + số đỉnh trong SCC lớn nhất, ghi vào log
   và `meta.json`.
2. **Ước tính chi phí & cảnh báo**: dựa trên hệ số ×2,1–2,7 đã đo, ước tính thời gian cho số chặng
   người dùng chọn; nếu vượt ngưỡng thì cảnh báo ngay trên giao diện **trước khi chạy**
   (ví dụ: *"Ước tính ~13 phút với cấu hình này — cân nhắc giảm còn 6 chặng (~35 giây)"*).
3. **Ngân sách thời gian cứng (time budget)**: thêm biến `DETECT_TIME_BUDGET_SEC`. Khi chạm ngân sách,
   DFS **dừng có kiểm soát** và báo cáo trung thực *"đã quét xong N/M đỉnh xuất phát, kết quả CHƯA đầy
   đủ"* — thay vì bị timeout giết ngang và mất trắng.

> **Nguyên tắc**: thà trả kết quả một phần **có ghi rõ là một phần**, còn hơn chạy 30 phút rồi chết.
> Tuyệt đối không được im lặng cắt bớt — đó là kiểu sai nguy hiểm nhất (báo cáo trông đầy đủ nhưng
> thiếu dữ liệu).

**Tiêu chí nghiệm thu**: chạy 10 chặng trên `hanoi_98cty` với ngân sách 60 giây → dừng đúng hạn, báo
cáo ghi rõ tỉ lệ đã quét, không crash.

---

### Giai đoạn 2 — Chấm điểm theo độ dài chu trình (thay đổi cốt lõi)

Đây là thay đổi **quyết định việc nâng chặng có giá trị hay chỉ tạo nhiễu**.

Ý tưởng: chu trình càng dài thì càng dễ xuất hiện ngẫu nhiên, nên phải **đạt tiêu chuẩn cao hơn** mới
được coi là đáng ngờ tương đương.

Hai cách làm, nên thử nghiệm cả hai rồi chọn theo số đo:

- **Cách A — nâng ngưỡng cắt nhánh theo độ dài**: `bound(hop) = 50 + k*(hop - 5)` với hop > 5.
  Ưu điểm: giảm chi phí *trong lúc* dò (cắt sớm), nên vừa nhanh hơn vừa sạch hơn. Nhược điểm: cắt có
  mất mát (không còn "không mất mát" như hiện tại) — **phải ghi rõ trong tài liệu và báo cáo**.
- **Cách B — phạt điểm theo độ dài khi chấm**: giữ nguyên cách dò, trừ điểm chu trình dài khi xếp hạng.
  Ưu điểm: không mất chu trình nào, minh bạch. Nhược điểm: không giảm được chi phí dò.

**Hiệu chuẩn hệ số phạt bằng dữ liệu thật, không đoán**: dùng `ground_truth_cycle.json` của IBM — chọn
hệ số sao cho 21 nhóm gian lận ≥6 chặng **vẫn đứng trên** các chu trình nền ngẫu nhiên cùng độ dài.

**Tiêu chí nghiệm thu**: trong top 100 chu trình xếp hạng cao nhất trên bộ IBM, tỉ lệ trùng với đáp án
gốc phải **tăng** so với trước khi phạt.

---

### Giai đoạn 3 — Nâng giới hạn có kiểm soát

Chỉ làm sau khi giai đoạn 1 và 2 đã xong và nghiệm thu đạt.

- Mở rộng lựa chọn số chặng: `[3, 4, 5, 6, 7, 8, 10]` (bỏ 9 cho gọn giao diện).
- **Giới hạn thích ứng theo mật độ**: hệ thống tự đề xuất trần dựa trên out-degree đo được, ví dụ:

  | Out-degree TB | Trần đề xuất |
  |---:|---:|
  | < 5 (thưa) | 10 chặng |
  | 5–20 | 8 chặng |
  | 20–50 | 6 chặng |
  | > 50 (dày như `hanoi_98cty`) | 5 chặng, cảnh báo rõ nếu chọn cao hơn |

  Người dùng **vẫn được phép** vượt đề xuất — nhưng phải thấy cảnh báo và ước tính thời gian trước.
- Cập nhật `datasources.json` (options + hint) và `Step2Business.jsx` cho khớp.

---

### Giai đoạn 4 — Đo lại hiệu năng & độ chính xác thật

Chạy ma trận thử nghiệm, ghi vào `GIOI_HAN_HE_THONG.md`:

| Bộ dữ liệu | Số chặng cần đo | Đo cái gì |
|---|---|---|
| `hanoi_98cty` (dày, 98 DN) | 3, 5, 6, 8, 10 | thời gian, RAM, số chu trình |
| `ibm_aml_hi_small` (thưa, 515K DN) | 3, 5, 8, 10 | thời gian, RAM, **recall so với đáp án IBM** |
| `data_test_mua_ban_long_vong` | 3, 5, 10 | recall + false positive so với `DAP_AN.json` |

**Chỉ số quan trọng nhất cần theo dõi** — không phải thời gian chạy, mà là:
- **Recall trên chu trình ≥6 chặng của IBM**: hiện 0/21. Mục tiêu ≥15/21.
- **Precision ở top 100**: có bị chu trình dài ngẫu nhiên chiếm chỗ không.
- **Số cờ đỏ trên `hanoi_98cty`**: nếu nhảy từ 1.074 lên hàng chục nghìn thì cách chấm điểm ở giai
  đoạn 2 chưa đạt — phải quay lại hiệu chỉnh.

---

### Giai đoạn 5 — Chịu tải phía báo cáo & giao diện

- `build_report.py`: giới hạn số dòng ghi vào `top.json` (ví dụ top 500), ghi rõ tổng số thật.
- Giao diện bước 5: phân trang phía máy chủ thay vì tải toàn bộ vào trình duyệt.
- Bổ sung bộ lọc theo số chặng (đã có sẵn ô "Mọi số chặng" — nay mới thực sự có ý nghĩa).

---

## 6. Việc KHÔNG nên làm

| Ý tưởng | Vì sao không |
|---|---|
| Dùng SCC/Louvain phân cụm để giảm chi phí | **Đã đo thật**: mất 85,35% chu trình thật trên dữ liệu dày. Chỉ an toàn trên dữ liệu thưa — mà dữ liệu thưa vốn đã không cần tối ưu |
| Nâng số chặng cho phương pháp `match` (chạy trong Nebula) | Đã cảnh báo tràn bộ nhớ từ 4 chặng, từng làm crash graphd. 10 chặng là 10 phép nối liên tiếp — bất khả thi |
| Đổi thẳng `[3,4,5]` → `[3..10]` trong giao diện rồi tính sau | Sẽ tạo ra hàng chục nghìn báo động rác ngay lần chạy đầu, làm mất niềm tin vào hệ thống. Xem mục 3 |
| Bỏ cắt nhánh để "chắc chắn không sót" | Đã có ghi nhận: bỏ cắt nhánh làm 5 chặng chạy >5 phút chưa xong thay vì 16 giây, cùng kết quả |

---

## 7. Tóm tắt trả lời câu hỏi ban đầu

**"Đẩy lên 10 hop có khả thi không?"**

- **Về quy mô**: khả thi trên đồ thị thưa (kể cả hàng trăm nghìn doanh nghiệp), **không** khả thi trên
  cụm dày từ ~150 doanh nghiệp trở lên (150 DN ~2,2 giờ · 200 DN ~11,2 giờ). Cụm dày 98 DN ở mức 12,9 phút — làm được nhưng hết biên an toàn.
- **Về độ chính xác**: **sẽ giảm** nếu chỉ nâng số chặng. Chỉ tăng nếu làm kèm chấm điểm theo độ dài
  (giai đoạn 2). Đây là điều kiện bắt buộc, không phải tùy chọn.
- **Về giá trị**: có thật và đáng làm — 39% chu trình rửa tiền thật đang bị bỏ sót. Nhưng nên làm
  **giai đoạn 0 (chu trình 2 chặng) trước** vì rẻ hơn nhiều mà phủ được 26%.

**Thứ tự đề xuất**: Giai đoạn 0 → 1 → 2 → đo lại → rồi mới quyết định có làm giai đoạn 3 không.
Sau giai đoạn 2 sẽ có đủ số liệu thật để biết 10 chặng có đáng hay không, thay vì quyết định bây giờ
khi chưa biết chất lượng kết quả ở chặng dài ra sao.

---

## 8. Phụ lục — cách tái lập phép đo

```bash
# Đo đường cong tăng trưởng theo số chặng (không cần NebulaGraph chạy)
cd detecting_cheat_by_nebula/pipeline
python3 - <<'EOF'
import csv, sys, time, collections
sys.path.insert(0, ".")
import detect_circular_trading as D

adj = collections.defaultdict(list)
with open("../data/trades.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        adj[r["seller_mst"]].append((r["buyer_mst"], int(r["period"]),
                                     float(r["total_amount"]), float(r["total_vat"])))
bound = D.prune_bound(has_hidden=False, has_risky=False)
for h in range(3, 11):
    t0 = time.time(); raw = D.enumerate_cycles_dfs(adj, h, bound); dt = time.time() - t0
    uniq = len({frozenset(c["members"]) for c in raw})
    print(f"hop={h}  {dt:7.2f}s  {len(raw):>8,} lần xuất hiện  {uniq:>8,} duy nhất", flush=True)
EOF
```

Lưu ý: `data/trades.csv` chứa bộ dữ liệu **chạy gần nhất** — chạy `DATASET=<tên_bộ> python3
ingest_csv86.py` trước nếu muốn đo trên bộ khác.

### Đo chi phí theo kích thước cụm dày (bảng mục 2.2.1)

```bash
cd detecting_cheat_by_nebula/pipeline
python3 - <<'EOF'
import csv, sys, time, random, collections
sys.path.insert(0, ".")
import detect_circular_trading as D

# Lay phan phoi tien/ky THAT lam mau, de do thi tong hop giong thuc te
real = []
with open("../data/trades.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        real.append((int(r["period"]), float(r["total_amount"]), float(r["total_vat"])))
random.seed(42)

def make(n, density=0.84):          # 0.84 = mat do that cua hanoi_98cty
    adj = collections.defaultdict(list)
    ids = [f"{i:04d}" for i in range(n)]
    for a in ids:
        for b in ids:
            if a != b and random.random() < density:
                adj[a].append((b, *random.choice(real)))
    return adj

bound = D.prune_bound(has_hidden=False, has_risky=False)
for n in (98, 120, 150, 200):
    adj = make(n); e = sum(len(v) for v in adj.values())
    for h in (3, 5):
        t0 = time.time(); raw = D.enumerate_cycles_dfs(adj, h, bound); dt = time.time()-t0
        uniq = len({frozenset(c["members"]) for c in raw})
        print(f"{n:>4} DN  out-deg {e/len(adj):>5.1f}  hop={h}  {dt:>7.1f}s  {uniq:>7,} chu trình", flush=True)
EOF
```

**Cách quy đổi sang thời gian thực tế**: nhân kết quả mô phỏng với **×2,69**. Hệ số này suy ra bằng
cách chạy mô phỏng ở đúng quy mô 98 DN (được 5,6s) rồi đối chiếu với số đo thật trên `hanoi_98cty`
(15,04s). Nên **đo lại hệ số này** nếu đổi sang bộ dữ liệu có cấu trúc khác — nó phản ánh mức độ
"vón cục" (hub) của mạng lưới thật, thứ mà đồ thị ngẫu nhiên không tái tạo được.
