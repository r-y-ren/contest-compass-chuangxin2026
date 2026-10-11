"""autodetect_backend 对抗测试（slug=backend_autodetect）：mock 探测/打开覆盖三态决策 + 真机一例。"""
from __future__ import annotations

import pytest

import src.autodetect_backend.autodetect_backend as ad_module
from src.autodetect_backend.autodetect_backend import autodetect_backend
from src.autodetect_backend.probe_uhd_devices import probe_uhd_devices
from src.manage_backend_registry.register_backend import REGISTRY, BackendError
from src.open_sim_backend.open_sim_backend import SimBackend

# 探测结果样例（形状同 probe_uhd_devices 返回）：命中 1 台 B210 / 无设备 / 工具缺失。
_PROBE_HIT = {
    "devices": [{"index": 0, "serial": "31B92DD", "product": "B210", "type": "b200"}],
    "raw": (
        "-- UHD Device 0\nDevice Address:\n"
        "    serial: 31B92DD\n    product: B210\n    type: b200"
    ),
    "available": True,
    "error": None,
}
_PROBE_NO_DEVICE = {
    "devices": [],
    "raw": "No UHD Devices Found",
    "available": False,
    "error": None,
}
_PROBE_BINARY_MISSING = {"devices": [], "raw": "", "available": False, "error": "binary_missing"}


@pytest.mark.parametrize("name", ["sim", "SIM"])
def test_backend_autodetect_explicit_sim_direct(name, monkeypatch):
    # 显式 sim 直取（lookup→注册表工厂→open_sim_backend 真开），不得触发探测；
    # 大小写变体经 lookup 归一到同一注册名。
    monkeypatch.setattr(
        ad_module, "probe_uhd_devices", lambda *a, **k: pytest.fail("显式路径不得探测")
    )
    backend, selection = autodetect_backend(name)
    assert isinstance(backend, SimBackend)
    assert selection["backend"] == "sim"
    assert selection["decision"] == "explicit"
    assert selection["explicit"] == name


def test_backend_autodetect_explicit_b210_failure_advises_sim(monkeypatch):
    # 显式 b210：注册表工厂打开失败 → BackendError 附降级建议+原始错误（不静默），
    # 因果链保留；同时断言 params 透传到显式工厂。
    seen = {}

    def _boom(params):
        seen["params"] = params
        raise BackendError("B210 无设备：uhd_find_devices 探测为空")

    monkeypatch.setitem(REGISTRY, "b210", {**REGISTRY["b210"], "factory": _boom})
    monkeypatch.setattr(
        ad_module, "open_sim_backend", lambda p: pytest.fail("显式失败不得静默降级 sim")
    )
    params = {"freq_hz": 2.45e9}
    with pytest.raises(BackendError) as ei:
        autodetect_backend("b210", params)
    msg = str(ei.value)
    assert "可改用 --backend sim 降级" in msg
    assert "B210 无设备" in msg  # 工厂原始错误透传
    assert isinstance(ei.value.__cause__, BackendError)  # __cause__ 因果链保留
    assert seen["params"] == params  # 显式路径 params 透传


def test_backend_autodetect_explicit_unknown_name_hints():
    # lookup 未知名 BackendError（含相近名提示）原样透传，不因包装丢失提示。
    with pytest.raises(BackendError) as ei:
        autodetect_backend("simx")
    msg = str(ei.value)
    assert "未知后端名" in msg
    assert "'simx'" in msg
    assert "相近建议" in msg
    assert "sim" in msg.split("相近建议", 1)[1]  # 提示列表里含 sim（编辑距离最近）


def test_backend_autodetect_auto_probe_hit_returns_b210(monkeypatch):
    # auto+探测 available+打开成功 → b210 实例 + probe_hit 决策 + 探测记录贯通。
    sentinel = object()
    monkeypatch.setattr(ad_module, "probe_uhd_devices", lambda: _PROBE_HIT)
    monkeypatch.setattr(ad_module, "open_b210_backend", lambda params: sentinel)
    backend, selection = autodetect_backend(None)
    assert backend is sentinel
    assert selection["backend"] == "b210"
    assert selection["decision"] == "probe_hit"
    assert selection["probe"] == _PROBE_HIT


