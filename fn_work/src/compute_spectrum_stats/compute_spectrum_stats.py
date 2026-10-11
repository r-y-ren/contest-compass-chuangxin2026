"""频谱统计行：SNR/JSR 反演/平坦度/底噪口径——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def compute_spectrum_stats(window: dict, reference: dict | None = None) -> dict:
    """频谱统计行：SNR/JSR 反演/平坦度/底噪口径。"""
    raise NotImplementedError("unimplemented:fn:compute_spectrum_stats")
