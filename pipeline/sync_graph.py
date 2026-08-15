# -*- coding: utf-8 -*-
"""Nap ../data/*.csv vao NebulaGraph (INSERT VERTEX / INSERT EDGE).

Chay:
  python3 sync_graph.py                 # nap tat ca cac ky
  PERIOD=202103 python3 sync_graph.py   # chi 1 ky (mo phong sync hang thang that)

Diem thay the DUY NHAT khi noi Trino that: doi _iter_rows() (dang doc CSV) trong
cac ham sync_*() thanh 1 generator doc tung dong tu con tro SQL (vd server-side
cursor cua Trino/DB-API, KHONG fetchall). Toan bo phan con lai giu nguyen — cac
ham nay chi can 1 iterator sinh tung dict-dong, khong quan tam nguon la CSV hay
SQL, va khong bao gio giu qua 1 lo BATCH_SIZE trong RAM.

Bien moi truong: SPACE, PERIOD, BATCH_SIZE (500), DATA_DIR, NEBULA_*
"""
from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress                              # noqa: E402
from nebula_client import esc, execute, get_space, session   # noqa: E402

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE / "data"))

# Vi sao chia lo: bang cu nhet CA 8.024 canh vao 1 cau INSERT. Chay duoc o quy mo
# nay nhung se vo khi doi sang bo NhomACD (~3.900 MST, hang trieu canh) vi Nebula
# gioi han kich thuoc 1 request. Chia lo cung cho phep bao tien trinh tung phan.
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "500"))

N_STEPS = 5


