"""R95 快速通道改造回归（域二十四改造点②）：_backend_params 的 tx_gain_db
白名单透传与 B210 缺省基准注入（双白名单另一侧=validate_scenario_schema
._KNOWN_KEYS 顶层键，见 tests/load_scenario/test_validate_scenario_schema.py）。

分支边界（sim/replay 零扰动=演进轮⑤范围外硬约束）：tx_gain_db 仅进 b210 分支——
sim 工厂消费 tx_gain_db 且缺省 0（open_sim_backend.py:286），注入即改 sim 行为；
replay 工厂不消费增益键（注册适配器只拆 sigmf_path/speed/block_size 三键），
两分支返回 dict 与改造前逐字节同。场景构造方式对齐 test_replay_passthrough
（同键序的场景 dict 形状）。
"""
from __future__ import annotations

from src.run_demo.run_demo import _backend_params
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
