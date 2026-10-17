"""R95 形态②正增益映射测试（B51）：_dispatch_backend 对 set_tx_gain+get_tx_gain 双在
形态下发绝对增益=resolve_base_tx_gain()−achieved_db——六档口径 30/40/45/50/55/60、
增益地板 partial（实际衰减=基准）、sim 旧路径逐字节、真 B210Backend 全链集成（M3）、
no_backend 现状与基准接线（改值生效+ValueError 透传）。R97 面（事件 tx_gain_db/
coarse_semantics 双列字段、sim 有意保留注记、报告脚注）归 B52，不在此。"""
from __future__ import annotations

import json
from unittest.mock import Mock, call

import pytest

import src.set_channel_attenuation.set_channel_attenuation as sa_module
from src.open_b210_backend.open_b210_backend import B210Backend, open_b210_backend
from src.set_channel_attenuation.plan_attenuator_combo import plan_attenuator_combo
from src.set_channel_attenuation.set_channel_attenuation import set_channel_attenuation
from src.shared.resolve_base_tx_gain import resolve_base_tx_gain

#: 六档口径：demo 档位 −25…0dBm → 衰减请求 25…0 → 下发增益 30/40/45/50/55/60
#: （step0 请求 25 经粗档接入超射 achieved=30 → 增益 30；顶档 0 → 基准 60）。
_SIX_TARGETS_DB = [25.0, 20.0, 15.0, 10.0, 5.0, 0.0]
_SIX_EXPECTED_GAINS_DB = [30.0, 40.0, 45.0, 50.0, 55.0, 60.0]

#: 地板用例域：粗 30+细 40 → 请求 70 可达且实达 70 > 基准 60 → 增益地板。
_FLOOR_DOMAIN = {"coarse_db": 30.0, "fine_steps_db": [0.0, 40.0]}


def _reject_constant(name: str) -> None:
    """严格解析哨兵：行内出现 NaN/Infinity 字面量即判失败（承兄弟测试口径）。"""
    raise ValueError(f"非法 JSON 字面量: {name}")


def _read_events(run_dir) -> list[dict]:
    """逐行严格读回 events.jsonl（parse_constant 拒绝非标准字面量）。"""
    raw = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    return [json.loads(line, parse_constant=_reject_constant) for line in raw.splitlines()]


def _b210_mock() -> Mock:
    """形态②假后端：set_tx_gain+get_tx_gain 双在（R96 鸭子特征名=get_tx_gain）。"""
    return Mock(spec=["set_tx_gain", "get_tx_gain"])


class _FakeDevice:
    """轻量鸭子设备（承 test_get_tx_gain 风格，不 import 兄弟私有夹具）：
    set_/get_ 存值对直读回，missing 按名缺方法。"""

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


class _FakeTransport:
    """注入传输：设备/哑流句柄原样回挂（本组集成用例不发射不收，流为哑件）。"""

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


def _open_b210(device) -> B210Backend:
    """注入传输开箱（基线参数合法，开箱 tx_gain_db=10.0）。"""
    return open_b210_backend(
        {
            "transport": _FakeTransport(device),
            "freq_hz": 100e6,
            "sample_rate": 1e6,
            "tx_gain_db": 10.0,
            "clock_ref": "internal",
        }
    )


def test_b210_gain_mapping_six_demo_levels_dispatch_gain_sequence():
    """①六档口径：衰减请求 25…0（demo 档位 −25…0dBm）→ 经 plan_attenuator_combo
    实算组合 → 下发增益序列 30/40/45/50/55/60；逐档对拍 下发=基准−实达。"""
    base = resolve_base_tx_gain()
    dispatched: list[float] = []
    for target in _SIX_TARGETS_DB:
        backend = _b210_mock()
        result = set_channel_attenuation({"backend": backend}, target)
        (gain,) = backend.set_tx_gain.call_args[0]
        dispatched.append(gain)
        planned = plan_attenuator_combo(target)  # 实算组合对拍（同缺省域）
        assert gain == pytest.approx(base - planned["achieved_db"])
        assert result["applied"] is True and result["applied_via"] == "tx_gain"
        assert result["achieved_db"] == planned["achieved_db"]
    assert dispatched == _SIX_EXPECTED_GAINS_DB


