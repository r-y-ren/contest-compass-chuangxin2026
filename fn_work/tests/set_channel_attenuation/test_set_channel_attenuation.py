"""set_channel_attenuation 对抗测试：验收 slug=channel_ladder（请求→组合映射、下发鸭子形态、
越界拒绝附可达域、事件落盘严格 JSON、纯计算模式、标定口径注入、返回键集）。
R97 记账增列（2026-10-17）：形态②返回/事件增 tx_gain_db+coarse_semantics、形态①事件体
补 applied_via——本文件精确键集断言随语义更新（B51 同款在案先例）；事件体逐档对拍与
sim 零变化反断言另见 test_attenuation_truthful.py。"""
from __future__ import annotations

import json
from unittest.mock import Mock, call

import pytest

import src.set_channel_attenuation.set_channel_attenuation as sa_module
from src.set_channel_attenuation.set_channel_attenuation import (
    AttenuationError,
    set_channel_attenuation,
)

_COMBO_KEYS = {
    "coarse",
    "coarse_db",
    "fine_step_db",
    "fine_actual_db",
    "achieved_db",
    "residual_db",
    "fine_from",
}


def _reject_constant(name: str) -> None:
    """严格解析哨兵：行内出现 NaN/Infinity/-Infinity 字面量即判失败。"""
    raise ValueError(f"非法 JSON 字面量: {name}")


def _read_events(run_dir) -> list[dict]:
    """逐行严格读回 events.jsonl（parse_constant 拒绝非标准字面量）。"""
    raw = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    return [json.loads(line, parse_constant=_reject_constant) for line in raw.splitlines()]


def test_channel_ladder_35db_dispatches_set_attenuation_and_logs_event(tmp_path):
    """① 35dB→粗档接入+细档 5：set_attenuation 以实达全量 35.0 下发，事件含 target/combo。"""
    backend = Mock(spec=["set_attenuation"])
    result = set_channel_attenuation({"backend": backend, "run_dir": str(tmp_path)}, 35.0)
    backend.set_attenuation.assert_called_once_with(35.0)
    assert result["coarse"] == "in" and result["coarse_db"] == 30.0
    assert result["fine_step_db"] == 5.0 and result["achieved_db"] == 35.0
    assert result["residual_db"] == 0.0
    assert result["applied"] is True and result["applied_via"] == "set_attenuation"
    (event,) = _read_events(tmp_path)
    assert event["type"] == "attenuation" and event["target_db"] == 35.0
    assert event["coarse"] == "in" and event["achieved_db"] == 35.0 and event["applied"] is True


def test_channel_ladder_set_tx_gain_positive_gain_dispatch(tmp_path):
    """② B210 形态（set_tx_gain+get_tx_gain 双在）正增益映射：请求 35 → 组合实达 35
    → 下发绝对增益 25.0（基准 60−35），applied_via='tx_gain'。
    R95 正增益映射改造：旧负值/相对地板语义用例随语义替换改写（2026-10-17）——原
    断言 set_tx_gain(-5.0)+先读 get_tx_gain 属旧相对增量口径；用例 docstring 本意
    "增益可读且足量"即形态②，故按本意改正增益断言（fake 保留 get_tx_gain）而非去
    getter 转 sim——sim 负值路径由下方 unknown_gain 用例（spec=["set_tx_gain"]）独立钉住。"""
    backend = Mock(spec=["set_tx_gain", "get_tx_gain"])
    result = set_channel_attenuation({"backend": backend, "run_dir": str(tmp_path)}, 35.0)
    backend.set_tx_gain.assert_called_once_with(25.0)
    # 绝对映射无需先读当前增益（唯一后端调用即下发本身）
    assert backend.method_calls == [call.set_tx_gain(25.0)]
    assert result["applied"] is True and result["applied_via"] == "tx_gain"
    (event,) = _read_events(tmp_path)
    assert event["applied"] is True and event["fine_step_db"] == 5.0
    assert event["achieved_db"] == 35.0


