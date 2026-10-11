"""build_gain_calibration 对抗测试：单调建表/幂等重建、非单调与非法值拒用、【待实测】占位、loader 集成往返。"""
from __future__ import annotations

import json
import os

import pytest

from src.build_gain_calibration.build_gain_calibration import (
    CalibrationError,
    build_gain_calibration,
)
from src.shared.load_calibration_table import load_calibration_table

_MONOTONE_FIVE = [
    {"gain_step": 0, "power_dbm": -20.0},
    {"gain_step": 1, "power_dbm": -12.5},
    {"gain_step": 2, "power_dbm": -6.0},
    {"gain_step": 3, "power_dbm": 0.5},
    {"gain_step": 4, "power_dbm": 3.0},
]
_MONOTONE_FIVE_ENTRIES = {
    "0": {"power_dbm": -20.0},
    "1": {"power_dbm": -12.5},
    "2": {"power_dbm": -6.0},
    "3": {"power_dbm": 0.5},
    "4": {"power_dbm": 3.0},
}


def _with_out_path(measurements: list, out_path) -> list:
    """返回首测点携带 out_path 的测量副本（非 dict 元素原样透传）。"""
    copied = [dict(point) if isinstance(point, dict) else point for point in measurements]
    copied[0]["out_path"] = str(out_path)
    return copied


def test_gain_calibration_monotone_five_points_builds_table_with_expected_content(tmp_path):
    """① 5 点单调→建表：返回字段齐全、文件内容恰为档位→power_dbm 映射。"""
    out = tmp_path / "gain.json"
    result = build_gain_calibration(_with_out_path(_MONOTONE_FIVE, out))
    assert result == {
        "table_path": str(out),
        "points": 5,
        "placeholder": False,
        "monotonic": True,
    }
    assert json.loads(out.read_text(encoding="utf-8")) == _MONOTONE_FIVE_ENTRIES


def test_gain_calibration_rebuild_is_byte_identical(tmp_path):
    """①b 幂等重建：同输入两次调用，表文件字节一致、返回一致。"""
    out = tmp_path / "gain.json"
    measurements = _with_out_path(_MONOTONE_FIVE, out)
    first = build_gain_calibration(measurements)
    first_text = out.read_text(encoding="utf-8")
    second = build_gain_calibration(measurements)
    assert second == first
    assert out.read_text(encoding="utf-8") == first_text


def test_gain_calibration_midpoint_drop_rejected_with_summary(tmp_path):
    """② 中点下降→CalibrationError 拒用，文案含违例摘要（档位/降幅），且不落表。"""
    out = tmp_path / "gain.json"
    dropping = [
        {"gain_step": "L1", "power_dbm": 0.0},
        {"gain_step": "L2", "power_dbm": 10.0},
        {"gain_step": "L3", "power_dbm": 7.0},
        {"gain_step": "L4", "power_dbm": 12.0},
    ]
    with pytest.raises(CalibrationError, match="非单调") as excinfo:
        build_gain_calibration(_with_out_path(dropping, out))
    message = str(excinfo.value)
    assert "L3" in message and "7" in message and "10" in message
    assert not out.exists()


def test_gain_calibration_nan_power_rejected(tmp_path):
    """③ NaN 功率→CalibrationError（形状错单独文案），不落表。"""
    out = tmp_path / "gain.json"
    poisoned = [
        {"gain_step": "L1", "power_dbm": 0.0},
        {"gain_step": "L2", "power_dbm": float("nan")},
    ]
    with pytest.raises(CalibrationError, match="形状非法"):
        build_gain_calibration(_with_out_path(poisoned, out))
    assert not out.exists()


def test_gain_calibration_inf_power_rejected(tmp_path):
    """③b inf 功率→CalibrationError（非有限实数按形状错拒用）。"""
    out = tmp_path / "gain.json"
    poisoned = [
        {"gain_step": "L1", "power_dbm": float("-inf")},
        {"gain_step": "L2", "power_dbm": 1.0},
    ]
    with pytest.raises(CalibrationError, match="形状非法"):
        build_gain_calibration(_with_out_path(poisoned, out))


def test_gain_calibration_bool_power_rejected(tmp_path):
    """③c True 功率（bool 不作量值）→CalibrationError。"""
    out = tmp_path / "gain.json"
    poisoned = [
        {"gain_step": "L1", "power_dbm": True},
        {"gain_step": "L2", "power_dbm": 2.0},
    ]
    with pytest.raises(CalibrationError, match="形状非法"):
        build_gain_calibration(_with_out_path(poisoned, out))


def test_gain_calibration_empty_sequence_rejected(tmp_path):
    """④ 空序列→CalibrationError（样本不足）。"""
    with pytest.raises(CalibrationError, match="样本不足"):
        build_gain_calibration([])


