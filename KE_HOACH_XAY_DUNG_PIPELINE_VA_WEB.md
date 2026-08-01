# KẾ HOẠCH — Đưa pipeline lòng vòng về `detecting_cheat_by_nebula/` và biến `nebula_demo` thành Console phát hiện gian lận

> ## ✅ ĐÃ TRIỂN KHAI XONG — 01/08/2026
>
> Cả 4 pha đã hoàn thành và nghiệm thu (20/20 test đạt). Tài liệu sử dụng:
> - Pipeline (CLI): [`README.md`](README.md)
> - Giao diện web: [`HUONG_DAN_SU_DUNG_WEB.md`](HUONG_DAN_SU_DUNG_WEB.md)
>
> **Khác biệt so với kế hoạch ban đầu** (đều phát sinh từ lỗi gặp thật khi chạy):
>
> | # | Kế hoạch ban đầu | Thực tế đã làm | Vì sao đổi |
> |---|---|---|---|
> | 1 | `detect` đọc adjacency từ `data/trades.csv` | Đọc thẳng từ Space trong Nebula | Chọn space `tax_graph` trên web mà đọc CSV của `detecting_cheat_by_nebula` sẽ phân tích **nhầm dữ liệu mà không báo lỗi** |
> | 2 | Giữ `score_risky = 0` như bản cũ | Tự dò dữ liệu có thật rồi chấm đủ 5 tín hiệu | Cùng mã nguồn chạy đúng cả `detecting_cheat_by_nebula` (trần 60) lẫn `tax_graph` (trần 100, đạt 90) |
> | 3 | Ngưỡng cắt nhánh cố định | Suy từ dữ liệu thật lúc chạy | Để cố định 10 thì DFS chạy **quá 5 phút**; suy ra 50 thì hết **15 giây**, cùng kết quả |
> | 4 | Vẽ chu trình bằng chuỗi hop nối tiếp có neo `id()` | Dạng **một chặng, neo cả hai đầu, ghim `rank`** | Dạng cũ **làm chết graphd** (OOM-kill) dù đã neo đủ 5 đỉnh |
> | 5 | 8 endpoint | 10 endpoint (thêm `/stop`, `/runs`) | Cần hủy giữa chừng và liệt kê lần chạy |
> | 6 | — | `run_id` của Go dùng luôn làm tên thư mục kết quả | Registry nằm trong RAM, restart là mất hết báo cáo cũ |
>
> **Lỗi đã phát hiện và sửa trong quá trình xây dựng:**
> - nGQL không hiểu comment `--` (chỉ `//`, `#`, `/* */`) — sửa cả parser schema lẫn file `cycles.ngql` sinh ra
> - `dedupe()` xoay `members` mà không xoay `periods`/`amounts` → **122/318 chu trình lệch** trên đường `METHOD=match`
>   (đường `dfs` không lộ ra vì mẹo Johnson khiến `members[0]` vốn đã là MST nhỏ nhất). Điểm số vẫn đúng,
>   nhưng câu nGQL ghim sai kỳ sẽ vẽ ra vòng thiếu cạnh mà không báo lỗi gì
> - `total_amount` trả về kiểu `int` ở space này, `double` ở space kia → thêm hàm đọc số chịu được cả hai
> - `LOOKUP` bắt buộc có index; `MATCH ... WHERE e.period >= x` cũng vậy → đường lui phải neo Tag rồi lọc ở client
>
> ---

> **Ngày lập:** 01/08/2026
> **Phạm vi:** (A) dựng pipeline Python trong `detecting_cheat_by_nebula/`; (B) nâng cấp web `nebula_demo` từ "chạy query" thành "console truy vấn gian lận đầu-cuối".
> **Nguồn tham chiếu:** `full_invoice_86/KE_HOACH_TONG_THE_PIPELINE_LONG_VONG.md` (kiến trúc 5 lớp + Data Contract mục 4), `tax_graph/pipeline/*` (mẫu pipeline), `invoice_agg_graph/*` (bản chạy thật hiện tại).

---

## 0. Hiện trạng đã khảo sát (số liệu THẬT, đo ngày 01/08/2026)

### 0.1 Môi trường máy hiện tại (macOS)

| Thành phần | Trạng thái | Ghi chú |
|---|---|---|
| NebulaGraph v3.8.0 | ✅ **Đang chạy** (Docker) | `nebula-graphd` :9669, `nebula-storaged0` :9779, `nebula-metad0` :9559 (unhealthy nhưng vẫn phục vụ), `nebula-studio` :7001 |
| Space có sẵn | ✅ 5 space | `basketballplayer`, `invoice_agg_graph`, `invoice_graph`, `social_commerce_graph`, `tax_graph` |
| Go | ✅ `go1.26.5 darwin/arm64` | build lại backend được |
| Server Go | ✅ **Đang chạy** :8080 | phải kill trước khi rebuild |
| Python3 + `nebula3` + `pandas` | ✅ `/usr/bin/python3`, pandas 2.3.3 | chạy pipeline được ngay |
| **Node / npm** | ❌ **CHƯA CÓ** | `frontend/dist` là bản build sẵn từ Windows. **Không sửa được frontend cho tới khi cài Node.** Có Homebrew → `brew install node` |

