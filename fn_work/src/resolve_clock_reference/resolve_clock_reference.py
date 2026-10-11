"""时基决策：GPS/10MHz/PPS 探测→驯服或软件钟降级+口径——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def resolve_clock_reference(backend=None) -> dict:
    """时基决策：GPS/10MHz/PPS 探测→驯服或软件钟降级+口径。"""
    raise NotImplementedError("unimplemented:fn:resolve_clock_reference")
