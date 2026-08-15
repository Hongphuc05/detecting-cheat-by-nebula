# -*- coding: utf-8 -*-
"""[Tuy chon nhap lieu 1] Cap CSV chuan detecting_cheat_by_nebula -> data/*.csv da chuan hoa.

DAU VAO (2 file, DEU KHONG CO DONG HEADER):
  company.csv : mst, ten_cong_ty, linh_vuc, dia_chi, doanh_thu, nam_bao_cao
  invoice.csv : so_hoa_don, ngay_xuat(yyyy-mm-dd), mst_nguon(ben BAN),
                mst_dich(ben MUA), mo_ta, tien_chua_thue, thue_gtgt,
                loai_gd, nhan_ai, rank

DAU RA (3 file trong ../data/):
  companies.csv      mst,name,sector,address,revenue,report_date
  trades.csv         seller_mst,buyer_mst,period,invoice_count,total_amount,
                     total_vat,first_date,last_date
  shares_address.csv company_a,company_b,norm_addr

===========================================================================
THUAT TOAN GOP CANH — "trai tim" can bao ve, doc ky truoc khi sua
===========================================================================
Buoc 1: suy ky ke khai tu ngay xuat hoa don. "2021-03-15" -> 202103.
        Day la khoa gop QUAN TRONG NHAT: 2 hoa don cung cap (ban, mua) nhung
        KHAC thang KHONG duoc gop chung, de giu nguyen tin hieu "nen thoi gian"
        — tin hieu chinh phat hien gian lan carousel (20/100 diem).
Buoc 2: GROUP BY (mst_nguon, mst_dich, period) — giong het SQL.
Buoc 3: moi nhom -> COUNT(*), SUM(tien), SUM(vat), MIN(ngay), MAX(ngay).
Buoc 4: ghi 1 dong = 1 canh TRADES, rank = period.

Ty le giam canh KHONG phai hang so — phu thuoc mat do that cua du lieu. Tren
detecting_cheat_by_nebula chi giam ~1,1 lan (moi cap DN trung binh giao dich ~1 lan/thang),
KHAC HAN kich ban gia lap tax_graph (~100 lan). Script tu in ty le THAT.

===========================================================================
NHIEU BO DU LIEU — moi bo 1 thu muc con trong raw/
===========================================================================
raw/ CHUA duoc phep chi co dung 1 cap company.csv/invoice.csv o goc — neu co bo
thu 2 se ghi de len bo dau, mat het dau vet "cong ty nao di voi hoa don nao".
Vi vay moi bo du lieu PHAI nam trong 1 thu muc rieng:

  raw/<ten_bo>/company.csv
  raw/<ten_bo>/invoice.csv

`ten_bo` chi duoc phep chu thuong/hoa, so, gach duoi (khong dau cach, khong ky
tu dac biet) — dung lam ten thu muc AN TOAN khi truyen tu web (chan duoc
"../../etc" hay tuong tu). Xem ham `_dataset_dir()`.

===========================================================================
CACH DUNG
===========================================================================
  python3 ingest_csv86.py                       # doc raw/hanoi_98cty/{company,invoice}.csv (mac dinh)
  DATASET=ten_bo_khac python3 ingest_csv86.py   # doc raw/ten_bo_khac/{company,invoice}.csv
  COMPANY_CSV=/duong/dan/a.csv INVOICE_CSV=/duong/dan/b.csv python3 ingest_csv86.py
  DATA_DIR=/noi/khac python3 ingest_csv86.py    # doi noi ghi ket qua

Bien moi truong: DATASET, COMPANY_CSV, INVOICE_CSV, DATA_DIR (deu tuy chon).
COMPANY_CSV/INVOICE_CSV neu dat se GHI DE hoan toan len DATASET (dung khi can
tro toi 1 file nam ngoai cau truc raw/<ten_bo>/ chuan, vi du script tu dong hoa).
"""
from __future__ import annotations

import csv
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
RAW_DIR = BASE / "raw"

