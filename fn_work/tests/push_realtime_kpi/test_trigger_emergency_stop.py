"""trigger_emergency_stop 对抗测试：先停发射序断言（mock 后端在 stop_tx 时刻旗标
未置）、stop dict 缺失补建、origin/stopped_at 透传、腐化 ctx 不抛（记 stop_failed
原因）、run_token 幂等透传、发射失败结果标注不抛。"""
from __future__ import annotations

from datetime import datetime

import pytest

from src.push_realtime_kpi.trigger_emergency_stop import trigger_emergency_stop


class _ProbeBackend:
    """记录调用时刻停旗快照的探针后端：stop_tx 时旗标应为「尚未置位」。"""

    def __init__(self, ctx):
        self._ctx = ctx
        self.snapshots = []

    def stop_tx(self):
        stop_box = self._ctx.get("stop", {}) if isinstance(self._ctx, dict) else {}
        self.snapshots.append(("stop_tx", stop_box.get("flag", False)))

    def set_tx_gain(self, gain):
        self.snapshots.append(("set_tx_gain", gain))


class _FailingBackend:
    """stop_tx 抛异常的后端（发射侧失败路径）。"""

    def __init__(self):
        self.calls = 0

    def stop_tx(self):
        self.calls += 1
        raise RuntimeError("tx-hw-fault")

    def set_tx_gain(self, gain):
        raise KeyboardInterrupt("KI-during-gain")  # BaseException 族也不许穿透


def test_stop_tx_runs_before_flag_set():
    """① 序断言：stop_tx 调用时刻停旗仍为 False（先停发射，后置旗）。"""
    ctx = {}
    probe = _ProbeBackend(ctx)
    ctx["backend"] = probe
    ctx["run_token"] = "run-1"
    result = trigger_emergency_stop(ctx, origin="test")
    assert probe.snapshots == [("stop_tx", False), ("set_tx_gain", 0)]
    assert ctx["stop"]["flag"] is True  # 全程结束后旗标才置位
    assert [e["event"] for e in result["events"]] == [
        "emergency_stop_requested",
        "transmit_stopped",
        "stop_flag_set",
    ]


def test_missing_stop_dict_created():
    """② ctx 无 stop 子 dict→就地创建 {'flag': True}。"""
    ctx = {"backend": None}
    trigger_emergency_stop(ctx, origin="watchdog")
    assert ctx["stop"] == {"flag": True}


def test_origin_passthrough_and_result_shape():
    """③ origin 原样透传，stopped_at 可按 ISO 解析，stop_result 携带发射侧状态。"""
    result = trigger_emergency_stop(
        {"backend": None, "run_token": "t"}, origin="ui-button"
    )
    assert result["origin"] == "ui-button"
    datetime.fromisoformat(result["stopped_at"])  # 合法 ISO 戳
    assert isinstance(result["stop_result"], dict)
    assert result["stop_result"]["status"] == "no_backend"  # backend None 语义
    assert result["status"] == "stopped"


@pytest.mark.parametrize("broken_ctx", [{"stop": "junk-not-dict"}, None])
def test_corrupt_ctx_never_raises(broken_ctx):
    """④ 腐化 ctx（stop 非可写 dict / ctx 为 None）→不抛，记 stop_failed+原因。"""
    result = trigger_emergency_stop(broken_ctx, origin="probe")
    assert result["status"] == "stop_failed"
    last = result["events"][-1]
    assert last["event"] == "stop_failed" and last["reason"]
    # 发射侧仍先行完成（None 后端 no_backend；junk ctx 亦先走安全停）
    assert result["events"][1]["event"] == "transmit_stopped"


def test_run_token_idempotency_passthrough():
    """⑤ run_token 透传：同 token 二次调用→already_stopped；换 token→重新停。"""
    backend = _ProbeBackend({})
    ctx = {"backend": backend, "run_token": "tok-A"}
    first = trigger_emergency_stop(ctx, origin="a")
    second = trigger_emergency_stop(ctx, origin="b")
    assert first["stop_result"]["status"] == "stopped"
    assert second["stop_result"]["status"] == "already_stopped"  # token 生效证明
    ctx["run_token"] = "tok-B"  # 新一轮运行——重走全流程
    third = trigger_emergency_stop(ctx, origin="c")
    assert third["stop_result"]["status"] == "stopped"


def test_backend_failure_recorded_flag_still_set():
    """⑥ 发射侧两步全炸（含 KI）→结果标注 failed 不抛，停旗仍尽力置位。"""
    be = _FailingBackend()
    ctx = {"backend": be, "run_token": "tok-f"}
    result = trigger_emergency_stop(ctx, origin="watchdog")
    assert be.calls == 1  # 停发射确被尝试
    assert result["stop_result"]["status"] == "failed"
    assert any(step["ok"] is False for step in result["stop_result"]["steps"])
    assert ctx["stop"]["flag"] is True  # 场景侧停旗不受发射失败牵连
    assert result["status"] == "stopped"  # 路径本身完成（失败只标注在 stop_result）
