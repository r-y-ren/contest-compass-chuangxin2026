"""stop_transmit_safely 对抗测试：两步静默、幂等/重试语义、None 后端、异常花样（BaseException 穿透）、context 透传与结构完整性。"""
from __future__ import annotations

from datetime import datetime

import pytest

from src.shared.stop_transmit_safely import stop_transmit_safely


class _FakeBackend:
    """双能力假后端：记录调用次数与增益参数，可按步注入异常。"""

    def __init__(self, stop_error=None, gain_error=None):
        self.stop_calls = 0
        self.gain_calls = []
        self._stop_error = stop_error
        self._gain_error = gain_error

    def stop_tx(self):
        self.stop_calls += 1
        if self._stop_error is not None:
            raise self._stop_error

    def set_tx_gain(self, gain):
        self.gain_calls.append(gain)
        if self._gain_error is not None:
            raise self._gain_error


class _StopOnlyBackend:
    """只有 stop_tx 的鸭子类型后端（缺增益方法）。"""

    def __init__(self):
        self.stop_calls = 0

    def stop_tx(self):
        self.stop_calls += 1


class _JunkAttrBackend:
    """stop_tx 属性为非 callable 垃圾值的畸形后端。"""

    stop_tx = 7

    def __init__(self):
        self.gain_calls = []

    def set_tx_gain(self, gain):
        self.gain_calls.append(gain)


class _LinkFault(Exception):
    """自定义异常类型样本。"""


def test_normal_backend_both_steps_stopped():
    """① 正常后端：stop_tx→set_tx_gain(0) 两步全过→stopped，顺序与参数正确。"""
    be = _FakeBackend()
    result = stop_transmit_safely(be, context={"origin": "run_power_ladder"})
    assert result["status"] == "stopped"
    assert [s["op"] for s in result["steps"]] == ["stop_tx", "set_tx_gain"]
    assert all(s["ok"] is True for s in result["steps"])
    assert be.stop_calls == 1
    assert be.gain_calls == [0]


def test_idempotent_second_call_already_stopped():
    """② 幂等：同一后端二次调用→already_stopped，不再触碰 backend。"""
    be = _FakeBackend()
    first = stop_transmit_safely(be)
    assert first["status"] == "stopped"
    second = stop_transmit_safely(be)
    assert second["status"] == "already_stopped"
    assert second["steps"] == []
    assert be.stop_calls == 1
    assert be.gain_calls == [0]


def test_no_backend_returns_no_backend_without_raise():
    """③ backend=None→no_backend 且绝不抛出；steps 为空，context 照样透传。"""
    ctx = {"run_dir": "/tmp/run_01", "origin": "trigger_emergency_stop"}
    result = stop_transmit_safely(None, context=ctx)
    assert result["status"] == "no_backend"
    assert result["steps"] == []
    assert result["context"] == ctx
    assert stop_transmit_safely(None)["status"] == "no_backend"


def test_stop_tx_error_still_zeroes_gain():
    """④ stop_tx 抛异常→仍执行增益归零→failed 且首步含异常类型与原因。"""
    be = _FakeBackend(stop_error=RuntimeError("射频去能失败"))
    result = stop_transmit_safely(be)
    assert result["status"] == "failed"
    assert result["steps"][0]["op"] == "stop_tx"
    assert result["steps"][0]["ok"] is False
    assert "RuntimeError" in result["steps"][0]["detail"]
    assert "射频去能失败" in result["steps"][0]["detail"]
    assert result["steps"][1]["op"] == "set_tx_gain"
    assert result["steps"][1]["ok"] is True
    assert be.gain_calls == [0]


def test_both_steps_fail_reasons_complete():
    """⑤ 两步都抛→failed，两步原因各自齐全不互相覆盖。"""
    be = _FakeBackend(stop_error=ValueError("bus locked"), gain_error=KeyError("gain"))
    result = stop_transmit_safely(be)
    assert result["status"] == "failed"
    failed = [s for s in result["steps"] if not s["ok"]]
    assert len(failed) == 2
    details = " | ".join(s["detail"] for s in result["steps"])
    assert "ValueError" in details and "bus locked" in details
    assert "KeyError" in details and "gain" in details


