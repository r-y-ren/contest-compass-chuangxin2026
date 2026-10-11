"""监测谱采集→monitor.csv（频率 bin+功率+时间戳）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def capture_monitor_spectrum(ctx: dict, stream, params: dict) -> object:
    """监测谱采集→monitor.csv（频率 bin+功率+时间戳）。"""
    raise NotImplementedError("unimplemented:fn:capture_monitor_spectrum")
