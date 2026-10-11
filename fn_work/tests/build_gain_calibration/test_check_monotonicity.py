"""check_monotonicity 镜像规则测试：非降校验（容差参数化）+ 形状错不抛异常。"""
from __future__ import annotations

import pytest

from src.build_gain_calibration.check_monotonicity import check_monotonicity


def _is_shape(result: list) -> bool:
    """形状错断言：恰好一条，error='shape'，detail 为非空字符串。"""
    return (
        isinstance(result, list)
        and len(result) == 1
        and isinstance(result[0], dict)
        and result[0].get("error") == "shape"
        and isinstance(result[0].get("detail"), str)
        and result[0]["detail"] != ""
    )


class TestMonotone:
    """① 正常递增→空违例列表。"""

    def test_strictly_increasing_passes(self):
        assert check_monotonicity([("L1", 0.0), ("L2", 5.0), ("L3", 10.5)]) == []

    def test_numeric_steps_increasing_passes(self):
        assert check_monotonicity([(0, -10), (1, -3), (2, 4)]) == []


class TestDropViolation:
    """② 中点下降→1 条违例，含 index/档位/本点/前点/降幅。"""

    def test_midpoint_drop_yields_single_violation(self):
        points = [("L1", 0.0), ("L2", 10.0), ("L3", 7.0), ("L4", 12.0)]
        result = check_monotonicity(points)
        assert len(result) == 1
        violation = result[0]
        assert set(violation) == {
            "index",
            "gain_step",
            "power_dbm",
            "prev_power_dbm",
            "drop_db",
        }
        assert violation["index"] == 2
        assert violation["gain_step"] == "L3"
        assert violation["power_dbm"] == 7.0
        assert violation["prev_power_dbm"] == 10.0
        assert violation["drop_db"] == pytest.approx(3.0)

    def test_multiple_drops_yield_violation_per_point(self):
        result = check_monotonicity([("a", 5.0), ("b", 3.0), ("c", 1.0)])
        assert [v["index"] for v in result] == [1, 2]
        assert result[0]["drop_db"] == pytest.approx(2.0)
        assert result[1]["drop_db"] == pytest.approx(2.0)

    def test_default_tolerance_zero_catches_tiny_drop(self):
        result = check_monotonicity([("a", 1.0), ("b", 0.9)])
        assert len(result) == 1
        assert result[0]["drop_db"] == pytest.approx(0.1)


class TestTolerance:
    """③ 容差内微降不违例；④ 恰好相等不违例。"""

    def test_drop_within_tolerance_passes(self):
        assert check_monotonicity([("a", 10.0), ("b", 9.6)], tolerance_db=0.5) == []

    def test_drop_exactly_equal_to_tolerance_passes(self):
        assert check_monotonicity([("a", 10.0), ("b", 9.5)], tolerance_db=0.5) == []

    def test_drop_beyond_tolerance_violates(self):
        result = check_monotonicity([("a", 10.0), ("b", 9.4)], tolerance_db=0.5)
        assert len(result) == 1
        assert result[0]["drop_db"] == pytest.approx(0.6)

    def test_equal_powers_pass_without_tolerance(self):
        assert check_monotonicity([("a", 5.0), ("b", 5.0), ("c", 5.0)]) == []


class TestShapeErrors:
    """⑤⑥ 形状错：空序列 / 元素非二元组 / 功率 NaN、inf、bool、字符串等。"""

    def test_empty_sequence_returns_shape_violation(self):
        result = check_monotonicity([])
        assert _is_shape(result)

    @pytest.mark.parametrize(
        "bad_power",
        [
            float("nan"),
            float("inf"),
            float("-inf"),
            True,
            False,
            "5.0",
            None,
            [5.0],
        ],
    )
    def test_invalid_power_returns_shape_violation(self, bad_power):
        assert _is_shape(check_monotonicity([("a", 1.0), ("b", bad_power)]))

    def test_invalid_power_at_first_point_returns_shape_violation(self):
        assert _is_shape(check_monotonicity([("a", float("nan")), ("b", 2.0)]))

    @pytest.mark.parametrize(
        "bad_element",
        [("a", 1.0, "extra"), ("a",), "ab", 5.0, None, {"a": 1.0}],
    )
    def test_non_pair_element_returns_shape_violation(self, bad_element):
        assert _is_shape(check_monotonicity([("a", 1.0), bad_element]))

    def test_points_not_a_sequence_returns_shape_violation(self):
        assert _is_shape(check_monotonicity(None))
        assert _is_shape(check_monotonicity(7))

    def test_invalid_tolerance_returns_shape_violation(self):
        assert _is_shape(check_monotonicity([("a", 1.0)], tolerance_db=float("nan")))
        assert _is_shape(check_monotonicity([("a", 1.0)], tolerance_db=True))


