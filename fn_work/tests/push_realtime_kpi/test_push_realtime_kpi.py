"""push_realtime_kpi 对抗测试：3 帧 2 假 socket 接收计数/sent_ms 盖戳/断连移除/
history 环形截尾/latency 键集与量值/空流/source 异常先 drain 后透传/积压降频
（恰好 50% 不降）/无订阅者不报错/急停控制帧本地直达/hub 形状错 ValueError。
"""
from __future__ import annotations

from collections import deque

import pytest

from src.push_realtime_kpi.push_realtime_kpi import push_realtime_kpi

#: measure_refresh_latency 结果键全集（收尾回执统计合约对拍）。
_LATENCY_KEYS = {
    "p50_ms",
    "p95_ms",
    "n_measured",
    "n_pending",
    "n_clock_skew",
    "n_invalid",
    "n_over_threshold",
    "over_threshold",
    "threshold_ms",
    "status",
}


class FakeSocket:
    """假 WS 端点：记录收到的帧；可模拟断连（send_json 抛）；可选回写回执。"""

    def __init__(self, *, fail: bool = False, acks: "list | None" = None,
                 ack_delay_ms: float = 123.0) -> None:
        self.frames = []
        self.fail = fail
        self._acks = acks
        self._ack_delay = ack_delay_ms

    def send_json(self, frame: dict) -> None:
        if self.fail:
            raise RuntimeError("connection closed")
        self.frames.append(frame)
        if self._acks is not None:  # 模拟页面回执：sent_ms 原样带回+固定延迟
            self._acks.append(
                {"sent_ms": frame["sent_ms"], "acked_ms": frame["sent_ms"] + self._ack_delay}
            )


def test_realtime_console_three_frames_two_sockets_receive_all():
    """① 3 帧×2 假 socket：两端各按序收满 3 帧，n_pushed=3，帧带 sent_ms 盖戳。"""
    s1, s2 = FakeSocket(), FakeSocket()
    hub = {"sockets": {s1, s2}, "history": [], "acks": []}
    frames = [{"kpi": "per", "seq": i} for i in range(3)]
    result = push_realtime_kpi(iter(frames), hub)
    assert result["n_pushed"] == 3
    assert result["n_disconnected"] == 0
    assert [f["seq"] for f in s1.frames] == [0, 1, 2]
    assert [f["seq"] for f in s2.frames] == [0, 1, 2]
    for f in s1.frames:  # 帧盖 sent_ms（毫秒数值戳）
        assert isinstance(f["sent_ms"], (int, float))


def test_realtime_console_existing_sent_ms_preserved():
    """② 帧自带 sent_ms→保留事件原戳不覆盖（端到端口径不低估）。"""
    sock = FakeSocket()
    hub = {"sockets": {sock}, "history": []}
    frame = {"kpi": "rssi", "sent_ms": 1000.0}
    push_realtime_kpi(iter([frame]), hub)
    assert sock.frames[0]["sent_ms"] == 1000.0


def test_realtime_console_dead_socket_removed_and_counted():
    """③ 断连 socket：send_json 抛→移除出 hub、n_disconnected 计数，好连接不受影响。"""
    good, dead = FakeSocket(), FakeSocket(fail=True)
    hub = {"sockets": [good, dead], "history": []}  # list 容器（鸭子类型移除）
    result = push_realtime_kpi(iter([{"v": 1}, {"v": 2}]), hub)
    assert result["n_disconnected"] == 1
    assert dead not in hub["sockets"]
    assert good in hub["sockets"]
    assert len(good.frames) == 2  # 好连接两帧全收（坏连接第一帧即被剔）


def test_realtime_console_history_ring_caps_at_100():
    """④ history 环形 100 条：105 帧入列→留最近 100（list 手动截尾/deque 自动）。"""
    hub = {"sockets": set(), "history": []}
    frames = [{"seq": i} for i in range(105)]
    result = push_realtime_kpi(iter(frames), hub)
    assert result["n_pushed"] == 105
    assert len(hub["history"]) == 100
    assert hub["history"][0] is frames[5]  # 头部=第 6 帧（前 5 条挤出）
    assert hub["history"][-1] is frames[104]  # 尾部=最新帧
    # 缺省自动建的有界 deque 同口径
    hub2 = {"sockets": set()}
    push_realtime_kpi(iter([{"seq": i} for i in range(120)]), hub2)
    assert isinstance(hub2["history"], deque)
    assert len(hub2["history"]) == 100
    assert hub2["history"][-1]["seq"] == 119


def test_realtime_console_latency_measured_from_hub_acks():
    """⑤ 收尾 measure_refresh_latency（hub['acks'] 回执戳流）：键集+量值正确。"""
    acks = []
    sock = FakeSocket(acks=acks, ack_delay_ms=123.0)
    hub = {"sockets": {sock}, "history": [], "acks": acks}
    result = push_realtime_kpi(iter([{"v": i} for i in range(6)]), hub)
    latency = result["latency"]
    assert set(latency) == _LATENCY_KEYS
    assert latency["n_measured"] == 6  # 6 帧全回执
    assert latency["p50_ms"] == pytest.approx(123.0)
    assert latency["over_threshold"] is False  # 123ms 远低于 500ms 判据
    assert hub["acks"] == []  # 回执戳流收尾排空（不跨轮重复计）


