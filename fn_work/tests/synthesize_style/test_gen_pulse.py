"""gen_pulse 对抗测试——周期脉冲串干扰 IQ（B7 叶子，上游 synthesize_style）。"""
from __future__ import annotations

import math

import numpy as np
import pytest

from src.synthesize_style.gen_pulse import gen_pulse

# 常用参数组（已数值验证与整样本 oracle 精确一致）：
#   DYAD: fs=8, repeat=1Hz（周期 8 样本），width=0.25s → 脉内 n%8∈{0,1}（二进制精确）
#   SQ:   fs=8, repeat=2Hz（周期 4 样本），width=0.25s → 50% 方波 n%4∈{0,1}
#   RF:   fs=2e6, repeat=10kHz（周期 200 样本），width=10µs → 每脉冲 20 样本


def _oracle_mask(n: int, samples_per_period: int, on_samples: int) -> np.ndarray:
    return (np.arange(n) % samples_per_period) < on_samples


def test_gating_on_nonzero_off_exact_zero():
    """门控断言：脉内非零（DC 载波下恰为 1+0j），脉间段精确 0+0j。"""
    x, meta = gen_pulse(pulse_width_s=0.25, repeat_hz=1.0, n_samples=32, fs=8.0)
    on = _oracle_mask(32, 8, 2)
    assert np.all(x[on].real == 1.0) and np.all(x[on].imag == 0.0)
    assert np.all(x[~on].real == 0.0) and np.all(x[~on].imag == 0.0)  # 精确零段


def test_strict_less_than_width_boundary_off():
    """t 恰落脉宽下边界（t == pulse_width_s）→ 断为脉间（严格 <，半开区间）。"""
    x, _ = gen_pulse(pulse_width_s=0.25, repeat_hz=1.0, n_samples=32, fs=8.0)
    assert x[2] == 0 and x[10] == 0 and x[18] == 0 and x[26] == 0
    y, _ = gen_pulse(pulse_width_s=0.00125, repeat_hz=100.0, n_samples=512, fs=1600.0)
    assert np.all(y[np.arange(512) % 16 == 2] == 0)  # t=0.00125s == width 边界


def test_measured_duty_cycle_matches_nominal_5pct():
    """占空比实测（非零样本占比）= 标称 duty，容差 5%。"""
    duty = 0.25
    x, meta = gen_pulse(pulse_width_s=0.0025, repeat_hz=100.0, n_samples=8000, fs=8000.0)
    measured = float(np.count_nonzero(x)) / x.size
    assert abs(measured - duty) <= 0.05 * duty
    assert meta["duty_cycle"] == pytest.approx(duty)


def test_fs_passthrough_time_axis_2e6():
    """fs 透传：fs=2e6、脉宽 10µs → 每脉冲恰 20 样本，首个关断样本在 n=20。"""
    x, meta = gen_pulse(pulse_width_s=10e-6, repeat_hz=10e3, n_samples=2000, fs=2e6)
    assert meta["pulse_width_s"] * 2e6 == pytest.approx(20.0, abs=1e-9)  # 脉宽样本数
    assert np.count_nonzero(x[:200]) == 20
    assert x[20] == 0 and x[19] != 0
    assert float(np.count_nonzero(x)) / x.size == pytest.approx(0.1)


def test_no_carrier_pulses_are_real_unit_amplitude():
    """with_carrier=False → 脉内恒幅 1（实数 +0j），脉间精确 0；幅度缩放生效。"""
    x, _ = gen_pulse(0.25, 1.0, 32, with_carrier=False, fs=8.0)
    on = _oracle_mask(32, 8, 2)
    assert np.all(x[on].real == 1.0) and np.all(x[on].imag == 0.0)
    assert np.all(x[~on] == 0)
    y, _ = gen_pulse(0.25, 1.0, 32, with_carrier=False, amplitude=0.5, fs=8.0)
    assert np.all(y[on].real == 0.5) and np.all(y[on].imag == 0.0)


