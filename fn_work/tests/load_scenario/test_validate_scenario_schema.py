"""validate_scenario_schema 对抗测试：只判形状与数值（不判红线），错误清单空=通过，永不抛出。"""
from __future__ import annotations

import pytest

from src.load_scenario.validate_scenario_schema import validate_scenario_schema

FS = 4e6


def _legal_scenario(style: str) -> dict:
    """七类样式各自的合法满参数样例（错误清单必须为空）。"""
    raw = {
        "style": style,
        "fs": FS,
        "freq_hz": 100e3,
        "power_dbm": -10.0,
        "duration_s": 0.01,
    }
    if style in ("bandlimited_noise", "partial_band"):
        raw["bandwidth_hz"] = 1e6
    if style == "pulse":
        raw["duty_cycle"] = 0.5
        raw["repeats"] = 3
    if style == "composite":
        raw["components"] = [
            {"style": "tone", "fs": 1e6},
            {"style": "partial_band", "fs": 2e6, "bandwidth_hz": 500e3},
        ]
    return raw


# ---- 七类样式（六类在册 + composite）合法样例：错误清单全空 ----


@pytest.mark.parametrize(
    "style",
    [
        "tone",
        "sweep",
        "chirp",
        "bandlimited_noise",
        "partial_band",
        "pulse",
        "composite",
    ],
)
def test_seven_styles_legal_samples_pass(style):
    assert validate_scenario_schema(_legal_scenario(style)) == []


def test_style_case_insensitive_passes():
    raw = _legal_scenario("tone")
    raw["style"] = "TONE"
    assert validate_scenario_schema(raw) == []


# ---- 必填键缺失 → 错误清单非空且指名 ----


def test_missing_style_reports_error():
    errors = validate_scenario_schema({"fs": FS, "freq_hz": 100e3})
    assert errors
    assert any("style" in err for err in errors)


def test_missing_fs_reports_error():
    errors = validate_scenario_schema({"style": "tone", "freq_hz": 100e3})
    assert errors
    assert any("fs" in err for err in errors)


# ---- 数字 str 宽容（B17 中#4）：可 float 且有限的 str 数值通过 ----


def test_numeric_str_fields_accepted():
    # PyYAML 1.1 口径下 '1e6'（无点科学计数）解析为 str——宽容通过待 normalize 数值化。
    raw = {
        "style": "tone",
        "fs": "1e6",
        "freq_hz": " 2450e6 ",
        "power_dbm": "-10",
        "duration_s": "2.5",
        "duty_cycle": "0.5",
        "judge_per_threshold": "0.1",
    }
    assert validate_scenario_schema(raw) == []


@pytest.mark.parametrize("bad", ["abc", "", "  ", "nan", "inf", "-inf", "+Infinity"])
def test_non_numeric_or_non_finite_str_rejected(bad):
    errors = validate_scenario_schema({"style": "tone", "fs": bad})
    assert errors and any("fs" in e for e in errors)


def test_numeric_str_rejection_message_notes_normalization():
    msg = " ".join(validate_scenario_schema({"style": "tone", "fs": "abc"}))
    assert "数字 str" in msg and "规范化" in msg


def test_repeats_integer_str_tolerated_but_fractional_str_rejected():
    assert validate_scenario_schema({"style": "tone", "fs": FS, "repeats": "3"}) == []
    assert validate_scenario_schema({"style": "tone", "fs": FS, "repeats": "3.0"}) == []
    assert validate_scenario_schema({"style": "tone", "fs": FS, "repeats": "abc"}) != []
    errs = validate_scenario_schema({"style": "tone", "fs": FS, "repeats": "2.5"})
    assert any("repeats" in e for e in errs)


# ---- 带限类 bandwidth_hz 必填 ----


@pytest.mark.parametrize("style", ["bandlimited_noise", "partial_band"])
def test_bandlimited_styles_missing_bandwidth_report_error(style):
    raw = _legal_scenario(style)
    del raw["bandwidth_hz"]
    errors = validate_scenario_schema(raw)
    assert errors
    assert any("bandwidth_hz" in err for err in errors)


# ---- 带宽取值域：56 MHz 上限（等号恰过，越限即拒） ----


def test_bandwidth_above_56mhz_rejected():
    raw = _legal_scenario("bandlimited_noise")
    raw["bandwidth_hz"] = 56.1e6
    errors = validate_scenario_schema(raw)
    assert errors
    assert any("bandwidth_hz" in err for err in errors)


def test_bandwidth_exactly_56mhz_passes():
    raw = _legal_scenario("partial_band")
    raw["bandwidth_hz"] = 56e6
    assert validate_scenario_schema(raw) == []


# ---- duty_cycle 严格开区间 (0,1)：边界 0/1 均拒 ----


def test_duty_cycle_zero_rejected():
    raw = _legal_scenario("pulse")
    raw["duty_cycle"] = 0
    errors = validate_scenario_schema(raw)
    assert errors
    assert any("duty_cycle" in err for err in errors)


