"""bridge_to_sitl 对抗单测：slug=sitl_bridge——map_per_to_injection 映射数值独立复算+饱和/空表/NaN 拒；bridge dry_run 参数表+缺库路径（monkeypatch sys.modules）+连接 None 跳过+缺 steps 拒+真连 mock 层参数下发。"""
from __future__ import annotations

import sys
import types

import pytest

from src.bridge_to_sitl.bridge_to_sitl import SitlWarn, bridge_to_sitl
from src.bridge_to_sitl.map_per_to_injection import map_per_to_injection

_PARAM_LOSS = "SIM_PACKET_LOSS"
_PARAM_LATENCY = "SIM_LATENCY_MS"


# --- map_per_to_injection：纯函数映射口径 ---


def test_sitl_bridge_map_three_step_values_independently_recomputed():
    """三台阶映射数值独立复算：丢包线性直通+饱和钳位+|Δlevel| 时延线性。"""
    steps = [
        {"per": 0.10, "level_db": -5.0},
        {"per": 0.50, "level_db": 0.0},
        {"per": 0.99, "level_db": 5.0},
    ]
    params = {"max_packet_loss": 0.95, "latency_per_db_ms": 2.0, "base_latency_ms": 5.0}
    out = map_per_to_injection(steps, params)
    assert len(out) == 3
    # 独立复算（ref 缺省取首档 level=-5）：
    #   档0: loss=0.10            latency=5+|(-5)-(-5)|*2=5.0   未饱和
    #   档1: loss=0.50            latency=5+|0-(-5)|*2=15.0     未饱和
    #   档2: 0.99>=0.95 → 0.95    latency=5+|5-(-5)|*2=25.0     饱和
    assert out[0]["packet_loss"] == pytest.approx(0.10)
    assert out[0]["latency_ms"] == pytest.approx(5.0)
    assert out[0]["saturated"] is False
    assert out[1]["packet_loss"] == pytest.approx(0.50)
    assert out[1]["latency_ms"] == pytest.approx(15.0)
    assert out[1]["saturated"] is False
    assert out[2]["packet_loss"] == pytest.approx(0.95)
    assert out[2]["latency_ms"] == pytest.approx(25.0)
    assert out[2]["saturated"] is True
    # 溯源字段：per/level_db 逐档回带
    for row, step in zip(out, steps):
        assert row["per"] == pytest.approx(step["per"])
        assert row["level_db"] == pytest.approx(step["level_db"])
    # 公式独立复算（不依赖手写常数）：latency = base + |level - ref| * k
    for row in out:
        assert row["latency_ms"] == pytest.approx(5.0 + abs(row["level_db"] + 5.0) * 2.0)


def test_sitl_bridge_map_explicit_ref_level_overrides_default():
    """显式 ref_level_db：时延按给定参考电平复算（不再取首档）。"""
    steps = [{"per": 0.2, "level_db": -10.0}, {"per": 0.4, "level_db": 2.0}]
    out = map_per_to_injection(steps, {"ref_level_db": 0.0, "latency_per_db_ms": 3.0})
    assert out[0]["latency_ms"] == pytest.approx(5.0 + 10.0 * 3.0)
    assert out[1]["latency_ms"] == pytest.approx(5.0 + 2.0 * 3.0)


def test_sitl_bridge_map_saturation_boundary_at_max():
    """饱和边界：per==max 恰饱和（loss 钳位）；per 略低于 max 不饱和。"""
    steps = [{"per": 0.95, "level_db": 0.0}, {"per": 0.9499, "level_db": 0.0}]
    out = map_per_to_injection(steps, {})
    assert out[0]["saturated"] is True
    assert out[0]["packet_loss"] == pytest.approx(0.95)
    assert out[1]["saturated"] is False
    assert out[1]["packet_loss"] == pytest.approx(0.9499)


def test_sitl_bridge_map_empty_steps_returns_empty_list():
    """空台阶 → 空参数表（空表标注，不抛）。"""
    assert map_per_to_injection([], {}) == []


def test_sitl_bridge_map_rejects_nan_negative_and_gt1_per():
    """per 非法域拒收：NaN/负/>1 一律 ValueError（bool 同拒）。"""
    for bad in [float("nan"), -0.01, 1.01, float("inf"), True, "0.5"]:
        with pytest.raises(ValueError):
            map_per_to_injection([{"per": bad, "level_db": 0.0}], {})
    # 域内边界合法：0.0 与 1.0 均应通过
    ok = map_per_to_injection(
        [{"per": 0.0, "level_db": 0.0}, {"per": 1.0, "level_db": 0.0}], {}
    )
    assert ok[0]["packet_loss"] == pytest.approx(0.0)
    assert ok[1]["saturated"] is True  # 1.0 >= 0.95 上限


