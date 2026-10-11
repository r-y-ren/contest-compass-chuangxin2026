"""lookup_jsr 行为用例：验收 slug=jsr_calibration（对抗用例，fn-implement 阶段填充）。"""
import json
import math

from src.lookup_jsr.lookup_jsr import lookup_jsr

_FREQ_HZ = 2.45e9


def _make_config(tmp_path):
    cal_dir = tmp_path / "calibrations"
    cal_dir.mkdir()
    return {"calibration_dir": str(cal_dir)}, cal_dir


def _write_gain(cal_dir, entries):
    cal_dir.joinpath("gain.json").write_text(json.dumps(entries), encoding="utf-8")


def test_jsr_calibration_exact_step_jsr_subtraction(tmp_path):
    config, cal_dir = _make_config(tmp_path)
    _write_gain(cal_dir, {"10": {"power_dbm": -10.0}, "20": {"power_dbm": -5.0}})
    result = lookup_jsr("10", _FREQ_HZ, -30.0, config)
    assert result["status"] == "ok"
    assert result["nearest"] is False
    assert result["matched_gain_step"] == "10"
    assert result["injected_power_dbm"] == -10.0
    assert result["jsr_db"] == -10.0 - (-30.0)
    assert result["jsr_db"] == 20.0
    assert result["signal_power_dbm"] == -30.0
    assert result["freq_mhz"] == 2450.0
    assert "extrapolated_note" not in result


def test_jsr_calibration_numeric_step_exact_match_not_nearest(tmp_path):
    config, cal_dir = _make_config(tmp_path)
    _write_gain(cal_dir, {"10": {"power_dbm": -10.0}, "20": {"power_dbm": -5.0}})
    result = lookup_jsr(20, _FREQ_HZ, -30.0, config)
    assert result["status"] == "ok"
    assert result["nearest"] is False
    assert result["matched_gain_step"] == "20"
    assert result["injected_power_dbm"] == -5.0
    assert "extrapolated_note" not in result


def test_jsr_calibration_nearest_step_flagged_extrapolated(tmp_path):
    config, cal_dir = _make_config(tmp_path)
    _write_gain(cal_dir, {"10": {"power_dbm": -10.0}, "20": {"power_dbm": -5.0}})
    # 14 距 10 差 4、距 20 差 6 → 最近邻档 "10"
    result = lookup_jsr("14", _FREQ_HZ, -25.0, config)
    assert result["status"] == "ok"
    assert result["nearest"] is True
    assert result["matched_gain_step"] == "10"
    assert result["injected_power_dbm"] == -10.0
    assert result["jsr_db"] == -10.0 - (-25.0)
    assert result["jsr_db"] == 15.0
    assert isinstance(result["extrapolated_note"], str) and "10" in result["extrapolated_note"]


def test_jsr_calibration_placeholder_table_unavailable(tmp_path):
    config, _cal_dir = _make_config(tmp_path)  # 目录存在但无 gain.json → 占位视图
    result = lookup_jsr("10", _FREQ_HZ, -30.0, config)
    assert result["status"] == "unavailable"
    assert "待实测" in result["note"]
    assert result["status"] != "ok"


def test_jsr_calibration_missing_calibration_dir_missing_table(tmp_path):
    config = {"calibration_dir": str(tmp_path / "no_such_dir")}
    result = lookup_jsr("10", _FREQ_HZ, -30.0, config)
    assert result["status"] == "missing_table"
    assert "build_gain_calibration" in result["note"]


def test_jsr_calibration_corrupt_table_missing_table(tmp_path):
    config, cal_dir = _make_config(tmp_path)
    cal_dir.joinpath("gain.json").write_text("{oops", encoding="utf-8")
    result = lookup_jsr("10", _FREQ_HZ, -30.0, config)
    assert result["status"] == "missing_table"
    assert "build_gain_calibration" in result["note"]


def test_jsr_calibration_nan_signal_invalid(tmp_path):
    config, cal_dir = _make_config(tmp_path)
    _write_gain(cal_dir, {"10": {"power_dbm": -10.0}})
    result = lookup_jsr("10", _FREQ_HZ, float("nan"), config)
    assert result["status"] == "invalid_signal"
    assert math.isnan(result["signal_power_dbm"])


def test_jsr_calibration_bool_signal_invalid(tmp_path):
    config, cal_dir = _make_config(tmp_path)
    _write_gain(cal_dir, {"10": {"power_dbm": -10.0}})
    result = lookup_jsr("10", _FREQ_HZ, True, config)
    assert result["status"] == "invalid_signal"


def test_jsr_calibration_unknown_gain_step_type_flagged(tmp_path):
    config, cal_dir = _make_config(tmp_path)
    _write_gain(cal_dir, {"10": {"power_dbm": -10.0}, "20": {"power_dbm": -5.0}})
    for bad_step in (None, [1], True, "boost"):
        result = lookup_jsr(bad_step, _FREQ_HZ, -30.0, config)
        assert result["status"] == "invalid_gain_step", bad_step
        assert result["status"] != "ok"


def test_jsr_calibration_negative_jsr_when_signal_stronger(tmp_path):
    config, cal_dir = _make_config(tmp_path)
    _write_gain(cal_dir, {"10": {"power_dbm": -10.0}})
    result = lookup_jsr("10", _FREQ_HZ, -3.5, config)
    assert result["status"] == "ok"
    assert result["jsr_db"] == -10.0 - (-3.5)
    assert result["jsr_db"] == -6.5
    assert result["jsr_db"] < 0


def test_jsr_calibration_empty_entries_unavailable(tmp_path):
    config, cal_dir = _make_config(tmp_path)
    _write_gain(cal_dir, {})
    result = lookup_jsr("10", _FREQ_HZ, -30.0, config)
    assert result["status"] == "unavailable"
