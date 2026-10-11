"""带限高斯噪声 IQ（平坦度≤4dB 设计）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
from numbers import Integral, Real

import numpy as np

__all__ = ["gen_bandlimited_noise"]

# 56MHz 带宽红线（口径同 check_style_params.BANDWIDTH_HZ_MAX，叶子内独立持有避免环依赖）。
BANDWIDTH_HZ_MAX = 56e6


def _finite_real(name: str, value: object) -> float:
    """域自校验：有限实数（拒 bool/NaN/inf/复数/字符串等），返回 float。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} 必须为有限实数（拒 bool/NaN/inf），got {value!r}")
    as_float = float(value)
    if not math.isfinite(as_float):
        raise ValueError(f"{name} 必须为有限实数（拒 NaN/inf），got {value!r}")
    return as_float


def gen_bandlimited_noise(
    bandwidth_hz: float,
    n_samples: int,
    fs: float = 1.0,
    center_offset_hz: float = 0.0,
    rms_amplitude: float = 1.0,
    seed: int | None = None,
) -> tuple[np.ndarray, dict]:
    """带限高斯噪声 IQ（频域法：白复高斯 → FFT → 矩形窗截带 → IFFT → RMS 归一化）。

    - 随机源：numpy.random.default_rng(seed)，seed=None 允许（每次真随机）；
      同 seed 两次调用逐位一致。
    - 截带：保留 FFT 频率轴上 [center_offset_hz − bw/2, center_offset_hz + bw/2)
      的 bin（矩形窗，边沿半开）；center_offset_hz 允许负值。带宽小于一个
      FFT bin 时退化为保留最靠近中心的单个 bin（保底 RMS 归一化良定义）。
    - 元数据（实测口径，如实返回）：
      * measured_bw_hz：实际保留 bin 数 × 频率分辨率 fs/n（频域构造下即信号
        真实支撑带宽，bin 量化误差为 fs/n 量级）；
      * occupied_bw99_hz：累积功率 0.5%–99.5% 分位点频宽（99% 功率带宽）；
      * flatness_db：带内 10%–90% 频段分组平均功率的最大/最小差（dB）——
        分组平均抑制周期图指数起伏，长样本（约 ≥8192 点）实测 ≤4dB 设计目标；
      * center_offset_hz / seed：回显输入。
    - 输出：complex64 ndarray，长度 n_samples，RMS 精确归一到 rms_amplitude。
    - 域自校验（防御纵深，均抛 ValueError 含参数名）：bandwidth_hz 有限 >0 且
      ≤fs/2（带限物理域）且 ≤56e6（红线）；n_samples 正 int（拒 bool）；
      fs 有限 >0；center_offset_hz 有限实数（负允许）；rms_amplitude 有限 >0；
      seed 为 int 或 None（拒 bool/浮点/字符串）。NaN/inf/bool 全拒。
    """
    bw = _finite_real("bandwidth_hz", bandwidth_hz)
    if bw <= 0.0:
        raise ValueError(f"bandwidth_hz 必须为正数（>0），got {bandwidth_hz!r}")
    if isinstance(n_samples, bool) or not isinstance(n_samples, Integral):
        raise ValueError(f"n_samples 必须为正整数（拒 bool/非整型），got {n_samples!r}")
    n = int(n_samples)
    if n <= 0:
        raise ValueError(f"n_samples 必须为正整数（>0），got {n_samples!r}")
    fs_hz = _finite_real("fs", fs)
    if fs_hz <= 0.0:
        raise ValueError(f"fs 必须为有限正数（>0），got {fs!r}")
    if bw > fs_hz / 2.0:
        raise ValueError(
            f"bandwidth_hz 超带限物理域（须 ≤fs/2={fs_hz / 2.0}），got {bandwidth_hz!r}"
        )
    if bw > BANDWIDTH_HZ_MAX:
        raise ValueError(
            f"bandwidth_hz 超 56MHz 红线（须 ≤{BANDWIDTH_HZ_MAX}），got {bandwidth_hz!r}"
        )
    center = _finite_real("center_offset_hz", center_offset_hz)
    rms = _finite_real("rms_amplitude", rms_amplitude)
    if rms <= 0.0:
        raise ValueError(f"rms_amplitude 必须为有限正数（>0），got {rms_amplitude!r}")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, Integral)):
        raise ValueError(f"seed 必须为 int 或 None（拒 bool/浮点/字符串），got {seed!r}")
    seed_out = None if seed is None else int(seed)

    # 1) 白复高斯（时域）→ FFT；2) 矩形窗截带 → IFFT。
    rng = np.random.default_rng(seed_out)
    white = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    spec = np.fft.fft(white)
    freqs = np.fft.fftfreq(n, d=1.0 / fs_hz)
    f_lo = center - bw / 2.0
    f_hi = center + bw / 2.0
    mask = (freqs >= f_lo) & (freqs < f_hi)
    if not mask.any():  # 带宽 < 单 bin 分辨率：退化为最近 bin，保底非零
        mask[int(np.argmin(np.abs(freqs - center)))] = True
    y = np.fft.ifft(spec * mask)

    # 3) RMS 归一化（float64 域完成再转 complex64）。
    y = y * (rms / math.sqrt(float(np.mean(np.abs(y) ** 2))))
    iq = y.astype(np.complex64)

    # 4) 实测元数据：基于交付信号（complex64）重算频谱，如实返回。
    df = fs_hz / n
    measured_bw_hz = float(int(mask.sum()) * df)
    spec_f = np.fft.fft(iq.astype(np.complex128))
    power = np.abs(spec_f) ** 2
    order = np.argsort(freqs)
    f_asc = freqs[order]
    p_asc = power[order]
    total = float(p_asc.sum())
    cum = np.cumsum(p_asc)
    i_lo = min(int(np.searchsorted(cum, 0.005 * total)), n - 1)
    i_hi = min(int(np.searchsorted(cum, 0.995 * total)), n - 1)
    i_hi = max(i_hi, i_lo + 1)
    occupied_bw99_hz = float(f_asc[i_hi] - f_asc[i_lo])

    # 带内平坦度：带内 bin 按频率顺序等宽分组取平均（抑制周期图指数起伏），
    # 取带内 10%–90% 频段上分组功率的最大/最小差（dB）。
    p_in = p_asc[mask[order]]
    n_in = int(p_in.size)
    g = max(1, n_in // 16)
    n_grp = n_in // g
    groups = p_in[: n_grp * g].reshape(n_grp, g).mean(axis=1)
    g_lo = int(math.floor(0.1 * n_grp))
    g_hi = max(int(math.ceil(0.9 * n_grp)), g_lo + 1)
    seg = groups[g_lo:g_hi]
    p_min = float(seg.min())
    flatness_db = 10.0 * math.log10(float(seg.max()) / p_min) if p_min > 0.0 else float("inf")

    meta = {
        "measured_bw_hz": measured_bw_hz,
        "occupied_bw99_hz": occupied_bw99_hz,
        "flatness_db": flatness_db,
        "center_offset_hz": center,
        "seed": seed_out,
    }
    return iq, meta
