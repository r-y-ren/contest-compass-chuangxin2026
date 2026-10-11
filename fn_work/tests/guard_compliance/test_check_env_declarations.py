"""check_env_declarations 行为用例：环境与对象声明纯校验（屏蔽盒+仅自建链路）。"""
from src.guard_compliance.check_env_declarations import check_env_declarations


def test_both_declarations_present_and_legal_passes():
    result = check_env_declarations({"shielded_box": True, "dut_scope": "self_built"})
    assert result["status"] == "pass"
    assert result["violations"] == []


def test_missing_shielded_box_is_violation():
    result = check_env_declarations({"dut_scope": "self_built"})
    assert result["status"] == "violation"
    assert len(result["violations"]) == 1
    assert "shielded_box" in result["violations"][0]


def test_shielded_box_false_is_violation():
    result = check_env_declarations({"shielded_box": False, "dut_scope": "self_built"})
    assert result["status"] == "violation"
    assert len(result["violations"]) == 1
    assert "shielded_box" in result["violations"][0]
    assert "False" in result["violations"][0]


def test_dut_scope_real_drone_is_violation_red_line():
    result = check_env_declarations({"shielded_box": True, "dut_scope": "real_drone"})
    assert result["status"] == "violation"
    assert len(result["violations"]) == 1
    assert "dut_scope" in result["violations"][0]
    assert "real_drone" in result["violations"][0]


def test_empty_dict_yields_two_violations():
    result = check_env_declarations({})
    assert result["status"] == "violation"
    assert len(result["violations"]) == 2
    assert any("shielded_box" in v for v in result["violations"])
    assert any("dut_scope" in v for v in result["violations"])


def test_none_input_yields_two_violations_without_raising():
    result = check_env_declarations(None)
    assert result["status"] == "violation"
    assert len(result["violations"]) == 2
    assert any("shielded_box" in v for v in result["violations"])
    assert any("dut_scope" in v for v in result["violations"])


def test_required_field_lists_both_declaration_keys():
    result = check_env_declarations({"shielded_box": True, "dut_scope": "self_built"})
    assert sorted(result["required"]) == ["dut_scope", "shielded_box"]
