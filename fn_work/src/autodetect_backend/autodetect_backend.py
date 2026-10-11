"""启动后端决策：探测→b210/降级 sim/显式失败不静默——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def autodetect_backend(explicit: str | None) -> tuple:
    """启动后端决策：探测→b210/降级 sim/显式失败不静默。"""
    raise NotImplementedError("unimplemented:fn:autodetect_backend")
