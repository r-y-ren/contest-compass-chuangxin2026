"""gen_sweep 对抗测试：线性扫频 IQ（相位连续、重复相位重置、域校验）。"""
from __future__ import annotations

import numpy as np
import pytest

from src.synthesize_style.gen_sweep import gen_sweep


def _peak_freq(segment: np.ndarray, fs: float) -> float:
    """段内 FFT 幅度最大谱线对应的频率。"""
    spectrum = np.abs(np.fft.fft(segment))
    frequencies = np.fft.fftfreq(len(segment), d=1.0 / fs)
    return float(frequencies[int(np.argmax(spectrum))])


def _inst_freq(iq: np.ndarray, fs: float) -> np.ndarray:
    """瞬时频率估计：unwrap 相位差分 / 2π * fs。"""
    phase = np.unwrap(np.angle(iq.astype(np.complex128)))
    return np.diff(phase) * fs / (2.0 * np.pi)


def test_f0_eq_f1_degenerates_to_single_tone():
    """f0==f1 退化为单音：与 gen_tone 公式独立计算的对照近等（不 import gen_tone）。"""
    fs, duration_s, amplitude = 480.0, 0.5, 0.63
    f = 60.0
    iq = gen_sweep(f, f, duration_s, repeats=1, fs=fs, amplitude=amplitude)
    n = int(round(duration_s * fs))
    t = np.arange(n) / fs
    reference = (amplitude * np.exp(2j * np.pi * f * t)).astype(np.complex64)
    assert iq.shape == (n,)
    np.testing.assert_allclose(iq, reference, rtol=1e-5, atol=1e-6)


def test_upsweep_fft_peak_start_near_f0_end_near_f1():
    """上扫：前 1/4 段 FFT 峰在 f0 附近 bin±2，末段在 f1 附近。"""
    fs, duration_s = 1000.0, 1.0
    f0, f1 = 100.0, 120.0
    iq = gen_sweep(f0, f1, duration_s, fs=fs)
    quarter = len(iq) // 4
    bin_width = fs / quarter
    f_start = _peak_freq(iq[:quarter], fs)
    f_end = _peak_freq(iq[-quarter:], fs)
    assert abs(f_start - f0) <= 2.0 * bin_width
    assert abs(f_end - f1) <= 2.0 * bin_width


def test_phase_unwrap_monotonic_no_2pi_jumps():
    """相位连续：unwrap 后相位增量无 2π 跳变异常，且上扫增量单调不减。"""
    fs, duration_s = 1000.0, 1.0
    iq = gen_sweep(100.0, 400.0, duration_s, fs=fs)
    phase = np.unwrap(np.angle(iq.astype(np.complex128)))
    d_phase = np.diff(phase)
    assert np.all(np.abs(d_phase) < np.pi)
    assert np.all(d_phase > 0)
    assert np.all(np.diff(d_phase) > -1e-3)


def test_repeats3_triples_length_and_each_segment_starts_at_phase_zero():
    """repeats=3：长度×3，三段首样本相位≈0（实≈amplitude、虚≈0），且三段逐样本一致。"""
    fs, duration_s, amplitude = 500.0, 0.4, 0.9
    iq = gen_sweep(50.0, 150.0, duration_s, repeats=3, fs=fs, amplitude=amplitude)
    n_per = int(round(duration_s * fs))
    assert len(iq) == 3 * n_per
    starts = iq[::n_per]
    assert len(starts) == 3
    np.testing.assert_allclose(starts.real, amplitude, rtol=1e-5, atol=1e-6)
    np.testing.assert_allclose(starts.imag, 0.0, atol=1e-6)
    for r in (1, 2):
        np.testing.assert_array_equal(iq[r * n_per : (r + 1) * n_per], iq[:n_per])


