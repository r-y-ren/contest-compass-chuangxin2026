"""红线总闸：功率/频段/声明三查，任一失败即拒（不可跳过）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def guard_compliance(config: dict) -> dict:
    """红线总闸：功率/频段/声明三查，任一失败即拒（不可跳过）。"""
    raise NotImplementedError("unimplemented:fn:guard_compliance")
