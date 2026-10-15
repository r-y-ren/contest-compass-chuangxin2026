"""run_scenario 的 EMC 场景信封通路单测（走查环 F1 修复配套，2026-10-14）：
scenario_type='emc' 的场景携 _EMC_PARAM_KEYS（emc_flow/span_hz/detector 等
schema 不在册的流程键）经 _normalize_scenario_object 信封摘出落位——校验通过
且 execute_scenario 按 emc_flow 分派真跑；非 emc 场景不摘（未知键拒绝不放松）。

R89 收官追加（2026-10-15）：conduction/radiation 两流程端到端 report.md 断言
（run_scenario 真跑→运行目录报告分节标题/表行/判定行）+ 报告结果对象 'emc' 段
flow 标签贯通见证（_report_payload 三形状映射改造点①验收）。
"""
import json
import os
import re

import pytest

import src.run_demo.run_demo as rd_mod
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


# ---------- R89 收官：三形状映射端到端（conduction/radiation report.md 断言） ----------


def _capture_report_payload(monkeypatch) -> dict:
    """包装 rd.build_report 截取报告结果对象（其余管线全真）。

    _report_payload 的报告结果对象只进 build_report 不落盘 result.json（落盘的
    scenario_result 为 sim 编排原始形状），flow 标签断言就近在调用口截取——
    包装透传真 build_report，运行全流程不受影响。
    """
    captured: dict = {}
    real_build = rd_mod.build_report

    def _wrap(run_dir, payload):
        captured["payload"] = payload
        return real_build(run_dir, payload)

    monkeypatch.setattr(rd_mod, "build_report", _wrap)
    return captured


def _read_text(run_dir: str, name: str) -> str:
    with open(os.path.join(run_dir, name), encoding="utf-8") as handle:
        return handle.read()


def test_emc_end_to_end_conduction_report_section_and_flow_label(tmp_path, monkeypatch):
    """R89①：conduction 端到端实跑——report.md 含「## EMC 传导摸底（模拟）」标题+
    读数/裕量表行（limit_line_dbmv 判定面：四列全出值非「未判定」）+passed 判定行
    +simulated=True 行；报告结果对象 'emc' 段 flow=='conduction'（readings 原生
    直传，无 points 适配键）；result.json scenario_result 内层为 readings 形状。"""
    captured = _capture_report_payload(monkeypatch)
    scenario = {
        **_BASE_EMC,
        "emc_flow": "conduction",
        "freq_hz": 100.0e6,
        "limit_line_dbmv": 60.0,  # 裕量判定面（margin_db/passed 出值）
    }
    result = run_scenario(scenario, out_root=str(tmp_path))
    assert result["status"] == "completed" and result["exit_code"] == 0
    report = _read_text(result["run_dir"], "report.md")
    assert "## EMC 传导摸底（模拟）" in report
    assert "> 频点 (Hz) | 读数 (dBm) | 换算 (dBµV) | 裕量 (dB)" in report
    # 读数/裕量表行：单点 100MHz、四列全数值（margin 非「未判定（未提供限值线）」）
    assert re.search(
        r"^> 100000000\.0 Hz \| -\d+\.\d+ dBm \| \d+\.\d+ dBµV \| \d+\.\d+ dB$",
        report,
        re.MULTILINE,
    )
    assert "> passed：合规（演示口径，非认证）" in report  # 限值线在场→判定出值
    assert "> simulated = True（本段全部读数带模拟标记）" in report
    # 报告结果对象：readings 原生直传+flow 标签（R89 三形状映射①分支）
    emc = captured["payload"]["emc"]
    assert emc["flow"] == "conduction"
    assert isinstance(emc["readings"], list) and emc["readings"]
    assert "points" not in emc  # 传导原生形状：无 readings←points 适配
    assert emc["passed"] is True and emc["simulated"] is True
    # result.json 落盘形态：scenario_result 内层为 sim 编排原生 readings 形状
    result_json = json.loads(_read_text(result["run_dir"], "result.json"))
    inner = result_json["scenario_result"]["result"]
    assert isinstance(inner["readings"], list) and inner["readings"]
    assert inner["simulated"] is True


