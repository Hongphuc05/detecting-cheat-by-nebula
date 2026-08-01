# detecting_cheat_by_nebula — Pipeline phát hiện mua bán lòng vòng

Pipeline vận hành chính thức cho bài toán phát hiện giao dịch lòng vòng (circular
trading / carousel VAT fraud) trên NebulaGraph.

- **Cấu trúc thư mục & tổng quan dự án:** [`CAU_TRUC_DU_AN.md`](CAU_TRUC_DU_AN.md) — đọc trước file này
- **Kế hoạch tổng thể (kiến trúc, Data Contract):** [`full_invoice_86/KE_HOACH_TONG_THE_PIPELINE_LONG_VONG.md`](../full_invoice_86/KE_HOACH_TONG_THE_PIPELINE_LONG_VONG.md)
- **Kế hoạch xây dựng pipeline + web:** [`KE_HOACH_XAY_DUNG_PIPELINE_VA_WEB.md`](KE_HOACH_XAY_DUNG_PIPELINE_VA_WEB.md)
- **Kho nghiên cứu / benchmark (giữ nguyên, không dùng để vận hành):** [`invoice_agg_graph/`](../invoice_agg_graph/)

---

## Chạy nhanh

```bash
cd detecting_cheat_by_nebula/pipeline

# Lần đầu (hoặc khi đổi dữ liệu nguồn): đọc CSV → tạo schema → nạp → quét → phát hiện → báo cáo
python3 run_all.py --all

# Dữ liệu đã nạp sẵn trong Nebula, chỉ chạy lại phát hiện
python3 run_all.py

# Tuỳ chỉnh
python3 run_all.py --from 202101 --to 202112 --hops 3 --method dfs
python3 run_all.py --rebuild          # xoá space rồi tạo lại (mất dữ liệu cũ)
```

Kết quả nằm trong `output/runs/<runId>/`:

| File | Nội dung |
|---|---|
| `report.txt` | Báo cáo chữ: tổng quan, cảnh báo trần điểm, top chu trình, top doanh nghiệp |
| `top.json` | Cùng nội dung, dạng máy đọc — giao diện web dùng file này |
| `cycles.ngql` | Câu lệnh nGQL dựng sẵn, dán thẳng vào Nebula Studio để vẽ |
| `graph_risk_flags.jsonl` | Toàn bộ chu trình đã chấm điểm (1 dòng/chu trình) |
| `validation.json` | Kết quả quét Data Contract |
| `progress.log` | Toàn bộ log tiến trình |
| `meta.json` | Tham số + thời gian + số liệu tóm tắt |

---

## Cấu trúc

Xem đầy đủ (cây thư mục, vai trò từng phần, "raw/ cần gì", vì sao `data/` không
phải nguồn phân tích) tại **[`CAU_TRUC_DU_AN.md`](CAU_TRUC_DU_AN.md)**. Tóm tắt:

```
detecting_cheat_by_nebula/
├── raw/<bộ>/     dữ liệu gốc: company.csv, invoice.csv (KHÔNG có header) + script.py + file Excel — mỗi bộ 1 thư mục con
├── data/         dữ liệu đã chuẩn hoá: companies.csv, trades.csv, shares_address.csv
├── schemas/      detecting_cheat_by_nebula.ngql — khuôn CREATE SPACE/TAG/EDGE/INDEX
├── pipeline/     7 script Python + datasources.json
├── output/runs/  mỗi lần chạy 1 thư mục
└── archive_truoc_pipeline/   tài liệu/rác từ giai đoạn nebula-importer cũ, không dùng để vận hành
```

### Các script

| Script | Việc |
|---|---|
| `progress.py` | Giao thức phát tiến trình `[[STEP]]` / `[[LOG]]` / `[[DONE]]` dùng chung |
| `nebula_client.py` | Kết nối Nebula + helper dùng chung (1 nơi duy nhất đọc cấu hình) |
| `ingest_csv86.py` | Đọc `raw/<bộ>/*.csv` (bộ chọn qua biến `DATASET`) → gộp hoá đơn thành cạnh theo kỳ → `data/*.csv` |
| `load_schema.py` | Tạo space / tag / edge / index từ `schemas/detecting_cheat_by_nebula.ngql` |
| `sync_graph.py` | Nạp `data/*.csv` vào Nebula theo lô |
| `validate_contract.py` | Quét space, đối chiếu Data Contract → checklist + **trần điểm** |
| `detect_circular_trading.py` | 4 bước lõi: khoanh vùng → dò chu trình → khử trùng lặp → chấm điểm |
| `build_report.py` | `.jsonl` → `report.txt` + `top.json` + `cycles.ngql` |
| `run_all.py` | Điều phối toàn bộ, tạo thư mục run, ghi `meta.json` |