def test_stop_only_backend_single_step_stopped():
    """⑥ 缺增益方法只有 stop_tx→单步成功→stopped。"""
    be = _StopOnlyBackend()
    result = stop_transmit_safely(be)
    assert result["status"] == "stopped"
    assert [s["op"] for s in result["steps"]] == ["stop_tx"]
    assert result["steps"][0]["ok"] is True
    assert be.stop_calls == 1


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_base_exceptions_propagate(exc):
    """⑦ BaseException 族（KeyboardInterrupt/SystemExit）不被捕获，必须穿透。"""
    be = _FakeBackend(stop_error=exc("interrupt"))
    with pytest.raises(exc):
        stop_transmit_safely(be)


@pytest.mark.parametrize(
    ("stop_error", "type_name", "msg_fragment"),
    [
        (RuntimeError("boom"), "RuntimeError", "boom"),
        (ValueError("gain write timeout"), "ValueError", "gain write timeout"),
        (_LinkFault("link down"), "_LinkFault", "link down"),
        (Exception(""), "Exception", ""),
    ],
)
def test_exception_variety_recorded_not_raised(stop_error, type_name, msg_fragment):
    """⑧ 异常类型花样（含自定义类与空消息、字符串消息）：一律捕获记录，不外抛。"""
    result = stop_transmit_safely(_FakeBackend(stop_error=stop_error))
    assert result["status"] == "failed"
    detail = result["steps"][0]["detail"]
    assert result["steps"][0]["ok"] is False
    assert type_name in detail
    if msg_fragment:
        assert msg_fragment in detail


def test_context_passthrough():
    """⑨ context 透传：原样（同一对象）进入事件记录；缺省为 None。"""
    ctx = {"run_dir": "/data/runs/r7", "origin": "manage_run"}
    result = stop_transmit_safely(_FakeBackend(), context=ctx)
    assert result["context"] is ctx
    assert stop_transmit_safely(_FakeBackend())["context"] is None


def test_result_structure_complete():
    """⑩ 返回结构键齐：status/steps/ts/context；ts 可解析为 ISO 时间；步骤键齐。"""
    result = stop_transmit_safely(_FakeBackend())
    assert set(result.keys()) == {"status", "steps", "ts", "context"}
    datetime.fromisoformat(result["ts"])
    for step in result["steps"]:
        assert set(step.keys()) == {"op", "ok", "detail"}


def test_independent_backends_no_state_leak():
    """⑪ 幂等记忆按 backend 隔离：A 已停不影响新后端 B 正常执行。"""
    stop_transmit_safely(_FakeBackend())
    be_b = _FakeBackend()
    result = stop_transmit_safely(be_b)
    assert result["status"] == "stopped"
    assert be_b.stop_calls == 1


def test_failed_attempt_retries_on_next_call():
    """⑫ 失败不登记幂等：二次调用全流程重试而非 already_stopped。"""
    be = _FakeBackend(gain_error=RuntimeError("spike"))
    first = stop_transmit_safely(be)
    assert first["status"] == "failed"
    second = stop_transmit_safely(be)
    assert second["status"] == "failed"
    assert be.stop_calls == 2
    assert be.gain_calls == [0, 0]


def test_non_callable_attribute_recorded_as_failure():
    """⑬ stop_tx 属性为非 callable（int）：调用期 TypeError 记为失败步，增益归零仍执行。"""
    be = _JunkAttrBackend()
    result = stop_transmit_safely(be)
    assert result["status"] == "failed"
    assert result["steps"][0]["ok"] is False
    assert "TypeError" in result["steps"][0]["detail"]
    assert result["steps"][1]["ok"] is True
    assert be.gain_calls == [0]


def test_no_capability_backend_vacuous_stopped_and_fallback_idempotent():
    """⑭ 无任何发射能力的后端（object()，且不可弱引用）：空步→stopped，走强持有回退仍幂等。"""
    be = object()
    first = stop_transmit_safely(be)
    assert first["status"] == "stopped"
    assert first["steps"] == []
    assert stop_transmit_safely(be)["status"] == "already_stopped"
