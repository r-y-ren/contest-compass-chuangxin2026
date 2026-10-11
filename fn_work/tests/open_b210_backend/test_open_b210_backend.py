"""open_b210_backend 对抗测试（slug=backend_b210）：注入 FakeTransport 覆盖开流/注册/域错路径 + 真机在位一例。"""
from __future__ import annotations

import logging

import pytest

from src.manage_backend_registry.lookup_backend import lookup_backend
from src.manage_backend_registry.register_backend import BackendError
from src.open_b210_backend import open_b210_backend as b210_module
from src.open_b210_backend.open_b210_backend import (
    B210Backend,
    open_b210_backend,
    probe_b210_available,
)
from src.resolve_clock_reference.resolve_clock_reference import resolve_clock_reference

# uhd_find_devices 有真机时的输出样例（在位标记 '-- UHD Device'）。
_DEVICE_PRESENT_OUTPUT = (
    "-- UHD Device 0\nDevice Address:\n    serial: 31B92DD\n    product: B210\n    type: b200"
)


class FakeDevice:
    """鸭子设备句柄：全 set/get 对（存值直读回，offsets 可造回读偏差），missing 可按名缺方法。"""

    _ALL = tuple(
        f"{verb}_{prefix}_{suffix}"
        for verb in ("set", "get")
        for prefix in ("tx", "rx")
        for suffix in ("freq", "gain", "rate", "bandwidth", "antenna")
    ) + ("set_clock_source", "set_time_source")

    def __init__(self, readback_offsets=None, missing=()):
        self.set_calls: dict[str, object] = {}
        self._store: dict[str, object] = {}
        self._offsets = readback_offsets or {}
        absent = set(missing)
        for name in self._ALL:
            if name in absent:
                continue
            if name.startswith("set_"):
                setattr(self, name, self._make_setter(name))
            else:
                setattr(self, name, self._make_getter(name))

    def _make_setter(self, name):
        def setter(value, _name=name):
            self.set_calls[_name] = value
            self._store["get_" + _name[4:]] = value

        return setter

    def _make_getter(self, name):
        def getter(_name=name):
            value = self._store.get(_name)
            offset = self._offsets.get(_name, 0)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return value + offset
            return value

        return getter


class FakeTxStream:
    """鸭子发射流：事件序 + 分块记录，send 恒足量送达 {'sent': len(chunk)}。"""

    def __init__(self):
        self.events: list[str] = []
        self.chunks: list[list[complex]] = []

    def start(self):
        self.events.append("start")

    def end(self):
        self.events.append("end")

    def stop(self):
        self.events.append("stop")

    def send(self, chunk):
        self.events.append("send")
        self.chunks.append(list(chunk))
        return {"sent": len(chunk)}


class FakeRxStream:
    """鸭子监测流：recv 按 script 计划逐次驱动（dict 原样返回 / BaseException 直接抛），耗尽回空块。"""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.requests: list[int] = []

    def recv(self, num_samps):
        self.requests.append(num_samps)
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, BaseException):
                raise item
            return dict(item)
        return {"samples": [], "overflow": False, "ts": 0}


class FakeTransport:
    """注入传输：make_device/make_tx_stream/make_rx_stream 各记参并回挂在身的假件。"""

    def __init__(self, device=None, tx=None, rx=None):
        self.device = device if device is not None else FakeDevice()
        self.tx = tx if tx is not None else FakeTxStream()
        self.rx = rx if rx is not None else FakeRxStream()
        self.device_args_seen: object = "__never__"
        self.stream_devices: list[tuple[str, object]] = []

    def make_device(self, args):
        self.device_args_seen = args
        return self.device

    def make_tx_stream(self, device):
        self.stream_devices.append(("tx", device))
        return self.tx

    def make_rx_stream(self, device):
        self.stream_devices.append(("rx", device))
        return self.rx


def _open_with(transport, **overrides):
    """以注入传输开箱的便捷口径：基线参数合法，overrides 覆盖单键。"""
    params = {
        "transport": transport,
        "freq_hz": 100e6,
        "sample_rate": 1e6,
        "tx_gain_db": 10.0,
        "clock_ref": "internal",
    }
    params.update(overrides)
    return open_b210_backend(params)