def test_channel_ladder_both_duck_methods_prefers_set_attenuation_exclusive(tmp_path):
    """③ 双鸭子并存：择 set_attenuation(全量实达)且互斥——不再调 set_tx_gain 防细档重复计。"""
    backend = Mock(spec=["set_attenuation", "set_tx_gain"])
    set_channel_attenuation({"backend": backend, "run_dir": str(tmp_path)}, 12.0)
    backend.set_attenuation.assert_called_once_with(12.0)  # 旁路+细档 12（|12−12|=0 < |12−30|）
    backend.set_tx_gain.assert_not_called()


def test_channel_ladder_no_backend_marks_applied_false_but_still_logs(tmp_path):
    """④ backend 缺→applied False + reason no_backend；事件仍是测量真值照记。"""
    result = set_channel_attenuation({"run_dir": str(tmp_path)}, 35.0)
    assert result["applied"] is False and result["reason"] == "no_backend"
    assert "applied_via" not in result
    (event,) = _read_events(tmp_path)
    assert event["applied"] is False and event["reason"] == "no_backend"
    assert event["target_db"] == 35.0 and event["achieved_db"] == 35.0  # 组合仍完整落盘
    # 对拍：backend 存在但两鸭子方法皆缺——与无 backend 同口径 no_backend
    methodless = Mock(spec=[])
    result2 = set_channel_attenuation(
        {"backend": methodless, "run_dir": str(tmp_path)}, 35.0
    )
    assert result2["applied"] is False and result2["reason"] == "no_backend"


def test_channel_ladder_run_dir_none_pure_computation_skips_event(monkeypatch, tmp_path):
    """⑤ run_dir 缺省 None→纯计算模式：不触事件写（append_event 被调即失败哨兵）。"""
    def _fail(*args, **kwargs):  # noqa: ANN001 - 哨兵：纯计算模式绝不应触事件
        raise AssertionError("纯计算模式不应调用 append_event")

    monkeypatch.setattr(sa_module, "append_event", _fail)
    backend = Mock(spec=["set_tx_gain", "get_tx_gain"])
    backend.get_tx_gain.return_value = 100.0  # 增益足量：细档 20 全额生效
    result = set_channel_attenuation({"backend": backend}, 20.0)
    assert result["applied"] is True and result["achieved_db"] == 20.0
    # R97 记账增列（2026-10-17）：形态②返回/事件增 tx_gain_db+coarse_semantics——键集随语义更新
    assert set(result) == _COMBO_KEYS | {
        "applied", "applied_via", "tx_gain_db", "coarse_semantics",
    }
    assert result["tx_gain_db"] == 40.0 and result["coarse_semantics"] == "gain_budget"
    assert not (tmp_path / "events.jsonl").exists()  # 任何位置均未落盘


def test_channel_ladder_unreachable_46db_attenuation_error_with_reachable_domain(tmp_path):
    """⑥ 46dB 超细档截断域（粗 30+细顶 10=40）→AttenuationError 附可达域，且未下发未落事件。"""
    backend = Mock(spec=["set_attenuation"])
    domain = {"coarse_db": 30.0, "fine_steps_db": [float(s) for s in range(0, 11)]}
    with pytest.raises(AttenuationError) as excinfo:
        set_channel_attenuation(
            {"backend": backend, "run_dir": str(tmp_path)}, 46.0, domain=domain
        )
    assert excinfo.value.reachable_max_db == 40.0
    assert excinfo.value.coarse_top_db == 30.0 and excinfo.value.fine_top_db == 10.0
    assert "可达域" in str(excinfo.value) and "40" in str(excinfo.value)
    backend.set_attenuation.assert_not_called()
    assert not (tmp_path / "events.jsonl").exists()  # 拒绝先于下发与落盘


