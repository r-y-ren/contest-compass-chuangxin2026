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
    # 真 uhd 口径的 gps_gpgga 传感器对象（自带 to_bool，由探测侧解析真值）：
    # gps_locked 缺（KeyError 记 reason）→ 序列推进到 gpgga，其结论胜出。
    class GpggaSensor:
        def to_bool(self):
            return True

    backend = FakeBackend(sensors={"gps_gpgga": GpggaSensor()})
    result = probe_gpsdo_status(backend)
    assert result["available"] is True
    assert result["gps_locked"] is True
    assert result["sensors_read"] == ["gps_gpgga"]
    assert "gps_locked" in result["reason"]  # 序列探测中被跳过的传感器记入 reason


def test_raw_gpgga_sentence_fail_closed_unrecognized():
    # B6 中#6 后契约：无 to_bool 的裸 NMEA 语句不在词汇表内 → fail-closed 记假
    # （不再按非空字符串真值回退），reason 标注 'unrecognized_sensor_value'。
    gpgga = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
    result = probe_gpsdo_status(FakeBackend(sensors={"gps_gpgga": gpgga}))
    assert result["gps_locked"] is False
    assert result["available"] is False
    assert "unrecognized_sensor_value" in result["reason"]


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


# ---- B6 对抗审查缺陷回归 ----


def test_defect_b6_6_fail_closed_sensor_value_parsing():
    """中#6：真值解析 fail-closed——to_bool 优先；未识别读数一律 False + reason
    标注 'unrecognized_sensor_value'（不再按真值回退假报锁定）。"""
    # 传感器对象有 to_bool()（uhd sensor_value 口径）→ 用之
    class ToBoolSensor:
        def to_bool(self):
            return True

    result = probe_gpsdo_status(FakeBackend(sensors={"gps_locked": ToBoolSensor()}))
    assert result["gps_locked"] is True
    assert result["available"] is True
    assert result["reason"] is None  # to_bool 结论被采信，无失败记录

    # to_bool() 自身抛异常 → 按未识别 fail-closed
    class BoomToBoolSensor:
        def to_bool(self):
            raise RuntimeError("boom")

    result = probe_gpsdo_status(FakeBackend(sensors={"gps_locked": BoomToBoolSensor()}))
    assert result["gps_locked"] is False
    assert result["available"] is False
    assert "unrecognized_sensor_value" in result["reason"]

    # 无 to_bool 的非布尔对象：str() 后词汇表——命中则按词汇表，未识别 fail-closed
    class StringySensor:
        def __str__(self):
            return "locked"

    result = probe_gpsdo_status(FakeBackend(sensors={"gps_locked": StringySensor()}))
    assert result["gps_locked"] is True
    assert result["available"] is True

    class OpaqueSensor:
        def __str__(self):
            return "maybe?"

    result = probe_gpsdo_status(FakeBackend(sensors={"gps_locked": OpaqueSensor()}))
    assert result["gps_locked"] is False  # 不再按 bool(raw) 默认真值回退
    assert result["available"] is False
    assert "unrecognized_sensor_value" in result["reason"]

    # 未识别字符串同理 False（裸 NMEA 语句等非空未知串不再算锁定）
    result = probe_gpsdo_status(FakeBackend(sensors={"gps_locked": "probably locked?"}))
    assert result["gps_locked"] is False
    assert result["available"] is False
    assert result["reason"] == (
        "sensor gps_locked value not recognized (unrecognized_sensor_value): 'probably locked?'"
    )
    assert result["sensors_read"] == ["gps_locked"]  # 读数事实仍在，仅真值按 fail-closed