def test_sitl_bridge_map_shape_errors():
    """形状错拒收：steps 非 list/档非 dict/缺字段/params 非 dict/参数越域。"""
    with pytest.raises(ValueError):
        map_per_to_injection("not-a-list", {})
    with pytest.raises(ValueError):
        map_per_to_injection([0.1, 0.2], {})
    with pytest.raises(ValueError):
        map_per_to_injection([{"per": 0.1}], {})  # 缺 level_db
    with pytest.raises(ValueError):
        map_per_to_injection([{"level_db": 0.0}], {})  # 缺 per
    with pytest.raises(ValueError):
        map_per_to_injection([{"per": 0.1, "level_db": float("nan")}], {})
    with pytest.raises(ValueError):
        map_per_to_injection([{"per": 0.1, "level_db": 0.0}], "params")
    with pytest.raises(ValueError):
        map_per_to_injection([], {"max_packet_loss": 1.5})  # 越界 (0,1]
    with pytest.raises(ValueError):
        map_per_to_injection([], {"max_packet_loss": 0.0})
    with pytest.raises(ValueError):
        map_per_to_injection([], {"base_latency_ms": -1.0})
    with pytest.raises(ValueError):
        map_per_to_injection([], {"latency_per_db_ms": -0.5})


def test_sitl_bridge_map_is_pure_and_does_not_mutate_inputs():
    """纯函数：同输入两次调用等价；入参 steps/params 不被改写。"""
    steps = [{"per": 0.3, "level_db": -2.0}, {"per": 0.97, "level_db": 3.0}]
    params = {"max_packet_loss": 0.9}
    first = map_per_to_injection(steps, params)
    second = map_per_to_injection(steps, params)
    assert first == second
    assert steps == [{"per": 0.3, "level_db": -2.0}, {"per": 0.97, "level_db": 3.0}]
    assert params == {"max_packet_loss": 0.9}


# --- bridge_to_sitl：桥接编排（不在位跳过不阻塞） --


def _result(steps=None):
    """B13 风格运行结果（steps_executed 台阶表）。"""
    if steps is None:
        steps = [
            {"per": 0.1, "level_db": -5.0},
            {"per": 0.5, "level_db": 0.0},
            {"per": 1.0, "level_db": 5.0},
        ]
    return {"status": "completed", "steps_executed": steps}


def test_sitl_bridge_dry_run_produces_injection_table_only():
    """dry_run：只产参数表（bridged/dry_run True），与 map 独立复算一致。"""
    sitl_config = {"connection": "udp:127.0.0.1:14540"}
    out = bridge_to_sitl(_result(), sitl_config, dry_run=True)
    assert out["bridged"] is True
    assert out["dry_run"] is True
    expected = map_per_to_injection(_result()["steps_executed"], {})
    assert out["injections"] == expected
    assert out["n_injections"] == 3
    # 独立复算末档：per=1.0 饱和至 0.95、时延 5+10*2=25
    assert out["injections"][-1]["packet_loss"] == pytest.approx(0.95)
    assert out["injections"][-1]["latency_ms"] == pytest.approx(25.0)
    assert out["injections"][-1]["saturated"] is True


def test_sitl_bridge_dry_run_mapping_params_passthrough():
    """dry_run 透传 sitl_config['mapping_params'] 覆盖缺省映射参数。"""
    out = bridge_to_sitl(
        _result(),
        {
            "connection": "udp:127.0.0.1:14540",
            "mapping_params": {"latency_per_db_ms": 10.0, "base_latency_ms": 1.0},
        },
        dry_run=True,
    )
    assert out["injections"][0]["latency_ms"] == pytest.approx(1.0)
    assert out["injections"][2]["latency_ms"] == pytest.approx(1.0 + 10.0 * 10.0)


def test_sitl_bridge_missing_pymavlink_returns_not_bridged_with_hint(monkeypatch):
    """缺库路径：sys.modules['pymavlink']=None → SitlWarn+reason=pymavlink_missing（不抛）。"""
    monkeypatch.setitem(sys.modules, "pymavlink", None)
    with pytest.warns(SitlWarn):
        out = bridge_to_sitl(_result(), {"connection": "udp:127.0.0.1:14540"})
    assert out["bridged"] is False
    assert out["reason"] == "pymavlink_missing"
    assert "pip install pymavlink" in out["hint"]
    # 参数表仍携带（跳过不等于丢数据）
    assert len(out["injections"]) == 3


def test_sitl_bridge_connection_none_skips_with_reason():
    """连接 None：跳过+标注（SitlWarn 警告、bridged False、reason 注明未配置）。"""
    with pytest.warns(SitlWarn):
        out = bridge_to_sitl(_result(), {"connection": None})
    assert out["bridged"] is False
    assert out["dry_run"] is False
    assert out["reason"] == "connection_not_configured"
    assert len(out["injections"]) == 3