### 0.2 Hiệu năng pipeline hiện tại (đo thật trên `invoice_agg_graph`, 98 công ty / 8.024 cạnh TRADES)

| Cấu hình | Thời gian | Chu trình duy nhất | Cờ đỏ (≥60) | Theo dõi (40-60) |
|---|---|---|---|---|
| DFS, 3 hop, kỳ 202001-202112 | **2,9 giây** | 348 | 99 | 249 |
| DFS, 5 hop, kỳ 202001-202112 | **16,1 giây** | 2.429 | **1.074** | 1.355 |

> **Hệ quả thiết kế:** 16 giây là **đủ ngắn để chạy trực tiếp** trong 1 request, nhưng **đủ dài để cần hiển thị tiến trình** (đúng yêu cầu của anh). Và khi đổi sang bộ NhómACD (~3.900 MST) thời gian sẽ tăng nhiều bậc → **thiết kế bắt buộc phải là chạy nền + stream tiến trình**, không được chạy đồng bộ chặn request.

### 0.3 Trần điểm 60/100 — sẽ được surface lên UI

Điểm cao nhất tìm được luôn là **60,0** vì `score_hidden_link` (25đ) và `score_risky_member` (15đ) luôn = 0 do thiếu dữ liệu ĐKKD (mục 4.2 Data Contract). Đây chính là thứ **bước "quét kiểm tra dữ liệu"** trên web sẽ báo cho người dùng TRƯỚC KHI chạy.

### 0.4 Cấu trúc web hiện tại (điểm chèn đã xác định chính xác)

```
main.go              → 6 route: / (static), /api/spaces, /api/query, /api/ai/{chat,insights,config}
App.jsx (300)        → state: spaces, selectedSpace, query, graphData, metrics, activeTab('graph'|'table')
                       handleRunQuery(q) → POST /api/query → setGraphData/setMetrics/setTableData
Header.jsx (77)      → <select> chọn space (dòng 53-65)
LeftConsole.jsx(603) → 4 tab: editor|presets|ai|scenario  (state `leftTab`, dòng 110)
                       • nút tab thêm sau dòng 277 | • panel thêm sau dòng 599
GraphCanvas.jsx(516) → nhận graphData {nodes,edges}; MÀU node lấy DUY NHẤT từ node.group (dòng 57-80)
                       ⚠ KHÔNG có hook tô màu riêng từng node → cần sửa nhỏ để highlight cờ đỏ
TableView / ElementInspector / ScenarioNotebook — không đụng tới
```

**Schema `graphData` (do Go `parser.go` sinh, phải giữ đúng):**
- node: `{ id, label, group, properties }` — GraphCanvas chỉ đọc `id`, `label`, `group`
- edge: `{ id, from, to, label, properties }`

---

## 1. Mục tiêu

| # | Yêu cầu của anh | Cách đáp ứng |
|---|---|---|
| 1 | Dựng luồng pipeline trong `detecting_cheat_by_nebula/` bằng file .py như `tax_graph/` | Phần A — 7 script Python, chạy được độc lập bằng CLI |
| 2a | Đầu vào import dữ liệu: hiện yêu cầu dữ liệu + tùy chọn nhập, mỗi tùy chọn 1 script đồng bộ | Manifest `datasources.json` + 3 script adapter (`ingest_*.py`) |
| 2b | Chọn space + chọn loại truy vấn gian lận | Endpoint `/api/fraud/querytypes` + bước 2 của wizard |
| 2c | Tự động quét xem dữ liệu hợp lệ chưa | Script `validate_contract.py` → checklist + cảnh báo trần điểm |
| 2d | Tự động hóa luồng, hiện tiến trình đang làm | Go spawn subprocess + **SSE** stream 4 bước + log |
| 2e | Preview file txt kết quả + top công ty nghi ngờ cao nhất | `build_report.py` sinh `report.txt` + tab "Báo cáo" ở giữa |
| 2f | Trực quan hóa chu trình lên đồ thị Nebula | Sinh nGQL → gọi lại `/api/query` có sẵn → GraphCanvas (+ hook highlight) |

**Nguyên tắc bất biến:**
1. **Không đụng dữ liệu/thư mục cũ.** `invoice_agg_graph/` giữ nguyên làm kho nghiên cứu & benchmark. `detecting_cheat_by_nebula/` thành nhà chính thức của pipeline vận hành.
2. **Python là nguồn chân lý duy nhất của thuật toán.** Go chỉ điều phối + stream, tuyệt đối không viết lại logic chấm điểm bằng Go (tránh 2 bản công thức lệch nhau).
3. **Mọi bước phải chạy được bằng CLI trước khi lên web.** Web chỉ là lớp vỏ gọi đúng những lệnh đó.
4. **Không bịa dữ liệu.** Thiếu ĐKKD thì báo thiếu và nói rõ mất bao nhiêu điểm, không suy diễn giả.

---

## 2. PHẦN A — Pipeline trong `detecting_cheat_by_nebula/`

