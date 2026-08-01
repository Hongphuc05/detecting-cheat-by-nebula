# -*- coding: utf-8 -*-
"""Quet space trong Nebula, doi chieu voi Hop dong Du lieu (Data Contract) cua
loai truy van gian lan duoc chon -> tra ve checklist JSON.

Day la buoc TRA LOI CAU HOI: "du lieu da du de chay chua, va neu thieu thi mat
bao nhieu diem?" — thay vi de nguoi dung chay xong moi phat hien diem bi tran.

Chay:
  python3 validate_contract.py                          # loai mac dinh: circular_trading
  SPACE=tax_graph python3 validate_contract.py
  QUERY_TYPE=circular_trading python3 validate_contract.py

Ket qua: in JSON ra stdout (dong duy nhat bat dau bang [[RESULT]]) de Go doc.
Them tuy chon PRETTY=1 de in dep cho nguoi doc bang CLI.

=========================================================================
BA MUC TRANG THAI — phan biet ky, vi hanh dong khac han nhau
=========================================================================
  pass    : co cau truc VA co du lieu           -> dung duoc
  empty   : co cau truc NHUNG khong co du lieu  -> pipeline chay duoc, tin hieu
                                                    luon = 0. Can DI TIM du lieu,
                                                    khong phai sua schema.
  missing : khong co cau truc                    -> phai tao schema + tim du lieu
  skipped : khong lien quan toi loai truy van dang chon

Vi sao khong gop `empty` vao `missing`: tren detecting_cheat_by_nebula, SHARES_ADDRESS CO edge
type nhung 0 canh (98 cong ty khong ai trung dia chi). Bao "missing" se khien
nguoi ta di sua schema — sai huong hoan toan.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress                                    # noqa: E402
from nebula_client import get_space, session       # noqa: E402

BASE = Path(__file__).resolve().parent
MANIFEST = BASE / "datasources.json"

# Cong thuc cham diem (phai KHOP voi detect_circular_trading.py). Neu ai doi
# trong so ben do ma quen sua o day, test nghiem thu se bat duoc vi tran diem
# in ra khong khop diem cao nhat thuc te.
W_BALANCE, W_TIME, W_HIDDEN, W_RISKY, W_VAT = 30, 20, 25, 15, 10


# --------------------------------------------------------------------------
# Cac ham do (probe) — moi ham tra (status, detail, extra_dict)
# --------------------------------------------------------------------------

def _show(s, what: str) -> set[str]:
    """SHOW TAGS / SHOW EDGES -> tap ten (da bo dau nhay)."""
    resp = s.execute(f"SHOW {what};")
    if not resp.is_succeeded():
        return set()
    return {resp.row_values(i)[0].as_string() for i in range(resp.row_size())}


def _props(s, kind: str, name: str) -> dict[str, str]:
    """DESCRIBE TAG/EDGE -> {ten_thuoc_tinh: kieu}."""
    resp = s.execute(f"DESCRIBE {kind} {name};")
    if not resp.is_succeeded():
        return {}
    out = {}
    for i in range(resp.row_size()):
        row = resp.row_values(i)
        out[row[0].as_string()] = row[1].as_string()
    return out


def _count(s, pattern: str) -> int:
    resp = s.execute(f"MATCH {pattern} RETURN count(*) AS c;")
    if not resp.is_succeeded() or resp.row_size() == 0:
        return 0
    return resp.row_values(0)[0].as_int()


def probe_tag_company(s, ctx) -> tuple[str, str, dict]:
    if "Company" not in ctx["tags"]:
        return "missing", "Không có Tag Company", {}
    n = _count(s, "(c:Company)")
    ctx["n_company"] = n
    if n == 0:
        return "empty", "Có Tag Company nhưng chưa nạp đỉnh nào", {"count": 0}
    return "pass", f"{n:,} đỉnh".replace(",", "."), {"count": n}


def probe_edge_trades(s, ctx) -> tuple[str, str, dict]:
    if "TRADES" not in ctx["edges"]:
        return "missing", "Không có Edge TRADES — không thể dò chu trình giao dịch", {}
    props = _props(s, "EDGE", "TRADES")
    need = ["period", "invoice_count", "total_amount", "total_vat"]
    lack = [p for p in need if p not in props]
    if lack:
        return "missing", f"Edge TRADES thiếu thuộc tính: {', '.join(lack)}", {"missing_props": lack}
    n = _count(s, "()-[e:TRADES]->()")
    ctx["n_trades"] = n
    if n == 0:
        return "empty", "Có Edge TRADES nhưng chưa nạp cạnh nào", {"count": 0}
    return "pass", f"{n:,} cạnh · đủ {len(need)}/{len(need)} thuộc tính bắt buộc".replace(",", "."), {"count": n}


def probe_rank_period(s, ctx) -> tuple[str, str, dict]:
    """rank(e) PHAI bang e.period. Toan bo buoc loc theo ky trong nGQL dua vao
    rank de khong phai doc thuoc tinh — lech la loc sai ky ma khong bao loi."""
    if ctx.get("n_trades", 0) == 0:
        return "skipped", "Chưa có cạnh TRADES để kiểm tra", {}
    resp = s.execute(
        "MATCH ()-[e:TRADES]->() RETURN rank(e) AS r, e.period AS p LIMIT 500;")
    if not resp.is_succeeded():
        return "missing", f"Không đọc được rank: {resp.error_msg()}", {}
    bad = sum(1 for i in range(resp.row_size())
              if resp.row_values(i)[0].as_int() != resp.row_values(i)[1].as_int())
    if bad:
        return "missing", f"{bad}/{resp.row_size()} cạnh mẫu có rank khác period", {"mismatch": bad}

    # Dai ky THAT phai lay bang min/max tren toan bo, KHONG lay tu mau 500 canh:
    # mau chi cham vao 1 phan du lieu nen se bao thieu ky dau/cuoi, va giao dien
    # dung con so nay de dien san o nhap "ky tu - ky den" -> nguoi dung se quet
    # thieu ky ma khong biet.
    agg = s.execute("MATCH ()-[e:TRADES]->() RETURN min(e.period) AS a, max(e.period) AS b;")
    if agg.is_succeeded() and agg.row_size():
        row = agg.row_values(0)
        ctx["period_from"], ctx["period_to"] = row[0].as_int(), row[1].as_int()
    return "pass", (f"khớp trên {resp.row_size()} cạnh mẫu · kỳ "
                    f"{ctx.get('period_from', '?')}-{ctx.get('period_to', '?')}"), {
        "sampled": resp.row_size(),
        "period_from": ctx.get("period_from"), "period_to": ctx.get("period_to")}


def probe_index(s, ctx) -> tuple[str, str, dict]:
    resp = s.execute("SHOW EDGE INDEXES;")
    if not resp.is_succeeded():
        return "missing", "Không đọc được danh sách index", {}
    names = {resp.row_values(i)[0].as_string() for i in range(resp.row_size())}
    hit = [n for n in names if "trades" in n.lower() and "period" in n.lower()]
    if hit:
        return "pass", f"có index {hit[0]}", {"index": hit[0]}
    # Khong chan chay: DFS doc tu CSV, khong dung index. Chi cham hon o che do MATCH.
    return "empty", "Chưa có index TRADES(period) — chế độ Truy vấn CSDL sẽ chậm hơn", {}


def probe_legal_rep(s, ctx) -> tuple[str, str, dict]:
    if "LEGAL_REP_OF" not in ctx["edges"]:
        return "missing", "Không có dữ liệu người đại diện pháp luật (ĐKKD)", {}
    n = _count(s, "()-[e:LEGAL_REP_OF]->()")
    if n == 0:
        return "empty", "Có Edge LEGAL_REP_OF nhưng 0 cạnh", {"count": 0}
    return "pass", f"{n:,} cạnh".replace(",", "."), {"count": n}


def probe_owns(s, ctx) -> tuple[str, str, dict]:
    if "OWNS" not in ctx["edges"]:
        return "missing", "Không có dữ liệu sở hữu vốn (ĐKKD)", {}
    n = _count(s, "()-[e:OWNS]->()")
    if n == 0:
        return "empty", "Có Edge OWNS nhưng 0 cạnh", {"count": 0}
    return "pass", f"{n:,} cạnh".replace(",", "."), {"count": n}


def probe_shares_address(s, ctx) -> tuple[str, str, dict]:
    if "SHARES_ADDRESS" not in ctx["edges"]:
        return "missing", "Không có cạnh địa chỉ chung", {}
    n = _count(s, "()-[e:SHARES_ADDRESS]->()")
    if n == 0:
        return "empty", "Có Edge SHARES_ADDRESS nhưng 0 cạnh — không cặp doanh nghiệp nào trùng địa chỉ đăng ký", {"count": 0}
    return "pass", f"{n:,} cạnh".replace(",", "."), {"count": n}


def probe_status_date(s, ctx) -> tuple[str, str, dict]:
    """Can `established_date` (DN moi thanh lap) va/hoac `status` (bo tron/ngung
    hoat dong) tren Tag Company."""
    if "Company" not in ctx["tags"]:
        return "missing", "Không có Tag Company", {}
    props = _props(s, "TAG", "Company")
    have = [p for p in ("established_date", "status", "is_new_company") if p in props]
    if not have:
        return "missing", "Tag Company không có cột established_date / status / is_new_company", {}
    # Co cot nhung co du lieu that khong?
    col = have[0]
    resp = s.execute(f"MATCH (c:Company) WHERE c.Company.{col} IS NOT NULL RETURN count(c) AS n;")
    n = resp.row_values(0)[0].as_int() if resp.is_succeeded() and resp.row_size() else 0
    if n == 0:
        return "empty", f"Có cột {', '.join(have)} nhưng toàn bộ đang rỗng", {"count": 0}
    return "pass", f"{n:,} doanh nghiệp có {', '.join(have)}".replace(",", "."), {"count": n, "cols": have}


def probe_price(s, ctx) -> tuple[str, str, dict]:
    return "skipped", "Lớp 3 (bất thường đơn giá) chưa bật trong phiên bản này", {}


CHECKS: dict = {
    "4.1.tag_company":     ("Tag Company (đỉnh doanh nghiệp)",          probe_tag_company),
    "4.1.edge_trades":     ("Edge TRADES + thuộc tính bắt buộc",         probe_edge_trades),
    "4.1.rank_period":     ("rank(TRADES) bằng period (yyyymm)",         probe_rank_period),
    "4.1.index":           ("Index TRADES(period)",                      probe_index),
    "4.2.legal_rep":       ("ĐKKD — người đại diện pháp luật",           probe_legal_rep),
    "4.2.owns":            ("ĐKKD — sở hữu vốn",                         probe_owns),
    "4.2.shares_address":  ("Địa chỉ đăng ký trùng nhau",                probe_shares_address),
    "4.2.status_date":     ("ĐKKD — ngày thành lập / trạng thái",        probe_status_date),
    "4.3.price":           ("[Lớp 3] Đơn giá / mã ngành",                probe_price),
}

# Nhom tin hieu -> diem. `any_of`: chi can 1 nguon `pass` la du diem cua nhom do
# (dung voi cach cham: score_hidden_link la nhi phan, 1 trong 3 khop la du 25d).
SIGNAL_GROUPS = [
    {"id": "hidden_link", "label": "liên kết ngầm",
     "points": W_HIDDEN, "any_of": ["4.2.legal_rep", "4.2.owns", "4.2.shares_address"]},
    {"id": "risky_member", "label": "thành viên rủi ro",
     "points": W_RISKY, "any_of": ["4.2.status_date"]},
]


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def main() -> None:
    space = get_space()
    qtype_id = os.environ.get("QUERY_TYPE", "circular_trading")

    manifest = load_manifest()
    qtype = next((q for q in manifest["query_types"] if q["id"] == qtype_id), None)
    if qtype is None:
        raise SystemExit(f"Loại truy vấn không tồn tại: {qtype_id}")
    if qtype.get("status") != "available":
        raise SystemExit(f"Loại truy vấn '{qtype_id}' chưa được triển khai")

    required = qtype.get("requires", [])
    optional = qtype.get("optional", [])
    wanted = required + optional

    results = []
    ctx: dict = {}
    with session() as s:
        ctx["tags"] = _show(s, "TAGS")
        ctx["edges"] = _show(s, "EDGES")

        for cid, (label, probe) in CHECKS.items():
            if cid not in wanted:
                continue
            try:
                status, detail, extra = probe(s, ctx)
            except Exception as e:                       # 1 check hong khong duoc lam sap ca lan quet
                status, detail, extra = "missing", f"Lỗi khi kiểm tra: {e}", {}
            results.append({
                "id": cid, "label": label, "status": status, "detail": detail,
                "required": cid in required, **extra,
            })

    by_id = {r["id"]: r for r in results}

    # can_run: moi muc BAT BUOC phai `pass`
    blocking = [r for r in results if r["required"] and r["status"] != "pass"]
    can_run = not blocking

    # Tran diem: tru diem cua tung NHOM tin hieu khong co nguon du lieu nao `pass`
    max_score = W_BALANCE + W_TIME + W_VAT + W_HIDDEN + W_RISKY
    lost = []
    for grp in SIGNAL_GROUPS:
        available = any(by_id.get(cid, {}).get("status") == "pass" for cid in grp["any_of"])
        if not available:
            max_score -= grp["points"]
            lost.append(grp)
            for cid in grp["any_of"]:
                if cid in by_id:
                    by_id[cid]["impact_group"] = grp["id"]
        # Gan diem anh huong cho muc dau tien cua nhom (de UI hien "-25 d")
        if not available and grp["any_of"][0] in by_id:
            by_id[grp["any_of"][0]]["impact_points"] = grp["points"]

    if not can_run:
        headline = ("KHÔNG chạy được — thiếu dữ liệu bắt buộc: "
                    + ", ".join(b["label"] for b in blocking))
    elif lost:
        detail = " + ".join(f"{g['points']} điểm {g['label']}" for g in lost)
        headline = (f"Chạy được — nhưng TRẦN ĐIỂM chỉ {max_score}/100 "
                    f"vì thiếu dữ liệu ĐKKD (mất {detail})")
    else:
        headline = "Đủ dữ liệu — đạt được thang điểm đầy đủ 100/100"

    out = {
        "space": space,
        "query_type": qtype_id,
        "query_type_name": qtype.get("name", qtype_id),
        "can_run": can_run,
        "max_achievable_score": max_score,
        "headline": headline,
        "checks": results,
        "summary": {
            "pass": sum(1 for r in results if r["status"] == "pass"),
            "empty": sum(1 for r in results if r["status"] == "empty"),
            "missing": sum(1 for r in results if r["status"] == "missing"),
        },
    }
    if "period_from" in ctx:
        out["data_period_from"] = ctx["period_from"]
        out["data_period_to"] = ctx["period_to"]

    print("[[RESULT]] " + json.dumps(out, ensure_ascii=False), flush=True)

    if os.environ.get("PRETTY"):
        icon = {"pass": "[v]", "empty": "[o]", "missing": "[x]", "skipped": "[-]"}
        print(f"\n  Space: {space} | Loai: {qtype.get('name')}", file=sys.stderr)
        print(f"  {headline}\n", file=sys.stderr)
        for r in results:
            pts = f"  -{r['impact_points']}d" if r.get("impact_points") else ""
            star = " *" if r["required"] else "  "
            print(f"  {icon[r['status']]}{star} {r['label']:<46} {r['detail']}{pts}", file=sys.stderr)
        print(f"\n  (* = bat buoc)  Tran diem: {max_score}/100\n", file=sys.stderr)

    progress.done(can_run=can_run, max_achievable_score=max_score, space=space)


if __name__ == "__main__":
    main()
