# PROMPT — Thiết kế lại `nebula_demo` thành giao diện nghiệp vụ theo từng bước

> Tài liệu này là **đề bài**, chưa phải kế hoạch triển khai. Viết ngày 01/08/2026.
> Ngữ cảnh nền: [`KE_HOACH_XAY_DUNG_PIPELINE_VA_WEB.md`](KE_HOACH_XAY_DUNG_PIPELINE_VA_WEB.md) (đã xong),
> [`HUONG_DAN_SU_DUNG_WEB.md`](HUONG_DAN_SU_DUNG_WEB.md), [`README.md`](README.md).

---

## 1. Vấn đề với giao diện hiện tại

Chế độ **Phát hiện gian lận** hiện đang bị nhét vào khung của một công cụ khác:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Header: [Truy vấn nGQL] [Phát hiện gian lận]          Space: [▾]    │
├──────────────┬──────────────────────────────────┬───────────────────┤
│              │ Graph View | Table View | Báo cáo│                   │
│ FraudConsole │                                  │ ELEMENT INSPECTOR │
│ (wizard      │      ┌──────────────────┐        │                   │
│  5 bước nhồi │      │  canvas đồ thị   │        │ "Click vào một    │
│  trong 340px)│      │   (TRỐNG RỖNG    │        │  Đỉnh hoặc Cạnh   │
│              │      │   suốt bước 1-4) │        │  để xem chi tiết" │
│              │      └──────────────────┘        │                   │
│   340px      │          ~1100px                 │      300px        │
└──────────────┴──────────────────────────────────┴───────────────────┘
```

Ba hệ quả cụ thể:

1. **~70% màn hình bị chiếm bởi thứ chưa dùng đến.** Canvas đồ thị và Element Inspector
   là mối quan tâm *trực quan hoá*, nhưng chúng chiếm chỗ ngay từ bước 1 (nhập dữ liệu),
   trong khi phải tới bước cuối mới có gì để vẽ.
2. **Nghiệp vụ bị ép vào cột 340px.** Bảng mô tả cột dữ liệu, checklist Data Contract,
   log tiến trình, bảng kết quả — tất cả phải cuộn dọc trong một dải hẹp. Không đủ chỗ
   để làm đúng những gì nghiệp vụ cần (xem trước dữ liệu kiểu bảng tính, đối chiếu cột,
   so sánh nhiều chu trình).
3. **Mô hình tư duy sai.** Người dùng nghiệp vụ (cán bộ thuế) không nghĩ theo
   "chạy query rồi vẽ đồ thị". Họ nghĩ theo "có dữ liệu gì → kiểm tra dữ liệu →
   chọn nghiệp vụ cần rà → chạy → đọc kết quả → *nếu cần* thì xem sơ đồ quan hệ".

---

## 2. Mục tiêu chuyển đổi

| | Hiện tại | Cần thành |
|---|---|---|
| Mô hình | Console đồ thị, gắn thêm sidebar gian lận | Bàn làm việc điều tra gian lận theo từng bước |
| Bố cục | 3 cột cố định, đồ thị luôn hiện | **Toàn màn hình theo từng bước**, mỗi bước 1 màn hình riêng |
| Đồ thị | Trung tâm, mặc định, luôn chiếm chỗ | **Tuỳ chọn, chỉ bật ở bước cuối** |
| Điều hướng | Cuộn dọc trong cột 340px | Thanh bước (stepper) ngang trên đầu, đi tới/lui được |
| Dữ liệu | Chỉ mô tả bằng chữ trong sidebar | **Xem được như Excel**: lưới bảng, tiêu đề cột, cuộn, phân trang |
| Tiến trình | 1 danh sách bước phẳng | Chia theo **quá trình con**, mỗi quá trình có tiến trình riêng |

**Nguyên tắc bao trùm:** mỗi bước là một màn hình làm việc trọn vẹn, dùng hết chiều
ngang. Không có vùng nào chiếm chỗ mà chưa tới lượt dùng.

---

## 3. Khung màn hình mới

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Gotix — Rà soát gian lận hoá đơn          Space: [invoice_agg_graph ▾] [☀/☾]│
├──────────────────────────────────────────────────────────────────────────────┤
│  ①  Dữ liệu  ──  ②  Nghiệp vụ  ──  ③  Kiểm tra  ──  ④  Chạy  ──  ⑤  Kết quả  │
│     ✓ 98 DN         ✓ Lòng vòng      ⚠ trần 60      ✓ 15,2s      1.074 cờ đỏ │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                    NỘI DUNG CỦA BƯỚC ĐANG CHỌN — TOÀN MÀN HÌNH               │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  [← Quay lại]                                        [Tiếp tục →]            │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Thanh bước** hiện trạng thái tóm tắt dưới mỗi bước (số liệu chốt của bước đó),
  cho phép bấm quay lại bước đã hoàn thành; bước chưa đủ điều kiện thì mờ và không bấm được.
- **Thanh đáy** có nút Quay lại / Tiếp tục; nút Tiếp tục mờ khi bước hiện tại chưa xong.
- Không còn Element Inspector cố định. Không còn tab Graph/Table cố định.

---

## 4. Đặc tả từng bước

### Bước ① — Dữ liệu (quản lý & nhập liệu, kiểu Excel)

Đây là bước được nâng cấp nhiều nhất. Chia 3 vùng:

**4.1 — Kiểm kê dữ liệu đang có** (phần trên, dạng thẻ/bảng)

Liệt kê các không gian dữ liệu đang có trong hệ thống, mỗi dòng cho biết:

| Không gian | Số DN | Số giao dịch | Dải kỳ | Có ĐKKD? | Trần điểm | Cập nhật |
|---|---|---|---|---|---|---|
| invoice_agg_graph | 98 | 7.945 | 202011–202112 | ✕ | 60/100 | 01/08 14:35 |
| tax_graph | 36 | 27 | 202501–202506 | ✓ | 100/100 | — |

Bấm 1 dòng = chọn không gian đó làm việc (thay cho dropdown Space ở header).

**4.2 — Mô tả & xem trước dữ liệu** (phần giữa, **lưới kiểu Excel**)

Tab con cho từng bảng dữ liệu: `Doanh nghiệp` · `Giao dịch (đã gộp)` · `Hoá đơn gốc` ·
`Liên kết địa chỉ`.

Mỗi tab hiện:
- **Bảng mô tả cột**: tên cột · kiểu · ý nghĩa · ví dụ · % giá trị rỗng
- **Lưới xem trước** kiểu bảng tính: số dòng bên trái, tiêu đề cột cố định khi cuộn,
  cuộn ngang/dọc, phân trang (50 dòng/trang), ô số căn phải, ô tiền có phân cách nghìn
- **Thanh chất lượng dữ liệu**: tổng dòng · dòng trùng · dòng tự bán cho mình đã loại ·
  MST không có trong bảng doanh nghiệp · khoảng ngày min–max

**4.3 — Nhập dữ liệu mới** (phần dưới, mở ra khi bấm "Nhập dữ liệu mới")

- Chọn nguồn (4 nguồn như hiện tại, 2 cái `planned` vẫn hiện nhưng mờ + ghi rõ vướng gì)
- **Trước khi nhập**: hiện bảng yêu cầu định dạng — mỗi cột 1 dòng, có ví dụ mẫu
- **Sau khi chọn file**: đọc thử 20 dòng đầu → hiện **lưới xem trước ngay trên trình duyệt**
  để người dùng tự đối chiếu cột trước khi bấm nhập thật (bắt lỗi lệch cột sớm)
- Bấm Nhập → hiện tiến trình → sau khi xong, phần 4.1 và 4.2 tự làm mới

> **Điểm cốt lõi của bước này:** người dùng phải **nhìn thấy dữ liệu thật** trước khi
> chạy bất cứ thứ gì, chứ không phải tin vào một dòng chữ "98 công ty".

---

### Bước ② — Nghiệp vụ (chọn loại rà soát)

Bỏ dropdown. Thay bằng **lưới thẻ**, mỗi loại nghiệp vụ 1 thẻ lớn:

```
┌────────────────────────────┐  ┌────────────────────────────┐
│ ⭕ MUA BÁN LÒNG VÒNG       │  │ 🏚 DOANH NGHIỆP MA         │
│                            │  │                            │
│ Tìm vòng khép kín A→B→C→A  │  │ DN mới lập, xuất hoá đơn   │
│ trong hoá đơn GTGT, chấm   │  │ lớn rồi ngừng hoạt động    │
│ điểm 0-100 theo 5 tín hiệu │  │                            │
│                            │  │                            │
│ Cần: TRADES, kỳ            │  │        SẮP CÓ              │
│ Nên có: ĐKKD (+40đ)        │  │                            │
│           ✓ SẴN SÀNG       │  │                            │
└────────────────────────────┘  └────────────────────────────┘
```

Chọn xong 1 thẻ → mở panel **tham số** bên dưới, đọc từ `params` trong `datasources.json`:
kỳ từ/đến (có thanh trượt theo dải kỳ thật của dữ liệu), số chặng, phương pháp — mỗi
tham số kèm dòng gợi ý chi phí ("5 chặng ~16 giây trên 98 DN").

Kèm khối giải thích **cách chấm điểm**: 5 tín hiệu, trọng số, ngưỡng cờ đỏ/theo dõi —
để người dùng hiểu con số họ sắp nhận được nghĩa là gì.

---

### Bước ③ — Kiểm tra dữ liệu (Data Contract)

Toàn màn hình, chia 2 cột:

- **Trái — Checklist**: từng mục 1 dòng, có biểu tượng trạng thái (✓ đủ / ○ trống / ✕ thiếu),
  nhãn, mô tả chi tiết đầy đủ (không cắt ngắn, không phải rê chuột mới thấy), số điểm mất.
  Mục thiếu có thêm dòng **"Cần gì để khắc phục"**.
- **Phải — Bảng điểm trực quan**: thanh 100 điểm chia 5 khúc theo tín hiệu, khúc nào
  không đạt được thì tô xám kèm nhãn "−25đ · không có dữ liệu ĐKKD". Nhìn 1 giây là hiểu
  vì sao trần chỉ 60.

Kết luận đậm ở trên cùng + nút **Chạy rà soát** ở dưới (mờ nếu `can_run = false`).

---

### Bước ④ — Chạy (chia theo quá trình con, mỗi quá trình 1 tiến trình)

Không còn là 1 danh sách bước phẳng. Chia thành các **quá trình**, mỗi quá trình là 1 khối
có thanh tiến trình riêng, các bước con bên trong, và số liệu chốt khi xong:

```
┌──────────────────────────────────────────────────────────────────────┐
│ ✓ QUÁ TRÌNH 1 — CHUẨN BỊ DỮ LIỆU                          2,1 giây   │
│   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  100%          │
│   ✓ Đọc file nguồn        98 DN · 8.976 hoá đơn            41ms      │
│   ✓ Gộp cạnh theo kỳ      7.945 cạnh (giảm 1,1 lần)        39ms      │
│   ✓ Nạp vào đồ thị        98 đỉnh · 7.945 cạnh            146ms      │
├──────────────────────────────────────────────────────────────────────┤
│ ⟳ QUÁ TRÌNH 2 — DÒ CHU TRÌNH                            đang chạy... │
│   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   45%          │
│   ✓ Khoanh vùng           95/98 DN vừa bán vừa mua        368ms      │
│   ⟳ Duyệt đồ thị (DFS)    đã tìm 1.240 lượt xuất hiện                │
│   ○ Khử trùng lặp                                                    │
├──────────────────────────────────────────────────────────────────────┤
│ ○ QUÁ TRÌNH 3 — CHẤM ĐIỂM & LẬP BÁO CÁO                              │
└──────────────────────────────────────────────────────────────────────┘

  ┌─ Nhật ký kỹ thuật ─────────────────────────── [▾ mở rộng] ────────┐
  │ DFS trong ứng dụng · cắt nhánh tại balance+time < 50 ...          │
  └───────────────────────────────────────────────────────────────────┘
                                                         [ Dừng lại ]
