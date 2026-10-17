"""normalize_scenario 对抗测试：默认填充+归一+深拷贝；类型仍冲突抛 ScenarioError。"""
from __future__ import annotations

import copy

import pytest

from src.load_scenario.normalize_scenario import normalize_scenario
from src.load_scenario.validate_scenario_schema import (
    ScenarioError,
    validate_scenario_schema,
)


def test_all_defaults_filled():
    out = normalize_scenario({"style": "tone", "fs": 1000000})
    assert out["style"] == "tone"
    assert isinstance(out["fs"], float)
    assert out["fs"] == 1e6
    assert out["power_dbm"] == -10.0
    assert out["duration_s"] == 1.0
    assert out["duty_cycle"] == 0.5
    assert out["repeats"] == 1
    assert isinstance(out["repeats"], int)
    assert out["backend"] == "auto"
    assert out["judge_per_threshold"] == pytest.approx(0.10)
    # freq_hz/bandwidth_hz 无缺省语义：缺省不虚构填充。
    assert "freq_hz" not in out
    assert "bandwidth_hz" not in out


def test_style_uppercase_normalized_to_lowercase():
    out = normalize_scenario({"style": "TONE", "fs": 1e6})
    assert out["style"] == "tone"


def test_numeric_string_values_coerced():
    out = normalize_scenario(
        {
            "style": "tone",
            "fs": "4000000",
            "freq_hz": "2450",
            "repeats": "3",
        }
    )
    assert out["fs"] == 4e6
    assert out["freq_hz"] == 2450.0
    assert isinstance(out["freq_hz"], float)
    assert out["repeats"] == 3


# ---- tx_gain_db 数值化（对抗审查 I4：str 裂缝收敛——与 freq_hz/bandwidth_hz 同款先例） ----


def test_tx_gain_db_numeric_str_coerced_to_float():
    """I4：schema 宽容的数字 str '60'（B17 中#4 PyYAML 口径）在此数值化——
    否则原样透传到 open_b210_backend._as_real 拒 str 运行期炸。"""
    out = normalize_scenario({"style": "tone", "fs": 1e6, "tx_gain_db": "60"})
    assert out["tx_gain_db"] == 60.0
    assert isinstance(out["tx_gain_db"], float)
    out = normalize_scenario({"style": "tone", "fs": 1e6, "tx_gain_db": 55})
    assert out["tx_gain_db"] == 55.0


def test_tx_gain_db_absent_not_filled():
    """无缺省语义：缺失不填（注入判定按键在场，不虚构 60.0）。"""
    out = normalize_scenario({"style": "tone", "fs": 1e6})
    assert "tx_gain_db" not in out


def test_tx_gain_db_bad_shapes_raise_scenario_error():
    """bool/非数字 str 拒（_to_float 口径：bool 是 int 子类但语义是开关）。"""
    with pytest.raises(ScenarioError, match="tx_gain_db"):
        normalize_scenario({"style": "tone", "fs": 1e6, "tx_gain_db": True})
    with pytest.raises(ScenarioError, match="tx_gain_db"):
        normalize_scenario({"style": "tone", "fs": 1e6, "tx_gain_db": "abc"})


def test_backend_sim_normalized_to_lowercase():
    out = normalize_scenario({"style": "tone", "fs": 1e6, "backend": "SIM"})
    assert out["backend"] == "sim"


def test_deep_copy_output_never_mutates_input():
    raw = {
        "style": "composite",
        "fs": 4e6,
        "components": [
            {"style": "tone", "fs": 1e6, "freq_hz": 100e3},
            {"style": "partial_band", "fs": 2e6, "bandwidth_hz": 500e3},
        ],
        "notes": {"tags": ["baseline"]},  # 未知键带嵌套可变对象（透传）
    }
    snapshot = copy.deepcopy(raw)
    out = normalize_scenario(raw)
    assert raw == snapshot
    # 改写输出（含嵌套分量与透传未知键）不影响入参。
    out["components"][0]["freq_hz"] = 999.0
    out["components"][1]["bandwidth_hz"] = 123.0
    out["notes"]["tags"].append("mutated")
    out["power_dbm"] = 3.0
    assert raw == snapshot


def test_judge_per_threshold_default_and_override():
    out = normalize_scenario({"style": "pulse", "fs": 1e6})
    assert out["judge_per_threshold"] == pytest.approx(0.10)
    out2 = normalize_scenario(
        {"style": "pulse", "fs": 1e6, "judge_per_threshold": 0.25}
    )
    assert out2["judge_per_threshold"] == pytest.approx(0.25)


def test_type_conflicts_raise_scenario_error():
    with pytest.raises(ScenarioError, match="fs"):
        normalize_scenario({"style": "tone", "fs": "not-a-number"})
    with pytest.raises(ScenarioError, match="freq_hz"):
        normalize_scenario({"style": "tone", "fs": 1e6, "freq_hz": None})
    with pytest.raises(ScenarioError, match="repeats"):
        normalize_scenario({"style": "pulse", "fs": 1e6, "repeats": 2.5})


def test_missing_fs_and_unknown_backend_raise():
    with pytest.raises(ScenarioError, match="fs"):
        normalize_scenario({"style": "tone"})
    with pytest.raises(ScenarioError, match="backend"):
        normalize_scenario({"style": "tone", "fs": 1e6, "backend": "hackrf"})


def test_composite_normalization_round_trip():
    raw = {
        "style": "COMPOSITE",
        "fs": 4e6,
        "components": [
            {"style": "tone", "fs": 2.4e6, "freq_hz": "2450"},
            {"style": "PARTIAL_BAND", "fs": 10e6, "bandwidth_hz": "2e6"},
        ],
    }
    out = normalize_scenario(raw)
    assert out["style"] == "composite"
    assert out["fs"] == 4e6
    # 分量递归同口径：小写归一 + 数值化宽容 + 默认填充。
    assert out["components"][0]["style"] == "tone"
    assert out["components"][0]["freq_hz"] == 2450.0
    assert isinstance(out["components"][0]["freq_hz"], float)
    assert out["components"][1]["style"] == "partial_band"
    assert out["components"][1]["bandwidth_hz"] == 2e6
    assert out["components"][0]["power_dbm"] == -10.0
    assert out["components"][1]["backend"] == "auto"
    assert out["components"][1]["judge_per_threshold"] == pytest.approx(0.10)
    # 往返：规范化产物再过 schema 校验应零错误。
    assert validate_scenario_schema(out) == []