def test_emc_end_to_end_radiation_report_section_and_flow_label(tmp_path, monkeypatch):
    """R89②：radiation 端到端实跑——report.md 含「## EMC 辐射摸底（模拟）」标题+
    谱图表行（有界渲染）+洁净度结论行（in_band_peaks/out_of_band_ratio_db）+
    补偿区（compensated+注记+不确定度）；报告结果对象 'emc' 段 flow=='radiation'
    （spectrum/cleanliness/补偿注记直传）；result.json scenario_result 内层为
    spectrum 形状。"""
    captured = _capture_report_payload(monkeypatch)
    scenario = {
        **_BASE_EMC,
        "emc_flow": "radiation",
        "center_hz": 100.0e6,
        "span_hz": 1.0e6,
    }
    result = run_scenario(scenario, out_root=str(tmp_path))
    assert result["status"] == "completed" and result["exit_code"] == 0
    report = _read_text(result["run_dir"], "report.md")
    assert "## EMC 辐射摸底（模拟）" in report
    assert "> 频点 (Hz) | 功率 (dB)" in report  # 谱图表头
    assert re.search(
        r"^> \d+\.\d+ Hz \| -\d+\.\d+ dB$", report, re.MULTILINE
    )  # 谱表行（频点/功率两列出值）
    # 洁净度结论行：三指标+criterion（值域宽断言——数值读回自本 run，不虚构对照）
    assert re.search(r"^> 带内峰簇数（in_band_peaks）：\d+$", report, re.MULTILINE)
    assert re.search(
        r"^> 带外杂散比（out_of_band_ratio_db）：-?\d+\.\d+ dB$", report, re.MULTILINE
    )
    assert "峰判定阈值（peak_threshold_db）" in report
    assert "简单阈值判据（演示口径）" in report  # criterion 判据文字
    # 补偿区：本场景未给 compensation_tables→未补偿+注记+不确定度三件在位
    assert "> 补偿：未补偿（compensated=False）" in report
    assert "> scenario 未提供 compensation_tables" in report
    assert "> 谱不确定度（uncertainty_db）：" in report
    assert "> simulated = True（本段全部读数带模拟标记）" in report
    # 报告结果对象：spectrum 直传+flow 标签（R89 三形状映射②分支）
    emc = captured["payload"]["emc"]
    assert emc["flow"] == "radiation"
    assert isinstance(emc["spectrum"], dict)
    assert emc["spectrum"]["freqs"] and emc["spectrum"]["power_db"]
    assert isinstance(emc["cleanliness"], dict)
    assert "in_band_peaks" in emc["cleanliness"]
    assert "out_of_band_ratio_db" in emc["cleanliness"]
    assert "readings" not in emc and "points" not in emc  # 辐射原生形状无他系键
    assert emc["simulated"] is True
    # result.json 落盘形态：scenario_result 内层为 spectrum 形状
    result_json = json.loads(_read_text(result["run_dir"], "result.json"))
    inner = result_json["scenario_result"]["result"]
    assert isinstance(inner["spectrum"], dict) and inner["spectrum"]["freqs"]
    assert inner["simulated"] is True


def test_emc_end_to_end_sweep_title_no_longer_conduction(tmp_path, monkeypatch):
    """R89③（口径缝回归）：sweep 端到端实跑——points→readings 适配保留+flow='sweep'
    标签补上后，report.md 标题为「## EMC 步进扫频（模拟）」而非旧口径缝下形状回推
    误挂的「## EMC 传导摸底（模拟）」；报告结果对象 readings←points 适配与 points
    原键并立在案。"""
    captured = _capture_report_payload(monkeypatch)
    scenario = {**_BASE_EMC, "emc_flow": "sweep", "band": "cispr_b", "step_hz": 5e6}
    result = run_scenario(scenario, out_root=str(tmp_path))
    assert result["status"] == "completed" and result["exit_code"] == 0
    report = _read_text(result["run_dir"], "report.md")
    assert "## EMC 步进扫频（模拟）" in report
    assert "## EMC 传导摸底（模拟）" not in report  # 口径缝闭合（不再误挂传导标题）
    assert "换算 (dBµV)" not in report  # 不落传导表头/裕量列
    emc = captured["payload"]["emc"]
    assert emc["flow"] == "sweep"
    assert emc["readings"] == emc["points"]  # 既有 points→readings 适配保留
    assert isinstance(emc["points"], list) and emc["points"]
