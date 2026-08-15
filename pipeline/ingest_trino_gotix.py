# -*- coding: utf-8 -*-
"""[Tuy chon nhap lieu 2] Doc truc tiep Gotix Data Lakehouse (Trino) -> data/*.csv chuan hoa.

CUNG DINH DANG DAU RA voi ingest_csv86.py (companies.csv/trades.csv/shares_address.csv) —
load_schema.py va sync_graph.py phia sau chay NGUYEN VEN, khong biet/khong can biet nguon
la CSV tai tay hay Trino. Xem chi tiet mapping + SQL da kiem chung tai:
  gotix-datalake/docs/KE_HOACH_SYNC_GOTIX_SANG_NEBULA.md (muc 3, muc "Buoc 0" — da do that
  05/08/2026 tren sandbox: 30.553 dong, mst_mua NULL 21,5% trong chieu='ban').

NGUON TRINO (da xac nhan DDL + SQL that qua thuc nghiem 05/08/2026):
  - nessie.tier2.einvoice_invoice                    -> trades.csv (DA TEST tren du lieu that)
  - nessie.tier2.company_header + company_industry   -> companies.csv (name/address/sector,
    NGUON CHINH — domain company da nap ~350k cong ty 11/08/2026, xem
    gotix-datalake/data/domains/company/README.md)
  - nessie.tier2.company_header.dai_dien_phap_luat   -> legal_reps.csv (~98% dien du, xac nhan
    12/08/2026 qua Trino: 365.426/371.689 dong active) — nguon DUY NHAT cho tin hieu
    LEGAL_REP_OF, cac datasource CSV khac (raw/*.csv) KHONG co cot nay.
  - nessie.tier2.tax_declaration_bctc_filing_header  -> shares_address.csv; fallback name/address
    khi mst khong co trong company_header
  - nessie.tier2.tax_declaration_bctc_item_value     -> companies.csv (revenue, item_code=Ct10 —
    domain company KHONG co cot doanh thu, van phai lay tu BCTC)
  ⚠️ SQL_SHARES_ADDRESS CHUA TEST duoc tren du lieu that — domain tax_declaration chua duoc
  bootstrap trong sandbox nay luc viet script goc (chi moi bootstrap einvoice). Kiem tra lai
  khi tax_declaration co du lieu that. SQL_COMPANIES (ban sua 12/08/2026) da doi nguon chinh
  sang company_header/company_industry — domain nay DA co du lieu that (~350k cong ty), nhung
  ban SQL merge nay van CHUA duoc chay thuc te tren Trino, can chay 1 lan de xac nhan truoc khi
  coi la "da hoat dong".

QUYET DINH DA CHOT VOI PHUC (05/08/2026, sua 12/08/2026):
  - sector: lay tu company_industry.ten_nganh (uu tien nganh_chinh=true) — domain company da
    co du lieu that nen KHONG con hardcode "Chua ro" nua; van de "Chua ro" cho cong ty khong co
    dong nganh nao (khong bia gia tri).
  - name/address: uu tien company_header (nguon rong hon, ~350k cong ty), fallback BCTC filing
    header khi mst khong co trong company_header (vd cong ty chua duoc nap vao domain company).
  - PHAM VI cong ty nap vao Nebula (CHOT 12/08/2026): CHI nap MST THAT co giao dich trong
    einvoice_invoice (xem _TRANSACTING_MST_CTE), KHONG nap toan bo ~350k cong ty trong
    company_header nua. Ly do: 1 cong ty khong giao dich khong bao gio xuat hien trong 1 chu
    trinh (chu trinh luon di qua canh TRADES) nen khong nap cung khong mat tin hieu gi, chi
    do dung thoi gian nap + lam sai lech so lieu "kiem ke du lieu" tren UI (tung thay 371.602
    DN nhung 0 giao dich). Ap dung dong nhat cho ca 4 file: companies.csv, legal_reps.csv,
    shares_phone.csv, shares_address.csv.
  - revenue/report_date: GIU NGUYEN tu BCTC — domain company khong co cot doanh thu/ky bao cao.
    Lay ban ghi Ct10 GAN NHAT hien co cho moi mst (khong bat buoc khop nam voi ky hoa don dang xet).
  - nguong NULL mst_mua: da do that 21,5% (chieu='ban') tren mau sandbox nho, CHAP NHAN DUOC,
    khong chan lai — se do lai khi co du lieu quy mo day du.

BIEN MOI TRUONG:
  TRINO_HOST      mac dinh "localhost"
  TRINO_PORT      mac dinh 18082 (dung dung port da xac nhan tren docker-compose sandbox nay —
                  KIEM TRA LAI khi doi moi truong)
  TRINO_USER      mac dinh "gotix_sync"
  TRINO_CATALOG   mac dinh "nessie"
  PERIOD_FROM     TUY CHON, dang yyyymm — khong set = nap TOAN BO du lieu co san (dung y het
                  triet ly cua ingest_csv86.py: ingest khong loc ky, loc ky la viec cua buoc
                  detect sau khi da nap vao Nebula — xem run_all.py dong 310-322, "pf/pt" chi
                  duoc tinh SAU buoc ingest+sync, KHONG duoc truyen xuong ingest)
  PERIOD_TO       TUY CHON, dang yyyymm — di kem PERIOD_FROM
  DATA_DIR        tuy chon, mac dinh giong ingest_csv86.py (../data)

PHU THUOC THEM: can `pip install trino` — CHUA co trong requirements.txt cua du an nay (du an
hien chi phu thuoc nebula3-python, xem CLAUDE.md muc "Tech stack"). Chua chay thu duoc tren may
nay vi package `trino` chua duoc cai — CAN CAI + TEST truoc khi coi script nay da hoat dong.

CACH DUNG:
  TRINO_HOST=localhost TRINO_PORT=18082 PERIOD_FROM=202301 PERIOD_TO=202312 \
    python3 ingest_trino_gotix.py
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress  # noqa: E402
from ingest_csv86 import normalize_address  # noqa: E402 - tai dung, khong nhan doi logic

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE / "data"))

TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
TRINO_PORT = int(os.environ.get("TRINO_PORT", "18082"))
TRINO_USER = os.environ.get("TRINO_USER", "gotix_sync")
TRINO_CATALOG = os.environ.get("TRINO_CATALOG", "nessie")

FETCH_BATCH = 500  # dung y het BATCH_SIZE da ghi trong ke hoach — cursor streaming, khong
                    # load ca ket qua vao 1 list truoc khi ghi (xem ly do RAM trong ingest_csv86.py)

N_STEPS = 5

# 2 trang thai VOID xac nhan that tren du lieu sandbox 05/08/2026 (SELECT trang_thai_hd,
# count(*) ... GROUP BY — xem chuoi day du, co tien to "Hoa don "). Khop dung quy uoc da ghi
# trong data/domains/einvoice/tier3/README.md muc 3 ("Loai (void)").
_VOID_STATUSES = ("Hóa đơn đã bị thay thế", "Hóa đơn đã bị xóa bỏ/hủy bỏ")

# CTE dung chung: tap MST THAT co giao dich (chieu='ban', dung y het dieu kien loc
# cua SQL_TRADES — neu lech dieu kien, se co MST duoc nap company info nhung cuoi
# cung khong co canh TRADES nao, dung y het van de ma viec loc nay muon tranh).
# Chot voi Phuc 12/08/2026: KHONG nap toan bo ~350k cong ty trong company_header
# nua — CHI nap dung tap cong ty THAT xuat hien trong giao dich, roi moi map sang
# company de lay du truong. Vi sao an toan (khong mat tin hieu): 1 cong ty KHONG
# giao dich thi khong bao gio xuat hien trong 1 chu trinh (chu trinh luon di qua
# canh TRADES) — nen cac tin hieu lien ket ngam (LEGAL_REP_OF/SHARES_ADDRESS/
# SHARES_PHONE) giua 2 cong ty ĐANG giao dich van giu nguyen du co loc bot cong ty
# thu 3 khong giao dich ra khoi Nebula.
_TRANSACTING_MST_CTE = f"""
transacting_mst AS (
  SELECT mst_ban_goc AS mst FROM einvoice_invoice
  WHERE chieu = 'ban' AND mst_ban_goc IS NOT NULL AND mst_mua_goc IS NOT NULL
    AND ky_hieu_mau_so IN ('1', '2')
    AND trang_thai_hd NOT IN ('{_VOID_STATUSES[0]}', '{_VOID_STATUSES[1]}')
  UNION
  SELECT mst_mua_goc AS mst FROM einvoice_invoice
  WHERE chieu = 'ban' AND mst_ban_goc IS NOT NULL AND mst_mua_goc IS NOT NULL
    AND ky_hieu_mau_so IN ('1', '2')
    AND trang_thai_hd NOT IN ('{_VOID_STATUSES[0]}', '{_VOID_STATUSES[1]}')
)
"""

# BUG THAT DA GAP (14/08/2026, xem BAO_CAO_TRIEN_KHAI.md Phase 2): tier2.einvoice_invoice co
# the co NHIEU DONG TRUNG cho CUNG 1 hoa don that (vd 2 luong cascade tier1->tier2 chay cho
# cung 1 file — da xac nhan that qua Trino: 2 dong y het cho cung mst_ban/mst_mua/ngay_lap/
# tien_chua_thue/source_file). Truoc day chi `invoice_count` khu trung lap dung
# (COUNT DISTINCT theo dinh danh hoa don), con SUM(tien_chua_thue)/SUM(tien_thue) THI KHONG —
# cong don ca hang trung lap, thoi phong sai gia tri canh TRADES (vd 100tr bi cong thanh 200tr).
# Fix: khu trung lap theo DUNG dinh danh hoa don that (mst_ban, ky_hieu_mau_so, ky_hieu_hd,
# so_hd — theo NĐ123) TRUOC KHI gop/SUM, dung 1 CTE rieng thay vi SUM truc tiep tren bang tho.
SQL_TRADES = """
WITH dedup_invoices AS (
  SELECT
    mst_ban_goc, mst_mua_goc, ngay_lap, tien_chua_thue, tien_thue
  FROM (
    SELECT mst_ban_goc, mst_mua_goc, ngay_lap, tien_chua_thue, tien_thue,
           ROW_NUMBER() OVER (
             PARTITION BY mst_ban, ky_hieu_mau_so, ky_hieu_hd, so_hd
             ORDER BY ictrl_dt DESC
           ) AS rn
    FROM einvoice_invoice
    WHERE chieu = 'ban'
      AND mst_ban_goc IS NOT NULL
      AND mst_mua_goc IS NOT NULL
      AND ky_hieu_mau_so IN ('1', '2')
      AND trang_thai_hd NOT IN ('{void_a}', '{void_b}')
      AND ngay_lap IS NOT NULL
      {period_filter}
  ) WHERE rn = 1
)
SELECT
  mst_ban_goc AS seller_mst,
  mst_mua_goc AS buyer_mst,
  CAST(date_format(CAST(ngay_lap AS TIMESTAMP), '%Y%m') AS INTEGER) AS period,
  COUNT(*) AS invoice_count,
  SUM(tien_chua_thue) AS total_amount,
  SUM(tien_thue) AS total_vat,
  date_format(CAST(MIN(ngay_lap) AS TIMESTAMP), '%Y-%m-%d') AS first_date,
  date_format(CAST(MAX(ngay_lap) AS TIMESTAMP), '%Y-%m-%d') AS last_date
