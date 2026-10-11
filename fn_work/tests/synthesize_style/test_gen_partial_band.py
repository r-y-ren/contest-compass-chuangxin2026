"""gen_partial_band 对抗测试——部分频带干扰 IQ（B7 叶子，上游 synthesize_style）。"""
from __future__ import annotations

import numpy as np
import pytest

from src.synthesize_style.gen_partial_band import gen_partial_band


def _psd_shifted(x: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """周期图（|FFT|²）与升频轴（fftshift），用于谱形状断言。"""
    n = len(x)
    psd = np.abs(np.fft.fft(x.astype(np.complex128))) ** 2
    return np.fft.fftshift(psd), np.fft.fftshift(np.fft.fftfreq(n, d=1.0 / fs))


def _reference_bandlimited(bw: float, n: int, fs: float, seed: int) -> np.ndarray:
    """独立实现对照：fftshift 域矩形窗零中心带限白噪声，RMS 归一到 1。"""
    rng = np.random.default_rng(seed)
    w = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    spec = np.fft.fftshift(np.fft.fft(w))
    f = np.fft.fftshift(np.fft.fftfreq(n, d=1.0 / fs))
    spec = np.where((f >= -bw / 2.0) & (f < bw / 2.0), spec, 0.0)
    x = np.fft.ifft(np.fft.ifftshift(spec))
    return x / np.sqrt(np.mean(np.abs(x) ** 2))


def _occupied_bw_99(x: np.ndarray, fs: float) -> float:
    """99% 占用带宽：累积功率 0.5%–99.5% 两侧频率之差（FCC 式定义）。"""
    psd, f = _psd_shifted(x, fs)
    csum = np.cumsum(psd)
    total = csum[-1]
    lo = int(np.searchsorted(csum, 0.005 * total))
    hi = int(np.searchsorted(csum, 0.995 * total))
    return float(f[hi] - f[lo])


# ---------- 行为：谱形状 ----------


def test_fraction_one_degenerates_to_full_band_reference_shape():
    """fraction=1+offset=0 → 全带退化：与独立带限噪声实现的功率谱形状近等。"""
    n, fs, bw = 8192, 8192.0, 4096.0
    iq, meta = gen_partial_band(1.0, bw, n, fs=fs, rms_amplitude=1.0, seed=11)
    ref = _reference_bandlimited(bw, n, fs, seed=977)

    assert meta["occupied_bw_hz"] == pytest.approx(bw)
    assert meta["center_offset_hz"] == 0.0

    psd_g, f = _psd_shifted(iq, fs)
    psd_r, _ = _psd_shifted(ref, fs)
    in_band = (f >= -bw / 2.0) & (f < bw / 2.0)
    assert int(in_band.sum()) == 4096  # df=1 Hz → 带内恰 4096 bin

    # 带外抑制：两实现均近乎零（≤ 带内均值 × 1e-6）
    assert psd_g[~in_band].max() <= 1e-6 * psd_g[in_band].mean()
    assert psd_r[~in_band].max() <= 1e-6 * psd_r[in_band].mean()

    # 带内形状对照：4 块块均值互差 ≤25%，且落解析电平 n²·rms²/K 的 [0.5, 2] 倍
    level = n * n / int(in_band.sum())
    for blk in np.array_split(np.flatnonzero(in_band), 4):
        g, r = psd_g[blk].mean(), psd_r[blk].mean()
        assert abs(g - r) <= 0.25 * 0.5 * (g + r)
        assert 0.5 * level <= g <= 2.0 * level
        assert 0.5 * level <= r <= 2.0 * level


def test_fraction_quarter_power_in_quarter_band():
    """fraction=0.25 → 功率集中在 1/4 带内：99% 功率带宽 ≈ victim_bw×fraction（±20%）。"""
    n, fs, bw = 8192, 8192.0, 4096.0
    iq, meta = gen_partial_band(0.25, bw, n, fs=fs, seed=7)
    occ = bw * 0.25
    assert meta["occupied_bw_hz"] == pytest.approx(occ)
    obw = _occupied_bw_99(iq, fs)
    assert abs(obw - occ) / occ <= 0.20


@pytest.mark.parametrize("offset", [600.0, -600.0])
def test_offset_moves_band_center(offset):
    """偏置挪带心：功率谱峰群质心 ≈ offset，显著 bin 跨度 ≈ occupied。"""
    n, fs, bw, frac = 8192, 8192.0, 4096.0, 0.25
    iq, _ = gen_partial_band(frac, bw, n, center_offset_hz=offset, fs=fs, seed=21)
    psd, f = _psd_shifted(iq, fs)
    centroid = float(np.sum(f * psd) / np.sum(psd))
    assert abs(centroid - offset) <= 40.0  # df=1 Hz，质心涨落 σ≈9 Hz
    occupied_bins = f[psd > 1e-9 * psd.max()]
    span = occupied_bins.max() - occupied_bins.min() + fs / n
    assert abs(span - bw * frac) <= 0.20 * bw * frac


def test_offset_at_exact_boundary_allowed():
    """等式边界放行：|offset|+occ/2 == bw/2 不抛（干扰带 [0, 500) Hz 贴边）。"""
    iq, meta = gen_partial_band(0.5, 1000.0, 4096, center_offset_hz=250.0, fs=1024.0, seed=3)
    psd, f = _psd_shifted(iq, 1024.0)
    assert meta["occupied_bw_hz"] == pytest.approx(500.0)
    outside = psd[(f < -1.0) | (f > 501.0)]
    assert outside.max() <= 1e-6 * psd.mean()


def test_sub_bin_band_falls_back_to_nearest_bin():
    """occ < 1 个 bin：保底距带心最近单 bin（此处 bin 0 → 纯直流恒包络）。"""
    iq, meta = gen_partial_band(0.008, 1.0, 256, center_offset_hz=0.496, fs=256.0, seed=5)
    assert meta["occupied_bw_hz"] == pytest.approx(0.008)
    assert np.max(np.abs(np.abs(iq.astype(np.complex128)) - 1.0)) < 1e-6


def test_single_sample_rms_exact():
    """n_samples=1 → 长度 1、|x| == rms_amplitude。"""
    iq, _ = gen_partial_band(0.5, 100.0, 1, fs=100.0, seed=8)
    assert iq.shape == (1,)
    assert iq.dtype == np.complex64
    assert float(np.abs(iq[0])) == pytest.approx(1.0, rel=1e-6)


# ---------- 行为：确定性 / 归一化 / 元数据 ----------


def test_seed_reproducibility():
    """同 seed 逐位复现（IQ 与 meta），异 seed 不同。"""
    kwargs = {"center_offset_hz": -100.0, "fs": 1024.0}
    a, ma = gen_partial_band(0.3, 1000.0, 2048, seed=42, **kwargs)
    b, mb = gen_partial_band(0.3, 1000.0, 2048, seed=42, **kwargs)
    c, _ = gen_partial_band(0.3, 1000.0, 2048, seed=43, **kwargs)
    assert np.array_equal(a, b)
    assert ma == mb
    assert not np.array_equal(a, c)


def test_default_seed_none_runs():
    """seed=None（默认熵源）可运行且 meta 如实记录 None。"""
    iq, meta = gen_partial_band(0.5, 100.0, 128, fs=100.0)
    assert iq.shape == (128,)
    assert meta["seed"] is None


@pytest.mark.parametrize("frac", [1.0, 0.25])
@pytest.mark.parametrize("rms", [0.25, 1.0, 3.0])
def test_rms_normalization(frac, rms):
    """时域 RMS 归一：mean(|x|²) ≈ rms_amplitude²（float32 舍入量级）。"""
    iq, _ = gen_partial_band(frac, 4096.0, 8192, fs=8192.0, rms_amplitude=rms, seed=13)
    power = float(np.mean(np.abs(iq.astype(np.complex128)) ** 2))
    assert power == pytest.approx(rms * rms, rel=1e-5)


def test_meta_key_set_and_values():
    """meta 键集恰为 5 键，值如实回填。"""
    iq, meta = gen_partial_band(0.25, 4096.0, 8192, center_offset_hz=512.0, fs=8192.0, seed=9)
    assert set(meta) == {"victim_bw_hz", "occupied_bw_hz", "fraction", "center_offset_hz", "seed"}
    assert meta["victim_bw_hz"] == 4096.0
    assert meta["occupied_bw_hz"] == pytest.approx(1024.0)
    assert meta["fraction"] == 0.25
    assert meta["center_offset_hz"] == 512.0
    assert meta["seed"] == 9


def test_dtype_and_shape():
    """输出 complex64 ndarray，长度恰为 n_samples。"""
    iq, _ = gen_partial_band(0.5, 100.0, 333, fs=50.0, seed=1)
    assert isinstance(iq, np.ndarray)
    assert iq.dtype == np.complex64
    assert iq.shape == (333,)


# ---------- 域自校验 ----------


def test_fraction_one_is_valid():
    """fraction=1.0 合法（0/1.5/True 由域外用例拒，此处正向锚点）。"""
    iq, meta = gen_partial_band(1.0, 100.0, 64, fs=100.0, seed=2)
    assert meta["fraction"] == 1.0
    assert iq.shape == (64,)


@pytest.mark.parametrize(
    "bad_frac",
    [0.0, -0.25, 1.5, float("nan"), float("inf"), -float("inf"), True, False, "0.5", 1 + 2j],
)
def test_fraction_domain_rejected(bad_frac):
    """fraction (0,1] 外/bool/NaN/inf/复数/字符串 → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="fraction"):
        gen_partial_band(bad_frac, 1000.0, 128)


@pytest.mark.parametrize(
    "bad_bw", [0.0, -100.0, float("nan"), float("inf"), True, "100"]
)
def test_victim_bw_domain_rejected(bad_bw):
    """victim_bw_hz 0/负/NaN/inf/bool/字符串 → ValueError。"""
    with pytest.raises(ValueError, match="victim_bw_hz"):
        gen_partial_band(0.5, bad_bw, 128)


@pytest.mark.parametrize(
    "bad_off", [float("nan"), float("inf"), -float("inf"), True, "0"]
)
def test_offset_finite_domain_rejected(bad_off):
    """center_offset_hz NaN/inf/bool/字符串 → ValueError。"""
    with pytest.raises(ValueError, match="center_offset_hz"):
        gen_partial_band(0.5, 1000.0, 128, center_offset_hz=bad_off, fs=1000.0)


@pytest.mark.parametrize(
    "frac,offset",
    [(0.5, 251.0), (1.0, 10.0), (0.25, -376.0), (0.8, -120.0)],
)
def test_out_of_band_offset_rejected(frac, offset):
    """越出被测带（|offset|+occ/2 > bw/2，bw=1000）→ ValueError。"""
    with pytest.raises(ValueError, match="center_offset_hz"):
        gen_partial_band(frac, 1000.0, 1024, center_offset_hz=offset, fs=1024.0)


@pytest.mark.parametrize(
    "bad_n", [0, -3, True, False, 2.5, 64.0, "8", None]
)
def test_n_samples_domain_rejected(bad_n):
    """n_samples 0/负/bool/浮点/字符串/None → ValueError。"""
    with pytest.raises(ValueError, match="n_samples"):
        gen_partial_band(0.5, 1000.0, bad_n)


@pytest.mark.parametrize(
    "bad_fs", [0.0, -1.0, float("nan"), float("inf"), True]
)
def test_fs_domain_rejected(bad_fs):
    """fs 0/负/NaN/inf/bool → ValueError。"""
    with pytest.raises(ValueError, match="fs"):
        gen_partial_band(0.5, 1000.0, 128, fs=bad_fs)


@pytest.mark.parametrize(
    "bad_rms", [0.0, -1.0, float("nan"), float("inf"), True]
)
def test_rms_domain_rejected(bad_rms):
    """rms_amplitude 0/负/NaN/inf/bool → ValueError。"""
    with pytest.raises(ValueError, match="rms_amplitude"):
        gen_partial_band(0.5, 1000.0, 128, rms_amplitude=bad_rms)


@pytest.mark.parametrize(
    "nan_kw",
    [
        {"fraction": float("nan")},
        {"victim_bw_hz": float("nan")},
        {"center_offset_hz": float("nan")},
        {"fs": float("nan")},
        {"rms_amplitude": float("nan")},
    ],
)
def test_nan_any_param_rejected(nan_kw):
    """NaN 全拒：任一浮点参数为 NaN → ValueError。"""
    kwargs = {"fraction": 0.5, "victim_bw_hz": 1000.0, "n_samples": 256, "fs": 1000.0}
    kwargs.update(nan_kw)
    with pytest.raises(ValueError):
        gen_partial_band(**kwargs)
