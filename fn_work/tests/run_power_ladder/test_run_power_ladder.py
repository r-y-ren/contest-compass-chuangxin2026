"""run_power_ladder 对抗测试：验收 slug=power_ladder（步进序列、事件时间线、失效即停、
异常先停发射再透传、判据形状口径、dwell 域、返回结构与 stop_result 落位）。"""
from __future__ import annotations

import json
from unittest.mock import Mock, call

import pytest

import src.run_power_ladder.run_power_ladder as pl_module
from src.run_power_ladder.run_power_ladder import (
    AttenuationError,
    EventWriteError,
    PlanError,
    run_power_ladder,
)

_RETURN_KEYS = {"executed", "stopped_at", "reason", "plan", "stop_result"}
_POWER_STEP_KEYS = {
    "type",
    "step",
    "target_db",
    "dwell_s",
    "coarse",
    "coarse_db",
    "fine_step_db",
    "fine_actual_db",
    "achieved_db",
    "residual_db",
    "fine_from",
    "applied",
}


def _reject_constant(name: str) -> None:
    """严格解析哨兵：行内出现 NaN/Infinity/-Infinity 字面量即判失败。"""
    raise ValueError(f"非法 JSON 字面量: {name}")


def _read_events(run_dir) -> list[dict]:
    """逐行严格读回 events.jsonl（parse_constant 拒绝非标准字面量）。"""
    raw = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    return [json.loads(line, parse_constant=_reject_constant) for line in raw.splitlines()]


def _power_steps(events: list[dict]) -> list[dict]:
    return [event for event in events if event["type"] == "power_step"]


def _ctx(tmp_path, backend, **extra):
    ctx = {"backend": backend, "run_dir": str(tmp_path)}
    ctx.update(extra)
    return ctx


def test_power_ladder_full_walk_complete_reason_and_step_event_sequence(tmp_path):
    """① 全档走完：reason complete、executed/power_step 事件 step 序连续+target_db 序。"""
    backend = Mock(spec=["set_attenuation", "stop_tx"])
    result = run_power_ladder(
        _ctx(tmp_path, backend),
        {"start_db": -20.0, "step_db": 10.0, "stop_db": -10.0},
        failure_cb=lambda info: {"failed": False},
        dwell_s=0.0,
        link_power_db=-30.0,
    )
    assert result["reason"] == "complete" and result["stopped_at"] is None
    assert [rec["step"] for rec in result["executed"]] == [0, 1]
    assert [rec["target_db"] for rec in result["executed"]] == [-20.0, -10.0]
    # 衰减口径：target −20→衰减 20、−10→衰减 10，按档序下发
    assert backend.set_attenuation.call_args_list == [call(20.0), call(10.0)]
    steps = _power_steps(_read_events(tmp_path))
    assert [event["step"] for event in steps] == [0, 1]
    assert [event["target_db"] for event in steps] == [-20.0, -10.0]