def test_sitl_bridge_missing_steps_rejected():
    """result 缺 'steps_executed' → ValueError（无可桥接数据先拒）。"""
    with pytest.raises(ValueError, match="steps_executed"):
        bridge_to_sitl({"status": "completed"}, {"connection": None})
    with pytest.raises(ValueError):
        bridge_to_sitl("not-a-dict", {"connection": None})
    with pytest.raises(ValueError):
        bridge_to_sitl(_result(), "not-a-dict")
    # B13 汇总口径 steps_executed 为 int（非台阶表）——形状错拒
    with pytest.raises(ValueError):
        bridge_to_sitl({"steps_executed": 3}, {"connection": None})


class _FakeMav:
    """简化 MAVLink mock 层：记录 param_set_send 调用。"""

    def __init__(self, recorder):
        self._rec = recorder

    def param_set_send(self, name, value):
        self._rec.append((name, float(value)))


class _FakeConn:
    """连接对象 mock：心跳+参数通道+close 记录。"""

    def __init__(self, recorder, fail_heartbeat=False):
        self._rec = recorder
        self._fail = fail_heartbeat
        self.mav = _FakeMav(recorder)

    def wait_heartbeat(self, timeout=None):
        self._rec.append(("heartbeat", timeout))
        if self._fail:
            raise OSError("no heartbeat within timeout")

    def close(self):
        self._rec.append(("close",))


def _install_fake_pymavlink(monkeypatch, conn_factory):
    """把伪造 pymavlink.mavutil 塞进 sys.modules（延迟 import 命中假件）。"""
    recorder = []

    def mavlink_connection(connection, *args, **kwargs):
        return conn_factory(recorder)

    mavutil_mod = types.ModuleType("pymavlink.mavutil")
    mavutil_mod.mavlink_connection = mavlink_connection
    pkg = types.ModuleType("pymavlink")
    pkg.mavutil = mavutil_mod
    monkeypatch.setitem(sys.modules, "pymavlink", pkg)
    monkeypatch.setitem(sys.modules, "pymavlink.mavutil", mavutil_mod)
    return recorder


def test_sitl_bridge_connection_failure_skips_not_raises(monkeypatch):
    """连接/心跳失败：SitlWarn+reason=connection_failed（安全断开跳过，不抛）。"""
    recorder = _install_fake_pymavlink(
        monkeypatch, lambda rec: _FakeConn(rec, fail_heartbeat=True)
    )
    with pytest.warns(SitlWarn):
        out = bridge_to_sitl(_result(), {"connection": "udp:127.0.0.1:14599"})
    assert out["bridged"] is False
    assert out["reason"] == "connection_failed"
    assert "OSError" in out["error"]
    assert len(out["injections"]) == 3
    # 未走到参数下发（recorder 只含心跳记录；参数调用均为二元组）
    assert all(
        len(item) != 2 or item[0] not in (_PARAM_LOSS, _PARAM_LATENCY)
        for item in recorder
    )


def test_sitl_bridge_live_path_sends_params_per_injection(monkeypatch):
    """真连 mock 层：心跳+逐注入档两条参数（丢包/时延）+安全 close。"""
    recorder = _install_fake_pymavlink(monkeypatch, lambda rec: _FakeConn(rec))
    out = bridge_to_sitl(_result(), {"connection": "udp:127.0.0.1:14540"})
    assert out["bridged"] is True
    assert out["dry_run"] is False
    injections = out["injections"]
    param_calls = [item for item in recorder if len(item) == 2]  # 心跳/close 非参数调用
    loss_calls = [v for name, v in param_calls if name == _PARAM_LOSS]
    latency_calls = [v for name, v in param_calls if name == _PARAM_LATENCY]
    assert loss_calls == [pytest.approx(i["packet_loss"]) for i in injections]
    assert latency_calls == [pytest.approx(i["latency_ms"]) for i in injections]
    assert ("heartbeat", 2.0) in recorder  # 缺省心跳超时
    assert ("close",) in recorder
    assert len(out["params_sent"]) == 2 * len(injections)


def test_sitl_bridge_param_send_failure_skips_not_raises(monkeypatch):
    """参数下发异常：SitlWarn+reason=param_send_failed（安全断开跳过，不抛）。"""

    class _BrokenMav:
        def param_set_send(self, name, value):
            raise RuntimeError("link dropped mid-param")

    class _BrokenConn:
        mav = _BrokenMav()

        def wait_heartbeat(self, timeout=None):
            return None

        def close(self):
            pass

    _install_fake_pymavlink(monkeypatch, lambda rec: _BrokenConn())
    with pytest.warns(SitlWarn):
        out = bridge_to_sitl(_result(), {"connection": "udp:127.0.0.1:14540"})
    assert out["bridged"] is False
    assert out["reason"] == "param_send_failed"
    assert "RuntimeError" in out["error"]


def test_sitl_bridge_empty_steps_dry_run_empty_table():
    """空台阶表：dry_run 合法产空注入表（空表标注不拒）。"""
    out = bridge_to_sitl(_result(steps=[]), {"connection": None}, dry_run=True)
    assert out["bridged"] is True
    assert out["injections"] == []
    assert out["n_injections"] == 0
