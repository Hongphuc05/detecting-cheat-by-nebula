# N4 — Báo cáo hoàn thành: Nâng data contract (sector thật + 3 cột rủi ro hiển thị)

> Đã code + kiểm chứng thật (chạy `ingest_trino_gotix.py` trên Trino thật, nạp vào space Nebula
> test, `DESCRIBE TAG`/`FETCH PROP`/`validate_contract.py` thật — không chỉ đọc code).
> Xem phân tích đầy đủ tại `N4_PHAN_TICH_YEU_CAU.md` cùng thư mục.

## 1. Phát hiện quan trọng nhất — premise của ticket đã lệch pha với thực tế

Trước khi code, đọc trực tiếp `ingest_trino_gotix.py` phát hiện: việc nối `sector` từ
`company_industry` (ticket mô tả là "chưa làm") **đã được viết từ 12/08/2026**, chỉ chưa từng
chạy thử trên Trino thật để xác nhận. Việc N4 làm cho phần này chuyển từ "viết code" sang
"kiểm chứng thật + đính chính 2 tài liệu đang lệch pha" (`BAO_CAO_TICH_HOP_GOTIX_NEBULA.md`,
`company/README.md`). Chi tiết đầy đủ ở mục 2 file phân tích.

Phát hiện thứ 2, còn quan trọng hơn cho việc chấm điểm: **điểm data contract đo THẬT hôm nay là
100/100**, không phải 60/100 như tên ticket. Xem mục 3.

## 2. Các quyết định tôi tự chốt (mục 7 tài liệu phân tích, đã duyệt với Phúc 18/08/2026)

| Câu hỏi mở | Đã chốt | Vì sao |
|---|---|---|
| Ứng viên #2 trong 3 cột rủi ro ban đầu (`TTHN-T2-D06-001`, tỷ lệ VAT) có dùng được không? | **Đổi sang `TTHN-T2-D07-002`** (Benford χ²) | Kiểm tra thật trên Trino: `D06-001` có **0 dòng** trong bảng tier3 (domain GTGT chưa bootstrap dữ liệu thật trong sandbox này) — không phải "nối được nhưng ít dữ liệu", mà là chưa tồn tại dòng nào. Đổi sang cột cùng nguồn `t2_invoice_risk` đã có dữ liệu thật. |
| 3 cột rủi ro có tính vào điểm 0-100 không? | **Không** — chỉ hiển thị thêm thuộc tính trên Company node | Ngôn ngữ ticket dùng "nối", không dùng "chấm điểm"; tính điểm buộc phải sửa `detect_circular_trading.py` (nguồn chân lý duy nhất của thuật toán) — rủi ro lệch bản gốc, không có cơ sở khách quan để tự đặt trọng số mới. Phân tích đánh đổi đầy đủ ở mục 3 file phân tích. |
| Nhánh/PR cho `detecting_cheat_by_nebula` | **Không tạo nhánh riêng**, sửa trực tiếp `main` | Chốt riêng với Phúc cho repo này (khác `gotix-datalake` — có tạo nhánh + PR) |

## 3. Điểm data contract — số liệu thật, không phải số trong tên ticket

Đã chạy `validate_contract.py` thật trên space Nebula test (`n4_test_company_risk`, nạp từ
`ingest_trino_gotix.py` sau khi sửa code, xoá space ngay sau khi đo):

```
Đủ dữ liệu — đạt được thang điểm đầy đủ 100/100
[v] * Tag Company                    350 đỉnh
[v] * Edge TRADES + thuộc tính       8.298 cạnh · đủ 4/4 thuộc tính bắt buộc
[v] * rank(TRADES) bằng period       khớp trên 500 cạnh mẫu · kỳ 202301-202604
[v]   Index TRADES(period)           có index idx_trades_period
[v]   ĐKKD — người đại diện pháp luật   86 cặp công ty chung người đại diện
[x]   ĐKKD — sở hữu vốn              Không có dữ liệu sở hữu vốn (ĐKKD)
[v]   Địa chỉ đăng ký trùng nhau     19 cạnh
[o]   Số điện thoại trụ sở trùng nhau  0 cạnh
[v]   ĐKKD — ngày thành lập/trạng thái  342 doanh nghiệp có established_date/status
```

**Kết luận quan trọng cho báo cáo chấm lại điểm (tiêu chí hoàn thành của ticket)**: điểm thật đo
được hôm nay là **100/100** — không phải 60/100. Cơ chế chấm điểm (`validate_contract.py`) chỉ
trừ điểm khi 1 trong 2 nhóm tín hiệu `hidden_link` (-25đ) hoặc `risky_member` (-15đ) **không có
nguồn nào pass** — `100 − 25 − 15 = 60`, khớp đúng con số trong tên ticket. Nhưng dữ liệu
`trino_gotix` hôm nay đã có `legal_rep` (86 cặp) và `status_date` (342/350 mst) đều **pass**, nên
không nhóm nào bị trừ. **3 cột rủi ro thuế/hoá đơn của N4 không nằm trong công thức chấm điểm
này** (theo quyết định mục 2) — nên KHÔNG phải lý do điểm đạt 100/100; điểm đã ở mức tối đa từ
trước khi N4 bắt đầu, nhờ 2 nguồn ĐKKD (`legal_rep`/`established_date`/`status`) đã có sẵn.

