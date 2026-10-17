"""R95 快速通道改造回归（域二十四改造点②）：_backend_params 的 tx_gain_db
白名单透传与 B210 缺省基准注入（双白名单另一侧=validate_scenario_schema
._KNOWN_KEYS 顶层键，见 tests/load_scenario/test_validate_scenario_schema.py）。

分支边界（sim/replay 零扰动=演进轮⑤范围外硬约束）：tx_gain_db 仅进 b210 分支——
sim 工厂消费 tx_gain_db 且缺省 0（open_sim_backend.py:286），注入即改 sim 行为；
replay 工厂不消费增益键（注册适配器只拆 sigmf_path/speed/block_size 三键），
两分支返回 dict 与改造前逐字节同。场景构造方式对齐 test_replay_passthrough
（同键序的场景 dict 形状）。

对抗审查 C1·Critical（2026-10-17）：注入判定解耦场景键字面——effective 后端
（CLI 显式>场景键>auto 探测）命中 B210 时经 _ensure_b210_tx_gain 在打开后补设
（selection 真值判定，params 面恒零扰动）；场景键字面 b210 路径仍走 params
工厂注入（向后兼容逐字不变）。
"""
from __future__ import annotations

import src.autodetect_backend.autodetect_backend as autodetect_module
from src.autodetect_backend.autodetect_backend import autodetect_backend
from src.run_demo.run_demo import _backend_params, _ensure_b210_tx_gain
from src.shared.resolve_base_tx_gain import resolve_base_tx_gain


def _b210_scenario(**overrides):
    """合法 b210 场景形状（最小后端参数面——_backend_params 只读 backend/freq_hz/增益键）。"""
    base = {
        "style": "tone",
        "fs": 1.0e6,
        "freq_hz": 2.4e9,
        "power_dbm": -10.0,
        "duration_s": 0.005,
        "backend": "b210",
    }
    base.update(overrides)
    return base


def _sim_scenario(**overrides):
    """手册标准形状：scenarios/*.yaml 全写 backend: sim（C1 缺陷场景）。"""
    return _b210_scenario(backend="sim", **overrides)


class _FakeGainBackend:
    """记录 set_tx_gain 调用的假后端（C1 断言注入真值）。"""

    def __init__(self):
        self.gain_calls: list = []

    def set_tx_gain(self, db):
        self.gain_calls.append(db)
        return db

    def stop_tx(self):
        return {"status": "ok"}


def test_tx_gain_passthrough_explicit_value_forwarded():
    """①场景显式 tx_gain_db=55 → b210 分支透传 55（专家直通覆盖）。"""
    params = _backend_params(_b210_scenario(tx_gain_db=55))
    assert params == {"freq_hz": 2.4e9, "tx_gain_db": 55}


def test_tx_gain_passthrough_b210_without_key_injects_base_gain():
    """②场景无键+backend b210 → 注入 resolve_base_tx_gain()（缺省基准 60.0——
    修复非阶梯发射路径缺省 0dB 耳语；工厂 _DEFAULT_TX_GAIN_DB=0 不再被走到）。"""
    params = _backend_params(_b210_scenario())
    assert params["tx_gain_db"] == resolve_base_tx_gain() == 60.0


def test_tx_gain_passthrough_sim_without_key_not_injected():
    """③场景无键+backend sim → 不注入（sim 零扰动：键不在返回 dict）。"""
    params = _backend_params(
        {"backend": "sim", "freq_hz": 2.4e9, "tx_gain_db": 60.0}  # 显式键亦不进 sim 分支
    )
    assert params == {"freq_hz": 2.4e9}
    assert "tx_gain_db" not in params


def test_tx_gain_passthrough_replay_not_injected_and_replay_keys_unchanged():
    """④场景无键+backend replay → 不注入且 replay 专用键行为不变
    （sigmf_path 必填早拒/ speed 可选透传，R64 口径逐字保留）。"""
    params = _backend_params(
        {
            "backend": "replay",
            "freq_hz": 2.4e9,
            "sigmf_path": "/data/rec/20260101.sigmf-meta",
            "speed": 2.0,
        }
    )
    assert params == {
        "freq_hz": 2.4e9,
        "sigmf_path": "/data/rec/20260101.sigmf-meta",
        "speed": 2.0,
    }
    assert "tx_gain_db" not in params


def test_tx_gain_passthrough_out_of_range_value_forwarded_verbatim():
    """⑤显式越界值 95 → 原样透传（域校验归后端工厂 0–89.75——本层不拦，
    断言透传值与场景键逐字节同值）。"""
    params = _backend_params(_b210_scenario(tx_gain_db=95))
    assert params["tx_gain_db"] == 95


