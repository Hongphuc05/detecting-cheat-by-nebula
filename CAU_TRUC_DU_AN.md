# Cấu trúc dự án `detecting_cheat_by_nebula`

> Tài liệu này mô tả **cây thư mục** và **vai trò từng phần** của `detecting_cheat_by_nebula/` —
> nơi vận hành chính thức pipeline phát hiện mua bán lòng vòng. Đọc file này trước
> khi đọc `README.md` (hướng dẫn chạy CLI) hoặc `HUONG_DAN_SU_DUNG_WEB.md` (hướng
> dẫn dùng giao diện web).
>
> Dọn dẹp lần gần nhất: 02/08/2026 — xem mục 5.

---

## 1. Tổng quan

`detecting_cheat_by_nebula` là bộ dữ liệu thật (98 doanh nghiệp Hà Nội, 8.976 hoá đơn GTGT) và
pipeline Python đi kèm để phát hiện giao dịch mua bán lòng vòng (circular trading).
Đây là nơi **vận hành chính thức** — khác với `invoice_agg_graph/` (kho nghiên cứu
& benchmark, giữ nguyên để tham khảo, không dùng để chạy thật) và `tax_graph/`
(bộ dữ liệu mô phỏng dùng đối chứng khi cần dữ liệu có đủ ĐKKD).

Luồng dữ liệu tổng quát:

```
raw/ (thô)  →  data/ (đã chuẩn hoá)  →  NebulaGraph  →  output/runs/<id>/ (kết quả)
     │                                      ▲
     └──────────── pipeline/ (7 script Python, điều phối bởi run_all.py) ──────┘
```

Giao diện web (`nebula_demo/`) gọi đúng các script trong `pipeline/` qua backend
Go — không có logic nghiệp vụ nào được viết lại ở phía web hay frontend.

---

## 2. Cây thư mục

```
detecting_cheat_by_nebula/
├── CAU_TRUC_DU_AN.md                      ← đang đọc — bản đồ tổng thể
├── README.md                              Hướng dẫn chạy pipeline bằng CLI
├── HUONG_DAN_SU_DUNG_WEB.md               Hướng dẫn dùng giao diện web (5 bước)
├── GIOI_HAN_HE_THONG.md                   Đo đạc thật: hệ thống chạy tốt tới đâu, giới hạn ở đâu
│
├── nebula_in_gotix.md                     Nghiên cứu khả thi: đưa NebulaGraph vào Gotix
├── nebula_in_real.md                      Nghiên cứu: NebulaGraph trong thực tế ngành tài chính
│
├── raw/                                   DỮ LIỆU THÔ — xem mục 3 (câu hỏi "raw/ cần gì")
│   ├── hanoi_98cty/                       1 BỘ DỮ LIỆU = 1 thư mục con
│   │   ├── company.csv                    98 công ty (KHÔNG có dòng tiêu đề)
│   │   ├── invoice.csv                    8.976 hoá đơn (KHÔNG có dòng tiêu đề)
│   │   ├── Mua vào bán ra 86 công ty.xlsx  File Excel gốc (91 sheet) — nguồn thật ban đầu
│   │   └── script.py                      Script trích xuất company.csv/invoice.csv TỪ file Excel trên
│   ├── data_test_mua_ban_long_vong/       Bộ tổng hợp có cài sẵn 19 chuỗi gian lận + DAP_AN.json để đối chiếu
│   └── ibm_aml_hi_small/                  Bộ test QUY MÔ (515.080 DN / 4,49 triệu hoá đơn, nguồn IBM AML)
│                                          — KHÔNG đẩy lên git (vượt giới hạn 100MB/file của GitHub)
│
├── data/                                  Dữ liệu ĐÃ CHUẨN HOÁ — output của ingest_csv86.py
│   ├── companies.csv                      mst, name, sector, address, revenue, report_date
│   ├── trades.csv                         Cạnh giao dịch đã GỘP theo kỳ (seller, buyer, period, ...)
│   └── shares_address.csv                 Cặp công ty trùng địa chỉ đăng ký (hiện rỗng — xem GIOI_HAN_HE_THONG.md)
│
├── schemas/
│   └── detecting_cheat_by_nebula.ngql                    Khuôn CREATE SPACE/TAG/EDGE/INDEX (thay {{SPACE}} lúc chạy)
│
├── pipeline/                              7 SCRIPT PYTHON — trái tim của dự án
│   ├── datasources.json                   Manifest: loại truy vấn + cách nhập liệu (điều khiển cả web)
│   ├── progress.py                        Giao thức phát tiến trình [[STEP]]/[[LOG]]/[[DONE]] dùng chung
│   ├── nebula_client.py                   Kết nối Nebula dùng chung (1 nơi duy nhất đọc cấu hình)
│   ├── ingest_csv86.py                    raw/*.csv → gộp hoá đơn thành cạnh theo kỳ → data/*.csv
│   ├── load_schema.py                     Tạo space/tag/edge/index từ schemas/detecting_cheat_by_nebula.ngql
│   ├── sync_graph.py                      Nạp data/*.csv vào Nebula theo lô
│   ├── validate_contract.py               Quét space, đối chiếu Data Contract → checklist + trần điểm
│   ├── detect_circular_trading.py         4 bước lõi: khoanh vùng → dò chu trình → khử trùng lặp → chấm điểm
│   ├── build_report.py                    .jsonl → report.txt + top.json + cycles.ngql
│   └── run_all.py                         Điều phối toàn bộ, tạo thư mục output/runs/<id>/
│
└── output/runs/<runId>/                   MỖI LẦN CHẠY — 1 thư mục riêng
    ├── meta.json                          Tham số + thời gian + số liệu tóm tắt
    ├── progress.log                       Toàn bộ log tiến trình
    ├── validation.json                    Kết quả quét Data Contract
    ├── graph_risk_flags.jsonl             Toàn bộ chu trình đã chấm điểm
    ├── report.txt                         Báo cáo dạng chữ
    ├── top.json                           Cùng nội dung report.txt, dạng máy đọc — web dùng file này
    └── cycles.ngql                        Câu lệnh nGQL dựng sẵn để vẽ lên Nebula Studio
```