# Ten bo mac dinh — bo du lieu THAT duy nhat hien co (98 cong ty Ha Noi).
DEFAULT_DATASET = "hanoi_98cty"
_DATASET_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _dataset_dir() -> Path:
    """Tra thu muc raw/<ten_bo>/, da kiem tra ten hop le va nam trong raw/.

    QUAN TRONG (bao mat): `DATASET` co the den tu request web (nguoi dung go ten
    bo du lieu). Regex chi cho chu/so/gach duoi/gach ngang chan duoc
    "../../etc/passwd"; kiem tra `resolve()` nam trong RAW_DIR la lop phong thu
    thu hai neu sau nay co ai noi long regex ma quen kiem lai."""
    name = os.environ.get("DATASET", DEFAULT_DATASET)
    if not _DATASET_RE.match(name):
        raise ValueError(f"Ten bo du lieu khong hop le: {name!r}")
    d = (RAW_DIR / name).resolve()
    if not str(d).startswith(str(RAW_DIR.resolve()) + os.sep):
        raise ValueError(f"Ten bo du lieu nam ngoai raw/: {name!r}")
    return d


_DATASET_DIR = _dataset_dir()
COMPANY_CSV = Path(os.environ.get("COMPANY_CSV", _DATASET_DIR / "company.csv"))
INVOICE_CSV = Path(os.environ.get("INVOICE_CSV", _DATASET_DIR / "invoice.csv"))
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE / "data"))

N_STEPS = 3

# Tran an toan cho so cap SHARES_ADDRESS (xem derive_shares_address). Dat 5 trieu:
# du rong cho moi bo du lieu that (98 cong ty that -> 0 cap; 515K cong ty voi dia
# chi da dang thuc te -> vai chuc nghin cap), nhung chan duoc truong hop dia chi
# sinh tu dong bi trung lap khien so cap no theo binh phuong.
MAX_SHARES_ADDRESS_PAIRS = int(os.environ.get("MAX_SHARES_ADDRESS_PAIRS", "5000000"))

# Cot trong invoice.csv (khong header). Chi so co dinh — neu doi thu tu cot phai
# sua o day, KHONG doan theo ten.
I_SO_HD, I_NGAY, I_BAN, I_MUA, I_MOTA, I_TIEN, I_VAT = 0, 1, 2, 3, 4, 5, 6


def to_period(ngay_xuat: str) -> int:
    """'2021-03-15' -> 202103. Nem loi neu sai format — that bai som con hon
    gop sai ky roi bao cao sai am tham."""
    parts = ngay_xuat.strip().split("-")
    if len(parts) != 3:
        raise ValueError(f"ngay_xuat khong dung dang yyyy-mm-dd: {ngay_xuat!r}")
    y, m, _ = parts
    return int(y) * 100 + int(m)


# --------------------------------------------------------------------------
# Chuan hoa dia chi — dung de suy SHARES_ADDRESS
# --------------------------------------------------------------------------
# Cac vien tat pho bien trong dia chi hanh chinh VN. Khong chuan hoa thi
# "P. Vinh Tuy" va "Phuong Vinh Tuy" bi coi la 2 dia chi khac nhau.
_ABBREV = [
    (r"\bp\.?\s", "phuong "), (r"\bq\.?\s", "quan "), (r"\btp\.?\s", "thanh pho "),
    (r"\btt\.?\s", "thi tran "), (r"\bkp\.?\s", "khu pho "), (r"\bng\.?\s", "ngo "),
    (r"\bđ\.?\s", "duong "), (r"\bd\.?\s", "duong "), (r"\bh\.?\s", "huyen "),
    (r"\bsn\.?\s", "so "), (r"\bs\.?\s", "so "),
]


