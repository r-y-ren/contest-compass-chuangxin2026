"""plan_ladder_steps 对抗用例：GB 缺省展开、0dBm 红线截断、custom 覆盖与参数域拒绝。"""
import pytest

from src.run_power_ladder.plan_ladder_steps import PlanError, plan_ladder_steps


def test_gb_default_link_zero_two_rungs_then_redline():
    # GB 缺省：起始 link−5=−5、步 5；0.0 恰过红线不截，+5 档被截断（索引 2）
    result = plan_ladder_steps(0.0)
    assert result == {
        "steps": [
            {"step": 0, "target_db": -5.0, "relative_db": -5.0, "note": "gb42590"},
            {"step": 1, "target_db": 0.0, "relative_db": 0.0, "note": "gb42590"},
        ],
        "truncated_at": 2,
        "redline_hit": True,
        "note": "gb42590",
    }


def test_gb_link_minus_10_ladder_to_zero():
    # link=−10 → 起始 −15：−15/−10/−5/0 共 4 档，+5 档（索引 4）触红线截断
    result = plan_ladder_steps(-10.0)
    assert [s["target_db"] for s in result["steps"]] == [-15.0, -10.0, -5.0, 0.0]
    assert [s["relative_db"] for s in result["steps"]] == [-5.0, 0.0, 5.0, 10.0]
    assert [s["step"] for s in result["steps"]] == [0, 1, 2, 3]
    assert result["truncated_at"] == 4
    assert result["redline_hit"] is True
    assert result["note"] == "gb42590"


def test_gb_link_positive_rejected_as_abnormal_link_power():
    # 链路功率本身高于 0dBm 红线即异常——直接拒（GB 口径）
    with pytest.raises(PlanError):
        plan_ladder_steps(1.0)


def test_gb_default_start_above_redline_rejected():
    # link=+6 → GB 起始 = +1 > 0：同为 PlanError
    with pytest.raises(PlanError):
        plan_ladder_steps(6.0)


def test_custom_exact_stop_off_grid_lands_on_stop():
    # start −20 / step 10 / stop −5：网格(−20,−10,0)未命中 −5，最后档钳位恰到 −5
    result = plan_ladder_steps(-10.0, {"start_db": -20.0, "step_db": 10.0, "stop_db": -5.0})
    assert [s["target_db"] for s in result["steps"]] == [-20.0, -10.0, -5.0]
    assert result["truncated_at"] is None
    assert result["redline_hit"] is False
    assert result["note"] == "custom"


def test_custom_stop_off_grid_last_rung_never_exceeds_stop():
    # stop=−7 不在网格上：最后档恰为 −7，任何档不越 stop
    result = plan_ladder_steps(-10.0, {"start_db": -20.0, "step_db": 10.0, "stop_db": -7.0})
    targets = [s["target_db"] for s in result["steps"]]
    assert targets == [-20.0, -10.0, -7.0]
    assert all(t <= -7.0 for t in targets)
    assert result["redline_hit"] is False


def test_custom_stop_on_grid_single_terminal_rung():
    # stop 命中网格：终档恰为 stop，无重复档
    result = plan_ladder_steps(-10.0, {"start_db": -20.0, "step_db": 5.0, "stop_db": -5.0})
    assert [s["target_db"] for s in result["steps"]] == [-20.0, -15.0, -10.0, -5.0]
    assert result["truncated_at"] is None
    assert result["redline_hit"] is False


def test_custom_stop_above_redline_truncates_at_zero():
    # stop_db>0：红线优先于 stop，截断在 0 红线（不输出 +5 档）
    result = plan_ladder_steps(-10.0, {"start_db": -20.0, "step_db": 10.0, "stop_db": 5.0})
    assert [s["target_db"] for s in result["steps"]] == [-20.0, -10.0, 0.0]
    assert result["truncated_at"] == 3
    assert result["redline_hit"] is True
    assert result["note"] == "custom"


def test_custom_without_stop_hits_redline():
    result = plan_ladder_steps(-10.0, {"start_db": -4.0, "step_db": 5.0})
    assert [s["target_db"] for s in result["steps"]] == [-4.0]
    assert result["truncated_at"] == 1
    assert result["redline_hit"] is True