def test_carrier_matches_global_time_reference():
    """载波相位按全局 t 计算（脉冲仅门控）：脉内样本 == amp·exp(j2πf·n/fs) 参考序列。"""
    n, fs, rep, width, fc, amp = 512, 1600.0, 100.0, 0.0013, 30.0, 1.5
    x, _ = gen_pulse(width, rep, n, carrier_hz=fc, fs=fs, amplitude=amp)
    ref = amp * np.exp(1j * (2.0 * np.pi * fc * np.arange(n) / fs))
    on = _oracle_mask(n, 16, 3)
    assert np.allclose(x[on].astype(np.complex128), ref[on], rtol=1e-5, atol=1e-6)
    assert np.all(x[~on] == 0)


def test_carrier_phase_continuous_across_pulses():
    """相位跨脉冲连续：脉冲首样本相位增量 = 2π·carrier/period（unwrap 断言）。"""
    n, fs, rep, width, fc = 512, 1600.0, 100.0, 0.0013, 30.0
    x, _ = gen_pulse(width, rep, n, carrier_hz=fc, fs=fs)
    starts = np.arange(0, n, 16)  # 各脉冲首样本（t=k/rep）
    phases = np.angle(x[starts].astype(np.complex128))
    increments = np.diff(np.unwrap(phases))
    expected = 2.0 * np.pi * fc / rep  # 相邻脉冲起点相位差 = 载频×周期×2π
    assert np.allclose(increments, expected, atol=1e-4)
    # 脉内相邻样本相位步进 = 2π·carrier/fs
    ratios = x[starts[:-1] + 1].astype(np.complex128) / x[starts[:-1]].astype(np.complex128)
    assert np.allclose(ratios, np.exp(1j * (2.0 * np.pi * fc / fs)), atol=1e-4)


def test_square_wave_50pct_duty_odd_even_symmetry():
    """duty=0.5 方波：通/断块等长（奇偶对称），模式 [on,on,off,off] 周期重复。"""
    x, meta = gen_pulse(pulse_width_s=0.25, repeat_hz=2.0, n_samples=16, fs=8.0)
    mask = x != 0
    assert mask.tolist() == [True, True, False, False] * 4
    assert meta["duty_cycle"] == pytest.approx(0.5)
    assert np.all(np.abs(x[mask].astype(np.complex128)) == 1.0)


def test_meta_contents_and_exact_keys():
    """meta 恰含四键，值回显输入；duty_cycle = pulse_width_s×repeat_hz。"""
    x, meta = gen_pulse(0.001, 500.0, 64, carrier_hz=250e3, fs=1e6)
    assert set(meta) == {"duty_cycle", "pulse_width_s", "repeat_hz", "carrier_hz"}
    assert meta["duty_cycle"] == pytest.approx(0.5)
    assert isinstance(x, np.ndarray) and isinstance(meta, dict)
    assert meta["pulse_width_s"] == 0.001 and meta["repeat_hz"] == 500.0
    assert meta["carrier_hz"] == 250e3


def test_default_dc_carrier_equals_explicit_zero():
    """默认载波（carrier_hz=0, with_carrier=True）与显式 DC 指定逐位一致。"""
    a, _ = gen_pulse(0.25, 1.0, 32, fs=8.0)
    b, _ = gen_pulse(0.25, 1.0, 32, carrier_hz=0.0, with_carrier=True, fs=8.0)
    assert np.array_equal(a, b)
    on = _oracle_mask(32, 8, 2)
    assert np.all(a[on].real == 1.0) and np.all(a[on].imag == 0.0)


def test_first_sample_phase_anchor():
    """t=0 必在脉内且相位 0：x[0] 实部恰为 amplitude、虚部恰为 0。"""
    x, _ = gen_pulse(0.0013, 100.0, 512, carrier_hz=30.0, fs=1600.0, amplitude=2.0)
    assert x[0].real == 2.0 and float(x[0].imag) == 0.0


@pytest.mark.parametrize(
    "width,repeat",
    [(0.6, 2.0), (0.5, 2.0), (1.2, 1.0), (2.0, 3.0)],  # duty=1.2/1.0/1.2/6.0
)
def test_duty_ge_1_rejected(width, repeat):
    """duty=pulse_width×repeat ≥1（脉宽≥周期）物理不可能 → ValueError。"""
    with pytest.raises(ValueError, match="duty"):
        gen_pulse(width, repeat, 64, fs=8.0)