`datasources.json` là **manifest** điều khiển cả giao diện web lẫn validator: khai
báo các loại truy vấn gian lận và các cách nhập dữ liệu. Thêm loại mới = sửa JSON
+ viết script, **không phải sửa React**.

---

## Số liệu đã kiểm chứng (01/08/2026, 98 công ty Hà Nội / 8.976 hoá đơn)

| Bước | Kết quả |
|---|---|
| Gộp cạnh | 8.976 hoá đơn → **7.945 cạnh** TRADES (giảm 1,1 lần; loại 98 dòng tự bán cho mình) |
| Khoanh vùng | 98 công ty → 95 seed (chỉ loại được 3% — đồ thị rất dày) |
| Dò chu trình (5 chặng) | 2.581 lượt → **2.429 chu trình** duy nhất, ~15 giây |
| Chấm điểm | **1.074 cờ đỏ** (≥60đ), 1.355 theo dõi (40-60đ) |
| Trần điểm | **60/100** — thiếu ĐKKD nên mất 25đ liên kết ngầm + 15đ thành viên rủi ro |

Đối chứng trên `tax_graph` (bộ mô phỏng có đủ ĐKKD): trần điểm **100/100**, điểm
cao nhất **90,0** — cùng một mã nguồn, không sửa dòng nào.

---

## Ba cạm bẫy đã gặp thật, đừng lặp lại

### 1. nGQL không hiểu comment `--`
Chỉ chấp nhận `//`, `#`, `/* */`. Dùng `--` (kiểu SQL) sẽ báo ``syntax error near `--'``,
kể cả khi nó nằm cuối dòng giữa câu lệnh. `load_schema.py` gỡ comment trước khi gửi.

### 2. Chuỗi hop nối tiếp làm **chết** graphd, dù đã neo hết id()
Câu tưởng an toàn này đã OOM-kill graphd (exit 137) ngay lần chạy đầu trên vòng 5 chặng:

```ngql
MATCH p=(c0)-[:TRADES]->(c1)-...->(c4)-[:TRADES]->(c0)
WHERE id(c0)=="..." AND id(c1)=="..." AND ...   -- neo đủ cả 5 đỉnh
```

Bộ lập kế hoạch **mở rộng cạnh trước rồi mới lọc id**, mà đỉnh hub có tới 158 cạnh
đi ra → nổ tổ hợp qua 5 chặng. Dạng an toàn duy nhất (đã đo: **0,04 giây**):

```ngql
MATCH (a:Company)-[e:TRADES]->(b:Company)
WHERE (id(a)=="A" AND id(b)=="B" AND rank(e)==202111)
   OR (id(a)=="B" AND id(b)=="C" AND rank(e)==202112)
   ...
RETURN a, e, b;
```

Mỗi chặng chỉ 1 bước mở rộng với **cả hai đầu đã neo** → không thể nổ tổ hợp.
`build_report.py` sinh đúng dạng này.

### 3. Ngưỡng cắt nhánh phải suy từ dữ liệu có thật, không được hard-code
Nếu coi "liên kết ngầm + thành viên rủi ro" luôn có thể đạt được thì ngưỡng cắt
nhánh = 60−10−40 = **10**, quá lỏng → DFS chạy **quá 5 phút chưa xong**.
Vì cả space `detecting_cheat_by_nebula` không có một cặp liên kết ngầm nào, trừ hẳn 40 điểm đó ra
khỏi cận trên vẫn **chính xác tuyệt đối** (không mất chu trình nào) và cho ngưỡng
= **50** → chạy hết **15 giây**. Cùng kết quả, nhanh hơn ~20 lần.

Bản cũ đạt hiệu ứng này bằng cách hard-code `W_RISKY = 0` — đúng cho `detecting_cheat_by_nebula`
nhưng **sai cho space có đủ ĐKKD** (sẽ cắt mất chu trình thật). Bản hiện tại tự dò
dữ liệu nên đúng cho mọi space.

---

## Yêu cầu môi trường

- NebulaGraph v3.8.0 đang chạy (`docker compose up -d` trong `nebula_demo/`)
- Python 3.9+ với `nebula3-python` và `pandas`

Biến môi trường (đều có mặc định): `SPACE`, `DATASET` (tên bộ trong `raw/<bộ>/`,
mặc định `hanoi_98cty`), `NEBULA_HOST`, `NEBULA_PORT`, `NEBULA_USER`, `NEBULA_PASSWORD`.

Nếu graphd bị OOM-kill: `docker start nebula-graphd`, chờ ~40 giây rồi chạy lại.
