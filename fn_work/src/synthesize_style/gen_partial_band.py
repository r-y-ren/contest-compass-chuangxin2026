"""部分频带干扰 IQ——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
from numbers import Integral, Real

import numpy as np

__all__ = ["gen_partial_band"]


def _finite_real(name: str, value: object) -> float:
    """域自校验：有限实数（拒 bool/NaN/inf/复数/字符串等），返回 float。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} 必须为有限实数（拒 bool/NaN/inf），got {value!r}")
    as_float = float(value)
    if not math.isfinite(as_float):
        raise ValueError(f"{name} 必须为有限实数（拒 NaN/inf），got {value!r}")
    return as_float


def _positive_real(name: str, value: object) -> float:
    """域自校验：有限正实数（>0，拒 0/负/NaN/inf/bool）。"""
    as_float = _finite_real(name, value)
    if as_float <= 0.0:
        raise ValueError(f"{name} 必须为有限正数（>0），got {value!r}")
    return as_float


def gen_partial_band(
    fraction: float,
    victim_bw_hz: float,
    n_samples: int,
    center_offset_hz: float = 0.0,
    fs: float = 1.0,
    rms_amplitude: float = 1.0,
    seed: int | None = None,
) -> tuple[np.ndarray, dict]:
    """部分频带干扰 IQ：白复高斯经频域矩形窗截取被测带宽的一部分。

    生成链：default_rng(seed) 白复高斯 → FFT → 仅保留落入
    [center_offset_hz − occupied/2, center_offset_hz + occupied/2) 的 bin →
    IFFT → 时域 RMS 归一化 rms_amplitude → complex64。其中
    occupied_bw_hz = victim_bw_hz × fraction。频域矩形窗保证周期图在被占带内
    平坦、带外恒零（矩形截止无滚降）。

    - fraction∈(0,1]：占被测带宽的比例（拒 bool）；fraction=1 且偏置 0 退化为
      零中心全被测带（即带限噪声）。
    - 带容约束：|center_offset_hz| + victim_bw_hz×fraction/2 ≤ victim_bw_hz/2
      ——干扰带不得越出被测带（等式边界按 1e-9 相对容差放行，越界 ValueError）；
      混叠域（B7低#7）：|center_offset_hz| + victim_bw_hz×fraction/2 ≤ fs/2
      （等式边界按 1e-9 相对容差放行，越界 ValueError 含两值）。
    - 被占带宽不足一个 FFT bin 时，保底保留距带心最近的单个 bin，输出非全零，
      meta 增 'fallback_bin': True 且 occupied_bw_hz 如实报单个 bin 宽 fs/n。
    - meta：{'victim_bw_hz','occupied_bw_hz','fraction','center_offset_hz','seed'}，
      其中 occupied_bw_hz 为实测占位（实际保留 bin 数 × fs/n；正常路径与标称
      victim_bw_hz×fraction 做一致性检查——至多差一个 bin——后如实上报）；
      保底路径额外含 'fallback_bin': True。seed 回显规范化 int（或 None）。
    - 域自校验（防御纵深）：fraction ∈ (0,1]；victim_bw_hz/fs/rms_amplitude 有限
      正数，rms_amplitude 还须 ∈[1e-30, 1e30]（输出 complex64 表示域，B7中#4）；
      center_offset_hz 有限实数；n_samples 正整数（拒 bool/浮点/字符串）；
      seed 为 int 或 None（拒 bool/浮点/字符串，B7低#6，与 blnoise 同口径）
      ——域错抛 ValueError（含参数名）。
    """
    frac = _finite_real("fraction", fraction)
    if not 0.0 < frac <= 1.0:
        raise ValueError(f"fraction 必须在 (0, 1] 内，got {fraction!r}")
    bw = _positive_real("victim_bw_hz", victim_bw_hz)
    if isinstance(n_samples, bool) or not isinstance(n_samples, Integral):
        raise ValueError(f"n_samples 必须为正整数（拒 bool/非整型），got {n_samples!r}")
    n = int(n_samples)
    if n <= 0:
        raise ValueError(f"n_samples 必须为正整数（>0），got {n_samples!r}")
    offset = _finite_real("center_offset_hz", center_offset_hz)
    fs_hz = _positive_real("fs", fs)
    rms = _positive_real("rms_amplitude", rms_amplitude)
    # 数值表示域（B7中#4）：complex64 输出幅度上下界，防 float32 上溢/下溢。
    if not 1e-30 <= rms <= 1e30:
        raise ValueError(
            f"rms_amplitude 数值超界：须 1e-30 ≤ rms_amplitude ≤ 1e30"
            f"（输出 complex64 表示域：float32 上溢≈3.4e38/下溢≈1.2e-38，留裕量），"
            f"got {rms_amplitude!r}"
        )
    # seed 统一 int|None 校验（B7低#6，与 gen_bandlimited_noise 同口径）。
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, Integral)):
        raise ValueError(f"seed 必须为 int 或 None（拒 bool/浮点/字符串），got {seed!r}")
    seed_out = None if seed is None else int(seed)

    occ_bw = bw * frac
    if abs(offset) + occ_bw / 2.0 > bw / 2.0 + bw * 1e-9:  # 浮点等式边界放行
        raise ValueError(
            "center_offset_hz 越界：|center_offset_hz| + victim_bw_hz*fraction/2 须 ≤ "
            f"victim_bw_hz/2，got |{offset}| + {occ_bw / 2.0} > {bw / 2.0}"
        )
    # 混叠域（B7低#7）：占位带不得越出采样域 ±fs/2（等式边界按相对容差放行）。
    alias_edge = abs(offset) + occ_bw / 2.0
    if alias_edge > fs_hz / 2.0 * (1.0 + 1e-9):
        raise ValueError(
            "center_offset_hz 超混叠域：|center_offset_hz| + victim_bw_hz*fraction/2 "
            f"须 ≤ fs/2，got |{offset}| + {occ_bw / 2.0} = {alias_edge} > fs/2={fs_hz / 2.0}"
        )

    rng = np.random.default_rng(seed_out)
    white = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    freqs = np.fft.fftfreq(n, d=1.0 / fs_hz)
    f_lo = offset - occ_bw / 2.0
    f_hi = offset + occ_bw / 2.0
    mask = (freqs >= f_lo) & (freqs < f_hi)
    fallback_bin = not bool(mask.any())
    if fallback_bin:  # occ < 1 个 bin：保底距带心最近的单个 bin
        mask[int(np.argmin(np.abs(freqs - offset)))] = True
    x = np.fft.ifft(np.fft.fft(white) * mask)

    cur_rms = math.sqrt(float(np.vdot(x, x).real) / n)
    iq = (x * (rms / cur_rms)).astype(np.complex64)

    # 实测占位（B7中#5）：实际保留 bin 数 × df，与标称 occ 一致性检查后如实上报。
    df = fs_hz / n
    occupied_actual = float(int(mask.sum()) * df)
    if not fallback_bin and abs(occupied_actual - occ_bw) > df:
        # 内部不变量（半开矩形窗 bin 计数与带宽至多差一个 df，理论不可达，防漂移）。
        raise ValueError(
            f"occupied_bw_hz 一致性校验失败：实际占位 {occupied_actual} 与标称 "
            f"{occ_bw} 差超单 bin（df={df}）"
        )
    meta = {
        "victim_bw_hz": bw,
        "occupied_bw_hz": occupied_actual,
        "fraction": frac,
        "center_offset_hz": offset,
        "seed": seed_out,
    }
    if fallback_bin:
        meta["fallback_bin"] = True  # 保底单 bin：occ < df 不可分辨，如实报 bin 宽 fs/n
    return iq, meta
