"""B7 对抗审查 12 项缺陷修复回归（fn-implement 补回归批次）。

每项缺陷至少一条 test_defect_b7_* 用例：
- 中#1 blnoise occupied_bw99 的 i_hi 越界（n=1/2、贴顶单 bin）；
- 中#2 gen_sweep 银行家舍入 round(0.5)=0 空输出；
- 中#3 compose_jamming._parse_iq NaN/inf 漏校验；
- 中#4 全生成器 amplitude/rms_amplitude 超 [1e-30, 1e30] 表示域；
- 中#5 gen_partial_band meta.occupied_bw_hz 报标称而非实测占位；
- 低#6 gen_partial_band seed 缺 int|None 域校验；
- 低#7 blnoise/partial_band 混叠域（|offset|+bw/2 > fs/2）漏拒；
- 低#8 blnoise 域校验顺序（物理域先于红线，报文归因）；
- 低#9 gen_pulse repeat_hz ≥ fs/2 采样欠定区漏拒；
- 低#10 gen_pulse with_carrier=False 时 meta.carrier_hz 回显误导；
- 低#11 compose_jamming |freq_offset|>fs/2 混叠无标注；
- 低#12 整型口径：gen_sweep repeats / gen_chirp n_samples / checker repeats
  拒 np.int64（bool 须仍拒）。
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from src.synthesize_style.check_style_params import check_style_params
from src.synthesize_style.compose_jamming import compose_jamming
from src.synthesize_style.gen_bandlimited_noise import gen_bandlimited_noise
from src.synthesize_style.gen_chirp import gen_chirp
from src.synthesize_style.gen_partial_band import gen_partial_band
from src.synthesize_style.gen_pulse import gen_pulse
from src.synthesize_style.gen_sweep import gen_sweep
from src.synthesize_style.gen_tone import gen_tone


def _rms(iq: np.ndarray) -> float:
    z = iq.astype(np.complex128)
    return float(np.sqrt(np.mean(np.real(z) ** 2 + np.imag(z) ** 2)))


# ---------------- 中#1：occupied_bw99 分位点越界（i_hi 钳位） ----------------


def test_defect_b7_mid1_n_samples_1_returns_truthful_zero():
    """n_samples=1 正常返回：occupied_bw99 两分位点重合 → 如实报 0（旧实现 IndexError）。"""
    iq, meta = gen_bandlimited_noise(0.2, 1, fs=1.0, seed=1)
    assert iq.shape == (1,) and iq.dtype == np.complex64
    assert meta["occupied_bw99_hz"] == 0.0  # 单 bin 无频宽可言，如实 0
    assert meta["measured_bw_hz"] == pytest.approx(1.0)  # 单 bin 宽 df=fs/n
    assert math.isfinite(meta["flatness_db"])


def test_defect_b7_mid1_n_samples_2_dc_bin_is_top_truthful_zero():
    """n_samples=2、占位 DC bin（fftfreq(2)=[0,-0.5]，DC 即升序顶）：正常返回且如实报 0。

    旧实现 i_hi=max(1, 1+1)=2 → IndexError；新钳位后分位点重合，如实 0。
    """
    iq, meta = gen_bandlimited_noise(0.2, 2, fs=1.0, seed=1)
    assert iq.shape == (2,) and iq.dtype == np.complex64
    assert meta["occupied_bw99_hz"] == 0.0
    assert _rms(iq) == pytest.approx(1.0, rel=0.01)


def test_defect_b7_mid1_n_samples_2_low_bin_reports_df():
    """n_samples=2、占位低频 bin（升序首位）→ occupied 至少跨一个 df（=0.5）。"""
    # 混叠等式边界：|−0.4|+0.2/2 = 0.5 == fs/2 放行；占位 bin 为 -0.5（升序首位）。
    iq, meta = gen_bandlimited_noise(0.2, 2, fs=1.0, center_offset_hz=-0.4, seed=1)
    assert iq.shape == (2,)
    assert meta["occupied_bw99_hz"] == pytest.approx(0.5)  # df = fs/n
    assert _rms(iq) == pytest.approx(1.0, rel=0.01)


def test_defect_b7_mid1_top_bin_single_occupancy_no_indexerror():
    """贴顶单 bin（保底 bin 落在频轴最顶 = 升序末位）：i_lo=i_hi=n-1 → 如实报 0 不越界。"""
    n, fs = 64, 1.0
    # center=0.49 的最近 bin 是 31/64（升序频轴最后一个元素）；bw<df 触发保底单 bin
    iq, meta = gen_bandlimited_noise(1e-4, n, fs=fs, center_offset_hz=0.49, seed=4)
    assert iq.shape == (n,)  # 旧实现 i_hi=max(63,64)=64 → IndexError
    assert meta["occupied_bw99_hz"] == 0.0  # 功率全在末位 bin，分位点重合，如实 0
    assert _rms(iq) == pytest.approx(1.0, rel=0.01)


# ---------------- 中#2：gen_sweep 长度 max(1, round(duration*fs)) ----------------


@pytest.mark.parametrize("duration_s", [0.0005, 1e-6])
def test_defect_b7_mid2_tiny_duration_yields_at_least_one_sample(duration_s):
    """duration*fs < 0.5（含银行家舍入 round(0.5)=0 情形）→ 仍至少 1 样本/次。"""
    iq = gen_sweep(100.0, 200.0, duration_s, fs=1000.0)
    assert isinstance(iq, np.ndarray) and iq.dtype == np.complex64
    assert len(iq) == 1
    assert iq[0].real == pytest.approx(1.0, abs=1e-6)
    assert float(iq[0].imag) == pytest.approx(0.0, abs=1e-6)


def test_defect_b7_mid2_tiny_duration_with_repeats():
    """duration>0 + repeats=3 → 至少 3 样本（每次重复至少 1 样本，无空拼接）。"""
    iq = gen_sweep(10.0, 30.0, 0.0005, repeats=3, fs=1000.0)
    assert len(iq) == 3
    assert np.array_equal(iq, iq[0:1].repeat(3))  # 单样本 one_shot 平铺


# ---------------- 中#3：compose_jamming iq NaN/inf 校验 ----------------


@pytest.mark.parametrize(
    "bad_iq",
    [[1.0, float("nan")], [1.0, float("inf")], [float("-inf"), 1.0], [1.0, complex(float("nan"), 1.0)]],
)
def test_defect_b7_mid3_nonfinite_iq_rejected_with_component_index(bad_iq):
    """分量 iq 含 NaN/inf（实部/虚部任一）→ ValueError 且报文含分量序号。"""
    with pytest.raises(ValueError, match=r"components\[0\].*iq"):
        compose_jamming([{"iq": bad_iq}])


def test_defect_b7_mid3_nonfinite_iq_second_component_indexed():
    """第 2 分量（idx=1）iq 含 inf → 报文归因到 components[1]。"""
    with pytest.raises(ValueError, match=r"components\[1\].*iq"):
        compose_jamming([{"iq": np.ones(8)}, {"iq": [1.0, float("inf")]}])


def test_defect_b7_mid3_power_share_no_nan_masking():
    """NaN 已在域校验拦截 → power_share 永不出现 NaN 掩饰路径（零功率仍如实 0.0）。"""
    _, meta = compose_jamming([{"iq": np.zeros(16)}, {"iq": np.zeros(16)}])
    assert meta["power_share"] == [0.0, 0.0]


# ---------------- 中#4：amplitude/rms_amplitude ∈ [1e-30, 1e30] ----------------

# (构造 callable, 幅度参数名)——覆盖 6 生成器 + compose 的 amplitude 键。
_AMPLITUDE_CASES = [
    (lambda a: gen_tone(10.0, 8, amplitude=a, fs=100.0), "amplitude"),
    (lambda a: gen_sweep(10.0, 20.0, 0.1, amplitude=a, fs=1000.0), "amplitude"),
    (lambda a: gen_chirp(200.0, 100.0, 1.0, 64, fs=2000.0, amplitude=a), "amplitude"),
    (lambda a: gen_pulse(0.25, 1.0, 16, fs=8.0, amplitude=a), "amplitude"),
    (lambda a: gen_bandlimited_noise(0.2, 64, fs=1.0, rms_amplitude=a, seed=1), "rms_amplitude"),
    (lambda a: gen_partial_band(0.5, 100.0, 64, fs=100.0, rms_amplitude=a, seed=1), "rms_amplitude"),
    (
        lambda a: compose_jamming([{"iq": np.ones(8), "envelope": "constant", "amplitude": a}]),
        "amplitude",
    ),
]


@pytest.mark.parametrize("call,name", _AMPLITUDE_CASES)
@pytest.mark.parametrize("bad", [1e31, 1e300, 1e-31, 1e-300])
def test_defect_b7_mid4_amplitude_out_of_representable_range_rejected(call, name, bad):
    """|amplitude|>1e30 或 <1e-30 → ValueError（含参数名与 complex64 表示域说明）。"""
    with pytest.raises(ValueError, match=name) as ei:
        call(bad)
    assert "1e30" in str(ei.value)  # dtype 表示域说明（complex64/float32 上下界）


@pytest.mark.parametrize("call", [c for c, _ in _AMPLITUDE_CASES])
@pytest.mark.parametrize("edge", [1e30, 1e-30])
def test_defect_b7_mid4_amplitude_boundaries_pass(call, edge):
    """边界值 1e30 / 1e-30 恰合法（闭域 [1e-30, 1e30]）。"""
    result = call(edge)
    out = result[0] if isinstance(result, tuple) else result
    assert np.all(np.isfinite(out.view(np.float32)))


# ---------------- 中#5：gen_partial_band occupied_bw_hz 实测占位 ----------------


def test_defect_b7_mid5_fallback_reports_bin_width_and_flag():
    """保底单 bin：occupied 如实报 bin 宽 fs/n 并加 'fallback_bin': True。"""
    n, fs = 256, 256.0
    iq, meta = gen_partial_band(0.008, 1.0, n, center_offset_hz=0.496, fs=fs, seed=5)
    assert meta["occupied_bw_hz"] == pytest.approx(fs / n)  # 实测单 bin 宽，非标称 0.008
    assert meta["fallback_bin"] is True
    assert iq.dtype == np.complex64 and iq.shape == (n,)


def test_defect_b7_mid5_normal_path_reports_actual_occupied():
    """正常路径：occupied = 实际保留 bin 数 × fs/n，与标称 occ 差至多一个 df。"""
    n, fs, bw, frac = 8192, 8192.0, 4096.0, 0.25
    iq, meta = gen_partial_band(frac, bw, n, fs=fs, seed=7)
    df = fs / n
    freqs = np.fft.fftfreq(n, d=1.0 / fs)
    occ_nominal = bw * frac
    n_bins = int(((freqs >= -occ_nominal / 2) & (freqs < occ_nominal / 2)).sum())
    assert meta["occupied_bw_hz"] == pytest.approx(n_bins * df)  # 与实际 bin 数一致
    assert abs(meta["occupied_bw_hz"] - occ_nominal) <= df  # 与标称至多差一个 bin
    assert "fallback_bin" not in meta  # 正常路径不加保底标注


def test_defect_b7_mid5_single_sample_occupied_is_bin_width():
    """n_samples=1：单 bin 占位 = fs/n = fs（bin 量化口径如实）。"""
    _, meta = gen_partial_band(0.5, 100.0, 1, fs=100.0, seed=8)
    assert meta["occupied_bw_hz"] == pytest.approx(100.0)


# ---------------- 低#6：gen_partial_band seed 域校验 ----------------


@pytest.mark.parametrize("bad_seed", [True, False, 1.5, 42.0, "7", 3 + 4j])
def test_defect_b7_low6_seed_domain_rejected(bad_seed):
    """seed bool/浮点/字符串/复数 → ValueError（含参数名，与 blnoise 同口径）。"""
    with pytest.raises(ValueError, match="seed"):
        gen_partial_band(0.5, 100.0, 64, fs=100.0, seed=bad_seed)


def test_defect_b7_low6_seed_integral_accepted_and_normalized():
    """seed=np.int64(42) 过（Integral 口径），meta 回显规范化 int 且同 seed 复现。"""
    a, ma = gen_partial_band(0.5, 100.0, 128, fs=100.0, seed=np.int64(42))
    b, mb = gen_partial_band(0.5, 100.0, 128, fs=100.0, seed=42)
    assert np.array_equal(a, b)
    assert ma["seed"] == mb["seed"] == 42 and isinstance(ma["seed"], int)


# ---------------- 低#7：混叠域（|center_offset| + bw/2 > fs/2）拒 ----------------


def test_defect_b7_low7_blnoise_aliasing_rejected_with_both_values():
    """blnoise：|0.4| + 0.4/2 = 0.6 > fs/2=0.5 → ValueError（含两值）。"""
    with pytest.raises(ValueError, match="center_offset_hz") as ei:
        gen_bandlimited_noise(0.4, 64, fs=1.0, center_offset_hz=0.4, seed=1)
    msg = str(ei.value)
    assert "0.4" in msg and "fs/2" in msg  # |center| 与 bw/2（或 fs/2）两值归因


def test_defect_b7_low7_blnoise_aliasing_boundary_passes():
    """等式边界：|0.3| + 0.4/2 = 0.5 == fs/2 → 放行（贴 Nyquist 不拒）。"""
    iq, _ = gen_bandlimited_noise(0.4, 64, fs=1.0, center_offset_hz=0.3, seed=1)
    assert iq.shape == (64,)


def test_defect_b7_low7_partial_band_aliasing_rejected():
    """partial_band：被测带内合法但越采样域（occ=1.0, |0.2|+0.5>fs/2=0.5）→ ValueError。"""
    with pytest.raises(ValueError, match="center_offset_hz") as ei:
        gen_partial_band(0.5, 2.0, 256, center_offset_hz=0.2, fs=1.0, seed=1)
    msg = str(ei.value)
    assert "0.2" in msg and "fs/2" in msg


def test_defect_b7_low7_partial_band_boundary_and_negative_offset():
    """等式边界放行；负偏置越界同样拒（|offset| 对称）。"""
    iq, _ = gen_partial_band(0.5, 1.0, 128, center_offset_hz=0.0, fs=1.0, seed=2)
    assert iq.shape == (128,)  # |0|+0.25 ≤ 0.5 过
    with pytest.raises(ValueError, match="center_offset_hz"):
        gen_partial_band(0.5, 2.0, 128, center_offset_hz=-0.2, fs=1.0, seed=3)


# ---------------- 低#8：blnoise 物理域先于红线（报文归因） ----------------


def test_defect_b7_low8_physical_domain_reported_before_redline():
    """fs=1（默认）下 57e6 值先撞 fs/2 物理域报文（非红线）——归因如实。"""
    with pytest.raises(ValueError, match="bandwidth_hz") as ei:
        gen_bandlimited_noise(57e6, 64, fs=1.0, seed=1)
    msg = str(ei.value)
    assert "fs/2" in msg and "物理域" in msg
    assert "红线" not in msg


def test_defect_b7_low8_redline_reported_when_inside_physical_domain():
    """fs/2=60e6 内的 57e6 → 红线报文（顺序正确才不误归因）。"""
    with pytest.raises(ValueError, match="bandwidth_hz") as ei:
        gen_bandlimited_noise(57e6, 64, fs=120e6, seed=1)
    assert "红线" in str(ei.value)


# ---------------- 低#9：gen_pulse repeat_hz ≥ fs/2 采样欠定区拒 ----------------


def test_defect_b7_low9_repeat_ge_half_fs_rejected_with_both_values():
    """repeat=60 ≥ fs/2=50 → ValueError（含两值）。"""
    with pytest.raises(ValueError, match="repeat_hz") as ei:
        gen_pulse(0.001, 60.0, 64, fs=100.0)
    msg = str(ei.value)
    assert "60" in msg and "50" in msg  # repeat_hz 与 fs/2 两值


def test_defect_b7_low9_repeat_at_exact_half_fs_rejected():
    """repeat == fs/2（=50）也拒（≥ 口径：每周期恰 2 样本仍欠定）。"""
    with pytest.raises(ValueError, match="repeat_hz"):
        gen_pulse(0.001, 50.0, 64, fs=100.0)


def test_defect_b7_low9_tiny_duty_legal_path_unchanged():
    """duty=1e-9 合法路径不受影响：正常生成、meta 如实、t=0 锚点保持。"""
    x, meta = gen_pulse(1e-9, 1.0, 16, fs=8.0)
    assert x.shape == (16,) and x.dtype == np.complex64
    assert meta["duty_cycle"] == pytest.approx(1e-9)
    assert x[0].real == 1.0 and float(x[0].imag) == 0.0


# ---------------- 低#10：gen_pulse with_carrier=False 的 meta 如实 ----------------


def test_defect_b7_low10_no_carrier_meta_carrier_none_and_flag():
    """with_carrier=False：meta.carrier_hz=None + 'carrier_ignored': True。"""
    _, meta = gen_pulse(0.25, 1.0, 32, carrier_hz=100.0, with_carrier=False, fs=8.0)
    assert meta["carrier_hz"] is None
    assert meta["carrier_ignored"] is True
    assert meta["duty_cycle"] == pytest.approx(0.25)


def test_defect_b7_low10_with_carrier_meta_unchanged_no_flag():
    """with_carrier=True：carrier_hz 照实回显且无 carrier_ignored 键。"""
    _, meta = gen_pulse(0.25, 1.0, 32, carrier_hz=100.0, with_carrier=True, fs=8.0)
    assert meta["carrier_hz"] == 100.0
    assert "carrier_ignored" not in meta


# ---------------- 低#11：compose 混叠标注（不拒） ----------------


def test_defect_b7_low11_alias_warning_lists_equivalent_offsets():
    """|Δf|>fs/2 分量不拒：meta.alias_warning = 折叠到 (-fs/2, fs/2] 的等效频偏列表。"""
    out, meta = compose_jamming(
        [
            {"iq": np.ones(32), "freq_offset_hz": 75.0},   # → -25
            {"iq": np.ones(32), "freq_offset_hz": -75.0},  # → +25
            {"iq": np.ones(32), "freq_offset_hz": 10.0},   # 域内，不入列
        ],
        fs=100.0,
    )
    assert out.shape == (32,)  # 不拒——复信号口径照常合成
    assert meta["alias_warning"] == pytest.approx([-25.0, 25.0])
    assert len(meta["power_share"]) == 3


def test_defect_b7_low11_no_alias_no_warning_key():
    """全部分量 |Δf| ≤ fs/2 → 不加 alias_warning 键（meta 键集不变）。"""
    _, meta = compose_jamming(
        [{"iq": np.ones(8), "freq_offset_hz": 50.0}], fs=100.0  # 等号=fs/2 域内
    )
    assert "alias_warning" not in meta
    assert set(meta) == {"n_components", "length", "power_share"}


# ---------------- 低#12：整型口径 Integral（np.int64 过，bool 拒） ----------------


def test_defect_b7_low12_sweep_repeats_integral_accepted():
    """gen_sweep repeats=np.int64(3) 过；repeats=True 仍拒。"""
    iq = gen_sweep(10.0, 30.0, 0.05, repeats=np.int64(3), fs=1000.0)
    assert len(iq) == 3 * int(round(0.05 * 1000.0))
    with pytest.raises(ValueError, match="repeats"):
        gen_sweep(10.0, 30.0, 0.05, repeats=True, fs=1000.0)


def test_defect_b7_low12_chirp_n_samples_integral_accepted():
    """gen_chirp n_samples=np.int64(100) 过；bool/float 仍拒。"""
    x = gen_chirp(200.0, 100.0, 1.0, np.int64(100), fs=2000.0)
    assert x.shape == (100,)
    for bad in (True, 100.0):
        with pytest.raises(ValueError, match="n_samples"):
            gen_chirp(200.0, 100.0, 1.0, bad, fs=2000.0)


def test_defect_b7_low12_checker_repeats_integral_accepted():
    """checker repeats=np.int64(3) 无错；np.int64(0)/bool 仍记错。"""
    legal = {
        "style": "pulse",
        "bandwidth_hz": 1e6,
        "duty_cycle": 0.5,
        "sample_rate_hz": 1e6,
    }
    ok = check_style_params({**legal, "repeats": np.int64(3)})
    assert not [e for e in ok["errors"] if "repeats" in e]
    for bad, rendered in ((np.int64(0), "0"), (True, "True")):
        r = check_style_params({**legal, "repeats": bad})
        assert any("repeats" in e and rendered in e for e in r["errors"])


def test_defect_b7_low12_tone_noise_integrals_accepted():
    """既有 Integral 口径抽检：gen_tone/blnoise/partial_band 的 n_samples、seed 均过 np.int64。"""
    assert gen_tone(10.0, np.int64(8), fs=100.0).shape == (8,)
    iq, _ = gen_bandlimited_noise(0.2, np.int64(64), fs=1.0, seed=np.int64(9))
    assert iq.shape == (64,)
    iq2, _ = gen_partial_band(0.5, 100.0, np.int64(64), fs=100.0, seed=np.int64(9))
    assert iq2.shape == (64,)
