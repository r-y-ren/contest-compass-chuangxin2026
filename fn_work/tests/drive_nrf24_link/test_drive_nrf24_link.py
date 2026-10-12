"""drive_nrf24_link 对抗测试：正常帧流增量口径、坏帧处置（阈下清零/超阈先停发射再抛）、
断开处置（源异常先停发射）、行流耗尽自然结束、样本形状（键集/无 rssi/rpd bool/时间戳
单调）、config/ctx 即刻校验、运行级 run_token 贯通停发射。"""
from __future__ import annotations

import pytest

from src.drive_nrf24_link.drive_nrf24_link import LinkError, drive_nrf24_link
from src.shared.stop_transmit_safely import stop_transmit_safely


class _RecordingBackend:
    """记录调用顺序的假停发射后端（stop_tx → set_tx_gain(0)）。"""

    def __init__(self) -> None:
        self.journal: list = []

    def stop_tx(self) -> None:
        self.journal.append("stop_tx")

    def set_tx_gain(self, gain) -> None:
        self.journal.append(("set_tx_gain", gain))


def _line(seq: int, sent: int, lost: int, retries: int, rpd: int) -> str:
    return f"NRF,{seq},{sent},{lost},{retries},{rpd}"


def _drive(lines, ctx=None, **overrides):
    """以行序列构造 config 并驱动（overrides 覆写 baud/max_bad_streak 等键）。"""
    config = {"port": "/dev/ttyUSB0", "source": iter(lines)}
    config.update(overrides)
    return drive_nrf24_link(config, ctx=ctx)


def test_dut_nrf24_normal_stream_per_increments():
    """① 正常帧流：一好帧一样本，per_raw=lost 增量/sent 增量、retries 为窗增量。"""
    lines = [
        _line(1, 100, 5, 3, 1),
        _line(2, 200, 12, 8, 0),
        _line(3, 330, 20, 15, 1),
    ]
    samples = list(_drive(lines, baud=115200))
    assert len(samples) == 3
    assert all(s["link"] == "nrf24" for s in samples)
    assert samples[0]["per_raw"] == pytest.approx(5 / 100)
    assert samples[1]["per_raw"] == pytest.approx(7 / 100)
    assert samples[2]["per_raw"] == pytest.approx(8 / 130)
    assert [s["retries"] for s in samples] == [3, 5, 7]
    assert all("per_note" not in s for s in samples)


def test_dut_nrf24_no_delta_note():
    """② 无增量窗：sent 增量为 0 → per_raw=None + per_note='no_delta'，后续窗恢复。"""
    lines = [
        _line(1, 100, 5, 3, 0),
        _line(2, 100, 5, 3, 1),  # 计数原地踏步
        _line(3, 150, 9, 9, 0),
    ]
    samples = list(_drive(lines))
    assert samples[0]["per_raw"] == pytest.approx(0.05)
    assert samples[1]["per_raw"] is None
    assert samples[1]["per_note"] == "no_delta"
    assert samples[1]["retries"] == 0
    assert samples[1]["rpd"] is True  # 门限位逐帧独立，无增量窗照常透传
    assert samples[2]["per_raw"] == pytest.approx(4 / 50)
    assert "per_note" not in samples[2]


def test_dut_nrf24_bad_streak_stops_tx_before_link_error():
    """③ 坏帧超阈：先停发射（两步齐全）再抛 LinkError——异常传出即证停发射已发生。"""
    be = _RecordingBackend()
    lines = [_line(1, 50, 2, 1, 0), "garbage", "NRF,1,2", "", 123]
    gen = _drive(lines, ctx={"backend": be}, max_bad_streak=3)
    collected = []
    with pytest.raises(LinkError) as ei:
        for sample in gen:
            collected.append(sample)
    assert len(collected) == 1  # 首个好帧已产出，随后 3 连坏触发
    assert be.journal == ["stop_tx", ("set_tx_gain", 0)]
    assert ei.value.stop_result is not None
    assert ei.value.stop_result["status"] == "stopped"
    assert "帧损坏超阈" in str(ei.value)


