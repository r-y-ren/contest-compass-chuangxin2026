"""tap_tx_window_blocks 骨架镜像测试（R88）——实现期承载：
①装配白名单（sim/b210 启用、replay/无 backend→None）；②dwell_cb 分片/停检/
dwell=0 保底 tick；③_pull_tick 归一盖戳入缓冲（本批已落地：sim 二元组归一/空读
静默/异常透传/max_blocks 透传/非 list 宽松容错）；④交窗判据与急停先行断言按
R88 验收指定口径扩展 tests/run_demo/test_sim_delivery_record_true.py（-k sim_delivery 族）。
"""
from __future__ import annotations

import time

import pytest

from src.tap_tx_window_blocks import tap_tx_window_blocks as tap_module
from src.tap_tx_window_blocks.tap_tx_window_blocks import (
    _make_tick_dwell_cb,
    _pull_tick,
    tap_tx_window_blocks as tap_fn,
)


class FakeBackend:
    """鸭子契约替身：read_samples(max_blocks)——记录每次入参，按脚本返回或抛。

    sim/B210 契约返回 list[块]；result 可注入任意返回形状（含 None/单块）以探
    宽松容错分支；error 非 None 则原样 raise。
    """

    def __init__(self, result: object = None, error: BaseException | None = None):
        self._result = result
        self._error = error
        self.calls: list[int] = []  # 每次 read_samples 收到的 max_blocks

    def read_samples(self, max_blocks: int) -> object:
        self.calls.append(max_blocks)
        if self._error is not None:
            raise self._error
        return self._result


def test_pull_tick_sim_tuple_block_normalized_into_buffer():
    """① sim 二元组块拉取归一：read_samples 返回 [(samples, {'rx_ts': 3})] →
    blocks 追加 1 块、块为 dict、samples 同引用、block_index==3、ts 为 float
    毫秒（盖戳=拉取时刻，落在调用前后窗内）。"""
    samples = [0.1 + 0.2j, 0.3 + 0.4j]
    backend = FakeBackend(result=[(samples, {"rx_ts": 3})])
    ts_before = time.monotonic() * 1000.0
    blocks: list = []
    _pull_tick(backend, blocks, 4)
    ts_after = time.monotonic() * 1000.0
    assert len(blocks) == 1  # 恰追加 1 块
    block = blocks[0]
    assert isinstance(block, dict)
    assert block["samples"] is samples  # 同引用（不复制）
    assert block["block_index"] == 3  # rx_ts 块号降级附注
    assert isinstance(block["ts"], float)
    assert ts_before <= block["ts"] <= ts_after  # 拉取时刻主机单调毫秒
    assert block["overflow"] is False  # meta 缺 overflow 键降级 False


def test_pull_tick_empty_read_silent():
    """② 空读静默：read_samples 返回 [] → blocks 不增、不抛。"""
    backend = FakeBackend(result=[])
    sentinel = object()
    blocks = [sentinel]
    _pull_tick(backend, blocks, 2)  # 不抛即通过
    assert blocks == [sentinel]  # 未追加


def test_pull_tick_read_samples_error_propagates_verbatim():
    """③ read_samples 抛 RuntimeError 原样透传：不捕获不改写，缓冲零追加。"""
    backend = FakeBackend(error=RuntimeError("boom"))
    blocks: list = []
    with pytest.raises(RuntimeError, match="boom"):
        _pull_tick(backend, blocks, 1)
    assert blocks == []  # 异常路径不追加


def test_pull_tick_max_blocks_passthrough():
    """④ max_blocks 透传：FakeBackend 记录入参，断言 == 给定值（逐次记录）。"""
    backend = FakeBackend(result=[])
    _pull_tick(backend, [], 7)
    _pull_tick(backend, [], 3)
    assert backend.calls == [7, 3]


def test_pull_tick_non_list_return_treated_as_empty_read():
    """⑤ 非 list 宽松容错：None/单块 dict 返回皆按空读静默（sim/B210 契约为
    list，与 _tee_backend_stream 空读口径一致——单块不折单例列表）。"""
    for result in (None, {"samples": [1j], "ts": 1.0, "overflow": False}):
        backend = FakeBackend(result=result)
        blocks: list = []
        _pull_tick(backend, blocks, 5)  # 不抛即通过
        assert blocks == []  # 非 list 不追加（区别于 _tee_backend_stream 单块直通）


class _SleepSpy:
    """time 模块替身：记录 sleep 入参不真睡（挂 tap 模块命名空间的 time 名上，
    monkeypatch 自动还原——不影响 shared.normalize_monitor_block 的真单调钟）。"""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)