def normalize_address(addr: str) -> str:
    """Chuan hoa dia chi ve dang so sanh duoc: bo dau, thuong hoa, go vien tat,
    bo dau cau, gop khoang trang.

    LUU Y THAT: tren 98 cong ty detecting_cheat_by_nebula, chuan hoa nay (va ca fuzzy-match
    70-90%% da thu truoc do) van cho ra 0 cap trung dia chi. Giu ham nay vi bo
    du lieu SAU (NhomACD ~3.900 MST) chac chan se can, khong phai vi bo hien tai.
    """
    s = unicodedata.normalize("NFD", addr.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")  # bo dau
    s = s.replace("đ", "d")
    s = re.sub(r"[.,;:/\-()]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for pat, rep in _ABBREV:
        s = re.sub(pat, rep, s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------
# Cac buoc
# --------------------------------------------------------------------------

def read_companies() -> list[list[str]]:
    """Cot 7 (`trang_thai`) la TUY CHON — bo du lieu cu (6 cot, vd hanoi_98cty) van
    doc duoc, tu dong coi nhu khong biet trang thai (rong, KHONG suy dien "active").
    Bo du lieu nao co du lieu DKKD that (vd 86_cty_full) moi truyen du 7 cot."""
    if not COMPANY_CSV.exists():
        raise FileNotFoundError(f"Khong thay file cong ty: {COMPANY_CSV}")
    rows = []
    with open(COMPANY_CSV, encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.reader(f), 1):
            if not row or not row[0].strip():
                continue
            if len(row) < 6:
                raise ValueError(
                    f"{COMPANY_CSV.name} dong {i}: can toi thieu 6 cot "
                    f"(mst,ten,linh_vuc,dia_chi,doanh_thu,nam_bao_cao), thay {len(row)}"
                )
            trang_thai = row[6] if len(row) >= 7 else ""
            rows.append(row[:6] + [trang_thai])
    if not rows:
        raise ValueError(f"{COMPANY_CSV.name} rong")
    return rows


def write_companies(rows: list[list[str]]) -> int:
    """Sao chep + doi ten cot cho khop schema. `status` de RONG (khong phai chuoi
    "active") khi khong biet — RONG = khong tinh vao tin hieu "thanh vien rui ro",
    khac voi mot gia tri that (vd "Tam ngung kinh doanh") = TINH vao tin hieu do.
    Xem muc 4.2 Data Contract: truoc day luon de trong vi khong co du lieu that."""
    out = DATA_DIR / "companies.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mst", "name", "sector", "address", "revenue", "report_date", "status"])
        for mst, name, sector, address, revenue, report_date, status in rows:
            w.writerow([mst.strip(), name.strip(), sector.strip(), address.strip(),
                        (revenue.strip() or "0"), report_date.strip(), status.strip()])
    return len(rows)


def aggregate_trades() -> tuple[int, int, int, tuple[int, int]]:
    """Gop hoa don -> canh TRADES. Tra (so hoa don, so canh, so dong tu-ban-cho-minh,
    (ky nho nhat, ky lon nhat))."""
    if not INVOICE_CSV.exists():
        raise FileNotFoundError(f"Khong thay file hoa don: {INVOICE_CSV}")

    # Chi can min/max ngay moi nhom (khong can toan bo danh sach) -> theo doi
    # bang 2 truong chay thay vi giu 1 list tang mai theo so hoa don. Voi bo du
    # lieu vai trieu hoa don, list "dates" cu se giu ca trieu chuoi ngay trong
    # RAM chi de rut ra 2 gia tri — day la 1 phan gay ap luc RAM/swap khi test
    # quy mo lon (xem IBM Transactions for AML/PHAN_TICH_BO_DU_LIEU_IBM_AML.md).
    groups: dict = defaultdict(lambda: {
        "count": 0, "amount": 0, "vat": 0, "first_date": None, "last_date": None,
    })
    n_invoices = n_self = 0

    with open(INVOICE_CSV, encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.reader(f), 1):
            if not row or not row[0].strip():
                continue
            if len(row) < 7:
                raise ValueError(
                    f"{INVOICE_CSV.name} dong {i}: can it nhat 7 cot, thay {len(row)}"
                )
            n_invoices += 1
            seller, buyer = row[I_BAN].strip(), row[I_MUA].strip()

            # detecting_cheat_by_nebula that co ~98 dong ban cho CHINH MINH (loi nhap lieu hoac
            # giao dich noi bo). Khong phai canh giao dich that -> phai loai, neu
            # khong se sinh "vong" gia do dai 1.
            if seller == buyer:
                n_self += 1
                continue

            ngay = row[I_NGAY].strip()
            g = groups[(seller, buyer, to_period(ngay))]
            g["count"] += 1
            g["amount"] += int(float(row[I_TIEN] or 0))
            g["vat"] += int(float(row[I_VAT] or 0))
            if g["first_date"] is None or ngay < g["first_date"]:
                g["first_date"] = ngay
            if g["last_date"] is None or ngay > g["last_date"]:
                g["last_date"] = ngay

    if not groups:
        raise ValueError("Khong gop duoc canh nao — kiem tra lai cot ben ban/ben mua")

    out = DATA_DIR / "trades.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["seller_mst", "buyer_mst", "period", "invoice_count",
                    "total_amount", "total_vat", "first_date", "last_date"])
        for (seller, buyer, period), g in sorted(groups.items()):
            w.writerow([seller, buyer, period, g["count"], g["amount"], g["vat"],
                        g["first_date"], g["last_date"]])

    periods = [k[2] for k in groups]
    return n_invoices, len(groups), n_self, (min(periods), max(periods))


