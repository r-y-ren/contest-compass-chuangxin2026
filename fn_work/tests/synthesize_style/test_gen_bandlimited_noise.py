"""gen_bandlimited_noise 对抗测试——带限高斯噪声 IQ（B7 叶子，上游 synthesize_style）。"""
from __future__ import annotations

import numpy as np
import pytest

from src.synthesize_style.gen_bandlimited_noise import gen_bandlimited_noise


def _rms(iq: np.ndarray) -> float:
    """复信号 RMS（float64 域计算）。"""
    z = iq.astype(np.complex128)
    return float(np.sqrt(np.mean(np.real(z) ** 2 + np.imag(z) ** 2)))


def _band_mask(n: int, fs: float, center: float, bw: float) -> np.ndarray:
    """与生成器同口径的半开矩形带 [center-bw/2, center+bw/2)。"""
    freqs = np.fft.fftfreq(n, d=1.0 / fs)
    return (freqs >= center - bw / 2.0) & (freqs < center + bw / 2.0)


def test_same_seed_bitwise_reproducible():
    """同 seed 两次调用 → IQ 逐位一致、meta 数值一致（含 None 默认参数路径）。"""
    iq1, m1 = gen_bandlimited_noise(0.2, 4096, fs=1.0, seed=123)
    iq2, m2 = gen_bandlimited_noise(0.2, 4096, fs=1.0, seed=123)
    assert iq1.dtype == iq2.dtype == np.complex64
    assert np.array_equal(iq1, iq2)
    assert np.array_equal(iq1.view(np.float32), iq2.view(np.float32))  # 逐位
    assert m1 == m2


def test_seed_none_random_but_rms_on_target():
    """seed=None → 两次输出随机不同，但 RMS 统计量仍归一到目标（容差 1%）。"""
    iq1, _ = gen_bandlimited_noise(0.2, 8192, seed=None)
    iq2, _ = gen_bandlimited_noise(0.2, 8192, seed=None)
    assert not np.array_equal(iq1, iq2)  # 随机源真随机（碰撞概率≈0）
    for iq in (iq1, iq2):
        assert _rms(iq) == pytest.approx(1.0, rel=0.01)


def test_occupied_bw99_within_10pct_of_target():
    """99% 功率带宽（0.5%–99.5% 分位频宽）落在目标带宽 ±10% 容差带内。"""
    bw, fs, n = 0.2, 1.0, 16384
    _, meta = gen_bandlimited_noise(bw, n, fs=fs, seed=7)
    occ = meta["occupied_bw99_hz"]
    assert 0.9 * bw <= occ <= 1.1 * bw


def test_out_of_band_power_suppressed():
    """矩形窗截带 → 带外功率占比 <5%（实测远低，仅 bin 量化/float32 舍入残余）。"""
    bw, fs, n, center = 0.2, 1.0, 8192, 0.1
    iq, meta = gen_bandlimited_noise(bw, n, fs=fs, center_offset_hz=center, seed=11)
    power = np.abs(np.fft.fft(iq.astype(np.complex128))) ** 2
    mask = _band_mask(n, fs, center, meta["measured_bw_hz"])
    out_frac = float(power[~mask].sum() / power.sum())
    assert out_frac < 0.05


def test_flatness_long_sample_within_4db():
    """足够长样本 → 实测带内平坦度 ≤4dB 设计目标（如实返回的 meta 值）。"""
    for n in (8192, 65536):
        _, meta = gen_bandlimited_noise(0.2, n, fs=1.0, seed=42)
        assert 0.0 <= meta["flatness_db"] <= 4.0


@pytest.mark.parametrize("center", [0.0, 0.15, -0.15])
def test_center_offset_shifts_spectral_centroid(center):
    """center_offset 平移频谱峰群：功率谱质心 ≈ center（负偏置同样成立）。"""
    bw, fs, n = 0.2, 1.0, 8192
    iq, _ = gen_bandlimited_noise(bw, n, fs=fs, center_offset_hz=center, seed=5)
    freqs = np.fft.fftfreq(n, d=1.0 / fs)
    power = np.abs(np.fft.fft(iq.astype(np.complex128))) ** 2
    centroid = float((freqs * power).sum() / power.sum())
    assert centroid == pytest.approx(center, abs=0.02 * fs)


def test_rms_normalization_and_scaling():
    """RMS 归一化断言（容差 1%）：不同 rms_amplitude 精确缩放（线性传递）。"""
    iq1, _ = gen_bandlimited_noise(0.2, 4096, rms_amplitude=1.0, seed=9)
    iq25, _ = gen_bandlimited_noise(0.2, 4096, rms_amplitude=2.5, seed=9)
    iq01, _ = gen_bandlimited_noise(0.2, 4096, rms_amplitude=0.1, seed=9)
    assert _rms(iq1) == pytest.approx(1.0, rel=0.01)
    assert _rms(iq25) == pytest.approx(2.5, rel=0.01)
    assert _rms(iq01) == pytest.approx(0.1, rel=0.01)
    assert np.allclose(iq25, 2.5 * iq1, rtol=1e-5, atol=1e-6)