def test_backend_b210_injected_transport_open_configure_and_capabilities():
    """注入传输：设备打开（记参）+ 双通道下发（set_calls 逐项）+ capabilities 断言。"""
    transport = FakeTransport()
    backend = _open_with(transport)
    assert isinstance(backend, B210Backend)
    assert transport.device_args_seen == "type=b200"
    assert transport.device is backend.device
    assert ("tx", transport.device) in transport.stream_devices
    assert ("rx", transport.device) in transport.stream_devices
    calls = transport.device.set_calls
    assert calls["set_tx_freq"] == 100e6
    assert calls["set_tx_gain"] == 10.0
    assert calls["set_tx_rate"] == 1e6
    assert calls["set_tx_bandwidth"] == 1e6  # 缺省带宽取采样率
    assert calls["set_tx_antenna"] == "TX/RX"
    assert calls["set_rx_freq"] == 100e6
    assert calls["set_rx_rate"] == 1e6
    assert calls["set_rx_antenna"] == "RX2"
    assert calls["set_clock_source"] == "internal"
    assert calls["set_time_source"] == "internal"
    # configure 报告挂在实例上：applied 回读值 + clock_ref 成功下发
    assert backend.configure_report["applied"]["ch1_tx"]["freq_hz"] == 100e6
    assert backend.configure_report["clock_ref"] == "internal"
    caps = backend.capabilities()
    assert caps["kind"] == "b210"
    assert caps["tx"] is True and caps["rx"] is True
    assert caps["freq_range_mhz"] == (70.0, 6000.0)
    assert caps["freq_hz"] == 100e6
    assert caps["sample_rate_hz"] == 1e6
    assert caps["tx_gain_range_db"] == (0.0, 89.75)
    assert caps["transport"] == "FakeTransport"
    assert caps["clock_ref"] == "internal"


def test_backend_b210_no_device_backend_error_contains_probe_summary(monkeypatch):
    """CLI 探测空 → BackendError 含探测输出摘要（供 autodetect_backend 降级）。"""
    monkeypatch.setattr(b210_module, "_run_find_devices", lambda: "No UHD Devices Found")
    with pytest.raises(BackendError) as ei:
        open_b210_backend({"transport": "uhd_py"})
    assert "No UHD Devices Found" in str(ei.value)  # 探测摘要并入消息


def test_backend_b210_uhd_cli_transport_readonly_probe_only(monkeypatch):
    """uhd_cli：只读探测传输——即使设备在位也不支持收发，BackendError 说明口径。"""
    monkeypatch.setattr(b210_module, "_run_find_devices", lambda: _DEVICE_PRESENT_OUTPUT)
    with pytest.raises(BackendError) as ei:
        _open_with("uhd_cli")
    message = str(ei.value)
    assert "uhd_cli" in message
    assert "只读探测" in message
    assert "serial: 31B92DD" in message  # 探测摘要并入（设备在位时）


def test_backend_b210_start_tx_routes_through_write_stream_stats():
    """start_tx 经 write_b210_tx_stream：FakeTxStream 分块/统计透传，start/end 生命周期可见。"""
    transport = FakeTransport()
    backend = _open_with(transport)
    stats = backend.start_tx([[1 + 2j, 3 + 4j, 5 + 6j], [7 + 8j] * 5])
    assert stats["samples_sent"] == 8
    assert stats["blocks"] == 2
    assert stats["underruns"] == 0
    assert stats["invalid_zeroed"] == 0
    assert [len(chunk) for chunk in transport.tx.chunks] == [3, 5]
    assert transport.tx.chunks[0] == [1 + 2j, 3 + 4j, 5 + 6j]
    assert transport.tx.events[0] == "start"
    assert transport.tx.events[-1] == "end"
    assert backend.last_tx_stats == stats


def test_backend_b210_start_tx_effects_ignored_with_warning(caplog):
    """effects 传入 → 忽略 + warning（真硬件无环回），发送统计照常返回。"""
    backend = _open_with(FakeTransport())
    effects = {"noise_dbm": -50.0, "delay_blocks": 2}
    with caplog.at_level(logging.WARNING, logger=b210_module.__name__):
        stats = backend.start_tx([[0j] * 4], effects=effects)
    assert stats["samples_sent"] == 4
    assert backend.last_effects_ignored == effects
    warnings = [r for r in caplog.records if "effects" in r.getMessage()]
    assert warnings, "effects 忽略须记 warning，不得静默"


