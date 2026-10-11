"""增益档→估计注入功率→JSR 换算（缺表拒绝）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def lookup_jsr(gain_step, freq_hz: float, signal_power_db: float) -> dict:
    """增益档→估计注入功率→JSR 换算（缺表拒绝）。"""
    raise NotImplementedError("unimplemented:fn:lookup_jsr")
