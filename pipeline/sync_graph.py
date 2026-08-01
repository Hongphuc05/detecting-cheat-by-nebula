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

N_STEPS = 3


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


def sync_companies(s) -> int:
    path = DATA_DIR / "companies.csv"
    if not path.exists():
        return 0

    def values():
        for r in _iter_rows(path):
            yield (
                f'"{r["mst"]}":("{esc(r["name"])}", "{esc(r["sector"])}", '
                f'"{esc(r["address"])}", {float(r["revenue"] or 0)}, '
                f'"{esc(r["report_date"])}")'
            )

    return insert_batched_stream(
        s, "INSERT VERTEX Company(name, sector, address, revenue, report_date)",
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


def main() -> None:
    period = os.environ.get("PERIOD")
    space = get_space()
    progress.log(f"Nap {DATA_DIR} -> space {space}"
                 + (f" (chi ky {period})" if period else " (tat ca cac ky)"))

    with session() as s:
        with progress.Step(1, N_STEPS, "Nap dinh Company") as st:
            n_c = sync_companies(s)
            st.metric(companies=n_c)
            progress.log(f"{n_c} dinh Company")

        with progress.Step(2, N_STEPS, "Nap canh TRADES") as st:
            n_t, p_min, p_max = sync_trades(s, period)
            st.metric(trades=n_t, period_from=p_min, period_to=p_max)
            progress.log(f"{n_t} canh TRADES (ky {p_min} den {p_max})")

        with progress.Step(3, N_STEPS, "Nap canh SHARES_ADDRESS") as st:
            n_s = sync_shares_address(s)
            st.metric(shares_address=n_s)
            progress.log(f"{n_s} canh SHARES_ADDRESS"
                         + (" (bo du lieu nay khong co cap nao trung dia chi)" if not n_s else ""))

    progress.done(space=space, companies=n_c, trades=n_t,
                  shares_address=n_s, period_from=p_min, period_to=p_max)


if __name__ == "__main__":
    main()