### 2.1 Cấu trúc thư mục đề xuất

```
detecting_cheat_by_nebula/
├── raw/                              ← dữ liệu gốc (DI CHUYỂN file đang nằm ở gốc vào đây)
│   ├── company.csv                       98 công ty (không header)
│   ├── invoice.csv                       8.976 hóa đơn (không header)
│   └── Mua vào bán ra 86 công ty.xlsx
│
├── data/                             ← dữ liệu đã chuẩn hóa (OUTPUT của bước ingest)
│   ├── companies.csv                     mst,name,sector,address,revenue,report_date
│   ├── trades.csv                        seller_mst,buyer_mst,period,invoice_count,total_amount,total_vat,first_date,last_date
│   └── shares_address.csv                company_a,company_b,norm_addr
│
├── schemas/
│   └── detecting_cheat_by_nebula.ngql                   CREATE SPACE/TAG/EDGE + INDEX
│
├── pipeline/
│   ├── datasources.json              ← MANIFEST: yêu cầu dữ liệu + tùy chọn nhập + loại truy vấn
│   ├── ingest_csv86.py               ← [Tùy chọn 1] cặp CSV chuẩn detecting_cheat_by_nebula → data/*.csv
│   ├── ingest_xlsx_nhomacd.py        ← [Tùy chọn 2] bộ xlsx bàn giao NhómACD → data/*.csv
│   ├── ingest_trino_gotix.py         ← [Tùy chọn 3] khung sẵn, chưa nối được (Gotix domain còn scaffold)
│   ├── load_schema.py                    tạo space/tag/edge (idempotent)
│   ├── sync_graph.py                     data/*.csv → INSERT VERTEX/EDGE
│   ├── validate_contract.py          ← MỚI: quét Data Contract → JSON checklist
│   ├── detect_circular_trading.py        4 bước lõi (bê từ invoice_agg_graph + thêm emit tiến trình)
│   ├── build_report.py               ← MỚI: jsonl → report.txt + top.json + cycles.ngql
│   ├── progress.py                   ← MỚI: helper emit [[STEP]]/[[LOG]] chuẩn
│   └── run_all.py                    ← MỚI: điều phối chạy tuần tự (ingest→schema→sync→validate→detect→report)
│
├── output/
│   └── runs/<runId>/                     mỗi lần chạy 1 thư mục riêng
│       ├── meta.json                     tham số + thời gian + trạng thái
│       ├── progress.log                  toàn bộ dòng tiến trình (để xem lại)
│       ├── graph_risk_flags.jsonl        kết quả thô đầy đủ
│       ├── report.txt                    ← BẢN PREVIEW cho web
│       ├── top.json                      top công ty/chu trình nghi vấn (cho UI)
│       └── cycles.ngql                   câu lệnh nGQL dựng sẵn để visualize
│
└── README.md                             cách chạy bằng CLI (không cần web)
```

> **Về tên space:** giữ nguyên `invoice_agg_graph` làm mặc định (dữ liệu đã nạp, đang chạy, tài liệu demo đang trỏ tới) — cấu hình qua biến `SPACE`, không phải hardcode. Tránh nạp trùng dữ liệu sang space mới chỉ vì đổi tên thư mục.

### 2.2 Giao thức tiến trình (`progress.py`) — trái tim của phần "hiện process"

Python in ra stdout 2 loại dòng, Go parse dòng bắt đầu bằng `[[`:

```
[[STEP]] {"n":1,"of":4,"name":"Khoanh vùng seed","status":"running"}
[[LOG]]  Đọc trades.csv: 8.024 cạnh trong kỳ 202001-202112
[[STEP]] {"n":1,"of":4,"status":"done","ms":120,"metric":{"seeds":95,"pruned_pct":3}}
[[STEP]] {"n":2,"of":4,"name":"Dò chu trình (DFS)","status":"running"}
[[LOG]]  ... 1.200/2.581 chu trình
[[STEP]] {"n":2,"of":4,"status":"done","ms":14200,"metric":{"raw_cycles":2581}}
[[STEP]] {"n":3,"of":4,"name":"Khử trùng lặp","status":"done","metric":{"unique":2429}}
[[STEP]] {"n":4,"of":4,"name":"Chấm điểm","status":"done","metric":{"red":1074,"watch":1355}}
[[DONE]] {"runId":"...","report":"report.txt","red":1074}
[[ERROR]] {"step":2,"msg":"..."}
```

Dòng thường (không có `[[`) → forward nguyên văn thành log. **Ưu điểm:** script vẫn chạy đẹp bằng CLI cho người đọc, đồng thời máy parse được — không cần 2 chế độ output.

### 2.3 `validate_contract.py` — quét dữ liệu hợp lệ (thành phần giá trị nhất)

Đối chiếu space đang chọn với Data Contract mục 4 của kế hoạch tổng thể. Trả JSON:

