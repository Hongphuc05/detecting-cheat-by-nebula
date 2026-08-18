# CLAUDE.md — detecting_cheat_by_nebula

## Mô tả

Pipeline Python **vận hành chính thức** phát hiện giao dịch **mua bán lòng vòng** (circular
trading / carousel VAT fraud) trên NebulaGraph. Đổi tên từ `invoice_86` ngày 02/08/2026 (xem
`CAU_TRUC_DU_AN.md` mục 5). Dữ liệu gốc: 98 doanh nghiệp thật ở Hà Nội, 8.976 hóa đơn GTGT thật
(`raw/hanoi_98cty/`), cộng thêm các bộ test tổng hợp/quy mô lớn khác trong `raw/<tên_bộ>/`.

Đây là **nguồn chân lý duy nhất** cho công thức chấm điểm/thuật toán — `nebula_demo` (Go) chỉ
gọi lại pipeline này qua subprocess, không viết lại logic.

## Tech stack / dependency chính

Python 3, phụ thuộc **`nebula3-python`** (client Nebula) — không pandas (đã bỏ khỏi
`sync_graph.py` trong lần tối ưu RAM). Từ khi có `ingest_trino_gotix.py` (nguồn dữ liệu tích hợp
thật với gotix), thêm phụ thuộc **`trino`** (Python client, chỉ script này dùng). **Không có
`requirements.txt`** — cần Phúc xác nhận cách cài đặt môi trường thực tế
(`pip install nebula3-python trino` thủ công? — đúng lệnh đang dùng trong `nebula_demo/Dockerfile`).

## Git workflow (chốt với Phúc 18/08/2026, cùng lúc quyết định N4)

Repo GitHub `Hongphuc05/detecting-cheat-by-nebula`, nhánh chính `main`. **Khác với
`gotix-datalake`** (repo đó bắt buộc tạo nhánh riêng + Merge Request, tuyệt đối không đụng
`main` mà không hỏi trước) — repo này **sửa/commit/push thẳng vào `main`**, không tạo nhánh
riêng, không cần Merge Request/PR cho mỗi task. Lý do: quy mô nhỏ, ít người sửa, không có luồng
review qua GitLab như `gotix-datalake`. Rule "NEVER touch main" trong `gotix-datalake/CLAUDE.md`
chỉ áp dụng cho repo đó, không áp dụng ở đây.

Lưu ý riêng: repo này đang ở chế độ **public** trên GitHub và còn dữ liệu thật (98 công ty Hà
Nội — MST/tên/địa chỉ/doanh thu) trong lịch sử git — chưa chốt xong việc này có ổn hay cần xử lý
(xem root `Bigdata/CLAUDE.md` mục C.4). Push code/doc bình thường vẫn làm thẳng `main` như trên;
việc riêng "public + dữ liệu thật" là 1 quyết định khác, chưa liên quan tới quy trình git thường
ngày.

## Cấu trúc thư mục quan trọng

```
detecting_cheat_by_nebula/
├── raw/<tên_bộ>/company.csv + invoice.csv    # dữ liệu THÔ, mỗi bộ 1 thư mục con
├── data/                                     # trung gian: companies.csv, trades.csv, shares_address.csv (tự sinh, KHÔNG commit)
├── schemas/detecting_cheat_by_nebula.ngql    # CREATE SPACE/TAG/EDGE/INDEX
├── pipeline/
│   ├── nebula_client.py            # kết nối Nebula dùng chung — 1 nơi duy nhất đọc cấu hình
│   ├── ingest_csv86.py              # raw/*.csv -> gộp hóa đơn theo THÁNG -> data/*.csv
│   ├── ingest_trino_gotix.py        # nguồn khác: đọc trực tiếp Trino (gotix-datalake) -> data/*.csv,
│   │                                 # dùng cho luồng tích hợp thật với gotix (xem mục "Tích hợp gotix" dưới)
│   ├── load_schema.py               # tạo space/tag/edge/index
│   ├── sync_graph.py                # nạp data/*.csv vào Nebula theo lô (streaming, không nạp cả file vào RAM)
│   ├── validate_contract.py         # quét space, đối chiếu Data Contract -> trần điểm khả đạt
│   ├── detect_circular_trading.py   # khoanh vùng -> DFS/MATCH dò chu trình -> khử trùng lặp -> chấm điểm
│   ├── export_invoice_flags.py      # tra ngược qua Trino: hóa đơn nào nằm trong chu trình đã dò
│   ├── build_report.py              # .jsonl -> report.txt + top.json + cycles.ngql
│   └── run_all.py                   # điều phối toàn bộ, tạo output/runs/<runId>/
└── output/runs/<runId>/              # kết quả mỗi lần chạy (KHÔNG commit) — LUÔN có meta.json
                                       # (started_at/finished_at/status/result), dùng làm nguồn
                                       # lịch sử cho nebula_demo (xem nebula_demo/CLAUDE.md)
```