def test_bandwidth_56m_exactly_passes():
    """bandwidth=56e6（fs=120e6，fs/2=60e6 内）恰过红线等号；measured_bw 对齐。"""
    fs, bw, n = 120e6, 56e6, 65536
    iq, meta = gen_bandlimited_noise(bw, n, fs=fs, seed=3)
    assert iq.dtype == np.complex64
    assert abs(meta["measured_bw_hz"] - bw) <= 2 * fs / n  # bin 量化级
    assert _rms(iq) == pytest.approx(1.0, rel=0.01)


@pytest.mark.parametrize(
    "bw,fs",
    [
        (60e6, 100e6),  # >fs/2（带限物理域），且 <56e6 红线 → fs/2 规则
        (57e6, 120e6),  # fs/2=60e6 内但 >56e6 → 红线拒
        (0.6, 1.0),  # 归一化域同规则：>fs/2
    ],
)
def test_bandwidth_upper_bound_rejected(bw, fs):
    """bandwidth 超 fs/2 或超 56MHz 红线 → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="bandwidth_hz"):
        gen_bandlimited_noise(bw, 1024, fs=fs, seed=1)


@pytest.mark.parametrize("bad_bw", [0.0, -5e6, -0.2, float("nan"), float("inf"), -float("inf"), True, False, "0.2", 1 + 2j])
def test_bandwidth_domain_rejected(bad_bw):
    """bandwidth 0/负/NaN/inf/bool/复数/字符串 → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="bandwidth_hz"):
        gen_bandlimited_noise(bad_bw, 16, seed=1)


@pytest.mark.parametrize("bad_n", [0, -1, True, False, 1.5, 16.0, "8", None])
def test_n_samples_domain_rejected(bad_n):
    """n_samples 0/负/bool/浮点/字符串/None → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="n_samples"):
        gen_bandlimited_noise(0.2, bad_n, seed=1)


@pytest.mark.parametrize("bad_fs", [0.0, -100.0, float("nan"), float("inf"), True, False, "1.0"])
def test_fs_domain_rejected(bad_fs):
    """fs 0/负/NaN/inf/bool/字符串 → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="fs"):
        gen_bandlimited_noise(0.2, 16, fs=bad_fs, seed=1)


@pytest.mark.parametrize("bad_center", [float("nan"), float("inf"), True, "0.1", 0.1 + 0.2j])
def test_center_offset_domain_rejected(bad_center):
    """center_offset NaN/inf/bool/字符串/复数 → ValueError（负值合法另测）。"""
    with pytest.raises(ValueError, match="center_offset_hz"):
        gen_bandlimited_noise(0.2, 16, center_offset_hz=bad_center, seed=1)


@pytest.mark.parametrize("bad_rms", [0.0, -1.0, float("nan"), float("inf"), True, "1.0"])
def test_rms_amplitude_domain_rejected(bad_rms):
    """rms_amplitude 0/负/NaN/inf/bool/字符串 → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="rms_amplitude"):
        gen_bandlimited_noise(0.2, 16, rms_amplitude=bad_rms, seed=1)


@pytest.mark.parametrize("bad_seed", [True, False, 1.5, "7", 3 + 4j])
def test_seed_domain_rejected(bad_seed):
    """seed bool/浮点/字符串/复数 → ValueError（None 与 int 合法）。"""
    with pytest.raises(ValueError, match="seed"):
        gen_bandlimited_noise(0.2, 16, seed=bad_seed)


def test_meta_key_set_and_echo():
    """meta 键集恰为五键；center_offset/seed 如实回显。"""
    iq, meta = gen_bandlimited_noise(0.2, 2048, fs=2.0, center_offset_hz=-0.3, seed=77)
    assert isinstance(iq, np.ndarray) and isinstance(meta, dict)
    assert set(meta) == {"measured_bw_hz", "occupied_bw99_hz", "flatness_db", "center_offset_hz", "seed"}
    assert meta["center_offset_hz"] == -0.3
    assert meta["seed"] == 77
    assert all(isinstance(meta[k], float) for k in ("measured_bw_hz", "occupied_bw99_hz", "flatness_db"))
    assert 0.0 < meta["measured_bw_hz"] <= 0.2 * 1.05
    assert meta["occupied_bw99_hz"] > 0.0


def test_output_dtype_and_length():
    """输出 complex64 ndarray、一维、长度恰为 n_samples。"""
    iq, _ = gen_bandlimited_noise(0.25, 37, fs=10.0, seed=2)
    assert isinstance(iq, np.ndarray)
    assert iq.dtype == np.complex64
    assert iq.ndim == 1
    assert iq.shape == (37,)


def test_default_fs_matches_explicit():
    """默认 fs=1.0 与显式 fs=1.0 同 seed 逐位一致。"""
    iq_def, m_def = gen_bandlimited_noise(0.2, 512, seed=13)
    iq_exp, m_exp = gen_bandlimited_noise(0.2, 512, fs=1.0, seed=13)
    assert np.array_equal(iq_def, iq_exp)
    assert m_def == m_exp


def test_narrow_band_nearest_bin_fallback():
    """带宽 < 频率分辨率 → 退化为最近单 bin：输出仍良定义、measured_bw=df。"""
    n, fs = 64, 1.0
    iq, meta = gen_bandlimited_noise(1e-4, n, fs=fs, seed=4)  # df=1/64≈0.0156 ≫ bw
    assert iq.dtype == np.complex64
    assert _rms(iq) == pytest.approx(1.0, rel=0.01)
    assert meta["measured_bw_hz"] == pytest.approx(fs / n)
    assert meta["occupied_bw99_hz"] > 0.0