def test_dwell_cb_zero_dwell_floors_one_tick(monkeypatch):
    """① dwell=0 保底一 tick：恰一次拉取（max_blocks 透传）、零 sleep；负数
    宽松归一同口径（不抛新类型，仍保底一 tick）。"""
    spy = _SleepSpy()
    monkeypatch.setattr(tap_module, "time", spy)
    backend = FakeBackend(result=[])
    cb = _make_tick_dwell_cb(backend, [], None, 0.01, 4)
    cb(0)
    assert backend.calls == [4]  # 恰一次 tick
    assert spy.calls == []  # 无 sleep（首片即因剩余≤0 跳出）
    backend.calls.clear()
    cb(-0.5)  # 负数按 0 处理：不抛、仍保底一 tick
    assert backend.calls == [4]
    assert spy.calls == []


def test_dwell_cb_slices_dwell_into_ticks(monkeypatch):
    """② dwell>slice_s 分片：dwell=0.05, slice_s=0.01 → tick 次数 ≥3、每片
    sleep ≤ slice_s、总睡眠不超 dwell（sleep 已替换为 no-op 防真睡）。"""
    spy = _SleepSpy()
    monkeypatch.setattr(tap_module, "time", spy)
    backend = FakeBackend(result=[])
    cb = _make_tick_dwell_cb(backend, [], None, 0.01, 2)
    cb(0.05)
    assert len(backend.calls) >= 3  # 逐片各一 tick
    assert len(spy.calls) >= 1  # 发生了切片睡眠
    assert all(0.0 < nap <= 0.01 + 1e-12 for nap in spy.calls)  # 片长 ≤ min(剩余, slice_s)
    assert sum(spy.calls) <= 0.05 + 1e-9  # 总睡眠 ≤ dwell（浮点余量）


def test_dwell_cb_stop_flag_raises_emergency_stop(monkeypatch):
    """③ 停旗置位→EmergencyStopRequested：异常类型 is 同一于
    src.run_demo.run_demo 的定义（延迟导入防环导仍归同一类）；停检先于 tick
    （零拉取、零睡眠）。"""
    spy = _SleepSpy()
    monkeypatch.setattr(tap_module, "time", spy)
    from src.run_demo.run_demo import EmergencyStopRequested as RunDemoEmergencyStop

    backend = FakeBackend(result=[])
    cb = _make_tick_dwell_cb(backend, [], {"flag": True}, 0.01, 3)
    with pytest.raises(RunDemoEmergencyStop, match="dwell 分片停检") as excinfo:
        cb(0.02)
    assert type(excinfo.value) is RunDemoEmergencyStop  # is 同一类（非副本/子类）
    assert backend.calls == []  # 停检先于拉取
    assert spy.calls == []


@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"slice_s": 0},             # 非正
        {"slice_s": -0.01},         # 负
        {"slice_s": True},          # bool
        {"slice_s": float("nan")},  # NaN
        {"slice_s": float("inf")},  # ±inf
        {"slice_s": "0.01"},        # 非实数
        {"max_blocks_per_tick": 0},     # 非正
        {"max_blocks_per_tick": -1},    # 负
        {"max_blocks_per_tick": True},  # bool
        {"max_blocks_per_tick": 2.5},   # 非整数
    ],
)
def test_make_tick_dwell_cb_factory_rejects_bad_domain(bad_kwargs):
    """④ 工厂期域拒绝（发射前口径）：slice_s 须正有限实数、max_blocks_per_tick
    须正整数——非法 ValueError，且不触碰 backend（零拉取）。"""
    backend = FakeBackend(result=[])
    kwargs = {"slice_s": 0.01, "max_blocks_per_tick": 4}
    kwargs.update(bad_kwargs)
    with pytest.raises(ValueError):
        _make_tick_dwell_cb(backend, [], None, **kwargs)
    assert backend.calls == []


def test_dwell_cb_read_samples_error_propagates_verbatim(monkeypatch):
    """⑤ 异常透传：_pull_tick 侧 read_samples 抛 → dwell_cb 调用原样上抛
    （同对象、不改写不捕获——由 ladder 停发射后透传）。"""
    monkeypatch.setattr(tap_module, "time", _SleepSpy())
    boom = RuntimeError("boom")
    backend = FakeBackend(error=boom)
    cb = _make_tick_dwell_cb(backend, [], None, 0.01, 5)
    with pytest.raises(RuntimeError, match="boom") as excinfo:
        cb(0.05)  # 多片 dwell：首片 tick 即抛
    assert excinfo.value is boom  # 原样（同对象）透传