→ Việc N4 lần này **không nâng điểm** (vì không còn gì để nâng — đã tối đa), chỉ bổ sung thêm
3 thuộc tính hiển thị (`book_tax_gap`, `invoice_adjustment_rate`, `invoice_benford_chi2`) nằm
ngoài công thức chấm điểm. Mục còn thiếu duy nhất trong data contract hiện tại: `OWNS` (sở hữu
vốn) — **chưa có nguồn** trong Gotix lakehouse, không nằm trong phạm vi N4.

## 4. Thay đổi cụ thể

**`detecting_cheat_by_nebula/pipeline/ingest_trino_gotix.py`**:
- Thêm 2 CTE mới vào `SQL_COMPANIES`: `latest_tax_risk` (đọc
  `tier3.tax_declaration_gtgt_tndn_t2_feature_value`, lọc `feature_name='TTHN-T2-D08-002'`,
  lấy `fiscal_year` mới nhất/mst) và `latest_invoice_risk` (đọc
  `tier3.einvoice_invoice_risk_feature_value`, lọc 2 `feature_name` `D07-001`/`D07-002`, pivot
  thành 2 cột qua `MAX(CASE WHEN ...)`).
- `fetch_companies()`: đọc thêm 3 cột, ghi ra `companies.csv` — giữ RỖNG (không suy diễn số 0)
  khi không có dữ liệu, đúng triết lý đã dùng cho `sector`.
- Cập nhật docstring đầu file: thêm 2 nguồn tier3 mới, ghi rõ độ phủ thật đo được; xác nhận
  `SQL_COMPANIES` đã chạy thật trên Trino (trước đây chỉ có code, chưa từng chạy).

**`detecting_cheat_by_nebula/pipeline/sync_graph.py`**: `sync_companies()` đọc thêm 3 cột từ
`companies.csv`, ghi NULL thật (không phải chuỗi rỗng) khi thiếu — cùng cơ chế với
`status`/`established_date` đã có.

**`detecting_cheat_by_nebula/schemas/detecting_cheat_by_nebula.ngql`**: thêm 3 property `double`
vào `CREATE TAG Company`: `book_tax_gap`, `invoice_adjustment_rate`, `invoice_benford_chi2`.
Ghi chú ngay trong schema: 3 cột này CHỈ HIỂN THỊ, không tính điểm.

**Không đụng**: `validate_contract.py`, `detect_circular_trading.py` (quyết định mục 2),
`compute_gtgt_tndn_t2.py`/`compute_invoice_risk.py` bên `gotix-datalake` (chỉ đọc feature có
sẵn, không sửa công thức).

**`gotix-datalake` (nhánh `feat/n4-company-sector-risk-contract`, worktree riêng)**:
- `docs/BAO_CAO_TICH_HOP_GOTIX_NEBULA.md` §4/§7 — đính chính bảng data contract + việc còn lại
  đã lệch pha (viết 05/08/2026, trước các lần sửa 12/08 và số đo thật 18/08), giữ nguyên bản cũ
  có gạch ngang để không mất lịch sử.
- `data/domains/company/README.md:38` — sửa câu "chưa làm trong domain này" gây hiểu lầm; việc
  nối `sector` đã hoàn tất ở phía tiêu thụ dữ liệu (`ingest_trino_gotix.py`).

## 5. Kết quả kiểm chứng — chạy thật, không chỉ đọc code

**Bước 1 — `sector`** (Trino thật, `SPACE`/`DATA_DIR` tạm, xoá sau khi xong):
```
350 công ty có giao dịch -> companies.csv
313/350 có sector thật (37 "Chưa rõ" — mst không có dòng ngành nào)
Đối chiếu 3 mst mẫu với SELECT ... FROM company_industry WHERE nganh_chinh=true trực tiếp trên
Trino -> khớp 100%.
```

**Bước 2 — 3 cột rủi ro** (chạy `ingest_trino_gotix.py` sau khi sửa code):
```
book_tax_gap:            0/350 có giá trị (mst duy nhất có dữ liệu tax_risk KHÔNG nằm trong 350
                          công ty có giao dịch — 2 nguồn tax_declaration/einvoice chưa giao nhau)
invoice_adjustment_rate:  5/350 có giá trị
invoice_benford_chi2:     2/350 có giá trị (cần ≥100 hoá đơn/mst)
```
Không lỗi SQL, `py_compile` cả 2 file sạch.

