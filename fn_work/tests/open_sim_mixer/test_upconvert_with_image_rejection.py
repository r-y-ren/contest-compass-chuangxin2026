"""upconvert_with_image_rejection 行为用例：上游 slug=sim_mixer13g（对抗用例，fn-implement 阶段填充）。"""
import pytest

from src.open_sim_mixer.upconvert_with_image_rejection import upconvert_with_image_rejection

_IF_OK = {"if_freq_hz": 100e6, "if_power_dbm": -10.0}
_LO_OK = {"lo_freq_hz": 10e9, "lo_power_dbm": 7.0, "phase_noise_dbc_hz": None}
_OUTPUT_KEYS = {
    "rf_freq_hz",
    "rf_power_dbm",
    "image_freq_hz",
    "image_power_dbm",
    "image_rejection_db",
    "phase_noise_note",
    "spurious",
}


def _ifp(**overrides):
    return {**_IF_OK, **overrides}


def _lop(**overrides):
    return {**_LO_OK, **overrides}


def test_formula2_rf_freq_is_lo_plus_if():
    # 公式(2)：f_RF = f_LO + f_IF（LO 10 GHz + IF 100 MHz → 10.1 GHz）
    result = upconvert_with_image_rejection(_ifp(), _lop())
    assert result["rf_freq_hz"] == pytest.approx(10.1e9)


def test_image_freq_and_residual_power_at_default_rejection():
    result = upconvert_with_image_rejection(_ifp(), _lop())
    assert result["image_freq_hz"] == pytest.approx(10e9 - 100e6)  # f_LO − f_IF = 9.9 GHz
    assert result["image_power_dbm"] == pytest.approx(-10.0 - 40.0)  # IF − 抑制（默认 40）
    assert result["image_rejection_db"] == pytest.approx(40.0)


def test_rejection_60_leaves_minus_60_residual():
    result = upconvert_with_image_rejection(_ifp(if_power_dbm=0.0), _lop(), rejection_db=60.0)
    assert result["image_power_dbm"] == pytest.approx(-60.0)
    assert result["image_rejection_db"] == pytest.approx(60.0)


def test_rf_power_uses_if_plus_3db_simplified_combining():
    # 简化口径：rf 功率 = IF 功率 + 3 dB，与 lo_power_dbm 数值无关
    result = upconvert_with_image_rejection(_ifp(if_power_dbm=-13.5), _lop(lo_power_dbm=13.0))
    assert result["rf_power_dbm"] == pytest.approx(-13.5 + 3.0)


def test_second_lo_spurious_pair_freqs_and_power():
    result = upconvert_with_image_rejection(_ifp(), _lop())
    spurious = result["spurious"]
    assert isinstance(spurious, list)
    assert len(spurious) == 2
    assert set(spurious[0]) == {"freq_hz", "power_dbm"}
    assert set(spurious[1]) == {"freq_hz", "power_dbm"}
    assert spurious[0]["freq_hz"] == pytest.approx(2 * 10e9 - 100e6)  # 2·f_LO − f_IF
    assert spurious[1]["freq_hz"] == pytest.approx(2 * 10e9 + 100e6)  # 2·f_LO + f_IF
    assert spurious[0]["power_dbm"] == pytest.approx(-10.0 - 60.0)
    assert spurious[1]["power_dbm"] == pytest.approx(-10.0 - 60.0)


def test_lo_phase_noise_passthrough():
    result = upconvert_with_image_rejection(_ifp(), _lop(phase_noise_dbc_hz=-95.5))
    assert result["phase_noise_note"] == pytest.approx(-95.5)
    assert isinstance(result["phase_noise_note"], float)


def test_lo_phase_noise_none_marks_ideal_lo():
    result = upconvert_with_image_rejection(_ifp(), _lop(phase_noise_dbc_hz=None))
    assert result["phase_noise_note"] == "ideal_lo"


@pytest.mark.parametrize("drop_key", ["if_freq_hz", "if_power_dbm"])
def test_missing_if_key_rejected_with_key_name(drop_key):
    params = _ifp()
    del params[drop_key]
    with pytest.raises(ValueError) as excinfo:
        upconvert_with_image_rejection(params, _lop())
    assert drop_key in str(excinfo.value)


@pytest.mark.parametrize("drop_key", ["lo_freq_hz", "lo_power_dbm", "phase_noise_dbc_hz"])
def test_missing_lo_key_rejected_with_key_name(drop_key):
    params = _lop()
    del params[drop_key]
    with pytest.raises(ValueError) as excinfo:
        upconvert_with_image_rejection(_ifp(), params)
    assert drop_key in str(excinfo.value)


@pytest.mark.parametrize("bad_freq", [0.0, -100e6, 0, -1, -1e9])
def test_non_positive_frequency_rejected(bad_freq):
    with pytest.raises(ValueError):
        upconvert_with_image_rejection(_ifp(if_freq_hz=bad_freq), _lop())
    with pytest.raises(ValueError):
        upconvert_with_image_rejection(_ifp(), _lop(lo_freq_hz=bad_freq))


