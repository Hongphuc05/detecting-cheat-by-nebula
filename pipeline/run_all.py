# -*- coding: utf-8 -*-
"""Dieu phoi toan bo luong: ingest -> schema -> sync -> validate -> detect -> report.

Moi lan chay tao 1 thu muc rieng trong ../output/runs/<runId>/ chua day du:
  meta.json  progress.log  graph_risk_flags.jsonl  report.txt  top.json  cycles.ngql

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
    if code != 0:
        raise RuntimeError(f"Buoc '{label}' that bai (ma thoat {code}) — xem log ben tren")
    return {**done_payload, **({"_result": result_payload} if result_payload else {})}


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
                                     ("sync", do_sync), ("detect", True), ("report", True)] if v],
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    with open(run_dir / "progress.log", "w", encoding="utf-8") as log:
        progress.log(f"=== Lan chay {run_id} · space {space} ===")
        log.write(f"=== Lan chay {run_id} · space {space} ===\n")

        if do_ingest:
            progress.log(f"--- Doc du lieu nguon ({ds['name']}) ---")
            ingest_env = {"DATASET": args.dataset} if args.dataset else {}
            run_script(ds["script"], ingest_env, log, "ingest")

        if do_schema:
            progress.log("--- Tao schema ---")
            run_script("load_schema.py",
                       {"SPACE": space, **({"REBUILD": "1"} if args.rebuild else {})},
                       log, "schema")

        if do_sync:
            progress.log("--- Nap vao Nebula ---")
            run_script("sync_graph.py", {"SPACE": space}, log, "sync")

        # --- Kiem tra hop dong du lieu (luon chay) -------------------------
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

        # --- Phat hien ----------------------------------------------------
        progress.log(f"--- Phat hien chu trinh (ky {pf}-{pt}) ---")
        jsonl = run_dir / "graph_risk_flags.jsonl"
        det = run_script("detect_circular_trading.py", {
            "SPACE": space, "PERIOD_FROM": pf, "PERIOD_TO": pt,
            "METHOD": args.method, "MAX_HOPS": args.hops, "OUT_FILE": str(jsonl),
        }, log, "detect")

        # --- Bao cao ------------------------------------------------------
        progress.log("--- Sinh bao cao ---")
        elapsed = time.time() - t0
        report_meta = {**meta, "period_from": pf, "period_to": pt,
                       "elapsed_sec": round(elapsed, 1),
                       "max_achievable_score": det.get("max_achievable_score", 100)}
        rep = run_script("build_report.py", {
            "SPACE": space, "IN_FILE": str(jsonl), "OUT_DIR": str(run_dir),
            "TOP_N": args.top_n, "META_JSON": json.dumps(report_meta, ensure_ascii=False),
        }, log, "report")

    meta.update({
        "period_from": pf, "period_to": pt,
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": round(time.time() - t0, 1),
        "status": "success",
        "result": {k: det.get(k) for k in
                   ("total", "red", "watch", "max_achievable_score", "top_score")},
        "files": {"jsonl": "graph_risk_flags.jsonl", "report": "report.txt",
                  "top_json": "top.json", "cycles_ngql": "cycles.ngql",
                  "validation": "validation.json", "log": "progress.log"},
    })
    (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    progress.log(f"=== XONG sau {meta['elapsed_sec']}s · {det.get('red', 0)} co do "
                 f"/ {det.get('total', 0)} chu trinh · ket qua: {run_dir} ===")
    progress.done(run_id=run_id, run_dir=str(run_dir), **meta["result"])


if __name__ == "__main__":
    main()
