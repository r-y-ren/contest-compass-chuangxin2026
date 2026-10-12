"""run_emc_radiation_sim 对抗测试：验收 slug=emc_radiation（内置音谱、洁净度判据、
无表/有表/空表/部分覆盖补偿口径、声明块、缺键拒绝、仪器域错透传与 center 回滚）。"""
from __future__ import annotations

import numpy as np
import pytest

from src.open_sim_analyzer.open_sim_analyzer import open_sim_analyzer
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


# ---------------------------------------------------------------------------
# B16 修复回归
# ---------------------------------------------------------------------------

def test_emc_radiation_empty_tables_compensated_false_with_empty_note():
    """B16中#3：空表（{} 或全空 entries）→ compensated=False +「表为空——未补偿」。"""
    scenario = {"center_hz": 1e9, "span_hz": 1e6}
    for empty_tables in ({}, {"link_loss": {}, "antenna": {}}):
        result = run_emc_radiation_sim(
            {}, {**scenario, "compensation_tables": empty_tables}
        )
        assert result["compensated"] is False
        assert "表为空" in result["compensation_note"]
        assert "未补偿" in result["compensation_note"]
        assert "compensation_confidence" not in result   # 未补偿不带置信度汇总


def test_emc_radiation_partial_coverage_confidence_summary():
    """B16中#3：部分覆盖 → compensated=True + 逐 bin 置信度汇总
    {'ok','extrapolated','no_table'}。"""
    scenario = {"center_hz": 1e9, "span_hz": 1e6}
    # link_loss 覆盖谱段（999.5–1000.5MHz 落 999–1001 区间内→ok）；
    # antenna 只覆盖 1100MHz 外 → 全程取低端端点 → extrapolated 支配
    tables = {
        "link_loss": {999.0: 3.0, 1001.0: 3.0},
        "antenna": {1100.0: 2.0, 1101.0: 2.0},
    }
    result = run_emc_radiation_sim({}, {**scenario, "compensation_tables": tables})
    assert result["compensated"] is True
    conf = result["compensation_confidence"]
    assert set(conf) == {"ok", "extrapolated", "no_table"}
    assert conf == {"ok": 0, "extrapolated": 1024, "no_table": 0}
    # antenna 键整体缺（走文件加载口径仍无表）→ no_table 支配；link_loss 仍贡献补偿
    one_table = {"link_loss": {999.0: 3.0, 1001.0: 3.0}}
    result2 = run_emc_radiation_sim({}, {**scenario, "compensation_tables": one_table})
    assert result2["compensated"] is True
    assert result2["compensation_confidence"] == {
        "ok": 0, "extrapolated": 0, "no_table": 1024,
    }


def test_emc_radiation_full_coverage_confidence_all_ok():
    """B16中#3：双表全覆盖 → 全 bin 'ok'（汇总随部分覆盖口径一并输出）。"""
    scenario = {"center_hz": 1e9, "span_hz": 1e6}
    tables = {
        "link_loss": {999.0: 3.0, 1001.0: 3.0},
        "antenna": {999.0: 2.0, 1001.0: 2.0},
    }
    result = run_emc_radiation_sim({}, {**scenario, "compensation_tables": tables})
    assert result["compensation_confidence"] == {"ok": 1024, "extrapolated": 0, "no_table": 0}


def test_emc_radiation_span_error_rolls_back_injected_center():
    """B16低#6：set_center 成功而 set_span 域错 → 注入实例 center 回滚（无半套残留）。"""
    analyzer = open_sim_analyzer({"center_hz": 2e9, "span_hz": 1e6})
    with pytest.raises(ValueError):
        run_emc_radiation_sim(
            {"spectrum_analyzer": analyzer},
            {"center_hz": 1e9, "span_hz": 1e12},   # span 超上域 110MHz → set_span 拒
        )
    assert analyzer.center_hz == pytest.approx(2e9)  # 原值恢复——center 不残留 1e9
    assert analyzer.span_hz == pytest.approx(1e6)    # span 本就未被写
