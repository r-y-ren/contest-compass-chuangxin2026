"""失效判据纯函数（默认 PER>10%）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def check_failure(per_result: dict, threshold: float = 0.10) -> dict:
    """失效判据纯函数（默认 PER>10%）。"""
    raise NotImplementedError("unimplemented:fn:check_failure")
