"""GPSDO/参考源状态读取（无硬件返回不可用+原因）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def probe_gpsdo_status(backend=None) -> dict:
    """GPSDO/参考源状态读取（无硬件返回不可用+原因）。"""
    raise NotImplementedError("unimplemented:fn:probe_gpsdo_status")