def test_dut_nrf24_sporadic_bad_frames_tolerated_and_streak_resets():
    """④ 零星坏帧：好帧将连续坏帧计数清零，阈下永不触发停发射/LinkError。"""
    be = _RecordingBackend()
    lines = [
        "x",
        _line(1, 10, 0, 0, 0),
        "y",
        _line(2, 20, 1, 1, 1),
        "z",
        _line(3, 30, 2, 2, 0),
    ]
    samples = list(_drive(lines, ctx={"backend": be}, max_bad_streak=3))
    assert len(samples) == 3  # 坏帧只跳过不产出
    assert be.journal == []
    assert samples[2]["per_raw"] == pytest.approx(1 / 10)


def test_dut_nrf24_lines_exhausted_natural_end_no_stop():
    """⑤ 行流耗尽自然结束：正常收尾不产错、不停发射（收尾停发射归编排方）；空流空产。"""
    be = _RecordingBackend()
    samples = list(_drive([_line(1, 10, 1, 0, 0), _line(2, 25, 3, 2, 1)], ctx={"backend": be}))
    assert len(samples) == 2
    assert be.journal == []
    assert list(_drive([], ctx={"backend": be})) == []


def test_dut_nrf24_rpd_passthrough_bool():
    """⑥ rpd 门限位透传：0/1 → bool False/True；bytes 行与 \\r\\n 行尾同径解析。"""
    lines = [
        b"NRF,1,10,0,0,0\r\n",
        "NRF,2,20,1,1,1",
        b"NRF,3,30,3,2,0",
    ]
    samples = list(_drive(lines))
    assert [s["rpd"] for s in samples] == [False, True, False]
    assert all(isinstance(s["rpd"], bool) for s in samples)


def test_dut_nrf24_sample_has_no_rssi_key():
    """⑦ 口径断言：NRF24 样本不含 rssi/rssi_dbm 键（无 RSSI 口径）。"""
    lines = [
        _line(1, 10, 1, 0, 1),
        _line(2, 10, 1, 0, 0),  # 无增量窗同样不带
        _line(3, 20, 2, 1, 1),
    ]
    for sample in list(_drive(lines)):
        assert "rssi" not in sample
        assert "rssi_dbm" not in sample


def test_dut_nrf24_invalid_config_rejected_eagerly():
    """⑧ config 非法即刻拒（ValueError，调用时抛出不消费 source）。"""
    bad_configs = [
        None,
        "/dev/ttyUSB0",
        7,
        {"baud": 115200, "source": []},  # 缺 port
        {"port": "", "source": []},
        {"port": "   ", "source": []},
        {"port": 3, "source": []},
        {"port": "/dev/x", "baud": True, "source": []},
        {"port": "/dev/x", "baud": 0, "source": []},
        {"port": "/dev/x", "baud": "115200", "source": []},
        {"port": "/dev/x", "baud": 115200.0, "source": []},
        {"port": "/dev/x"},  # 缺 source
        {"port": "/dev/x", "source": None},
        {"port": "/dev/x", "source": "NRF,0,1,0,0,0"},  # 整段文本 footgun
        {"port": "/dev/x", "source": b"NRF,0,1,0,0,0"},
        {"port": "/dev/x", "source": 42},  # 不可迭代
        {"port": "/dev/x", "source": [], "max_bad_streak": 0},
        {"port": "/dev/x", "source": [], "max_bad_streak": True},
        {"port": "/dev/x", "source": [], "max_bad_streak": 2.5},
    ]
    for config in bad_configs:
        with pytest.raises(ValueError):
            drive_nrf24_link(config)


def test_dut_nrf24_invalid_ctx_rejected_eagerly():
    """⑧b ctx 非 dict/None 即刻拒（ValueError）。"""
    with pytest.raises(ValueError):
        drive_nrf24_link({"port": "/dev/x", "source": []}, ctx=123)


