"""check_style_params 对抗测试：只判域不合成，errors 非空=整体拒，永不抛出。"""
from __future__ import annotations

import pytest

from src.synthesize_style.check_style_params import check_style_params

FS = 1e6


def _legal_params(style: str) -> dict:
    """每个样式的合法满参数样例（errors/warnings 必须全零）。"""
    params = {
        "style": style,
        "freq_hz": 100e3,
        "power_dbm": -10.0,
        "duration_s": 0.01,
        "sample_rate_hz": FS,
    }
    if style in ("bandlimited_noise", "partial_band", "pulse"):
        params["bandwidth_hz"] = 1e6
    if style == "pulse":
        params["duty_cycle"] = 0.5
        params["repeats"] = 3
    return params


# ---- 六类样式合法样例：全零 errors（且无 warning） ----


@pytest.mark.parametrize(
    "style",
    ["tone", "sweep", "chirp", "bandlimited_noise", "partial_band", "pulse"],
)
def test_six_styles_legal_samples_pass(style):
    assert check_style_params(_legal_params(style)) == {"errors": [], "warnings": []}


# ---- 带限类 bandwidth_hz 必填 ----


@pytest.mark.parametrize("style", ["bandlimited_noise", "partial_band", "pulse"])
def test_bandlimited_styles_missing_bandwidth_rejected(style):
    params = _legal_params(style)
    del params["bandwidth_hz"]
    result = check_style_params(params)
    assert len(result["errors"]) == 1
    assert "bandwidth_hz" in result["errors"][0]


@pytest.mark.parametrize("style", ["tone", "sweep", "chirp"])
def test_non_bandlimited_styles_bandwidth_optional(style):
    assert check_style_params(_legal_params(style))["errors"] == []


# ---- bandwidth_hz 域：56e6 恰过 / 56.1e6 拒 / 非正拒 ----


def test_bandwidth_56mhz_boundary_passes_and_above_rejected():
    ok = check_style_params({**_legal_params("bandlimited_noise"), "bandwidth_hz": 56e6})
    assert ok["errors"] == []
    bad = check_style_params(
        {**_legal_params("bandlimited_noise"), "bandwidth_hz": 56.1e6}
    )
    assert len(bad["errors"]) == 1
    assert "bandwidth_hz" in bad["errors"][0]
    assert "56100000" in bad["errors"][0]


@pytest.mark.parametrize("bandwidth_hz", [0.0, -5e6])
def test_bandwidth_non_positive_rejected(bandwidth_hz):
    result = check_style_params({**_legal_params("tone"), "bandwidth_hz": bandwidth_hz})
    assert any(
        "bandwidth_hz" in e and repr(float(bandwidth_hz)) in e for e in result["errors"]
    )


# ---- power_dbm 红线域：+0.5 拒 / 0.0 过 / -100 过 / -100.1 拒 ----


@pytest.mark.parametrize(
    "power_dbm, rejected",
    [(0.5, True), (0.0, False), (-100.0, False), (-100.1, True)],
)
def test_power_redline_domain(power_dbm, rejected):
    result = check_style_params({**_legal_params("tone"), "power_dbm": power_dbm})
    if rejected:
        assert any(
            "power_dbm" in e and repr(power_dbm) in e for e in result["errors"]
        )
    else:
        assert result["errors"] == []


# ---- duty_cycle 严格开区间：0/1 边界拒，0.5 过 ----


@pytest.mark.parametrize("duty_cycle, rejected", [(0.0, True), (1.0, True), (0.5, False)])
def test_duty_cycle_open_interval(duty_cycle, rejected):
    result = check_style_params({**_legal_params("pulse"), "duty_cycle": duty_cycle})
    if rejected:
        assert len(result["errors"]) == 1
        assert "duty_cycle" in result["errors"][0]
        assert repr(duty_cycle) in result["errors"][0]
    else:
        assert result["errors"] == []


# ---- freq_hz：超 fs/2 是 warning 非 error；负偏移域内干净 ----


