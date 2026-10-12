"""drive_esp32_link 对抗单测（slug=dut_esp32 的 B11 顶层：ESP32 链路驱动，lines 注入）。"""
import sys
import types

import pytest

from src.drive_esp32_link.drive_esp32_link import LinkError, drive_esp32_link

# 正常样本的精确键集（per_note/seq_rollback 为条件附加键）
_BASE_KEYS = {
    "timestamp_ms",
    "link",
    "seq",
    "per_raw",
    "per_cum",
    "retries",
    "rssi_dbm",
    "source",
}


def _frame(seq, sent, err, retries=0, rssi="-62.5"):
    """构造一行合法 ESP32 帧：ESP,<seq>,<sent>,<err>,<retries>,<rssi>。"""
    return f"ESP,{seq},{sent},{err},{retries},{rssi}"


def _lines_cfg(lines, **extra):
    cfg = {"source": "lines", "lines": lines}
    cfg.update(extra)
    return cfg


class _FakeBackend:
    """记录停发射调用序的鸭子后端（stop_transmit_safely 依序调 stop_tx→set_tx_gain(0)）。"""

    def __init__(self):
        self.calls = []

    def stop_tx(self):
        self.calls.append("stop_tx")
        return {"status": "no_tx"}

    def set_tx_gain(self, gain):
        self.calls.append(f"set_tx_gain:{gain}")
        return {"status": "no_tx"}


class _ExplodingLines:
    """先吐若干行再抛 OSError（模拟串口读取中途断开）。"""

    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return self

    def __next__(self):
        if self._items:
            return self._items.pop(0)
        raise OSError("device disconnected")


def _fake_serial_module(monkeypatch, serial_impl):
    """把假 serial 模块塞进 sys.modules（覆盖真实 pyserial 存在与否的环境差异）。"""
    fake = types.ModuleType("serial")

    class _FakeSerialException(Exception):
        pass

    fake.SerialException = _FakeSerialException
    fake.Serial = serial_impl
    monkeypatch.setitem(sys.modules, "serial", fake)
    return fake


def test_dut_esp32_normal_three_frames_per_incremental():
    lines = [_frame(1, 100, 1), _frame(2, 200, 4), _frame(3, 300, 4)]
    samples = list(drive_esp32_link(_lines_cfg(lines)))
    assert [s["seq"] for s in samples] == [1, 2, 3]
    # 增量口径：本帧 err−上帧 err / 本帧 sent−上帧 sent（首帧以 0 为基线）
    assert samples[0]["per_raw"] == pytest.approx(1 / 100)
    assert samples[1]["per_raw"] == pytest.approx(3 / 100)  # (4-1)/(200-100)
    assert samples[2]["per_raw"] == pytest.approx(0.0)  # (4-4)/(300-200)
    # 累计口径：本帧 err/sent
    assert samples[0]["per_cum"] == pytest.approx(1 / 100)
    assert samples[1]["per_cum"] == pytest.approx(4 / 200)
    assert samples[2]["per_cum"] == pytest.approx(4 / 300)
    assert all(s["link"] == "esp32" and s["source"] == "esp32" for s in samples)
    assert all(s["retries"] == 0 and s["rssi_dbm"] == -62.5 for s in samples)
    assert all("per_note" not in s for s in samples)


def test_dut_esp32_no_sent_delta_per_none_with_note():
    lines = [_frame(1, 100, 2), _frame(2, 100, 2), _frame(3, 100, 5)]
    samples = list(drive_esp32_link(_lines_cfg(lines)))
    assert samples[0]["per_raw"] == pytest.approx(2 / 100)
    assert "per_note" not in samples[0]
    # sent 增量 0：不可比窗 per_raw=None+no_delta 注（即使 err 有跳变也不除零，
    # 更不得以 0.0 冒充零丢包判据证据——与 drive_nrf24_link 同口径）
    assert samples[1]["per_raw"] is None
    assert samples[1]["per_note"] == "no_delta"
    assert samples[2]["per_raw"] is None
    assert samples[2]["per_note"] == "no_delta"