def test_channel_ladder_inf_target_is_unreachable_not_valueerror():
    """⑥b +inf 视为超域→AttenuationError（默认域顶 30+20=50），非 ValueError。"""
    with pytest.raises(AttenuationError) as excinfo:
        set_channel_attenuation({}, float("inf"))
    assert excinfo.value.reachable_max_db == 50.0
    with pytest.raises(ValueError) as excinfo2:
        set_channel_attenuation({}, float("nan"))
    assert not isinstance(excinfo2.value, AttenuationError)


def test_channel_ladder_cal_from_ctx_equals_direct_cal_table(tmp_path):
    """⑦ ctx['attenuator_cal'] 与 cal_table 直传等价：细档按标定实际值（30+4.6=34.6）。"""
    ctx_cal = {"backend": Mock(spec=["set_attenuation"]), "run_dir": str(tmp_path),
               "attenuator_cal": {5.0: 4.6}}
    via_ctx = set_channel_attenuation(ctx_cal, 35.0)
    via_param = set_channel_attenuation(
        {"backend": Mock(spec=["set_attenuation"]), "run_dir": str(tmp_path)},
        35.0,
        cal_table={5.0: 4.6},
    )
    assert via_ctx["fine_from"] == "calibrated" and via_ctx["fine_actual_db"] == 4.6
    assert via_ctx["achieved_db"] == 34.6 and via_ctx["residual_db"] == pytest.approx(0.4)
    for key in _COMBO_KEYS | {"applied", "applied_via"}:
        assert via_ctx[key] == via_param[key]
    # 直传优先于 ctx：直传 {5.0: 5.2} 时 ctx 表不得生效
    override = set_channel_attenuation(
        {"attenuator_cal": {5.0: 4.6}}, 35.0, cal_table={5.0: 5.2}
    )
    assert override["fine_actual_db"] == 5.2 and override["fine_from"] == "calibrated"


def test_channel_ladder_domain_param_forwarded_to_planner():
    """⑦b domain 参数化透传：细档含 16.5 档时残差归零（默认整数档只能到 0.5）。"""
    default_result = set_channel_attenuation({}, 16.5)
    assert default_result["residual_db"] == pytest.approx(0.5)  # 默认档 16（列表序平手胜）
    exact = set_channel_attenuation({}, 16.5, domain={"fine_steps_db": [0.0, 16.5]})
    assert exact["residual_db"] == 0.0 and exact["fine_step_db"] == 16.5
    assert exact["coarse"] == "bypass"  # 16.5 < 30−16.5 → 旁路态残差更小


def test_channel_ladder_event_jsonl_strict_parse_shape_and_stamps(tmp_path):
    """⑧ 事件 JSONL 严格解析（拒 NaN/Inf 字面量）：type/target/combo/applied+双时间戳。"""
    set_channel_attenuation({"backend": Mock(spec=["set_attenuation"]), "run_dir": str(tmp_path)}, 35.0)
    (event,) = _read_events(tmp_path)
    assert event["type"] == "attenuation"
    # R97（2026-10-17）：形态①事件体补 applied_via（返回已有、事件补齐=如实对称）
    assert set(event) == _COMBO_KEYS | {
        "type", "target_db", "applied", "applied_via", "ts", "wallclock",
    }
    assert event["applied_via"] == "set_attenuation"
    assert isinstance(event["ts"], int)  # 单调钟毫秒
    assert isinstance(event["wallclock"], str) and "T" in event["wallclock"]  # ISO8601
    assert all(isinstance(event[k], (int, float)) for k in
               ("target_db", "coarse_db", "fine_step_db", "fine_actual_db",
                "achieved_db", "residual_db"))  # 数值字段不落占位串


def test_channel_ladder_invalid_targets_raise_valueerror():
    """⑨ target 域错 ValueError 透传：NaN/负数/bool/字符串均拒绝。"""
    for bad in (float("nan"), -1.0, True, "35"):
        with pytest.raises(ValueError) as excinfo:
            set_channel_attenuation({}, bad)
        assert not isinstance(excinfo.value, AttenuationError)


