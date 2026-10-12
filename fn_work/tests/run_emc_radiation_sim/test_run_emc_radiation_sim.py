"""run_emc_radiation_sim 对抗测试：验收 slug=emc_radiation（内置音谱、洁净度判据、
无表/有表补偿口径、声明块、缺键拒绝、仪器域错透传）。"""
from __future__ import annotations

import numpy as np
import pytest

from src.run_emc_radiation_sim.run_emc_radiation_sim import run_emc_radiation_sim


def test_emc_radiation_builtin_tone_spectrum_and_cleanliness():
    """iq=None 内置音路径：单音 −30 dBm 恰落 center；洁净度一键/深杂散抑制。"""
    result = run_emc_radiation_sim({}, {"center_hz": 1e9, "span_hz": 1e6})
    spec = result["spectrum"]
    assert len(spec["freqs"]) == 1024 == len(spec["power_db"])
    assert spec["freqs"][0] == pytest.approx(1e9 - 5e5)            # 轴覆盖 center±span/2
    peak_power = max(spec["power_db"])
    assert peak_power == pytest.approx(-30.0, abs=1.6)             # 内置音 ±1.5dB 不确定度
    peak_bin = spec["power_db"].index(peak_power)
    assert spec["freqs"][peak_bin] == pytest.approx(1e9)           # 音恰落 center
    clean = result["cleanliness"]
    assert clean["in_band_peaks"] == 1                             # 单音 → 单峰簇
    assert clean["out_of_band_ratio_db"] < -40.0                   # 带外仅底噪（≈−60dB）
    assert result["simulated"] is True
    assert result["uncertainty_db"] == pytest.approx(1.5)


def test_emc_radiation_no_tables_compensated_false_with_note():
    """无补偿表：compensated=False + 未补偿标注；声明含 CISPR 16-1-1。"""
    result = run_emc_radiation_sim({}, {"center_hz": 1e9, "span_hz": 1e6})
    assert result["compensated"] is False
    assert "未" in result["compensation_note"] and "补偿" in result["compensation_note"]
    assert "CISPR 16-1-1" in result["disclaimer"]
    assert result["disclaimer"].startswith("> ")


def test_emc_radiation_tables_compensation_shifts_power():
    """tables 直传：双表平坦（L=3dB, C=2dB）→ 全谱平移 +5dB（与无表对照逐位差）。"""
    scenario = {"center_hz": 1e9, "span_hz": 1e6}
    raw = run_emc_radiation_sim({}, scenario)["spectrum"]["power_db"]
    tables = {
        "link_loss": {999.0: 3.0, 1001.0: 3.0},   # 谱落 999–1001 MHz 区间内 → 精确插值
        "antenna": {999.0: 2.0, 1001.0: 2.0},
    }
    comp = run_emc_radiation_sim({}, {**scenario, "compensation_tables": tables})
    assert comp["compensated"] is True
    assert "compensate_link_power" in comp["compensation_note"]
    for i in (0, 100, 512, 900, 1023):
        assert comp["spectrum"]["power_db"][i] == pytest.approx(
            raw[i] + 5.0, abs=1e-9
        )  # p_actual = p_measured + L_link + C_ant
    assert comp["spectrum"]["power_db"] != raw               # 谱值确已改变
    assert comp["cleanliness"]["in_band_peaks"] == 1         # 平移不改峰结构


def test_emc_radiation_two_tones_yield_two_in_band_peaks():
    """注入双音 IQ：峰簇归并正确——两个分离音 → in_band_peaks=2，杂散比≈−6dB。"""
    n = 1024
    k1, k2 = 100, 724                                             # fftshift 后相距 400 bin
    n_arr = np.arange(n)
    iq = np.exp(2j * np.pi * k1 * n_arr / n) + 0.5 * np.exp(2j * np.pi * k2 * n_arr / n)
    result = run_emc_radiation_sim(
        {}, {"center_hz": 1e9, "span_hz": 10e6, "iq": iq, "peak_drop_db": 10.0}
    )
    assert result["cleanliness"]["in_band_peaks"] == 2
    ratio = result["cleanliness"]["out_of_band_ratio_db"]
    assert -12.0 < ratio < 0.0                                    # 第二音 −6.02dB 为主杂散
    assert result["simulated"] is True


def test_emc_radiation_missing_center_or_span_rejected():
    """scenario 缺 center_hz / span_hz → ValueError。"""
    with pytest.raises(ValueError):
        run_emc_radiation_sim({}, {"span_hz": 1e6})
    with pytest.raises(ValueError):
        run_emc_radiation_sim({}, {"center_hz": 1e9})


def test_emc_radiation_analyzer_domain_error_propagates():
    """仪器观测域错透传：center 低于下域 / span 超上域 → setter ValueError。"""
    with pytest.raises(ValueError):
        run_emc_radiation_sim({}, {"center_hz": 1e5, "span_hz": 1e6})   # center < 1MHz
    with pytest.raises(ValueError):
        run_emc_radiation_sim({}, {"center_hz": 1e9, "span_hz": 1e9})   # span > 110MHz


def test_emc_radiation_ctx_and_scenario_shape_rejected():
    """共同口径：ctx/scenario 非 dict → ValueError。"""
    with pytest.raises(ValueError):
        run_emc_radiation_sim(None, {"center_hz": 1e9, "span_hz": 1e6})
    with pytest.raises(ValueError):
        run_emc_radiation_sim({}, 42)


def test_emc_radiation_disclaimer_emc_scene_and_simulated_flag():
    """声明块互含 emc 场景句（恒含行）+ 模拟标记恒在。"""
    result = run_emc_radiation_sim({}, {"center_hz": 1e9, "span_hz": 1e6})
    assert "本测试为模拟演示" in result["disclaimer"]
    assert "CISPR 16-1-1" in result["disclaimer"]
    assert result["simulated"] is True