```json
{
  "space": "invoice_agg_graph",
  "query_type": "circular_trading",
  "can_run": true,
  "max_achievable_score": 60,
  "headline": "Chạy được — nhưng TRẦN ĐIỂM chỉ 60/100 vì thiếu dữ liệu ĐKKD (mất 40 điểm)",
  "checks": [
    {"id":"4.1.tag_company","label":"Tag Company","status":"pass","detail":"98 đỉnh"},
    {"id":"4.1.edge_trades","label":"Edge TRADES + thuộc tính bắt buộc","status":"pass","detail":"8.024 cạnh; đủ 6/6 thuộc tính"},
    {"id":"4.1.rank_period","label":"rank(TRADES) == period (yyyymm)","status":"pass","detail":"kỳ 202001→202112"},
    {"id":"4.1.index","label":"Index idx_trades_period","status":"pass"},
    {"id":"4.2.legal_rep","label":"ĐKKD — người đại diện (LEGAL_REP_OF)","status":"missing","impact_points":25,
     "impact":"score_hidden_link luôn = 0","fix":"cần bảng ĐKKD, xem mục 4.2 kế hoạch tổng thể"},
    {"id":"4.2.owns","label":"ĐKKD — sở hữu vốn (OWNS)","status":"missing","impact_points":0,
     "impact":"gộp chung 25đ ở trên"},
    {"id":"4.2.shares_address","label":"Địa chỉ chung (SHARES_ADDRESS)","status":"empty","impact_points":0,
     "detail":"có edge type nhưng 0 cạnh — 98 công ty không ai trùng địa chỉ (đã fuzzy-match 70-90%)"},
    {"id":"4.2.status_date","label":"ĐKKD — ngày thành lập / trạng thái","status":"missing","impact_points":15,
     "impact":"score_risky_member luôn = 0"},
    {"id":"4.3.price","label":"[Lớp 3, tùy chọn] Đơn giá / mã ngành","status":"skipped","detail":"Lớp 3 chưa bật"}
  ]
}
```

Ba mức: `pass` / `empty` (có cấu trúc, không có dữ liệu) / `missing` (không có cấu trúc). `can_run=false` chỉ khi thiếu thứ ở nhóm 4.1 (bắt buộc).

### 2.4 `datasources.json` — manifest điều khiển cả UI lẫn validator

Một file duy nhất mô tả: có những loại truy vấn gian lận nào, mỗi loại cần dữ liệu gì, và có những cách nhập dữ liệu nào. UI đọc file này để render, **không hardcode trong React** → thêm loại truy vấn mới sau này chỉ cần sửa JSON + viết script.

```json
{
  "query_types": [
    { "id": "circular_trading", "name": "Mua bán lòng vòng (Circular Trading)", "status": "available",
      "script": "detect_circular_trading.py",
      "params": [
        {"id":"period_from","label":"Kỳ từ (yyyymm)","type":"int","default":202001},
        {"id":"period_to","label":"Kỳ đến (yyyymm)","type":"int","default":202112},
        {"id":"max_hops","label":"Số chặng tối đa","type":"select","options":[3,4,5],"default":5,
         "hint":"3 chặng ~3 giây · 5 chặng ~16 giây (đo trên 98 công ty)"},
        {"id":"method","label":"Phương pháp","type":"select","options":["dfs","match"],"default":"dfs",
         "hint":"dfs = quét đầy đủ, không cắt cụt · match = truy vấn thuần Nebula, có giới hạn/seed"}
      ],
      "requires": ["4.1.tag_company","4.1.edge_trades","4.1.rank_period"],
      "optional":  ["4.2.legal_rep","4.2.owns","4.2.shares_address","4.2.status_date"] },
    { "id": "shell_company",  "name": "Doanh nghiệp ma / hóa đơn khống", "status": "coming_soon" },
    { "id": "shared_identity","name": "Trùng định danh (CCCD/SĐT/địa chỉ)", "status": "coming_soon" },
    { "id": "price_anomaly",  "name": "Bất thường đơn giá (Lớp 3)",        "status": "coming_soon" }
  ],
  "datasources": [
    { "id":"csv86", "name":"Cặp CSV chuẩn detecting_cheat_by_nebula", "status":"available", "script":"ingest_csv86.py",
      "inputs":[
        {"name":"company.csv","required":true,
         "columns":["mst","tên công ty","lĩnh vực","địa chỉ","doanh thu","năm báo cáo"],
         "note":"KHÔNG có dòng header; địa chỉ có dấu phẩy phải bọc trong ngoặc kép"},
        {"name":"invoice.csv","required":true,
         "columns":["so_hoa_don","ngay_xuat (yyyy-mm-dd)","mst_nguon (bên bán)","mst_dich (bên mua)","mo_ta","tien_chua_thue","thue_gtgt","loai_gd","nhan_ai","rank"],
         "note":"KHÔNG có header; so_hoa_don KHÔNG unique toàn cục — khóa thật là cột rank"}
      ]},
    { "id":"local_existing", "name":"Dùng dữ liệu đã có sẵn trong detecting_cheat_by_nebula/raw", "status":"available",
      "script":"ingest_csv86.py", "inputs":[] },
    { "id":"xlsx_nhomacd", "name":"Bộ xlsx bàn giao NhómACD (HDBan/HDMua/HDBanMTT/HDMuaMTT)", "status":"planned",
      "script":"ingest_xlsx_nhomacd.py",
      "note":"11.444 file / 8,7GB / 3.819-3.913 MST — xem full_invoice_86/DATA_CONTRACT_BANGIAO_NHOMACD.md" },
    { "id":"trino_gotix", "name":"Kết nối Trino / Gotix lakehouse", "status":"planned",
      "script":"ingest_trino_gotix.py",
      "note":"Chờ domain einvoice trong Gotix hết scaffold — xem detecting_cheat_by_nebula/nebula_in_gotix.md" }
  ]
}
```

