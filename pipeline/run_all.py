# -*- coding: utf-8 -*-
"""Dieu phoi toan bo luong: ingest -> schema -> sync -> validate -> detect -> report.

Moi lan chay tao 1 thu muc rieng trong ../output/runs/<runId>/ chua day du:
  meta.json  progress.log  graph_risk_flags.jsonl  report.txt  top.json  cycles.ngql
  invoice_loops_min_len3_<pf>_<pt>.jsonl   (chu trinh — members/hop_len/amounts/periods)
  company_metrics_<pf>_<pt>.jsonl          (degree/reciprocity/new_partner_90d/betweenness)
  invoice_flags_min_len3_<pf>_<pt>.jsonl   (co is_circular tung hoa don thuc — CAN Trino,
                                             bo qua neu Trino khong ket noi duoc)

Chay day du (lan dau, hoac khi doi du lieu nguon):
  python3 run_all.py --all

Chi phat hien (du lieu da nap san trong Nebula — truong hop thuong gap nhat):
  python3 run_all.py

Cac tuy chon:
  --all              chay ca ingest + schema + sync truoc khi phat hien
  --ingest           chi chay lai buoc doc du lieu nguon
  --sync             chi chay lai buoc nap vao Nebula
  --rebuild          xoa space roi tao lai (keo theo --sync)
  --from 202011      ky bat dau (mac dinh: lay tu validate)
  --to 202112        ky ket thuc
  --hops 5           so chang toi da
  --method dfs|match phuong phap do
  --datasource ID    id nguon du lieu trong datasources.json (mac dinh local_existing)
  --run-id XYZ       dat ten thu muc ket qua (mac dinh sinh theo thoi gian)

QUAN TRONG — vi sao goi script con bang subprocess chu khong import:
  1. Moi script phai chay doc lap duoc bang CLI (yeu cau nghiem thu P1). Goi bang
     subprocess dam bao duong chay qua web va duong chay tay LA MOT, khong the
     phan hoa thanh 2 nhanh khac nhau.
  2. Tien trinh [[STEP]]/[[LOG]] chay thang qua stdout, Go doc duoc y het khi goi
     truc tiep tung script.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress                              # noqa: E402

PIPELINE = Path(__file__).resolve().parent
BASE = PIPELINE.parent
RUNS_DIR = BASE / "output" / "runs"
MANIFEST = PIPELINE / "datasources.json"


# Tien trinh con dang chay — de dep sach khi bi loi/ngat giua chung.
_running_procs: list[subprocess.Popen] = []


def run_script(name: str, env_extra: dict, log_file, label: str) -> dict:
    """Chay 1 script con, chuyen tiep stdout ra ngoai (de Go/nguoi doc thay tien
    trinh theo thoi gian thuc) DONG THOI ghi vao progress.log.

    Tra ve payload cua dong [[DONE]] neu co (de buoc sau dung lai so lieu)."""
    env = {**os.environ, **{k: str(v) for k, v in env_extra.items()}}
    proc = subprocess.Popen(
        [sys.executable, str(PIPELINE / name)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env=env, text=True, encoding="utf-8", bufsize=1,
    )
    _running_procs.append(proc)
    done_payload: dict = {}
    result_payload: dict = {}
    for line in proc.stdout:
        line = line.rstrip("\n")
        print(line, flush=True)          # chuyen tiep nguyen van
        log_file.write(line + "\n")
        log_file.flush()
        if line.startswith("[[DONE]] "):
            try:
                done_payload = json.loads(line[len("[[DONE]] "):])
            except json.JSONDecodeError:
                pass
        elif line.startswith("[[RESULT]] "):
            try:
                result_payload = json.loads(line[len("[[RESULT]] "):])
            except json.JSONDecodeError:
                pass
    code = proc.wait()
    if proc in _running_procs:
        _running_procs.remove(proc)
    if code != 0:
        raise RuntimeError(f"Buoc '{label}' that bai (ma thoat {code}) — xem log ben tren")
    return {**done_payload, **({"_result": result_payload} if result_payload else {})}


# ---------------------------------------------------------------------------
# Don dep khi that bai
# ---------------------------------------------------------------------------

def kill_leftover_procs() -> int:
    """Giet moi tien trinh con con song. Tra so tien trinh da giet.

    Vi sao can: mot buoc that bai giua chung co the de lai tien trinh con van
    dang ghi vao Nebula. Neu khong giet, lan import ke tiep se chay song song
    voi no -> tranh chap du lieu, ket qua khong the tin duoc."""
    killed = 0
    for p in list(_running_procs):
        if p.poll() is None:          # con dang chay
            try:
                p.kill()
                p.wait(timeout=10)
                killed += 1
            except Exception:
                pass
        _running_procs.remove(p)
    return killed


def space_exists(space: str) -> bool:
    """Kiem tra space co ton tai trong Nebula khong (khong USE vao space)."""
    try:
        from nebula_client import session as _session
        with _session(use_space=False) as s:
            resp = s.execute("SHOW SPACES;")
            if not resp.is_succeeded():
                return False
            for i in range(resp.row_size()):
                row = resp.row_values(i)
                if row and str(row[0].as_string()) == space:
                    return True
    except Exception:
        pass
    return False


def drop_space(space: str) -> bool:
    """Xoa han space khoi Nebula. Tra True neu thanh cong."""
    try:
        from nebula_client import session as _session
        with _session(use_space=False) as s:
            resp = s.execute(f"DROP SPACE IF EXISTS {space};")
            return resp.is_succeeded()
    except Exception:
        return False


def cleanup_after_failure(space: str, log_file, drop_allowed: bool,
                          reason: str) -> dict:
    """Don sach sau khi import that bai, de san sang import lai ngay.

    `drop_allowed` — CO duoc phep xoa space khong. Chi True khi lan chay nay tu
    tao ra space (truoc do chua ton tai) hoac nguoi dung da yeu cau --rebuild.
    Vi sao phai chan: neu space da co san du lieu tot tu truoc va lan chay nay
    chi bo sung them, xoa han space se pha huy du lieu cu cua nguoi dung — mat
    mat that, khong khoi phuc duoc.
    """
    def emit(msg: str) -> None:
        progress.log(msg)
        if log_file and not log_file.closed:
            log_file.write(msg + "\n")
            log_file.flush()

    emit(f"--- Don dep sau khi that bai ({reason}) ---")
    info: dict = {"reason": reason}

    n_killed = kill_leftover_procs()
    info["processes_killed"] = n_killed
    emit(f"Da giet {n_killed} tien trinh con con dang chay"
         if n_killed else "Khong con tien trinh con nao dang chay")

    if drop_allowed:
        if drop_space(space):
            info["space_dropped"] = True
            emit(f"Da xoa space '{space}' (du lieu nap do dang)")
        else:
            info["space_dropped"] = False
            emit(f"KHONG xoa duoc space '{space}' — kiem tra Nebula con song khong")
    else:
        info["space_dropped"] = False
        info["space_kept_reason"] = "space da ton tai truoc lan chay nay"
        emit(f"GIU NGUYEN space '{space}': space nay da co truoc lan chay, "
             f"xoa se mat du lieu cu. Neu muon lam sach han, chay lai voi --rebuild.")

    # data/*.csv la file trung gian, sinh lai duoc moi lan chay -> xoa cho sach.
    removed = []
    data_dir = BASE / "data"
    for name in ("companies.csv", "trades.csv", "shares_address.csv"):
        f = data_dir / name
        if f.exists():
            try:
                f.unlink()
                removed.append(name)
            except OSError:
                pass
    info["intermediate_removed"] = removed
    emit(f"Da xoa file trung gian: {', '.join(removed)}" if removed
         else "Khong co file trung gian nao can xoa")

    emit("=== Da don sach — co the bam Nhap du lieu lai ngay ===")
    return info


def main() -> None:
    ap = argparse.ArgumentParser(description="Chay pipeline phat hien mua ban long vong")
    ap.add_argument("--all", action="store_true", help="chay ca ingest + schema + sync")
    ap.add_argument("--ingest", action="store_true")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--rebuild", action="store_true", help="xoa space roi tao lai")
    ap.add_argument("--from", dest="period_from", type=int)
    ap.add_argument("--to", dest="period_to", type=int)
    ap.add_argument("--hops", type=int, default=int(os.environ.get("MAX_HOPS", "5")))
    ap.add_argument("--method", default=os.environ.get("METHOD", "dfs"), choices=["dfs", "match"])
    ap.add_argument("--datasource", default="local_existing")
    ap.add_argument("--dataset", default=os.environ.get("DATASET"),
                    help="ten bo du lieu trong raw/<ten_bo>/ — chi dung khi --datasource local_existing")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--run-id")
    ap.add_argument("--skip-detect", action="store_true",
                    help="chi ingest+schema+sync, KHONG chay detect/report — dung cho luong "
                         "'Nhap du lieu' (chi nap du lieu vao Nebula, chua phan tich). Buoc "
                         "detect/report thuoc rieng workflow 'Chay' (Step 4), tranh chay 2 lan "
                         "cho cung 1 lan bam — lan dau (luc import) dung tham so mac dinh, lan sau "
                         "(luc bam Chay) dung tham so nguoi dung chon, ket qua lan dau bi vut bo.")
    args = ap.parse_args()

    # Vi sao khong fallback thang ve "invoice_agg_graph": tung mac loi that — chay
    # CLI voi --dataset X ma quen set SPACE se lam du lieu cua X bi nap LAN vao
    # space mac dinh (invoice_agg_graph), tron voi du lieu cua cac lan chay khac.
    # Khop dung logic ben Go (fraud.go: SPACE tu dataset neu chua set thu cong) de
    # 2 duong chay (web UI va CLI truc tiep) khong con lech nhau.
    space = os.environ.get("SPACE") or (
        args.dataset.lower().replace("-", "_") if args.dataset else "invoice_agg_graph"
    )
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    t0 = time.time()

    do_ingest = args.all or args.ingest
    do_schema = args.all or args.rebuild
    do_sync = args.all or args.sync or args.rebuild

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ds = next((d for d in manifest["datasources"] if d["id"] == args.datasource), None)
    if ds is None:
        raise SystemExit(f"Nguon du lieu khong ton tai: {args.datasource}")
    if ds.get("status") != "available":
        raise SystemExit(f"Nguon '{args.datasource}' chua dung duoc: {ds.get('blocked_by', '')}")

    meta = {
        "run_id": run_id, "space": space, "datasource": args.datasource,
        "dataset": args.dataset,
        "method": args.method, "max_hops": args.hops,
        "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "steps_run": [k for k, v in [("ingest", do_ingest), ("schema", do_schema),
                                     ("sync", do_sync), ("detect", not args.skip_detect),
                                     ("report", not args.skip_detect)] if v],
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Ghi nho space da ton tai TRUOC lan chay nay chua — quyet dinh xem khi that
    # bai co duoc phep xoa space khong (xem cleanup_after_failure).
    space_existed_before = space_exists(space) if (do_schema or do_sync) else True

    with open(run_dir / "progress.log", "w", encoding="utf-8") as log:
        progress.log(f"=== Lan chay {run_id} · space {space} ===")
        log.write(f"=== Lan chay {run_id} · space {space} ===\n")

        # Cac buoc NHAP DU LIEU. Bo trong try rieng: neu that bai o day thi du
        # lieu trong Nebula dang do dang -> phai don sach truoc khi cho import
        # lai, neu khong lan sau se nap chong len du lieu nua voi.
        # (Cac buoc sau — validate/detect/report — chi DOC, that bai o do khong
        # lam ban du lieu nen khong can don.)
        ingest_result: dict = {}
        sync_result: dict = {}
        try:
            if do_ingest:
                progress.log(f"--- Doc du lieu nguon ({ds['name']}) ---")
                ingest_env = {"DATASET": args.dataset} if args.dataset else {}
                ingest_result = run_script(ds["script"], ingest_env, log, "ingest")

            if do_schema:
                progress.log("--- Tao schema ---")
                run_script("load_schema.py",
                           {"SPACE": space, **({"REBUILD": "1"} if args.rebuild else {})},
                           log, "schema")

            if do_sync:
                progress.log("--- Nap vao Nebula ---")
                sync_result = run_script("sync_graph.py", {"SPACE": space}, log, "sync")

        except BaseException as exc:
            # BaseException (khong phai Exception): bat ca KeyboardInterrupt va
            # SystemExit — nguoi dung bam Huy giua chung cung phai don sach.
            cleanup = cleanup_after_failure(
                space, log,
                drop_allowed=args.rebuild or not space_existed_before,
                reason=f"{type(exc).__name__}: {exc}",
            )
            meta.update({
                "status": "failed",
                "failed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": f"{type(exc).__name__}: {exc}",
                "cleanup": cleanup,
            })
            (run_dir / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            raise

        pf = pt = None
        det: dict = {}
        loops_file = metrics_file = flags_file = None

        if args.skip_detect:
            # Luong "Nhap du lieu" (Step 1) — chi can du lieu nam trong Nebula,
            # KHONG can biet chu trinh nao/diem may — do la viec cua Step 4 (Chay),
            # noi nguoi dung da chon dung PERIOD_FROM/TO + MAX_HOPS + METHOD. Chay
            # detect o day (voi tham so MAC DINH, chua ai chon) chi de roi bi vut
            # bo khi Step 4 chay lai — da do that: ton vai phut tren du lieu day
            # dac (xem cty86_full), khong ai dung ket qua do ca.
            progress.log("--- Bo qua kiem tra/phat hien/bao cao (--skip-detect: "
                         "chi nhap du lieu, chua phan tich) ---")
        else:
            # --- Kiem tra hop dong du lieu ---------------------------------
            progress.log("--- Kiem tra du lieu ---")
            val = run_script("validate_contract.py", {"SPACE": space}, log, "validate")
            contract = val.get("_result", {})
            if contract:
                (run_dir / "validation.json").write_text(
                    json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
                progress.log(contract.get("headline", ""))
                if not contract.get("can_run"):
                    raise SystemExit("Du lieu chua du de chay — xem validation.json")

            # Ky mac dinh: lay dai ky THAT co trong do thi (khong doan)
            pf = args.period_from or contract.get("data_period_from")
            pt = args.period_to or contract.get("data_period_to")
            if pf is None or pt is None:
                raise SystemExit("Khong xac dinh duoc ky phan tich — truyen --from/--to")

            # --- Phat hien --------------------------------------------------
            progress.log(f"--- Phat hien chu trinh (ky {pf}-{pt}) ---")
            jsonl = run_dir / "graph_risk_flags.jsonl"
            det = run_script("detect_circular_trading.py", {
                "SPACE": space, "PERIOD_FROM": pf, "PERIOD_TO": pt,
                "METHOD": args.method, "MAX_HOPS": args.hops, "OUT_FILE": str(jsonl),
            }, log, "detect")
            # detect_circular_trading.py tu dat ten 2 file nay trong CUNG thu muc voi
            # OUT_FILE (xem detect_circular_trading.py::main, bien loops_file/metrics_file)
            loops_file = run_dir / f"invoice_loops_min_len3_{pf}_{pt}.jsonl"
            metrics_file = run_dir / f"company_metrics_{pf}_{pt}.jsonl"

            # --- Co theo tung hoa don thuc (tra nguoc qua Trino) ---------------
            flags_file = run_dir / f"invoice_flags_min_len3_{pf}_{pt}.jsonl"
            try:
                run_script("export_invoice_flags.py", {
                    "IN_FILE": str(jsonl), "PERIOD_FROM": pf, "PERIOD_TO": pt,
                    "OUT_DIR": str(run_dir),
                }, log, "invoice_flags")
            except RuntimeError as exc:
                # Buoc nay CAN Trino (khac voi detect, chi can Nebula) — neu Trino
                # khong ket noi duoc (vd package `trino` chua cai, hoac dang chay
                # tren dataset CSV thuan khong co nguon Trino), khong nen lam SAP
                # toan bo run — cac output khac (graph_risk_flags/report) van dung.
                progress.log(f"!! Bo qua invoice_flags (can Trino, khong bat buoc): {exc}")
                flags_file = None

            # --- Bao cao ------------------------------------------------------
            progress.log("--- Sinh bao cao ---")
            elapsed = time.time() - t0
            report_meta = {**meta, "period_from": pf, "period_to": pt,
                           "elapsed_sec": round(elapsed, 1),
                           "max_achievable_score": det.get("max_achievable_score", 100)}
            run_script("build_report.py", {
                "SPACE": space, "IN_FILE": str(jsonl), "OUT_DIR": str(run_dir),
                "TOP_N": args.top_n, "META_JSON": json.dumps(report_meta, ensure_ascii=False),
            }, log, "report")

    # Lich su NAP DU LIEU (--skip-detect) truoc day luon ghi "result" toan None du
    # sync_graph.py da tu tinh san so lieu (companies/trades...) qua progress.done()
    # — chi la run_script() khong duoc gan bien nen bi vut di. Gio lay dung tu
    # sync_result (uu tien, vi la buoc NAP THAT vao Nebula) hoac ingest_result neu
    # khong co sync (vd chi chay --ingest don le).
    if args.skip_detect:
        run_result = {k: v for k, v in (sync_result or ingest_result or {}).items()
                      if k != "space"}
    else:
        run_result = {k: det.get(k) for k in
                      ("total", "red", "watch", "max_achievable_score", "top_score")}

    meta.update({
        "period_from": pf, "period_to": pt,
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": round(time.time() - t0, 1),
        "status": "success",
        "result": run_result,
        "files": ({"jsonl": "graph_risk_flags.jsonl", "report": "report.txt",
                  "top_json": "top.json", "cycles_ngql": "cycles.ngql",
                  "validation": "validation.json", "log": "progress.log",
                  "invoice_loops": loops_file.name if loops_file else None,
                  "company_metrics": metrics_file.name if metrics_file else None,
                  "invoice_flags": flags_file.name if flags_file else None}
                  if not args.skip_detect else {}),
    })
    (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    progress.log(f"=== XONG sau {meta['elapsed_sec']}s · {det.get('red', 0)} co do "
                 f"/ {det.get('total', 0)} chu trinh · ket qua: {run_dir} ===")
    progress.done(run_id=run_id, run_dir=str(run_dir), **meta["result"])


if __name__ == "__main__":
    main()