## Lệnh build/test/lint/run cụ thể

```bash
cd detecting_cheat_by_nebula/pipeline

python3 run_all.py --all                                   # lần đầu / khi đổi dữ liệu nguồn
python3 run_all.py                                          # đã có dữ liệu trong Nebula, chỉ chạy lại phát hiện
python3 run_all.py --from 202101 --to 202112 --hops 5 --method dfs
python3 run_all.py --rebuild                                # xóa space rồi tạo lại (MẤT dữ liệu cũ)
DATASET=<tên_bộ> python3 ingest_csv86.py                    # chạy riêng bước đọc dữ liệu
```

Không tìm thấy test tự động (không có `pytest`/thư mục `tests/`) hay lint config riêng.

## Data flow / kiến trúc riêng

```
raw/<tên_bộ>/company.csv + invoice.csv (KHÔNG có dòng tiêu đề, đọc theo VỊ TRÍ cột)
        │  ingest_csv86.py — gộp mọi hóa đơn cùng 1 cặp bán-mua trong CÙNG 1 THÁNG thành 1 cạnh
        ▼
data/companies.csv, trades.csv, shares_address.csv
        │  sync_graph.py — INSERT VERTEX/EDGE theo lô
        ▼
NebulaGraph (space = tên dataset, trừ khi ghi đè bằng env SPACE)
        │  detect_circular_trading.py — DFS (mặc định) hoặc MATCH (hop cố định, KHÔNG dùng `*`)
        ▼
output/runs/<runId>/{report.txt, top.json, graph_risk_flags.jsonl, cycles.ngql}
```

## Tích hợp gotix (`gotix-datalake` ↔ Nebula), 14/08/2026

Nhánh dữ liệu thứ 2, song song với `raw/*.csv` — đọc trực tiếp từ Trino của `gotix-datalake`
(`ingest_trino_gotix.py`, `datasource_id=trino_gotix`) thay vì file CSV tĩnh. Toàn bộ kiến trúc
chi tiết (nạp gần-realtime, dò vòng theo lịch 30 phút, trả kết quả về Iceberg
`tier3.risk_feature_graph_*`) nằm bên phía `gotix-datalake`, xem
`gotix-datalake/docs/DAG_for_nebula/BAO_CAO_TRIEN_KHAI.md` — không nhắc lại ở đây để tránh 2 nơi
lệch nhau. Điểm cần biết ở phía repo này:
- `run_all.py --all --skip-detect --datasource trino_gotix` là lệnh gotix-datalake's Airflow DAG
  (`tier2_ingest_nebula_delta`) gọi qua `nebula_demo` mỗi khi có hóa đơn mới — KHÔNG chạy detect,
  chỉ nạp dữ liệu (xem lý do ở comment `run_all.py::main`, tránh tốn thời gian chạy detect 2 lần).
- `run_all.py` (không `--skip-detect`, `--datasource trino_gotix`) là lệnh DAG
  `tier3_compute_risk_features_graph` gọi theo lịch 30 phút để dò vòng.

Schema cột bắt buộc (đọc theo vị trí, không có header):
- `company.csv` (6 cột): `mst, ten_cong_ty, linh_vuc, dia_chi, doanh_thu, nam_bao_cao`
- `invoice.csv` (≥7 cột): `so_hoa_don, ngay_xuat, mst_nguon, mst_dich, mo_ta, tien_chua_thue, thue_gtgt`

