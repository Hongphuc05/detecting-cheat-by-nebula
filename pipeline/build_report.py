# -*- coding: utf-8 -*-
"""Doc ket qua .jsonl -> sinh 3 dau ra cho nguoi va cho giao dien web.

  report.txt   ban bao cao chu, doc truc tiep hoac preview tren web
  top.json     du lieu co cau truc cho giao dien (bang top + nut xem do thi)
  cycles.ngql  cau lenh nGQL dung san de ve chu trinh len Nebula

Chay:
  IN_FILE=../output/graph_risk_flags_202011_202112.jsonl python3 build_report.py
  OUT_DIR=... TOP_N=20 python3 build_report.py

Bien moi truong:
  IN_FILE (bat buoc)  OUT_DIR (mac dinh = thu muc chua IN_FILE)  TOP_N (20)
  SPACE, META_JSON (chuoi JSON tham so lan chay, de ghi vao dau bao cao)
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress                                      # noqa: E402
from nebula_client import get_space, session          # noqa: E402

RED_THRESHOLD, WATCH_THRESHOLD = 60.0, 40.0
N_STEPS = 3


def fmt_int(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def fmt_money(n) -> str:
    """Tien VND -> dang trieu/ty cho de doc trong bang."""
    n = float(n)
    if n >= 1e9:
        return f"{n / 1e9:,.1f} ty".replace(",", ".")
    if n >= 1e6:
        return f"{n / 1e6:,.0f} tr".replace(",", ".")
    return fmt_int(n)


def load_names(s, msts: set[str]) -> dict[str, str]:
    """Lay ten cong ty tu space dang chay (khong doc CSV — de bao cao luon khop
    voi du lieu that su duoc phan tich)."""
    if not msts:
        return {}
    names = {}
    batch = sorted(msts)
    for i in range(0, len(batch), 200):
        ids = ", ".join(f'"{m}"' for m in batch[i:i + 200])
        r = s.execute(f"MATCH (c:Company) WHERE id(c) IN [{ids}] RETURN id(c), c.Company.name;")
        if not r.is_succeeded():
            continue
        for j in range(r.row_size()):
            row = r.row_values(j)
            v = row[1]
            names[row[0].as_string()] = v.as_string() if v.is_string() else ""
    return names


def build_ngql(members: list[str], periods: list | None = None) -> str:
    """Sinh cau nGQL ve chu trinh — dang MOT CHANG, neo CA HAI dau, liet ke tung
    cap bang OR. Tra ve dung cac dinh + canh tao thanh vong.

    ==================================================================
    DAY LA CACH DUY NHAT DA KIEM CHUNG AN TOAN — doc truoc khi sua
    ==================================================================
    Ban dau ham nay sinh chuoi hop noi tiep:
        MATCH p=(c0)-[:TRADES]->(c1)-...->(c4)-[:TRADES]->(c0)
        WHERE id(c0)=="..." AND id(c1)=="..." AND ... (neo DU CA 5 dinh)
    Nhin thi tuong an toan vi da neo het. THUC TE DA LAM CHET SERVER: graphd bi
    OOM-kill (exit 137) ngay lan chay dau tren vong 5 chang. Ly do: bo lap ke
    hoach mo rong `(c0)-[:TRADES]->(c1)` TRUOC roi moi loc `id(c1)`, ma c0 la
    dinh hub co toi 158 canh di ra -> so to hop no theo cap so nhan qua 5 chang.
    Neo id() KHONG cuu duoc, dung y het canh bao trong
    nebula_demo/schemas/invoice_graph.md.

    Dang mot-chang-OR nay moi chang chi co 1 buoc mo rong voi ca hai dau da neo,
    nen khong the no to hop. Do that: 0,04 giay cho vong 5 chang (so voi lam
    chet server o dang cu).

    `periods` (tuy chon): ghim them rank(e) == ky de lay DUNG cac canh da dung
    khi cham diem. Khong truyen thi tra ve moi ky giao dich giua cac cap do —
    rong hon, van dung, nhung khong khop 1-1 voi diem so.
    """
    n = len(members)
    conds = []
    for i in range(n):
        a, b = members[i], members[(i + 1) % n]
        c = f'(id(a) == "{a}" AND id(b) == "{b}"'
        if periods and i < len(periods):
            c += f" AND rank(e) == {int(periods[i])}"
        conds.append(c + ")")
    return ("MATCH (a:Company)-[e:TRADES]->(b:Company)\nWHERE "
            + "\n   OR ".join(conds) + "\nRETURN a, e, b;")


def main() -> None:
    in_file = Path(os.environ["IN_FILE"])
    out_dir = Path(os.environ.get("OUT_DIR", in_file.parent))
    out_dir.mkdir(parents=True, exist_ok=True)
    top_n = int(os.environ.get("TOP_N", "20"))
    meta = json.loads(os.environ.get("META_JSON", "{}"))
    space = get_space()

    # ---- Buoc 1: doc & thong ke ------------------------------------------
    with progress.Step(1, N_STEPS, "Đọc kết quả & thống kê") as st:
        rows = [json.loads(ln) for ln in in_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        rows.sort(key=lambda r: -r["score"])
        red = [r for r in rows if r["score"] >= RED_THRESHOLD]
        watch = [r for r in rows if WATCH_THRESHOLD <= r["score"] < RED_THRESHOLD]

        # "Hub": dem so lan mot MST xuat hien trong chu trinh CO DO.
        # Day la chi so RE (dem tren ket qua da co), KHONG phai Betweenness
        # Centrality that (thuat toan Brandes, O(V*E)) — dung ten khac de khong
        # ai trich dan nham trong bao cao.
        hub_red: dict = defaultdict(int)
        hub_best: dict = defaultdict(float)
        for r in red:
            for m in r["members"]:
                hub_red[m] += 1
                hub_best[m] = max(hub_best[m], r["score"])
        hubs = sorted(hub_red.items(), key=lambda kv: (-kv[1], -hub_best[kv[0]]))
        st.metric(total=len(rows), red=len(red), watch=len(watch), hubs=len(hubs))

    # ---- Buoc 2: lay ten cong ty -----------------------------------------
    with progress.Step(2, N_STEPS, "Tra tên doanh nghiệp") as st:
        need = {m for r in rows[:top_n] for m in r["members"]} | {m for m, _ in hubs[:top_n]}
        with session() as s:
            names = load_names(s, need)
        st.metric(resolved=len(names))

    def nm(mst: str) -> str:
        return names.get(mst, "") or "(chua co ten trong do thi)"

    # ---- Buoc 3: sinh 3 file ---------------------------------------------
    with progress.Step(3, N_STEPS, "Sinh báo cáo") as st:
        max_score = meta.get("max_achievable_score", 100)
        L: list[str] = []
        L.append("=" * 78)
        L.append("BÁO CÁO PHÁT HIỆN MUA BÁN LÒNG VÒNG (CIRCULAR TRADING)")
        L.append("=" * 78)
        L.append(f"Không gian dữ liệu : {space}")
        L.append(f"Kỳ phân tích       : {meta.get('period_from', '?')} - {meta.get('period_to', '?')}")
        L.append(f"Số chặng tối đa    : {meta.get('max_hops', '?')}   "
                 f"Phương pháp: {meta.get('method', '?')}")
        if meta.get("started_at"):
            L.append(f"Chạy lúc           : {meta['started_at']}")
        if meta.get("elapsed_sec"):
            L.append(f"Thời gian chạy     : {meta['elapsed_sec']:.1f} giây")
        L.append("")
        L.append("-" * 78)
        L.append("TỔNG QUAN")
        L.append("-" * 78)
        L.append(f"  Chu trình duy nhất tìm được : {fmt_int(len(rows)):>8}")
        L.append(f"  Cờ đỏ    (điểm >= {RED_THRESHOLD:.0f})       : {fmt_int(len(red)):>8}")
        L.append(f"  Theo dõi (điểm {WATCH_THRESHOLD:.0f} - {RED_THRESHOLD:.0f})   : {fmt_int(len(watch)):>8}")
        L.append(f"  Bỏ qua   (điểm < {WATCH_THRESHOLD:.0f})       : "
                 f"{fmt_int(len(rows) - len(red) - len(watch)):>8}")
        L.append("")

        if max_score < 100:
            L.append("!" * 78)
            L.append(f"CẢNH BÁO TRẦN ĐIỂM: bộ dữ liệu này chỉ đạt tối đa {max_score:.0f}/100 điểm.")
            missing = []
            if not any(r["score_hidden_link"] for r in rows):
                missing.append("  - Thiếu dữ liệu ĐKKD (người đại diện / sở hữu vốn / địa chỉ chung)")
                missing.append("    => tín hiệu 'liên kết ngầm' luôn = 0, mất 25 điểm")
            if not any(r["score_risky_member"] for r in rows):
                missing.append("  - Thiếu ngày thành lập / trạng thái doanh nghiệp")
                missing.append("    => tín hiệu 'thành viên rủi ro' luôn = 0, mất 15 điểm")
            L.extend(missing)
            L.append("  Chi tiết: full_invoice_86/KE_HOACH_TONG_THE_PIPELINE_LONG_VONG.md mục 4.2")
            L.append("!" * 78)
            L.append("")

        L.append("-" * 78)
        L.append(f"TOP {top_n} CHU TRÌNH ĐIỂM CAO NHẤT")
        L.append("-" * 78)
        for i, r in enumerate(rows[:top_n], 1):
            L.append(f"{i:3d}. {r['score']:5.1f} điểm | {r['hop_len']} chặng | "
                     f"kỳ {min(r['periods'])}-{max(r['periods'])}")
            L.append(f"     chi tiết: cân bằng {r['score_balance']:.0f} · thời gian {r['score_time']:.0f}"
                     f" · liên kết ngầm {r['score_hidden_link']:.0f} · rủi ro {r['score_risky_member']:.0f}"
                     f" · VAT {r['score_vat']:.0f}")
            for k, m in enumerate(r["members"]):
                arrow = "  ->" if k else "    "
                amt = fmt_money(r["amounts"][k]) if k < len(r["amounts"]) else ""
                L.append(f"     {arrow} {m}  {nm(m)[:44]:<44} {amt:>10}")
            L.append("")

        L.append("-" * 78)
        L.append(f"TOP {top_n} DOANH NGHIỆP XUẤT HIỆN TRONG NHIỀU CỜ ĐỎ NHẤT")
        L.append("-" * 78)
        if hubs:
            L.append(f"{'#':>3}  {'MST':<14} {'Tên doanh nghiệp':<44} {'Số cờ đỏ':>9} {'Điểm cao nhất':>14}")
            for i, (mst, cnt) in enumerate(hubs[:top_n], 1):
                L.append(f"{i:3d}  {mst:<14} {nm(mst)[:44]:<44} {cnt:>9} {hub_best[mst]:>14.1f}")
            L.append("")
            L.append("  Ghi chú: đây là số lần MST xuất hiện trong chu trình cờ đỏ (chỉ số đếm,")
            L.append("  KHÔNG phải Betweenness Centrality). Doanh nghiệp đứng đầu bảng này nên")
            L.append("  được ưu tiên tra cứu ĐKKD trước.")
        else:
            L.append("  (không có chu trình cờ đỏ nào)")
        L.append("")
        L.append("=" * 78)
        L.append("Xem trực quan: mở file cycles.ngql, dán vào Nebula Studio hoặc bấm nút")
        L.append("'Xem trên đồ thị' ở bảng kết quả trên giao diện web.")
        L.append("=" * 78)

        report_path = out_dir / "report.txt"
        report_path.write_text("\n".join(L), encoding="utf-8")

        # top.json — cho giao dien
        top_json = {
            "space": space,
            "meta": meta,
            "summary": {
                "total": len(rows), "red": len(red), "watch": len(watch),
                "skipped": len(rows) - len(red) - len(watch),
                "max_achievable_score": max_score,
                "top_score": rows[0]["score"] if rows else 0,
            },
            "top_cycles": [
                {**r, "names": [nm(m) for m in r["members"]],
                 "ngql": build_ngql(r["members"], r.get("periods"))}
                for r in rows[:top_n]
            ],
            "top_companies": [
                {"mst": m, "name": nm(m), "red_count": c, "best_score": hub_best[m]}
                for m, c in hubs[:top_n]
            ],
        }
        (out_dir / "top.json").write_text(
            json.dumps(top_json, ensure_ascii=False, indent=2), encoding="utf-8")

        # cycles.ngql — dan thang vao Nebula Studio
        # Comment PHAI dung `//`: nGQL KHONG hieu `--` cua SQL (da mac loi that,
        # bao "syntax error near `--\'"). File nay duoc dan thang vao Nebula Studio
        # nen sai kieu comment la ca file khong chay duoc.
        Q = [f"// {top_n} chu trinh diem cao nhat — space {space}",
             f"// Sinh tu {in_file.name}. Dang MOT CHANG neo ca 2 dau + ghim rank —",
             "// KHONG dung `*`, cung KHONG dung chuoi hop noi tiep (da lam OOM graphd).",
             "", f"USE {space};", ""]
        for i, r in enumerate(rows[:top_n], 1):
            Q.append(f"// #{i} · {r['score']} diem · {r['hop_len']} chang")
            Q.append(build_ngql(r["members"], r.get("periods")))
            Q.append("")
        (out_dir / "cycles.ngql").write_text("\n".join(Q), encoding="utf-8")

        st.metric(report=str(report_path), lines=len(L))

    progress.log(f"Bao cao: {report_path}")
    progress.done(report=str(report_path), top_json=str(out_dir / "top.json"),
                  cycles_ngql=str(out_dir / "cycles.ngql"),
                  total=len(rows), red=len(red), watch=len(watch))


if __name__ == "__main__":
    main()
