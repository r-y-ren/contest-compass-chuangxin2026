"""read_b210_rx_stream 对抗单测：FakeRecv 鸭子句柄全路径覆盖（无硬件）。

覆盖：保序/ts 连续/device_ts 透传；溢出计数与恢复；连续溢出超阈→BackendError；
recv 异常包装（__cause__）；max_blocks 恰停不预读；空块跳过不占 ts；max_blocks=0；
缺 recv→ValueError（调用即抛）；非复数样本原样透传；惰性热停止；overflow_limit
参数化；空块溢出计数与非溢出空块清零连续段。
"""
from __future__ import annotations

import pytest

from src.open_b210_backend.read_b210_rx_stream import BackendError, read_b210_rx_stream


class FakeRecv:
    """鸭子流句柄：按脚本回放 recv 结果/异常，记录每次调用的 n。脚本耗尽即断言失败
    （防止被测生成器多读时测试静默空转）。"""

    def __init__(self, script=()):
        self.script = list(script)
        self.calls: list[int] = []

    def recv(self, n):
        self.calls.append(n)
        if not self.script:
            raise AssertionError("FakeRecv 脚本已耗尽：被测代码多读了一块")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def blk(seq, n=3, overflow=False, device_ts=None):
    """构造一块确定性复样本（内容随 seq 可区分，device_ts 默认随 seq 递增）。"""
    return {
        "samples": [complex(seq * n + k, -k) for k in range(n)],
        "overflow": overflow,
        "ts": 10_000 * (seq + 1) if device_ts is None else device_ts,
    }


def empty_blk(overflow=False, device_ts=0):
    """空样本块（recv 空转）：溢出标志可独立设置。"""
    return {"samples": [], "overflow": overflow, "ts": device_ts}


def test_blocks_in_order_with_contiguous_ts_and_device_ts_passthrough():
    fake = FakeRecv([blk(i) for i in range(5)])
    out = list(read_b210_rx_stream(fake, max_blocks=5))
    assert [b["ts"] for b in out] == [0, 1, 2, 3, 4]  # 产出序号连续起于 0
    assert [b["device_ts"] for b in out] == [10_000 * (i + 1) for i in range(5)]
    assert [b["samples"] for b in out] == [blk(i)["samples"] for i in range(5)]
    assert all(b["overflow"] is False for b in out)
    assert all(set(b) == {"samples", "ts", "overflow", "device_ts"} for b in out)
    assert fake.calls and all(isinstance(n, int) and n > 0 for n in fake.calls)


def test_overflow_flag_counted_and_streak_resets_on_clean_block():
    # 6 连溢出 + 1 净块 + 6 连溢出：若无清零逻辑累计 12 连续必超默认阈 10
    script = (
        [blk(i, overflow=True) for i in range(6)]
        + [blk(6)]
        + [blk(i, overflow=True) for i in range(6, 12)]
    )
    out = list(read_b210_rx_stream(FakeRecv(script), max_blocks=13))
    assert len(out) == 13
    assert [b["ts"] for b in out] == list(range(13))  # 溢出块照样产出并占号
    assert sum(1 for b in out if b["overflow"]) == 12
    assert out[6]["overflow"] is False  # 净块标志如实透传


def test_eleven_consecutive_overflows_raise_backend_error():
    fake = FakeRecv([blk(i, overflow=True) for i in range(11)])
    out = []
    with pytest.raises(BackendError, match="溢出"):
        for block in read_b210_rx_stream(fake):
            out.append(block)
    assert len(out) == 10  # 默认阈 10：第 11 个连续溢出块判阈即抛、不产出


def test_recv_exception_wrapped_as_backend_error_with_cause():
    boom = RuntimeError("UHD device disconnected")
    fake = FakeRecv([blk(0), boom])  # 首块正常，第二块 recv 抛
    out = []
    with pytest.raises(BackendError, match="UHD device disconnected") as exc_info:
        for block in read_b210_rx_stream(fake):
            out.append(block)
    assert len(out) == 1  # 已产出块不吞
    assert exc_info.value.__cause__ is boom  # 原因链保留