---

## 3. `raw/` cần đúng những gì? (câu hỏi hay gặp)

**Không phải "vứt gì vào cũng được".** Mỗi bộ dữ liệu PHẢI nằm trong **1 thư mục
con riêng** của `raw/`, đặt tên tuỳ ý (chỉ chữ/số/gạch dưới/gạch ngang):

```
raw/<ten_bo>/company.csv
raw/<ten_bo>/invoice.csv
```

Lý do bắt buộc chia thư mục: nếu chỉ có 1 cặp `raw/company.csv` + `raw/invoice.csv`
cố định ở gốc thì không thể có bộ dữ liệu thứ hai — bộ mới sẽ **ghi đè** lên bộ
cũ, mất hết dấu vết "công ty nào đi với hoá đơn nào" của bộ trước. Cấu trúc con
theo tên bộ giải quyết đúng vấn đề này.

Khi chọn *"Dùng dữ liệu có sẵn trong detecting_cheat_by_nebula/raw"* (`datasource: local_existing`)
trên giao diện web, `Step1Data` gọi `GET /api/fraud/raw-datasets` để **liệt kê
mọi bộ đang có**, người dùng chọn đúng 1 bộ trước khi bấm "Nhập dữ liệu". Phía
CLI, `ingest_csv86.py` đọc bộ theo biến môi trường `DATASET` (mặc định
`hanoi_98cty`):

```python
DEFAULT_DATASET = "hanoi_98cty"
RAW_DIR = BASE / "raw"
COMPANY_CSV = RAW_DIR / DATASET / "company.csv"   # DATASET lay tu env, co kiem tra ky tu hop le
INVOICE_CSV = RAW_DIR / DATASET / "invoice.csv"
```

`COMPANY_CSV`/`INVOICE_CSV` vẫn override được tuyệt đối qua biến môi trường
riêng, dùng khi cần trỏ tới file nằm ngoài cấu trúc `raw/<ten_bo>/` chuẩn.

Yêu cầu bắt buộc cho từng file bên trong 1 bộ:

| File | Số cột tối thiểu | Thứ tự cột (KHÔNG có dòng tiêu đề) |
|---|---|---|
| `company.csv` | đúng 6 | `mst, ten_cong_ty, linh_vuc, dia_chi, doanh_thu, nam_bao_cao` |
| `invoice.csv` | tối thiểu 7 (thừa cột phía sau bị bỏ qua an toàn) | `so_hoa_don, ngay_xuat, mst_nguon, mst_dich, mo_ta, tien_chua_thue, thue_gtgt` |

Hai điều quan trọng cần biết:

1. **Sai tên file hoặc thiếu cột → báo lỗi rõ ràng ngay lập tức** (`FileNotFoundError`
   hoặc `ValueError` liệt kê rõ thiếu gì). Đây là điểm an toàn có chủ đích — thà
   dừng sớm còn hơn nạp dữ liệu sai mà không ai biết.
2. **Đúng SỐ LƯỢNG cột nhưng SAI THỨ TỰ/Ý NGHĨA sẽ KHÔNG báo lỗi gì** — hệ thống
   đọc theo vị trí cột (index cố định), không tự suy ra ý nghĩa từng cột. Ví dụ:
   nếu đảo vị trí `mst_nguon` và `mst_dich`, pipeline vẫn chạy trơn tru nhưng
   **toàn bộ chiều mua-bán bị đảo ngược** — sai âm thầm, nguy hiểm hơn báo lỗi.
   Đây là lý do bước "Xem trước dữ liệu" (giao diện web, bước 1) tồn tại: luôn
   nhìn vài dòng đầu qua giao diện trước khi tin dữ liệu đã đúng cột.

