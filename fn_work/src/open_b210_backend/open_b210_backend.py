"""B210 真硬件后端：UHD 双通道初始化（CH1 TX/CH2 RX）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def open_b210_backend(params: dict) -> object:
    """B210 真硬件后端：UHD 双通道初始化（CH1 TX/CH2 RX）。"""
    raise NotImplementedError("unimplemented:fn:open_b210_backend")
