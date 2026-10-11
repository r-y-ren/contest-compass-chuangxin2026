"""guard_compliance 集成测试：三查聚合、豁免审计透传、条款化拒绝原因与不可跳过。"""
from __future__ import annotations

import inspect

import pytest

from src.guard_compliance.guard_compliance import guard_compliance


def _legal_config() -> dict:
    """三查全过的合法场景配置。"""
    return {
        "power": {"power_dbm": -10.0},
        "bands": [(2400.0, 2483.5)],
        "declarations": {"shielded_box": True, "dut_scope": "self_built"},
    }


def _valid_waiver() -> dict:
    return {
        "id": "W-2026-042",
        "reason": "实验室屏蔽环境科研豁免",
        "approved_by": "合规负责人A",
    }


def test_compliance_guard_all_three_checks_pass():
    """① 三查全过的合法场景 → pass。"""
    result = guard_compliance(_legal_config())
    assert result["status"] == "pass"
    assert result["violations"] == []
    assert result["waiver_audits"] == []
    assert result["declarations_echo"] == ["shielded_box", "dut_scope"]
    assert result["checks"]["power"]["status"] == "pass"
    assert result["checks"]["band"]["status"] == "pass"
    assert result["checks"]["declarations"]["status"] == "pass"


def test_compliance_guard_power_over_limit_rejected():
    """② 超功率（power_dbm=+3）→ rejected 且 violations 含 power 条款，其余条款不背锅。"""
    cfg = _legal_config()
    cfg["power"] = {"power_dbm": 3.0}
    result = guard_compliance(cfg)
    assert result["status"] == "rejected"
    assert result["checks"]["power"]["status"] == "violation"
    assert any(v.startswith("[power]") for v in result["violations"])
    assert not any(v.startswith("[band]") for v in result["violations"])
    assert not any(v.startswith("[declaration]") for v in result["violations"])


def test_compliance_guard_band_out_of_whitelist_rejected():
    """③ 越频段（900–928 MHz）→ rejected 且 violations 含 band 条款。"""
    cfg = _legal_config()
    cfg["bands"] = [(900.0, 928.0)]
    result = guard_compliance(cfg)
    assert result["status"] == "rejected"
    assert result["checks"]["band"]["status"] == "violation"
    assert any(v.startswith("[band]") for v in result["violations"])
    assert not any(v.startswith("[power]") for v in result["violations"])
    assert not any(v.startswith("[declaration]") for v in result["violations"])


def test_compliance_guard_missing_declarations_rejected():
    """④ 缺声明（无 declarations 键）→ rejected 且 violations 含 declaration 条款。"""
    cfg = _legal_config()
    del cfg["declarations"]
    result = guard_compliance(cfg)
    assert result["status"] == "rejected"
    assert result["checks"]["declarations"]["status"] == "violation"
    assert any(v.startswith("[declaration]") for v in result["violations"])
    assert not any(v.startswith("[power]") for v in result["violations"])
    assert not any(v.startswith("[band]") for v in result["violations"])
    assert result["declarations_echo"] == []


def test_compliance_guard_valid_waiver_passes_with_audit():
    """⑤ 有效豁免的超功率 → pass 且 waiver_audits 非空（审计条目透传）。"""
    cfg = _legal_config()
    cfg["power"] = {"power_dbm": 3.0, "waiver": _valid_waiver()}
    result = guard_compliance(cfg)
    assert result["status"] == "pass"
    assert result["violations"] == []
    assert result["checks"]["power"]["status"] == "waived"
    assert len(result["waiver_audits"]) == 1
    audit = result["waiver_audits"][0]
    assert audit["id"] == "W-2026-042"
    assert audit["reason"] == "实验室屏蔽环境科研豁免"
    assert audit["approved_by"] == "合规负责人A"
    assert audit["timestamp"]