def test_b210_gain_mapping_step0_coarse_overshoot_achieved_30_residual_minus_5():
    """①b step0（请求 25）：粗档接入超射——coarse='in'/coarse_db=30、细档 0、
    achieved=30 > 请求 25、residual=−5（过衰减），增益下发 30。"""
    backend = _b210_mock()
    result = set_channel_attenuation({"backend": backend}, 25.0)
    backend.set_tx_gain.assert_called_once_with(30.0)  # 60−30
    assert result["coarse"] == "in" and result["coarse_db"] == 30.0
    assert result["fine_step_db"] == 0.0 and result["fine_actual_db"] == 0.0
    assert result["achieved_db"] == 30.0
    assert result["residual_db"] == pytest.approx(-5.0)
    assert result["applied"] is True and result["applied_via"] == "tx_gain"


def test_b210_gain_mapping_event_achieved_matches_dispatched_combo(tmp_path):
    """②事件断言：run_dir 落 events 后事件 applied=True 且 achieved_db 与实达组合
    逐字段一致；返回 applied_via='tx_gain'（R95 新值）；绝对映射无需先读当前增益
    （唯一后端调用即下发本身）。"""
    backend = _b210_mock()
    result = set_channel_attenuation({"backend": backend, "run_dir": str(tmp_path)}, 35.0)
    backend.set_tx_gain.assert_called_once_with(25.0)  # 基准 60−实达 35
    assert backend.method_calls == [call.set_tx_gain(25.0)]  # 不先读 get_tx_gain
    assert result["applied"] is True and result["applied_via"] == "tx_gain"
    (event,) = _read_events(tmp_path)
    assert event["type"] == "attenuation" and event["target_db"] == 35.0
    assert event["applied"] is True
    assert event["achieved_db"] == result["achieved_db"] == 35.0
    assert event["fine_step_db"] == result["fine_step_db"] == 5.0
    assert event["coarse"] == result["coarse"] == "in"


def test_b210_gain_mapping_gain_floor_partial_when_attenuation_exceeds_base(tmp_path):
    """③地板：衰减请求 70 > 基准 60（域粗30+细40 实达 70）→ 下发增益 0、
    applied='partial'+applied_detail='gain_floor'、achieved=60、residual=10；
    fine_actual=基准−粗档=30（组合自洽：粗30+细30=60）。"""
    backend = _b210_mock()
    result = set_channel_attenuation(
        {"backend": backend, "run_dir": str(tmp_path)}, 70.0, domain=_FLOOR_DOMAIN
    )
    backend.set_tx_gain.assert_called_once_with(0)
    assert result["applied"] == "partial"
    assert result["applied_via"] == "tx_gain" and result["applied_detail"] == "gain_floor"
    assert result["achieved_db"] == 60.0
    assert result["residual_db"] == pytest.approx(10.0)  # 欠衰减=target−基准
    assert result["coarse"] == "in" and result["coarse_db"] == 30.0
    assert result["fine_actual_db"] == pytest.approx(30.0)
    assert result["fine_step_db"] == 40.0  # 请求档如实保留
    (event,) = _read_events(tmp_path)
    assert event["applied"] == "partial" and event["applied_detail"] == "gain_floor"
    assert event["achieved_db"] == 60.0 and event["target_db"] == 70.0


def test_b210_gain_mapping_sim_path_byte_for_byte_preserved(tmp_path):
    """④sim 形态（仅 set_tx_gain 无 get_tx_gain）逐字节：下发值=−fine_step_db、
    applied='unknown_gain'、applied_via='set_tx_gain'（演进轮⑤硬约束，零改变）。"""
    backend = Mock(spec=["set_tx_gain"])
    result = set_channel_attenuation({"backend": backend, "run_dir": str(tmp_path)}, 35.0)
    backend.set_tx_gain.assert_called_once_with(-5.0)  # 旧相对增量路径原样
    assert result["applied"] == "unknown_gain"
    assert result["applied_via"] == "set_tx_gain"
    assert "applied_detail" not in result and "reason" not in result
    (event,) = _read_events(tmp_path)
    assert event["applied"] == "unknown_gain"
    assert event["achieved_db"] == 35.0 and event["fine_step_db"] == 5.0


