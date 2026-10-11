"""单音 CW 复指数 IQ——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
from numbers import Integral, Real

import numpy as np

__all__ = ["gen_tone"]


def _finite_real(name: str, value: object) -> float:
    """域自校验：有限实数（拒 bool/NaN/inf/复数/字符串等），返回 float。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} 必须为有限实数（拒 bool/NaN/inf），got {value!r}")
    as_float = float(value)
    if not math.isfinite(as_float):
        raise ValueError(f"{name} 必须为有限实数（拒 NaN/inf），got {value!r}")
    return as_float


def gen_tone(
    freq_offset_hz: float,
    n_samples: int,
    amplitude: float = 1.0,
    fs: float = 1.0,
) -> np.ndarray:
    """单音 CW 复指数 IQ：x[n] = amplitude * exp(j*2π*freq_offset_hz*n/fs)。

    - 相位从 0 起：x[0] = amplitude（纯实数，精确落点）。
    - 恒包络：float64 内积相位后转 complex64，|x| 偏差 ≤ float32 舍入量级。
    - 域自校验（防御纵深）：freq_offset_hz 有限实数；amplitude 有限 >0 且
      ∈[1e-30, 1e30]（输出 complex64 表示域：float32 上溢≈3.4e38/下溢≈1.2e-38，
      留两个量级裕量，B7中#4）；n_samples 正 int；fs 有限 >0——域错抛
      ValueError（含参数名）。
    """
    freq = _finite_real("freq_offset_hz", freq_offset_hz)
    amp = _finite_real("amplitude", amplitude)
    if amp <= 0.0:
        raise ValueError(f"amplitude 必须为有限正数（>0），got {amplitude!r}")
    if not 1e-30 <= amp <= 1e30:
        raise ValueError(
            f"amplitude 数值超界：须 1e-30 ≤ amplitude ≤ 1e30"
            f"（输出 complex64 表示域：float32 上溢≈3.4e38/下溢≈1.2e-38，留裕量），"
            f"got {amplitude!r}"
        )
    if isinstance(n_samples, bool) or not isinstance(n_samples, Integral):
        raise ValueError(f"n_samples 必须为正整数（拒 bool/非整型），got {n_samples!r}")
    n = int(n_samples)
    if n <= 0:
        raise ValueError(f"n_samples 必须为正整数（>0），got {n_samples!r}")
    fs_hz = _finite_real("fs", fs)
    if fs_hz <= 0.0:
        raise ValueError(f"fs 必须为有限正数（>0），got {fs!r}")

    t = np.arange(n, dtype=np.float64) / fs_hz
    iq = amp * np.exp(1j * (2.0 * math.pi * freq * t))
    iq[0] = amp  # 相位 0 精确落点（exp(1j*0.0) 本即精确，此为显式锚定）
    return iq.astype(np.complex64)
