"""synthesize_style 对抗测试（B8 顶层 R9）：校验→分派→defaults 合并→六样式频谱
特征→composite 递归合成→meta 副本/幂等→power_dbm 仅记录不缩放。"""
from __future__ import annotations

import numpy as np
import pytest

from src.synthesize_style.gen_tone import gen_tone
from src.synthesize_style.synthesize_style import synthesize_style
from src.switch_style.lookup_style_recipe import RECIPES, StyleError, register_recipe


# ---- 六样式基本契约：complex64 + meta 形状 + fs 透传记录 ----


_SIX_STYLE_PARAMS = {
    "tone": {"freq_offset_hz": 1e3, "n_samples": 256},
    "sweep": {"f0": -1e3, "f1": 1e3, "duration_s": 1e-3},
    "chirp": {"center_hz": 0.0, "bandwidth_hz": 10e3, "period_s": 1e-3, "n_samples": 512},
    "bandlimited_noise": {"bandwidth_hz": 10e3, "n_samples": 2048, "seed": 11},
    "partial_band": {"fraction": 0.5, "victim_bw_hz": 10e3, "n_samples": 2048, "seed": 12},
    "pulse": {"pulse_width_s": 1e-4, "repeat_hz": 1e3, "n_samples": 2048},
}


@pytest.mark.parametrize("style", sorted(_SIX_STYLE_PARAMS))
def test_styles_synth_six_styles_basic_contract(style):
    """六样式各自最小参数合成：complex64 非空 + meta 三基本键 + fs 入合并参数。"""
    params = {"style": style, "fs": 1e6, **_SIX_STYLE_PARAMS[style]}
    iq, meta = synthesize_style(params)
    assert isinstance(iq, np.ndarray) and iq.dtype == np.complex64 and iq.size > 0
    assert meta["style"] == style
    assert meta["n_samples"] == iq.size
    assert meta["params"]["fs"] == 1e6
    assert meta["params"]["style"] == style


# ---- 六样式频谱特征 ----


def test_styles_synth_tone_single_fft_peak_bin():
    """tone：整 bin 单频 → FFT 唯一主峰且峰值远高于次峰（泄漏可忽略）。"""
    iq, meta = synthesize_style(
        {"style": "tone", "fs": 1024.0, "freq_offset_hz": 100.0, "n_samples": 1024}
    )
    spec = np.abs(np.fft.fft(iq.astype(np.complex128)))
    assert int(np.argmax(spec)) == 100
    desc = np.sort(spec)[::-1]
    assert desc[0] > 100.0 * desc[1]
    assert meta["n_samples"] == 1024


def test_styles_synth_fs_passthrough_tone_0p1fs():
    """fs 透传：fs=100、频偏 0.1fs=10 Hz → 峰 bin = 0.1*N = 100。"""
    iq, meta = synthesize_style(
        {"style": "tone", "fs": 100.0, "freq_offset_hz": 10.0, "n_samples": 1000}
    )
    spec = np.abs(np.fft.fft(iq.astype(np.complex128)))
    assert int(np.argmax(spec)) == 100  # 0.1 * fs → 0.1 * N 样本 bin
    assert meta["params"]["fs"] == 100.0


def test_styles_synth_bandlimited_noise_bandwidth_meta():
    """bandlimited_noise：实测带宽元数据 ≈ 请求带宽（±2 个 FFT bin），RMS 归一。"""
    n, fs, bw, seed = 8192, 1e6, 20e3, 7
    iq, meta = synthesize_style(
        {"style": "bandlimited_noise", "fs": fs, "bandwidth_hz": bw,
         "n_samples": n, "seed": seed}
    )
    df = fs / n
    assert meta["measured_bw_hz"] == pytest.approx(bw, abs=2 * df)
    assert 0 < meta["occupied_bw99_hz"] <= bw + 2 * df
    assert meta["seed"] == seed
    rms = float(np.sqrt(np.mean(np.abs(iq.astype(np.complex128)) ** 2)))
    assert rms == pytest.approx(1.0, abs=1e-3)  # rms_amplitude 缺省 1.0


def test_styles_synth_pulse_duty_cycle():
    """pulse：脉宽×重复频率=0.1 → meta 占空比 0.1，非零样本占比 ≈ 0.1。"""
    iq, meta = synthesize_style(
        {"style": "pulse", "fs": 1e6, "pulse_width_s": 1e-4, "repeat_hz": 1e3,
         "n_samples": 8192}
    )
    assert meta["duty_cycle"] == pytest.approx(0.1)
    assert meta["carrier_hz"] == 0.0
    frac_nonzero = float(np.count_nonzero(iq) / iq.size)
    assert 0.09 < frac_nonzero < 0.115  # 脉间段精确为零