class TestSequenceOrderOnly:
    """⑦ 乱序档位（字符串混数值键）：只按序列顺序判，不按键排序。"""

    def test_unsorted_string_steps_with_increasing_power_passes(self):
        # 若实现按档位键排序（a,b,c），功率将变为 3,2,1 而违例；正确行为是按序列顺序判。
        assert check_monotonicity([("c", 1.0), ("b", 2.0), ("a", 3.0)]) == []

    def test_mixed_type_steps_judged_by_sequence_order(self):
        # str 与 int 键混排无法排序；序列顺序功率递增→空。
        assert check_monotonicity([("high", 1.0), (2, 2.0), ("low", 3.0)]) == []

    def test_mixed_type_steps_decreasing_in_sequence_order_violates(self):
        result = check_monotonicity([("low", 3.0), (2, 2.0), ("high", 1.0)])
        assert [v["index"] for v in result] == [1, 2]
        assert result[0]["gain_step"] == 2
        assert result[1]["gain_step"] == "high"

    def test_bool_gain_step_is_transparent_label(self):
        # 档位仅作标签透传，不参与数值判定。
        assert check_monotonicity([(False, 1.0), (True, 2.0)]) == []


class TestBoundaries:
    """边界补充：单点、int 功率、bool 边界值。"""

    def test_single_point_passes(self):
        assert check_monotonicity([("L0", -5.0)]) == []

    def test_integer_powers_pass(self):
        assert check_monotonicity([(1, 1), (2, 2), (3, 2)]) == []

    def test_violation_never_raises_on_any_input(self):
        # 不抛异常契约：各种垃圾输入都返回列表而非抛出。
        for bad in ([], [1, 2], [("a",)], [("a", True)], "xy", None):
            assert isinstance(check_monotonicity(bad), list)


class TestDefectB2Regression:
    """B2 对抗审查缺陷回归（高#1 超大 int 功率 / 低#14 负容差）：一律不抛异常、按形状违例返回。"""

    def test_defect_b2_huge_int_power_returns_shape_violation(self):
        # 10**400 级大整数功率：int→float 转换溢出须按 shape 违例返回而非 OverflowError。
        result = check_monotonicity([("a", 1), ("b", 10**400)])
        assert _is_shape(result)
        assert "超大" in result[0]["detail"]

    def test_defect_b2_huge_int_power_at_first_point_returns_shape_violation(self):
        result = check_monotonicity([("a", 10**400), ("b", 2.0)])
        assert _is_shape(result)
        assert "超大" in result[0]["detail"]

    def test_defect_b2_huge_int_powers_never_raise(self):
        for points in ([("a", 10**400)], [("a", 10**400), ("b", 10**400)], [(1, 10**400), (2, 1)]):
            assert isinstance(check_monotonicity(points), list)

    def test_defect_b2_negative_tolerance_returns_shape_violation(self):
        # 负容差：shape 违例且文案注明容差须非负。
        result = check_monotonicity([("a", 1.0), ("b", 2.0)], tolerance_db=-1.0)
        assert _is_shape(result)
        assert "非负" in result[0]["detail"]

    def test_defect_b2_negative_zero_tolerance_treated_as_zero(self):
        # -0.0 视为 0：本身不触发形状违例；等功率不违例，微降仍按 0 容差判违例。
        assert check_monotonicity([("a", 1.0), ("b", 1.0)], tolerance_db=-0.0) == []
        result = check_monotonicity([("a", 1.0), ("b", 0.5)], tolerance_db=-0.0)
        assert len(result) == 1
        assert result[0]["drop_db"] == pytest.approx(0.5)
