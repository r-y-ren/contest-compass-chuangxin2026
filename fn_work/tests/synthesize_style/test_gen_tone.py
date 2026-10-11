"""gen_tone 对抗测试——单音 CW 复指数 IQ（B7 叶子，上游 synthesize_style）。"""
from __future__ import annotations

import numpy as np
import pytest

from src.synthesize_style.gen_tone import gen_tone


def test_zero_freq_is_pure_dc():
    """零频 → 全部样本恰为 amplitude 的纯实数。"""
    x = gen_tone(0.0, 64, amplitude=2.5, fs=100.0)
    assert x.dtype == np.complex64
    assert np.all(x.real == 2.5)  # 2.5 在 float32 下精确可表示
    assert np.all(x.imag == 0.0)


@pytest.mark.parametrize("f0", [100.0, 100.3])
def test_fft_peak_at_nearest_bin_pm1(f0):
    """单频 → FFT 峰落在最近 bin ±1（含非整 bin 泄漏情形）。"""
    n, fs = 1024, 1024.0
    x = gen_tone(f0, n, fs=fs)
    spec = np.abs(np.fft.fft(x.astype(np.complex128)))
    peak_bin = int(np.argmax(spec))
    assert abs(peak_bin - round(f0 * n / fs)) <= 1


def test_fft_on_bin_peak_magnitude():
    """整 bin 频点 → 峰值幅度 ≈ n_samples*amplitude（幅度标定）。"""
    n, fs, f0, amp = 1024, 1024.0, 100.0, 0.5
    x = gen_tone(f0, n, amplitude=amp, fs=fs)
    spec = np.abs(np.fft.fft(x.astype(np.complex128)))
    assert abs(spec.max() - n * amp) / (n * amp) < 1e-5


def test_constant_envelope():
    """恒包络：正交频点（0/π/2/π/3π/2）下 |x|==amplitude 容差 1e-9。"""
    x = gen_tone(250.0, 64, amplitude=2.5, fs=1000.0)
    assert np.max(np.abs(np.abs(x.astype(np.complex128)) - 2.5)) <= 1e-9
    # 一般频点：float32 舍入量级内恒包络
    y = gen_tone(123.4, 512, amplitude=0.75, fs=1000.0)
    assert np.max(np.abs(np.abs(y.astype(np.complex128)) - 0.75)) < 1e-6


def test_phase_starts_at_zero():
    """相位起点：x[0] ≈ amplitude 且虚部为 0。"""
    x = gen_tone(97.5, 32, amplitude=3.0, fs=400.0)
    assert x[0].real == pytest.approx(3.0, abs=1e-9)
    assert abs(float(x[0].imag)) <= 1e-9


def test_single_sample():
    """n_samples=1 → 长度 1、相位 0 落点。"""
    x = gen_tone(50.0, 1, amplitude=2.0, fs=200.0)
    assert isinstance(x, np.ndarray)
    assert x.shape == (1,)
    assert x.dtype == np.complex64
    assert x[0].real == pytest.approx(2.0, abs=1e-9)
    assert float(x[0].imag) == 0.0


def test_negative_freq_conjugate_symmetry():
    """负频 → 与正频共轭对称：实部相等、虚部相反。"""
    n, fs, f0 = 256, 1024.0, 100.0
    xp = gen_tone(f0, n, fs=fs)
    xn = gen_tone(-f0, n, fs=fs)
    assert np.array_equal(xn.real, xp.real)
    assert np.array_equal(xn.imag, -xp.imag)
    assert np.array_equal(xn, np.conj(xp))


@pytest.mark.parametrize(
    "bad_freq",
    [float("nan"), float("inf"), -float("inf"), True, False, 1 + 2j, "50"],
)
def test_freq_domain_rejected(bad_freq):
    """freq NaN/inf/bool/复数/字符串 → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="freq_offset_hz"):
        gen_tone(bad_freq, 16)


@pytest.mark.parametrize("bad_amp", [0.0, -1.0, float("nan"), float("inf"), True])
def test_amplitude_domain_rejected(bad_amp):
    """amplitude 0/-1/NaN/inf/bool → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="amplitude"):
        gen_tone(10.0, 16, amplitude=bad_amp)


@pytest.mark.parametrize(
    "bad_fs", [0.0, -100.0, float("nan"), float("inf"), True, False]
)
def test_fs_domain_rejected(bad_fs):
    """fs 0/负/NaN/inf/bool → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="fs"):
        gen_tone(10.0, 16, fs=bad_fs)


@pytest.mark.parametrize(
    "bad_n", [0, -1, True, False, 1.5, 16.0, "8", None]
)
def test_n_samples_domain_rejected(bad_n):
    """n_samples 0/负/bool/浮点/字符串/None → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="n_samples"):
        gen_tone(10.0, bad_n)


def test_output_dtype_and_length():
    """输出为 complex64 ndarray，长度恰为 n_samples。"""
    x = gen_tone(10.0, 37, amplitude=1.0, fs=100.0)
    assert isinstance(x, np.ndarray)
    assert x.dtype == np.complex64
    assert x.shape == (37,)


def test_default_normalized_fs_matches_explicit():
    """规格化默认 fs=1.0 与显式 fs=1.0 一致。"""
    assert np.array_equal(gen_tone(0.25, 8), gen_tone(0.25, 8, fs=1.0))