### 2.5 `build_report.py` — sinh file preview

Đọc `graph_risk_flags.jsonl`, sinh 3 thứ:

1. **`report.txt`** — bản người đọc:
```
================================================================
BÁO CÁO PHÁT HIỆN MUA BÁN LÒNG VÒNG
Space: invoice_agg_graph | Kỳ: 202001 - 202112 | Chặng tối đa: 5 | Phương pháp: dfs
Chạy lúc: 2026-08-01 14:32:10 | Thời gian: 16,1 giây
================================================================

TỔNG QUAN
  Chu trình duy nhất tìm được : 2.429
  Cờ đỏ   (điểm >= 60)        : 1.074
  Theo dõi (40 <= điểm < 60)  : 1.355
  Bỏ qua  (điểm < 40)         :     0

⚠ CẢNH BÁO TRẦN ĐIỂM: bộ dữ liệu này thiếu ĐKKD → điểm tối đa đạt được là
  60/100 (mất 25đ liên kết ngầm + 15đ DN rủi ro). Chi tiết: mục 4.2 Data Contract.

TOP 20 CHU TRÌNH ĐIỂM CAO NHẤT
 #   Điểm  Chặng  Thành viên (MST → tên)                          Kỳ
 1   60.0    3    0102159423 CÔNG TY ... → 0108831225 ... → ...   202111-202112
 ...

TOP 20 CÔNG TY XUẤT HIỆN TRONG NHIỀU CỜ ĐỎ NHẤT
 #   MST         Tên                              Số cờ đỏ  Điểm cao nhất
 1   0104976614  CÔNG TY ...                          87        60.0
 ...
```

2. **`top.json`** — cùng nội dung, dạng máy đọc, cho UI render bảng + nút "Xem trên đồ thị".

3. **`cycles.ngql`** — câu lệnh dựng sẵn (như file `show_flagged_cycles.ngql` đã làm hôm qua).

> **Bảng "TOP công ty xuất hiện trong nhiều cờ đỏ nhất"** chính là phần "hub indices" đã duyệt trong kế hoạch tổng thể mục 2.2 — đếm số lần một MST nằm trong chu trình cờ đỏ. Rẻ (đếm trên kết quả có sẵn), không phải Betweenness Centrality thật.

---

## 3. PHẦN B — Web: từ "chạy query" thành "Console phát hiện gian lận"

### 3.1 API mới (Go)

| Endpoint | Method | Vào | Ra |
|---|---|---|---|
| `/api/fraud/manifest` | GET | — | Nội dung `datasources.json` |
| `/api/fraud/validate` | POST | `{space, query_type}` | JSON checklist ở mục 2.3 |
| `/api/fraud/import` | POST (multipart) | `{datasource_id, files[]}` | `{runId}` → stream qua `/api/fraud/stream` |
| `/api/fraud/run` | POST | `{space, query_type, params{}}` | `{runId}` (trả ngay, chạy nền) |
| `/api/fraud/stream?runId=` | GET (**SSE**) | — | event `step` / `log` / `done` / `error` |
| `/api/fraud/result?runId=` | GET | — | `top.json` + tóm tắt + đường dẫn file |
| `/api/fraud/report?runId=` | GET | — | `report.txt` (text/plain) |
| `/api/fraud/cycle-ngql` | POST | `{members:[mst...]}` | `{query}` — câu nGQL để visualize |

**Thiết kế runner (`internal/services/pipeline_runner.go`):**
- `exec.CommandContext(ctx, "python3", scriptPath, ...)` — **mảng đối số cố định, không dựng chuỗi shell**; tham số truyền qua biến môi trường, đã validate kiểu.
- Quét `space` phải nằm trong danh sách `SHOW SPACES` thật → chặn injection.
- Mỗi run có `runId` + thư mục riêng; registry in-memory `map[runId]*Run` giữ trạng thái + ring-buffer log để client kết nối muộn vẫn xem lại được từ đầu.
- Timeout cứng (mặc định 10 phút) + nút Hủy (`ctx.Cancel`).
- Song song tối đa 1 run/space để không nghẽn Nebula.

### 3.2 Frontend

