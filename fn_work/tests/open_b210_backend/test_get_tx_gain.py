"""get_tx_gain 单测（slug=backend_b210·R96 地基——R96 验收继承）。

覆盖两级口径（device 读回优先 / self.tx_gain_db 跟踪回退）、device 异常原样
透传（非 BackendError 包装）、注册表反射（_METHOD_NAMES 在册+契约面承载）与
读回形状拒绝（bool/非数值如实抛）。夹具风格承 test_open_b210_backend（自建
轻量假件，不 import 兄弟测试模块私有夹具）。
"""
from __future__ import annotations

import pytest

from src.manage_backend_registry import register_backend as register_module
from src.manage_backend_registry.lookup_backend import lookup_backend
from src.manage_backend_registry.register_backend import BackendError
from src.open_b210_backend import open_b210_backend as b210_module
from src.open_b210_backend.open_b210_backend import B210Backend, open_b210_backend


class FakeDevice:
    """轻量鸭子设备（承兄弟测试 FakeDevice 风格）：set/get 存值对直读回，
    missing 按名缺方法；get_tx_gain 可在开箱后覆写为 boom/异形值（开箱期
    configure 回读须走正常存值路径）。"""

    _ALL = tuple(
        f"{verb}_{prefix}_{suffix}"
        for verb in ("set", "get")
        for prefix in ("tx", "rx")
        for suffix in ("freq", "gain", "rate", "bandwidth", "antenna")
    ) + ("set_clock_source", "set_time_source")

    def __init__(self, missing=()):
        self.set_calls: dict[str, object] = {}
        self._store: dict[str, object] = {}
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
            return self._store.get(_name)

        return getter


class FakeTransport:
    """注入传输：设备/哑流句柄原样回挂（本组用例不发射不收，流为哑件）。"""

    def __init__(self, device):
        self.device = device
        self.tx = object()
        self.rx = object()

    def make_device(self, args):
        return self.device

    def make_tx_stream(self, device):
        return self.tx

    def make_rx_stream(self, device):
        return self.rx


def _open(device) -> B210Backend:
    """注入传输开箱（基线参数合法）：device 按用例缺方法/开箱后覆写读回。"""
    return open_b210_backend(
        {
            "transport": FakeTransport(device),
            "freq_hz": 100e6,
            "sample_rate": 1e6,
            "tx_gain_db": 10.0,
            "clock_ref": "internal",
        }
    )


def test_get_tx_gain_reads_device_readback_after_set():
    """①R96 验收继承：set_tx_gain(60) 后 get_tx_gain()==60.0（fake device 带
    回读）；纯读回不新增 set_calls（不下发指令）。"""
    device = FakeDevice()
    backend = _open(device)
    assert backend.set_tx_gain(60) == 60
    gain = backend.get_tx_gain()
    assert gain == 60.0
    assert isinstance(gain, float)
    assert backend.tx_gain_db == 60.0  # set_tx_gain 回读已同步跟踪字段
    calls_after_set = dict(device.set_calls)
    assert backend.get_tx_gain() == 60.0  # 重复读稳定
    assert device.set_calls == calls_after_set  # 纯读回：无新下发


def test_get_tx_gain_falls_back_to_tracking_without_device_getter():
    """②device 无 get_tx_gain getter → 返回 self.tx_gain_db 跟踪值（开箱基线
    10.0；无 getter 时 set_tx_gain 走跟踪路径、读回随动）。"""
    backend = _open(FakeDevice(missing=("get_tx_gain",)))
    assert backend.get_tx_gain() == 10.0
    assert backend.set_tx_gain(42) == 42.0  # 无 getter：set 走跟踪回退
    assert backend.get_tx_gain() == 42.0
    backend.tx_gain_db = 33.5  # 跟踪字段为无 getter 时唯一事实源
    assert backend.get_tx_gain() == 33.5


def test_get_tx_gain_device_exception_propagates_unwrapped():
    """③device.get_tx_gain 自身异常原样透传：类型即 fake 抛的原类型
    （RuntimeError），非 BackendError 包装。"""

    def boom():
        raise RuntimeError("UHD: gain read failed")

    device = FakeDevice()
    backend = _open(device)
    device.get_tx_gain = boom  # 开箱后覆写（开箱期 configure 仍走正常回读）
    with pytest.raises(RuntimeError, match="UHD: gain read failed") as ei:
        backend.get_tx_gain()
    assert type(ei.value) is RuntimeError
    assert not isinstance(ei.value, BackendError)


def test_get_tx_gain_registered_in_method_names():
    """④注册表反射（R96 完整落点）：_METHOD_NAMES 在册 + 契约面实际承载——
    get_tx_gain 已入词汇表、五名列表过 _check_contract 直核（与 import 期
    register 调用同一闸门）；SimBackend 式四名子集仍合法（契约是子集关系非
    必备）；import 期实注册存活（lookup 取回本工厂）。"""
    assert "get_tx_gain" in b210_module._METHOD_NAMES
    assert callable(getattr(B210Backend, "get_tx_gain", None))
    # 契约词汇表面（register_backend 单一事实源）：可选名已入白名单
    assert "get_tx_gain" in register_module._ALLOWED_METHOD_NAMES
    caps = {"tx": True, "rx": True, "freq_range_mhz": (70.0, 6000.0)}
    # 五名列表过真实交检闸门（不抛即承载 get_tx_gain）
    register_module._check_contract(list(b210_module._METHOD_NAMES), caps)
    # 子集关系见证：不含 get_tx_gain 的四名（SimBackend 形态）仍合法——非必备
    register_module._check_contract(
        ["start_tx", "stop_tx", "set_tx_gain", "read_samples"], caps
    )
    # import 期实注册存活：五名直传未在注册期炸，lookup 取回本工厂
    factory, _meta = lookup_backend("b210")
    assert factory is open_b210_backend


@pytest.mark.parametrize("bad", [True, False, "60.0", None])
def test_get_tx_gain_non_numeric_readback_rejected(bad):
    """⑤读回形状异常（bool/非数值）拒绝：如实抛 BackendError，不返回伪值。"""
    device = FakeDevice()
    backend = _open(device)
    device.get_tx_gain = lambda: bad
    with pytest.raises(BackendError, match="读回形状异常"):
        backend.get_tx_gain()