def test_duty_cycle_one_rejected():
    raw = _legal_scenario("pulse")
    raw["duty_cycle"] = 1
    errors = validate_scenario_schema(raw)
    assert errors
    assert any("duty_cycle" in err for err in errors)


# ---- composite 缺 components → 错误 ----


def test_composite_missing_components_reports_error():
    errors = validate_scenario_schema({"style": "composite", "fs": FS})
    assert errors
    assert any("components" in err for err in errors)


# ---- 未知键：错误清单附「未知键: k」 ----


def test_unknown_key_reports_error():
    raw = _legal_scenario("tone")
    raw["foo"] = 1
    errors = validate_scenario_schema(raw)
    assert errors
    assert any("未知键: foo" in err for err in errors)


# ---- 顶层 tx_gain_db（R95 快速通道改造点①）：在册数值键，域宽归后端工厂 ----


def test_tx_gain_db_legal_values_pass():
    """顶层 tx_gain_db 合法数值过（int/float/数字 str 宽容，B17 中#4 同口径）；
    越界值 95 亦过——域宽 0–89.75 归后端工厂（open_b210_backend），本层不拦。"""
    for ok in (60, 60.0, 0.0, 89.75, 95, "60"):
        raw = _legal_scenario("tone")
        raw["tx_gain_db"] = ok
        assert validate_scenario_schema(raw) == [], ok


@pytest.mark.parametrize(
    "bad", ["abc", float("nan"), float("inf"), float("-inf"), True, False, None, [60.0], {"db": 60}]
)
def test_tx_gain_db_bad_shapes_rejected(bad):
    """非法形状拒（不可解析 str/NaN/±inf/bool/None/list/dict）——power_dbm 同款
    _number_field 口径（bool 是 int 子类但语义是开关，显式排除）。"""
    raw = _legal_scenario("tone")
    raw["tx_gain_db"] = bad
    errors = validate_scenario_schema(raw)
    assert errors and any("tx_gain_db" in e for e in errors)


def test_tx_gain_db_in_known_keys_while_unknown_keys_still_rejected():
    """在册后不再报「未知键: tx_gain_db」；其余未知键（含近形键）仍拒——
    B21 未知键全拒纪律不因白名单扩键而放松。"""
    raw = _legal_scenario("tone")
    raw["tx_gain_db"] = 60.0
    assert validate_scenario_schema(raw) == []
    raw["tx_gains_db"] = 60.0  # 近形未知键仍拒
    errors = validate_scenario_schema(raw)
    assert any("未知键: tx_gains_db" in e for e in errors)


# ---- 执行信封键（B21 高#1）：在册即过形状检查，坏形状逐键指名 ----


def test_envelope_keys_full_legal_set_passes():
    """执行信封键全量合法样例：错误清单为空（场景文件路线不再整条死路）。"""
    raw = _legal_scenario("tone")
    raw.update(
        {
            "scenario_type": "gb42590",
            "judge_min_samples": 2,
            "dwell_s": 0.0,
            "baseline_samples": 10,
            "ledger_entry": "B1",
            "distances": [1.0, 10.0],
            "model_params": {"d0_m": 1.0, "l0_db": 20.0, "n": 2.0},
            "ladder": {"start_db": -6.0, "step_db": 3.0},
            "ladder_params": {"stop_db": 0.0},
            "record": False,
            "sim_events": [{"type": "power_step", "jsr_db": -20.0, "ts": 0.0}],
        }
    )
    assert validate_scenario_schema(raw) == []


def test_envelope_scenario_type_case_insensitive_four_values():
    for ok in ("gb42590", "GB42590", " Distance ", "Custom", "EMC"):
        raw = _legal_scenario("tone")
        raw["scenario_type"] = ok
        assert validate_scenario_schema(raw) == [], ok


@pytest.mark.parametrize(
    "bad",
    ["quantum", "", "gb42590/", 42, None, ["gb42590"]],
)
def test_envelope_scenario_type_bad_values_rejected(bad):
    raw = _legal_scenario("tone")
    raw["scenario_type"] = bad
    errors = validate_scenario_schema(raw)
    assert errors and any("scenario_type" in e for e in errors)


@pytest.mark.parametrize("key", ["judge_min_samples", "baseline_samples"])
@pytest.mark.parametrize("bad", [0, -3, 2.5, True, "abc", None])
def test_envelope_positive_int_keys_reject_bad(key, bad):
    raw = _legal_scenario("tone")
    raw[key] = bad
    errors = validate_scenario_schema(raw)
    assert errors and any(key in e for e in errors)


def test_envelope_positive_int_keys_integer_str_tolerated():
    raw = _legal_scenario("tone")
    raw["judge_min_samples"] = "3"
    raw["baseline_samples"] = "10"
    assert validate_scenario_schema(raw) == []