def test_b210_gain_mapping_integration_real_b210_backend_positive_gain(tmp_path):
    """⑤M3 集成·正增益路：真 B210Backend×set_channel_attenuation 全链——请求 35 →
    设备 set_tx_gain 收 25.0（基准−实达），真回读链同步 tx_gain_db=25.0。"""
    device = _FakeDevice()
    backend = _open_b210(device)
    result = set_channel_attenuation({"backend": backend, "run_dir": str(tmp_path)}, 35.0)
    assert result["applied"] is True and result["applied_via"] == "tx_gain"
    assert result["achieved_db"] == 35.0
    assert device.set_calls["set_tx_gain"] == 25.0
    assert backend.get_tx_gain() == 25.0  # 设备存值对回读（真 get_tx_gain 链）
    assert backend.tx_gain_db == 25.0
    (event,) = _read_events(tmp_path)
    assert event["applied"] is True and event["achieved_db"] == 35.0


def test_b210_gain_mapping_integration_real_b210_backend_gain_floor(tmp_path):
    """⑤M3 集成·地板路：真 B210Backend×set_channel_attenuation 全链——请求 70（域
    粗30+细40）→ 设备 set_tx_gain 收 0、partial+gain_floor、实达改写 60/残差 10。"""
    device = _FakeDevice()
    backend = _open_b210(device)
    result = set_channel_attenuation(
        {"backend": backend, "run_dir": str(tmp_path)}, 70.0, domain=_FLOOR_DOMAIN
    )
    assert result["applied"] == "partial" and result["applied_detail"] == "gain_floor"
    assert result["applied_via"] == "tx_gain"
    assert device.set_calls["set_tx_gain"] == 0
    assert backend.get_tx_gain() == 0.0
    assert result["achieved_db"] == 60.0
    assert result["residual_db"] == pytest.approx(10.0)
    (event,) = _read_events(tmp_path)
    assert event["applied"] == "partial" and event["applied_detail"] == "gain_floor"
    assert event["achieved_db"] == 60.0


def test_b210_gain_mapping_no_backend_reason_unchanged(tmp_path):
    """⑥现状：backend 缺或两方法皆缺 → applied=False+reason='no_backend'。"""
    missing = set_channel_attenuation({"run_dir": str(tmp_path)}, 35.0)
    assert missing["applied"] is False and missing["reason"] == "no_backend"
    assert "applied_via" not in missing
    methodless = set_channel_attenuation(
        {"backend": Mock(spec=[]), "run_dir": str(tmp_path)}, 35.0
    )
    assert methodless["applied"] is False and methodless["reason"] == "no_backend"


def test_b210_gain_mapping_base_gain_consumed_from_resolve_base_tx_gain(monkeypatch):
    """接线：基准真消费 resolve_base_tx_gain——改值 55 → 请求 35 下发 20（55−35）。"""
    monkeypatch.setattr(sa_module, "resolve_base_tx_gain", lambda: 55.0)
    backend = _b210_mock()
    set_channel_attenuation({"backend": backend}, 35.0)
    backend.set_tx_gain.assert_called_once_with(20.0)


def test_b210_gain_mapping_base_gain_valueerror_propagates(monkeypatch):
    """接线：resolve_base_tx_gain 越界 ValueError 透传，且未下发（先解析后下发）。"""
    def _boom():
        raise ValueError("base_tx_gain 越界")

    monkeypatch.setattr(sa_module, "resolve_base_tx_gain", _boom)
    backend = _b210_mock()
    with pytest.raises(ValueError, match="base_tx_gain 越界"):
        set_channel_attenuation({"backend": backend}, 35.0)
    backend.set_tx_gain.assert_not_called()