def test_dut_nrf24_timestamps_monotonic_nondecreasing():
    """⑨ 时间戳：float 单调钟 ms，严格非降且恒正。"""
    lines = [_line(i, i * 10, i, 0, 0) for i in range(1, 7)]
    timestamps = [s["timestamp_ms"] for s in list(_drive(lines))]
    assert all(isinstance(t, float) and t > 0 for t in timestamps)
    assert all(later >= earlier for earlier, later in zip(timestamps, timestamps[1:]))


def test_dut_nrf24_sample_key_set_exact():
    """⑩ 键集：常规样本恰 5 键；不可比窗恰 5 键+per_note，别无他键。"""
    lines = [
        _line(1, 100, 5, 3, 1),
        _line(2, 100, 5, 3, 0),  # 无增量窗
        _line(3, 150, 9, 9, 1),
    ]
    samples = list(_drive(lines))
    base = {"timestamp_ms", "link", "per_raw", "retries", "rpd"}
    assert set(samples[0]) == base
    assert set(samples[1]) == base | {"per_note"}
    assert set(samples[2]) == base


def test_dut_nrf24_counter_regression_rebaselines():
    """⑪ 计数回退（复位/回绕）：per_note='counter_reset'、per_raw=None、重定基线后恢复。"""
    lines = [
        _line(1, 100, 5, 3, 0),
        _line(2, 50, 2, 1, 0),  # sent/lost/retries 全回退
        _line(3, 120, 6, 4, 1),
    ]
    samples = list(_drive(lines))
    assert samples[1]["per_raw"] is None
    assert samples[1]["per_note"] == "counter_reset"
    assert samples[1]["retries"] == 0  # 回退窗不硬算负增量
    assert samples[2]["per_raw"] == pytest.approx(4 / 70)  # 以回退后读数为新基线
    assert samples[2]["retries"] == 3


def test_dut_nrf24_source_exception_stops_then_link_error():
    """⑫ 断开处置：source 迭代抛异常 → 已产出样本保留，先停发射再 LinkError（链上原异常）。"""
    be = _RecordingBackend()

    def _src():
        yield _line(1, 50, 2, 1, 0)
        yield _line(2, 80, 5, 2, 0)
        raise RuntimeError("serial disconnect")

    gen = drive_nrf24_link({"port": "/dev/ttyUSB0", "source": _src()}, ctx={"backend": be})
    collected = []
    with pytest.raises(LinkError) as ei:
        for sample in gen:
            collected.append(sample)
    assert len(collected) == 2
    assert isinstance(ei.value.__cause__, RuntimeError)
    assert "serial disconnect" in str(ei.value.__cause__)
    assert be.journal == ["stop_tx", ("set_tx_gain", 0)]
    assert ei.value.stop_result["status"] == "stopped"


def test_dut_nrf24_lazy_until_first_next():
    """⑬ 惰性：调用只做校验不消费 source，返回迭代器，首个 next 才开始读行。"""
    consumed: list = []

    def _src():
        for text in [_line(1, 10, 1, 0, 0), _line(2, 20, 2, 1, 1)]:
            consumed.append(text)
            yield text

    gen = drive_nrf24_link({"port": "/dev/ttyUSB0", "source": _src()})
    assert consumed == []
    assert hasattr(gen, "__next__")
    first = next(gen)
    assert len(consumed) == 1
    assert first["link"] == "nrf24"


def test_dut_nrf24_external_run_token_threaded_to_stop():
    """⑭ token 贯通：外部 run_token 原样用于停发射——同 token 再停 already_stopped、
    换 token 重实停（运行级幂等，未被 '_auto:' 覆盖）。"""
    be = _RecordingBackend()
    with pytest.raises(LinkError):
        list(_drive(["a", "b", "c"], ctx={"backend": be, "run_token": "tok-1"}, max_bad_streak=3))
    assert stop_transmit_safely(be, run_token="tok-1")["status"] == "already_stopped"
    assert stop_transmit_safely(be, run_token="tok-2")["status"] == "stopped"