**Chuyển chế độ ở Header** — thêm 2 nút bên cạnh dropdown space:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ NebulaGraph Console   [Truy vấn nGQL] [🛡 Phát hiện gian lận]   Space:[▾] │
└──────────────────────────────────────────────────────────────────────────┘
```

State mới ở `App.jsx`: `appMode: 'query' | 'fraud'`. Khi `fraud`, panel trái render `<FraudConsole/>` thay cho `<LeftConsole/>`; panel giữa thêm tab thứ 3.

**`FraudConsole.jsx` — wizard 5 bước (panel trái):**

```
┌─ 🛡 PHÁT HIỆN GIAN LẬN ─────────────────┐
│                                          │
│ ● 1. NGUỒN DỮ LIỆU              [✓]     │
│   ┌────────────────────────────────┐    │
│   │ ▸ Yêu cầu dữ liệu  (bung ra)   │    │
│   │   • company.csv: 6 cột...      │    │
│   │   • invoice.csv: 10 cột...     │    │
│   └────────────────────────────────┘    │
│   ○ Dùng dữ liệu có sẵn (detecting_cheat_by_nebula)    │
│   ○ Tải lên cặp CSV chuẩn      [Chọn]   │
│   ○ Bộ xlsx NhómACD          (sắp có)   │
│   ○ Trino / Gotix            (sắp có)   │
│                        [ Nhập dữ liệu ] │
│                                          │
│ ● 2. KHÔNG GIAN & LOẠI TRUY VẤN  [✓]    │
│   Space:  [invoice_agg_graph      ▾]    │
│   Loại:   [Mua bán lòng vòng      ▾]    │
│           (3 loại khác: sắp có)          │
│   Kỳ từ [202001] đến [202112]           │
│   Chặng [5 ▾]  ~16 giây                 │
│                                          │
│ ● 3. KIỂM TRA DỮ LIỆU            [!]    │
│   ⚠ Chạy được — TRẦN ĐIỂM 60/100        │
│   ✓ Tag Company              98 đỉnh    │
│   ✓ Edge TRADES           8.024 cạnh    │
│   ✓ rank == period      202001-202112   │
│   ✗ ĐKKD người đại diện        −25 đ    │
│   ⊘ Địa chỉ chung        0 cạnh (−0đ)   │
│   ✗ Ngày TL / trạng thái       −15 đ    │
│                      [ Chạy phát hiện ] │
│                                          │
│ ● 4. TIẾN TRÌNH                          │
│   ▓▓▓▓▓▓▓▓▓▓░░░░  Bước 2/4              │
│   ✓ 1 Khoanh vùng seed   95 seed  0,1s  │
│   ⟳ 2 Dò chu trình (DFS)  1.200...      │
│   ○ 3 Khử trùng lặp                     │
│   ○ 4 Chấm điểm                         │
│   ┌─ log ──────────────────────────┐    │
│   │ [detect] PHUONG PHAP: DFS...   │    │
│   └────────────────────────────────┘    │
│                            [ Hủy ]       │
│                                          │
│ ● 5. KẾT QUẢ                     [✓]    │
│   Cờ đỏ 1.074 · Theo dõi 1.355          │
│   [ Xem báo cáo ] [ Tải .jsonl ]        │
│   TOP CHU TRÌNH NGHI VẤN:               │
│   60.0  0102159423→0108831225→...  [👁] │
│   60.0  0101770848→0107658306→...  [👁] │
└──────────────────────────────────────────┘
```

**Tab thứ 3 ở panel giữa: `Báo cáo`** (`FraudReportView.jsx`)
- Trên: 4 thẻ số liệu (Chu trình / Cờ đỏ / Theo dõi / Thời gian)
- Giữa: 2 bảng — *Top chu trình theo điểm* và *Top công ty theo số cờ đỏ*, mỗi dòng có nút 👁 "Xem trên đồ thị"
- Dưới: `report.txt` dạng `<pre>` cuộn được + nút Copy/Tải

**Nút 👁 hoạt động thế nào:** gọi `/api/fraud/cycle-ngql` → nhận câu nGQL → gọi `handleRunQuery()` **có sẵn** → GraphCanvas render. Đúng đường đi đã được kiểm chứng, không viết engine vẽ mới.

**Sửa nhỏ GraphCanvas — thêm highlight (bắt buộc, ~12 dòng):**
Hiện màu node lấy DUY NHẤT từ `node.group` (dòng 57-80), không có đường tô riêng. Thêm 1 prop `highlightIds` (Set VID):
```js
// sau khối if/else chọn màu theo group (dòng ~64)
const hi = highlightIds?.has(String(n.id));
// trong object trả về (dòng ~68-79)
borderWidth: hi ? 4 : 2,
color: { background: color, border: hi ? '#dc2626' : '#ffffff', ... }
```
→ Thành viên chu trình cờ đỏ có viền đỏ dày, phân biệt ngay với các node lân cận. Không phá cách hoạt động cũ (`highlightIds` không truyền = như cũ).

### 3.3 File thay đổi / thêm mới

| File | Loại | Ghi chú |
|---|---|---|
| `nebula_demo/internal/handlers/fraud.go` | **mới** | 8 endpoint mục 3.1 |
| `nebula_demo/internal/services/pipeline_runner.go` | **mới** | spawn python3, parse `[[...]]`, registry run |
| `nebula_demo/internal/config/config.go` | sửa | thêm `PipelineDir`, `PythonBin` |
| `nebula_demo/main.go` | sửa | đăng ký 8 route mới |
| `frontend/src/App.jsx` | sửa | `appMode`, `fraudResult`, `highlightIds`, tab thứ 3 |
| `frontend/src/components/Header.jsx` | sửa | 2 nút chuyển chế độ |
| `frontend/src/components/GraphCanvas.jsx` | sửa nhỏ | prop `highlightIds` (~12 dòng) |
| `frontend/src/components/FraudConsole.jsx` | **mới** | wizard 5 bước |
| `frontend/src/components/FraudReportView.jsx` | **mới** | tab Báo cáo |
| `frontend/src/services/fraudApi.js` | **mới** | 8 hàm gọi API + client SSE |
| `LeftConsole / TableView / ElementInspector / ScenarioNotebook` | **không đụng** | |

---

## 4. Kiến trúc tổng thể sau khi xong

```
┌───────────────────────────────────────────────────────────────────────┐
│  TRÌNH DUYỆT — http://localhost:8080                                  │
│  [Truy vấn nGQL] ←→ [🛡 Phát hiện gian lận]                           │
│   FraudConsole (wizard 5 bước)  │  GraphCanvas │ TableView │ Báo cáo  │
└───────────────────────────────────────────────────────────────────────┘
        │ REST + SSE                            │ POST /api/query (đã có)
        ▼                                       ▼
