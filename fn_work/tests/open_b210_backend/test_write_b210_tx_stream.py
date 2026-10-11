"""write_b210_tx_stream 对抗测试：FakeStream 鸭子句柄覆盖送达/欠载/异常/规整/回调路径。"""
from __future__ import annotations

import pytest

from src.manage_backend_registry.register_backend import BackendError
from src.open_b210_backend.write_b210_tx_stream import write_b210_tx_stream


class FakeStream:
    """鸭子发射流：事件序 + 分块记录；send 行为按 send_results 计划逐次驱动。

    send_results 每项：int → 本次返回 {'sent': int}；BaseException 实例 → send 抛出；
    计划耗尽 → 按足量 {'sent': len(chunk)} 返回。end_raises 非 None 时 end() 抛出。
    """

    def __init__(self, send_results=None, end_raises=None):
        self.events: list[str] = []
        self.chunks: list[list[complex]] = []
        self.send_results = list(send_results or [])
        self.end_raises = end_raises

    def start(self):
        self.events.append("start")

    def end(self):
        self.events.append("end")
        if self.end_raises is not None:
            raise self.end_raises

    def send(self, chunk):
        self.events.append("send")
        self.chunks.append(list(chunk))
        plan = (
            self.send_results[len(self.chunks) - 1]
            if len(self.chunks) <= len(self.send_results)
            else None
        )
        if plan is None:
            return {"sent": len(chunk)}
        if isinstance(plan, BaseException):
            raise plan
        return {"sent": plan}


def test_full_delivery_stats_and_lifecycle_ordering():
    """全量送达：样本/分块统计正确，start 先于一切 send、end 最后。"""
    stream = FakeStream()
    result = write_b210_tx_stream(
        stream, [[1 + 2j, 3 + 4j, 5 + 6j, 7 + 8j], [9 + 10j, 11 + 12j]], chunk_size=3
    )
    assert result == {
        "samples_sent": 6,
        "blocks": 3,
        "underruns": 0,
        "invalid_zeroed": 0,
    }
    # 4 样本块按 3 切 → [3,1]，2 样本块 → [2]
    assert [len(c) for c in stream.chunks] == [3, 1, 2]
    assert stream.chunks[0] == [1 + 2j, 3 + 4j, 5 + 6j]
    assert stream.events[0] == "start"
    assert stream.events[-1] == "end"
    assert stream.events.count("send") == 3


def test_partial_send_counts_underrun_without_error():
    """sent 部分返回：记 1 次欠载、样本按实际 sent 累计，未超默认阈值 3 不熔断。"""
    stream = FakeStream(send_results=[3])
    result = write_b210_tx_stream(stream, [[0j] * 8], chunk_size=4)
    assert result == {
        "samples_sent": 7,  # 首块 sent=3 + 次块足量 4
        "blocks": 2,
        "underruns": 1,
        "invalid_zeroed": 0,
    }


def test_four_consecutive_underruns_raise_backend_error():
    """连续 4 次欠载 > 默认阈值 3 → BackendError，第 4 块即熔断且 end() 仍被调用。"""
    stream = FakeStream(send_results=[0, 0, 0, 0, 99])
    with pytest.raises(BackendError, match="欠载"):
        write_b210_tx_stream(stream, [[1j]] * 5, chunk_size=8)
    assert stream.events.count("send") == 4  # 第 5 块未下发
    assert stream.events[-1] == "end"  # 异常路径 finally 兜底 end()


def test_underruns_exactly_at_limit_completes():
    """恰好 3 次（= 默认阈值）不熔断：超阈语义是 > 而非 >=。"""
    stream = FakeStream(send_results=[0, 0, 0])
    result = write_b210_tx_stream(stream, [[0j] * 3], chunk_size=1)
    assert result == {
        "samples_sent": 0,
        "blocks": 3,
        "underruns": 3,
        "invalid_zeroed": 0,
    }


def test_send_runtime_error_wrapped_with_cause():
    """send 抛 RuntimeError → BackendError 包装透传，原异常挂在 __cause__。"""
    stream = FakeStream(send_results=[4, RuntimeError("boom")])
    with pytest.raises(BackendError) as excinfo:
        write_b210_tx_stream(stream, [[0j] * 8], chunk_size=4)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert "boom" in str(excinfo.value)


def test_on_progress_exception_swallowed(caplog):
    """on_progress 回调异常被吞掉并记录：发送不中断、后续块仍被调用且拿到累计值。"""
    calls = []

    def bad_progress(sent_total):
        calls.append(sent_total)
        raise ValueError("callback boom")

    stream = FakeStream()
    with caplog.at_level("WARNING"):
        result = write_b210_tx_stream(
            stream, [[0j] * 10], chunk_size=4, on_progress=bad_progress
        )
    assert calls == [4, 8, 10]  # 每块下发后调用，参数为累计已发样本数
    assert result == {
        "samples_sent": 10,
        "blocks": 3,
        "underruns": 0,
        "invalid_zeroed": 0,
    }
    assert any("on_progress" in r.getMessage() for r in caplog.records)


