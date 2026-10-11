"""线性调频 chirp IQ（B7 叶子，上游 synthesize_style）——重写规约与签名意图详见 fn_docs/responsibility.md。

以 center_hz 为中心、带宽 bandwidth_hz 在周期 period_s 内扫过，重复至 n_samples 个样本：
- sawtooth：周期内 f(u) = center − bw/2 + bw·u/period，扫到高边沿后瞬回低边沿；
- triangle：前半周期从低边沿升到高边沿，后半周期降回（斜率为锯齿的两倍）。
相位按瞬时频率积分连续累积：每个完整周期对相位（单位：周）恰贡献 center·period
（升/降扫积分抵消，仅余中心频率项），故跨周期相位连续——周期边界只有频率瞬跳，
相位积分不断裂。输出恒包络、长度 n_samples（不整周期直接截断）、complex64。
"""
from __future__ import annotations

import math
from numbers import Integral

import numpy as np

__all__ = ["gen_chirp"]

_VALID_SHAPES = ("sawtooth", "triangle")


def _finite_float(value, name: str) -> float:
    """数值参数校验：必须为有限实数（拒 bool/NaN/±inf/字符串等非数值）。

    错误信息含参数名，便于上游定位。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 必须为有限实数（拒 bool/非数值）: {value!r}")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} 超出 float 可表示范围: {value!r}") from None
    if not math.isfinite(number):
        raise ValueError(f"{name} 必须为有限实数（拒 NaN/inf）: {value!r}")
    return number


def gen_chirp(
    center_hz: float,
    bandwidth_hz: float,
    period_s: float,
    n_samples: int,
    fs: float = 1.0,
    shape: str = "sawtooth",
    amplitude: float = 1.0,
) -> np.ndarray:
    """生成线性调频 chirp 复基带恒包络 IQ（complex64，长度 n_samples）。

    输入:
        center_hz: 扫频中心频率（Hz，有限实数）；
        bandwidth_hz: 扫频带宽（Hz，>0，扫频范围为 center±bandwidth/2）；
        period_s: 单次扫频周期（秒，>0）；
        n_samples: 输出样本数（正 int，不整周期时截断到该长度）；
        fs: 采样率（Hz，>0，默认 1.0）；
        shape: 'sawtooth'（锯齿，升后瞬回）或 'triangle'（三角，升后降各半周期）；
        amplitude: 恒包络幅度（>0，默认 1.0）。
    输出:
        ndarray complex64，长度 n_samples，|x| ≡ amplitude，相位跨周期连续。
    错误:
        ValueError（信息含参数名）：center/bandwidth/period/fs/amplitude 非有限实数
        或拒 bool；bandwidth/period/fs/amplitude 非正，amplitude 还须 ∈[1e-30, 1e30]
        （输出 complex64 表示域，B7中#4）；n_samples 非正 int（拒 bool/float，接受
        任意 Integral——np.int64 过，B7低#12）；shape 不在 {'sawtooth','triangle'}。
    """
    center = _finite_float(center_hz, "center_hz")
    bandwidth = _finite_float(bandwidth_hz, "bandwidth_hz")
    period = _finite_float(period_s, "period_s")
    rate = _finite_float(fs, "fs")
    amp = _finite_float(amplitude, "amplitude")

    if bandwidth <= 0.0:
        raise ValueError(f"bandwidth_hz 必须为正数: {bandwidth_hz!r}")
    if period <= 0.0:
        raise ValueError(f"period_s 必须为正数: {period_s!r}")
    if rate <= 0.0:
        raise ValueError(f"fs 必须为正数: {fs!r}")
    if amp <= 0.0:
        raise ValueError(f"amplitude 必须为正数: {amplitude!r}")
    if not 1e-30 <= amp <= 1e30:
        raise ValueError(
            f"amplitude 数值超界：须 1e-30 ≤ amplitude ≤ 1e30"
            f"（输出 complex64 表示域：float32 上溢≈3.4e38/下溢≈1.2e-38，留裕量），"
            f"got {amplitude!r}"
        )
    if isinstance(n_samples, bool) or not isinstance(n_samples, Integral) or n_samples <= 0:
        raise ValueError(f"n_samples 必须为正 int: {n_samples!r}")
    n = int(n_samples)
    if not isinstance(shape, str) or shape not in _VALID_SHAPES:
        raise ValueError(f"shape 必须为 {'/'.join(_VALID_SHAPES)} 之一: {shape!r}")

    t = np.arange(n, dtype=np.float64) / rate
    cycles = np.floor(t / period)  # 已扫过的完整周期数 k
    u = t - cycles * period  # 周期内时间 ∈ [0, period)
    low = center - 0.5 * bandwidth  # 扫频低边沿（每周期起点）
    high = center + 0.5 * bandwidth  # 扫频高边沿（锯齿终点 / 三角峰值点）
    half = 0.5 * period

    if shape == "sawtooth":
        # 周期内 f(u) = low + bandwidth·u/period，积分得 low·u + bandwidth·u²/(2·period)
        phase_partial = low * u + 0.5 * bandwidth * u * u / period
    else:
        # 三角：前半周期 f(u) = low + bandwidth·u/half（升到 high），
        # 后半周期 f = high − bandwidth·v/half（v = u − half，降回 low）。
        v = u - half
        phase_partial = np.where(
            u < half,
            low * u + 0.5 * bandwidth * u * u / half,
            center * half + high * v - 0.5 * bandwidth * v * v / half,
        )

    # 每个完整周期对相位恰贡献 center·period（升/降扫相互抵消）——跨周期相位连续
    phase_cycles = cycles * (center * period) + phase_partial
    return (amp * np.exp(2j * np.pi * phase_cycles)).astype(np.complex64)
