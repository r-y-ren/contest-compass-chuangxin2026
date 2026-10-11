"""线性扫频 IQ（相位连续，f0→f1 线性过渡，可重复）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math

import numpy as np


def _as_finite_real(name: str, value: object) -> float:
    """域校验：有限实数（拒 bool/NaN/±inf/非数值型），返回 float。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite real number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite real number, got {value!r}")
    return number


def gen_sweep(
    f0: float,
    f1: float,
    duration_s: float,
    repeats: int = 1,
    fs: float = 1.0,
    amplitude: float = 1.0,
) -> np.ndarray:
    """线性扫频 IQ（相位连续）。

    单次扫频相位累积 phase[n] = 2π*(f0*t + 0.5*k*t²)，k=(f1-f0)/duration_s，
    t = n/fs；每次 repeats 重复相位重置为 0；输出长度 round(duration_s*fs)*repeats，
    恒包络 amplitude，dtype complex64。f0>f1 为下扫，同样允许。
    """
    f0 = _as_finite_real("f0", f0)
    f1 = _as_finite_real("f1", f1)
    duration_s = _as_finite_real("duration_s", duration_s)
    if duration_s <= 0:
        raise ValueError(f"duration_s must be > 0, got {duration_s!r}")
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
        raise ValueError(f"repeats must be a positive int, got {repeats!r}")
    fs = _as_finite_real("fs", fs)
    if fs <= 0:
        raise ValueError(f"fs must be > 0, got {fs!r}")
    amplitude = _as_finite_real("amplitude", amplitude)
    if amplitude <= 0:
        raise ValueError(f"amplitude must be a finite real > 0, got {amplitude!r}")

    n_per = int(round(duration_s * fs))
    t = np.arange(n_per, dtype=np.float64) / fs
    k = (f1 - f0) / duration_s
    phase = 2.0 * np.pi * (f0 * t + 0.5 * k * t * t)
    one_shot = amplitude * np.exp(1j * phase)
    return np.ascontiguousarray(np.tile(one_shot, repeats), dtype=np.complex64)
