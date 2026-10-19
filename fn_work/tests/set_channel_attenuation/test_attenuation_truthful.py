"""R97 记账如实化测试（B52，slug=attenuation_truthful）：_dispatch_backend 事件记账层——
形态②事件/返回增 tx_gain_db（物理换算列，未标定）+coarse_semantics='gain_budget'
（粗档=增益预算记账分量）与 applied_via='tx_gain' 进事件体（B51 门 I1 承接：R95
验收②字面达成）；深档地板事件 tx_gain_db=0；形态③ sim 事件体逐字节零变化反断言
（键集+各值硬编码——applied_via 仅返回携带、unknown_gain 有意保留防误判）；形态①
事件体 applied_via 补齐（返回已有、事件补齐=如实对称）。报告侧"未标定换算"脚注
（build_report）用例在 tests/build_report/test_build_report.py 扩展承载。"""
from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src.set_channel_attenuation.set_channel_attenuation import set_channel_attenuation
from src.shared.resolve_base_tx_gain import resolve_base_tx_gain

#: 六档口径：demo 档位 −25…0dBm → 衰减请求 25…0 → 实达 30/20/15/10/5/0 →
#: 物理下发增益 30/40/45/50/55/60（首档差 10dB、其余 5dB，顶档=C 相位实测锚）。
_SIX_TARGETS_DB = [25.0, 20.0, 15.0, 10.0, 5.0, 0.0]
_SIX_EXPECTED_GAINS_DB = [30.0, 40.0, 45.0, 50.0, 55.0, 60.0]

#: 地板用例域：粗 30+细 40 → 请求 70 可达且实达 70 > 基准 60 → 增益地板。
_FLOOR_DOMAIN = {"coarse_db": 30.0, "fine_steps_db": [0.0, 40.0]}

#: 改造前（B51 后、B52 前）sim 形态事件体口径——键集硬编码，逐字节零变化反断言
#: （演进轮⑤硬约束：unknown_gain/无 applied_via/无 tx_gain_db/无 coarse_semantics）。
_SIM_EVENT_KEYS = {
    "type",
    "target_db",
    "coarse",
    "coarse_db",
    "fine_step_db",
    "fine_actual_db",
    "achieved_db",
    "residual_db",
    "fine_from",
    "applied",
    "ts",
    "wallclock",
}

#: 形态②（B210）正常档事件体精确键集（B52 对抗 M-1：sim 有 _SIM_EVENT_KEYS 硬编码
#: 反断言而形态②仅逐字段断言，未来杂键不会被拦）＝sim 同源底盘（含 ts/wallclock
#: 自然戳——实跑确认在事件体，纳入策略与 _SIM_EVENT_KEYS 同款）＋形态②三新键
#: tx_gain_db/coarse_semantics/applied_via；键集为实跑打印采集后写死（六档逐档一致）。
_B210_EVENT_KEYS = {
    "type",
    "target_db",
    "coarse",
    "coarse_db",
    "fine_step_db",
    "fine_actual_db",
    "achieved_db",
    "residual_db",
    "fine_from",
    "tx_gain_db",
    "coarse_semantics",
    "applied",
    "applied_via",
    "ts",
    "wallclock",
}


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


def test_attenuation_truthful_b210_six_level_event_gain_column_and_semantics(tmp_path):
    """① B210 形态逐档事件断言：applied 无 unknown_gain、applied_via='tx_gain'
    在事件体、tx_gain_db=基准−achieved 逐档对拍（六档增益 30/40/45/50/55/60）、
    coarse_semantics='gain_budget'；返回同携双列（事件与返回增列同源）。"""
    base = resolve_base_tx_gain()
    for target, expected_gain in zip(_SIX_TARGETS_DB, _SIX_EXPECTED_GAINS_DB):
        run_dir = tmp_path / f"step_{target:g}"
        run_dir.mkdir()
        backend = _b210_mock()
        result = set_channel_attenuation(
            {"backend": backend, "run_dir": str(run_dir)}, target
        )
        (event,) = _read_events(run_dir)
        assert event["applied"] is True  # 无 unknown_gain（R97：仅 sim 形态保留）
        assert event["applied_via"] == "tx_gain"  # 进事件体（I1：R95 验收②字面达成）
        assert event["tx_gain_db"] == pytest.approx(base - event["achieved_db"])
        assert event["tx_gain_db"] == pytest.approx(expected_gain)
        assert event["coarse_semantics"] == "gain_budget"
        assert "unknown_gain" not in str(event["applied"])
        # 返回同携双列（经实达组合摊开——事件与返回同源）
        assert result["tx_gain_db"] == pytest.approx(expected_gain)
        assert result["coarse_semantics"] == "gain_budget"
        assert result["applied_via"] == "tx_gain"
        backend.set_tx_gain.assert_called_once_with(expected_gain)


