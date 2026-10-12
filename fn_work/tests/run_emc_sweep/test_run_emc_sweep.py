"""run_emc_sweep 对抗测试：验收 slug=emc_sweep（计划透传、逐点读数、杂散标记/计数、
iq_provider 逐点注入、频段便捷、单点警告、越界裁剪、声明与敏感度口径）。"""
from __future__ import annotations

import math

import pytest

from src.run_emc_sweep.run_emc_sweep import run_emc_sweep

#: 仿真底噪口径：−150 dBm/Hz + 10·log10(rbw)。
_NOISE_9K = -150.0 + 10.0 * math.log10(9e3)
_NOISE_120K = -150.0 + 10.0 * math.log10(120e3)


def test_emc_sweep_cispr_b_band_convenience_points_and_band_split_rbw():
    """cispr_b 频段便捷：150kHz–30MHz 对数步 r=1 → 恰 9 点；频段分界 RBW 折弯可观测。"""
    result = run_emc_sweep({}, {"band": "cispr_b", "scale": "log", "step_hz": 1.0})
    freqs = [p["freq_hz"] for p in result["points"]]
    assert result["n_points"] == 9 == len(freqs)
    assert freqs[0] == pytest.approx(150e3)
    assert freqs[-1] == pytest.approx(30e6)
    assert result["plan"]["band"] == "cispr_b"
    # 仅 30MHz 点落 ≥30MHz 上带：自动 RBW 120kHz → 底噪 −99.2 dBm 超缺省阈 −100
    assert result["points"][-1]["power_dbm"] == pytest.approx(_NOISE_120K)
    assert result["n_spurious"] == 1
    assert result["points"][-1].get("spurious") is True
    assert all("spurious" not in p for p in result["points"][:-1])  # 其余 9kHz 底噪不超阈


def test_emc_sweep_spurious_threshold_flags_all_points():
    """阈值即口径：spurious_threshold_dbm=−120 → 全部底噪点（−110.5）超阈全标记。"""
    scenario = {
        "start_hz": 9e3,
        "stop_hz": 90e3,
        "step_hz": 9e3,
        "spurious_threshold_dbm": -120.0,
    }
    result = run_emc_sweep({}, scenario)
    assert result["n_points"] == 10
    assert result["n_spurious"] == 10
    assert all(p.get("spurious") is True for p in result["points"])
    assert "-120.0" in result["sensitivity_note"] and "敏感度" in result["sensitivity_note"]


def test_emc_sweep_default_threshold_linear_noise_floor_no_spurious():
    """缺省阈 −100：9k–90k 全带 <30MHz → 9kHz RBW 底噪 −110.5 不超阈，无标记。"""
    result = run_emc_sweep({}, {"start_hz": 9e3, "stop_hz": 90e3, "step_hz": 9e3})
    assert result["n_points"] == 10
    assert result["n_spurious"] == 0
    assert all("spurious" not in p for p in result["points"])
    assert all(p["power_dbm"] == pytest.approx(_NOISE_9K) for p in result["points"])
    assert result["simulated"] is True


def test_emc_sweep_iq_provider_called_per_planned_point():
    """iq_provider 逐点注入：按计划顺序恰每点一次调用；0dBm 音读数全点超阈。"""
    calls: list[float] = []

    def provider(freq_hz: float):
        calls.append(freq_hz)
        return [1.0] * 64                                         # 4 帧×16 → DC 音 0 dBm

    scenario = {
        "start_hz": 1e6,
        "stop_hz": 3e6,
        "step_hz": 1e6,
        "iq_provider": provider,
    }
    result = run_emc_sweep({}, scenario)
    assert calls == result["plan"]["points_hz"]                    # 逐点恰一次、按计划序
    assert result["n_spurious"] == 3                              # 0 dBm ≫ −100 dBm
    assert all(p["power_dbm"] == pytest.approx(0.0, abs=1e-9) for p in result["points"])
    assert all(p.get("spurious") is True for p in result["points"])


def test_emc_sweep_plan_scale_log_passthrough():
    """plan 透传：scale='log' 原样进计划与输出（1M→2M→4M 恰 3 点）。"""
    result = run_emc_sweep(
        {}, {"start_hz": 1e6, "stop_hz": 4e6, "step_hz": 1.0, "scale": "log"}
    )
    assert result["plan"]["scale"] == "log"
    assert result["plan"]["step_note"].startswith("log")
    assert [p["freq_hz"] for p in result["points"]] == [
        pytest.approx(1e6),
        pytest.approx(2e6),
        pytest.approx(4e6),
    ]
    assert result["n_points"] == 3 == result["plan"]["n_points"]


def test_emc_sweep_single_point_plan_warning_surfaced():
    """单点退化：step ≥ 跨度 → 计划 single_point 警告浮出到输出 warnings。"""
    result = run_emc_sweep({}, {"start_hz": 1e6, "stop_hz": 2e6, "step_hz": 1e6})
    assert result["n_points"] == 1
    assert "single_point" in result["warnings"]
    assert result["points"][0]["freq_hz"] == pytest.approx(1e6)


def test_emc_sweep_out_of_domain_points_clipped_and_annotated():
    """R35 越界裁剪+标注：超 3GHz 上界的计划点裁到 3GHz，不丢点。"""
    result = run_emc_sweep({}, {"start_hz": 2.9e9, "stop_hz": 3.5e9, "step_hz": 2e8})
    assert all(p["freq_hz"] <= 3e9 for p in result["points"])
    assert any("裁剪" in w for w in result["warnings"])
    assert result["n_points"] == result["plan"]["n_points"]        # 裁剪不丢点
    assert result["simulated"] is True                             # 演示态继续，不抛


def test_emc_sweep_scenario_plan_and_ctx_errors():
    """scenario 缺 start/stop（无 band）、ctx 形状错、计划域错（起止颠倒）→ ValueError。"""
    with pytest.raises(ValueError):
        run_emc_sweep({}, {"stop_hz": 90e3})                       # 缺 start_hz
    with pytest.raises(ValueError):
        run_emc_sweep(None, {"start_hz": 9e3, "stop_hz": 90e3})    # ctx 非 dict
    with pytest.raises(ValueError):
        run_emc_sweep({}, {"start_hz": 90e3, "stop_hz": 9e3, "step_hz": 9e3})  # 起止颠倒透传
    with pytest.raises(TypeError):
        run_emc_sweep(
            {}, {"start_hz": 9e3, "stop_hz": 90e3, "iq_provider": "not-callable"}
        )


def test_emc_sweep_disclaimer_simulated_and_cispr_a_convenience():
    """声明块互含 emc 场景句 + cispr_a 频段便捷（9k–150k 线性 9k 步 → 17 点）。"""
    result = run_emc_sweep({}, {"band": "cispr_a", "step_hz": 9e3})
    assert result["simulated"] is True
    assert "本测试为模拟演示" in result["disclaimer"]
    assert "CISPR 16-1-1" in result["disclaimer"]
    assert result["n_points"] == 17
    assert result["points"][0]["freq_hz"] == pytest.approx(9e3)
    assert result["points"][-1]["freq_hz"] == pytest.approx(150e3)
