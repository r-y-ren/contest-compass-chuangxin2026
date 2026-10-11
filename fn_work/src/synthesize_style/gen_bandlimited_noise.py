"""带限高斯噪声 IQ（平坦度≤4dB 设计）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def gen_bandlimited_noise(bandwidth: float, n_samples: int, seed: int | None = None) -> tuple:
    """带限高斯噪声 IQ（平坦度≤4dB 设计）。"""
    raise NotImplementedError("unimplemented:fn:gen_bandlimited_noise")
