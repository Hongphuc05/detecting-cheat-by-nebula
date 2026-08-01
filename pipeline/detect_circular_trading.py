# -*- coding: utf-8 -*-
"""Phat hien giao dich mua ban long vong (circular trading) — 4 buoc lõi.

  Buoc 1  Khoanh vung seed   : cong ty VUA BAN VUA MUA moi co the nam trong vong
  Buoc 2  Do chu trinh        : DFS trong ung dung (mac dinh) hoac MATCH trong Nebula
  Buoc 3  Khu trung lap       : xoay ve dang chuan, giu to hop canh diem CAO NHAT
  Buoc 4  Cham diem 0-100     : 5 tin hieu co trong so

Chay:
  PERIOD_FROM=202011 PERIOD_TO=202112 python3 detect_circular_trading.py
  MAX_HOPS=3 METHOD=match python3 detect_circular_trading.py

Bien moi truong:
  PERIOD_FROM, PERIOD_TO   bat buoc, dang yyyymm
  SPACE                    space Nebula (mac dinh invoice_agg_graph)
  METHOD                   dfs (mac dinh) | match
  MAX_HOPS                 do dai vong toi da, mac dinh 5 (chi dung cho dfs)
  HOP_LENGTHS              danh sach do dai co dinh cho METHOD=match, mac dinh "3"
  MAX_SEEDS, CYCLES_PER_SEED_LIMIT   chi dung cho METHOD=match
  OUT_FILE                 duong dan file .jsonl ket qua
  NO_PRUNE=1               tat cat nhanh (cham hon nhieu, dung de kiem toan)

=========================================================================
NGUON DU LIEU: DOC TU NEBULA, KHONG DOC CSV
=========================================================================
Ban truoc doc adjacency tu ../data/trades.csv. Da bo vi mot bay nguy hiem: khi
giao dien cho chon space, nguoi dung chon `tax_graph` nhung script van doc CSV
cua detecting_cheat_by_nebula -> phan tich NHAM du lieu ma KHONG he bao loi, bao cao ra van
trong nhu that. Doc thang tu space da chon thi khong the lech.
Chi phi: 1 cau LOOKUP dung index, do that 7.945 canh / 0,33 giay.

=========================================================================
CHAM DIEM: DAY DU 5 TIN HIEU, TU THICH UNG THEO DU LIEU CO SAN
=========================================================================
Ban truoc go cung `score_risky = 0` cho rieng detecting_cheat_by_nebula. Da bo: script tu do
xem space co LEGAL_REP_OF / OWNS / SHARES_ADDRESS / status / established_date
hay khong roi cham dung theo cai co that. Nho vay:
  - Chay tren detecting_cheat_by_nebula (thieu DKKD) -> tran diem 60/100, dung nhu validate bao.
  - Chay tren tax_graph (du DKKD)      -> dat thang 100/100, khong phai sua code.
  - Khi DKKD that ve, chi can nap them canh, KHONG dong vao file nay.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress                                          # noqa: E402
from nebula_client import as_num, get_space, session     # noqa: E402

N_STEPS = 4

# Trong so 5 tin hieu — DINH NGHIA MOT CHO DUY NHAT. validate_contract.py doc
# cung bo so nay de tinh tran diem; lech nhau se bi test nghiem thu bat.
W_BALANCE, W_TIME, W_HIDDEN, W_RISKY, W_VAT = 30.0, 20.0, 25.0, 15.0, 10.0
RED_THRESHOLD, WATCH_THRESHOLD = 60.0, 40.0


# ---------------------------------------------------------------------------
# Nap du lieu tu Nebula
# ---------------------------------------------------------------------------

def _edge_types(s) -> set[str]:
    r = s.execute("SHOW EDGES;")
    return {r.row_values(i)[0].as_string() for i in range(r.row_size())} if r.is_succeeded() else set()


def _tag_props(s, tag: str) -> set[str]:
    r = s.execute(f"DESCRIBE TAG {tag};")
    return {r.row_values(i)[0].as_string() for i in range(r.row_size())} if r.is_succeeded() else set()


def load_adjacency(s, period_from: int, period_to: int) -> tuple[dict, int]:
    """seller -> [(buyer, period, amount, vat), ...] cho cac canh trong cua so ky.

    Dung LOOKUP (co index TRADES(period)) thay vi MATCH quet toan bang: cung toc do
    o quy mo nay nhung khong dam vao canh bao "cam quet khong neo" cua space day dac.
    """
    r = s.execute(
        f"LOOKUP ON TRADES WHERE TRADES.period >= {period_from} AND TRADES.period <= {period_to} "
        f"YIELD src(edge) AS a, dst(edge) AS b, properties(edge).period AS p, "
        f"properties(edge).total_amount AS amt, properties(edge).total_vat AS vat;")

    if not r.is_succeeded():
        # LOOKUP bat buoc phai co index TRADES(period). Space chua tao index
        # (validate_contract.py bao muc 4.1.index = empty) van phai chay duoc.
        #
        # Luu y da kiem chung: KHONG the lui ve `MATCH ... WHERE e.period >= x` —
        # Nebula cung doi index cho moi bo loc theo thuoc tinh canh
        # ("IndexNotFound: No valid index found"). Cach duy nhat khong can index
        # la neo vao Tag roi LOC KY O PHIA CLIENT.
        # Danh doi: keo ve TOAN BO canh roi moi loc -> ton bang thong hon nhieu
        # tren du lieu lon. Chap nhan duoc vi day la duong lui, khong phai duong
        # chinh; tao index se tu quay lai nhanh LOOKUP.
        progress.log(f"Khong co index TRADES(period) — lui ve quet theo Tag, loc ky o client "
                     f"(cham hon; tao index de nhanh hon)")
        r = s.execute("MATCH (a:Company)-[e:TRADES]->(b:Company) "
                      "RETURN id(a) AS a, id(b) AS b, e.period AS p, "
                      "e.total_amount AS amt, e.total_vat AS vat;")
    if not r.is_succeeded():
        raise RuntimeError(f"Khong doc duoc canh TRADES: {r.error_msg()}")

    adj: dict = {}
    n = 0
    for i in range(r.row_size()):
        row = r.row_values(i)
        a, b = row[0].as_string(), row[1].as_string()
        p = row[2].as_int()
        if a == b:                              # tu ban cho chinh minh — khong phai giao dich
            continue
        if not (period_from <= p <= period_to):  # can cho duong lui (LOOKUP da loc san)
            continue
        adj.setdefault(a, []).append(
            (b, p, as_num(row[3]), as_num(row[4])))
        n += 1
    return adj, n


def load_hidden_link_pairs(s) -> tuple[set, list[str]]:
    """Nap TRUOC toan bo cap cong ty co lien ket ngam vao bo nho (1 lan).

    Vi sao khong truy van tung cap khi cham diem: 2.429 chu trinh x ~10 cap =
    ~24.000 luot round-trip toi Nebula — cham hon ca buoc do chu trinh. Nap truoc
    1 lan cho ket qua y het voi chi phi khong dang ke.
    """
    edges = _edge_types(s)
    pairs: set = set()
    sources: list[str] = []

    def collect(q: str, label: str):
        r = s.execute(q)
        if not r.is_succeeded():
            return
        before = len(pairs)
        for i in range(r.row_size()):
            row = r.row_values(i)
            pairs.add(frozenset((row[0].as_string(), row[1].as_string())))
        if len(pairs) > before:
            sources.append(f"{label} ({len(pairs) - before} cap)")

    if "SHARES_ADDRESS" in edges:
        collect("MATCH (a:Company)-[:SHARES_ADDRESS]-(b:Company) RETURN id(a), id(b);",
                "chung dia chi")
    if "OWNS" in edges:
        collect("MATCH (a:Company)-[:OWNS]-(b:Company) RETURN id(a), id(b);",
                "so huu von")
    if "LEGAL_REP_OF" in edges:
        # 2 cong ty chung 1 nguoi dai dien phap luat
        collect("MATCH (a:Company)<-[:LEGAL_REP_OF]-(p)-[:LEGAL_REP_OF]->(b:Company) "
                "WHERE id(a) < id(b) RETURN id(a), id(b);", "chung nguoi dai dien")

    pairs.discard(frozenset())          # loai cap rong neu co
    return {p for p in pairs if len(p) == 2}, sources


def load_risky_companies(s) -> tuple[set, str]:
    """Tap MST bi coi la rui ro: DN moi thanh lap hoac khong con hoat dong.
    Tu do theo cot co that tren Tag Company — thieu cot thi tra tap rong."""
    props = _tag_props(s, "Company")
    conds = []
    if "is_new_company" in props:
        conds.append("c.Company.is_new_company == true")
    if "status" in props:
        conds.append('c.Company.status != "active"')
    if not conds:
        return set(), ""

    q = f"MATCH (c:Company) WHERE {' OR '.join(conds)} RETURN id(c);"
    r = s.execute(q)
    if not r.is_succeeded():
        return set(), ""
    return ({r.row_values(i)[0].as_string() for i in range(r.row_size())},
            " hoac ".join(conds))


# ---------------------------------------------------------------------------
# Buoc 1 — Khoanh vung seed
# ---------------------------------------------------------------------------

def find_seeds(adj: dict) -> tuple[list[str], int]:
    """Cong ty chi co the nam trong chu trinh neu VUA BAN VUA MUA trong cua so ky.
    Ban san xuat that: 1 cau SQL re tren Trino."""
    sellers = set(adj)
    buyers = {b for outs in adj.values() for (b, *_rest) in outs}
    return sorted(sellers & buyers), len(sellers | buyers)


# ---------------------------------------------------------------------------
# Buoc 2 — Do chu trinh
# ---------------------------------------------------------------------------

def month_idx(p) -> int:
    p = int(p)
    return (p // 100) * 12 + (p % 100)


def score_components(amounts: list, periods: list, vats: list) -> tuple[float, float, float]:
    """3 thanh phan phu thuoc TO HOP CANH cu the (khac voi 2 thanh phan chi phu
    thuoc TAP THANH VIEN). Dung chung boi buoc khu trung lap va buoc cham diem
    -> cong thuc chi ton tai o DUNG MOT CHO, khong the lech nhau."""
    # (1) Can bang gia tri: tien di het vong gan nguyen ven = dong tien ao
    mx = max(amounts) if amounts else 0
    ratio = (min(amounts) / mx) if mx else 0
    s_balance = W_BALANCE if ratio >= 0.8 else max(0.0, W_BALANCE * (ratio - 0.3) / 0.5)

    # (2) Nen thoi gian: ca vong dien ra gon trong 1-2 ky
    span = max(map(month_idx, periods)) - min(map(month_idx, periods))
    s_time = W_TIME if span <= 1 else max(0.0, W_TIME - span * 5.0)

    # (3) VAT bat thuong: ty le VAT/tien lech nhieu so voi trung vi trong vong
    rates = [v / a for v, a in zip(vats, amounts) if a]
    if rates:
        med = sorted(rates)[len(rates) // 2]
        s_vat = W_VAT if max(abs(r - med) for r in rates) > 0.03 else 0.0
    else:
        s_vat = 0.0
    return s_balance, s_time, s_vat


def prune_bound(has_hidden: bool, has_risky: bool) -> float:
    """Nguong cat nhanh KHONG MAT MAT, suy tu TRONG SO va tu DU LIEU CO THAT.

    Mot nhanh chi bo duoc neu diem TOI DA no con co the dat < nguong co do:
        balance + time + (VAT toi da) + (hidden + risky CO THE DAT) < 60

    Cho "co the dat": neu ca space khong co MOT cap lien ket ngam nao, thi khong
    chu trinh nao co the an 25 diem do — tru han ra khoi can tren van la chinh xac
    tuyet doi, khong mat chu trinh nao.

    Vi sao phai lam vay (bai hoc dat gia, do that): coi hidden+risky LUON co the
    dat duoc thi nguong = 60-10-40 = 10, qua long, DFS tren detecting_cheat_by_nebula chay >5 phut
    chua xong. Suy theo du lieu that (detecting_cheat_by_nebula khong co ca hai) thi nguong = 50
    va chay het 16 giay. Cung ket qua, nhanh hon ~20 lan.

    Ban cu go cung `W_RISKY = 0` de dat hieu ung nay — dung cho detecting_cheat_by_nebula nhung
    SAI cho space co du DKKD (se cat mat chu trinh that). Cach nay dung cho ca hai.
    """
    if os.environ.get("NO_PRUNE"):
        return float("-inf")
    achievable = (W_HIDDEN if has_hidden else 0.0) + (W_RISKY if has_risky else 0.0)
    return RED_THRESHOLD - W_VAT - achievable


def enumerate_cycles_dfs(adj: dict, max_hops: int, bound: float, min_len: int = 3) -> list[dict]:
    """DFS voi 2 co che cat nhanh:
      1. Cat don dieu theo diem (prune_bound) — khong mat mat, chung minh o tren.
      2. Meo Johnson: chi di qua dinh >= dinh xuat phat -> moi chu trinh chi gap
         dung 1 lan cho moi to hop canh.
    """
    out = []
    for start in sorted(adj):
        stack = [(start, [start], [], [], [])]
        while stack:
            v, verts, periods, amounts, vats = stack.pop()
            for (w, p, amt, vat) in adj.get(v, ()):
                if w < start:                    # Johnson: khu trung lap mien phi
                    continue
                np_, na = periods + [p], amounts + [amt]
                s_b, s_t, _ = score_components(na, np_, [0] * len(na))
                if s_b + s_t < bound:            # cat nhanh don dieu
                    continue
                nv = vats + [vat]
                if w == start:
                    if len(verts) >= min_len:
                        out.append({"members": verts, "amounts": na, "periods": np_, "vats": nv})
                    continue
                if w in verts:                   # cac dinh phai phan biet
                    continue
                if len(verts) < max_hops:
                    stack.append((w, verts + [w], np_, na, nv))
    return out


def build_fixed_hop_query(seed: str, hop_len: int, period_from: int, period_to: int, limit: int) -> str:
    """Sinh MATCH voi dung `hop_len` canh lien tiep, liet ke tuong minh tung bien
    canh — KHONG dung cu phap bien thien do dai `*`.

    Vi sao cam `*`: xem nebula_demo/schemas/invoice_graph.md — space nay tung lam
    CRASH server nhieu lan voi `*2..4`, KE CA khi da neo id() va gioi han hop, vi
    cac dinh hub co bac qua cao.
    """
    mids = [f"c{i}" for i in range(1, hop_len)]
    evars = [f"e{i}" for i in range(1, hop_len + 1)]
    nodes = ["v"] + mids + ["v"]

    pattern = "(v:Company)"
    for i, ev in enumerate(evars):
        tag = ":Company" if i < hop_len - 1 else ""
        pattern += f"-[{ev}:TRADES]->({nodes[i + 1]}{tag})"

    conds = [f"rank({ev}) >= {period_from} AND rank({ev}) <= {period_to}" for ev in evars]
    # Cac dinh trung gian phai phan biet nhau va phan biet voi seed, neu khong se
    # ra "vong" gia kieu [X, C, C].
    conds += [f"id({mids[i]}) != id({mids[j]})"
              for i in range(len(mids)) for j in range(i + 1, len(mids))]
    conds += [f'id({m}) != "{seed}"' for m in mids]

    return (f"MATCH p = {pattern} WHERE id(v) == \"{seed}\" AND {' AND '.join(conds)} "
            f"RETURN [{', '.join(f'id({n})' for n in nodes)}] AS msts, "
            f"[{', '.join(f'{e}.total_amount' for e in evars)}] AS amounts, "
            f"[{', '.join(f'{e}.period' for e in evars)}] AS periods, "
            f"[{', '.join(f'{e}.total_vat' for e in evars)}] AS vats LIMIT {limit};")


def enumerate_cycles_match(s, seeds: list[str], hop_lengths: list[int],
                           period_from: int, period_to: int, limit: int) -> list[dict]:
    out = []
    for i, seed in enumerate(seeds):
        for hop in hop_lengths:
            r = s.execute(build_fixed_hop_query(seed, hop, period_from, period_to, limit))
            if not r.is_succeeded():
                progress.log(f"  bo qua seed {seed} hop {hop}: {r.error_msg()[:80]}")
                continue
            for row in r.as_primitive():
                out.append({
                    "members": list(row["msts"])[:-1],   # bo phan tu cuoi (= dau, khep vong)
                    "amounts": list(row["amounts"]),
                    "periods": list(row["periods"]),
                    "vats": list(row["vats"]),
                })
        if (i + 1) % 20 == 0:
            progress.log(f"  ... da quet {i + 1}/{len(seeds)} seed")
    return out


# ---------------------------------------------------------------------------
# Buoc 3 — Khu trung lap
# ---------------------------------------------------------------------------

def canonicalize(c: dict) -> tuple[tuple[str, ...], dict]:
    """Xoay chu trinh ve dang chuan (MST nho nhat dung dau) va tra ve ban da xoay.

    Mot vong vat ly A-B-C == B-C-A == C-A-B, phai dem dung 1 lan -> can dang chuan.

    ====================================================================
    PHAI XOAY CA 4 MANG CUNG LUC — day la loi da xay ra that
    ====================================================================
    `amounts[i]` / `periods[i]` / `vats[i]` mo ta canh di TU members[i] TOI
    members[i+1]. Neu chi xoay `members` ma giu nguyen 3 mang kia thi chi so lech
    nhau, va:
      - Diem so VAN DUNG (balance/time/vat deu la min/max/trung vi — khong phu
        thuoc thu tu) nen loi KHONG lo ra o bao cao.
      - Nhung cau nGQL ve do thi ghim `rank(e) == periods[i]` se tro sai ky, ve
        ra vong THIEU CANH ma khong bao loi gi.

    Do that tren duong METHOD=match: 122/318 chu trinh bi lech.
    Duong METHOD=dfs khong lo ra vi meo Johnson chi di qua dinh >= dinh xuat phat,
    nen members[0] von da la MST nho nhat, xoay 0 buoc. Chinh vi vay loi nay am
    rat lau — chi 1 trong 2 duong bi dinh.
    """
    members = c["members"]
    i = members.index(min(members))
    if i == 0:
        return tuple(members), c
    rot = lambda xs: xs[i:] + xs[:i]  # noqa: E731
    return tuple(rot(members)), {
        "members": rot(members),
        "amounts": rot(c["amounts"]),
        "periods": rot(c["periods"]),
        "vats": rot(c["vats"]),
    }


def dedupe(all_cycles: list[dict]) -> dict:
    """dang chuan -> to hop canh co DIEM CAO NHAT trong nhom.

    QUAN TRONG: giu "to hop gap dau tien" la BUG lam DEM THIEU co do. Giua 2 cong
    ty co nhieu canh (moi ky 1 canh) nen cung 1 nhom cong ty tao duoc nhieu to hop
    khac diem. Do that tren detecting_cheat_by_nebula o 3 hop: giu-dau-tien = 23 co do,
    giu-cao-nhat = 99 co do — dem thieu 4,3 lan.
    """
    best: dict = {}
    best_score: dict = {}
    for c in all_cycles:
        key, rotated = canonicalize(c)
        sc = sum(score_components(rotated["amounts"], rotated["periods"], rotated["vats"]))
        if key not in best or sc > best_score[key]:
            best[key], best_score[key] = rotated, sc
    return best


# ---------------------------------------------------------------------------
# Buoc 4 — Cham diem
# ---------------------------------------------------------------------------

def score_cycle(key: tuple[str, ...], c: dict, hidden_pairs: set, risky: set) -> dict:
    s_balance, s_time, s_vat = score_components(c["amounts"], c["periods"], c["vats"])

    # (4) Lien ket ngam — nhi phan: chi can 1 cap bat ky trong vong co lien ket
    s_hidden = W_HIDDEN if (hidden_pairs and any(
        frozenset((a, b)) in hidden_pairs
        for i, a in enumerate(key) for b in key[i + 1:])) else 0.0

    # (5) Thanh vien rui ro — nhi phan: 1 thanh vien la DN moi/bo tron la du
    s_risky = W_RISKY if (risky and any(m in risky for m in key)) else 0.0

    return {
        "members": list(key),
        "hop_len": len(key),
        "score": round(s_balance + s_time + s_hidden + s_risky + s_vat, 1),
        "score_balance": round(s_balance, 1),
        "score_time": round(s_time, 1),
        "score_hidden_link": s_hidden,
        "score_risky_member": s_risky,
        "score_vat": s_vat,
        "amounts": c["amounts"],
        "periods": c["periods"],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    period_from = int(os.environ["PERIOD_FROM"])
    period_to = int(os.environ["PERIOD_TO"])
    method = os.environ.get("METHOD", "dfs").lower()
    if method not in ("dfs", "match"):
        raise SystemExit("METHOD phai la 'dfs' hoac 'match'")
    max_hops = int(os.environ.get("MAX_HOPS", "5"))
    space = get_space()

    out_file = Path(os.environ.get(
        "OUT_FILE",
        Path(__file__).resolve().parent.parent / "output" /
        f"graph_risk_flags_{period_from}_{period_to}.jsonl"))
    out_file.parent.mkdir(parents=True, exist_ok=True)

    progress.log(f"Space {space} | ky {period_from}-{period_to} | "
                 f"phuong phap {method} | toi da {max_hops} chang")

    with session() as s:
        # ---- Buoc 1 -------------------------------------------------------
        with progress.Step(1, N_STEPS, "Khoanh vùng & kiểm kê tín hiệu") as st:
            adj, n_edges = load_adjacency(s, period_from, period_to)
            if not adj:
                raise RuntimeError(
                    f"Khong co canh TRADES nao trong ky {period_from}-{period_to}")
            seeds, n_total = find_seeds(adj)
            pruned = 100 * (1 - len(seeds) / n_total) if n_total else 0

            # Nap 2 nguon tin hieu chi phu thuoc TAP THANH VIEN ngay tu day (khong
            # doi den buoc 4): can biet chung CO TON TAI khong de suy nguong cat
            # nhanh cho buoc 2 — xem prune_bound().
            hidden_pairs, hp_src = load_hidden_link_pairs(s)
            risky, risky_src = load_risky_companies(s)

            max_score = (W_BALANCE + W_TIME + W_VAT
                         + (W_HIDDEN if hidden_pairs else 0.0)
                         + (W_RISKY if risky else 0.0))

            st.metric(edges=n_edges, companies=n_total, seeds=len(seeds),
                      pruned_pct=round(pruned, 1),
                      max_achievable_score=int(max_score))
            progress.log(f"{n_edges} canh · {n_total} cong ty co giao dich "
                         f"-> {len(seeds)} seed (vua ban vua mua), da loai {pruned:.0f}%")
            if pruned < 20:
                progress.log("Ty le loai thap — do thi kha day dac, buoc do se ton "
                             "nhieu thoi gian hon do thi thua")
            progress.log(
                f"Lien ket ngam: {', '.join(hp_src)}" if hidden_pairs
                else f"Khong co du lieu lien ket ngam -> tin hieu nay luon 0 (mat {W_HIDDEN:.0f} diem)")
            progress.log(
                f"Thanh vien rui ro: {len(risky)} cong ty ({risky_src})" if risky
                else f"Khong co du lieu DN moi/bo tron -> tin hieu nay luon 0 (mat {W_RISKY:.0f} diem)")
            if max_score < 100:
                progress.log(f"=> TRAN DIEM cua bo du lieu nay: {max_score:.0f}/100")

        # ---- Buoc 2 -------------------------------------------------------
        with progress.Step(2, N_STEPS, "Dò chu trình khép kín") as st:
            if method == "dfs":
                b = prune_bound(bool(hidden_pairs), bool(risky))
                progress.log(f"DFS trong ung dung · cat nhanh tai balance+time < {b:.0f} "
                             f"(suy tu trong so + du lieu co that, khong mat mat) · "
                             f"khong gioi han so ket qua")
                raw = enumerate_cycles_dfs(adj, max_hops, b)
                src = f"{len(adj)} dinh co canh di ra"
            else:
                hops = [int(x) for x in os.environ.get("HOP_LENGTHS", "3").split(",")]
                limit = int(os.environ.get("CYCLES_PER_SEED_LIMIT", "50"))
                seeds = seeds[:int(os.environ.get("MAX_SEEDS", "5000"))]
                if max(hops) > 3:
                    progress.log(f"CANH BAO: hop {hops} vuot muc 3 da kiem chung an toan "
                                 f"cho space day dac — co the tran bo nho")
                progress.log(f"MATCH trong Nebula · chuoi hop co dinh {hops} · "
                             f"gioi han {limit} ket qua/seed -> KET QUA CO THE BI CAT CUT")
                raw = enumerate_cycles_match(s, seeds, hops, period_from, period_to, limit)
                src = f"{len(seeds)} seed"
            st.metric(raw_cycles=len(raw), source=src)
            progress.log(f"{len(raw)} lan xuat hien chu trinh (tu {src})")

        # ---- Buoc 3 -------------------------------------------------------
        with progress.Step(3, N_STEPS, "Khử trùng lặp") as st:
            unique = dedupe(raw)
            st.metric(unique=len(unique), removed=len(raw) - len(unique))
            progress.log(f"{len(raw)} -> {len(unique)} chu trinh duy nhat "
                         f"(giu to hop canh diem cao nhat moi nhom)")

        # ---- Buoc 4 -------------------------------------------------------
        with progress.Step(4, N_STEPS, "Chấm điểm rủi ro 0-100") as st:
            # hidden_pairs / risky da nap o buoc 1 (can cho nguong cat nhanh)
            scored = [score_cycle(k, c, hidden_pairs, risky) for k, c in unique.items()]
            scored.sort(key=lambda x: (-x["score"], x["members"]))

            n_red = sum(1 for x in scored if x["score"] >= RED_THRESHOLD)
            n_watch = sum(1 for x in scored if WATCH_THRESHOLD <= x["score"] < RED_THRESHOLD)

            with open(out_file, "w", encoding="utf-8") as f:
                for x in scored:
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")

            st.metric(total=len(scored), red=n_red, watch=n_watch,
                      max_achievable_score=int(max_score),
                      top_score=scored[0]["score"] if scored else 0)

    progress.log(f"Tong {len(scored)} chu trinh · co do (>={RED_THRESHOLD:.0f}): {n_red} · "
                 f"theo doi ({WATCH_THRESHOLD:.0f}-{RED_THRESHOLD:.0f}): {n_watch}")
    if scored and scored[0]["score"] < max_score:
        progress.log(f"Diem cao nhat: {scored[0]['score']}/{max_score:.0f} "
                     f"(tran diem cua bo du lieu nay la {max_score:.0f}/100)")

    progress.done(space=space, out_file=str(out_file), total=len(scored),
                  red=n_red, watch=n_watch, max_achievable_score=int(max_score),
                  top_score=scored[0]["score"] if scored else 0,
                  period_from=period_from, period_to=period_to,
                  method=method, max_hops=max_hops)


if __name__ == "__main__":
    main()
