"""check_power_cap 镜像规则测试：功率上限红线（默认 0.0 dBm）+ 豁免审计。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

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


# ---------------------------------------------------------------------------
# 缺陷回归（对抗审查确认的触发输入，逐条锁死）
# ---------------------------------------------------------------------------


class TestDefect1And6IllegalPowerValues:
    """缺陷#1/#6：NaN/±inf/bool/字符串/None 的 power_dbm 全部违例且不可豁免。

    NaN 与任何上限比较恒为 False，旧实现据此放行（红线绕过）；±inf 走
    "功率超限"路径可被豁免凭证豁免。修后统一归入形状错，先行拒绝。
    """

    @pytest.mark.parametrize(
        "bad_power",
        [
            float("nan"),
            float("inf"),
            float("-inf"),
            True,
            False,
            "high",
            None,
        ],
        ids=["nan", "inf", "-inf", "True", "False", "str", "None"],
    )
    def test_defect_1_illegal_power_value_is_unwaivable_violation(self, bad_power):
        result = check_power_cap({"power_dbm": bad_power})
        assert result["status"] == "violation"
        assert result["waiver_audit"] is None
        assert any("功率值非法" in v for v in result["violations"])
        assert any("power_dbm" in v for v in result["violations"])

    @pytest.mark.parametrize(
        "bad_power",
        [float("nan"), float("inf"), float("-inf")],
        ids=["nan", "inf", "-inf"],
    )
    def test_defect_6_inf_power_not_waived_even_with_valid_waiver(self, bad_power):
        # ±inf/NaN 属形状错，即使携带完整有效豁免凭证也不得 waived
        result = check_power_cap({"power_dbm": bad_power}, waiver=_valid_waiver())
        assert result["status"] == "violation"
        assert result["waiver_audit"] is None
        assert any("功率值非法" in v for v in result["violations"])


class TestDefect2CapOverrideNonFinite:
    """缺陷#2：cap_dbm=NaN/inf/+5/True → 回退默认 0.0 判定且记违例。

    NaN 覆盖曾被当"合法收紧"采纳，之后任意功率与 NaN 比较恒 False →
    全部放行。修后非法覆盖一律回退默认并记违例（文案区分"试图放松
    红线"与"非法覆盖值"）；合法收紧 cap_dbm=-5 仍生效。
    """

    @pytest.mark.parametrize(
        "bad_cap",
        [float("nan"), float("inf"), 5, True],
        ids=["nan", "inf", "+5", "True"],
    )
    def test_defect_2_illegal_cap_falls_back_to_default_with_violation(
        self, bad_cap
    ):
        result = check_power_cap({"power_dbm": 3.0, "cap_dbm": bad_cap})
        assert result["status"] == "violation"
        assert result["cap_dbm"] == 0.0  # 一律回退默认 0.0 判
        assert any("cap_dbm" in v and "非法" in v for v in result["violations"])
        assert any("功率超限" in v for v in result["violations"])  # 按 0.0 判仍超限

    def test_defect_2_nan_cap_cannot_release_any_power(self):
        # 对抗复现：NaN 上限 + 1e9 功率，旧实现 1e9 > NaN 恒 False → pass
        result = check_power_cap({"power_dbm": 1e9, "cap_dbm": float("nan")})
        assert result["status"] == "violation"
        assert result["cap_dbm"] == 0.0
        assert any("非法" in v for v in result["violations"])

    def test_defect_2_nan_cap_with_within_limit_power_still_violates(self):
        # 功率本身合规也须暴露"非法覆盖"事实，不得静默吞掉
        result = check_power_cap({"power_dbm": -3.0, "cap_dbm": float("nan")})
        assert result["status"] == "violation"
        assert result["cap_dbm"] == 0.0
        assert any("非法覆盖值" in v for v in result["violations"])

    def test_defect_2_tighter_cap_minus_5_still_takes_effect(self):
        # 合法收紧路径不受影响：-5 上限生效
        result = check_power_cap({"power_dbm": -7.0, "cap_dbm": -5.0})
        assert result["status"] == "pass"
        assert result["cap_dbm"] == -5.0
        assert result["violations"] == []


class TestDefect3WaiverWhitespaceValues:
    """缺陷#3：豁免三键值为纯空白（" "/"\\t"/"\\n"）不得判有效豁免。"""

    @pytest.mark.parametrize("blank", [" ", "\t", "\n"], ids=["space", "tab", "newline"])
    def test_defect_3_whitespace_waiver_value_is_invalid(self, blank):
        bad = {"id": "W-2026-009", "reason": blank, "approved_by": "合规负责人A"}
        result = check_power_cap({"power_dbm": 3.0}, waiver=bad)
        assert result["status"] == "violation"
        assert result["waiver_audit"] is None
        assert any("豁免凭证无效" in v for v in result["violations"])
        assert any("功率超限" in v for v in result["violations"])

    def test_defect_3_non_string_waiver_value_is_invalid(self):
        # None/非字符串（如数字 id）同样无效
        bad = {"id": 123, "reason": "实验室屏蔽环境科研豁免", "approved_by": "合规负责人A"}
        result = check_power_cap({"power_dbm": 3.0}, waiver=bad)
        assert result["status"] == "violation"
        assert result["waiver_audit"] is None
        assert any("豁免凭证无效" in v for v in result["violations"])

    def test_defect_3_normal_waiver_still_waives(self):
        # 正常非空白豁免仍走 waived（修复不得误伤合法豁免）
        result = check_power_cap({"power_dbm": 3.0}, waiver=_valid_waiver())
        assert result["status"] == "waived"
        assert result["waiver_audit"] is not None
        assert result["waiver_audit"]["id"] == "W-2026-001"
