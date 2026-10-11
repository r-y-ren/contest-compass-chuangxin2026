"""probe_gpsdo_status 行为用例：鸭子 backend 的 GPSDO/参考源状态探测（对抗 FakeBackend）。"""
from __future__ import annotations

import pytest

from src.resolve_clock_reference.probe_gpsdo_status import probe_gpsdo_status

RESULT_KEYS = {"available", "gps_locked", "clock_source", "time_source", "sensors_read", "reason"}
ALL_GPS_SENSORS = ("gps_locked", "gps_gpgga", "gps_time")

_UNSET = object()


class FakeBackend:
    """鸭子后端：可选 GPS 传感器表 / clock·time 源方法 / 各类读失败；未配置的方法置 None 模拟缺失。"""

    def __init__(self, sensors=None, failing_sensors=(), sensor_error=None,
                 clock_source=_UNSET, time_source=_UNSET,
                 fail_clock=False, fail_time=False):
        self._sensors = dict(sensors or {})
        self._failing_sensors = set(failing_sensors)
        self._sensor_error = sensor_error or RuntimeError("sensor read failed")
        self._clock_source = clock_source
        self._time_source = time_source
        self._fail_clock = fail_clock
        self._fail_time = fail_time
        self.sensor_calls: list[str] = []
        if clock_source is _UNSET and not fail_clock:
            self.get_clock_source = None  # 实例属性遮蔽类方法，模拟方法缺失
        if time_source is _UNSET and not fail_time:
            self.get_time_source = None

    def get_mboard_sensor(self, name):
        self.sensor_calls.append(name)
        if name in self._failing_sensors:
            raise self._sensor_error
        if name not in self._sensors:
            raise KeyError(f"no such sensor: {name}")
        return self._sensors[name]

    def get_clock_source(self):
        if self._fail_clock:
            raise RuntimeError("clock source read failed")
        return self._clock_source

    def get_time_source(self):
        if self._fail_time:
            raise RuntimeError("time source read failed")
        return self._time_source


def test_result_key_set():
    result = probe_gpsdo_status(FakeBackend(sensors={"gps_locked": True}))
    assert set(result) == RESULT_KEYS


def test_gps_locked_true_means_available():
    backend = FakeBackend(sensors={"gps_locked": True}, clock_source="gpsdo", time_source="gpsdo")
    result = probe_gpsdo_status(backend)
    assert result["available"] is True
    assert result["gps_locked"] is True
    assert result["sensors_read"] == ["gps_locked"]
    assert result["clock_source"] == "gpsdo"
    assert result["time_source"] == "gpsdo"
    assert result["reason"] is None


def test_gps_locked_false_reported_faithfully():
    result = probe_gpsdo_status(FakeBackend(sensors={"gps_locked": False}))
    assert result["gps_locked"] is False
    assert result["available"] is False
    assert result["sensors_read"] == ["gps_locked"]
    assert result["reason"] == "gps_not_locked"


def test_no_gps_methods_but_clock_source_readable():
    class ClockOnlyBackend:
        def get_clock_source(self):
            return "internal"

    result = probe_gpsdo_status(ClockOnlyBackend())
    assert result["available"] is False
    assert result["gps_locked"] is None
    assert result["sensors_read"] == []
    assert result["clock_source"] == "internal"
    assert result["time_source"] is None
    assert result["reason"] == "no_gps_support"


def test_backend_none():
    result = probe_gpsdo_status(None)
    assert result == {
        "available": False,
        "gps_locked": None,
        "clock_source": None,
        "time_source": None,
        "sensors_read": [],
        "reason": "no_backend",
    }


def test_sensor_exception_recorded_without_raising():
    backend = FakeBackend(sensor_error=RuntimeError("uhd boom"),
                          failing_sensors=ALL_GPS_SENSORS)
    result = probe_gpsdo_status(backend)  # 所有传感器名均抛错，但不向上抛
    assert result["available"] is False
    assert result["gps_locked"] is None
    assert result["sensors_read"] == []
    assert "gps_locked" in result["reason"]
    assert "RuntimeError" in result["reason"]
    assert "uhd boom" in result["reason"]


@pytest.mark.parametrize("raw", ["True", "true", "Locked", "LOCKED", "1"])
def test_truthy_string_sensor_values(raw):
    result = probe_gpsdo_status(FakeBackend(sensors={"gps_locked": raw}))
    assert result["gps_locked"] is True
    assert result["available"] is True


@pytest.mark.parametrize("raw", ["False", "false", "unlocked", "0", ""])
def test_falsy_string_sensor_values(raw):
    result = probe_gpsdo_status(FakeBackend(sensors={"gps_locked": raw}))
    assert result["gps_locked"] is False
    assert result["available"] is False


def test_first_readable_sensor_in_sequence_wins():
    gpgga = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
    backend = FakeBackend(sensors={"gps_gpgga": gpgga})
    result = probe_gpsdo_status(backend)
    assert result["available"] is True
    assert result["gps_locked"] is True
    assert result["sensors_read"] == ["gps_gpgga"]
    assert "gps_locked" in result["reason"]  # 序列探测中被跳过的传感器记入 reason


def test_missing_time_source_leaves_none():
    backend = FakeBackend(sensors={"gps_locked": True}, clock_source="gpsdo")
    result = probe_gpsdo_status(backend)
    assert result["available"] is True
    assert result["clock_source"] == "gpsdo"
    assert result["time_source"] is None


def test_object_without_any_related_methods():
    result = probe_gpsdo_status(object())
    assert result == {
        "available": False,
        "gps_locked": None,
        "clock_source": None,
        "time_source": None,
        "sensors_read": [],
        "reason": "no_gps_support",
    }


def test_clock_source_failure_accumulates_in_reason():
    backend = FakeBackend(sensors={"gps_locked": True}, fail_clock=True)
    result = probe_gpsdo_status(backend)
    assert result["available"] is True
    assert result["gps_locked"] is True
    assert result["clock_source"] is None
    assert "get_clock_source" in result["reason"]
    assert "RuntimeError" in result["reason"]
