"""run_emc_conduction_sim 对抗测试：验收 slug=emc_conduction（LISN 模拟读数链、dBµV 换算、
限值裕量与 passed 口径、ctx 注入透传、频域裁剪、缺键拒绝、模拟口径声明）。"""
from __future__ import annotations

import math

import pytest

from src.open_sim_emi_receiver.open_sim_emi_receiver import open_sim_emi_receiver
from src.run_emc_conduction_sim.run_emc_conduction_sim import run_emc_conduction_sim

#: 仿真底噪口径：−150 dBm/Hz + 10·log10(rbw)；<30MHz 缺省 RBW=9kHz。
_NOISE_9K = -150.0 + 10.0 * math.log10(9e3)
_NOISE_120K = -150.0 + 10.0 * math.log10(120e3)


def test_emc_conduction_single_point_dbuv_margin_disclaimer():
    """单点底噪读数：dBµV=dBm+107 换算、margin、声明含 CISPR 16-1-1、模拟标记。"""
    result = run_emc_conduction_sim({}, {"freq_hz": 10e6, "limit_line_dbmv": 0.0})
    (reading,) = result["readings"]
    assert reading["freq_hz"] == pytest.approx(10e6)
    assert reading["power_dbm"] == pytest.approx(_NOISE_9K)      # <30MHz → RBW 9kHz 底噪
    assert reading["power_dbuv"] == pytest.approx(_NOISE_9K + 107.0)  # dBµV = dBm + 107
    assert reading["margin_db"] == pytest.approx(0.0 - (_NOISE_9K + 107.0))
    assert result["detector"] == "peak"                          # 工厂缺省检波器
    assert result["simulated"] is True
    assert "CISPR 16-1-1" in result["disclaimer"]                # 非 CISPR 16-1-1 接收机声明
    assert result["disclaimer"].startswith("> ")                 # markdown 引用块口径
    assert "107" in result["conversion_note"]                    # 换算口径随输出注明


def test_emc_conduction_iq_injection_reads_above_noise_floor():
    """iq 注入路径：电流探头模拟 IQ 读数为音功率（≈0 dBm），绝非底噪口径。"""
    scenario = {"freq_hz": 10e6, "iq": [1.0] * 64, "limit_line_dbmv": 60.0}
    result = run_emc_conduction_sim({}, scenario)
    reading = result["readings"][0]
    assert reading["power_dbm"] == pytest.approx(0.0, abs=1e-9)  # 单音幅度 1.0 → 0 dBm
    assert reading["power_dbm"] > _NOISE_9K + 60.0               # 远高于底噪（非底噪路径）
    assert reading["power_dbuv"] == pytest.approx(107.0)
    assert reading["margin_db"] == pytest.approx(60.0 - 107.0)   # 超限 → 负裕量
    assert result["passed"] is False


def test_emc_conduction_passed_verdict_margin_signs():
    """passed 口径：裕量全非负 → True；任一超限 → False（演示口径，非认证）。"""
    ok = run_emc_conduction_sim({}, {"freq_hz": 10e6, "limit_line_dbmv": 0.0})
    assert ok["passed"] is True                                   # margin ≈ +3.46 ≥ 0
    assert "非认证" in ok["compliance_note"]
    over = run_emc_conduction_sim({}, {"freq_hz": 10e6, "limit_line_dbmv": -10.0})
    assert over["passed"] is False
    assert over["readings"][0]["margin_db"] < 0
    # 多点其一超限即 False
    mixed = run_emc_conduction_sim(
        {},
        {"freq_hz": [10e6, 20e6], "limit_line_dbmv": {10e6: 0.0, 20e6: -100.0}},
    )
    assert mixed["passed"] is False