@pytest.mark.parametrize(
    "overrides",
    [
        {"if_freq_hz": float("nan")},
        {"if_freq_hz": True},
        {"if_freq_hz": False},
        {"if_freq_hz": "100e6"},
        {"if_freq_hz": None},
        {"if_freq_hz": [100e6]},
        {"if_freq_hz": 10 ** 400},  # int 超出 float 可表示域
        {"if_power_dbm": float("nan")},
        {"if_power_dbm": float("inf")},
        {"if_power_dbm": True},
        {"if_power_dbm": "-10"},
        {"if_power_dbm": None},
    ],
)
def test_if_domain_violations_rejected(overrides):
    with pytest.raises(ValueError):
        upconvert_with_image_rejection(_ifp(**overrides), _lop())


@pytest.mark.parametrize(
    "overrides",
    [
        {"lo_freq_hz": float("nan")},
        {"lo_freq_hz": True},
        {"lo_power_dbm": float("nan")},
        {"lo_power_dbm": False},
        {"lo_power_dbm": float("-inf")},
        {"phase_noise_dbc_hz": float("nan")},
        {"phase_noise_dbc_hz": True},
        {"phase_noise_dbc_hz": "low"},
    ],
)
def test_lo_domain_violations_rejected(overrides):
    with pytest.raises(ValueError):
        upconvert_with_image_rejection(_ifp(), _lop(**overrides))


@pytest.mark.parametrize("bad_rejection", [float("nan"), True, "40", None, float("inf")])
def test_rejection_domain_violations_rejected(bad_rejection):
    with pytest.raises(ValueError):
        upconvert_with_image_rejection(_ifp(), _lop(), bad_rejection)


def test_negative_rejection_rejected():
    with pytest.raises(ValueError) as excinfo:
        upconvert_with_image_rejection(_ifp(), _lop(), -5.0)
    assert "rejection_db" in str(excinfo.value)


def test_zero_rejection_allowed_full_image_residual():
    result = upconvert_with_image_rejection(_ifp(), _lop(), 0.0)
    assert result["image_power_dbm"] == pytest.approx(-10.0)  # 0 抑制 → 镜像全残留
    assert result["image_rejection_db"] == pytest.approx(0.0)


def test_output_key_set_fixed_and_power_scalars():
    result = upconvert_with_image_rejection(_ifp(), _lop(), 40.0)
    assert set(result) == _OUTPUT_KEYS
    for key in (
        "rf_freq_hz",
        "rf_power_dbm",
        "image_freq_hz",
        "image_power_dbm",
        "image_rejection_db",
    ):
        assert isinstance(result[key], float)


@pytest.mark.parametrize("bad_if", [None, [], "if", 42, True])
def test_non_dict_if_params_rejected(bad_if):
    with pytest.raises(ValueError):
        upconvert_with_image_rejection(bad_if, _lop())


@pytest.mark.parametrize("bad_lo", [None, (), "lo", 42.5])
def test_non_dict_lo_params_rejected(bad_lo):
    with pytest.raises(ValueError):
        upconvert_with_image_rejection(_ifp(), bad_lo)


def test_int_inputs_normalized_to_float():
    result = upconvert_with_image_rejection(
        {"if_freq_hz": 100_000_000, "if_power_dbm": -10},
        {"lo_freq_hz": 10_000_000_000, "lo_power_dbm": 7, "phase_noise_dbc_hz": -95},
        40,
    )
    assert result["rf_freq_hz"] == pytest.approx(10.1e9)
    assert result["phase_noise_note"] == pytest.approx(-95.0)
    assert isinstance(result["rf_freq_hz"], float)
    assert isinstance(result["phase_noise_note"], float)


def test_default_rejection_is_40():
    result = upconvert_with_image_rejection(_ifp(), _lop())
    assert result["image_rejection_db"] == pytest.approx(40.0)


def test_image_freq_literal_formula_when_if_exceeds_lo():
    # 字面公式 f_LO − f_IF（不折叠/不取绝对值）：f_IF > f_LO 时为负
    result = upconvert_with_image_rejection(_ifp(if_freq_hz=2e9), _lop(lo_freq_hz=1e9))
    assert result["image_freq_hz"] == pytest.approx(1e9 - 2e9)
    assert result["rf_freq_hz"] == pytest.approx(3e9)


def test_extra_input_keys_ignored_not_leaking_into_output():
    result = upconvert_with_image_rejection(_ifp(extra="ignored"), _lop(mode="high_side"))
    assert set(result) == _OUTPUT_KEYS


def test_pure_deterministic_and_inputs_untouched():
    if_params, lo_params = _ifp(), _lop(phase_noise_dbc_hz=-90.0)
    snapshot = (dict(if_params), dict(lo_params))
    first = upconvert_with_image_rejection(if_params, lo_params, 40.0)
    second = upconvert_with_image_rejection(if_params, lo_params, 40.0)
    assert first == second
    assert (if_params, lo_params) == snapshot