FROM dedup_invoices
GROUP BY mst_ban_goc, mst_mua_goc, CAST(date_format(CAST(ngay_lap AS TIMESTAMP), '%Y%m') AS INTEGER)
"""

# "moi nhat theo mst" dung dung quy tac latest cua lake: so_lan giam dan -> ngay -> load_ts
# (DATALAKE_RISK_NOTES.md B2, nhu da dan trong ke hoach).
#
# Nguon chinh cho name/address/sector la domain `company` (~350k cong ty, xem docstring dau
# file) — BCTC (tax_declaration) chi con dung cho revenue/report_date (2 cot ma domain company
# khong co) va lam FALLBACK name/address cho mst chua co trong company_header.
#
# CHOT 12/08/2026: CHI lay company info cho MST nam trong transacting_mst (xem
# _TRANSACTING_MST_CTE) — khong con nap toan bo ~350k cong ty nua. Loc o WHERE
# cuoi (tren COALESCE(c.mst, f.mst)), khong loc rieng tung nhanh JOIN, de dam bao
# dung ca 2 truong hop: MST chi co trong company_header, hoac chi co trong BCTC.
SQL_COMPANIES = f"""
WITH {_TRANSACTING_MST_CTE},
latest_filing AS (
  SELECT mst, ten_nnt, dchi_nnt, ictrl_dt
  FROM (
    SELECT mst, ten_nnt, dchi_nnt, ictrl_dt,
           ROW_NUMBER() OVER (PARTITION BY mst ORDER BY so_lan DESC, ngay_lap_tkhai DESC, load_ts DESC) AS rn
    FROM tax_declaration_bctc_filing_header
  ) WHERE rn = 1
),
latest_revenue AS (
  SELECT mst, item_value_num AS revenue
  FROM (
    SELECT mst, item_value_num,
           ROW_NUMBER() OVER (PARTITION BY mst ORDER BY ictrl_dt DESC) AS rn
    FROM tax_declaration_bctc_item_value
    WHERE item_code = 'Ct10' AND statement_code = 'KQKD' AND period_scope = 'nam_nay'
  ) WHERE rn = 1
),
latest_company AS (
  SELECT mst, ten_cong_ty, dia_chi, trang_thai, ngay_hoat_dong
  FROM (
    SELECT mst, ten_cong_ty, dia_chi, trang_thai, ngay_hoat_dong,
           ROW_NUMBER() OVER (PARTITION BY mst ORDER BY ictrl_dt DESC) AS rn
    FROM company_header
    WHERE record_status = 'active' AND mst IS NOT NULL
  ) WHERE rn = 1
),
latest_sector AS (
  SELECT mst, ten_nganh
  FROM (
    SELECT mst, ten_nganh,
           ROW_NUMBER() OVER (
             PARTITION BY mst
             ORDER BY (CASE WHEN nganh_chinh THEN 0 ELSE 1 END), ictrl_dt DESC
           ) AS rn
    FROM company_industry
    WHERE mst IS NOT NULL AND ten_nganh IS NOT NULL
  ) WHERE rn = 1
)
SELECT
  COALESCE(c.mst, f.mst)                AS mst,
  COALESCE(c.ten_cong_ty, f.ten_nnt)    AS name,
  s.ten_nganh                            AS sector,
  COALESCE(c.dia_chi, f.dchi_nnt)       AS address,
  r.revenue                              AS revenue,
  f.ictrl_dt                             AS report_date,
  c.trang_thai                           AS status,
  c.ngay_hoat_dong                       AS established_date