def test_backend_b210_read_samples_routes_through_read_stream():
    """read_samples 经 read_b210_rx_stream：块序号单调、device_ts/overflow 透传、默认 1 块。"""
    rx = FakeRxStream(
        script=[
            {"samples": [1 + 1j, 2 + 2j], "overflow": False, "ts": 111},
            {"samples": [3 + 3j], "overflow": True, "ts": 222},
            {"samples": [9 + 9j], "overflow": False, "ts": 333},
        ]
    )
    backend = _open_with(FakeTransport(rx=rx))
    blocks = backend.read_samples(2)
    assert len(blocks) == 2
    assert blocks[0]["samples"] == [1 + 1j, 2 + 2j]
    assert blocks[0]["ts"] == 0  # read_b210_rx_stream 产出块单调序号（起于 0）
    assert blocks[0]["device_ts"] == 111
    assert blocks[1]["overflow"] is True
    assert blocks[1]["device_ts"] == 222
    single = backend.read_samples()  # 缺省 max_blocks=1
    assert len(single) == 1
    assert single[0]["samples"] == [9 + 9j]
    assert all(n == 65536 for n in rx.requests)  # 确经 read 协议（_RECV_NUM_SAMPS 口径）


def test_backend_b210_stop_tx_and_set_tx_gain_passthrough():
    """stop_tx 透传发射流 stop；set_tx_gain 透传设备 setter 并以回读值为实际生效值。"""
    transport = FakeTransport()
    backend = _open_with(transport)
    assert backend.stop_tx() is None
    assert "stop" in transport.tx.events
    applied = backend.set_tx_gain(37.5)
    assert applied == 37.5
    assert transport.device.set_calls["set_tx_gain"] == 37.5
    assert backend.tx_gain_db == 37.5
    with pytest.raises(ValueError):  # bool 拒收
        backend.set_tx_gain(True)
    with pytest.raises(ValueError):  # 非有限拒收
        backend.set_tx_gain(float("nan"))


def test_backend_b210_set_tx_gain_missing_setter_backend_error():
    """设备句柄缺 set_tx_gain → BackendError（而非 AttributeError 裸穿）。"""
    backend = _open_with(FakeTransport(device=FakeDevice(missing=("set_tx_gain",))))
    with pytest.raises(BackendError):
        backend.set_tx_gain(10.0)


def test_backend_b210_registry_lookup_integration():
    """自注册集成：lookup('b210') 取回本工厂与 caps，工厂注入传输可开箱。"""
    factory, meta = lookup_backend("b210")
    assert factory is open_b210_backend
    assert meta["caps"] == {"tx": True, "rx": True, "freq_range_mhz": (70.0, 6000.0)}
    instance = factory({"transport": FakeTransport(), "freq_hz": 100e6})
    assert isinstance(instance, B210Backend)
    assert instance.capabilities()["kind"] == "b210"


@pytest.mark.parametrize(
    "bad_params, needle",
    [
        (None, "params"),  # params 非 dict
        ({"transport": "usb"}, "transport"),  # 未知传输名
        ({"freq_hz": 69e6}, "freq_hz"),  # 域下界外
        ({"freq_hz": 6.1e9}, "freq_hz"),  # 域上界外
        ({"sample_rate": 0}, "sample_rate"),
        ({"tx_gain_db": 91.0}, "tx_gain_db"),
        ({"rx_gain_db": -1.0}, "rx_gain_db"),
        ({"clock_ref": "gps"}, "clock_ref"),
        ({"tx_antenna": "J1"}, "antenna"),
        ({"device_args": 123}, "device_args"),
    ],
)
def test_backend_b210_invalid_params_raise_value_error(bad_params, needle):
    """params 域错 → ValueError（消息定位到出错键）。"""
    with pytest.raises(ValueError) as ei:
        open_b210_backend(bad_params)
    assert needle in str(ei.value)


