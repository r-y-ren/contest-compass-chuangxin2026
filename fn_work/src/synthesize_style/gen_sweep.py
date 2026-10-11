"""线性扫频 IQ（相位连续）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def gen_sweep(f0: float, f1: float, duration_s: float, repeats: int = 1, fs: float = 1.0) -> object:
    """线性扫频 IQ（相位连续）。"""
    raise NotImplementedError("unimplemented:fn:gen_sweep")