def test_downsweep_end_segment_frequency_low():
    """下扫 f0>f1：末段 FFT 峰频率低——落在末 1/4 扫频带 [f1, f1+Δ/4] 加 bin 余量内，且低于中点频率。"""
    fs, duration_s = 1000.0, 1.0
    f0, f1 = 400.0, 100.0
    iq = gen_sweep(f0, f1, duration_s, fs=fs)
    quarter = len(iq) // 4
    bin_width = fs / quarter
    f_end = _peak_freq(iq[-quarter:], fs)
    assert f1 - 2.0 * bin_width <= f_end <= f1 + 0.25 * (f0 - f1) + 2.0 * bin_width
    assert f_end < (f0 + f1) / 2.0


def test_instantaneous_frequency_midpoint_near_mean():
    """瞬时频率（差分相位/2π）中点≈(f0+f1)/2，容差 5%。"""
    fs, duration_s = 1000.0, 1.0
    f0, f1 = 100.0, 400.0
    iq = gen_sweep(f0, f1, duration_s, fs=fs)
    inst = _inst_freq(iq, fs)
    mid = inst[len(inst) // 2]
    expected = (f0 + f1) / 2.0
    assert abs(mid - expected) <= 0.05 * expected


@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"f0": float("nan")}, "f0"),
        ({"f0": float("inf")}, "f0"),
        ({"f0": True}, "f0"),
        ({"f1": float("nan")}, "f1"),
        ({"f1": float("-inf")}, "f1"),
        ({"f1": False}, "f1"),
        ({"duration_s": float("nan")}, "duration_s"),
        ({"fs": float("inf")}, "fs"),
        ({"amplitude": float("nan")}, "amplitude"),
        ({"amplitude": float("inf")}, "amplitude"),
    ],
)
def test_nonfinite_or_bool_params_rejected(kwargs, name):
    """NaN/±inf/bool 参数化拒，报错含参数名。"""
    base = {
        "f0": 100.0,
        "f1": 200.0,
        "duration_s": 0.1,
        "repeats": 1,
        "fs": 1000.0,
        "amplitude": 1.0,
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=name):
        gen_sweep(**base)


@pytest.mark.parametrize("duration_s", [0.0, -0.5, -100.0])
def test_nonpositive_duration_rejected(duration_s):
    with pytest.raises(ValueError, match="duration_s"):
        gen_sweep(100.0, 200.0, duration_s, fs=1000.0)


@pytest.mark.parametrize("repeats", [0, -3, True, 2.0])
def test_invalid_repeats_rejected(repeats):
    with pytest.raises(ValueError, match="repeats"):
        gen_sweep(100.0, 200.0, 0.1, repeats=repeats, fs=1000.0)


@pytest.mark.parametrize("fs", [0.0, -1000.0])
def test_nonpositive_fs_rejected(fs):
    with pytest.raises(ValueError, match="fs"):
        gen_sweep(100.0, 200.0, 0.1, fs=fs)


@pytest.mark.parametrize("amplitude", [0.0, -1.0])
def test_nonpositive_amplitude_rejected(amplitude):
    with pytest.raises(ValueError, match="amplitude"):
        gen_sweep(100.0, 200.0, 0.1, amplitude=amplitude, fs=1000.0)


def test_constant_envelope():
    """恒包络：全样本幅度≈amplitude（±0.1%）。"""
    amplitude = 0.37
    iq = gen_sweep(80.0, 320.0, 0.2, repeats=2, fs=2000.0, amplitude=amplitude)
    magnitudes = np.abs(iq)
    assert np.all(magnitudes >= amplitude * 0.999)
    assert np.all(magnitudes <= amplitude * 1.001)


def test_dtype_complex64_and_length_rounding():
    """输出 ndarray complex64；长度 n=round(duration_s*fs)*repeats。"""
    iq = gen_sweep(10.0, 30.0, 0.0104, repeats=2, fs=1000.0)
    assert isinstance(iq, np.ndarray)
    assert iq.dtype == np.complex64
    assert iq.ndim == 1
    assert iq.shape == (20,)  # round(0.0104*1000)=10，×2