def test_backend_b210_injected_transport_missing_duck_methods_value_error():
    """注入对象缺鸭子方法 → ValueError（域错，非 AttributeError）。"""
    with pytest.raises(ValueError) as ei:
        open_b210_backend({"transport": object()})
    assert "make_device" in str(ei.value)


def test_backend_b210_value_error_paths_touch_no_transport():
    """域错先于设备调用：注入传输计数为零（ValueError 路径零硬件副作用）。"""
    transport = FakeTransport()
    with pytest.raises(ValueError):
        _open_with(transport, freq_hz=6.5e9)
    assert transport.device_args_seen == "__never__"
    assert transport.stream_devices == []


def test_backend_b210_device_open_failure_wraps_uhd_text():
    """设备打开失败 → BackendError 含 UHD 错误原文，__cause__ 保留原异常。"""

    class BoomDeviceTransport(FakeTransport):
        def make_device(self, args):
            raise RuntimeError("UHD device open failed: Device or resource busy")

    with pytest.raises(BackendError) as ei:
        _open_with(BoomDeviceTransport())
    assert "Device or resource busy" in str(ei.value)
    assert "device_args" in str(ei.value)
    assert isinstance(ei.value.__cause__, RuntimeError)


def test_backend_b210_stream_handle_failure_wraps_backend_error():
    """流句柄创建失败 → BackendError 包装（原文并入）。"""

    class BoomStreamTransport(FakeTransport):
        def make_tx_stream(self, device):
            raise RuntimeError("stream args invalid: fc32 not supported")

    with pytest.raises(BackendError) as ei:
        _open_with(BoomStreamTransport())
    assert "stream args invalid" in str(ei.value)


def test_backend_b210_configure_readback_failure_propagates():
    """回读偏差超容差 → configure 的 BackendError 透传出 open（不吞为半开箱）。"""
    device = FakeDevice(readback_offsets={"get_tx_freq": 10.0})  # 频率容差 1Hz
    with pytest.raises(BackendError) as ei:
        _open_with(FakeTransport(device=device))
    assert "回读不符" in str(ei.value)


# ---- B5 对抗审查缺陷回归（中#1 configure 调用点异常契约 / 中#3 open 侧域校验同步）----


def test_defect_b5_1_open_configure_setter_exception_wrapped_backend_error():
    """中#1：configure 调用点随 configure_b210_channels 自然入契约——setter 异常 →
    BackendError（含 UHD 原文），不再裸穿 RuntimeError 出 open。"""
    device = FakeDevice()

    def boom(value):
        raise RuntimeError("UHD LookupError: 100e6 out of range")

    device.set_tx_freq = boom
    with pytest.raises(BackendError) as ei:
        _open_with(FakeTransport(device=device))
    msg = str(ei.value)
    assert "set_tx_freq" in msg and "UHD LookupError" in msg
    assert isinstance(ei.value.__cause__, RuntimeError)


def test_defect_b5_3_open_side_gain_domains_split_tx_rx():
    """中#3（open 侧同步）：rx_gain_db 域 0–76（对齐真机 RX 上限），tx 0–89.75 不变。"""
    with pytest.raises(ValueError, match="rx_gain_db"):
        _open_with(FakeTransport(), rx_gain_db=80.0)  # 80 在旧统一域 89.75 内、超新 RX 上界
    transport = FakeTransport()
    with pytest.raises(ValueError, match="tx_gain_db"):
        _open_with(transport, tx_gain_db=90.0)
    assert transport.device_args_seen == "__never__"  # 域校验先于设备打开
    backend = _open_with(FakeTransport(), rx_gain_db=76.0)  # 恰上界合法
    assert backend.configure_report["applied"]["ch2_rx"]["gain_db"] == pytest.approx(76.0)


def test_defect_b5_3_open_side_antenna_whitelists_split_tx_rx():
    """中#3（open 侧同步）：tx_antenna 白名单 {'TX/RX'}、rx_antenna {'TX/RX','RX2'}。"""
    for bad_overrides, needle in (
        ({"tx_antenna": "RX2"}, "tx_antenna"),  # RX2 是收端口专属
        ({"tx_antenna": "RX1"}, "tx_antenna"),  # 'RX1' 已移除
        ({"rx_antenna": "RX1"}, "rx_antenna"),  # 'RX1' 已移除
        ({"rx_antenna": "TX"}, "rx_antenna"),  # 'TX' 已移除
    ):
        with pytest.raises(ValueError, match=needle):
            _open_with(FakeTransport(), **bad_overrides)
    # 合法组合照常开箱：rx 也可选 TX/RX（双工共用端口）
    backend = _open_with(FakeTransport(), rx_antenna="TX/RX", tx_antenna="TX/RX")
    assert isinstance(backend, B210Backend)
    assert backend.configure_report["applied"]["ch2_rx"]["antenna"] == "TX/RX"