# ---- 对抗审查 C1：注入判定按解析后的实际后端（effective，非场景键字面） ----


def test_tx_gain_passthrough_effective_b210_via_cli_injects():
    """C1①：场景 backend:sim + CLI 显式 b210 → selection.backend='b210'（显式
    名打开即定）→ 打开后补设 resolve_base_tx_gain()（params 面零扰动）。"""
    fake = _FakeGainBackend()
    _ensure_b210_tx_gain(fake, {"backend": "b210"}, _sim_scenario())
    assert fake.gain_calls == [resolve_base_tx_gain()] == [60.0]


def test_tx_gain_passthrough_effective_b210_via_probe_hit_injects(monkeypatch):
    """C1②：场景 backend:sim + auto（mock probe 命中 B210，mock 工厂开假后端）
    → autodetect 真决策流 selection.backend='b210' → 补注入 60.0；且 mock 工厂
    收到的 params 不含 tx_gain_db（params 面零扰动证据）。"""
    fake = _FakeGainBackend()
    captured: list = []

    def _fake_open_b210(params):
        captured.append(params)
        return fake

    monkeypatch.setattr(
        autodetect_module,
        "probe_uhd_devices",
        lambda: {"available": True, "devices": [{"product": "B210"}], "error": None},
    )
    monkeypatch.setattr(autodetect_module, "open_b210_backend", _fake_open_b210)
    scenario = _sim_scenario()
    backend_obj, selection = autodetect_backend(None, _backend_params(scenario))
    assert selection["backend"] == "b210"
    _ensure_b210_tx_gain(backend_obj, selection, scenario)
    assert fake.gain_calls == [resolve_base_tx_gain()]
    assert captured == [{"freq_hz": 2.4e9}]  # params 未被塞 tx_gain_db


def test_tx_gain_passthrough_effective_sim_via_probe_miss_no_inject(monkeypatch):
    """C1③：场景 backend:sim + auto 探测不命中（mock probe 无设备→真降级开
    软件仿真后端）→ selection.backend='sim' → 不注入（零扰动保持）。"""
    fake = _FakeGainBackend()
    monkeypatch.setattr(
        autodetect_module,
        "probe_uhd_devices",
        lambda: {"available": False, "devices": [], "error": None},
    )
    scenario = _sim_scenario()
    backend_obj, selection = autodetect_backend(None, _backend_params(scenario))
    assert selection["backend"] == "sim"
    _ensure_b210_tx_gain(fake, selection, scenario)
    assert fake.gain_calls == []


def test_tx_gain_passthrough_effective_b210_scenario_key_b210_no_double_set():
    """C1 护持：场景键字面 b210 路径 params 工厂已带（显式透传/基准注入），
    _ensure_b210_tx_gain 不重复下发（向后兼容=该路径行为逐字不变）。"""
    fake = _FakeGainBackend()
    _ensure_b210_tx_gain(fake, {"backend": "b210"}, _b210_scenario())
    assert fake.gain_calls == []


def test_tx_gain_passthrough_effective_b210_explicit_key_forwarded():
    """C1 护持：effective b210+场景键非 b210+显式 tx_gain_db=55 → 补设专家
    直通值 55（不覆盖为基准 60）。"""
    fake = _FakeGainBackend()
    _ensure_b210_tx_gain(
        fake, {"backend": "b210"}, _sim_scenario(tx_gain_db=55)
    )
    assert fake.gain_calls == [55]


def test_tx_gain_passthrough_normalize_str_gain_chain_end_to_end():
    """I4 链贯通：schema 宽容数字 str '60' → normalize 数值化 60.0 → b210
    params 白名单透传 60.0（str 裂缝收敛的端到端断言）。"""
    from src.load_scenario.normalize_scenario import normalize_scenario

    normalized = normalize_scenario(
        {"style": "tone", "fs": 1.0e6, "backend": "b210", "tx_gain_db": "60"}
    )
    assert normalized["tx_gain_db"] == 60.0
    assert _backend_params(normalized)["tx_gain_db"] == 60.0


def test_tx_gain_passthrough_set_failure_stops_tx_then_reraises():
    """补设失败先停发射再原样重抛（先停发射铁律——B51 scoped 复审补例，原异常不被包装）。"""

    class _FailingGainBackend(_FakeGainBackend):
        def set_tx_gain(self, db):
            raise RuntimeError("UHD: set gain failed")

    import pytest

    fake = _FailingGainBackend()
    stopped: list = []
    fake.stop_tx = lambda: (stopped.append(1), {"status": "ok"})[1]
    with pytest.raises(RuntimeError, match="UHD: set gain failed"):
        _ensure_b210_tx_gain(fake, {"backend": "b210"}, _sim_scenario())
    assert stopped == [1]