def test_backend_autodetect_auto_probe_hit_open_busy_fails_loud(monkeypatch):
    # auto+探测命中但打开失败（如被占用）→ BackendError 附探测摘要+降级建议，不静默 sim。
    monkeypatch.setattr(ad_module, "probe_uhd_devices", lambda: _PROBE_HIT)

    def _busy(params):
        raise BackendError(
            "B210 设备打开失败（device_args='type=b200'）: RuntimeError: Device or resource busy"
        )

    monkeypatch.setattr(ad_module, "open_b210_backend", _busy)
    monkeypatch.setattr(
        ad_module, "open_sim_backend", lambda p: pytest.fail("探测命中打开失败不得静默降级 sim")
    )
    with pytest.raises(BackendError) as ei:
        autodetect_backend(None)
    msg = str(ei.value)
    assert "Device or resource busy" in msg  # 原始错误透传
    assert "31B92DD" in msg  # 探测摘要（serial）附上
    assert "可改用 --backend sim 降级" in msg
    assert isinstance(ei.value.__cause__, BackendError)


def test_backend_autodetect_auto_no_device_falls_back_sim_with_params(monkeypatch):
    # auto+探测 no_device → sim 降级（真开非 mock），reason=no_device，params 透传。
    monkeypatch.setattr(ad_module, "probe_uhd_devices", lambda: _PROBE_NO_DEVICE)
    params = {"freq_hz": 915e6, "sample_rate": 2e6}
    backend, selection = autodetect_backend(None, params)
    assert isinstance(backend, SimBackend)
    assert backend.freq_hz == 915e6  # params 透传到 sim 打开
    assert backend.sample_rate == 2e6
    assert selection["backend"] == "sim"
    assert selection["decision"] == "auto_fallback"
    assert selection["reason"] == "no_device"
    assert selection["probe"] == _PROBE_NO_DEVICE


def test_backend_autodetect_auto_binary_missing_fallback_reason(monkeypatch):
    # auto+探测 binary_missing → sim 降级，error 记入 reason 与 probe；显式 'auto' 同走探测。
    monkeypatch.setattr(ad_module, "probe_uhd_devices", lambda: _PROBE_BINARY_MISSING)
    backend, selection = autodetect_backend("auto")
    assert isinstance(backend, SimBackend)
    assert selection["backend"] == "sim"
    assert selection["decision"] == "auto_fallback"
    assert selection["reason"] == "binary_missing"
    assert selection["probe"]["error"] == "binary_missing"


def test_backend_autodetect_auto_exit_error_fallback_reason(monkeypatch):
    # auto+探测 exit_N（available False）→ sim 降级，reason=exit_1（探测 error 记录）。
    probe = {"devices": [], "raw": "-- err", "available": False, "error": "exit_1"}
    monkeypatch.setattr(ad_module, "probe_uhd_devices", lambda: probe)
    backend, selection = autodetect_backend(None)
    assert isinstance(backend, SimBackend)
    assert selection["decision"] == "auto_fallback"
    assert selection["reason"] == "exit_1"
    assert selection["probe"]["error"] == "exit_1"


def test_backend_autodetect_auto_devices_but_error_falls_back(monkeypatch):
    # 探测有设备段但带 error（退出码非零）：不碰真机，降级 sim 且 reason=error。
    probe = {
        "devices": list(_PROBE_HIT["devices"]),
        "raw": "-- UHD Device 0\n",
        "available": True,
        "error": "exit_1",
    }
    monkeypatch.setattr(ad_module, "probe_uhd_devices", lambda: probe)
    monkeypatch.setattr(
        ad_module, "open_b210_backend", lambda p: pytest.fail("探测带 error 不得尝试打开真机")
    )
    backend, selection = autodetect_backend(None)
    assert isinstance(backend, SimBackend)
    assert selection["decision"] == "auto_fallback"
    assert selection["reason"] == "exit_1"


