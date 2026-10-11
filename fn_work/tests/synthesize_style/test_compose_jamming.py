"""compose_jamming 对抗测试——J(t) 多源合成（B7 叶子，上游 synthesize_style）。"""
from __future__ import annotations

import numpy as np
import pytest

from src.synthesize_style.compose_jamming import compose_jamming
from src.synthesize_style.gen_tone import gen_tone


def _comp(iq, **kw):
    """分量 dict 快捷构造：默认恒包络 1.0、零频偏、零相位。"""
    return {"iq": iq, **kw}


# ---------- 直通与标量调制 ----------


def test_single_component_passthrough_exact():
    """单分量恒包络/零频偏/零相位 → 输出逐样本等于原 iq（无幅相扰动）。"""
    rng = np.random.default_rng(7)
    iq = (rng.standard_normal(128) + 1j * rng.standard_normal(128)).astype(np.complex64)
    out, meta = compose_jamming([_comp(iq)])
    assert out.dtype == np.complex64
    assert np.array_equal(out, iq)  # exp(j0)=1 精确直通
    assert meta["n_components"] == 1
    assert meta["length"] == 128
    assert meta["power_share"] == [1.0]


def test_amplitude_key_scales_constant_envelope():
    """envelope='constant' + amplitude 数值 → 恒定缩放（A_k 标量路径）。"""
    iq = np.ones(64, dtype=np.complex64)
    out, meta = compose_jamming([_comp(iq, envelope="constant", amplitude=2.5)])
    assert np.all(out.real == 2.5)  # 2.5 在 float32 下精确可表示
    assert np.all(out.imag == 0.0)
    assert meta["power_share"] == [1.0]


def test_phase_pi_flips_sign():
    """phase_rad=π → 输出 ≈ −iq（exp(jπ)=−1，仅 float 舍入级偏差）。"""
    iq = gen_tone(37.0, 256, amplitude=1.0, fs=512.0)
    out, _ = compose_jamming([_comp(iq, phase_rad=np.pi)])
    ref = -(iq.astype(np.complex128))
    assert np.max(np.abs(out.astype(np.complex128) - ref)) <= 1e-6


# ---------- 公式(1) 对抗断言 ----------


def test_two_equal_tones_beat_period_2delta():
    """两等幅单音 offset=±Δ → J(t)=2cos(2πΔt)：|J| 呈 1/(2Δ) 拍频周期、谱呈双峰。"""
    n, fs, delta = 400, 2000.0, 50.0
    comps = [
        _comp(np.ones(n), freq_offset_hz=delta),
        _comp(np.ones(n), freq_offset_hz=-delta),
    ]
    out, meta = compose_jamming(comps, fs=fs)
    out_c = out.astype(np.complex128)
    t = np.arange(n) / fs
    # 时域公式断言：实部=2cos(2πΔt)、虚部≈0
    assert np.max(np.abs(out_c.real - 2.0 * np.cos(2.0 * np.pi * delta * t))) <= 1e-3
    assert np.max(np.abs(out_c.imag)) <= 1e-5
    # 包络拍频：|J| 峰间隔 = fs/(2Δ) = 20 样本（±1）
    mag = np.abs(out_c)
    peaks = [k for k in range(1, n - 1) if mag[k] >= mag[k - 1] and mag[k] > mag[k + 1]]
    assert len(peaks) >= 18
    assert np.all(np.abs(np.diff(peaks) - fs / (2.0 * delta)) <= 1.0)
    assert abs(mag.max() - 2.0) <= 1e-4 and mag.min() <= 1e-4  # 峰谷达满幅/零
    # 功率谱双峰：±Δ 各落 bin ±Δ·n/fs = ±10
    spec = np.abs(np.fft.fft(out_c))
    top2 = np.argsort(spec)[-2:]
    assert set(int(b) for b in top2) == {10, 400 - 10}
    assert meta["power_share"] == pytest.approx([0.5, 0.5], rel=0.01)


def test_envelope_linear_ramp_modulates():
    """envelope 数组线性渐变 → 输出 = ramp(t)·iq（逐样本调制断言）。"""
    n, fs = 512, 1024.0
    iq = gen_tone(100.0, n, amplitude=1.0, fs=fs)
    ramp = np.linspace(0.25, 2.0, n)
    out, _ = compose_jamming([_comp(iq, envelope=ramp)], fs=fs)
    ref = ramp * iq.astype(np.complex128)
    assert np.max(np.abs(out.astype(np.complex128) - ref)) <= 1e-5


@pytest.mark.parametrize("f0", [100.0, 100.3])
def test_freq_shift_moves_fft_peak_bin(f0):
    """频偏经 exp(j2πΔf t) 实现：DC 分量 +Δ → 谱峰挪至最近 bin ±1（含非整 bin）。"""
    n, fs, delta = 1024, 1024.0, f0
    out, _ = compose_jamming([_comp(np.ones(n), freq_offset_hz=delta)], fs=fs)
    spec = np.abs(np.fft.fft(out.astype(np.complex128)))
    peak_bin = int(np.argmax(spec))
    assert abs(peak_bin - round(delta * n / fs)) <= 1


def test_single_component_matches_gen_tone():
    """单分量频移+相位 ≡ gen_tone 同参输出（与兄弟叶子交叉标定）。"""
    n, fs, f0, amp, theta = 512, 1024.0, 80.0, 0.7, 0.3
    base = np.full(n, amp)
    out, _ = compose_jamming([_comp(base, freq_offset_hz=f0, phase_rad=theta)], fs=fs)
    t = np.arange(n) / fs
    ref = amp * np.exp(1j * (2.0 * np.pi * f0 * t + theta))
    assert np.allclose(out.astype(np.complex128), ref, atol=1e-6)


