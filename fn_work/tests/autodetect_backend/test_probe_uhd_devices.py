"""probe_uhd_devices 对抗单测：subprocess 全 mock，另含真机在位一例（skipif 无工具）。"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from src.autodetect_backend import probe_uhd_devices as mod
from src.autodetect_backend.probe_uhd_devices import probe_uhd_devices

# 仿真实 uhd_find_devices 4.9 输出：横幅/--分隔线/name: 字段都应被正确忽略。
TWO_DEVICE_OUTPUT = """--------------------------------------------------
-- UHD Device 0
--------------------------------------------------
Device Address:
    serial: 31B92DD
    name: Custom_SDR_B210
    product: B210
    type: b200

--------------------------------------------------
-- UHD Device 1
--------------------------------------------------
Device Address:
    serial: F4A1B2C
    name: Custom_SDR_B210
    product: B205 mini
    type: b200

"""


def _patch_run(monkeypatch, *, stdout="", stderr="", returncode=0, exc=None):
    """替换模块内 subprocess.run；返回调用记录 [(cmd, kwargs)] 供透传断言。"""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if exc is not None:
            raise exc
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    return calls


def test_two_devices_parsed_with_all_fields(monkeypatch):
    _patch_run(monkeypatch, stdout=TWO_DEVICE_OUTPUT)
    result = probe_uhd_devices()
    assert result["error"] is None
    assert result["available"] is True
    assert result["devices"] == [
        {"index": 0, "serial": "31B92DD", "product": "B210", "type": "b200"},
        {"index": 1, "serial": "F4A1B2C", "product": "B205 mini", "type": "b200"},
    ]
    assert "-- UHD Device 1" in result["raw"]


def test_empty_output_means_unavailable(monkeypatch):
    # 无设备段（含 "--" 开头的 "No devices found" 行，不得误判为设备头）
    _patch_run(monkeypatch, stdout="-- Empty device list... \n-- No devices found\n")
    result = probe_uhd_devices()
    assert result["devices"] == []
    assert result["available"] is False
    assert result["error"] is None


def test_binary_missing_returns_error_not_raise(monkeypatch):
    _patch_run(monkeypatch, exc=FileNotFoundError(2, "uhd_find_devices"))
    result = probe_uhd_devices()  # 不得抛出
    assert result["error"] == "binary_missing"
    assert result["available"] is False
    assert result["devices"] == []


def test_timeout_returns_error_not_raise(monkeypatch):
    exc = subprocess.TimeoutExpired(cmd=["uhd_find_devices"], timeout=10.0)
    _patch_run(monkeypatch, exc=exc)
    result = probe_uhd_devices()  # 不得抛出
    assert result["error"] == "timeout"
    assert result["available"] is False
    assert result["devices"] == []


def test_nonzero_exit_keeps_stderr_summary(monkeypatch):
    _patch_run(monkeypatch, stdout="", stderr="RuntimeError: usb device busy\n", returncode=1)
    result = probe_uhd_devices()
    assert result["error"] == "exit_1"
    assert result["available"] is False
    assert "usb device busy" in result["raw"]


def test_device_without_serial_line_keeps_none(monkeypatch):
    # 设备段缺 serial: 行（如 B205 mini 某些固件）→ serial None，其余字段照常解析
    stdout = """--------------------------------------------------
-- UHD Device 0
--------------------------------------------------
Device Address:
    product: B210
    type: b200
"""
    _patch_run(monkeypatch, stdout=stdout)
    result = probe_uhd_devices()
    assert result["devices"] == [{"index": 0, "serial": None, "product": "B210", "type": "b200"}]
    assert result["available"] is True


def test_blank_serial_value_is_none(monkeypatch):
    # "serial:" 后无内容 → None 而非空串
    _patch_run(monkeypatch, stdout="-- UHD Device 0\nDevice Address:\n    serial:\n    type: b200\n")
    result = probe_uhd_devices()
    assert result["devices"] == [{"index": 0, "serial": None, "product": None, "type": "b200"}]


def test_timeout_s_passed_through_to_subprocess(monkeypatch):
    calls = _patch_run(monkeypatch, stdout=TWO_DEVICE_OUTPUT)
    probe_uhd_devices(timeout_s=3.5)
    (cmd, kwargs) = calls[0]
    assert cmd == ["uhd_find_devices"]
    assert kwargs["timeout"] == 3.5


@pytest.mark.skipif(shutil.which("uhd_find_devices") is None, reason="uhd_find_devices 不在位")
def test_real_machine_device_present():
    # 真机在位实跑（不 mock）：B210 应被解析到；占用丢段属正常探测结果，但当前应非空
    result = probe_uhd_devices(timeout_s=15.0)
    assert result["error"] is None
    assert result["available"] is True
    assert result["devices"], "真机在位应至少解析到一台 USRP"
    first = result["devices"][0]
    assert isinstance(first["index"], int)
    assert first["serial"], "B210 在位应带 serial"
    assert "-- UHD Device" in result["raw"]
