"""run_scenario 的 EMC 场景信封通路单测（走查环 F1 修复配套，2026-10-14）：
scenario_type='emc' 的场景携 _EMC_PARAM_KEYS（emc_flow/span_hz/detector 等
schema 不在册的流程键）经 _normalize_scenario_object 信封摘出落位——校验通过
且 execute_scenario 按 emc_flow 分派真跑；非 emc 场景不摘（未知键拒绝不放松）。
"""
import pytest

from src.run_demo.run_demo import run_scenario

#: 完整 EMC 场景（demo_emc_flows._COMMON_DEFAULTS 同口径最小集）。
_BASE_EMC = {
    "style": "bandlimited_noise",
    "fs": 10.0e6,
    "bandwidth_hz": 2.0e6,
    "freq_hz": 2.4e9,
    "power_dbm": -20.0,
    "duration_s": 0.01,
    "backend": "sim",
    "bands": [[2400.0, 2483.5]],
    "shielded_box": True,
    "dut_scope": "self_built",
    "scenario_type": "emc",
}


def test_emc_envelope_sweep_flow_runs_to_completion(tmp_path):
    """① emc+sweep（band 便捷参数）：信封摘出后校验通过→真跑 completed。"""
    scenario = {**_BASE_EMC, "emc_flow": "sweep", "band": "cispr_b", "step_hz": 5e6}
    result = run_scenario(scenario, out_root=str(tmp_path))
    assert result["status"] == "completed" and result["exit_code"] == 0


def test_emc_envelope_radiation_span_hz_dispatch(tmp_path):
    """② radiation 流程键（span_hz/detector/rbw_hz 均 schema 不在册）：信封
    摘出落位→分派 run_emc_radiation_sim 真跑 completed。"""
    scenario = {
        **_BASE_EMC,
        "emc_flow": "radiation",
        "center_hz": 100.0e6,
        "span_hz": 1.0e6,
        "detector": "average",
        "rbw_hz": 1e3,
    }
    result = run_scenario(scenario, out_root=str(tmp_path))
    assert result["status"] == "completed" and result["exit_code"] == 0


def test_emc_envelope_not_loosened_for_non_emc_scenarios(tmp_path):
    """③ 不放松：非 emc 场景携 emc_flow/span_hz → 仍按未知键拒绝
    （validation_failed，与既有形状纪律一致）。"""
    scenario = {
        **_BASE_EMC,
        "scenario_type": "gb42590",
        "emc_flow": "sweep",
    }
    del scenario["scenario_type"]  # 缺省 gb42590（非 emc——信封不摘）
    result = run_scenario(scenario, out_root=str(tmp_path))
    assert result["status"] == "validation_failed"
    assert "未知键: emc_flow" in result["error"]


def test_emc_envelope_unknown_other_keys_still_rejected(tmp_path):
    """④ emc 场景的信封摘出仅限在册 EMC 流程键：其余未知键照拒。"""
    scenario = {**_BASE_EMC, "emc_flow": "sweep", "band": "cispr_b", "bogus_key": 1}
    result = run_scenario(scenario, out_root=str(tmp_path))
    assert result["status"] == "validation_failed"
    assert "未知键: bogus_key" in result["error"]


def test_emc_envelope_bad_flow_value_rejected_at_dispatch(tmp_path):
    """⑤ emc_flow 值域归分派器（ScenarioError 发射前拒绝）：未知值→运行失败
    附原文（不因信封摘出而放宽值域）。"""
    scenario = {**_BASE_EMC, "emc_flow": "bogus", "band": "cispr_b"}
    result = run_scenario(scenario, out_root=str(tmp_path))
    assert result["status"] == "failed"
    assert "未知 emc_flow" in result["error"]
