"""resolve_clock_reference 行为用例：时基决策（gpsdo/external/software）对抗 FakeBackend；验收 slug=clocking。"""
from __future__ import annotations

from src.resolve_clock_reference.probe_gpsdo_status import probe_gpsdo_status
from src.resolve_clock_reference.resolve_clock_reference import resolve_clock_reference

RESULT_KEYS = {"clock_ref", "basis", "discipline_applied", "warnings"}

_UNSET = object()


class FakeBackend:
    """鸭子后端：GPS 传感器表 / clock·time 源读写 / 驯服 set 方法可选可失败；未配置的方法置 None 模拟缺失。"""

    def __init__(self, sensors=None, failing_sensors=(), sensor_error=None,
                 clock_source=_UNSET, time_source=_UNSET,
                 fail_clock=False, fail_time=False,
                 has_set_clock=True, has_set_time=True,
                 fail_set_clock=False, fail_set_time=False, set_error=None):
        self._sensors = dict(sensors or {})
        self._failing_sensors = set(failing_sensors)
        self._sensor_error = sensor_error or RuntimeError("sensor read failed")
        self._clock_source = clock_source
        self._time_source = time_source
        self._fail_clock = fail_clock
        self._fail_time = fail_time
        self._fail_set_clock = fail_set_clock
        self._fail_set_time = fail_set_time
        self._set_error = set_error or RuntimeError("set failed")
        self.set_calls: list[tuple[str, str]] = []
        if clock_source is _UNSET and not fail_clock:
            self.get_clock_source = None  # 实例属性遮蔽类方法，模拟方法缺失
        if time_source is _UNSET and not fail_time:
            self.get_time_source = None
        if not has_set_clock:
            self.set_clock_source = None
        if not has_set_time:
            self.set_time_source = None

    def get_mboard_sensor(self, name):
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

    def set_clock_source(self, source):
        self.set_calls.append(("set_clock_source", source))
        if self._fail_set_clock:
            raise self._set_error

    def set_time_source(self, source):
        self.set_calls.append(("set_time_source", source))
        if self._fail_set_time:
            raise self._set_error


def test_clocking_result_key_set():
    result = resolve_clock_reference(FakeBackend(sensors={"gps_locked": True}))
    assert set(result) == RESULT_KEYS


def test_clocking_gps_locked_with_setters_yields_gpsdo_disciplined():
    backend = FakeBackend(sensors={"gps_locked": True}, clock_source="internal", time_source="internal")
    result = resolve_clock_reference(backend)
    assert result["clock_ref"] == "gpsdo"
    assert result["discipline_applied"] is True
    assert result["warnings"] == []
    assert backend.set_calls == [("set_clock_source", "gpsdo"), ("set_time_source", "gpsdo")]
    assert result["basis"]["available"] is True


def test_clocking_set_clock_source_failure_degrades_to_software():
    backend = FakeBackend(sensors={"gps_locked": True},
                          fail_set_clock=True, set_error=RuntimeError("uhd set boom"))
    result = resolve_clock_reference(backend)
    assert result["clock_ref"] == "software"
    assert result["discipline_applied"] is False
    assert any("set_clock_source" in w for w in result["warnings"])
    assert any("uhd set boom" in w for w in result["warnings"])
    assert any("degraded to software" in w for w in result["warnings"])


def test_clocking_set_failures_accumulate_multiple_warnings():
    backend = FakeBackend(sensors={"gps_locked": True}, fail_set_clock=True, fail_set_time=True)
    result = resolve_clock_reference(backend)
    assert result["clock_ref"] == "software"
    assert result["discipline_applied"] is False
    assert len(result["warnings"]) >= 3  # 两条 set 失败原因 + 一条降级结论
    assert any("set_clock_source" in w for w in result["warnings"])
    assert any("set_time_source" in w for w in result["warnings"])
    assert any("degraded to software" in w for w in result["warnings"])


def test_clocking_no_gps_but_external_clock_source_yields_external():
    backend = FakeBackend(clock_source="external", has_set_clock=False, has_set_time=False)
    result = resolve_clock_reference(backend)
    assert result["clock_ref"] == "external"
    assert result["discipline_applied"] is False
    assert result["basis"]["clock_source"] == "external"
    assert result["warnings"] == []
    assert backend.set_calls == []


def test_clocking_backend_without_any_methods_yields_software():
    result = resolve_clock_reference(object())
    assert result["clock_ref"] == "software"
    assert result["discipline_applied"] is False
    assert result["basis"]["reason"] == "no_gps_support"
    assert any("no_gps_support" in w for w in result["warnings"])


def test_clocking_backend_none_yields_software_with_reason():
    result = resolve_clock_reference(None)
    assert result["clock_ref"] == "software"
    assert result["discipline_applied"] is False
    assert result["basis"]["reason"] == "no_backend"
    assert any("no_backend" in w for w in result["warnings"])


def test_clocking_default_backend_argument_matches_none():
    assert resolve_clock_reference() == resolve_clock_reference(None)


def test_clocking_truthy_locked_string_chains_to_gpsdo():
    backend = FakeBackend(sensors={"gps_locked": "Locked"})
    result = resolve_clock_reference(backend)
    assert result["basis"]["gps_locked"] is True
    assert result["basis"]["available"] is True
    assert result["clock_ref"] == "gpsdo"
    assert result["discipline_applied"] is True


def test_clocking_discipline_false_for_external_and_software():
    external = resolve_clock_reference(FakeBackend(clock_source="external", has_set_clock=False, has_set_time=False))
    software = resolve_clock_reference(FakeBackend(clock_source="internal", has_set_clock=False, has_set_time=False))
    assert external["clock_ref"] == "external" and external["discipline_applied"] is False
    assert software["clock_ref"] == "software" and software["discipline_applied"] is False


def test_clocking_gps_locked_without_setters_stays_gpsdo_undisciplined():
    backend = FakeBackend(sensors={"gps_locked": True}, has_set_clock=False, has_set_time=False)
    result = resolve_clock_reference(backend)
    assert result["clock_ref"] == "gpsdo"
    assert result["discipline_applied"] is False
    assert any("missing" in w for w in result["warnings"])
    assert backend.set_calls == []


def test_clocking_basis_equals_raw_probe_output():
    backend = FakeBackend(sensors={"gps_locked": True}, clock_source="gpsdo", time_source="gpsdo")
    result = resolve_clock_reference(backend)
    assert result["basis"] == probe_gpsdo_status(backend)


def test_clocking_never_raises_on_hostile_backend():
    class HostileBackend:
        def __getattr__(self, name):
            raise RuntimeError(f"boom: {name}")

    result = resolve_clock_reference(HostileBackend())  # 不抛出即通过
    assert result["clock_ref"] == "software"
    assert result["discipline_applied"] is False
    assert result["warnings"]
