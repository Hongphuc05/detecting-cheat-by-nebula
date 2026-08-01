# -*- coding: utf-8 -*-
"""Ket noi NebulaGraph dung chung cho ca pipeline — 1 cho duy nhat doc cau hinh.

Vi sao tach rieng: truoc day moi script tu viet lai get_session() giong het nhau.
Khi doi host/port/space chi can sua 1 file thay vi 4, va khong the xay ra chuyen
2 script tro vao 2 space khac nhau vi ai do sua thieu.

Bien moi truong:
  NEBULA_HOST (127.0.0.1) NEBULA_PORT (9669) NEBULA_USER (root) NEBULA_PASSWORD (nebula)
  SPACE (invoice_agg_graph)
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager

from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool

# Ten space hop le trong Nebula: chu, so, gach duoi. Chan luon injection tu web
# (Go cung validate lai, nhung phong thu nhieu lop — script co the bi goi truc tiep).
SPACE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def get_space() -> str:
    space = os.environ.get("SPACE", "invoice_agg_graph")
    if not SPACE_RE.match(space):
        raise ValueError(f"Ten space khong hop le: {space!r}")
    return space


@contextmanager
def session(use_space: bool = True):
    """Dung: `with session() as s: s.execute(...)`. Tu dong tra session ve pool
    va dong pool ke ca khi co ngoai le."""
    host = os.environ.get("NEBULA_HOST", "127.0.0.1")
    port = int(os.environ.get("NEBULA_PORT", "9669"))
    user = os.environ.get("NEBULA_USER", "root")
    pwd = os.environ.get("NEBULA_PASSWORD", "nebula")

    pool = ConnectionPool()
    if not pool.init([(host, port)], Config()):
        raise RuntimeError(
            f"Khong ket noi duoc NebulaGraph tai {host}:{port}. "
            f"Kiem tra: docker ps | grep nebula-graphd"
        )
    s = pool.get_session(user, pwd)
    try:
        if use_space:
            execute(s, f"USE {get_space()};")
        yield s
    finally:
        s.release()
        pool.close()


def execute(s, ngql: str, label: str = ""):
    """Chay nGQL, nem RuntimeError kem context neu that bai.

    KHONG BAO GIO nuot loi im lang: mot INSERT that bai ma khong bao se tao ra
    do thi thieu canh, va bao cao gian lan sau do sai ma khong ai biet tai sao.
    """
    resp = s.execute(ngql)
    if not resp.is_succeeded():
        tag = f"[{label}] " if label else ""
        raise RuntimeError(f"{tag}nGQL loi: {resp.error_msg()}\n--- Query ---\n{ngql[:400]}")
    return resp


def esc(v) -> str:
    """Escape cho string literal trong nGQL."""
    return str(v).replace("\\", "\\\\").replace('"', '\\"')


def as_num(v) -> float:
    """Doc 1 o so ma KHONG can biet truoc no la int hay double.

    Vi sao can (da mac loi that): cung 1 thuoc tinh `total_amount` khai bao la
    double, nhung Nebula tra ve kieu INT o space `tax_graph` va DOUBLE o space
    `invoice_agg_graph` — goi thang as_double() se nem
    "expect int type, but is int" tren space kia. Gio doc space nao cung duoc.
    """
    if v.is_int():
        return float(v.as_int())
    if v.is_double():
        return v.as_double()
    if v.is_null() or v.is_empty():
        return 0.0
    try:
        return float(str(v).strip('"'))
    except ValueError:
        return 0.0