def test_backend_b210_probe_available_caches_cli_result(monkeypatch):
    """probe_b210_available：CLI 结果缓存生效，refresh 强制重探。"""
    monkeypatch.setattr(b210_module, "_PROBE_CACHE", None)
    monkeypatch.setattr(b210_module, "_run_find_devices", lambda: _DEVICE_PRESENT_OUTPUT)
    assert probe_b210_available() is True
    # 缓存期：底层输出已变，仍回旧结果
    monkeypatch.setattr(b210_module, "_run_find_devices", lambda: "No UHD Devices Found")
    assert probe_b210_available() is True
    assert probe_b210_available(refresh=True) is False


# 真硬件用例：skipif 用公开探测（内部 uhd_find_devices CLI，缓存结果）——不在位整段跳过。
_IS_B210_PRESENT = probe_b210_available()


@pytest.mark.skipif(not _IS_B210_PRESENT, reason="B210 不在位")
def test_backend_b210_real_hardware_open_and_close():
    """真在位一例实跑：uhd_py 打开 + 参数下发回读 + capabilities + close（不发射）。"""
    with open_b210_backend(
        {
            "transport": "uhd_py",
            "freq_hz": 100e6,
            "sample_rate": 1e6,
            "tx_gain_db": 0.0,
            "clock_ref": "internal",
        }
    ) as backend:
        assert isinstance(backend, B210Backend)
        assert backend.capabilities()["kind"] == "b210"
        assert backend.capabilities()["freq_range_mhz"] == (70.0, 6000.0)
        applied = backend.configure_report["applied"]
        assert applied["ch1_tx"]["freq_hz"] == pytest.approx(100e6, abs=1.0)
        assert applied["ch2_rx"]["freq_hz"] == pytest.approx(100e6, abs=1.0)
        assert backend.configure_report["clock_ref"] == "internal"
    assert backend.closed


# ---- B6 对抗审查缺陷回归（中#5 GPSDO/时钟源鸭子方法，注入传输用例 + 真机只读一例）----


class _SensorDevice(FakeDevice):
    """FakeDevice 加主板传感器/时钟源读写：传感器缺抛 LookupError（真 uhd 口径）；
    源读取签名带 mboard 下标（对齐真 uhd 4.x 绑定 get_*_source 无缺省参的口径）。"""

    def __init__(self, sensors=None):
        super().__init__()
        # FakeDevice.__init__ 会给 set_clock_source/set_time_source 挂实例级通用
        # setter（写 _store）——弹出以让本类的源读写实现生效。
        self.__dict__.pop("set_clock_source", None)
        self.__dict__.pop("set_time_source", None)
        self._sensors = dict(sensors or {})
        self.source_calls: list[tuple[str, object]] = []
        self._sources = {"clock": "internal", "time": "internal"}

    def get_mboard_sensor(self, name):
        if name not in self._sensors:
            raise LookupError(f"unknown sensor: {name}")
        return self._sensors[name]

    def get_clock_source(self, mboard=0):
        return self._sources["clock"]

    def get_time_source(self, mboard=0):
        return self._sources["time"]

    def set_clock_source(self, source, mboard=None):
        self.source_calls.append(("set_clock_source", source))
        self._sources["clock"] = source

    def set_time_source(self, source, mboard=None):
        self.source_calls.append(("set_time_source", source))
        self._sources["time"] = source