def test_power_ladder_failure_at_second_rung_stops_before_final_event(tmp_path):
    """② 判据第 2 档触发：stopped_at=1 reason failure；stop_tx 调用先于事件流末行。"""
    backend = Mock(spec=["set_attenuation", "stop_tx"])
    lines_at_stop: list[int] = []

    def _snapshot_event_count():
        lines_at_stop.append(len((tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()))

    backend.stop_tx.side_effect = _snapshot_event_count

    def _cb(info):
        return {"failed": info["step"] == 1, "detail": "PER=12%>10%"}

    result = run_power_ladder(_ctx(tmp_path, backend), None, failure_cb=_cb, dwell_s=0.0, link_power_db=-20.0)
    assert result["reason"] == "failure" and result["stopped_at"] == 1
    assert len(result["executed"]) == 2
    assert result["executed"][1]["failed"] is True
    assert result["executed"][1]["failure_detail"] == "PER=12%>10%"
    backend.stop_tx.assert_called_once()
    events = _read_events(tmp_path)
    # 停发射时刻事件行数 = 终态行数−1：末行（ladder_stop）写于 stop_tx 之后
    assert lines_at_stop == [len(events) - 1]
    assert events[-1]["type"] == "ladder_stop"
    assert events[-1]["reason"] == "failure" and events[-1]["stopped_at"] == 1
    assert events[-1]["failure_detail"] == "PER=12%>10%"
    assert [event["step"] for event in _power_steps(events)] == [0, 1]


def test_power_ladder_failure_cb_none_walks_all_rungs(tmp_path):
    """③ 判据缺省 None=永不失效：3 档全走完，各档无 failed 字段。"""
    backend = Mock(spec=["set_attenuation"])
    result = run_power_ladder(
        _ctx(tmp_path, backend),
        {"start_db": -15.0, "step_db": 5.0, "stop_db": -5.0},
        dwell_s=0.0,
    )
    assert result["reason"] == "complete" and result["stopped_at"] is None
    assert [rec["target_db"] for rec in result["executed"]] == [-15.0, -10.0, -5.0]
    assert all("failed" not in rec for rec in result["executed"])
    assert backend.set_attenuation.call_count == 3


def test_power_ladder_link_zero_gb_plan_two_rungs_truncated(tmp_path):
    """④ link=0 GB 缺省：两档 [−5, 0] 恰至红线（0dBm 恰过不截），reason truncated。"""
    backend = Mock(spec=["set_attenuation"])
    result = run_power_ladder(_ctx(tmp_path, backend), None, dwell_s=0.0, link_power_db=0.0)
    assert result["reason"] == "truncated" and result["stopped_at"] is None
    assert [rec["target_db"] for rec in result["executed"]] == [-5.0, 0.0]
    assert result["plan"]["truncated_at"] == 2 and result["plan"]["redline_hit"] is True
    assert result["plan"]["note"] == "gb42590"
    # target 0→衰减 0：末档以零衰减下发
    assert backend.set_attenuation.call_args_list == [call(5.0), call(0.0)]


def test_power_ladder_redline_truncated_distinct_link(tmp_path):
    """④b 红线截断非 link=0 特例：link=−7 → [−12, −7, −2] 三档后 +3 越线截断。"""
    backend = Mock(spec=["set_attenuation"])
    result = run_power_ladder(_ctx(tmp_path, backend), None, dwell_s=0.0, link_power_db=-7.0)
    assert result["reason"] == "truncated"
    assert [rec["target_db"] for rec in result["executed"]] == [-12.0, -7.0, -2.0]
    assert result["plan"]["truncated_at"] == 3


def test_power_ladder_unreachable_46db_rung_stops_then_propagates(tmp_path):
    """⑤ 46dB 档超可达域（细档标定压顶=10 → 域顶 40）：停发射后透传，未下发未落事件。"""
    backend = Mock(spec=["set_attenuation", "stop_tx"])
    capped_cal = {float(step): step * 0.5 for step in range(0, 21)}  # 细档实际值减半 → 顶 10
    with pytest.raises(AttenuationError) as excinfo:
        run_power_ladder(
            _ctx(tmp_path, backend, attenuator_cal=capped_cal),
            {"start_db": -46.0, "stop_db": -46.0},
            dwell_s=0.0,
        )
    assert excinfo.value.reachable_max_db == 40.0
    backend.set_attenuation.assert_not_called()
    backend.stop_tx.assert_called_once()  # 先停发射再透传
    assert not (tmp_path / "events.jsonl").exists()


def test_power_ladder_event_write_error_stops_then_propagates(tmp_path):
    """⑥ 事件落盘失败（run_dir 不存在）：已下发不吞副作用，停发射后透传。"""
    backend = Mock(spec=["set_attenuation", "stop_tx"])
    bad_dir = tmp_path / "no_such_dir"
    with pytest.raises(EventWriteError):
        run_power_ladder(
            {"backend": backend, "run_dir": str(bad_dir)},
            {"start_db": -5.0, "stop_db": -5.0},
            dwell_s=0.0,
        )
    backend.set_attenuation.assert_called_once_with(5.0)  # 下发已生效，错误不吞副作用
    backend.stop_tx.assert_called_once()


@pytest.mark.parametrize("bad_return", [{"detail": "半截判据"}, True, None])
def test_power_ladder_failure_cb_bad_shape_treated_as_not_failed(tmp_path, bad_return):
    """⑦ 判据返回形状错（缺 'failed'/非 dict）：视为未失效记 warning，全档走完。"""
    backend = Mock(spec=["set_attenuation"])
    seen: list[int] = []

    def _cb(info):
        seen.append(info["step"])
        return bad_return

    result = run_power_ladder(
        _ctx(tmp_path, backend),
        {"start_db": -10.0, "step_db": 5.0, "stop_db": -5.0},
        failure_cb=_cb,
        dwell_s=0.0,
    )
    assert result["reason"] == "complete" and result["stopped_at"] is None
    assert seen == [0, 1]  # 每档仍被征询
    assert all("warning" in rec for rec in result["executed"])
    assert all("failed" not in rec for rec in result["executed"])
    assert "视为未失效" in result["executed"][0]["warning"]


def test_power_ladder_invalid_dwell_rejected_before_any_side_effect(tmp_path):
    """⑧ dwell_s 负/NaN/±inf/bool → ValueError（发射前拒绝）：无下发、无事件、无停发射。"""
    backend = Mock(spec=["set_attenuation", "stop_tx"])
    for bad in (-0.1, -1, float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="dwell_s"):
            run_power_ladder(_ctx(tmp_path, backend), None, dwell_s=bad, link_power_db=-20.0)
    backend.set_attenuation.assert_not_called()
    backend.stop_tx.assert_not_called()
    assert not (tmp_path / "events.jsonl").exists()


def test_power_ladder_return_keyset_and_plan_payload(tmp_path):
    """⑨ 返回结构键集：executed/stopped_at/reason/plan/stop_result；plan 为原计划。"""
    backend = Mock(spec=["set_attenuation", "stop_tx"])
    result = run_power_ladder(_ctx(tmp_path, backend), {"start_db": -10.0, "stop_db": -10.0}, dwell_s=0.0)
    assert set(result) == _RETURN_KEYS
    assert result["plan"]["note"] == "custom"
    assert [rung["target_db"] for rung in result["plan"]["steps"]] == [-10.0]
    assert isinstance(result["stop_result"], dict)


def test_power_ladder_stop_result_recorded_on_completion(tmp_path):
    """⑩ stop_result 落位：收尾停发射结果（status=stopped、stop_tx 步成功）+事件留痕。"""
    backend = Mock(spec=["set_attenuation", "stop_tx"])
    result = run_power_ladder(_ctx(tmp_path, backend), None, dwell_s=0.0, link_power_db=0.0)
    stop = result["stop_result"]
    assert stop["status"] == "stopped"
    assert [step["op"] for step in stop["steps"]] == ["stop_tx"]
    assert all(step["ok"] for step in stop["steps"])
    backend.stop_tx.assert_called_once()
    assert _read_events(tmp_path)[-1]["stop_status"] == "stopped"


def test_power_ladder_events_jsonl_strict_parse_power_step_fields(tmp_path):
    """⑪ 事件 JSONL 严格解析：power_step 字段齐备（组合+applied+双时间戳），ts 单调不降。"""
    backend = Mock(spec=["set_attenuation"])
    run_power_ladder(
        _ctx(tmp_path, backend),
        {"start_db": -10.0, "step_db": 5.0, "stop_db": -5.0},
        dwell_s=0.0,
    )
    events = _read_events(tmp_path)
    steps = _power_steps(events)
    assert len(steps) == 2
    for step_event in steps:
        assert _POWER_STEP_KEYS <= set(step_event)
        assert isinstance(step_event["ts"], int) and "T" in step_event["wallclock"]
        assert step_event["applied"] is True and step_event["dwell_s"] == 0.0
    assert all(a["ts"] <= b["ts"] for a, b in zip(events, events[1:]))
    # 逐档 attenuation 事件（set_channel_attenuation 自落）与 power_step 交替且档序一致
    atts = [event for event in events if event["type"] == "attenuation"]
    assert [event["target_db"] for event in atts] == [10.0, 5.0]


def test_power_ladder_dwell_sleep_called_per_rung(tmp_path, monkeypatch):
    """⑫ dwell 真实计时路径：每档 time.sleep(dwell_s) 一次（0 亦照调，可测可注）。"""
    sleeps: list[float] = []
    monkeypatch.setattr(pl_module.time, "sleep", lambda seconds: sleeps.append(seconds))
    backend = Mock(spec=["set_attenuation"])
    run_power_ladder(
        _ctx(tmp_path, backend),
        {"start_db": -10.0, "step_db": 5.0, "stop_db": -5.0},
        dwell_s=0.0,
    )
    assert sleeps == [0.0, 0.0]


def test_power_ladder_backend_method_error_stops_then_propagates(tmp_path):
    """⑬ 后端方法异常（第 2 档 set_attenuation 抛 RuntimeError）：停发射后透传。"""
    backend = Mock(spec=["set_attenuation", "stop_tx"])
    backend.set_attenuation.side_effect = [None, RuntimeError("visa link lost")]
    with pytest.raises(RuntimeError, match="visa link lost"):
        run_power_ladder(
            _ctx(tmp_path, backend),
            {"start_db": -10.0, "step_db": 5.0, "stop_db": -5.0},
            dwell_s=0.0,
        )
    backend.stop_tx.assert_called_once()
    assert [event["step"] for event in _power_steps(_read_events(tmp_path))] == [0]  # 第 2 档未落


def test_power_ladder_failure_cb_exception_stops_then_propagates(tmp_path):
    """⑭ 判据自身异常：与下发/落盘异常同语义——先停发射再透传。"""
    backend = Mock(spec=["set_attenuation", "stop_tx"])

    def _cb(info):
        raise ValueError("判据自身异常")

    with pytest.raises(ValueError, match="判据自身异常"):
        run_power_ladder(
            _ctx(tmp_path, backend),
            {"start_db": -5.0, "stop_db": -5.0},
            failure_cb=_cb,
            dwell_s=0.0,
        )
    backend.stop_tx.assert_called_once()


def test_power_ladder_run_dir_none_pure_execution_no_events(tmp_path, monkeypatch):
    """⑮ run_dir 缺省 None：纯执行不落任何事件（append_event 被调即失败哨兵）。"""
    def _fail(*args, **kwargs):  # noqa: ANN001 - 哨兵：无 run_dir 绝不应写事件
        raise AssertionError("run_dir=None 不应调用 append_event")

    monkeypatch.setattr(pl_module, "append_event", _fail)
    backend = Mock(spec=["set_attenuation"])
    result = run_power_ladder(
        {"backend": backend},
        {"start_db": -5.0, "stop_db": -5.0},
        dwell_s=0.0,
    )
    assert result["reason"] == "complete"
    backend.set_attenuation.assert_called_once_with(5.0)
    assert not (tmp_path / "events.jsonl").exists()


def test_power_ladder_plan_error_passthrough_without_stop(tmp_path):
    """⑯ 计划域错误（GB 口径 link>0）透传：未发射即拒，不触发停发射。"""
    backend = Mock(spec=["set_attenuation", "stop_tx"])
    with pytest.raises(PlanError):
        run_power_ladder(_ctx(tmp_path, backend), None, dwell_s=0.0, link_power_db=6.0)
    backend.set_attenuation.assert_not_called()
    backend.stop_tx.assert_not_called()
    assert not (tmp_path / "events.jsonl").exists()


def test_power_ladder_non_callable_failure_cb_rejected_upfront(tmp_path):
    """⑰ failure_cb 非 callable 且非 None：发射前 TypeError 拒绝。"""
    backend = Mock(spec=["set_attenuation", "stop_tx"])
    with pytest.raises(TypeError, match="failure_cb"):
        run_power_ladder(
            _ctx(tmp_path, backend),
            {"start_db": -5.0, "stop_db": -5.0},
            failure_cb="not-a-callable",  # type: ignore[arg-type]
            dwell_s=0.0,
        )
    backend.set_attenuation.assert_not_called()
    backend.stop_tx.assert_not_called()
