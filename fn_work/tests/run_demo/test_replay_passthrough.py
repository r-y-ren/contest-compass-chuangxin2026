"""run_demo R64 快速通道改造回归：_backend_params 按 backend 类型透传 replay 参数
+ _normalize_scenario_object 的 replay 信封键落位（改造点登记于责任文档 R64 块引言）。

向后兼容口径：非 replay 后端不透传 sigmf_path/speed（场景携此键仍按未知键拒——
既有 schema 纪律不放松）；replay 后端缺 sigmf_path → ValueError 早拒。
"""
import pytest

from src.run_demo.run_demo import (
    LoadScenarioError,
    _backend_params,
    _normalize_scenario_object,
)


def _replay_scenario(**overrides):
    """合法 replay 场景（sigmf_path/speed 信封键+声明齐全）。"""
    base = {
        "style": "tone",
        "fs": 1.0e6,
        "freq_hz": 2.4e9,
        "power_dbm": -10.0,
        "duration_s": 0.005,
        "backend": "replay",
        "sigmf_path": "/data/rec/20260101.sigmf-meta",
        "speed": 2.0,
        "bands": [[2400.0, 2483.5]],
        "shielded_box": True,
        "dut_scope": "self_built",
    }
    base.update(overrides)
    return base


# ---- _backend_params：按 backend 类型透传 ----


def test_backend_params_sim_keeps_freq_only():
    """sim 口径不变：仅 freq_hz 透传（正有限实数）。

    b210 不再同锁（2026-10-17，R95 改造点②有意变更）：场景无 tx_gain_db 时
    _backend_params 注入缺省基准 resolve_base_tx_gain()=60.0——修复 B210 打开
    缺省 0dB 耳语；原 `== {}` 断言与注入口径互斥，随双白名单扩键更新。
    """
    assert _backend_params({"backend": "sim", "freq_hz": 2.4e9}) == {
        "freq_hz": 2.4e9
    }
    assert _backend_params({"backend": "sim", "freq_hz": -1.0}) == {}
    # R95（2026-10-17）：b210 无键 → 注入基准增益 60dB（显式键=专家直通覆盖）。
    assert _backend_params({"backend": "b210"}) == {"tx_gain_db": 60.0}


def test_backend_params_replay_passes_sigmf_path_and_speed():
    """replay→sigmf_path+speed 透传（freq_hz 同前）——R64 通路补齐。"""
    params = _backend_params(_replay_scenario())
    assert params == {
        "freq_hz": 2.4e9,
        "sigmf_path": "/data/rec/20260101.sigmf-meta",
        "speed": 2.0,
    }


def test_backend_params_replay_speed_optional_defaults_absent():
    """speed 缺省不在参数 dict（open_replay_backend 缺省 1.0）。"""
    params = _backend_params(_replay_scenario(speed=None))
    assert params == {
        "freq_hz": 2.4e9,
        "sigmf_path": "/data/rec/20260101.sigmf-meta",
    }


def test_backend_params_replay_missing_sigmf_path_rejected():
    """replay 缺 sigmf_path→ValueError 早拒（消息指明必填）。"""
    with pytest.raises(ValueError, match="sigmf_path"):
        _backend_params({"backend": "replay", "freq_hz": 2.4e9})


def test_backend_params_non_replay_ignores_replay_keys():
    """非 replay 后端不透传 replay 键（sigmf_path 在场亦忽略——向后兼容）。"""
    params = _backend_params(
        {"backend": "sim", "freq_hz": 2.4e9, "sigmf_path": "/x.sigmf-meta"}
    )
    assert params == {"freq_hz": 2.4e9}


# ---- _normalize_scenario_object：replay 信封键落位 ----


def test_normalize_replay_scenario_keeps_envelope_keys():
    """replay 场景的 sigmf_path/speed 过三件套后原样落位顶层（schema 不在册但
    按 R64 信封键口径透传——_backend_params 的消费前提）。"""
    prepared = _normalize_scenario_object(_replay_scenario())
    assert prepared["sigmf_path"] == "/data/rec/20260101.sigmf-meta"
    assert prepared["speed"] == 2.0
    assert prepared["backend"] == "replay"
    assert prepared["shielded_box"] is True and prepared["dut_scope"] == "self_built"


def test_normalize_non_replay_scenario_still_rejects_replay_keys():
    """非 replay 场景携 sigmf_path/speed→仍按未知键拒（既有纪律不放松）。"""
    with pytest.raises(LoadScenarioError, match="未知键"):
        _normalize_scenario_object(
            _replay_scenario(backend="sim")
        )


def test_normalize_replay_bad_envelope_value_survives_to_backend_factory():
    """speed 非法值不在规范化层拦截（域校验归 open_replay_backend ≥0.1 口径）——
    信封键只透传不判域。"""
    prepared = _normalize_scenario_object(_replay_scenario(speed=0.01))
    assert prepared["speed"] == 0.01