def test_defect_b6_5_b210_duck_methods_passthrough_injected():
    """中#5：get_mboard_sensor/get·set_clock·time_source 透传——传感器缺→None，
    源读写经设备生效。"""
    device = _SensorDevice(sensors={"gps_locked": True})
    backend = _open_with(FakeTransport(device=device))
    assert backend.get_mboard_sensor("gps_locked") is True  # 透传
    assert backend.get_mboard_sensor("no_such_sensor") is None  # 传感器缺 → None（不抛）
    assert backend.get_clock_source() == "internal"
    assert backend.get_time_source() == "internal"
    backend.set_clock_source("external")
    backend.set_time_source("external")
    assert backend.get_clock_source() == "external"  # 透传下发后回读生效
    assert backend.get_time_source() == "external"
    assert ("set_clock_source", "external") in device.source_calls
    assert ("set_time_source", "external") in device.source_calls


def test_defect_b6_5_b210_missing_device_methods():
    """中#5：设备句柄缺源读取方法 → BackendError（非 AttributeError 裸穿）；
    缺 get_mboard_sensor → None（探测侧按无 GPS 能力处理）。"""
    backend = _open_with(FakeTransport(), clock_ref=None)  # FakeDevice 无源方法
    with pytest.raises(BackendError, match="get_clock_source"):
        backend.get_clock_source()
    with pytest.raises(BackendError, match="get_time_source"):
        backend.get_time_source()
    assert backend.get_mboard_sensor("gps_locked") is None


def test_defect_b6_5_b210_setter_exceptions_propagate_backend_error():
    """中#5：set_* 透传异常上抛（BackendError 包装含 UHD 原文，__cause__ 保留），
    由调用方（驯服路径）处理降级。"""

    class BoomSetDevice(_SensorDevice):
        def set_time_source(self, source):
            raise RuntimeError("UHD: refusing time source")

    backend = _open_with(FakeTransport(device=BoomSetDevice()), clock_ref=None)
    with pytest.raises(BackendError) as ei:
        backend.set_time_source("gpsdo")
    message = str(ei.value)
    assert "set_time_source" in message
    assert "refusing time source" in message
    assert isinstance(ei.value.__cause__, RuntimeError)


def test_defect_b6_5_b210_backend_feeds_resolve_clock_reference():
    """中#5 端到端：B210Backend 鸭子方法使 resolve_clock_reference 的 gpsdo/external
    探测与驯服在本后端可达——未锁定降 software、锁定驯服 gpsdo、外接源 external。"""
    # 传感器未锁定 → software 降级（basis 带探测事实）
    backend = _open_with(FakeTransport(device=_SensorDevice(sensors={"gps_locked": False})), clock_ref=None)
    decision = resolve_clock_reference(backend)
    assert decision["clock_ref"] == "software"
    assert decision["basis"]["gps_locked"] is False
    assert decision["basis"]["clock_source"] == "internal"

    # 传感器锁定 → 经鸭子 setter 驯服 gpsdo
    device = _SensorDevice(sensors={"gps_locked": True})
    backend = _open_with(FakeTransport(device=device), clock_ref=None)
    decision = resolve_clock_reference(backend)
    assert decision["clock_ref"] == "gpsdo"
    assert decision["discipline_applied"] is True
    assert ("set_clock_source", "gpsdo") in device.source_calls
    assert ("set_time_source", "gpsdo") in device.source_calls

    # 无 GPS 传感器（缺→None→fail-closed 未锁定）但外接时钟源 → external 时基
    device = _SensorDevice(sensors={})
    device._sources["clock"] = "external"
    backend = _open_with(FakeTransport(device=device), clock_ref=None)
    decision = resolve_clock_reference(backend)
    assert decision["clock_ref"] == "external"


@pytest.mark.skipif(not _IS_B210_PRESENT, reason="B210 不在位")
def test_defect_b6_5_b210_real_hardware_clock_source_readonly():
    """中#5 真机只读一例：get_clock_source 可读且应为 'internal'（开箱不传
    clock_ref，全程不下发时钟/时间源命令，仅读取）。"""
    with open_b210_backend(
        {
            "transport": "uhd_py",
            "freq_hz": 100e6,
            "sample_rate": 1e6,
            "tx_gain_db": 0.0,
        }
    ) as backend:
        clock = backend.get_clock_source()
        assert isinstance(clock, str) and clock
        assert clock == "internal"  # B210 缺省时钟源
        time_source = backend.get_time_source()
        assert isinstance(time_source, str) and time_source
    assert backend.closed