def test_styles_synth_chirp_first_last_instantaneous_freq():
    """chirp：瞬时频率首末覆盖 [center−bw/2, center+bw/2]（相位差分估计）。"""
    center, bw = 0.0, 20e3
    low, high = center - bw / 2, center + bw / 2
    iq, _ = synthesize_style(
        {"style": "chirp", "fs": 1e6, "center_hz": center, "bandwidth_hz": bw,
         "period_s": 1e-3, "n_samples": 4096}
    )
    x = iq.astype(np.complex128)
    inst = np.diff(np.unwrap(np.angle(x))) * 1e6 / (2 * np.pi)
    valid = inst[(inst > low - 2e3) & (inst < high + 2e3)]  # 剔除锯齿回跳点
    assert valid.size > 3000
    assert low - 500 <= valid.min() <= low + 500
    assert high - 500 <= valid.max() <= high + 500


def test_styles_synth_sweep_length_from_duration_fs_repeats():
    """sweep：长度 = round(duration×fs)×repeats（5000×3=15000），恒包络。"""
    iq, meta = synthesize_style(
        {"style": "sweep", "fs": 1e6, "f0": -10e3, "f1": 10e3,
         "duration_s": 5e-3, "repeats": 3}
    )
    assert iq.size == 15000
    assert meta["n_samples"] == 15000
    assert np.allclose(np.abs(iq), 1.0)


def test_styles_synth_partial_band_occupied_fraction():
    """partial_band：占比 0.25 → 实测占位 ≈ victim×fraction，带外功率近零。"""
    n, fs = 8192, 1e6
    iq, meta = synthesize_style(
        {"style": "partial_band", "fs": fs, "fraction": 0.25,
         "victim_bw_hz": 20e3, "n_samples": n, "seed": 3}
    )
    df = fs / n
    assert meta["occupied_bw_hz"] == pytest.approx(5e3, abs=2 * df)
    assert meta["fraction"] == 0.25 and meta["victim_bw_hz"] == 20e3
    spec = np.abs(np.fft.fft(iq.astype(np.complex128))) ** 2
    freqs = np.fft.fftfreq(n, d=1.0 / fs)
    out_band = np.abs(freqs) > 2500.0 + 2 * df
    assert float(spec[out_band].sum() / spec.sum()) < 1e-3


# ---- defaults 合并 / required / check 失败 / 未注册 ----


def test_styles_synth_sweep_defaults_merge_fs():
    """defaults 合并：sweep 只给 f0/f1/duration → fs/repeats 由配方缺省补齐，
    显式 f0 优先于缺省 −10e3，调用方原参不被污染。"""
    params = {"style": "sweep", "f0": -5e3, "f1": 5e3, "duration_s": 2e-3}
    iq, meta = synthesize_style(params)
    assert iq.size == 2000  # round(2e-3 × 缺省 fs=1e6)
    assert meta["params"]["fs"] == 1e6
    assert meta["params"]["repeats"] == 1
    assert meta["params"]["f0"] == -5e3
    assert "fs" not in params and "repeats" not in params  # 原参未染


def test_styles_synth_missing_required_lists_names():
    """required 缺 → StyleError 列缺参名（六基础样式 required 均有缺省覆盖，
    经 register_recipe 注册 required 超出 defaults 的扩展样式触发）。"""
    register_recipe(
        "gap_style",
        {"generator": gen_tone, "defaults": {"freq_offset_hz": 5.0},
         "required": ["freq_offset_hz", "n_samples"]},
    )
    try:
        with pytest.raises(StyleError) as ei:
            synthesize_style({"style": "gap_style", "fs": 1000.0})
        assert "n_samples" in str(ei.value)
        # 补齐缺参后同一扩展样式可正常合成（defaults 供 freq_offset_hz=5.0）。
        iq, meta = synthesize_style(
            {"style": "gap_style", "fs": 1000.0, "n_samples": 128}
        )
        assert iq.size == 128 and meta["params"]["freq_offset_hz"] == 5.0
    finally:
        RECIPES.pop("gap_style", None)


def test_styles_synth_check_failure_power_over_cap():
    """check 失败：power_dbm=+3 越红线 → StyleError 附 errors 清单（含参数名）。"""
    with pytest.raises(StyleError) as ei:
        synthesize_style(
            {"style": "tone", "fs": 1e3, "freq_offset_hz": 10.0,
             "n_samples": 64, "power_dbm": 3.0}
        )
    msg = str(ei.value)
    assert "power_dbm" in msg and "校验失败" in msg


def test_styles_synth_unregistered_style_error_lists_roster():
    """未注册样式 → StyleError 附在册清单（含六样式名与原样式名）。"""
    with pytest.raises(StyleError) as ei:
        synthesize_style({"style": "bogus", "fs": 1000.0})
    msg = str(ei.value)
    assert "bogus" in msg and "tone" in msg and "pulse" in msg


def test_styles_synth_missing_style_or_fs_rejected():
    """params 必含 'style' 与 'fs'：tone 无 fs 缺省可继承 → 缺 fs 即 StyleError。"""
    with pytest.raises(StyleError):
        synthesize_style({"freq_offset_hz": 10.0, "n_samples": 64, "fs": 100.0})
    with pytest.raises(StyleError) as ei:
        synthesize_style({"style": "tone", "freq_offset_hz": 10.0, "n_samples": 64})
    assert "fs" in str(ei.value)


