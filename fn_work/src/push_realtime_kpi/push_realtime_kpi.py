"""实时流枢纽：三路→WS 广播（<500ms 判据/积压降频）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def push_realtime_kpi(source, hub) -> dict:
    """实时流枢纽：三路→WS 广播（<500ms 判据/积压降频）。"""
    raise NotImplementedError("unimplemented:fn:push_realtime_kpi")