def test_compliance_guard_all_three_clauses_violate_together():
    """⑥ 三查同时坏 → rejected 且 violations 三条款齐。"""
    result = guard_compliance(
        {
            "power": {"power_dbm": 3.0},
            "bands": [(900.0, 928.0)],
        }
    )
    assert result["status"] == "rejected"
    assert any(v.startswith("[power]") for v in result["violations"])
    assert any(v.startswith("[band]") for v in result["violations"])
    assert any(v.startswith("[declaration]") for v in result["violations"])


def test_compliance_guard_no_skip_path():
    """⑦ 无跳过路径：函数签名仅收 config 一个参数；任何非法 config 形状一律拒绝且不抛出。"""
    # 签名仅 config 一个参数，无 *args/**kwargs/默认开关——不存在绕过参数
    params = list(inspect.signature(guard_compliance).parameters.values())
    assert [p.name for p in params] == ["config"]
    assert all(
        p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for p in params
    )

    # 各类非法/残缺 config 全部拒绝，绝不抛出
    bad_configs = [
        {},
        None,
        "not-a-config",
        42,
        {"power": {}},
        {"bands": []},
        {"declarations": {}},
        {"power": {"power_dbm": 3.0}, "bands": [(900.0, 928.0)]},
    ]
    for bad in bad_configs:
        result = guard_compliance(bad)
        assert result["status"] == "rejected", f"非法配置未被拒绝: {bad!r}"
        assert result["violations"], f"拒绝原因清单为空: {bad!r}"


# ---------------------------------------------------------------------------
# 缺陷回归（对抗审查确认的触发输入，逐条锁死）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_bands", [None, "900-928", 42], ids=["None", "str", "int"])
def test_defect_4_top_level_band_shape_violation_carries_original_value(bad_bands):
    """缺陷#4：bands 整体形状错时，总闸顶层违例文案必须携带原值 repr。"""
    cfg = _legal_config()
    cfg["bands"] = bad_bands
    result = guard_compliance(cfg)
    assert result["status"] == "rejected"
    assert result["checks"]["band"]["status"] == "violation"
    band_violations = [v for v in result["violations"] if v.startswith("[band]")]
    assert band_violations, "缺 [band] 条款违例"
    assert any(repr(bad_bands) in v for v in band_violations)


def test_defect_4_long_original_value_repr_truncated_to_60_chars():
    """缺陷#4：超长原值的 repr 截断到 60 字符（携带但不无限长）。"""
    cfg = _legal_config()
    cfg["bands"] = int("9" * 100)  # repr 为 100 位数字，无引号干扰
    result = guard_compliance(cfg)
    band_violations = [v for v in result["violations"] if v.startswith("[band]")]
    assert band_violations
    assert "9" * 60 in band_violations[0]  # 前 60 字符保留
    assert "9" * 61 not in band_violations[0]  # 第 61 位起截断


def test_defect_1_nan_power_rejected_end_to_end():
    """端到端：NaN 功率过总闸 → rejected 且 [power] 条款在，其余条款不背锅。"""
    cfg = _legal_config()
    cfg["power"] = {"power_dbm": float("nan")}
    result = guard_compliance(cfg)
    assert result["status"] == "rejected"
    assert result["checks"]["power"]["status"] == "violation"
    assert result["checks"]["power"]["waiver_audit"] is None
    assert any(
        v.startswith("[power]") and "功率值非法" in v for v in result["violations"]
    )
    assert not any(v.startswith("[band]") for v in result["violations"])
    assert not any(v.startswith("[declaration]") for v in result["violations"])


def test_defect_6_inf_power_with_valid_waiver_still_rejected_end_to_end():
    """端到端：±inf 功率即使携带完整豁免凭证也不得 waived（形状错不可豁免）。"""
    cfg = _legal_config()
    cfg["power"] = {"power_dbm": float("inf"), "waiver": _valid_waiver()}
    result = guard_compliance(cfg)
    assert result["status"] == "rejected"
    assert result["checks"]["power"]["status"] == "violation"
    assert result["waiver_audits"] == []  # 不得透传任何豁免审计条目
    assert any(
        v.startswith("[power]") and "功率值非法" in v for v in result["violations"]
    )
