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


# ---- raw 非 dict → 单条错误，不抛 ----


@pytest.mark.parametrize("bad_raw", ["not-a-dict", [1, 2], 42])
def test_non_dict_input_returns_single_error(bad_raw):
    errors = validate_scenario_schema(bad_raw)
    assert isinstance(errors, list)
    assert len(errors) == 1