FROM latest_company c
FULL OUTER JOIN latest_filing f ON f.mst = c.mst
LEFT JOIN latest_revenue r ON r.mst = COALESCE(c.mst, f.mst)
LEFT JOIN latest_sector s ON s.mst = COALESCE(c.mst, f.mst)
WHERE COALESCE(c.mst, f.mst) IN (SELECT mst FROM transacting_mst)
"""

# Nguoi dai dien phap luat — moi nhat theo mst, chi lay dong co gia tri that (khac
# rong). Dung lai dung 1 CTE "latest theo ictrl_dt" nhu latest_company o SQL_COMPANIES.
# CHOT 12/08/2026: cung loc theo transacting_mst nhu SQL_COMPANIES — khong tao
# dinh Person/canh LEGAL_REP_OF cho cong ty khong giao dich (se khong bao gio
# duoc nap thanh dinh Company, canh do vo nghia).
SQL_LEGAL_REPS = f"""
WITH {_TRANSACTING_MST_CTE}
SELECT mst, dai_dien_phap_luat
FROM (
  SELECT mst, dai_dien_phap_luat,
         ROW_NUMBER() OVER (PARTITION BY mst ORDER BY ictrl_dt DESC) AS rn
  FROM company_header
  WHERE record_status = 'active' AND mst IS NOT NULL
    AND dai_dien_phap_luat IS NOT NULL AND length(trim(dai_dien_phap_luat)) > 0
    AND mst IN (SELECT mst FROM transacting_mst)
) WHERE rn = 1
"""

# So dien thoai tru so — DDL nguon tu ghi ro cot nay "raw, KHONG dung cho Nebula,
# KHONG clean" (chua tach so/chua chuan hoa). Chuan hoa THAT SU lam o Python (xem
# _phone_candidates()), SQL chi loc rong/qua ngan de do it rac keo ve.
# CHOT 12/08/2026: loc theo transacting_mst, cung ly do voi SQL_LEGAL_REPS.
SQL_PHONES = f"""
WITH {_TRANSACTING_MST_CTE}
SELECT mst, dien_thoai_tru_so
FROM (
  SELECT mst, dien_thoai_tru_so,
         ROW_NUMBER() OVER (PARTITION BY mst ORDER BY ictrl_dt DESC) AS rn
  FROM company_header
  WHERE record_status = 'active' AND mst IS NOT NULL
    AND dien_thoai_tru_so IS NOT NULL AND length(trim(dien_thoai_tru_so)) >= 9
    AND mst IN (SELECT mst FROM transacting_mst)
) WHERE rn = 1
"""

# CHOT 12/08/2026 (sua lai lan 2): BAN CU chi doc dchi_nnt tu BCTC — sai, vi dia
# chi hien thi THAT tren Company node lay tu company_header.dia_chi la CHINH
# (xem SQL_COMPANIES: COALESCE(c.dia_chi, f.dchi_nnt)), BCTC chi la du phong. Ban
# cu vo tinh lam SHARES_ADDRESS chi so khop theo dia chi BCTC (nguon rat mong,
# hien chi 3 dong) ma bo qua han company_header (nguon rong, ~350k cong ty co
# dia chi) — 2 cong ty trung dia chi theo company_header se KHONG bao gio duoc
# phat hien. Sua: dung LAI DUNG logic merge cua SQL_COMPANIES (company_header
# chinh, BCTC du phong) roi moi chuan hoa/ghep cap o Python.
SQL_SHARES_ADDRESS = f"""
WITH {_TRANSACTING_MST_CTE},
latest_company AS (
  SELECT mst, dia_chi
  FROM (
    SELECT mst, dia_chi,
           ROW_NUMBER() OVER (PARTITION BY mst ORDER BY ictrl_dt DESC) AS rn
    FROM company_header
    WHERE record_status = 'active' AND mst IS NOT NULL
      AND mst IN (SELECT mst FROM transacting_mst)
  ) WHERE rn = 1
),
latest_filing AS (
  SELECT mst, dchi_nnt
  FROM (
    SELECT mst, dchi_nnt,
           ROW_NUMBER() OVER (PARTITION BY mst ORDER BY so_lan DESC, ngay_lap_tkhai DESC, load_ts DESC) AS rn
    FROM tax_declaration_bctc_filing_header
    WHERE mst IN (SELECT mst FROM transacting_mst)
  ) WHERE rn = 1
)
SELECT
  COALESCE(c.mst, f.mst) AS mst,
  COALESCE(c.dia_chi, f.dchi_nnt) AS address