`Mua vào bán ra 86 công ty.xlsx` và `script.py` trong `raw/hanoi_98cty/`
**không được `ingest_csv86.py` đọc trực tiếp** — chúng là nguồn gốc dùng để
**tự sinh lại** `company.csv`/`invoice.csv` nếu cần (chạy
`python3 raw/hanoi_98cty/script.py`), không phải đầu vào của pipeline chính.

---

## 4. Ba lớp dữ liệu — đừng nhầm lẫn

| Lớp | Vai trò | Ai ghi | Ai đọc |
|---|---|---|---|
| `raw/` | Dữ liệu thô, đúng định dạng gốc, KHÔNG sửa tay | `raw/script.py` (từ Excel) hoặc người dùng tải lên | `ingest_csv86.py` |
| `data/` | Đã gộp cạnh theo kỳ, sẵn sàng nạp đồ thị | `ingest_csv86.py` | `sync_graph.py` |
| NebulaGraph (space) | Nguồn chân lý duy nhất khi phân tích | `sync_graph.py` | `validate_contract.py`, `detect_circular_trading.py`, web |

**Nguyên tắc quan trọng đã rút ra khi xây dựng:** `detect_circular_trading.py`
đọc thẳng từ NebulaGraph (không đọc lại `data/*.csv`) — vì nếu web cho chọn
space `tax_graph` mà script vẫn đọc CSV của `detecting_cheat_by_nebula`, kết quả sẽ sai mà
không báo lỗi gì. `data/` chỉ là trạm trung chuyển, không phải nguồn để phân tích.

---

## 5. Lịch sử dọn dẹp

### 02/08/2026 — đổi tên dự án & dọn file thừa

| Việc | Chi tiết |
|---|---|
| Đổi tên thư mục | `invoice_86/` → `detecting_cheat_by_nebula/`, cập nhật mọi đường dẫn trong `nebula_demo` (Go) và các script Python. Đổi luôn `schemas/invoice_86.ngql` → `schemas/detecting_cheat_by_nebula.ngql` |
| Xoá 2 tệp prompt dùng một lần | `PROMPT_SINH_DU_LIEU_TEST_LONG_VONG.md` (đề bài sinh bộ test — đã sinh xong), `PROMPT_THIET_KE_LAI_GIAO_DIEN_NGHIEP_VU.md` (đề bài thiết kế UI — đã làm xong) |
| Xoá `KE_HOACH_XAY_DUNG_PIPELINE_VA_WEB.md` | Kế hoạch đã triển khai xong, nội dung còn giá trị đã nằm trong tài liệu này + `README.md` |
| Xoá `archive_truoc_pipeline/` | Tài liệu & tệp `.bak` từ giai đoạn `nebula-importer` cũ, không có gì đang tham chiếu tới |
| Dọn `output/runs/` | Giữ 3 lần chạy gần nhất, xoá 29 lần cũ — giải phóng **465MB → 364KB** |

Tất cả tệp bị xoá đều đã có trong lịch sử git (`detecting-cheat-by-nebula` trên
GitHub), khôi phục được bằng `git show <commit>:<đường_dẫn>` nếu cần tra cứu lại.

### 01/08/2026 — dọn lần đầu, gom cấu trúc

| Trước | Sau |
|---|---|
| `company.csv`, `invoice.csv`, `Mua vào bán ra 86 công ty.xlsx` bị trùng lặp ở cả gốc `detecting_cheat_by_nebula/` lẫn `raw/` | Xoá bản trùng ở gốc (đã đối chiếu byte-for-byte giống hệt), giữ đúng 1 bản trong `raw/` |
| `script.py` nằm ở gốc, tách rời file Excel nó cần đọc | Chuyển vào `raw/script.py` — cùng chỗ với `.xlsx`, không phải sửa dòng code nào (đường dẫn tính theo vị trí file) |
| 8 tệp/thư mục thuộc giai đoạn `nebula-importer` cũ nằm rải rác ở gốc | Gom vào `archive_truoc_pipeline/` (đã xoá hẳn ngày 02/08/2026) |
| Không có tài liệu tổng quan cấu trúc | Tài liệu này |

Kiểm chứng sau khi dọn: `python3 pipeline/ingest_csv86.py` vẫn nạp đúng 98 công
ty / 8.976 hoá đơn / 7.945 cạnh; giao diện web vẫn chạy `run_all.py` bình thường
— không có gì phụ thuộc vào các đường dẫn đã di chuyển.