# ---------- 功率占比口径 ----------


@pytest.mark.parametrize(
    ("a1", "a2", "expect"),
    [(1.0, 1.0, [0.5, 0.5]), (1.0, 2.0, [0.2, 0.8]), (3.0, 1.0, [0.9, 0.1])],
)
def test_power_share_normalized(a1, a2, expect):
    """功率占比 = 各分量功率/总功率：等幅各 0.5；1:2 → 0.2/0.8（容差 1%）。"""
    n = 256
    comps = [
        _comp(np.ones(n), envelope="constant", amplitude=a1, freq_offset_hz=30.0),
        _comp(np.ones(n), envelope="constant", amplitude=a2, freq_offset_hz=-45.0),
    ]
    _, meta = compose_jamming(comps, fs=256.0)
    assert meta["power_share"] == pytest.approx(expect, rel=0.01)
    assert sum(meta["power_share"]) == pytest.approx(1.0, abs=1e-9)


def test_phase_pi_cancellation_between_components():
    """同波形两分量相位差 π → 合成相消 ≈ 0，占比仍各 0.5（按合成前功率计）。"""
    iq = gen_tone(60.0, 300, amplitude=1.0, fs=300.0)
    out, meta = compose_jamming(
        [_comp(iq), _comp(iq, phase_rad=np.pi)], fs=300.0
    )
    assert np.max(np.abs(out.astype(np.complex128))) <= 1e-6
    assert meta["power_share"] == pytest.approx([0.5, 0.5], rel=0.01)


def test_zero_total_power_share_is_all_zeros():
    """全零分量（总功率 0）→ power_share 如实列全 0.0（占空口径），输出全零。"""
    out, meta = compose_jamming(
        [_comp(np.zeros(64)), _comp(np.zeros(64), freq_offset_hz=10.0)]
    )
    assert out.dtype == np.complex64
    assert np.array_equal(out, np.zeros(64, dtype=np.complex64))
    assert meta["power_share"] == [0.0, 0.0]
    assert meta["n_components"] == 2 and meta["length"] == 64


# ---------- 域自校验（ValueError） ----------


def test_length_mismatch_rejected_with_lengths():
    """等长校验：iq 长度不一致 → ValueError 且列出各长度。"""
    with pytest.raises(ValueError) as ei:
        compose_jamming([_comp(np.ones(64)), _comp(np.ones(128))])
    msg = str(ei.value)
    assert "64" in msg and "128" in msg


def test_envelope_length_mismatch_own_iq_rejected():
    """envelope 数组须与自身 iq 等长：31 vs 32 → ValueError 含两长度。"""
    with pytest.raises(ValueError) as ei:
        compose_jamming([_comp(np.ones(32), envelope=np.ones(31))])
    msg = str(ei.value)
    assert "31" in msg and "32" in msg


@pytest.mark.parametrize(
    "bad", [(), None, "tone", 5, {"iq": [1j]}, [np.ones(8)], [[1.0, 2.0]]]
)
def test_bad_components_container_or_element_rejected(bad):
    """components 非非空 list[dict]（元组/None/标量/非 dict 元素）→ ValueError。"""
    with pytest.raises(ValueError):
        compose_jamming(bad)


def test_empty_components_rejected():
    """空 components 列表 → ValueError。"""
    with pytest.raises(ValueError):
        compose_jamming([])


def test_missing_iq_key_rejected():
    """分量缺必填键 'iq'（仅有频偏）→ ValueError。"""
    with pytest.raises(ValueError, match="iq"):
        compose_jamming([{"freq_offset_hz": 10.0}])


@pytest.mark.parametrize(
    "override",
    [
        {"freq_offset_hz": float("nan")},
        {"freq_offset_hz": float("inf")},
        {"freq_offset_hz": True},
        {"phase_rad": float("nan")},
        {"phase_rad": float("inf")},
        {"phase_rad": False},
    ],
)
def test_nonfinite_or_bool_freq_phase_rejected(override):
    """freq_offset/phase NaN/inf/bool → ValueError（域错统一 ValueError）。"""
    with pytest.raises(ValueError):
        compose_jamming([_comp(np.ones(16), **override)])


@pytest.mark.parametrize("bad_env", [[1.0, float("nan"), 1.0], [1.0, float("inf")]])
def test_nonfinite_envelope_rejected(bad_env):
    """envelope 数组含 NaN/inf → ValueError。"""
    with pytest.raises(ValueError):
        compose_jamming([_comp(np.ones(len(bad_env)), envelope=bad_env)])


def test_bad_fs_rejected():
    """fs 非有限正数（0/负/NaN/bool）→ ValueError。"""
    for bad_fs in [0.0, -100.0, float("nan"), True]:
        with pytest.raises(ValueError):
            compose_jamming([_comp(np.ones(8))], fs=bad_fs)


# ---------- 接口契约 ----------


def test_sequence_iq_and_meta_types():
    """iq 接受 Sequence[complex]（list）；meta 字段类型/取值如实。"""
    iq = [1.0 + 0.0j, 0.0 + 1.0j, -1.0 + 0.0j, 0.0 - 1.0j]
    out, meta = compose_jamming([_comp(iq)])
    assert out.dtype == np.complex64
    assert out.shape == (4,)
    assert isinstance(meta, dict)
    assert isinstance(meta["n_components"], int) and meta["n_components"] == 1
    assert isinstance(meta["length"], int) and meta["length"] == 4
    assert isinstance(meta["power_share"], list)
    assert all(isinstance(s, float) for s in meta["power_share"])
    assert np.array_equal(out, np.asarray(iq, dtype=np.complex64))
