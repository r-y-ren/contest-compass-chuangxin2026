"""gen_chirp 行为用例：B7 叶子（对抗用例，fn-implement 阶段填充）。

公共参数 FS=2000/PERIOD=1s/CENTER=200/BW=100：低边沿 150 Hz、高边沿 250 Hz，
最高瞬时频率 250 Hz 对应每样本相位 2π·250/2000 ≈ 0.785 rad < π，保证 unwrap 可靠
恢复真实相位轨迹。三角"中点频率≈center"指半程斜坡中点（u=T/4 与 u=3T/4）：
按规约（前半升后半降扫满带宽）周期中点 u=T/2 是频率峰值 center+bw/2，两断言均验证。
"""
import numpy as np
import pytest

from src.synthesize_style.gen_chirp import gen_chirp

FS = 2000.0
PERIOD = 1.0
CENTER = 200.0
BW = 100.0
LOW = CENTER - BW / 2.0
HIGH = CENTER + BW / 2.0


def test_sawtooth_start_segment_fft_peak_near_low_edge():
    # 前 1/4 周期段瞬时频率 150→175 Hz，chirp 谱峰应落在起始频率（低边沿）附近
    x = gen_chirp(CENTER, BW, PERIOD, 2000, fs=FS, shape="sawtooth")
    seg = x[:500]
    spec = np.abs(np.fft.fftshift(np.fft.fft(seg)))
    freqs = np.fft.fftshift(np.fft.fftfreq(seg.size, d=1.0 / FS))
    peak = freqs[int(np.argmax(spec))]
    assert abs(peak - LOW) <= 0.4 * BW


def test_sawtooth_end_segment_fft_peak_near_high_edge():
    # 末 1/4 周期段（非周期边界，无瞬回混入）瞬时频率 225→250 Hz，峰在高边沿附近
    x = gen_chirp(CENTER, BW, PERIOD, 2000, fs=FS, shape="sawtooth")
    seg = x[1500:2000]
    spec = np.abs(np.fft.fftshift(np.fft.fft(seg)))
    freqs = np.fft.fftshift(np.fft.fftfreq(seg.size, d=1.0 / FS))
    peak = freqs[int(np.argmax(spec))]
    assert abs(peak - HIGH) <= 0.4 * BW


def test_triangle_ramp_midpoint_frequency_near_center():
    # 三角：差分相位估计瞬时频率。半程斜坡中点（u=T/4、3T/4）应为 center（容差 5% 带宽），
    # 周期中点 u=T/2 为峰值 center+bw/2（区分锯齿：锯齿在 T/2 才过 center）。
    x = gen_chirp(CENTER, BW, PERIOD, 2000, fs=FS, shape="triangle")
    phase = np.unwrap(np.angle(x))
    f_est = lambda idx: (phase[idx + 1] - phase[idx - 1]) * FS / (4.0 * np.pi)
    assert abs(f_est(500) - CENTER) <= 0.05 * BW  # u = T/4，升程中点
    assert abs(f_est(1500) - CENTER) <= 0.05 * BW  # u = 3T/4，降程中点
    assert abs(f_est(1000) - HIGH) <= 0.05 * BW  # u = T/2，三角频率峰值


@pytest.mark.parametrize("shape", ["sawtooth", "triangle"])
def test_phase_continuous_across_period_wrap(shape):
    # 跨周期相位连续：unwrap 后全程无 >π 跳变（周期边界仅频率瞬跳，相位积分不断裂）
    x = gen_chirp(CENTER, BW, PERIOD, 8000, fs=FS, shape=shape)  # 8 个整周期
    phase = np.unwrap(np.angle(x))
    assert np.max(np.abs(np.diff(phase))) < np.pi


def test_two_cycle_sample_repetition():
    # 两周期轨迹重复：参数取整周期样本数与整数 center·period 周数
    # （fs=4、period=16s → 64 样本/周期；center=0.75 → 每周期 12 整周相位），
    # 周期 1 与周期 2 同相位点样本等值，且瞬时频率轨迹（相位差分）逐点重复。
    x = gen_chirp(0.75, 0.5, 16.0, 128, fs=4.0, shape="sawtooth")
    assert np.allclose(x[:64], x[64:128], rtol=1e-6, atol=1e-6)
    phase = np.unwrap(np.angle(x))
    inst = np.diff(phase)
    assert np.allclose(inst[:63], inst[64:127], atol=1e-5)


def test_bandwidth_zero_rejected():
    with pytest.raises(ValueError, match="bandwidth_hz"):
        gen_chirp(CENTER, 0.0, PERIOD, 100, fs=FS)


def test_invalid_shape_rejected():
    with pytest.raises(ValueError, match="shape"):
        gen_chirp(CENTER, BW, PERIOD, 100, fs=FS, shape="square")


@pytest.mark.parametrize(
    "kwargs,name",
    [
        (dict(center_hz=float("nan")), "center_hz"),
        (dict(bandwidth_hz=float("nan")), "bandwidth_hz"),
        (dict(period_s=float("nan")), "period_s"),
        (dict(fs=float("nan")), "fs"),
        (dict(amplitude=float("nan")), "amplitude"),
        (dict(center_hz=float("inf")), "center_hz"),
        (dict(bandwidth_hz=float("-inf")), "bandwidth_hz"),
        (dict(center_hz=True), "center_hz"),
        (dict(bandwidth_hz=False), "bandwidth_hz"),
        (dict(period_s="1.0"), "period_s"),
        (dict(fs=None), "fs"),
    ],
)
def test_nan_inf_bool_nonnumeric_params_rejected(kwargs, name):
    base = dict(center_hz=CENTER, bandwidth_hz=BW, period_s=PERIOD, n_samples=100, fs=FS)
    with pytest.raises(ValueError, match=name):
        gen_chirp(**{**base, **kwargs})


@pytest.mark.parametrize("shape", ["sawtooth", "triangle"])
def test_constant_envelope(shape):
    x = gen_chirp(CENTER, BW, PERIOD, 2000, fs=FS, shape=shape, amplitude=0.7)
    assert np.allclose(np.abs(x), 0.7, rtol=1e-5, atol=1e-6)


def test_non_integer_period_truncates_to_exact_length():
    # 周期 12.3s @ fs=10 → 123 样本/周期；n=377 = 3 周期 + 8 样本，不整周期截断
    x = gen_chirp(10.0, 4.0, 12.3, 377, fs=10.0)
    assert isinstance(x, np.ndarray)
    assert x.shape == (377,)


def test_dtype_complex64():
    x = gen_chirp(CENTER, BW, PERIOD, 1000, fs=FS)
    assert x.dtype == np.complex64


@pytest.mark.parametrize(
    "kwargs,name",
    [
        (dict(bandwidth_hz=-3.0), "bandwidth_hz"),
        (dict(period_s=0.0), "period_s"),
        (dict(period_s=-1.0), "period_s"),
        (dict(fs=0.0), "fs"),
        (dict(amplitude=0.0), "amplitude"),
        (dict(amplitude=-2.0), "amplitude"),
        (dict(n_samples=0), "n_samples"),
        (dict(n_samples=-5), "n_samples"),
        (dict(n_samples=100.0), "n_samples"),
        (dict(n_samples=True), "n_samples"),
    ],
)
def test_nonpositive_or_mistyped_params_rejected(kwargs, name):
    base = dict(center_hz=CENTER, bandwidth_hz=BW, period_s=PERIOD, n_samples=100, fs=FS)
    with pytest.raises(ValueError, match=name):
        gen_chirp(**{**base, **kwargs})