def test_gb_max_steps_default_cap_30():
    # 深阶梯 30 档内到不了红线：恰 30 档封顶（防失控），非红线截断
    result = plan_ladder_steps(-1000.0)
    targets = [s["target_db"] for s in result["steps"]]
    assert len(targets) == 30
    assert targets[0] == -1005.0
    assert targets[-1] == -860.0  # −1005 + 29×5
    assert result["truncated_at"] is None
    assert result["redline_hit"] is False


def test_custom_max_steps_cap_before_redline():
    result = plan_ladder_steps(-10.0, {"start_db": -30.0, "step_db": 1.0, "max_steps": 4})
    assert [s["target_db"] for s in result["steps"]] == [-30.0, -29.0, -28.0, -27.0]
    assert result["truncated_at"] is None
    assert result["redline_hit"] is False
    assert result["note"] == "custom"


def test_max_steps_only_keeps_gb_note():
    # 仅覆盖 max_steps 不触发自定义，仍为 GB 口径
    result = plan_ladder_steps(-10.0, {"max_steps": 3})
    assert [s["target_db"] for s in result["steps"]] == [-15.0, -10.0, -5.0]
    assert result["note"] == "gb42590"
    assert result["truncated_at"] is None
    assert result["redline_hit"] is False


def test_params_none_equals_omitted():
    assert plan_ladder_steps(0.0, None) == plan_ladder_steps(0.0)


def test_int_inputs_accepted():
    result = plan_ladder_steps(-10, {"start_db": -20, "step_db": 10, "stop_db": -5})
    assert [s["target_db"] for s in result["steps"]] == [-20.0, -10.0, -5.0]


@pytest.mark.parametrize("bad_step", [0, 0.0, -3.0, float("nan"), float("inf"), True])
def test_invalid_step_rejected(bad_step):
    # 步长 0/负/NaN/±inf/bool 一律 ValueError
    with pytest.raises(ValueError):
        plan_ladder_steps(-10.0, {"step_db": bad_step})


@pytest.mark.parametrize("bad_link", [float("nan"), float("inf"), True, False, "0"])
def test_invalid_link_power_rejected(bad_link):
    # link 功率域错：NaN/±inf/bool/非数值一律 ValueError
    with pytest.raises(ValueError):
        plan_ladder_steps(bad_link)


@pytest.mark.parametrize("bad_max", [0, -1, True, 2.5, "30", None])
def test_invalid_max_steps_rejected(bad_max):
    with pytest.raises(ValueError):
        plan_ladder_steps(-10.0, {"max_steps": bad_max})


def test_custom_start_above_redline_rejected():
    with pytest.raises(PlanError):
        plan_ladder_steps(-10.0, {"start_db": 1.0, "step_db": 5.0})


def test_stop_below_start_rejected():
    with pytest.raises(ValueError):
        plan_ladder_steps(-10.0, {"start_db": -10.0, "step_db": 5.0, "stop_db": -30.0})


def test_plan_error_is_distinct_domain_exception():
    # PlanError 为本模块自定义异常：是 Exception 但不是 ValueError
    assert issubclass(PlanError, Exception)
    assert not issubclass(PlanError, ValueError)


def test_result_contract_shape_and_rung_fields():
    result = plan_ladder_steps(0.0)
    assert set(result.keys()) == {"steps", "truncated_at", "redline_hit", "note"}
    for rung in result["steps"]:
        assert set(rung.keys()) == {"step", "target_db", "relative_db", "note"}
        assert isinstance(rung["step"], int) and not isinstance(rung["step"], bool)
        assert isinstance(rung["target_db"], float)
        assert isinstance(rung["relative_db"], float)
        assert rung["note"] == result["note"]
    assert isinstance(result["redline_hit"], bool)
    # truncated_at 要么 None 要么 int（被截档索引）
    assert result["truncated_at"] is None or isinstance(result["truncated_at"], int)


def test_rung_note_marks_custom_mode():
    result = plan_ladder_steps(-10.0, {"start_db": -20.0, "step_db": 10.0, "stop_db": -5.0})
    assert all(rung["note"] == "custom" for rung in result["steps"])
    assert result["note"] == "custom"