def test_freq_beyond_half_sample_rate_is_warning_not_error():
    result = check_style_params({**_legal_params("tone"), "freq_hz": 0.75 * FS})
    assert result["errors"] == []
    assert len(result["warnings"]) == 1
    assert "freq_hz" in result["warnings"][0]


def test_negative_freq_within_half_sample_rate_clean():
    result = check_style_params({**_legal_params("tone"), "freq_hz": -0.4 * FS})
    assert result == {"errors": [], "warnings": []}


# ---- NaN/inf/bool 值逐键参数化拒（文案含键名与值） ----


@pytest.mark.parametrize(
    "key",
    [
        "freq_hz",
        "bandwidth_hz",
        "power_dbm",
        "duration_s",
        "duty_cycle",
        "repeats",
        "sample_rate_hz",
    ],
)
@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), True])
def test_nan_inf_bool_values_rejected_per_key(key, bad_value):
    params = {**_legal_params("pulse"), key: bad_value}
    result = check_style_params(params)
    hits = [e for e in result["errors"] if key in e and repr(bad_value) in e]
    assert len(hits) == 1


# ---- 未知键 → warning 不拒 ----


def test_unknown_key_warns_not_rejects():
    result = check_style_params({**_legal_params("tone"), "foo": 123})
    assert result["errors"] == []
    assert len(result["warnings"]) == 1
    assert "foo" in result["warnings"][0]


# ---- repeats：正 int；2.0/True/0/负数拒，3 过 ----


@pytest.mark.parametrize(
    "repeats, rejected", [(2.0, True), (True, True), (0, True), (-3, True), (3, False)]
)
def test_repeats_positive_int_only(repeats, rejected):
    result = check_style_params({**_legal_params("pulse"), "repeats": repeats})
    if rejected:
        assert len([e for e in result["errors"] if "repeats" in e and repr(repeats) in e]) == 1
    else:
        assert result["errors"] == []


# ---- params 非 dict → 单条 errors，不抛 ----


@pytest.mark.parametrize("params", [None, [1, 2], "tone", 7])
def test_non_dict_params_single_error_no_raise(params):
    result = check_style_params(params)
    assert set(result) == {"errors", "warnings"}
    assert len(result["errors"]) == 1
    assert result["warnings"] == []
    assert "dict" in result["errors"][0]


# ---- style：缺失/非 str/白名单外（含大写）拒 ----


@pytest.mark.parametrize("style", [None, 7, "nope", "TONE"])
def test_bad_style_rejected_with_style_name_in_message(style):
    result = check_style_params({**_legal_params("tone"), "style": style})
    assert len(result["errors"]) == 1
    assert "style" in result["errors"][0]


def test_missing_style_rejected():
    params = _legal_params("tone")
    del params["style"]
    result = check_style_params(params)
    assert len(result["errors"]) == 1
    assert "style" in result["errors"][0]


# ---- duration_s / sample_rate_hz 非正拒 ----


@pytest.mark.parametrize(
    "key, value",
    [("duration_s", 0.0), ("duration_s", -1.0), ("sample_rate_hz", 0.0)],
)
def test_non_positive_domains_rejected(key, value):
    result = check_style_params({**_legal_params("tone"), key: value})
    assert any(key in e and repr(float(value)) in e for e in result["errors"])


# ---- errors 文案必须含键名与值；垃圾值不抛 ----


def test_error_messages_carry_key_and_value():
    result = check_style_params(
        {**_legal_params("tone"), "power_dbm": 0.5, "duration_s": -2.0}
    )
    assert len(result["errors"]) == 2
    joined = "\n".join(result["errors"])
    assert "power_dbm" in joined and "0.5" in joined
    assert "duration_s" in joined and "-2.0" in joined


def test_never_raises_on_garbage_values():
    result = check_style_params({"style": "tone", "freq_hz": object(), "power_dbm": "high"})
    assert len(result["errors"]) == 2
    assert result["errors"]  # 非数值/垃圾值一律记错，不抛
