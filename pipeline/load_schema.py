# -*- coding: utf-8 -*-
"""Tao space / tag / edge / index tu ../schemas/detecting_cheat_by_nebula.ngql.

Chay:
  python3 load_schema.py            # tao neu chua co (idempotent, an toan)
  REBUILD=1 python3 load_schema.py  # XOA space roi tao lai (mat toan bo du lieu!)

Khi nao can REBUILD=1: sau khi doi logic gop canh trong ingest (vi INSERT chi ghi
de theo khoa, KHONG xoa canh cu — canh khong con trong du lieu moi se nam lai
trong do thi va lam sai ket qua dem).

Bien moi truong: SPACE, REBUILD, NEBULA_* (xem nebula_client.py)
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress                     # noqa: E402
from nebula_client import execute, get_space, session   # noqa: E402

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schemas" / "detecting_cheat_by_nebula.ngql"

# Nebula lan truyen thay doi schema qua heartbeat cua metad. CREATE SPACE xong
# KHONG the USE ngay, va CREATE TAG xong khong the INSERT ngay — phai doi.
# Con so lay tu chu thich trong schema goc cua tax_graph (10-20s cho space).
WAIT_SPACE = int(os.environ.get("WAIT_SPACE", "20"))
WAIT_SCHEMA = int(os.environ.get("WAIT_SCHEMA", "10"))

N_STEPS = 3


def split_statements(sql: str) -> list[str]:
    """Tach file .ngql thanh tung cau, sau khi go het comment.

    QUAN TRONG (da mac loi that): nGQL KHONG hieu comment kieu `--` cua SQL —
    no chi chap nhan `//`, `#`, `/* */`. Phai go TRUOC khi gui, va phai go ca
    comment CUOI DONG chu khong chi dong bat dau bang `--`, vi
    `partition_num = 10,  -- ghi chu` nam GIUA cau lenh se lam Nebula bao
    "syntax error near `--'".

    Go comment truoc khi tach `;` cung tranh bay: dau `;` nam trong comment se
    lam cat cau lenh sai cho.

    Gioi han da biet: khong xu ly `--` nam trong chuoi string literal. Schema
    cua pipeline nay khong co literal nao nhu vay; neu sau them thi phai doi
    sang parser that.
    """
    body = re.sub(r"(--|//|#).*?$", "", sql, flags=re.MULTILINE)
    return [s.strip() for s in body.split(";") if s.strip()]


def main() -> None:
    space = get_space()
    rebuild = bool(os.environ.get("REBUILD"))

    raw = SCHEMA_FILE.read_text(encoding="utf-8").replace("{{SPACE}}", space)
    stmts = split_statements(raw)

    # Tach lam 3 nhom vi giua chung phai CHO heartbeat, khong chay lien tuc duoc.
    create_space = [s for s in stmts if s.upper().startswith("CREATE SPACE")]
    use_stmt = [s for s in stmts if s.upper().startswith("USE ")]
    rest = [s for s in stmts if s not in create_space and s not in use_stmt]
    tags_edges = [s for s in rest if not s.upper().startswith("CREATE EDGE INDEX")]
    indexes = [s for s in rest if s.upper().startswith("CREATE EDGE INDEX")]

    progress.log(f"Space dich: {space}" + (" (REBUILD — se xoa du lieu cu)" if rebuild else ""))

    with progress.Step(1, N_STEPS, "Tao space") as st:
        # use_space=False: space co the chua ton tai, USE se loi.
        with session(use_space=False) as s:
            if rebuild:
                execute(s, f"DROP SPACE IF EXISTS {space};", "drop space")
                progress.log(f"Da xoa space {space}, cho heartbeat...")
                time.sleep(WAIT_SPACE)
            for stmt in create_space:
                execute(s, stmt + ";", "create space")
        progress.log(f"Cho {WAIT_SPACE}s de metad lan truyen space...")
        time.sleep(WAIT_SPACE)
        st.metric(space=space, rebuilt=rebuild)

    with progress.Step(2, N_STEPS, "Tao tag & edge") as st:
        with session() as s:
            for stmt in tags_edges:
                execute(s, stmt + ";", "tag/edge")
        progress.log(f"Cho {WAIT_SCHEMA}s de lan truyen tag/edge...")
        time.sleep(WAIT_SCHEMA)
        st.metric(statements=len(tags_edges))

    with progress.Step(3, N_STEPS, "Tao index") as st:
        with session() as s:
            for stmt in indexes:
                execute(s, stmt + ";", "index")
        st.metric(statements=len(indexes))

    progress.done(space=space, rebuilt=rebuild,
                  statements=len(create_space) + len(tags_edges) + len(indexes))


if __name__ == "__main__":
    main()