def _iter_rows(path: Path):
    """Doc CSV theo tung dong (dict theo header) — KHONG nap ca file vao RAM.

    Vi sao khong dung pandas: pd.read_csv(dtype=str) nap toan bo file thanh 1
    DataFrame TRUOC KHI insert_batched kip chia lo — voi vai trieu dong, ban
    than DataFrame + list VALUES da format (buoc truoc day) giu 2 ban sao day
    du dong thoi trong RAM. Doc thang bang csv.DictReader chi giu 1 dong tai 1
    thoi diem, dung dung tinh chat "chia lo" ma insert_batched huong toi.
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def insert_batched_stream(s, prefix: str, value_iter, label: str, on_progress=None) -> int:
    """Nhu insert_batched nhung nhan 1 iterator sinh tung chuoi VALUE — chi giu
    toi da BATCH_SIZE chuoi trong RAM tai 1 thoi diem, khong bao gio giu ca danh
    sach day du."""
    n = 0
    batch: list[str] = []
    for value in value_iter:
        batch.append(value)
        if len(batch) >= BATCH_SIZE:
            execute(s, f"{prefix} VALUES {', '.join(batch)};", label)
            n += len(batch)
            if on_progress:
                on_progress(n)
            batch = []
    if batch:
        execute(s, f"{prefix} VALUES {', '.join(batch)};", label)
        n += len(batch)
        if on_progress:
            on_progress(n)
    return n


def _indexed_names(s, kind: str) -> set[str]:
    """Ten Tag/Edge da co it nhat 1 index gan vao (kind = 'TAG' hoac 'EDGE')."""
    resp = execute(s, f"SHOW {kind} INDEXES;")
    return {resp.row_values(i)[1].as_string() for i in range(resp.row_size())}


def _count_now(kind: str, label: str, match_pattern: str, indexed: set[str]) -> int:
    """Dem so dong hien co trong Nebula cho 1 Tag/Edge.

    BUG THAT DA KIEM CHUNG (05/08/2026, NebulaGraph v3.8.0 standalone): `MATCH`
    khong neo tren 1 Tag/Edge DA CO index co the tra ve SAI (0 dong) du du lieu
    that co that. Vi vay Tag/Edge nao co index thi dem bang LOOKUP (giong ky
    thuat da dung o validate_contract.py/fraud_data.go), khong index moi dung
    MATCH nhu cu.

    Dung SESSION MOI (khong phai session vua dung de INSERT) — phat hien
    07/08/2026: dem lai bang chinh session da ghi co the doc trung 1
    graphd/storaged con giu view cu (session bi ghim), trong khi mot ket noi
    moi thay dung so dong that. Neu day dung la nguyen nhan, tach session se
    doc dung tu lan dau thay vi phai doi/gian doan."""
    with session() as vs:
        if label in indexed:
            target = "id(vertex)" if kind == "TAG" else "id(edge)"
            resp = vs.execute(f"LOOKUP ON {label} YIELD {target} AS id;")
            if resp.is_succeeded():
                return resp.row_size()
        resp = vs.execute(f"MATCH {match_pattern} RETURN count(*) AS c;")
        if not resp.is_succeeded() or resp.row_size() == 0:
            return 0
        return resp.row_values(0)[0].as_int()


def _wait_until_synced(s, kind: str, label: str, match_pattern: str, expected: int,
                        tries: int = 10, sleep_s: float = 2.0) -> int:
    """Doi Nebula lan truyen du lieu XONG roi moi tra ve, thay vi tin ngay ket
    qua INSERT.

    BUG THAT DA GAP (05/08/2026): INSERT VERTEX/EDGE bao is_succeeded()=True
    ngay lap tuc, nhung tren 1 SPACE VUA TAO, storage/index chua kip lan truyen
    — dem lai ngay sau do co the ra 0 (hoac thieu) du du lieu that su da nap
    dung (kiem chung: 5544 canh TRADES nap xong trong 103ms, dem lai ngay sau
    do qua validate_contract.py ra 0). Cho 2s roi dem lai, toi da 10 lan
    (~20s) truoc khi ket luan."""
    if expected == 0:
        return 0
    indexed = _indexed_names(s, "TAG" if kind == "TAG" else "EDGE")
    n = 0
    for attempt in range(tries):
        n = _count_now(kind, label, match_pattern, indexed)
        if n >= expected:
            return n
        if attempt < tries - 1:
            progress.log(
                f"  ... da nap {expected} nhung Nebula moi xac nhan doc lai duoc "
                f"{n} {label} — cho {sleep_s:.0f}s de lan truyen roi thu lai "
                f"({attempt + 1}/{tries})")
            time.sleep(sleep_s)
    raise RuntimeError(
        f"Nap {label} bao thanh cong {expected} dong, nhung sau {tries} lan doi "
        f"(~{tries * sleep_s:.0f}s) Nebula van chi xac nhan doc lai duoc {n} dong. "
        f"Co the cluster dang qua tai/cham hon binh thuong — thu bam 'Nhap du "
        f"lieu' lai."
    )


def sync_companies(s) -> int:
    path = DATA_DIR / "companies.csv"
    if not path.exists():
        return 0

    def values():
        for r in _iter_rows(path):
            # status/established_date RONG (khong biet) -> NULL that su trong nGQL,
            # khong phai chuoi "" — de load_risky_companies() khong khop nham cong ty
            # khong co du lieu (xem ingest_csv86.py::write_companies).
            status = r.get("status", "").strip()
            status_lit = f'"{esc(status)}"' if status else "NULL"
            established = r.get("established_date", "").strip()
            established_lit = f'"{esc(established)}"' if established else "NULL"
            yield (
                f'"{r["mst"]}":("{esc(r["name"])}", "{esc(r["sector"])}", '
                f'"{esc(r["address"])}", {float(r["revenue"] or 0)}, '
                f'"{esc(r["report_date"])}", {status_lit}, {established_lit})'
            )

    return insert_batched_stream(
        s, "INSERT VERTEX Company(name, sector, address, revenue, report_date, "
           "status, established_date)",
        values(), "companies")


def sync_trades(s, period: str | None) -> tuple[int, int, int]:
    """Tra (so canh da nap, ky nho nhat, ky lon nhat)."""
    path = DATA_DIR / "trades.csv"
    if not path.exists():
        return 0, 0, 0

    p_min = p_max = None

    def values():
        nonlocal p_min, p_max
        for r in _iter_rows(path):
            if period and int(r["period"]) != int(period):
                continue
            per = int(r["period"])
            p_min = per if p_min is None else min(p_min, per)
            p_max = per if p_max is None else max(p_max, per)
            yield (
                f'"{r["seller_mst"]}" -> "{r["buyer_mst"]}"@{r["period"]}:'
                f'({r["period"]}, {int(r["invoice_count"])}, {float(r["total_amount"])}, '
                f'{float(r["total_vat"])}, "{r["first_date"]}", "{r["last_date"]}")'
            )

    def report(done_n):
        progress.log(f"  ... {done_n} canh TRADES")

    n = insert_batched_stream(
        s,
        "INSERT EDGE TRADES(period, invoice_count, total_amount, total_vat, first_date, last_date)",
        values(), "trades", report)
    if n == 0:
        return 0, 0, 0
    return n, p_min, p_max


def sync_shares_address(s) -> int:
    path = DATA_DIR / "shares_address.csv"
    if not path.exists():
        return 0

    def values():
        for r in _iter_rows(path):
            yield f'"{r["company_a"]}" -> "{r["company_b"]}"@0:("{esc(r["norm_addr"])}")'

    return insert_batched_stream(s, "INSERT EDGE SHARES_ADDRESS(norm_addr)", values(), "shares_address")


def sync_shares_phone(s) -> int:
    """Doc data/shares_phone.csv (company_a, company_b, norm_phone) — CHI
    datasource trino_gotix moi sinh ra file nay (xem
    ingest_trino_gotix.py::fetch_shares_phone); voi cac datasource CSV khac,
    file khong ton tai va ham nay tra 0, dung y het sync_shares_address()."""
    path = DATA_DIR / "shares_phone.csv"
    if not path.exists():
        return 0

    def values():
        for r in _iter_rows(path):
            yield f'"{r["company_a"]}" -> "{r["company_b"]}"@0:("{esc(r["norm_phone"])}")'

    return insert_batched_stream(s, "INSERT EDGE SHARES_PHONE(norm_phone)", values(), "shares_phone")


def sync_legal_reps(s) -> tuple[int, int]:
    """Tra (so dinh Person, so canh LEGAL_REP_OF). Doc data/legal_reps.csv
    (person_id, person_name, mst) — CHI datasource trino_gotix moi sinh ra file
    nay (xem ingest_trino_gotix.py::fetch_legal_reps); voi cac datasource CSV
    khac, file khong ton tai va ham nay tra (0, 0) — dung y het cach
    sync_shares_address() xu ly file khong ton tai.

    2 luot doc rieng file CSV (thay vi doc 1 lan roi giu trong RAM) de giu dung
    tinh chat "khong bao gio nap qua 1 batch vao RAM" cua insert_batched_stream —
    trung VID Person qua nhieu dong la BINH THUONG (nhieu cong ty chung 1 nguoi
    dai dien), INSERT VERTEX ghi de theo VID nen khong can tu dedupe truoc.
    """
    path = DATA_DIR / "legal_reps.csv"
    if not path.exists():
        return 0, 0

    def person_values():
        for r in _iter_rows(path):
            yield f'"{r["person_id"]}":("{esc(r["person_name"])}")'

    def edge_values():
        for r in _iter_rows(path):
            yield f'"{r["person_id"]}" -> "{r["mst"]}"@0:()'

    n_p = insert_batched_stream(s, "INSERT VERTEX Person(name)", person_values(), "persons")
    n_e = insert_batched_stream(s, "INSERT EDGE LEGAL_REP_OF()", edge_values(), "legal_rep_of")
    return n_p, n_e


def main() -> None:
    period = os.environ.get("PERIOD")
    space = get_space()
    progress.log(f"Nap {DATA_DIR} -> space {space}"
                 + (f" (chi ky {period})" if period else " (tat ca cac ky)"))

    with session() as s:
        with progress.Step(1, N_STEPS, "Nap dinh Company") as st:
            n_c = sync_companies(s)
            _wait_until_synced(s, "TAG", "Company", "(v:Company)", n_c)
            st.metric(companies=n_c)
            progress.log(f"{n_c} dinh Company")

        with progress.Step(2, N_STEPS, "Nap canh TRADES") as st:
            n_t, p_min, p_max = sync_trades(s, period)
            _wait_until_synced(s, "EDGE", "TRADES", "()-[e:TRADES]->()", n_t)
            st.metric(trades=n_t, period_from=p_min, period_to=p_max)
            progress.log(f"{n_t} canh TRADES (ky {p_min} den {p_max})")

        with progress.Step(3, N_STEPS, "Nap canh SHARES_ADDRESS") as st:
            n_s = sync_shares_address(s)
            _wait_until_synced(s, "EDGE", "SHARES_ADDRESS", "()-[e:SHARES_ADDRESS]->()", n_s)
            st.metric(shares_address=n_s)
            progress.log(f"{n_s} canh SHARES_ADDRESS"
                         + (" (bo du lieu nay khong co cap nao trung dia chi)" if not n_s else ""))

        with progress.Step(4, N_STEPS, "Nap canh SHARES_PHONE") as st:
            n_ph = sync_shares_phone(s)
            _wait_until_synced(s, "EDGE", "SHARES_PHONE", "()-[e:SHARES_PHONE]->()", n_ph)
            st.metric(shares_phone=n_ph)
            progress.log(f"{n_ph} canh SHARES_PHONE"
                         + (" (bo du lieu nay khong co cap nao trung SDT)" if not n_ph else ""))

        with progress.Step(5, N_STEPS, "Nap dinh Person & canh LEGAL_REP_OF") as st:
            n_p, n_lr = sync_legal_reps(s)
            _wait_until_synced(s, "EDGE", "LEGAL_REP_OF", "()-[e:LEGAL_REP_OF]->()", n_lr)
            st.metric(persons=n_p, legal_rep_of=n_lr)
            progress.log(f"{n_p} dinh Person, {n_lr} canh LEGAL_REP_OF"
                         + (" (bo du lieu nay khong co nguon nguoi dai dien)" if not n_lr else ""))

    progress.done(space=space, companies=n_c, trades=n_t,
                  shares_address=n_s, shares_phone=n_ph, persons=n_p, legal_rep_of=n_lr,
                  period_from=p_min, period_to=p_max)


if __name__ == "__main__":
    main()