def test_dwell_cb_blocks_accumulate_via_closure(monkeypatch):
    """⑥ 闭包贯通：blocks 缓冲经闭包逐 tick 追加归一块（_pull_tick 编排接线）。"""
    monkeypatch.setattr(tap_module, "time", _SleepSpy())
    samples = [1j, 2j]
    backend = FakeBackend(result=[(samples, {"rx_ts": 1})])
    blocks: list = []
    cb = _make_tick_dwell_cb(backend, blocks, None, 0.01, 8)
    cb(0.03)
    assert len(blocks) == len(backend.calls)  # 每次拉取恰追加 1 块
    assert len(blocks) >= 3
    assert all(isinstance(b, dict) and b["samples"] is samples for b in blocks)


class _AssemblyBackend:
    """装配能力探测替身：caps_return 呈现为 capabilities() 返回值（with_caps=False
    时整个方法缺失）；with_read=False 时缺 read_samples（探测只读——装配期本不该
    被调，调用记录供「只装配不拉取」断言）；read_result 为 read_samples 脚本返回。"""

    def __init__(
        self,
        caps_return: object = None,
        with_caps: bool = True,
        with_read: bool = True,
        read_result: object = None,
    ):
        self._caps_return = caps_return
        self._read_result = read_result
        self.read_samples_calls: list[int] = []
        if with_caps:
            self.capabilities = self._capabilities
        if with_read:
            self.read_samples = self._read_samples

    def _capabilities(self) -> object:
        return self._caps_return

    def _read_samples(self, max_blocks: int) -> object:
        self.read_samples_calls.append(max_blocks)
        return self._read_result


@pytest.mark.parametrize("kind", ["sim", "b210"])
def test_tap_whitelist_kind_enabled_assembles_wiring(kind):
    """①② 白名单启用（sim/b210）：返回恰 {'dwell_cb','blocks'} 两键、块缓冲挂
    ctx['tx_window_blocks'] 且与返回 blocks 同引用、dwell_cb 可调用且经闭包写入
    该缓冲；装配只探测不拉取（read_samples 零调用）。"""
    samples = [3j, 4j]
    backend = _AssemblyBackend(
        caps_return={"kind": kind}, read_result=[(samples, {"rx_ts": 2})]
    )
    ctx = {"backend": backend}
    kit = tap_fn(ctx)
    assert isinstance(kit, dict)
    assert set(kit) == {"dwell_cb", "blocks"}  # 恰两键
    assert callable(kit["dwell_cb"])
    assert "tx_window_blocks" in ctx  # 白名单通过才写键
    assert ctx["tx_window_blocks"] is kit["blocks"]  # 同引用（非副本）
    assert kit["blocks"] == []  # 只装配不拉取：缓冲起点为空
    assert backend.read_samples_calls == []  # 装配期零拉取（探测只读）
    kit["dwell_cb"](0)  # 接线验证：dwell=0 保底一 tick，块落入 ctx 挂的同一缓冲
    assert len(ctx["tx_window_blocks"]) == 1
    assert ctx["tx_window_blocks"][0]["samples"] is samples  # 归一后同引用


def test_tap_replay_kind_rejected_no_ctx_key():
    """③ replay 拒：kind='replay' → None 且不写 ctx['tx_window_blocks']
    （调用方不接线，后置采集语义保持），零拉取。"""
    backend = _AssemblyBackend(caps_return={"kind": "replay"})
    ctx = {"backend": backend}
    assert tap_fn(ctx) is None
    assert "tx_window_blocks" not in ctx
    assert backend.read_samples_calls == []


def test_tap_probing_failures_return_none_without_ctx_write():
    """④ 能力探测不通过族：无 backend/capabilities 缺失/返回非 dict（None/
    list）/read_samples 缺失 → 一律 None 且不写 ctx 键（防御不抛）。"""
    cases: list[tuple[str, dict]] = [
        ("无 backend", {}),
        ("capabilities 缺失", {"backend": _AssemblyBackend(with_caps=False)}),
        (
            "capabilities 返回 None",
            {"backend": _AssemblyBackend(caps_return=None)},
        ),
        (
            "capabilities 返回 list",
            {"backend": _AssemblyBackend(caps_return=["sim"])},
        ),
        (
            "read_samples 缺失",
            {"backend": _AssemblyBackend(caps_return={"kind": "sim"}, with_read=False)},
        ),
    ]
    for label, ctx in cases:
        assert tap_fn(ctx) is None, label
        assert "tx_window_blocks" not in ctx, label


def test_tap_non_dict_ctx_returns_none_lenient():
    """⑤ ctx 非 dict → None（宽松不抛——gb 协议调用方自身已校验 ctx 形状）。"""
    for bad in (None, [], "ctx", 42, object()):
        assert tap_fn(bad) is None
