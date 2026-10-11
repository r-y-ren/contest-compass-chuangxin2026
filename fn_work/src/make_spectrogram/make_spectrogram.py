"""IQ→谱图（STFT 参数化，训练推理共用，短段跳过）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def make_spectrogram(iq, params: dict) -> tuple:
    """IQ→谱图（STFT 参数化，训练推理共用，短段跳过）。"""
    raise NotImplementedError("unimplemented:fn:make_spectrogram")