┌───────────────────────────────────────────────────────────────────────┐
│  GO BACKEND (server.exe / go run main.go) :8080                       │
│   handlers/fraud.go ──► services/pipeline_runner.go                   │
│        │                    exec.Command("python3", ...)              │
│        │                    ├─ đọc stdout, parse [[STEP]]/[[LOG]]     │
│        │                    └─ đẩy SSE + ghi output/runs/<runId>/     │
│   handlers/query.go (đã có, không đổi) ──► db/nebula.go               │
└───────────────────────────────────────────────────────────────────────┘
        │ subprocess                            │ Thrift :9669
        ▼                                       ▼
┌────────────────────────────────┐   ┌──────────────────────────────────┐
│  PIPELINE PYTHON (detecting_cheat_by_nebula/) │   │  NebulaGraph v3.8.0 (Docker)     │
│  ingest → schema → sync →      │──►│  space invoice_agg_graph         │
│  validate → detect → report    │   │  Company / TRADES / SHARES_ADDR  │
└────────────────────────────────┘   └──────────────────────────────────┘
```

---

## 5. Kế hoạch theo pha

### P0 — Chuẩn bị môi trường (~10 phút) 🔴 CHẶN P3
| Việc | Tiêu chí xong |
|---|---|
| `brew install node` | `node -v` và `npm -v` chạy được |
| `cd frontend && npm install && npm run build` (bản chưa sửa) | `dist/` build lại thành công, web vẫn chạy như cũ |
| Kill server cũ, `go build -o server main.go` | Binary macOS build được (`server`, không phải `server.exe`) |

> **Nếu không cài được Node:** phương án dự phòng là làm giao diện gian lận bằng HTML/JS thuần trong `nebula_demo/public/` (đã có sẵn `app.js` 356 dòng làm mẫu) và phục vụ ở route riêng `/fraud`. Xấu hơn, không dùng lại được GraphCanvas — chỉ chọn nếu bắt buộc.

### P1 — Pipeline Python (chạy được bằng CLI, chưa cần web)
| Việc | Tiêu chí xong |
|---|---|
| Dựng cây thư mục, di chuyển raw data | `detecting_cheat_by_nebula/raw/*.csv` đúng chỗ, file gốc không mất |
| `progress.py` + `ingest_csv86.py` | `python3 ingest_csv86.py` sinh đủ 3 file `data/*.csv`, in `[[STEP]]` |
| `load_schema.py` + `sync_graph.py` | Nạp lại được vào space, đếm khớp 98 đỉnh / 8.024 cạnh |
| `validate_contract.py` | In JSON checklist đúng như mục 2.3, `max_achievable_score=60` |
| `detect_circular_trading.py` (+ emit tiến trình) | Ra đúng 2.429 chu trình / 1.074 cờ đỏ ở 5 hop — **khớp số đã đo** |
| `build_report.py` | Sinh `report.txt` + `top.json` + `cycles.ngql`; nGQL paste vào Nebula chạy được |
| `run_all.py` + `README.md` | 1 lệnh chạy hết đầu-cuối |

**Nghiệm thu P1:** chạy `python3 run_all.py` → ra thư mục `output/runs/<id>/` đủ 6 file, số liệu khớp bảng mục 0.2. Web chưa cần đụng tới.

### P2 — Backend Go
| Việc | Tiêu chí xong |
|---|---|
| `pipeline_runner.go` | `curl -N /api/fraud/stream?runId=` thấy tiến trình chảy theo thời gian thực |
| `fraud.go` (8 endpoint) | Test bằng `curl` từng cái, có case lỗi (space sai, thiếu file) |
| Đăng ký route + config | `go build` sạch, các route cũ không hỏng |

**Nghiệm thu P2:** chạy trọn 1 pipeline **chỉ bằng curl**, không cần frontend.

### P3 — Frontend
| Việc | Tiêu chí xong |
|---|---|
| `fraudApi.js` + client SSE | Console log thấy event chảy |
| `FraudConsole.jsx` wizard 5 bước | Bấm qua 5 bước ra kết quả thật |
| `FraudReportView.jsx` tab Báo cáo | 2 bảng top + preview `report.txt` |
| `GraphCanvas` prop `highlightIds` | Chế độ query cũ **không đổi gì**; chế độ gian lận có viền đỏ |
| `Header` + `App` chuyển chế độ | Đổi qua lại 2 chế độ không mất state |

### P4 — Tích hợp & tài liệu
| Việc | Tiêu chí xong |
|---|---|
| Chạy thật đầu-cuối 3 kịch bản (3/4/5 hop) | Số trên web khớp số CLI |
| Kiểm thử lỗi: space không hợp lệ, hủy giữa chừng, chạy 2 lần song song | Không treo, không crash Nebula |
| `detecting_cheat_by_nebula/README.md` + cập nhật `HUONG_DAN_VAN_HANH_MAC.md` | Người khác đọc là chạy được |

---

## 6. Rủi ro & cách xử lý

| # | Rủi ro | Mức | Cách xử lý |
|---|---|---|---|
| 1 | **Không có Node/npm** → không build được frontend | 🔴 Cao | P0 cài trước. Dự phòng: UI HTML thuần ở `/fraud` (mất GraphCanvas) |
| 2 | Spawn subprocess → lỗ hổng command injection | 🔴 Cao | Mảng đối số cố định (không qua shell); whitelist tên script từ manifest; validate `space` với `SHOW SPACES`; tham số ép kiểu int |
| 3 | Pipeline chạy lâu trên dữ liệu lớn (NhómACD 3.900 MST) | 🟠 TB | Chạy nền + runId + SSE (đã thiết kế); timeout cứng 10 phút; nút Hủy; giới hạn 1 run/space |
| 4 | Query đa chặng làm crash Nebula (đã xảy ra thật trên `invoice_graph`) | 🟠 TB | Nút 👁 **chỉ sinh chuỗi hop CỐ ĐỊNH có neo `id()`**, tuyệt đối không sinh `*2..5` — đúng cảnh báo trong `schemas/invoice_graph.md` |
| 5 | Sửa `GraphCanvas` làm hỏng chế độ query cũ | 🟡 Thấp | `highlightIds` là prop tùy chọn; không truyền = hành vi cũ y nguyên; test lại chế độ query trước khi bàn giao |
| 6 | Trùng lặp logic giữa `detecting_cheat_by_nebula/` và `invoice_agg_graph/` | 🟡 Thấp | `detecting_cheat_by_nebula/` là bản vận hành chính thức; thêm ghi chú ở `invoice_agg_graph/README` trỏ về; **không xóa** kho nghiên cứu/benchmark |
| 7 | Upload file lớn (xlsx 8,7GB) làm sập server | 🟡 Thấp | Giới hạn kích thước upload; nguồn NhómACD để trạng thái `planned`, khi làm sẽ đọc từ đường dẫn trên đĩa chứ không upload qua HTTP |
| 8 | `metad0` đang `unhealthy` | 🟡 Thấp | Hiện vẫn phục vụ bình thường; theo dõi, nếu nạp dữ liệu lỗi thì `docker compose restart` |

---

## 7. Những gì CỐ TÌNH KHÔNG làm ở giai đoạn này

1. **Không viết lại thuật toán bằng Go** — giữ Python là nguồn chân lý duy nhất.
2. **Không bật Lớp 1 (community detection)** — đã kiểm chứng mất 85,4% chu trình thật trên dữ liệu dày.
3. **Không làm 3 loại truy vấn gian lận còn lại** — để `coming_soon` trong manifest, khung đã sẵn.
4. **Không nối Trino/Gotix thật** — domain `einvoice` còn là scaffold rỗng; để script khung.
5. **Không tự bịa dữ liệu ĐKKD** để lấp 40 điểm — báo thiếu rõ ràng trên UI thay vì suy diễn giả.
6. **Không đụng `tax_graph/`, `invoice_agg_graph/`, `full_invoice_86/`** — chỉ thêm 1 dòng ghi chú trỏ đường.

---

## 8. Việc cần anh quyết trước khi bắt tay

| # | Câu hỏi | Đề xuất của tôi |
|---|---|---|
| 1 | Cho cài Node bằng Homebrew không? | **Nên** — không có thì không sửa được giao diện React |
| 2 | Space đích: giữ `invoice_agg_graph` hay tạo `detecting_cheat_by_nebula` mới? | **Giữ `invoice_agg_graph`** (dữ liệu đã nạp, tài liệu đang trỏ tới), cấu hình qua biến môi trường |
| 3 | Di chuyển `company.csv` / `invoice.csv` vào `detecting_cheat_by_nebula/raw/`? | **Nên** — tách rõ raw / data / output. Có thể giữ bản sao ở chỗ cũ nếu anh muốn chắc |
| 4 | Làm cả 4 pha một lượt, hay bàn giao từng pha? | **Từng pha** — P1 xong chạy thử CLI, duyệt rồi mới sang P2 |
