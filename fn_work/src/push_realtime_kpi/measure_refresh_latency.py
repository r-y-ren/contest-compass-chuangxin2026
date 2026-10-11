"""端到端刷新延迟统计（P50/P95/超阈率）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def measure_refresh_latency(frame_stamps) -> dict:
    """端到端刷新延迟统计（P50/P95/超阈率）。"""
    raise NotImplementedError("unimplemented:fn:measure_refresh_latency")