def test_dut_esp32_seq_rollback_annotated_not_raised():
    lines = [_frame(10, 100, 1), _frame(3, 50, 0), _frame(11, 60, 0)]
    samples = list(drive_esp32_link(_lines_cfg(lines)))  # 回退不抛
    assert [s["seq"] for s in samples] == [10, 3, 11]
    assert "seq_rollback" not in samples[0]
    assert samples[1]["seq_rollback"] is True  # 3 < 10：计数器重置场景
    assert "seq_rollback" not in samples[2]
    # 重置帧 sent 回退（50<100）→ 不可比窗按 None+注；后续帧以重置值为新基线
    assert samples[1]["per_raw"] is None and samples[1]["per_note"] == "no_delta"
    assert samples[2]["per_raw"] == pytest.approx(0.0)  # (0-0)/(60-50)
    assert set(samples[1]) - _BASE_KEYS == {"per_note", "seq_rollback"}


def test_dut_esp32_delta_overflow_annotated_not_fatal():
    lines = [_frame(1, 100, 1), _frame(2, 110, 25), _frame(3, 210, 30)]
    samples = list(drive_esp32_link(_lines_cfg(lines)))  # 不杀流
    assert samples[0]["per_raw"] == pytest.approx(1 / 100)
    # err 增量 24 > sent 增量 10：物理不可能→per_raw=None+delta_overflow 注
    assert samples[1]["per_raw"] is None
    assert samples[1]["per_note"] == "delta_overflow"
    assert samples[1]["per_cum"] == pytest.approx(25 / 110)  # 累计口径照实
    # 流继续：后续窗恢复数值口径 (30-25)/(210-110)
    assert samples[2]["per_raw"] == pytest.approx(5 / 100)
    assert "per_note" not in samples[2]


def test_dut_esp32_cum_overflow_flagged_same_window():
    lines = [_frame(1, 100, 5), _frame(2, 200, 250)]
    samples = list(drive_esp32_link(_lines_cfg(lines)))
    # err 增量 245>100 → delta_overflow；同窗 per_cum=250/200>1 → cum_overflow 标记
    assert samples[1]["per_note"] == "delta_overflow"
    assert samples[1]["per_raw"] is None
    assert samples[1]["per_cum"] == pytest.approx(1.25)
    assert samples[1]["cum_overflow"] is True
    assert "cum_overflow" not in samples[0]  # 正常窗不带标记


def test_dut_esp32_err_rollback_counter_reset_err_then_recovered():
    lines = [_frame(1, 100, 10, retries=2), _frame(2, 200, 3, retries=7),
             _frame(3, 300, 8)]
    samples = list(drive_esp32_link(_lines_cfg(lines)))  # 不杀流
    assert samples[0]["per_raw"] == pytest.approx(10 / 100)
    # err 回退（3<10）而 sent 仍在涨（200>100）：err 计数回退=设备复位/回绕，与
    # drive_nrf24_link 的 counter_reset 语义对齐——per_raw=None+counter_reset_err 注，
    # 不得以 0.0 冒充零丢包判据证据；retries 照常透出、累计口径照实
    assert samples[1]["per_raw"] is None
    assert samples[1]["per_note"] == "counter_reset_err"
    assert samples[1]["per_cum"] == pytest.approx(3 / 200)
    assert samples[1]["retries"] == 7
    assert set(samples[1]) - _BASE_KEYS == {"per_note"}
    # 后续窗以回退后的 err=3 为新基线恢复正常数值口径 (8-3)/(300-200)
    assert samples[2]["per_raw"] == pytest.approx(5 / 100)
    assert "per_note" not in samples[2]


def test_dut_esp32_counter_reset_err_exclusive_with_no_delta_and_overflow():
    # 三态互斥构造：no_delta（sent 增量 0）/ counter_reset_err（err 回退而 sent 涨）/
    # delta_overflow（err 增量>sent 增量），每窗恰落一种、不叠加
    lines = [
        _frame(1, 100, 5),   # 首帧基线窗：正常数值
        _frame(2, 100, 5),   # sent 增量 0 且 err 增量 0 → no_delta（非 counter_reset_err）
        _frame(3, 200, 3),   # err 增量 -2<0 且 sent 增量 100>0 → counter_reset_err
        _frame(4, 210, 80),  # err 增量 77>sent 增量 10 → delta_overflow
    ]
    samples = list(drive_esp32_link(_lines_cfg(lines)))
    assert samples[0]["per_raw"] == pytest.approx(5 / 100)
    assert "per_note" not in samples[0]
    assert samples[1]["per_note"] == "no_delta"
    assert samples[2]["per_note"] == "counter_reset_err"
    assert samples[3]["per_note"] == "delta_overflow"
    # 每窗 per_note 与 per_raw=None 恰同现同缺（数值在位不带注，带注必为 None）
    for s in samples:
        assert ("per_note" in s) == (s["per_raw"] is None)


