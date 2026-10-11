"""双通道参数下发与回读校验（频率/增益/采样率/时钟源）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def configure_b210_channels(device, params: dict) -> dict:
    """双通道参数下发与回读校验（频率/增益/采样率/时钟源）。"""
    raise NotImplementedError("unimplemented:fn:configure_b210_channels")
