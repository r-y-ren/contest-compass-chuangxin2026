"""按名登记后端工厂（含契约形式检查）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def register_backend(name: str, factory, meta: dict, *, override: bool = False) -> None:
    """按名登记后端工厂（含契约形式检查）。"""
    raise NotImplementedError("unimplemented:fn:register_backend")