def test_gain_calibration_none_writes_placeholder_table(tmp_path, monkeypatch):
    """⑤ None→【待实测】占位表：entries 空且 placeholder=True，无任何预写数字。"""
    monkeypatch.chdir(tmp_path)
    result = build_gain_calibration(None)
    assert result["placeholder"] is True
    assert result["points"] == 0
    assert result["table_path"] == os.path.join("fn_work", "calibrations", "gain.json")
    placeholder_file = tmp_path / "fn_work" / "calibrations" / "gain.json"
    text = placeholder_file.read_text(encoding="utf-8")
    assert json.loads(text) == {}
    assert not any(ch.isdigit() for ch in text), "占位表禁止预写任何数字"


def test_gain_calibration_single_point_rejected(tmp_path):
    """⑥ 单点→CalibrationError（样本不足，<2 点）。"""
    out = tmp_path / "gain.json"
    with pytest.raises(CalibrationError, match="样本不足"):
        build_gain_calibration(_with_out_path([{"gain_step": "L1", "power_dbm": 1.0}], out))
    assert not out.exists()


def test_gain_calibration_custom_out_path_with_directory_autocreate(tmp_path):
    """⑦ measurements 携带 out_path 自定义到 tmp_path 深层不存在的目录→自动建目录落表。"""
    out = tmp_path / "nested" / "deep" / "gain.json"
    result = build_gain_calibration(_with_out_path(_MONOTONE_FIVE, out))
    assert result["table_path"] == str(out)
    assert out.is_file()
    assert json.loads(out.read_text(encoding="utf-8")) == _MONOTONE_FIVE_ENTRIES


def test_gain_calibration_placeholder_flag_matches_file_content(tmp_path, monkeypatch):
    """⑧ 占位标志与文件内容一致：placeholder=False 文件恰含实测条目；True 文件为空表。"""
    measured_out = tmp_path / "measured" / "gain.json"
    measured = build_gain_calibration(_with_out_path(_MONOTONE_FIVE, measured_out))
    assert measured["placeholder"] is False
    assert json.loads(measured_out.read_text(encoding="utf-8")) == _MONOTONE_FIVE_ENTRIES

    placeholder_cwd = tmp_path / "placeholder_cwd"
    placeholder_cwd.mkdir()
    monkeypatch.chdir(placeholder_cwd)
    placeholder = build_gain_calibration(None)
    assert placeholder["placeholder"] is True
    placeholder_file = tmp_path / "placeholder_cwd" / "fn_work" / "calibrations" / "gain.json"
    assert json.loads(placeholder_file.read_text(encoding="utf-8")) == {}


def test_gain_calibration_load_calibration_table_round_trip(tmp_path):
    """⑨ 集成：建表后 load_calibration_table 能读回且 entries 相等。"""
    cal_dir = tmp_path / "calibrations"
    build_gain_calibration(_with_out_path(_MONOTONE_FIVE, cal_dir / "gain.json"))
    view = load_calibration_table("gain", {"calibration_dir": str(cal_dir)})
    assert view["placeholder"] is False
    assert view["name"] == "gain"
    assert view["source"] == str(cal_dir / "gain.json")
    assert dict(view["entries"]) == _MONOTONE_FIVE_ENTRIES


def test_gain_calibration_duplicate_step_labels_rejected(tmp_path):
    """⑩ str(gain_step) 序列化后档位重复（'1' 与 1）→CalibrationError，防 JSON 键静默塌缩。"""
    out = tmp_path / "gain.json"
    duplicated = [
        {"gain_step": "1", "power_dbm": 0.0},
        {"gain_step": 1, "power_dbm": 5.0},
    ]
    with pytest.raises(CalibrationError, match="重复"):
        build_gain_calibration(_with_out_path(duplicated, out))
    assert not out.exists()


def test_gain_calibration_malformed_point_shape_rejected(tmp_path):
    """⑪ 测点结构非法（缺字段/非 dict）→CalibrationError 形状文案。"""
    out = tmp_path / "gain.json"
    missing_key = [
        {"gain_step": "L1", "power_dbm": 0.0},
        {"power_dbm": 5.0},
    ]
    with pytest.raises(CalibrationError, match="形状非法"):
        build_gain_calibration(_with_out_path(missing_key, out))
    non_dict = [
        {"gain_step": "L1", "power_dbm": 0.0},
        "L2",
    ]
    with pytest.raises(CalibrationError, match="形状非法"):
        build_gain_calibration(_with_out_path(non_dict, out))
    assert not out.exists()


def test_gain_calibration_non_list_measurements_rejected(tmp_path):
    """⑫ measurements 非 list/None（str/dict/int）→CalibrationError。"""
    for bad in ("L1", {"gain_step": "L1", "power_dbm": 1.0}, 42):
        with pytest.raises(CalibrationError, match="形状非法"):
            build_gain_calibration(bad)


def test_gain_calibration_default_out_path_under_cwd(tmp_path, monkeypatch):
    """⑬ 缺省输出路径 'fn_work/calibrations/gain.json'（相对当前目录）且目录自动创建。"""
    monkeypatch.chdir(tmp_path)
    result = build_gain_calibration(_MONOTONE_FIVE)
    expected = tmp_path / "fn_work" / "calibrations" / "gain.json"
    assert result["table_path"] == os.path.join("fn_work", "calibrations", "gain.json")
    assert json.loads(expected.read_text(encoding="utf-8")) == _MONOTONE_FIVE_ENTRIES