def test_realtime_console_empty_source_zero_pushed():
    """⑥ source 空→n_pushed=0，latency 零样本统计，不报错。"""
    hub = {"sockets": {FakeSocket()}, "history": [], "acks": []}
    result = push_realtime_kpi(iter([]), hub)
    assert result["n_pushed"] == 0
    assert result["n_disconnected"] == 0
    assert result["degraded"] is False
    assert result["latency"]["n_measured"] == 0
    assert result["latency"]["status"] == "insufficient"


def test_realtime_console_source_exception_propagates_after_drain():
    """⑦ source 中途抛→透传原异常；透传前 hub 已 drain（acks 清空、已推帧留痕）。"""
    def boom_source():
        yield {"kpi": 1}
        yield {"kpi": 2}
        raise RuntimeError("source-boom")

    hub = {
        "sockets": set(),
        "history": [],
        "acks": [{"sent_ms": 1.0, "acked_ms": 2.0}],  # 遗留回执也应被 drain
    }
    with pytest.raises(RuntimeError, match="source-boom"):
        push_realtime_kpi(boom_source(), hub)
    assert hub["acks"] == []  # drained
    assert [f["kpi"] for f in hub["history"]] == [1, 2]  # 炸前帧留痕


def test_realtime_console_backlog_over_half_degrades():
    """⑧ 积压降频：广播异常率>50%（2 坏连接全失败）→degraded 且 hub 落降频标志。"""
    bad1, bad2 = FakeSocket(fail=True), FakeSocket(fail=True)
    hub = {"sockets": {bad1, bad2}, "history": []}
    result = push_realtime_kpi(iter([{"v": 1}, {"v": 2}]), hub)
    assert result["degraded"] is True
    assert result["n_disconnected"] == 2
    assert hub["degraded"] is True  # 降频标志（生产侧据此降频）
    assert hub["sockets"] == set()  # 坏连接全剔


def test_realtime_console_backlog_at_half_not_degraded():
    """⑨ 判据边界：异常率恰好 50%（1 好 1 坏）不触发降频（严格大于才降）。"""
    good, bad = FakeSocket(), FakeSocket(fail=True)
    hub = {"sockets": {good, bad}, "history": []}
    result = push_realtime_kpi(iter([{"v": 1}]), hub)
    assert result["n_disconnected"] == 1
    assert result["degraded"] is False
    assert "degraded" not in hub


def test_realtime_console_no_subscribers_no_error():
    """⑩ 无订阅者：帧照常消费计数（n_pushed>0）不报错、不降频、history 留痕。"""
    hub = {"sockets": set(), "history": [], "acks": []}
    result = push_realtime_kpi(iter([{"v": 1}, {"v": 2}, {"v": 3}]), hub)
    assert result["n_pushed"] == 3
    assert result["n_disconnected"] == 0
    assert result["degraded"] is False
    assert len(hub["history"]) == 3


def test_realtime_console_emergency_stop_frame_direct_path():
    """⑪ 急停控制帧本地直达：直调 trigger_emergency_stop（不经广播队列）——
    ctx 停旗置位、结果记 hub、在线端点收到急停通知帧。"""
    sock = FakeSocket()
    ctx = {}
    hub = {"sockets": {sock}, "history": [], "acks": [], "ctx": ctx}
    result = push_realtime_kpi(
        iter([{"type": "emergency_stop", "origin": "ui-button"}]), hub
    )
    assert result["n_pushed"] == 1
    assert hub["emergency_stop"]["status"] == "stopped"
    assert hub["emergency_stop"]["origin"] == "ui-button"
    assert ctx["stop"]["flag"] is True  # 场景侧停旗置位
    assert sock.frames[0]["type"] == "emergency_stopped"
    assert sock.frames[0]["status"] == "stopped"


def test_realtime_console_emergency_stop_without_ctx_falls_back_to_hub():
    """⑫ hub 无 ctx→急停上下文以 hub 自身兜底（停旗落 hub['stop'] 可被生产侧读到）。"""
    hub = {"sockets": set(), "history": [], "acks": []}
    result = push_realtime_kpi(iter([{"type": "emergency_stop"}]), hub)
    assert result["n_pushed"] == 1
    assert hub["emergency_stop"]["status"] == "stopped"
    assert hub["stop"]["flag"] is True


def test_realtime_console_hub_not_dict_valueerror():
    """⑬ hub 非 dict（None/str）→ValueError。"""
    with pytest.raises(ValueError, match="hub"):
        push_realtime_kpi(iter([{"v": 1}]), None)
    with pytest.raises(ValueError, match="hub"):
        push_realtime_kpi(iter([{"v": 1}]), "hub")


def test_realtime_console_non_dict_frames_skipped():
    """⑭ 形状坏条目（非 dict 帧）丢弃：流不因单条中断，后续帧照常广播。"""
    sock = FakeSocket()
    hub = {"sockets": {sock}, "history": []}
    result = push_realtime_kpi(iter(["junk", {"v": 1}, 42, {"v": 2}]), hub)
    assert result["n_pushed"] == 2
    assert [f["v"] for f in sock.frames] == [1, 2]
    assert len(hub["history"]) == 2