**Bước 3 — Nebula thật** (space test `n4_test_company_risk`, `run_all.py --all --skip-detect
--datasource trino_gotix`, xoá space + dữ liệu chạy ngay sau khi đo xong):
```
DESCRIBE TAG Company -> đủ 10 property, có book_tax_gap/invoice_adjustment_rate/invoice_benford_chi2
FETCH PROP mst=0100100424 -> sector="Sản xuất xe đạp và xe cho người tàn tật",
  book_tax_gap=__NULL__, invoice_adjustment_rate=0.023885, invoice_benford_chi2=609.022809
FETCH PROP mst=8888000001 -> invoice_adjustment_rate=0.0, invoice_benford_chi2=1017.037295
```
Khớp đúng dữ liệu trong `companies.csv` — không lệch khi qua `sync_graph.py`/Nebula.
`validate_contract.py` → 100/100 (chi tiết mục 3).

## 6. Đánh đổi / rủi ro còn lại

- **Độ phủ 3 cột rủi ro rất thấp hiện tại (0-5/350 mst)**: đây là hệ quả của dữ liệu nguồn
  (domain `tax_declaration`/`einvoice` mới bootstrap ít công ty), KHÔNG phải bug — code join
  đúng, `NULL` đúng nghĩa "chưa có dữ liệu". Độ phủ sẽ tự tăng khi 2 domain đó nạp thêm dữ liệu
  thật, không cần sửa lại `ingest_trino_gotix.py`.
- **Quyết định "không tính điểm"** đổi lấy an toàn (không đụng công thức lõi `detect_circular_
  trading.py`) — nhưng đồng nghĩa 3 cột rủi ro thuế/hoá đơn hiện KHÔNG ảnh hưởng gì tới xếp hạng
  nguy cơ thật của thuật toán dò chu trình, chỉ là dữ liệu hiển thị tham khảo trên node. Nếu sau
  này Phúc muốn dùng làm tín hiệu chấm điểm thật, cần quay lại thiết kế trọng số + sửa 2 file
  (`validate_contract.py` + `detect_circular_trading.py`) — chưa làm trong N4.
- **`datasources.json` mục `trino_gotix.blocked_by`** vẫn ghi chú cũ "einvoice_invoice hiện đang
  0 dòng" — đã lỗi thời (đo thật hôm nay: 8.298 cạnh) nhưng KHÔNG nằm trong phạm vi N4 (không
  liên quan sector/3 cột rủi ro), không tự sửa — nêu ở đây để Phúc biết, không âm thầm bỏ qua.

## 7. Việc chưa làm / gợi ý bước tiếp theo

- `OWNS` (sở hữu vốn ĐKKD) vẫn chưa có nguồn trong Gotix lakehouse — mục duy nhất còn thiếu
  thật trong data contract, không thuộc phạm vi N4.
- Sửa lại ghi chú lỗi thời ở `datasources.json` (mục 6) — việc nhỏ, không liên quan N4, có thể
  làm riêng khi thuận tiện.
- Nếu muốn 3 cột rủi ro ảnh hưởng thật tới điểm/xếp hạng, cần quyết định trọng số cụ thể trước
  khi sửa `validate_contract.py`/`detect_circular_trading.py` — chưa quyết trong lần này.

## 8. ✅ FIXED (18/08/2026, phát hiện qua task `gotix-datalake/N1`) — space production `gotix_tax_graph` chưa migrate 3 cột mới

N4 chỉ verify `CREATE TAG Company` (đủ 10 property) trên 1 **space test tạm**
(`n4_test_company_risk`, mục 5) rồi xoá — không kiểm tra space **production thật**
`gotix_tax_graph` (space duy nhất Airflow DAG của `gotix-datalake` dùng). Vì `CREATE TAG
IF NOT EXISTS` là no-op trên tag đã tồn tại, `gotix_tax_graph` vẫn chỉ có 7/10 property, khiến
MỌI lần nạp Nebual thật qua Airflow (`tier2_ingest_nebula_delta`) fail 100% với
`SemanticError: Unknown column 'book_tax_gap' in schema` — cùng loại lỗi đã cảnh báo trước ở
comment file DDL (dòng "space cu van thieu cot nay") nhưng lần này rơi đúng vào space
production, không phải space cũ nào khác.

Đã fix: chạy `ALTER TAG Company ADD (book_tax_gap double, invoice_adjustment_rate double,
invoice_benford_chi2 double);` trực tiếp trên `gotix_tax_graph` (qua `nebula3-python`, container
`nebula-demo-api`). Verify: `DESCRIBE TAG Company` → đủ 10 property; trigger lại
`tier2_ingest_nebula_delta` qua Airflow → `success`; `FETCH PROP` 1 công ty thật → ghi đủ, 3 cột
mới `NULL` đúng nghĩa (công ty đó chưa có dữ liệu rủi ro). Chi tiết đầy đủ:
`gotix-datalake/docs/N1/N1_BAO_CAO.md` mục 4.
