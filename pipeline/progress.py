# -*- coding: utf-8 -*-
"""Giao thuc phat tien trinh dung chung cho moi script trong pipeline.

MUC DICH: 1 script chay duoc CA HAI che do ma khong can 2 ban output:
  - Chay bang CLI  -> nguoi doc thay dong log binh thuong, de hieu.
  - Chay qua web   -> Go doc stdout, bat dong bat dau bang `[[` de dung
                      thanh thanh tien trinh / stepper tren giao dien.

DINH DANG (moi thu 1 dong, JSON sau tag, LUON flush ngay):
  [[STEP]]  {"n":1,"of":4,"name":"...","status":"running"}
  [[STEP]]  {"n":1,"of":4,"status":"done","ms":120,"metric":{...}}
  [[LOG]]   {"msg":"..."}
  [[DONE]]  {...payload tuy y...}
  [[ERROR]] {"step":2,"msg":"..."}

Dong KHONG bat dau bang `[[` -> Go coi la log tho, forward nguyen van. Nho vay
cac script cu (in bang print thuong) van chay duoc ma khong phai sua gi.

QUAN TRONG — flush=True o moi dong: neu khong, Python buffer stdout khi ghi vao
pipe (khong phai terminal) va Go se chi nhan duoc TOAN BO output luc script ket
thuc -> thanh tien trinh dung im roi nhay 100%% mot phat, mat het y nghia.
"""
from __future__ import annotations

import json
import sys
import time

# Bat buoc UTF-8 cho stdout: bao cao co dau tieng Viet, console Windows mac dinh
# cp1252 se nem UnicodeEncodeError. Python >= 3.7 moi co reconfigure().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _emit(tag: str, payload: dict) -> None:
    print(f"[[{tag}]] {json.dumps(payload, ensure_ascii=False)}", flush=True)


def log(msg: str) -> None:
    """Dong log thuong — hien trong khung log cuon cua giao dien."""
    _emit("LOG", {"msg": msg})


def done(**payload) -> None:
    """Bao pipeline ket thuc THANH CONG. Payload di kem se duoc web doc de
    biet phai lay ket qua o dau (runId, duong dan file, so lieu tom tat)."""
    _emit("DONE", payload)


def error(step: int | None, msg: str) -> None:
    """Bao loi. KHONG tu goi sys.exit() — de nguoi goi quyet dinh dung hay chay tiep."""
    _emit("ERROR", {"step": step, "msg": msg})


class Step:
    """Context manager cho 1 buoc: tu phat `running` luc vao, `done` luc ra
    (kem thoi gian thuc te), va `ERROR` neu co ngoai le.

    Dung:
        with Step(2, 4, "Do chu trinh") as st:
            ...
            st.metric(raw_cycles=2581)

    Vi sao dung context manager thay vi goi tay 2 lan: khong the quen phat `done`,
    va thoi gian `ms` luon dung ke ca khi buoc thoat som bang return/exception.
    """

    def __init__(self, n: int, of: int, name: str):
        self.n, self.of, self.name = n, of, name
        self._metric: dict = {}
        self._t0 = 0.0

    def metric(self, **kv) -> None:
        """Gan so lieu ket qua cua buoc — hien ben canh ten buoc tren giao dien."""
        self._metric.update(kv)

    def __enter__(self) -> "Step":
        self._t0 = time.time()
        _emit("STEP", {"n": self.n, "of": self.of, "name": self.name, "status": "running"})
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        ms = int((time.time() - self._t0) * 1000)
        if exc_type is not None:
            error(self.n, f"{self.name}: {exc}")
            return False  # khong nuot ngoai le
        _emit("STEP", {
            "n": self.n, "of": self.of, "name": self.name,
            "status": "done", "ms": ms, "metric": self._metric,
        })
        return False