def test_channel_ladder_two_targets_event_order_and_monotonic_ts(tmp_path):
    """⑩ 两档切换：35dB（in）→10dB（bypass）事件顺序保持且 ts 单调不降。"""
    ctx = {"run_dir": str(tmp_path)}
    first = set_channel_attenuation(ctx, 35.0)
    second = set_channel_attenuation(ctx, 10.0)
    events = _read_events(tmp_path)
    assert len(events) == 2
    assert events[0]["target_db"] == 35.0 and events[0]["coarse"] == "in"
    assert events[1]["target_db"] == 10.0 and events[1]["coarse"] == "bypass"
    assert events[0]["ts"] <= events[1]["ts"]
    assert events[0]["coarse_db"] == first["coarse_db"]  # 事件行与返回组合逐字段一致
    assert events[1]["achieved_db"] == second["achieved_db"] == 10.0


def test_channel_ladder_return_keyset_per_path(tmp_path):
    """⑪ 返回结构键集：成功=combo+applied+applied_via；未下发=combo+applied+reason。"""
    backend = Mock(spec=["set_tx_gain", "get_tx_gain"])
    backend.get_tx_gain.return_value = 50.0
    ok = set_channel_attenuation(
        {"backend": backend, "run_dir": str(tmp_path)}, 0.0
    )
    # R97 记账增列（2026-10-17）：形态②返回增 tx_gain_db（请求 0 → 增益=基准 60）+coarse_semantics
    assert set(ok) == _COMBO_KEYS | {
        "applied", "applied_via", "tx_gain_db", "coarse_semantics",
    }
    assert ok["tx_gain_db"] == 60.0 and ok["coarse_semantics"] == "gain_budget"
    assert ok["coarse"] == "bypass" and ok["fine_step_db"] == 0.0 and ok["achieved_db"] == 0.0
    denied = set_channel_attenuation({"run_dir": str(tmp_path)}, 0.0)
    assert set(denied) == _COMBO_KEYS | {"applied", "reason"}


def test_channel_ladder_invalid_run_dir_event_write_error_after_dispatch(tmp_path):
    """⑫ run_dir 无效→EventWriteError 透传（测量真值），且下发先于事件已生效。"""
    backend = Mock(spec=["set_attenuation"])
    bad_dir = tmp_path / "no_such_dir"
    with pytest.raises(sa_module.EventWriteError):
        set_channel_attenuation({"backend": backend, "run_dir": str(bad_dir)}, 35.0)
    backend.set_attenuation.assert_called_once_with(35.0)  # 下发已发生，错误不吞副作用


def test_channel_ladder_non_dict_ctx_rejected():
    """⑫b ctx 形状错（非 dict）→ValueError（与 domain/cal_table 形状错同族）。"""
    with pytest.raises(ValueError, match="ctx"):
        set_channel_attenuation([("backend", None)], 35.0)  # type: ignore[arg-type]


# ---- B9中#3 鸭子下发保真（R95 正增益映射改造后口径）：增益地板/增益不可读如实标注 ----


class _SimGainBackend:
    """B210 形态假后端（R95 后绝对增益口径）：get_tx_gain 在场=形态②判据；
    set_tx_gain 记录并持有下发的绝对增益值（初始增益对绝对映射不参与计算）。"""

    def __init__(self, initial_gain_db: float = 80.0) -> None:
        self.gain_db = float(initial_gain_db)
        self.gain_calls: list[float] = []

    def get_tx_gain(self) -> float:
        return self.gain_db

    def set_tx_gain(self, db: float) -> None:
        self.gain_calls.append(float(db))
        self.gain_db = float(db)