def test_max_blocks_yields_exactly_and_reads_no_extra():
    fake = FakeRecv([blk(i) for i in range(10)])
    out = list(read_b210_rx_stream(fake, max_blocks=3))
    assert [b["ts"] for b in out] == [0, 1, 2]
    assert len(fake.calls) == 3  # 恰产 3 块后停：不做第 4 次投机预读


def test_empty_blocks_skipped_without_consuming_ts():
    script = [blk(0), empty_blk(), blk(1), empty_blk(), empty_blk(), blk(2)]
    out = list(read_b210_rx_stream(FakeRecv(script), max_blocks=3))
    assert [b["ts"] for b in out] == [0, 1, 2]  # 空块跳过且不占 ts
    assert [b["device_ts"] for b in out] == [10_000, 20_000, 30_000]


def test_max_blocks_zero_is_empty_and_reads_nothing():
    fake = FakeRecv([blk(0)])
    assert list(read_b210_rx_stream(fake, max_blocks=0)) == []
    assert fake.calls == []  # 一次 recv 都不发生


def test_missing_or_uncallable_recv_raises_value_error_eagerly():
    with pytest.raises(ValueError, match="recv"):
        read_b210_rx_stream(object())  # 调用即抛（非生成器函数的惰性首 next）
    with pytest.raises(ValueError, match="recv"):
        read_b210_rx_stream(type("H", (), {"recv": 5})())  # 属性在但不可调用
    fake = FakeRecv([])
    with pytest.raises(ValueError):
        read_b210_rx_stream(fake, max_blocks=-1)  # 参数域一并即刻校验
    with pytest.raises(ValueError):
        read_b210_rx_stream(fake, overflow_limit=-1)


def test_non_complex_samples_passed_through_verbatim():
    weird = [1.5, None, "iq", 2 + 3j]
    fake = FakeRecv([{"samples": list(weird), "overflow": False, "ts": 77}])
    out = list(read_b210_rx_stream(fake, max_blocks=1))
    assert out[0]["samples"] == weird  # 不做类型规整/换算
    assert all(a is b for a, b in zip(out[0]["samples"], weird))  # 元素对象原样
    assert out[0]["device_ts"] == 77


def test_lazy_generator_reads_only_on_demand():
    fake = FakeRecv([blk(i) for i in range(5)])
    gen = read_b210_rx_stream(fake)  # max_blocks=None：无限语义
    assert fake.calls == []          # 未取即不读（热停止的惰性面）
    assert next(gen)["ts"] == 0
    assert len(fake.calls) == 1
    next(gen)
    gen.close()                      # 消费方断流
    assert len(fake.calls) == 2      # 断流后不再读


def test_overflow_limit_parameterized():
    script = [blk(i, overflow=True) for i in range(3)]
    out = []
    with pytest.raises(BackendError):
        for block in read_b210_rx_stream(FakeRecv(script), overflow_limit=2):
            out.append(block)
    assert len(out) == 2  # 阈 2：第 3 个连续溢出块即抛


def test_overflow_on_empty_block_counts_and_clean_empty_resets():
    # 空块带溢出：设备级状态照样计数（与是否携带样本无关）——阈 2 时第 3 个即抛
    with pytest.raises(BackendError):
        list(read_b210_rx_stream(FakeRecv([empty_blk(overflow=True)] * 3), overflow_limit=2))
    # 非溢出空块中断连续段：6 溢出 + 空净块 + 6 溢出（若不清零则 12 连续必超阈 10）
    script = (
        [blk(i, overflow=True) for i in range(6)]
        + [empty_blk()]
        + [blk(i, overflow=True) for i in range(6, 12)]
    )
    out = list(read_b210_rx_stream(FakeRecv(script), max_blocks=12))
    assert len(out) == 12  # 12 个非空块全部产出（空块跳过不产出）


# ---- B5 对抗审查缺陷回归（中#2 RX 空转封顶 / 低#12 partial_meta + len() 判空）----