@pytest.mark.parametrize("bad", [-0.5, "nan", "inf", True, "abc"])
def test_envelope_dwell_s_negative_or_nonfinite_rejected(bad):
    raw = _legal_scenario("tone")
    raw["dwell_s"] = bad
    errors = validate_scenario_schema(raw)
    assert errors and any("dwell_s" in e for e in errors)


def test_envelope_dwell_s_zero_and_positive_pass():
    raw = _legal_scenario("tone")
    raw["dwell_s"] = 0.0
    assert validate_scenario_schema(raw) == []
    raw["dwell_s"] = 1.5
    assert validate_scenario_schema(raw) == []
    raw["dwell_s"] = "0"  # 数字 str 宽容（B17 中#4 同口径）
    assert validate_scenario_schema(raw) == []


@pytest.mark.parametrize("ok", ["B1", "L99", "A0", "  K12  "])
def test_envelope_ledger_entry_shape_passes(ok):
    raw = _legal_scenario("tone")
    raw["ledger_entry"] = ok
    assert validate_scenario_schema(raw) == []


@pytest.mark.parametrize("bad", ["M1", "B123", "b1", "B", 21, None, "B-7"])
def test_envelope_ledger_entry_bad_shape_rejected(bad):
    raw = _legal_scenario("tone")
    raw["ledger_entry"] = bad
    errors = validate_scenario_schema(raw)
    assert errors and any("ledger_entry" in e for e in errors)


@pytest.mark.parametrize(
    "bad",
    [
        "1.0",  # 非 list
        [1.0, "abc"],
        [1.0, 0.0],  # 零距离
        [1.0, -2.0],
        [1.0, True],
        [1.0, "nan"],
    ],
)
def test_envelope_distances_bad_elements_rejected(bad):
    raw = _legal_scenario("tone")
    raw["distances"] = bad
    errors = validate_scenario_schema(raw)
    assert errors and any("distances" in e for e in errors)


def test_envelope_distances_numeric_str_and_empty_list_loose():
    # 数字 str 元素宽容（PyYAML '1e3' 口径）；空 list 不在本层拦（map 归下游）。
    raw = _legal_scenario("tone")
    raw["distances"] = ["1e1", 20]
    assert validate_scenario_schema(raw) == []
    raw["distances"] = []
    assert validate_scenario_schema(raw) == []


@pytest.mark.parametrize("key", ["model_params", "ladder", "ladder_params"])
@pytest.mark.parametrize("bad", ["x", [1], 3, None])
def test_envelope_dict_keys_reject_non_dict(key, bad):
    raw = _legal_scenario("tone")
    raw[key] = bad
    errors = validate_scenario_schema(raw)
    assert errors and any(key in e for e in errors)


@pytest.mark.parametrize("bad", ["true", 1, 0, [True], None])
def test_envelope_record_must_be_bool(bad):
    raw = _legal_scenario("tone")
    raw["record"] = bad
    errors = validate_scenario_schema(raw)
    assert errors and any("record" in e for e in errors)


@pytest.mark.parametrize("bad", ["x", {"type": "power_step"}, 3, None])
def test_envelope_sim_events_must_be_list(bad):
    raw = _legal_scenario("tone")
    raw["sim_events"] = bad
    errors = validate_scenario_schema(raw)
    assert errors and any("sim_events" in e for e in errors)


def test_envelope_keys_survive_normalize_passthrough(tmp_path):
    """normalize 透传（同功能块口径）：执行信封键原样落规范化输出顶层。"""
    from src.load_scenario.normalize_scenario import normalize_scenario

    raw = _legal_scenario("tone")
    raw.update(
        {
            "scenario_type": "distance",
            "judge_min_samples": 2,
            "dwell_s": 0.5,
            "baseline_samples": 10,
            "ledger_entry": "B21",
            "distances": [1.0, 10.0],
            "model_params": {"d0_m": 1.0, "l0_db": 20.0, "n": 2.0},
            "record": True,
            "sim_events": [{"jsr_db": -20.0}],
        }
    )
    out = normalize_scenario(raw)
    assert out["scenario_type"] == "distance"  # 原样透传（归一归消费方）
    assert out["judge_min_samples"] == 2
    assert out["dwell_s"] == 0.5
    assert out["baseline_samples"] == 10
    assert out["ledger_entry"] == "B21"
    assert out["distances"] == [1.0, 10.0]
    assert out["model_params"] == {"d0_m": 1.0, "l0_db": 20.0, "n": 2.0}
    assert out["record"] is True
    assert out["sim_events"] == [{"jsr_db": -20.0}]
    assert out["style"] == "tone" and out["fs"] == 4e6  # 规范字段照常


# ---- raw 非 dict → 单条错误，不抛 ----


@pytest.mark.parametrize("bad_raw", ["not-a-dict", [1, 2], 42])
def test_non_dict_input_returns_single_error(bad_raw):
    errors = validate_scenario_schema(bad_raw)
    assert isinstance(errors, list)
    assert len(errors) == 1