def test_dut_esp32_consecutive_bad_frames_stop_tx_before_link_error():
    backend = _FakeBackend()
    lines = [_frame(1, 100, 1)] + ["garbage,not,a,frame"] * 5
    gen = drive_esp32_link(_lines_cfg(lines), {"backend": backend})
    got = []
    with pytest.raises(LinkError) as excinfo:
        for sample in gen:
            got.append(sample)
    # 坏帧不产出样本；首帧好样本已产出
    assert [s["seq"] for s in got] == [1]
    # 事件序：LinkError 抛出时 stop_tx 已先于 set_tx_gain(0) 调用过
    assert backend.calls == ["stop_tx", "set_tx_gain:0"]
    assert "5" in str(excinfo.value)  # 默认阈 5（与 drive_nrf24_link 同缺省）


def test_dut_esp32_sparse_bad_frames_counter_reset_continues():
    lines = (
        ["nope"] * 4
        + [_frame(1, 100, 1)]
        + ["nope"] * 4
        + [_frame(2, 200, 2)]
    )
    samples = list(drive_esp32_link(_lines_cfg(lines)))  # 4<5 不抛
    assert [s["seq"] for s in samples] == [1, 2]
    assert samples[1]["per_raw"] == pytest.approx(1 / 100)


def test_dut_esp32_lines_exhaustion_ends_normally():
    gen = drive_esp32_link(_lines_cfg([_frame(1, 10, 0)]))
    assert next(gen)["seq"] == 1
    with pytest.raises(StopIteration):  # 耗尽=正常结束，不是错误
        next(gen)
    assert list(drive_esp32_link(_lines_cfg([]))) == []


def test_dut_esp32_invalid_source_value_error():
    for bad_source in ("usb", "", None, 123):
        with pytest.raises(ValueError, match="source"):
            drive_esp32_link({"source": bad_source, "lines": []})


def test_dut_esp32_non_dict_config_value_error():
    with pytest.raises(ValueError, match="serial_config"):
        drive_esp32_link(["ESP,1,2,3,4,NA"])
    with pytest.raises(ValueError, match="baud"):
        drive_esp32_link(_lines_cfg([], baud=0))
    with pytest.raises(ValueError, match="bad_frame_limit"):
        drive_esp32_link(_lines_cfg([], bad_frame_limit=0))


def test_dut_esp32_lines_source_requires_lines_value_error():
    with pytest.raises(ValueError, match="lines"):
        drive_esp32_link({"source": "lines"})
    with pytest.raises(ValueError, match="lines"):
        drive_esp32_link({"source": "lines", "lines": 42})


def test_dut_esp32_missing_pyserial_link_error_with_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "serial", None)  # 模拟 pyserial 未安装
    with pytest.raises(LinkError) as excinfo:
        list(drive_esp32_link({"source": "serial", "port": "/dev/ttyUSB0"}))
    msg = str(excinfo.value)
    assert "pyserial" in msg and "pip install" in msg


def test_dut_esp32_missing_port_with_importable_serial_link_error(monkeypatch):
    def _serial_ok(port, baud):
        raise AssertionError("port 缺失时不应触达串口打开")

    _fake_serial_module(monkeypatch, _serial_ok)
    with pytest.raises(LinkError) as excinfo:
        list(drive_esp32_link({"source": "serial"}))  # port 缺省 None
    assert "port" in str(excinfo.value)


def test_dut_esp32_serial_open_failure_stops_tx_then_link_error(monkeypatch):
    def _serial_boom(port, baud):
        raise RuntimeError(f"could not open port {port!r}")

    _fake_serial_module(monkeypatch, _serial_boom)
    backend = _FakeBackend()
    cfg = {"source": "serial", "port": "/dev/ttyUSB99", "baud": 115200}
    with pytest.raises(LinkError) as excinfo:
        list(drive_esp32_link(cfg, {"backend": backend}))
    assert backend.calls == ["stop_tx", "set_tx_gain:0"]  # 先停发射再抛
    assert "could not open port" in str(excinfo.value)