def test_defect_b5_2_idle_breaker_default_200_trips_on_201st_empty_block():
    """中#2：连续空块默认阈 200——第 201 块熔断，消息含空转计数与"RX 无数据"提示。"""
    fake = FakeRecv([empty_blk()] * 201)
    with pytest.raises(BackendError) as excinfo:
        list(read_b210_rx_stream(fake))
    msg = str(excinfo.value)
    assert "201" in msg and "idle_limit=200" in msg  # 空转计数与阈值入消息
    assert "RX 无数据" in msg and "增益/天线/频率" in msg  # 排障提示文案
    assert fake.calls and len(fake.calls) == 201  # 第 201 次 recv 即熔断，不再空转
    # 恰 200 块不熔断：随后有数据应正常产出（">" 语义）
    fake2 = FakeRecv([empty_blk()] * 200 + [blk(0)])
    out = list(read_b210_rx_stream(fake2, max_blocks=1))
    assert out[0]["ts"] == 0 and len(out[0]["samples"]) == 3


def test_defect_b5_2_idle_limit_parameterized_and_eagerly_validated():
    """中#2：idle_limit 参数化；非法取值（负数/bool）调用即抛 ValueError，不读首块。"""
    for bad in (-1, True, 1.5):
        fake = FakeRecv([blk(0)])
        with pytest.raises(ValueError, match="idle_limit"):
            read_b210_rx_stream(fake, idle_limit=bad)
        assert fake.calls == []
    fake = FakeRecv([empty_blk()] * 4)
    with pytest.raises(BackendError, match="RX 无数据"):
        list(read_b210_rx_stream(fake, idle_limit=3))  # 第 4 个连续空块熔断


def test_defect_b5_2_idle_counter_resets_on_data_block():
    """中#2：连续语义——携带样本的块清零空转计数，两段 3 空块（阈 3）不熔断。"""
    script = [empty_blk()] * 3 + [blk(0)] + [empty_blk()] * 3 + [blk(1)]
    out = list(read_b210_rx_stream(FakeRecv(script), max_blocks=2, idle_limit=3))
    assert [b["ts"] for b in out] == [0, 1]


def test_defect_b5_12_missing_meta_keys_defaults_with_partial_meta_flag():
    """低#12：recv dict 缺 'ts'/'overflow' → 缺省值兜底 + 产出块标注 partial_meta=True。"""
    script = [
        {"samples": [1j, 2j]},  # overflow 与 ts 全缺
        {"samples": [3j], "ts": 9},  # 仅缺 overflow
        {"samples": [4j], "overflow": True},  # 仅缺 ts
    ]
    out = list(read_b210_rx_stream(FakeRecv(script), max_blocks=3))
    assert out[0]["overflow"] is False  # 缺省
    assert out[0]["device_ts"] is None  # 缺省
    assert out[0]["partial_meta"] is True
    assert out[1]["overflow"] is False
    assert out[1]["device_ts"] == 9  # 在的键如实透传
    assert out[1]["partial_meta"] is True
    assert out[2]["overflow"] is True
    assert out[2]["device_ts"] is None
    assert out[2]["partial_meta"] is True
    # 键全的块不附 partial_meta（缺省不静默，但完整块不加噪声键）
    (full_block,) = list(read_b210_rx_stream(FakeRecv([blk(0)]), max_blocks=1))
    assert "partial_meta" not in full_block


def test_defect_b5_12_numpy_samples_emptiness_judged_by_len():
    """低#12：samples 判空用 len()——numpy 数组 not 真值判定会 ValueError 直接炸。"""
    np = pytest.importorskip("numpy")
    arr = np.array([1 + 1j, 2 + 2j], dtype=np.complex64)
    empty_arr = np.array([], dtype=np.complex64)
    script = [
        {"samples": arr, "overflow": False, "ts": 1},
        {"samples": empty_arr, "overflow": False, "ts": 2},
        {"samples": arr, "overflow": False, "ts": 3},
    ]
    out = list(read_b210_rx_stream(FakeRecv(script), max_blocks=2))
    assert len(out) == 2  # 空数组按 len()==0 跳过不炸、不产出
    assert out[0]["samples"] == [1 + 1j, 2 + 2j]
    assert out[1]["ts"] == 1  # 第二个非空块占产出序号 1
