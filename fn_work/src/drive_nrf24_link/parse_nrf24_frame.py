"""NRF24 单帧解析（发送/丢包/重传/RPD）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def parse_nrf24_frame(frame: bytes) -> dict:
    """NRF24 单帧解析（发送/丢包/重传/RPD）。"""
    raise NotImplementedError("unimplemented:fn:parse_nrf24_frame")
