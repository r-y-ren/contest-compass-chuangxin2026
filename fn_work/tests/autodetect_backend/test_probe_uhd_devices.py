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
    # 真机在位实跑（不 mock）：先 probe 一次做门禁——B210 未枚举到（未接入或被占用，
    # available False / devices 空）属环境态而非缺陷，skip 退场；在位才继续原断言。
    result = probe_uhd_devices(timeout_s=15.0)
    if not result["available"] or not result["devices"]:
        pytest.skip("B210 未枚举到（未接入或被占用）——真机例跳过")
    assert result["error"] is None
    assert result["available"] is True
    assert result["devices"], "真机在位应至少解析到一台 USRP"
    first = result["devices"][0]
    assert isinstance(first["index"], int)
    assert first["serial"], "B210 在位应带 serial"
    assert "-- UHD Device" in result["raw"]


# ---- B6 对抗审查缺陷回归 ----


def _patch_run_seq(monkeypatch, results):
    """按序替换 subprocess.run：results 每项为 (stdout, stderr, returncode) 或异常；
    顺带记录 time.sleep 调用（重试间隔断言用），测试内不做真实 sleep。"""
    calls = []
    sleeps: list[float] = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        item = results.pop(0)
        if isinstance(item, BaseException):
            raise item
        stdout, stderr, returncode = item
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))
    return calls, sleeps


def test_defect_b6_1_stderr_not_parsed_as_device_fields(monkeypatch):
    """中#1：设备字段只出自 stdout——stderr 里的 serial:/product: 行不得冒充设备字段。"""
    stdout = "-- UHD Device 0\nDevice Address:\n"
    stderr = "    serial: FAKE123\n    product: B210\n    type: b200\n"
    _patch_run_seq(monkeypatch, [(stdout, stderr, 0)])
    result = probe_uhd_devices()
    assert result["devices"] == [{"index": 0, "serial": None, "product": None, "type": None}]
    assert "FAKE123" in result["raw"]  # stderr 原文只进 raw 摘要

    # stderr 含完整伪设备段（含 "-- UHD Device" 头）也不得计台
    _patch_run_seq(
        monkeypatch,
        [
            ("No UHD Devices Found\n", "-- UHD Device 7\n    serial: FAKE123\n    type: b200\n", 0),
            ("No UHD Devices Found\n", "", 0),  # 首次空段触发一次重试
        ],
    )
    result = probe_uhd_devices()
    assert result["devices"] == []
    assert result["available"] is False


def test_defect_b6_13_giant_stdout_truncated_in_raw(monkeypatch):
    """低#13：stdout 超 20000 字符截尾（头 200 + 尾 4000）——防 raw 巨型贯通 selection；
    设备解析仍用完整 stdout 不受截断影响。"""
    stdout = "-- UHD Device 0\n" + "x" * 22000 + "\n    serial: ABC123\n    type: b200\n"
    _patch_run_seq(monkeypatch, [(stdout, "", 0)])
    result = probe_uhd_devices()
    assert result["devices"][0]["serial"] == "ABC123"  # 解析用完整 stdout
    assert result["devices"][0]["type"] == "b200"
    raw = result["raw"]
    assert len(raw) < 10000  # 头 200 + 标注 + 尾 4000 的有界摘要
    assert "stdout 截断" in raw
    assert raw.startswith("-- UHD Device 0")  # 头部保留
    assert "ABC123" in raw  # 尾部覆盖设备字段段


def test_defect_b6_14_retry_once_when_empty_then_success(monkeypatch):
    """低#14：首跑空设备段 → 0.5s 后重试一次；重试命中以末次为准，'retried': True。"""
    _patch_run_seq(monkeypatch, [("", "", 0), (TWO_DEVICE_OUTPUT, "", 0)])
    result = probe_uhd_devices()
    assert result["retried"] is True
    assert len(result["devices"]) == 2
    assert result["available"] is True
    assert result["error"] is None


def test_defect_b6_14_retry_interval_is_half_second(monkeypatch):
    """低#14：重试间隔 0.5s（消解 USB 枚举 flake 的等待窗口）。"""
    _, sleeps = _patch_run_seq(monkeypatch, [("", "", 0), ("", "", 0)])
    probe_uhd_devices()
    assert sleeps == [0.5]


def test_defect_b6_14_both_attempts_empty_returns_no_device(monkeypatch):
    """低#14：两次都空才按 no_device 口径返回（available False、error None、retried True）。"""
    calls, _ = _patch_run_seq(monkeypatch, [("-- No devices found\n", "", 0), ("", "", 0)])
    result = probe_uhd_devices()
    assert result["devices"] == []
    assert result["available"] is False
    assert result["error"] is None
    assert result["retried"] is True
    assert len(calls) == 2  # 恰好两次，不再三连


def test_defect_b6_14_retry_on_nonzero_exit_then_success(monkeypatch):
    """低#14：CLI 失败（非零退出）同样重试一次；末次成功则 error 清零。"""
    _patch_run_seq(monkeypatch, [("", "usb device busy\n", 1), (TWO_DEVICE_OUTPUT, "", 0)])
    result = probe_uhd_devices()
    assert result["error"] is None
    assert result["available"] is True
    assert result["retried"] is True


def test_defect_b6_14_no_retry_on_first_success(monkeypatch):
    """低#14：首跑命中不重试（retried False、单次调用）。"""
    calls, sleeps = _patch_run_seq(monkeypatch, [(TWO_DEVICE_OUTPUT, "", 0)])
    result = probe_uhd_devices()
    assert result["retried"] is False
    assert len(calls) == 1
    assert sleeps == []


def test_defect_b6_14_no_retry_on_binary_missing(monkeypatch):
    """低#14：binary_missing 为确定性缺失，不重试（retried False、单次调用）。"""
    calls, sleeps = _patch_run_seq(monkeypatch, [FileNotFoundError(2, "uhd_find_devices")])
    result = probe_uhd_devices()
    assert result["error"] == "binary_missing"
    assert result["retried"] is False
    assert len(calls) == 1
    assert sleeps == []