def test_attenuation_truthful_b210_gain_floor_event_tx_gain_zero(tmp_path):
    """② 深档地板（请求 70 > 基准 60）：事件 partial+gain_floor+achieved=60+
    tx_gain_db=0（物理换算列如实=地板下发增益 0）。"""
    backend = _b210_mock()
    result = set_channel_attenuation(
        {"backend": backend, "run_dir": str(tmp_path)}, 70.0, domain=_FLOOR_DOMAIN
    )
    backend.set_tx_gain.assert_called_once_with(0)
    (event,) = _read_events(tmp_path)
    assert event["applied"] == "partial" and event["applied_detail"] == "gain_floor"
    assert event["applied_via"] == "tx_gain"
    assert event["target_db"] == 70.0 and event["achieved_db"] == 60.0
    assert event["tx_gain_db"] == 0.0
    assert event["coarse_semantics"] == "gain_budget"
    assert result["tx_gain_db"] == 0.0  # 返回同携


def test_attenuation_truthful_b210_event_keyset_pinned(tmp_path):
    """⑤ B210 形态事件键集精确钉住（B52 对抗 M-1）：六档逐档 set(event)==
    _B210_EVENT_KEYS——形态②此前仅逐字段断言，多键/漏键不会被拦（sim 已有键集
    硬编码先例，此处同款补齐）；ts/wallclock 自然戳实跑确认在事件体并纳入键集。"""
    for target in _SIX_TARGETS_DB:
        run_dir = tmp_path / f"keyset_{target:g}"
        run_dir.mkdir()
        set_channel_attenuation(
            {"backend": _b210_mock(), "run_dir": str(run_dir)}, target
        )
        (event,) = _read_events(run_dir)
        # 键集逐档精确钉住；变异自证：若实现给形态②误加/漏加任一键，本用例即红。
        assert set(event) == _B210_EVENT_KEYS
        # 自然戳类型对拍（纳入键集后的同款口径，承 sim 用例）
        assert isinstance(event["ts"], int) and isinstance(event["wallclock"], str)
        # 正常档杂键显式点名（键集相等已蕴含，点名助读：地板/未下发键绝不在）
        for absent in ("applied_detail", "reason"):
            assert absent not in event


def test_attenuation_truthful_sim_event_byte_identical_zero_change(tmp_path):
    """③ sim 形态零变化反断言：fake 仅 set_tx_gain——事件 dict 键集与各值与改造前
    口径完全一致（unknown_gain/无 applied_via/无 tx_gain_db/无 coarse_semantics，
    键集硬编码钉住）；applied_via='set_tx_gain' 仅返回携带。"""
    backend = Mock(spec=["set_tx_gain"])
    result = set_channel_attenuation({"backend": backend, "run_dir": str(tmp_path)}, 35.0)
    backend.set_tx_gain.assert_called_once_with(-5.0)  # 旧相对增量路径原样
    (event,) = _read_events(tmp_path)
    # 键集逐字节零变化（硬约束——演进轮⑤登记：unknown_gain=名义模型口径非缺陷）
    assert set(event) == _SIM_EVENT_KEYS
    assert event["type"] == "attenuation"
    assert event["target_db"] == 35.0
    assert event["coarse"] == "in" and event["coarse_db"] == 30.0
    assert event["fine_step_db"] == 5.0 and event["fine_actual_db"] == 5.0
    assert event["achieved_db"] == 35.0 and event["residual_db"] == 0.0
    assert event["fine_from"] == "nominal"
    assert event["applied"] == "unknown_gain"
    assert isinstance(event["ts"], int) and isinstance(event["wallclock"], str)
    # 三新字段绝不出现于事件体
    for absent in ("applied_via", "tx_gain_db", "coarse_semantics"):
        assert absent not in event
    # 返回仍带 applied_via='set_tx_gain'（操作面口径），且不携物理换算双列
    assert result["applied_via"] == "set_tx_gain" and result["applied"] == "unknown_gain"
    assert "tx_gain_db" not in result and "coarse_semantics" not in result


def test_attenuation_truthful_instrument_event_carries_applied_via(tmp_path):
    """④ 形态① fake（带 set_attenuation）：事件体含 applied_via='set_attenuation'
    （返回已有、事件补齐=如实对称）。"""
    backend = Mock(spec=["set_attenuation"])
    result = set_channel_attenuation(
        {"backend": backend, "run_dir": str(tmp_path)}, 35.0
    )
    backend.set_attenuation.assert_called_once_with(35.0)
    (event,) = _read_events(tmp_path)
    assert event["applied"] is True and event["applied_via"] == "set_attenuation"
    # 仪器形态无物理换算语义：不携 tx_gain_db/coarse_semantics
    assert "tx_gain_db" not in event and "coarse_semantics" not in event
    assert result["applied_via"] == "set_attenuation"
