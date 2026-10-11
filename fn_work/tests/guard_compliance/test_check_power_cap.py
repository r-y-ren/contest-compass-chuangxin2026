"""check_power_cap 镜像规则测试：功率上限红线（默认 0.0 dBm）+ 豁免审计。"""
from __future__ import annotations

from datetime import datetime, timezone

from src.guard_compliance.check_power_cap import check_power_cap


def _valid_waiver() -> dict:
    return {
        "id": "W-2026-001",
        "reason": "实验室屏蔽环境科研豁免",
        "approved_by": "合规负责人A",
    }


class TestBaseline:
    """① -10dBm 通过。"""

    def test_within_cap_passes(self):
        result = check_power_cap({"power_dbm": -10.0})
        assert result["status"] == "pass"
        assert result["cap_dbm"] == 0.0
        assert result["power_dbm"] == -10.0
        assert result["violations"] == []
        assert result["waiver_audit"] is None

    def test_boundary_equal_to_default_cap_passes(self):
        result = check_power_cap({"power_dbm": 0.0})
        assert result["status"] == "pass"
        assert result["violations"] == []


class TestOverLimit:
    """② +3dBm 违例，violations 指明功率与上限。"""

    def test_over_cap_violates_with_power_and_cap_in_message(self):
        result = check_power_cap({"power_dbm": 3.0})
        assert result["status"] == "violation"
        assert result["cap_dbm"] == 0.0
        assert result["power_dbm"] == 3.0
        assert result["waiver_audit"] is None
        assert len(result["violations"]) == 1
        message = result["violations"][0]
        assert "3.0" in message  # 指明实际功率
        assert "0.0" in message  # 指明上限


class TestWaiver:
    """③ 超限+有效豁免→waived 且审计条目含 id/reason/approved_by/时间戳。"""

    def test_valid_waiver_waives_with_full_audit_entry(self):
        result = check_power_cap({"power_dbm": 3.0}, waiver=_valid_waiver())
        assert result["status"] == "waived"
        assert result["power_dbm"] == 3.0
        assert result["cap_dbm"] == 0.0
        audit = result["waiver_audit"]
        assert isinstance(audit, dict)
        assert audit["id"] == "W-2026-001"
        assert audit["reason"] == "实验室屏蔽环境科研豁免"
        assert audit["approved_by"] == "合规负责人A"
        # 时间戳：ISO 8601 可解析、带时区、接近当前时刻
        stamped = datetime.fromisoformat(audit["timestamp"])
        assert stamped.tzinfo is not None
        now = datetime.now(timezone.utc)
        assert abs((now - stamped).total_seconds()) < 60
        # 超限事实仍留在 violations 中（豁免可审计、可追溯）
        assert any("功率超限" in v for v in result["violations"])

    # ④ 豁免缺键→仍 violation。

    def test_waiver_missing_key_still_violates(self):
        bad = {"id": "W-2026-002", "reason": "缺批准人"}
        result = check_power_cap({"power_dbm": 3.0}, waiver=bad)
        assert result["status"] == "violation"
        assert result["waiver_audit"] is None
        assert any("功率超限" in v for v in result["violations"])
        assert any("豁免凭证无效" in v for v in result["violations"])

    def test_waiver_empty_value_still_violates(self):
        bad = {"id": "W-2026-003", "reason": "", "approved_by": "合规负责人A"}
        result = check_power_cap({"power_dbm": 3.0}, waiver=bad)
        assert result["status"] == "violation"
        assert result["waiver_audit"] is None
        assert any("豁免凭证无效" in v for v in result["violations"])

    def test_waiver_irrelevant_when_within_cap(self):
        result = check_power_cap({"power_dbm": -10.0}, waiver=_valid_waiver())
        assert result["status"] == "pass"
        assert result["waiver_audit"] is None

    def test_waiver_cannot_cover_missing_power_dbm(self):
        # 输入形状错不属于功率超限违例，豁免不生效
        result = check_power_cap({}, waiver=_valid_waiver())
        assert result["status"] == "violation"
        assert result["waiver_audit"] is None


class TestCapOverride:
    """⑤ cap_dbm 覆盖为 -5 生效；覆盖为 +5 视为非法。

    口径（实现选择）：非法覆盖（高于默认 0.0 或非数值）一律回退默认 0.0 判定，
    且同时记违例说明——试图放松红线本身就是违例。
    """

    def test_tighter_cap_takes_effect(self):
        result = check_power_cap({"power_dbm": -7.0, "cap_dbm": -5.0})
        assert result["status"] == "pass"
        assert result["cap_dbm"] == -5.0

    def test_tighter_cap_causes_violation(self):
        result = check_power_cap({"power_dbm": -3.0, "cap_dbm": -5.0})
        assert result["status"] == "violation"
        assert result["cap_dbm"] == -5.0
        assert any("-5.0" in v for v in result["violations"])

    def test_looser_cap_rejected_judged_by_default(self):
        result = check_power_cap({"power_dbm": 3.0, "cap_dbm": 5.0})
        assert result["status"] == "violation"
        assert result["cap_dbm"] == 0.0  # 回退默认 0 判
        assert any("cap_dbm" in v and "非法" in v for v in result["violations"])
        assert any("功率超限" in v for v in result["violations"])  # 按 0.0 判仍超限

    def test_looser_cap_rejected_even_if_power_within_default(self):
        # 功率本身不超默认 0，但试图抬高上限仍记违例（口径：二选一中选"违例说明"）
        result = check_power_cap({"power_dbm": -3.0, "cap_dbm": 5.0})
        assert result["status"] == "violation"
        assert result["cap_dbm"] == 0.0
        assert any("cap_dbm" in v and "非法" in v for v in result["violations"])

    def test_non_numeric_cap_override_rejected(self):
        result = check_power_cap({"power_dbm": -3.0, "cap_dbm": "5"})
        assert result["status"] == "violation"
        assert result["cap_dbm"] == 0.0
        assert any("cap_dbm" in v and "非法" in v for v in result["violations"])


class TestMalformedInput:
    """⑥ 缺 power_dbm→violation（不抛异常，形状错走返回值）。"""

    def test_missing_power_dbm_violates(self):
        result = check_power_cap({"something_else": 1})
        assert result["status"] == "violation"
        assert result["power_dbm"] is None
        assert result["waiver_audit"] is None
        assert any("power_dbm" in v for v in result["violations"])

    def test_non_numeric_power_dbm_violates(self):
        result = check_power_cap({"power_dbm": "high"})
        assert result["status"] == "violation"
        assert any("power_dbm" in v for v in result["violations"])

    def test_non_dict_config_violates(self):
        result = check_power_cap(None)  # type: ignore[arg-type]
        assert result["status"] == "violation"
        assert any("power_config" in v for v in result["violations"])

    def test_result_schema_always_complete(self):
        # 任何路径下返回值六键齐全、类型正确（上层总闸可放心转拒）
        for result in (
            check_power_cap({"power_dbm": -10.0}),
            check_power_cap({"power_dbm": 3.0}),
            check_power_cap({"power_dbm": 3.0}, waiver=_valid_waiver()),
            check_power_cap({}),
        ):
            assert set(result) == {
                "status",
                "cap_dbm",
                "power_dbm",
                "violations",
                "waiver_audit",
            }
            assert result["status"] in ("pass", "violation", "waived")
            assert isinstance(result["violations"], list)