```

Yêu cầu:
- **Nhật ký kỹ thuật thu gọn mặc định** — người dùng nghiệp vụ không cần đọc, nhưng
  mở ra được khi cần đối chiếu.
- Mỗi bước con hiện **số liệu chốt bằng ngôn ngữ nghiệp vụ**, không phải tên biến
  (`raw_cycles=2581` → "đã tìm 2.581 lượt xuất hiện chu trình").
- Khi xong: tự chuyển sang bước ⑤ sau ~1 giây, có nút bỏ qua.

---

### Bước ⑤ — Kết quả (toàn màn hình) + trực quan hoá **theo yêu cầu**

**5.1 — Dải số liệu** (trên cùng): chu trình · cờ đỏ · theo dõi · điểm cao nhất/trần · thời gian.
Nếu trần < 100 thì có dải cảnh báo giải thích rõ.

**5.2 — Nội dung chính**: tab `Chu trình` · `Doanh nghiệp` · `File kết quả` — dùng **hết
chiều ngang** (khác hẳn hiện tại bị ép trong ~1100px). Bảng chu trình cần thêm:
- Lọc theo mức (cờ đỏ / theo dõi / tất cả), theo số chặng, theo kỳ
- Sắp xếp theo từng cột
- Ô tìm kiếm theo MST hoặc tên doanh nghiệp
- Mỗi dòng bung ra được để xem chi tiết 5 tín hiệu + số tiền + kỳ từng cạnh

**5.3 — Trực quan hoá: TẮT MẶC ĐỊNH**

Đây là thay đổi trọng tâm của yêu cầu. Đồ thị **không** chiếm chỗ cho tới khi được gọi:

- Mỗi dòng chu trình có nút **"Xem sơ đồ"**
- Bấm vào → mở **ngăn trượt (drawer) chiếm ~60% màn hình từ bên phải**, hoặc cửa sổ nổi
  toàn màn hình — chứa canvas đồ thị + Element Inspector (hai thứ đang chiếm chỗ hiện nay)
- Đóng ngăn → quay lại bảng, không mất trạng thái lọc/sắp xếp
- Có công tắc **"Luôn hiện sơ đồ"** cho ai muốn giữ mở

Trong ngăn trực quan hoá vẫn giữ nguyên năng lực đã có: viền đỏ cho thành viên chu trình,
Tùy chỉnh hiển thị, Fit View, Physics, AI Phân tích Đồ thị.

---

## 5. Ràng buộc bất biến — KHÔNG được phá

1. **Chế độ "Truy vấn nGQL" giữ nguyên 100%.** Đó là sản phẩm gốc: LeftConsole 4 tab,
   GraphCanvas, TableView, ElementInspector, ScenarioNotebook. Việc thiết kế lại chỉ
   áp dụng cho chế độ Phát hiện gian lận.
2. **Không viết lại thuật toán bằng JavaScript.** Mọi số liệu phải đến từ API; Python
   vẫn là nguồn chân lý duy nhất của công thức chấm điểm.
3. **Không sinh nGQL dạng chuỗi hop nối tiếp.** Chỉ dùng dạng một chặng neo cả hai đầu
   như hiện tại — dạng kia đã làm chết graphd (OOM-kill).
4. **Không bịa dữ liệu.** Thiếu ĐKKD thì hiện rõ là thiếu và mất bao nhiêu điểm.
5. **Tái sử dụng `GraphCanvas` nguyên vẹn**, chỉ đổi nơi đặt nó (từ cột giữa cố định
   sang ngăn trượt gọi theo yêu cầu). Cẩn thận: vis-network cần vùng chứa có kích thước
   thật lúc khởi tạo — mở trong ngăn ẩn/hiện phải xử lý resize.
6. **Manifest `datasources.json` vẫn điều khiển giao diện.** Thêm loại nghiệp vụ mới
   vẫn chỉ cần sửa JSON + viết script, không phải sửa React.

---

## 6. API cần bổ sung

Giao diện mới cần dữ liệu mà backend hiện chưa cung cấp:

| Endpoint | Việc | Phục vụ |
|---|---|---|
| `GET /api/fraud/datasets` | Kiểm kê mọi space: số DN, số cạnh, dải kỳ, có ĐKKD không, trần điểm, thời điểm cập nhật | Bước ①.1 |
| `GET /api/fraud/schema?space=` | Mô tả cột từng bảng: tên, kiểu, ý nghĩa, % rỗng | Bước ①.2 |
| `GET /api/fraud/preview?space=&table=&page=` | Xem trước dữ liệu dạng lưới, có phân trang | Bước ①.2 |
| `GET /api/fraud/quality?space=` | Thống kê chất lượng: trùng, tự bán cho mình, MST mồ côi, khoảng ngày | Bước ①.2 |
| `POST /api/fraud/preview-upload` | Đọc thử 20 dòng đầu của file vừa chọn, chưa nhập thật | Bước ①.3 |

Mô tả ý nghĩa cột nên đọc từ `datasources.json` (đã có sẵn phần `columns` với `desc`),
tránh viết lặp ở 2 nơi.

---

## 7. Tiêu chí nghiệm thu

1. Ở bước ①–④, **không có pixel nào** dành cho canvas đồ thị hay Element Inspector.
2. Bước ① xem được dữ liệu thật dạng lưới, cuộn được, phân trang được, tiêu đề cột
   không trôi khi cuộn.
3. Bước ② chọn nghiệp vụ bằng thẻ; loại chưa làm hiện rõ "sắp có" kèm lý do.
4. Bước ③ nhìn 1 giây hiểu được vì sao trần điểm là 60 chứ không phải 100.
5. Bước ④ chia ít nhất 3 quá trình, mỗi quá trình có thanh tiến trình riêng; nhật ký
   kỹ thuật thu gọn mặc định.
6. Bước ⑤ bảng kết quả dùng hết chiều ngang, lọc/sắp xếp/tìm kiếm được; đồ thị chỉ hiện
   khi bấm "Xem sơ đồ".
7. Chuyển sang chế độ "Truy vấn nGQL" — mọi thứ hoạt động **y hệt trước khi sửa**.
8. `npm run build` sạch, `go build` sạch, chạy lại bộ 20 test nghiệm thu vẫn đạt.

---

## 8. Điểm cần chốt trước khi làm

| # | Câu hỏi | Đề xuất |
|---|---|---|
| 1 | Trực quan hoá mở dạng **ngăn trượt bên phải** hay **cửa sổ nổi toàn màn hình**? | Ngăn trượt ~60% — vẫn thấy bảng kết quả bên trái để đối chiếu |
| 2 | Lưới Excel: tự viết hay dùng thư viện (AG Grid / TanStack Table)? | **Tự viết** — nhu cầu đơn giản (cuộn + phân trang + tiêu đề cố định), tránh thêm ~200KB bundle |
| 3 | Xem trước dữ liệu đọc từ **file CSV** hay từ **Nebula**? | Từ **Nebula** — đúng thứ sẽ được phân tích, tránh bẫy "xem một đằng chạy một nẻo" đã gặp |
| 4 | Bước ① có cho **xoá / nạp lại** dữ liệu của một space không? | Có, nhưng phải gõ xác nhận tên space (thao tác phá huỷ) |
| 5 | Giữ nút chuyển 2 chế độ ở header, hay tách hẳn 2 đường dẫn `/` và `/fraud`? | Giữ nút — đơn giản hơn, không phải thêm router |