def test_emc_conduction_injected_receiver_params_pass_through():
    """ctx 注入接收机：scenario 未给 detector/rbw_hz 时注入参数原样透传。"""
    rx = open_sim_emi_receiver(
        {"freq_hz": 10e6, "detector": "quasi_peak", "rbw_hz": 120e3}
    )
    result = run_emc_conduction_sim({"em_receiver": rx}, {"freq_hz": 10e6})
    reading = result["readings"][0]
    assert reading["rbw_hz"] == pytest.approx(120e3)              # 注入 RBW 不被改写
    assert reading["power_dbm"] == pytest.approx(_NOISE_120K)     # 底噪按注入 RBW 积分
    assert result["detector"] == "quasi_peak"                     # 注入检波器透传


def test_emc_conduction_missing_freq_rejected():
    """scenario 缺 freq_hz / 空序列 → ValueError（测点是硬前置）。"""
    with pytest.raises(ValueError):
        run_emc_conduction_sim({}, {"limit_line_dbmv": 0.0})
    with pytest.raises(ValueError):
        run_emc_conduction_sim({}, {"freq_hz": []})
    with pytest.raises(ValueError):
        run_emc_conduction_sim({}, {"freq_hz": "10MHz"})


def test_emc_conduction_multi_point_with_limit_mapping():
    """sweep 小段：freq 列表逐点读数 + 限值映射逐点取限；映射缺点 ValueError。"""
    scenario = {
        "freq_hz": [150e3, 1e6],
        "limit_line_dbmv": {150e3: 40.0, 1e6: 50.0},
    }
    result = run_emc_conduction_sim({}, scenario)
    assert [r["freq_hz"] for r in result["readings"]] == [150e3, 1e6]
    r0, r1 = result["readings"]
    assert r0["power_dbm"] == pytest.approx(_NOISE_9K)            # 两点均 <30MHz → 9kHz
    assert r0["margin_db"] == pytest.approx(40.0 - (r0["power_dbm"] + 107.0))
    assert r1["margin_db"] == pytest.approx(50.0 - (r1["power_dbm"] + 107.0))
    with pytest.raises(ValueError, match="缺频点"):
        run_emc_conduction_sim(
            {}, {"freq_hz": [150e3, 1e6], "limit_line_dbmv": {150e3: 40.0}}
        )


def test_emc_conduction_out_of_domain_freq_clipped_with_warning():
    """R33 裁剪+标注：测点低于模拟域下限 1kHz → 裁剪到 1kHz 并记 warnings。"""
    result = run_emc_conduction_sim({}, {"freq_hz": 500.0, "limit_line_dbmv": 0.0})
    assert result["readings"][0]["freq_hz"] == pytest.approx(1e3)  # 读数为裁剪后实测频率
    assert any("裁剪" in w for w in result["warnings"])
    assert result["simulated"] is True                             # 演示态继续，不抛


def test_emc_conduction_ctx_and_scenario_shape_rejected():
    """共同口径：ctx/scenario 非 dict → ValueError。"""
    with pytest.raises(ValueError):
        run_emc_conduction_sim(None, {"freq_hz": 10e6})
    with pytest.raises(ValueError):
        run_emc_conduction_sim("ctx", {"freq_hz": 10e6})
    with pytest.raises(ValueError):
        run_emc_conduction_sim({}, ["freq_hz"])


def test_emc_conduction_missing_limit_margin_none_passed_none():
    """未提供限值线：margin_db=None、passed=None（无法判定，演示态继续不抛）。"""
    result = run_emc_conduction_sim({}, {"freq_hz": 10e6})
    assert result["readings"][0]["margin_db"] is None
    assert result["passed"] is None
    assert result["simulated"] is True
    assert "limit_note" in result


def test_emc_conduction_disclaimer_carries_emc_scene_simulated_flag():
    """声明块互含 emc 场景句（恒含行）+ 模拟标记恒在。"""
    result = run_emc_conduction_sim({}, {"freq_hz": 10e6})
    assert "本测试为模拟演示" in result["disclaimer"]             # emc 场景恒含句
    assert "CISPR 16-1-1" in result["disclaimer"]
    assert result["simulated"] is True
