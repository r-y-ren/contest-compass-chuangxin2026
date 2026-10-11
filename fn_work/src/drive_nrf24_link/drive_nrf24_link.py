"""NRF24 链路驱动：计数帧流（丢包/重传，无 RSSI 口径）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def drive_nrf24_link(serial_config: dict) -> object:
    """NRF24 链路驱动：计数帧流（丢包/重传，无 RSSI 口径）。"""
    raise NotImplementedError("unimplemented:fn:drive_nrf24_link")
