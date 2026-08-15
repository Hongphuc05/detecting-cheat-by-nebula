# -*- coding: utf-8 -*-
"""Gan co is_circular cho TUNG hoa don thuc (khong phai tung canh da GOP) thuoc cac
chu trinh da phat hien — dau ra invoice_flags_min_len*.jsonl dung schema yeu cau
trong detecting_cheat_by_nebula/output/Ghi_Chu_Nebula_Output.md muc 3.2:
  {"einvoice_row_id": ..., "is_circular": true, "cycle_ids": [...]}

VI SAO TACH THANH SCRIPT RIENG (khong lam luon trong detect_circular_trading.py):
trades.csv da GOP nhieu hoa don thuc thanh 1 canh (seller, buyer, period) tu buoc
ingest (SUM(tien)/COUNT(so_hd)) — detect_circular_trading.py chi doc duoc canh da
gop tu Nebula, KHONG con giu einvoice_row_id goc. Muon tra nguoc ve tung hoa don
phai truy van lai Trino (nguon that cua einvoice_invoice), nen tach thanh 1 buoc
doc lap, chay SAU detect_circular_trading.py (dung dung file graph_risk_flags*.jsonl
no da sinh ra lam input, khong doc lai tu Nebula).

Chay:
  IN_FILE=../output/graph_risk_flags_202301_202312.jsonl \
  PERIOD_FROM=202301 PERIOD_TO=202312 python3 export_invoice_flags.py

Bien moi truong:
  IN_FILE (bat buoc)          duong dan graph_risk_flags*.jsonl da sinh tu detect_circular_trading.py
  PERIOD_FROM/PERIOD_TO (bat buoc)  dung de dat ten file dau ra, khop voi detect
  OUT_DIR                     mac dinh = thu muc chua IN_FILE
  FLAG_THRESHOLD               diem toi thieu (thang 0-100) de coi 1 chu trinh la
                               "dang flag" -> moi gan co cho hoa don cua no. Mac dinh
                               = WATCH_THRESHOLD (40) cua detect_circular_trading.py.
                               QUYET DINH TU CHON (khong co san trong yeu cau goc,
                               Ghi_Chu_Nebula_Output.md khong noi ro nguong nao) —
                               ghi ro o day de de doi, KHONG bia la "dung chuan".
  TRINO_HOST/PORT/USER/CATALOG  giong ingest_trino_gotix.py (mac dinh localhost:18082)

PHU THUOC: can `pip install trino`, giong ingest_trino_gotix.py — xem CLAUDE.md
muc "Tech stack" cua du an nay.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress                                          # noqa: E402
from detect_circular_trading import WATCH_THRESHOLD       # noqa: E402 - tai dung nguong co san

TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
TRINO_PORT = int(os.environ.get("TRINO_PORT", "18082"))
TRINO_USER = os.environ.get("TRINO_USER", "gotix_sync")
TRINO_CATALOG = os.environ.get("TRINO_CATALOG", "nessie")

# Dung KHOP DUNG dieu kien loc cua SQL_TRADES trong ingest_trino_gotix.py — neu
# lech loc, canh dung de dung do thi va hoa don tra nguoc se KHONG con khop nhau.
_VOID_STATUSES = ("Hóa đơn đã bị thay thế", "Hóa đơn đã bị xóa bỏ/hủy bỏ")
LOOKUP_BATCH = 300  # so triple (seller,buyer,period) moi lan query IN-list

N_STEPS = 3


def _sql_str(v: str) -> str:
    """Escape string literal cho Trino SQL — mst la vertex id tu Nebula, khong nen
    gia dinh chac chan chi co chu so."""
    return "'" + str(v).replace("'", "''") + "'"


def _connect():
    from trino.dbapi import connect  # import cuc bo — bao loi ro rang neu chua cai package

    return connect(host=TRINO_HOST, port=TRINO_PORT, user=TRINO_USER,
                   catalog=TRINO_CATALOG, schema="tier2")


def load_cycles(in_file: Path, threshold: float) -> list[dict]:
    cycles = []
    with open(in_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            if c.get("score", 0) >= threshold:
                cycles.append(c)
    return cycles


def cycle_edges(cycles: list[dict]) -> dict[tuple, list[str]]:
    """(seller, buyer, period) -> danh sach cycle_id (khoa = members noi bang '|')
    di qua canh nay. 1 canh co the thuoc nhieu chu trinh chong lap nhau.

    Quy uoc chi so (giong canonicalize()/score_cycle() trong detect_circular_trading.py):
    periods[i] la ky cua canh members[i] -> members[(i+1) % hop_len]."""
    edge_cycles: dict[tuple, list[str]] = {}
    for c in cycles:
        members, periods = c["members"], c["periods"]
        cid = "|".join(members)
        length = len(members)
        for i in range(length):
            edge = (members[i], members[(i + 1) % length], int(periods[i]))
            edge_cycles.setdefault(edge, []).append(cid)
    return edge_cycles


def fetch_invoice_ids(conn, triples: list[tuple]) -> dict[tuple, list[str]]:
    """triples -> {(seller,buyer,period): [einvoice_row_id, ...]} tra tu Trino."""
    cur = conn.cursor()
    out: dict[tuple, list[str]] = {}
    for i in range(0, len(triples), LOOKUP_BATCH):
        batch = triples[i:i + LOOKUP_BATCH]
        values = ", ".join(f"({_sql_str(s)}, {_sql_str(b)}, {p})" for s, b, p in batch)
        sql = f"""
            SELECT einvoice_row_id, mst_ban_goc, mst_mua_goc,
                   CAST(date_format(CAST(ngay_lap AS TIMESTAMP), '%Y%m') AS INTEGER) AS period
            FROM einvoice_invoice
            WHERE chieu = 'ban'
              AND ky_hieu_mau_so IN ('1', '2')
              AND trang_thai_hd NOT IN ({_sql_str(_VOID_STATUSES[0])}, {_sql_str(_VOID_STATUSES[1])})
              AND (mst_ban_goc, mst_mua_goc,
                   CAST(date_format(CAST(ngay_lap AS TIMESTAMP), '%Y%m') AS INTEGER)) IN ({values})
        """
        cur.execute(sql)
        for row in cur.fetchall():
            key = (row[1], row[2], int(row[3]))
            out.setdefault(key, []).append(row[0])
    return out


def main() -> None:
    in_file = Path(os.environ["IN_FILE"])
    period_from = int(os.environ["PERIOD_FROM"])
    period_to = int(os.environ["PERIOD_TO"])
    out_dir = Path(os.environ.get("OUT_DIR", in_file.parent))
    threshold = float(os.environ.get("FLAG_THRESHOLD", WATCH_THRESHOLD))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"invoice_flags_min_len3_{period_from}_{period_to}.jsonl"

    with progress.Step(1, N_STEPS, "Đọc chu trình đã phát hiện") as st:
        cycles = load_cycles(in_file, threshold)
        edge_cycles = cycle_edges(cycles)
        st.metric(cycles=len(cycles), edges=len(edge_cycles), threshold=threshold)
        progress.log(f"{len(cycles)} chu trình >= {threshold} điểm (FLAG_THRESHOLD) "
                     f"-> {len(edge_cycles)} cạnh cần tra ngược hóa đơn")

    if not edge_cycles:
        open(out_file, "w", encoding="utf-8").close()
        progress.log("Không có chu trình đạt ngưỡng flag -> invoice_flags rỗng")
        progress.done(out_file=str(out_file), invoices=0, cycles=len(cycles))
        return

    with progress.Step(2, N_STEPS, "Tra ngược hóa đơn thật từ Trino") as st:
        conn = _connect()
        invoice_map = fetch_invoice_ids(conn, list(edge_cycles.keys()))
        n_invoices = sum(len(v) for v in invoice_map.values())
        st.metric(edges_matched=len(invoice_map), invoices=n_invoices)
        progress.log(f"{n_invoices} hóa đơn thật khớp {len(invoice_map)}/{len(edge_cycles)} cạnh "
                     f"(cạnh không khớp: hóa đơn có thể đã bị lọc/hủy sau khi Nebula đã nạp)")

    with progress.Step(3, N_STEPS, "Ghi cờ theo từng hóa đơn") as st:
        row_cycles: dict[str, set] = {}
        for edge, row_ids in invoice_map.items():
            cids = edge_cycles.get(edge, [])
            for rid in row_ids:
                row_cycles.setdefault(rid, set()).update(cids)
        with open(out_file, "w", encoding="utf-8") as f:
            for rid, cids in row_cycles.items():
                f.write(json.dumps({
                    "einvoice_row_id": rid, "is_circular": True,
                    "cycle_ids": sorted(cids),
                }, ensure_ascii=False) + "\n")
        st.metric(invoices=len(row_cycles), out_file=str(out_file))

    progress.log(f"{len(row_cycles)} hóa đơn được gắn cờ is_circular -> {out_file.name}")
    progress.done(out_file=str(out_file), invoices=len(row_cycles), cycles=len(cycles))


if __name__ == "__main__":
    main()