# ---- composite 合成模式 ----


def test_styles_synth_composite_two_tones_double_peak():
    """composite 两 tone 分量 → 双峰谱（净频位=生成频率+合成级频偏=±40kHz）
    + components_meta + 功率占比均分 + fs 继承。"""
    params = {
        "style": "composite",
        "fs": 1e6,
        "components": [
            {"style": "tone", "freq_offset_hz": 20e3, "n_samples": 5000},
            {"style": "tone", "freq_offset_hz": -20e3, "n_samples": 5000,
             "phase_rad": 0.0},
        ],
    }
    iq, meta = synthesize_style(params)
    assert iq.dtype == np.complex64 and iq.size == 5000
    assert meta["style"] == "composite" and meta["n_components"] == 2
    assert meta["power_share"][0] == pytest.approx(0.5, abs=1e-9)
    assert meta["power_share"][1] == pytest.approx(0.5, abs=1e-9)
    # 峰 bin：±40e3 × 5000/1e6 = ±200（整 bin，两峰等幅、远高于第三峰）
    spec = np.abs(np.fft.fft(iq.astype(np.complex128)))
    top2 = set(int(i) for i in np.argsort(spec)[-2:])
    assert top2 == {200, 4800}
    desc = np.sort(spec)[::-1]
    assert desc[2] < 1e-2 * desc[0]
    # 分量递归 meta：继承的顶层 fs 已入各分量合并参数
    assert len(meta["components_meta"]) == 2
    for comp_meta in meta["components_meta"]:
        assert comp_meta["style"] == "tone"
        assert comp_meta["params"]["fs"] == 1e6
        assert comp_meta["n_samples"] == 5000


def test_styles_synth_composite_component_error_carries_index():
    """composite 分量递归失败 → StyleError 附来源分量序号（components[1]）。"""
    params = {
        "style": "composite",
        "fs": 1e6,
        "components": [
            {"style": "tone", "freq_offset_hz": 10e3, "n_samples": 1024},
            {"style": "nope", "freq_offset_hz": 1.0},  # 未注册样式
        ],
    }
    with pytest.raises(StyleError) as ei:
        synthesize_style(params)
    msg = str(ei.value)
    assert "分量[1]" in msg and "nope" in msg


def test_styles_synth_composite_bad_components_rejected():
    """components 非 list / 空列表 / 元素非 dict → StyleError。"""
    with pytest.raises(StyleError):
        synthesize_style({"style": "composite", "fs": 1e6, "components": []})
    with pytest.raises(StyleError):
        synthesize_style({"style": "composite", "fs": 1e6, "components": "tone"})
    with pytest.raises(StyleError):
        synthesize_style({"style": "composite", "fs": 1e6, "components": ["tone"]})  # 元素非 dict
    with pytest.raises(StyleError):
        synthesize_style({"style": "composite", "fs": 1e6,
                          "components": [{"freq_offset_hz": 1.0}]})  # 分量缺 style
    with pytest.raises(StyleError):
        synthesize_style({"style": "composite", "components": [{"style": "tone"}]})  # 顶层缺 fs


# ---- meta.params 副本与幂等 / power_dbm 仅记录 ----


def test_styles_synth_meta_params_copy_idempotent():
    """meta['params'] 是副本：改写不影响调用方原参，也不影响再合成（seed 固定幂等）。"""
    params = {
        "style": "bandlimited_noise", "fs": 1e6, "bandwidth_hz": 10e3,
        "n_samples": 4096, "seed": 42,
    }
    iq1, meta1 = synthesize_style(params)
    assert meta1["params"] is not params
    meta1["params"]["seed"] = 999
    meta1["params"]["bandwidth_hz"] = 1e3
    assert params["seed"] == 42 and params["bandwidth_hz"] == 10e3  # 原参未染
    iq2, meta2 = synthesize_style(params)
    assert np.array_equal(iq1, iq2)  # 同参数（同 seed）逐位一致
    assert meta2["params"]["seed"] == 42 and meta2["params"]["bandwidth_hz"] == 10e3
    assert meta1["params"] is not meta2["params"]


def test_styles_synth_power_dbm_recorded_not_scaling():
    """power_dbm 仅记录入 meta 不缩放幅度：不同 dBm 输出逐位一致，包络恒为标称 1。"""
    base = {"style": "tone", "fs": 1024.0, "freq_offset_hz": 100.0, "n_samples": 512}
    iq_a, meta_a = synthesize_style({**base, "power_dbm": -30.0})
    iq_b, meta_b = synthesize_style({**base, "power_dbm": -90.0})
    iq_c, meta_c = synthesize_style(dict(base))
    assert np.array_equal(iq_a, iq_b)
    assert np.array_equal(iq_a, iq_c)
    assert np.allclose(np.abs(iq_a), 1.0)  # 幅度仍是生成器标称，未按 dBm 缩放
    assert meta_a["params"]["power_dbm"] == -30.0
    assert meta_b["params"]["power_dbm"] == -90.0
    assert "power_dbm" not in meta_c["params"]
