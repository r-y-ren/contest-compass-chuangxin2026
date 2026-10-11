"""ESP32 链路驱动：串口连接+KPI 帧流（断开先停发射）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def drive_esp32_link(serial_config: dict) -> object:
    """ESP32 链路驱动：串口连接+KPI 帧流（断开先停发射）。"""
    raise NotImplementedError("unimplemented:fn:drive_esp32_link")
