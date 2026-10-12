"""load_scenario 对抗测试：合法往返/红线联动/schema 透传/坏 yaml/手写回退局限。"""
from __future__ import annotations

from pathlib import Path

import pytest

import src.load_scenario.load_scenario as load_mod
from src.load_scenario.load_scenario import load_scenario
from src.load_scenario.validate_scenario_schema import ScenarioError

REPO_ROOT = Path(__file__).resolve().parents[3]

# 完整合法场景：字段 + 信封键（bands/shielded_box/dut_scope 平铺形态）。
VALID_YAML = """\
style: TONE
fs: 2000000
freq_hz: 2440000000
power_dbm: -10
duration_s: 2.5
repeats: 2
backend: SIM
bands:
  - [2400, 2483.5]
shielded_box: true
dut_scope: self_built
"""


def _write(tmp_path, text, name="scenario.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_scenario_validate_full_valid_roundtrip(tmp_path):
    res = load_scenario(_write(tmp_path, VALID_YAML))
    # 规范化形状（normalize 口径）：小写归一/数值化/缺省填充。
    assert res["style"] == "tone"
    assert res["fs"] == 2000000.0
    assert res["freq_hz"] == 2440000000.0
    assert res["power_dbm"] == -10.0
    assert res["duration_s"] == 2.5
    assert res["repeats"] == 2
    assert res["backend"] == "sim"
    assert res["duty_cycle"] == 0.5  # 缺省
    assert res["judge_per_threshold"] == 0.10  # 缺省
    # 信封键落位（红线通过后原样带到顶层）。
    assert res["bands"] == [[2400, 2483.5]]
    assert res["shielded_box"] is True
    assert res["dut_scope"] == "self_built"


def test_scenario_validate_power_dbm_default_passes_guard(tmp_path):
    text = VALID_YAML.replace("power_dbm: -10\n", "")  # 缺省 -10 经红线
    res = load_scenario(_write(tmp_path, text))
    assert res["power_dbm"] == -10.0


def test_scenario_validate_missing_declarations_rejected(tmp_path):
    text = VALID_YAML.replace("shielded_box: true\n", "").replace(
        "dut_scope: self_built\n", ""
    )
    with pytest.raises(ScenarioError) as ei:
        load_scenario(_write(tmp_path, text))
    msg = str(ei.value)
    assert "shielded_box" in msg and "dut_scope" in msg
    assert "红线" in msg and "补齐" in msg  # 红线不可跳——提示补声明


def test_scenario_validate_wrong_declaration_values_rejected(tmp_path):
    text = VALID_YAML.replace("shielded_box: true", "shielded_box: false").replace(
        "dut_scope: self_built", "dut_scope: real_device"
    )
    with pytest.raises(ScenarioError) as ei:
        load_scenario(_write(tmp_path, text))
    msg = str(ei.value)
    assert "[declaration]" in msg and "self_built" in msg


def test_scenario_validate_schema_errors_passthrough(tmp_path):
    text = """\
style: laser
bogus_key: 1
bands:
  - [2400, 2483.5]
shielded_box: true
dut_scope: self_built
"""
    with pytest.raises(ScenarioError) as ei:
        load_scenario(_write(tmp_path, text))  # style 未知 + fs 缺失 + 未知键
    msg = str(ei.value)
    assert "laser" in msg and "fs 缺失" in msg
    assert "未知键: bogus_key" in msg
    assert "1." in msg and "3 处" in msg  # 编号清单透传


def test_scenario_validate_power_redline_rejected(tmp_path):
    text = VALID_YAML.replace("power_dbm: -10", "power_dbm: 3")  # schema 只判形状，红线拦 +3
    with pytest.raises(ScenarioError) as ei:
        load_scenario(_write(tmp_path, text))
    msg = str(ei.value)
    assert "[power]" in msg and "功率超限" in msg


def test_scenario_validate_band_redline_rejected(tmp_path):
    text = VALID_YAML.replace("- [2400, 2483.5]", "- [2400, 3000]")  # 越白名单
    with pytest.raises(ScenarioError) as ei:
        load_scenario(_write(tmp_path, text))
    assert "[band]" in str(ei.value)


def test_scenario_validate_missing_bands_rejected(tmp_path):
    text = VALID_YAML.replace("bands:\n  - [2400, 2483.5]\n", "")  # 缺节即红线违例
    with pytest.raises(ScenarioError) as ei:
        load_scenario(_write(tmp_path, text))
    assert "[band]" in str(ei.value)


def test_scenario_validate_bad_yaml_rejected(tmp_path):
    text = "style: tone\nfs: [1, 2\n"  # 未闭合流序列
    with pytest.raises(ScenarioError) as ei:
        load_scenario(_write(tmp_path, text))
    msg = str(ei.value)
    assert "YAML 解析失败" in msg and "行" in msg  # 行号尽力


def test_scenario_validate_missing_path_rejected(tmp_path):
    with pytest.raises(ScenarioError) as ei:
        load_scenario(str(tmp_path / "nope.yaml"))
    assert "不存在" in str(ei.value)
    with pytest.raises(ScenarioError):  # 非 str 路径同样拒
        load_scenario(42)


def test_scenario_validate_empty_and_non_mapping_docs_rejected(tmp_path):
    with pytest.raises(ScenarioError) as ei:
        load_scenario(_write(tmp_path, ""))  # 空文件 → None → 形状错
    assert "dict" in str(ei.value)
    with pytest.raises(ScenarioError) as ei2:
        load_scenario(_write(tmp_path, "- a\n- b\n"))  # 顶层列表 → 形状错
    assert "dict" in str(ei2.value)


def test_scenario_validate_fallback_flat_and_single_level_nesting(tmp_path, monkeypatch):
    monkeypatch.setattr(load_mod, "_yaml", None)  # 模拟无 yaml 库
    text = """\
style: tone
fs: 1000000
power_dbm: -10
declarations:
    shielded_box: true
    dut_scope: self_built
bands:
    - [2400, 2483.5]
"""
    res = load_scenario(_write(tmp_path, text, "scenario_fallback.yaml"))
    assert res["style"] == "tone" and res["fs"] == 1000000.0
    assert res["power_dbm"] == -10.0
    assert res["shielded_box"] is True and res["dut_scope"] == "self_built"
    assert res["bands"] == [[2400, 2483.5]]  # '- [a, b]' 二元组列表项


def test_scenario_validate_fallback_complex_structure_needs_pyyaml(tmp_path, monkeypatch):
    monkeypatch.setattr(load_mod, "_yaml", None)
    deep = "style: tone\nfs: 1000000\ndeep:\n    inner:\n        leaf: 1\n"
    with pytest.raises(ScenarioError) as ei:
        load_scenario(_write(tmp_path, deep, "deep.yaml"))
    assert "PyYAML" in str(ei.value) and "单层嵌套" in str(ei.value)
    inline = "style: tone\nfs: 1000000\nmeta: {a: 1}\n"
    with pytest.raises(ScenarioError) as ei2:
        load_scenario(_write(tmp_path, inline, "inline.yaml"))
    assert "PyYAML" in str(ei2.value)


def test_scenario_validate_fallback_orphan_indent_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(load_mod, "_yaml", None)
    text = "style: tone\n    fs: 1000000\n"  # 缩进行无宿主键
    with pytest.raises(ScenarioError) as ei:
        load_scenario(_write(tmp_path, text, "orphan.yaml"))
    assert "宿主键" in str(ei.value) and "PyYAML" in str(ei.value)


def test_scenario_validate_nested_declarations_form(tmp_path):
    # 声明键的替代形态：单层嵌套 declarations 块（与平铺形态等效）。
    text = VALID_YAML.replace(
        "shielded_box: true\ndut_scope: self_built\n",
        "declarations:\n  shielded_box: true\n  dut_scope: self_built\n",
    )
    res = load_scenario(_write(tmp_path, text))
    assert res["shielded_box"] is True and res["dut_scope"] == "self_built"


def test_scenario_validate_real_repo_guard_wiring_sanity():
    # 真仓库结构不变量：红线模块在位（load_scenario 的 guard_compliance 落点）。
    assert (REPO_ROOT / "fn_work" / "src" / "guard_compliance" / "guard_compliance.py").is_file()