def test_channel_ladder_tx_gain_positive_mapping_and_floor_truthful(tmp_path):
    """B9中#3→R95 增益地板如实（绝对映射口径）：正档全额（请求 15 → 下发 45=60−15，
    applied True）；请求 85（域顶 30+85）实达 85 > 基准 60 → 地板：下发 0、partial
    +gain_floor、实际衰减=基准（achieved=60、residual=25、fine_actual=基准−粗档）；
    同一后端再下 85 结果一致（绝对映射无状态——旧"按当前增益判地板"性质随语义替换）。
    R95 正增益映射改造：旧负值/相对地板语义用例随语义替换改写（2026-10-17）。"""
    domain = {"coarse_db": 30.0, "fine_steps_db": [0.0, 15.0, 85.0]}
    sim = _SimGainBackend(80.0)
    # 正档 15：请求 15 → 旁路粗档+细档 15，实达 15 ≤ 基准 → 下发绝对增益 45
    first = set_channel_attenuation({"backend": sim, "run_dir": str(tmp_path)}, 15.0)
    assert sim.gain_db == 45.0 and sim.gain_calls == [45.0]
    assert first["applied"] is True and first["applied_via"] == "tx_gain"
    assert first["fine_step_db"] == 15.0 and first["achieved_db"] == 15.0
    assert "applied_detail" not in first
    # 请求 85（实达 85 > 基准 60）：增益地板——下发 0、实际细档衰减=基准−粗档
    floored = set_channel_attenuation(
        {"backend": _SimGainBackend(80.0), "run_dir": str(tmp_path)}, 85.0, domain=domain
    )
    assert floored["coarse"] == "bypass" and floored["fine_step_db"] == 85.0  # 请求档如实保留
    assert floored["fine_actual_db"] == 60.0  # 基准−粗档(0)=60：细档实享预算
    assert floored["achieved_db"] == 60.0 and floored["residual_db"] == pytest.approx(25.0)
    assert floored["applied"] == "partial"
    assert floored["applied_via"] == "tx_gain" and floored["applied_detail"] == "gain_floor"
    # R97 记账增列（2026-10-17）：形态②地板返回增 tx_gain_db（=0）+coarse_semantics
    assert set(floored) == _COMBO_KEYS | {
        "applied", "applied_via", "applied_detail", "tx_gain_db", "coarse_semantics",
    }
    # 绝对映射无状态：同一 sim（已置 45）再下 85 → 仍下发 0、结果与全新后端一致
    sequential = set_channel_attenuation({"backend": sim}, 85.0, domain=domain)
    assert sim.gain_db == 0.0 and sim.gain_calls == [45.0, 0.0]
    assert sequential["applied"] == "partial" and sequential["applied_detail"] == "gain_floor"
    assert sequential["achieved_db"] == 60.0
    # 事件真值：applied/achieved 按实际，不再虚报
    event1, event2 = _read_events(tmp_path)
    assert event1["applied"] is True and event1["achieved_db"] == 15.0
    assert event2["applied"] == "partial" and event2["applied_detail"] == "gain_floor"
    assert event2["achieved_db"] == 60.0 and event2["target_db"] == 85.0


def test_channel_ladder_tx_gain_without_get_tx_gain_marks_unknown_gain(tmp_path):
    """B9中#3 无 get_tx_gain：增益地板是否夹 0 无法判定——applied 'unknown_gain'（如实
    标不确定），下发照做、事件同标。"""
    backend = Mock(spec=["set_tx_gain"])
    result = set_channel_attenuation({"backend": backend, "run_dir": str(tmp_path)}, 35.0)
    backend.set_tx_gain.assert_called_once_with(-5.0)  # 细档 5 照常下发
    assert result["applied"] == "unknown_gain" and result["applied_via"] == "set_tx_gain"
    assert "applied_detail" not in result and "reason" not in result
    assert set(result) == _COMBO_KEYS | {"applied", "applied_via"}
    (event,) = _read_events(tmp_path)
    assert event["applied"] == "unknown_gain" and "applied_detail" not in event