def test_duty_just_below_one_accepted():
    """duty 贴近 1（0.999/0.9）合法接受，实测占空比吻合。"""
    x, meta = gen_pulse(0.999, 1.0, 200, fs=200.0)
    assert meta["duty_cycle"] == pytest.approx(0.999)
    assert float(np.count_nonzero(x)) / 200 >= 0.99
    y, meta2 = gen_pulse(0.9, 1.0, 200, fs=200.0)  # 通 180 / 断 20
    assert np.count_nonzero(y) == 180
    assert np.all(y[180:] == 0)


@pytest.mark.parametrize(
    "bad_width",
    [0.0, -1e-3, float("nan"), float("inf"), -float("inf"), True, False, "0.1", None, 0.25 + 0j],
)
def test_pulse_width_domain_rejected(bad_width):
    """pulse_width_s 0/负/NaN/inf/bool/字符串/None/复数 → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="pulse_width_s"):
        gen_pulse(bad_width, 1.0, 16, fs=8.0)


@pytest.mark.parametrize("bad_repeat", [0.0, -5.0, float("nan"), float("inf"), True, "10"])
def test_repeat_hz_domain_rejected(bad_repeat):
    """repeat_hz 0/负/NaN/inf/bool/字符串 → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="repeat_hz"):
        gen_pulse(0.25, bad_repeat, 16, fs=8.0)


@pytest.mark.parametrize(
    "bad_carrier", [float("nan"), float("inf"), -float("inf"), True, "x", 1 + 2j]
)
def test_carrier_hz_domain_rejected(bad_carrier):
    """carrier_hz NaN/inf/bool/字符串/复数 → ValueError（含参数名）；负频合法。"""
    with pytest.raises(ValueError, match="carrier_hz"):
        gen_pulse(0.25, 1.0, 16, carrier_hz=bad_carrier, fs=8.0)
    x, _ = gen_pulse(0.25, 1.0, 16, carrier_hz=-100.0, fs=8.0)  # 负载频为合法频偏
    assert x.shape == (16,)


@pytest.mark.parametrize("bad_flag", [1, 0, 1.0, "true", None])
def test_with_carrier_must_be_bool(bad_flag):
    """with_carrier 非 bool 型（int/float/str/None）→ ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="with_carrier"):
        gen_pulse(0.25, 1.0, 16, with_carrier=bad_flag, fs=8.0)


@pytest.mark.parametrize("bad_n", [0, -3, True, False, 2.5, 8.0, "9", None])
def test_n_samples_domain_rejected(bad_n):
    """n_samples 0/负/bool/浮点/字符串/None → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="n_samples"):
        gen_pulse(0.25, 1.0, bad_n, fs=8.0)


@pytest.mark.parametrize(
    "bad_fs", [0.0, -100.0, float("nan"), float("inf"), True, False]
)
def test_fs_domain_rejected(bad_fs):
    """fs 0/负/NaN/inf/bool → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="fs"):
        gen_pulse(0.25, 1.0, 16, fs=bad_fs)


@pytest.mark.parametrize("bad_amp", [0.0, -1.0, float("nan"), float("inf"), True])
def test_amplitude_domain_rejected(bad_amp):
    """amplitude 0/负/NaN/inf/bool → ValueError（含参数名）。"""
    with pytest.raises(ValueError, match="amplitude"):
        gen_pulse(0.25, 1.0, 16, fs=8.0, amplitude=bad_amp)


def test_dtype_and_length_unaligned_n():
    """输出 complex64、长度恰 n_samples；非整周期截断处门控仍逐样本正确。"""
    n = 37  # 4 个整周期 + 半周期截断
    x, _ = gen_pulse(0.25, 1.0, n, fs=8.0)
    assert isinstance(x, np.ndarray) and x.dtype == np.complex64 and x.shape == (37,)
    assert np.array_equal(x != 0, _oracle_mask(n, 8, 2))


def test_carrier_at_zero_hz_with_carrier_true_is_dc():
    """carrier_hz=0 且 with_carrier=True → 载波退化为 DC：脉内恰为 amplitude。"""
    x, _ = gen_pulse(0.25, 1.0, 32, carrier_hz=0.0, amplitude=3.0, fs=8.0)
    on = _oracle_mask(32, 8, 2)
    assert np.all(x[on].real == 3.0) and np.all(x[on].imag == 0.0)