## Gotcha/rule riêng

- **Sai THỨ TỰ cột (không phải thiếu cột) KHÔNG báo lỗi gì** — chỉ đảo ngược âm thầm chiều
  mua-bán. Luôn xem trước dữ liệu qua giao diện web (bước 1) trước khi tin dữ liệu đúng cột.
- **`min_len=3`** trong `enumerate_cycles_dfs` loại bỏ hoàn toàn chu trình 2 chặng — theo phân
  tích với bộ IBM AML, đây là **26% số chu trình gian lận thật** đã biết trước, đang bị bỏ sót
  có chủ đích (xem `KE_HOACH_NANG_CAP_10_HOP.md`).
- **Chi phí DFS tăng theo hàm mũ theo MẬT ĐỘ đồ thị (out-degree), không theo số đỉnh** — đo thật:
  98 công ty dày đặc (out-degree ~82) tốn CPU hơn 515.080 công ty thưa (out-degree ~1,5). Đẩy số
  chặng tối đa (`--hops`) lên cao trên cụm dày có thể khiến DFS chạy hàng giờ — xem
  `GIOI_HAN_HE_THONG.md` + `KE_HOACH_NANG_CAP_10_HOP.md` để có số đo cụ thể trước khi đổi.
- **Bước gộp hóa đơn theo THÁNG giả định ~1 hóa đơn/cặp/tháng.** Với dữ liệu có nhiều giao dịch
  nền trong cùng 1 kỳ (vd bộ IBM AML dồn cả 10 ngày vào 1 kỳ), gộp cạnh sẽ **phá hủy** tín hiệu
  cân bằng giá trị thay vì bảo toàn nó — không dùng bộ dữ liệu kiểu này để đo độ chính xác.
- **`run_all.py` tự suy `SPACE` từ `--dataset`** nếu biến môi trường `SPACE` chưa được set thủ
  công (đã sửa bug thật: trước đây fallback cứng về `invoice_agg_graph`, gây lẫn dữ liệu giữa
  các bộ khi ai đó chạy CLI quên set `SPACE`).
- **Hook tự dọn dẹp khi import lỗi** (`cleanup_after_failure` trong `run_all.py`): giết tiến
  trình con còn treo + xóa file trung gian, **chỉ xóa space nếu space đó do chính lần chạy này
  tạo ra** (chưa tồn tại trước đó) hoặc dùng `--rebuild` — không bao giờ xóa space đã có dữ liệu
  tốt từ trước.
- **Schema cần cả `idx_trades_period` VÀ `idx_company`** (thêm sau) để `nebula_demo` dùng được
  đường `LOOKUP` nhanh ở bảng xem trước — thiếu index tự lùi về `MATCH` chậm hơn nhưng vẫn đúng.
- Cấm cú pháp nGQL `*` biến thiên độ dài (giống ghi chú ở `nebula_demo/CLAUDE.md`) — từng crash
  `graphd` trên dữ liệu dày.
- **`meta.json` (trong `output/runs/<runId>/`) là nguồn lịch sử bền vững duy nhất** cho MỌI lần
  chạy `run_all.py`, dù là nạp dữ liệu (`--all --skip-detect`, `steps_run` chứa `"ingest"`) hay dò
  vòng (`steps_run` chứa `"detect"`). Trường `result` **khác nhau theo loại chạy**: dò vòng ghi
  `total/red/watch/max_achievable_score/top_score` (từ `detect_circular_trading.py`); nạp dữ liệu
  ghi `companies/trades/shares_address/shares_phone/persons/legal_rep_of/period_from/period_to`
  (lấy từ `sync_graph.py::progress.done(...)`, đã sửa 15/08/2026 — trước đó bị bỏ qua, `result`
  toàn `null` dù số liệu đã có sẵn trong log). `nebula_demo`'s tab "Lịch Sử" (`/history`) đọc thẳng
  các file này, KHÔNG đọc registry trong bộ nhớ của Go (mất khi container restart).