def test_iq_element_normalization_counts_invalid():
    """元素规整：complex 原样、二元组转 complex、裸实数/垃圾置 0j 并计数。"""
    block = [
        1 + 2j,        # complex 原样
        (1.0, -2.0),   # 二元组 → 1-2j
        [3, 4],        # 二元 list → 3+4j
        5.5,           # 裸实数 → 0j 计数
        7,             # 裸 int → 0j 计数
        "garbage",     # 垃圾 → 0j 计数
        None,          # 垃圾 → 0j 计数
        (1, 2, 3),     # 三元组 → 0j 计数
        (1, "x"),      # 分量非数 → 0j 计数
        (True, 0),     # bool 分量拒收 → 0j 计数
    ]
    stream = FakeStream()
    result = write_b210_tx_stream(stream, [block], chunk_size=64)
    assert result == {
        "samples_sent": 10,
        "blocks": 1,
        "underruns": 0,
        "invalid_zeroed": 7,
    }
    assert stream.chunks[0] == [
        1 + 2j, 1 - 2j, 3 + 4j, 0j, 0j, 0j, 0j, 0j, 0j, 0j,
    ]


def test_end_exception_swallowed_and_result_intact():
    """end() 异常被吞掉：不影响返回统计，end 事件仍入序。"""
    stream = FakeStream(end_raises=RuntimeError("end boom"))
    result = write_b210_tx_stream(stream, [[1j, 2j]], chunk_size=4)
    assert result == {
        "samples_sent": 2,
        "blocks": 1,
        "underruns": 0,
        "invalid_zeroed": 0,
    }
    assert stream.events[-1] == "end"


def test_empty_iterator_zero_stats():
    """空迭代器：零统计正常返回，仍走 start/end 生命周期，无任何 send。"""
    stream = FakeStream()
    result = write_b210_tx_stream(stream, [], chunk_size=4096)
    assert result == {
        "samples_sent": 0,
        "blocks": 0,
        "underruns": 0,
        "invalid_zeroed": 0,
    }
    assert stream.events == ["start", "end"]
    assert stream.chunks == []


def test_chunk_size_non_positive_raises_valueerror_before_start():
    """chunk_size<=0 → ValueError，且校验先于 start()，不触碰句柄。"""
    for bad in (0, -1):
        stream = FakeStream()
        with pytest.raises(ValueError, match="chunk_size"):
            write_b210_tx_stream(stream, [[1j]], chunk_size=bad)
        assert stream.events == []


def test_start_end_methods_optional():
    """鸭子句柄只有 send（缺 start/end 方法）→ 跳过生命周期调用，正常送达。"""

    class SendOnly:
        def __init__(self):
            self.chunks = []

        def send(self, chunk):
            self.chunks.append(list(chunk))
            return {"sent": len(chunk)}

    handle = SendOnly()
    result = write_b210_tx_stream(handle, [[1j, 2j, 3j]], chunk_size=2)
    assert result == {
        "samples_sent": 3,
        "blocks": 2,
        "underruns": 0,
        "invalid_zeroed": 0,
    }
    assert [len(c) for c in handle.chunks] == [2, 1]


# ---- B5 对抗审查缺陷回归（低#4 chunk_size 正 int / 低#5 start 异常 end 兜底）----


def test_defect_b5_4_chunk_size_rejects_bool_float_and_non_int():
    """低#4：chunk_size 须正 int——bool/float/str/None 一律 ValueError，且先于 start()。"""
    for bad in (True, 4.5, 4096.0, "4096", None, -3):
        stream = FakeStream()
        with pytest.raises(ValueError, match="chunk_size"):
            write_b210_tx_stream(stream, [[1j]], chunk_size=bad)
        assert stream.events == []  # 校验先于 start()，不触碰句柄
    # 正 int 照常（bool 之外的 int 子类语义不受影响）
    assert write_b210_tx_stream(FakeStream(), [[1j, 2j]], chunk_size=1)["blocks"] == 2


def test_defect_b5_5_start_exception_end_still_attempted():
    """低#5：start() 抛异常 → finally 仍兜底尽力 end()（突发终止不丢）。"""

    class StartBoomStream(FakeStream):
        def start(self):
            self.events.append("start")
            raise RuntimeError("start: stream not configured")

    stream = StartBoomStream()
    with pytest.raises(RuntimeError, match="stream not configured"):
        write_b210_tx_stream(stream, [[1j]])
    assert stream.events == ["start", "end"]  # end() 兜底已调
    assert stream.chunks == []  # start 失败后不进入发送


def test_defect_b5_5_start_exception_without_end_logs_skipped_end(caplog):
    """低#5：start() 抛异常且句柄无 end() → 记 skipped_end 日志（不静默丢突发终止）。"""

    class NoEndStream:
        def __init__(self):
            self.calls: list[str] = []

        def start(self):
            self.calls.append("start")
            raise RuntimeError("start boom")

        def send(self, chunk):  # pragma: no cover - start 失败不应触达 send
            raise AssertionError("send 不应被调用")

    handle = NoEndStream()
    with caplog.at_level("WARNING"):
        with pytest.raises(RuntimeError, match="start boom"):
            write_b210_tx_stream(handle, [[1j]])
    assert any("skipped_end" in r.getMessage() for r in caplog.records)


def test_defect_b5_5_end_attempted_on_send_failure_path():
    """低#5（返回/异常路径 end 尽力）：send 失败路径 end() 已有兜底——固化回归。"""
    stream = FakeStream(send_results=[RuntimeError("send boom")])
    with pytest.raises(BackendError, match="send boom"):
        write_b210_tx_stream(stream, [[1j]], chunk_size=4)
    assert stream.events == ["start", "send", "end"]