# ---- B6 对抗审查缺陷回归 ----


def test_defect_b6_10_probe_inconsistent_falls_back_sim(monkeypatch):
    """低#10：probe available=True 但 devices==[]（矛盾态）→ 按不可用降级 sim，
    reason='probe_inconsistent'，不碰真机（open_b210_backend 不得被调）。"""
    probe = {
        "devices": [],
        "raw": "-- some banner without device section",
        "available": True,
        "error": None,
        "retried": True,
    }
    monkeypatch.setattr(ad_module, "probe_uhd_devices", lambda: probe)
    monkeypatch.setattr(
        ad_module, "open_b210_backend", lambda p: pytest.fail("矛盾态不得尝试打开真机")
    )
    backend, selection = autodetect_backend(None)
    assert isinstance(backend, SimBackend)
    assert selection["backend"] == "sim"
    assert selection["decision"] == "auto_fallback"
    assert selection["reason"] == "probe_inconsistent"
    assert selection["probe"] is probe


def test_backend_autodetect_params_passthrough_to_b210(monkeypatch):
    # auto 探测命中路径：params 原样透传 open_b210_backend（None 时透传空 dict）。
    monkeypatch.setattr(ad_module, "probe_uhd_devices", lambda: _PROBE_HIT)
    seen = {}

    def fake_open(params):
        seen["params"] = params
        return object()

    monkeypatch.setattr(ad_module, "open_b210_backend", fake_open)
    params = {"freq_hz": 3.6e9, "tx_gain_db": 10.0}
    autodetect_backend(None, params)
    assert seen["params"] == params
    autodetect_backend(None)  # params 缺省 → 空 dict 透传
    assert seen["params"] == {}


def test_backend_autodetect_selection_key_sets(monkeypatch):
    # 选择记录键集按决策路径定形（供日志/UI/报告贯通方按键取用）。
    _, sel = autodetect_backend("sim")
    assert set(sel) == {"backend", "decision", "explicit"}
    monkeypatch.setattr(ad_module, "probe_uhd_devices", lambda: _PROBE_HIT)
    monkeypatch.setattr(ad_module, "open_b210_backend", lambda params: object())
    _, sel = autodetect_backend(None)
    assert set(sel) == {"backend", "decision", "probe"}
    monkeypatch.setattr(ad_module, "probe_uhd_devices", lambda: _PROBE_NO_DEVICE)
    _, sel = autodetect_backend(None)
    assert set(sel) == {"backend", "decision", "probe", "reason"}


@pytest.mark.parametrize("explicit", [None, "", "   ", "auto", "AUTO"])
def test_backend_autodetect_auto_variants_route_to_probe(monkeypatch, explicit):
    # None/空/空白/'auto'（大小写不敏感）一律走探测决策，不进 lookup 注册表解析。
    monkeypatch.setattr(ad_module, "probe_uhd_devices", lambda: _PROBE_NO_DEVICE)
    backend, selection = autodetect_backend(explicit)
    assert isinstance(backend, SimBackend)
    assert selection["decision"] == "auto_fallback"
    assert selection["backend"] == "sim"


@pytest.mark.skipif(
    not probe_uhd_devices()["available"],
    reason="UHD 设备/工具不在位：真机例跳过（auto→b210 实开）",
)
def test_backend_autodetect_real_hardware_open_and_close():
    # 真机在位（不 mock）：auto → open_b210_backend 实开 b210（uhd_py 传输），
    # 决策 probe_hit 且探测记录贯通；统一接口在位，用毕 close 释放。
    backend, selection = autodetect_backend(None, {"sample_rate": 1e6})
    try:
        assert selection["backend"] == "b210"
        assert selection["decision"] == "probe_hit"
        assert selection["probe"]["available"] is True
        for method in ("start_tx", "stop_tx", "set_tx_gain", "read_samples", "close"):
            assert callable(getattr(backend, method, None)), f"缺统一接口方法 {method}"
    finally:
        backend.close()
