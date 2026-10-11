"""ESP32 单帧解析（seq/错包/重传/RSSI+校验）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def parse_esp32_frame(frame: bytes) -> dict:
    """ESP32 单帧解析（seq/错包/重传/RSSI+校验）。"""
    raise NotImplementedError("unimplemented:fn:parse_esp32_frame")
