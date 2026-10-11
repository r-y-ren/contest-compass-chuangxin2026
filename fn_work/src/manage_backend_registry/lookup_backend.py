"""按名（含别名）取工厂与能力元数据——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def lookup_backend(name: str) -> tuple:
    """按名（含别名）取工厂与能力元数据。"""
    raise NotImplementedError("unimplemented:fn:lookup_backend")