def test_dut_esp32_stream_read_failure_stops_tx_then_link_error():
    backend = _FakeBackend()
    lines = _ExplodingLines([_frame(1, 100, 1)])
    gen = drive_esp32_link(_lines_cfg(lines), {"backend": backend})
    got = []
    with pytest.raises(LinkError) as excinfo:
        for sample in gen:
            got.append(sample)
    assert [s["seq"] for s in got] == [1]  # 断开前的好帧已产出
    assert backend.calls == ["stop_tx", "set_tx_gain:0"]  # 事件序：停发射先于抛错
    assert "OSError" in str(excinfo.value) and "disconnected" in str(excinfo.value)


def test_dut_esp32_rssi_na_passthrough_none():
    lines = [_frame(1, 50, 0, rssi="NA"), _frame(2, 100, 0, rssi="NA")]
    samples = list(drive_esp32_link(_lines_cfg(lines)))
    assert [s["rssi_dbm"] for s in samples] == [None, None]


def test_dut_esp32_timestamp_ms_monotonic():
    lines = [_frame(i, i * 10, 0) for i in range(1, 7)]
    samples = list(drive_esp32_link(_lines_cfg(lines)))
    stamps = [s["timestamp_ms"] for s in samples]
    assert all(ts > 0 for ts in stamps)
    assert all(later >= earlier for earlier, later in zip(stamps, stamps[1:]))


def test_dut_esp32_sample_key_set():
    samples = list(drive_esp32_link(_lines_cfg([_frame(1, 100, 2)])))
    assert set(samples[0]) == _BASE_KEYS  # 正常样本恰为基线键集，无附加键
    values = samples[0]
    assert isinstance(values["timestamp_ms"], float)
    assert isinstance(values["seq"], int) and isinstance(values["per_raw"], float)
    assert isinstance(values["per_cum"], float) and isinstance(values["retries"], int)


def test_dut_esp32_custom_bad_frame_limit_threshold():
    # 阈值 3：第 3 个连续坏帧即断流
    backend = _FakeBackend()
    with pytest.raises(LinkError):
        list(drive_esp32_link(_lines_cfg(["x"] * 3, bad_frame_limit=3), {"backend": backend}))
    assert backend.calls == ["stop_tx", "set_tx_gain:0"]
    # 阈值 4：3 个坏帧+收尾好帧——不抛且好帧照常产出
    lines = ["x"] * 3 + [_frame(9, 30, 0)]
    samples = list(drive_esp32_link(_lines_cfg(lines, bad_frame_limit=4)))
    assert [s["seq"] for s in samples] == [9]


def test_dut_esp32_auto_run_token_two_rounds_both_actually_stop():
    """三轴中#2：ctx 未提供 token 时自生成 '_auto:' 写回——同 backend+同 ctx 两轮
    错误路径均实停（若无 token 机制，第二轮会被进程级幂等吞成 already_stopped）。"""
    backend = _FakeBackend()
    ctx = {"backend": backend}
    with pytest.raises(LinkError):
        list(drive_esp32_link(_lines_cfg(["x"] * 5), ctx))  # 默认阈 5
    assert ctx["run_token"].startswith("_auto:")
    assert backend.calls == ["stop_tx", "set_tx_gain:0"]
    # 第二轮（同 ctx 复用）：旧 '_auto:' token 换新 → 停发射运行级幂等仍实停
    token_first = ctx["run_token"]
    with pytest.raises(LinkError):
        list(drive_esp32_link(_lines_cfg(["x"] * 5), ctx))
    assert ctx["run_token"] != token_first
    assert ctx["run_token"].startswith("_auto:")
    assert backend.calls == ["stop_tx", "set_tx_gain:0"] * 2  # 两轮各实停一次


def test_dut_esp32_external_run_token_not_overwritten():
    """外部 token（无 '_auto:' 前缀）不被覆盖，两轮沿用同 token。"""
    backend = _FakeBackend()
    ctx = {"backend": backend, "run_token": "caller-token"}
    with pytest.raises(LinkError):
        list(drive_esp32_link(_lines_cfg(["x"] * 5, bad_frame_limit=2), ctx))
    assert ctx["run_token"] == "caller-token"
    assert backend.calls == ["stop_tx", "set_tx_gain:0"]
    # 同外部 token 再触发：停发射幂等 already_stopped（不再实打两步）
    with pytest.raises(LinkError):
        list(drive_esp32_link(_lines_cfg(["x"] * 2, bad_frame_limit=2), ctx))
    assert ctx["run_token"] == "caller-token"
    assert backend.calls == ["stop_tx", "set_tx_gain:0"]  # 未增长