FROM latest_company c
FULL OUTER JOIN latest_filing f ON f.mst = c.mst
WHERE COALESCE(c.dia_chi, f.dchi_nnt) IS NOT NULL
  AND length(trim(COALESCE(c.dia_chi, f.dchi_nnt))) > 10
"""


def _connect():
    from trino.dbapi import connect  # import cuc bo — bao loi ro rang neu chua cai package

    return connect(host=TRINO_HOST, port=TRINO_PORT, user=TRINO_USER,
                   catalog=TRINO_CATALOG, schema="tier2")


def _stream_rows(cur, sql: str):
    """Chay 1 cau SQL, tra generator doc theo lo (khong load ca ket qua vao RAM 1 luc)."""
    cur.execute(sql)
    while True:
        batch = cur.fetchmany(FETCH_BATCH)
        if not batch:
            break
        for row in batch:
            yield row


def fetch_companies(conn) -> int:
    cur = conn.cursor()
    out = DATA_DIR / "companies.csv"
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        # 8 cot — 7 cot khop schema companies.csv cua ingest_csv86.py (mst,name,sector,
        # address,revenue,report_date,status) + "established_date" rieng cho nguon nay
        # (ingest_csv86.py khong co cot nay, sync_companies() tu kiem tra co/khong).
        # "status" = trang_thai DKKD that; "established_date" = ngay_hoat_dong that —
        # dung boi load_risky_companies() (detect_circular_trading.py) cho tin hieu
        # "thanh vien rui ro" (status rui ro HOAC moi thanh lap <12 thang truoc ky).
        w.writerow(["mst", "name", "sector", "address", "revenue", "report_date", "status",
                    "established_date"])
        for (mst, name, sector, address, revenue, report_date, status,
             established_date) in _stream_rows(cur, SQL_COMPANIES):
            w.writerow([
                mst, (name or "").strip(), (sector or "Chưa rõ").strip(),
                (address or "").strip(), (revenue if revenue is not None else 0),
                report_date, (status or "").strip(),
                established_date if established_date else "",
            ])
            n += 1
    return n


def fetch_trades(conn, period_from: int | None, period_to: int | None) -> int:
    cur = conn.cursor()
    if period_from is not None and period_to is not None:
        period_filter = (
            "AND CAST(date_format(CAST(ngay_lap AS TIMESTAMP), '%Y%m') AS INTEGER) "
            f"BETWEEN {period_from} AND {period_to}"
        )
    else:
        period_filter = ""  # khong set = nap toan bo, loc ky la viec cua buoc detect sau
    sql = SQL_TRADES.format(
        void_a=_VOID_STATUSES[0], void_b=_VOID_STATUSES[1], period_filter=period_filter,
    )
    out = DATA_DIR / "trades.csv"
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["seller_mst", "buyer_mst", "period", "invoice_count",
                    "total_amount", "total_vat", "first_date", "last_date"])
        for row in _stream_rows(cur, sql):
            w.writerow(row)
            n += 1
    return n


def fetch_shares_address(conn) -> int:
    """Keo (mst, dchi_nnt moi nhat) ve truoc, chuan hoa + ghep cap O PYTHON — dung y het
    thuat toan derive_shares_address() cua ingest_csv86.py de khong lech logic giua 2 nguon."""
    cur = conn.cursor()
    by_addr: dict[str, list[str]] = {}
    for mst, addr in _stream_rows(cur, SQL_SHARES_ADDRESS):
        norm = normalize_address(addr)
        if norm:
            by_addr.setdefault(norm, []).append(mst.strip())

    out = DATA_DIR / "shares_address.csv"
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company_a", "company_b", "norm_addr"])
        for norm, msts in sorted(by_addr.items()):
            uniq = sorted(set(msts))
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    w.writerow([uniq[i], uniq[j], norm])
                    n += 1
    return n


_PHONE_SPLIT_RE = re.compile(r"[/\-]")
_PHONE_DIGITS_RE = re.compile(r"\D")


def _phone_candidates(raw: str) -> list[str]:
    """Tach 1 o "dien_thoai_tru_so" thanh danh sach so dien thoai HOP LE.

    Du lieu THAT lan lon (xac nhan qua Trino 12/08/2026): nhieu o chua 2 so noi
    boi `/` hoac `-` (vd "0971359012/09828849"), co o dinh lien khong dau phan
    cach (vd "09966399628098886619" — 20 chu so, ro rang la 2+ so dinh lai), co
    o bi cat cut (vd "090615" chi 6 chu so). DDL nguon tu ghi ro cot nay "raw,
    KHONG dung cho Nebula, KHONG clean" — Phuc xac nhan 12/08/2026 van muon lay,
    nhung PHAI loc than trong: chi giu ung vien tach duoc RO RANG (bang `/`/`-`)
    va dung DUNG 10 hoac 11 chu so, bat dau bang "0" (dinh dang VN). Moi truong
    hop khac (qua ngan, qua dai, dinh lien khong tach duoc) BI LOAI — dung tinh
    than "de trong that hon suy dien" da co san trong file nay (vd
    _RISKY_STATUSES), khong co gang doan/ghep lai so bi cat cut.
    """
    out = []
    for part in _PHONE_SPLIT_RE.split(raw):
        digits = _PHONE_DIGITS_RE.sub("", part)
        if len(digits) in (10, 11) and digits.startswith("0"):
            out.append(digits)
    return out


# Tran an toan CHO TUNG SO (khac MAX_SHARES_ADDRESS_PAIRS cua ingest_csv86.py — do
# la tran TONG so cap toan cuc, con day la loc CHAT LUONG tin hieu tung nhom). Do
# THAT tren du lieu company_header (12/08/2026): 1 SDT bi DUNG CHUNG boi 116 cong
# ty — gan chac chan la SDT van phong DICH VU THANH LAP DOANH NGHIEP (dai ly dang
# ky ho hang tram cong ty), KHONG PHAI lien ket so huu/dieu hanh that. Neu khong
# loc, 1 so nay mot minh sinh C(116,2)=6.670 cap "lien ket ngam" gia, lam nhieu tin
# hieu that. Nguong 5: cho phep nhom nho (2-5 cong ty — dung profile "vai cong ty
# do 1 nguoi dung sau lap" ma tin hieu nay muon bat), loai nhom lon (dai ly dich
# vu). Co the chinh qua env neu can.
MAX_SHARES_PHONE_GROUP = int(os.environ.get("MAX_SHARES_PHONE_GROUP", "5"))


def fetch_shares_phone(conn) -> int:
    """Suy lien ket ngam moi: 2 cong ty chung SDT tru so -> shares_phone.csv
    (company_a, company_b, norm_phone), dung y het cau truc shares_address.csv,
    tru viec loc bot nhom qua lon (xem MAX_SHARES_PHONE_GROUP).
    Nap qua EDGE SHARES_PHONE — xem schemas/detecting_cheat_by_nebula.ngql."""
    cur = conn.cursor()
    by_phone: dict[str, list[str]] = {}
    for mst, raw in _stream_rows(cur, SQL_PHONES):
        for phone in _phone_candidates(raw):
            by_phone.setdefault(phone, []).append(mst.strip())

    out = DATA_DIR / "shares_phone.csv"
    n = 0
    n_skipped_groups = 0
    # 1 cap cong ty CHI duoc 1 canh — 1 cong ty co the co 2 SDT hop le trong cung 1
    # o (vd "A/B"), va SDT thu 2 co the TINH CO trung voi 1 cong ty khac o 1 nhom
    # phone khac -> cung 1 cap (X,Y) xuat hien o 2 nhom -> INSERT EDGE thu 2 GHI DE
    # thu nhat (Nebula khoa canh theo src+dst+rank, rank=0 co dinh) -> so dong ghi
    # CSV > so canh thuc te trong Nebula, lam _wait_until_synced() bao loi sai (da
    # gap that 12/08/2026: 28.377 dong ghi, 28.376 canh — dedupe tai day de tranh).
    seen_pairs: set[tuple[str, str]] = set()
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company_a", "company_b", "norm_phone"])
        for phone, msts in sorted(by_phone.items()):
            uniq = sorted(set(msts))
            if len(uniq) > MAX_SHARES_PHONE_GROUP:
                n_skipped_groups += 1
                continue
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    pair = (uniq[i], uniq[j])
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    w.writerow([uniq[i], uniq[j], phone])
                    n += 1
    if n_skipped_groups:
        progress.log(f"  ... bỏ qua {n_skipped_groups} số điện thoại dùng chung bởi "
                     f">{MAX_SHARES_PHONE_GROUP} công ty (nghi là SĐT đại lý dịch vụ, "
                     f"không phải liên kết thật)")
    return n


def fetch_legal_reps(conn) -> int:
    """Ghi legal_reps.csv (person_id, person_name, mst) — nguon cho TAG Person +
    EDGE LEGAL_REP_OF (xem schemas/detecting_cheat_by_nebula.ngql). Chi datasource
    nay co du lieu — raw/*.csv khac khong co cot dai_dien_phap_luat."""
    cur = conn.cursor()
    out = DATA_DIR / "legal_reps.csv"
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["person_id", "person_name", "mst"])
        for mst, name in _stream_rows(cur, SQL_LEGAL_REPS):
            name = (name or "").strip()
            if not name:
                continue
            # tai dung normalize_address() de chuan hoa CHUOI (bo dau, thuong hoa, gop
            # khoang trang) — ham nay khong rieng gi dia chi, chi la 1 ham chuan hoa
            # chuoi chung; 2 cach ghi ten khac nhau (co/khong dau, thua khoang trang)
            # cua CUNG 1 nguoi se gop ve 1 Person duy nhat.
            # VID PHAI <=16 byte (vid_type FIXED_STRING(16)) -> khong dung ten that lam
            # VID (ten co dau de vuot 16 byte) — bam sha256 roi cat 16 ky tu hex.
            norm = normalize_address(name)
            person_id = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
            w.writerow([person_id, name, mst])
            n += 1
    return n


def main() -> None:
    _pf, _pt = os.environ.get("PERIOD_FROM"), os.environ.get("PERIOD_TO")
    period_from = int(_pf) if _pf else None
    period_to = int(_pt) if _pt else None
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    ky_label = f"{period_from}-{period_to}" if period_from else "TOÀN BỘ (không lọc kỳ)"
    progress.log(f"Nguồn: Trino {TRINO_HOST}:{TRINO_PORT} catalog={TRINO_CATALOG} "
                 f"| kỳ {ky_label} -> {DATA_DIR}")
    conn = _connect()

    with progress.Step(1, N_STEPS, "Đọc công ty (company_header/company_industry + BCTC)") as st:
        n_company = fetch_companies(conn)
        st.metric(companies=n_company)
        progress.log(f"{n_company} công ty CÓ GIAO DỊCH -> companies.csv "
                     f"(name/address/sector từ domain company, revenue/report_date từ BCTC — "
                     f"sector='Chưa rõ' chỉ còn cho mst không có dòng ngành nào; công ty không "
                     f"giao dịch trong einvoice_invoice KHÔNG được nạp — xem transacting_mst)")

    with progress.Step(2, N_STEPS, "Đọc & gộp giao dịch (einvoice_invoice)") as st:
        n_edges = fetch_trades(conn, period_from, period_to)
        st.metric(edges=n_edges)
        progress.log(f"{n_edges} cạnh TRADES -> trades.csv "
                     f"(đã loại chieu='mua', trạng thái void, ký_hiệu_mẫu ngoài 1/2, mst NULL)")

    with progress.Step(3, N_STEPS, "Suy liên kết địa chỉ chung") as st:
        n_addr = fetch_shares_address(conn)
        st.metric(shares_address=n_addr)
        progress.log(f"{n_addr} cặp công ty trùng địa chỉ đăng ký -> shares_address.csv")

    with progress.Step(4, N_STEPS, "Suy liên kết số điện thoại chung") as st:
        n_phone = fetch_shares_phone(conn)
        st.metric(shares_phone=n_phone)
        progress.log(f"{n_phone} cặp công ty trùng số điện thoại trụ sở -> shares_phone.csv")

    with progress.Step(5, N_STEPS, "Đọc người đại diện pháp luật") as st:
        n_legal = fetch_legal_reps(conn)
        st.metric(legal_reps=n_legal)
        progress.log(f"{n_legal} dòng người đại diện -> legal_reps.csv "
                     f"(chỉ domain company mới có cột dai_dien_phap_luat)")

    progress.done(companies=n_company, edges=n_edges, shares_address=n_addr,
                  shares_phone=n_phone, legal_reps=n_legal,
                  period_from=period_from, period_to=period_to, data_dir=str(DATA_DIR))


if __name__ == "__main__":
    main()