def derive_shares_address(company_rows: list[list[str]]) -> int:
    """Suy lien ket ngam DUY NHAT co the rut ra tu detecting_cheat_by_nebula: 2 cong ty cung
    dia chi dang ky (sau chuan hoa) -> canh SHARES_ADDRESS.

    KHONG suy dien LEGAL_REP_OF / OWNS: du lieu goc khong he co nguoi dai dien
    hay so huu von, bia ra se lam sai diem so (25/100)."""
    by_addr: dict = defaultdict(list)
    for mst, _name, _sector, address, *_ in company_rows:
        norm = normalize_address(address)
        if norm:  # bo qua dia chi rong (cong ty stub, ho so khong day du)
            by_addr[norm].append(mst.strip())

    # CHOT CHAN AN TOAN — uoc tinh so cap TRUOC khi sinh.
    #
    # Vi sao can: so cap tang theo BINH PHUONG so cong ty cung 1 dia chi. Da mac
    # loi that — mot bo du lieu test sinh nham chi 600 dia chi khac nhau cho
    # 515.080 cong ty (~858 cong ty/dia chi) khien buoc nay phai sinh ~220 TRIEU
    # cap trong 1 list Python: tien trinh chay 98% CPU, RAM tang khong diem dung,
    # khong bao gio xong, phai kill tay. Uoc tinh truoc + dung som voi thong bao
    # ro rang thi loi kieu do lo ra ngay thay vi treo may am tham.
    est_pairs = sum(len(set(m)) * (len(set(m)) - 1) // 2 for m in by_addr.values())
    if est_pairs > MAX_SHARES_ADDRESS_PAIRS:
        worst_addr, worst_msts = max(by_addr.items(), key=lambda kv: len(set(kv[1])))
        raise ValueError(
            f"Du lieu dia chi bat thuong: se sinh ~{est_pairs:,} cap SHARES_ADDRESS "
            f"(nguong an toan {MAX_SHARES_ADDRESS_PAIRS:,}).\n"
            f"  {len(by_addr):,} dia chi khac nhau cho {len(company_rows):,} cong ty.\n"
            f"  Dia chi bi dung chung nhieu nhat: {len(set(worst_msts)):,} cong ty "
            f"-> {worst_addr!r}\n"
            f"Nguyen nhan thuong gap: file company.csv duoc sinh tu dong voi khong "
            f"gian dia chi qua hep. Kiem tra lai nguon du lieu truoc khi chay tiep."
        )

    rows = []
    for norm, msts in sorted(by_addr.items()):
        uniq = sorted(set(msts))
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                rows.append([uniq[i], uniq[j], norm])

    out = DATA_DIR / "shares_address.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company_a", "company_b", "norm_addr"])
        w.writerows(rows)
    return len(rows)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    progress.log(f"Bo du lieu: {os.environ.get('DATASET', DEFAULT_DATASET)} "
                 f"({COMPANY_CSV} + {INVOICE_CSV}) -> {DATA_DIR}")

    with progress.Step(1, N_STEPS, "Doc & kiem tra file cong ty") as st:
        company_rows = read_companies()
        n_company = write_companies(company_rows)
        st.metric(companies=n_company)
        progress.log(f"{n_company} cong ty -> companies.csv")

    with progress.Step(2, N_STEPS, "Gop hoa don thanh canh theo ky") as st:
        n_inv, n_edges, n_self, (p_min, p_max) = aggregate_trades()
        ratio = n_inv / n_edges if n_edges else 0
        st.metric(invoices=n_inv, edges=n_edges, self_loops=n_self,
                  period_from=p_min, period_to=p_max, reduce_ratio=round(ratio, 2))
        progress.log(f"{n_inv} hoa don -> {n_edges} canh TRADES (giam {ratio:.1f} lan), "
                     f"ky {p_min} den {p_max}")
        if n_self:
            progress.log(f"Da loai {n_self} dong ban cho chinh minh (seller == buyer)")

    with progress.Step(3, N_STEPS, "Suy lien ket dia chi chung") as st:
        n_addr = derive_shares_address(company_rows)
        st.metric(shares_address=n_addr)
        if n_addr:
            progress.log(f"{n_addr} cap cong ty trung dia chi dang ky")
        else:
            progress.log("Khong cap cong ty nao trung dia chi dang ky (da chuan hoa) "
                         "-> tin hieu 'lien ket ngam' se luon = 0 voi bo du lieu nay")

    progress.done(companies=n_company, edges=n_edges, invoices=n_inv,
                  shares_address=n_addr, period_from=p_min, period_to=p_max,
                  data_dir=str(DATA_DIR))


if __name__ == "__main__":
    main()
