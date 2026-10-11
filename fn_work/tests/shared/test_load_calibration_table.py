"""load_calibration_table 对抗测试：三类表往返、NaN/inf/bool/结构/重复键损坏、缺表占位与缺目录。"""
from __future__ import annotations

import json
import sys

import pytest

from src.shared.load_calibration_table import CalibrationError, load_calibration_table


def _cfg_with_dir(tmp_path):
    """建立临时标定目录，返回 (config, dir)。"""
    cal = tmp_path / "calibrations"
    cal.mkdir()
    return {"calibration_dir": str(cal)}, cal


def _write_table(cal_dir, name, payload):
    (cal_dir / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_gain_table_round_trip(tmp_path):
    """① gain 表正常往返：档位→power_dbm，视图字段齐全。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "gain", {"low": {"power_dbm": -12.5}, "mid": {"power_dbm": 0.0}, "high": {"power_dbm": 3.0}})
    view = load_calibration_table("gain", cfg)
    assert view["name"] == "gain"
    assert view["placeholder"] is False
    assert view["source"].endswith("gain.json")
    assert view["entries"] == {"low": {"power_dbm": -12.5}, "mid": {"power_dbm": 0.0}, "high": {"power_dbm": 3.0}}
    assert view["meta"]["entry_count"] == 3


def test_link_loss_table_round_trip(tmp_path):
    """② link_loss 表正常往返：频点字符串键规范化为 float MHz。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "link_loss", {"2400": 1.5, "5800": 2})
    view = load_calibration_table("link_loss", cfg)
    assert view["placeholder"] is False
    assert view["entries"] == {2400.0: 1.5, 5800.0: 2}
    assert view["name"] == "link_loss"


def test_antenna_table_round_trip(tmp_path):
    """③ antenna 表正常往返：频点 MHz→dB。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "antenna", {"2400.5": 7.2, "5799.5": 9.8})
    view = load_calibration_table("antenna", cfg)
    assert view["placeholder"] is False
    assert view["entries"] == {2400.5: 7.2, 5799.5: 9.8}


def test_nan_value_rejected(tmp_path):
    """④ NaN 值（JSON NaN 字面量）→ CalibrationError。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "link_loss", {"2400": float("nan")})
    with pytest.raises(CalibrationError, match="NaN"):
        load_calibration_table("link_loss", cfg)


def test_inf_value_rejected(tmp_path):
    """⑤ inf 值（JSON Infinity 字面量）→ CalibrationError。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "antenna", {"2400": float("inf")})
    with pytest.raises(CalibrationError, match="Infinity"):
        load_calibration_table("antenna", cfg)


def test_bool_value_rejected(tmp_path):
    """⑥ bool 值（gain.power_dbm=true 与 link_loss dB=true）→ CalibrationError。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "gain", {"low": {"power_dbm": True}})
    with pytest.raises(CalibrationError, match="bool"):
        load_calibration_table("gain", cfg)
    _write_table(cal, "link_loss", {"2400": True})
    with pytest.raises(CalibrationError, match="bool"):
        load_calibration_table("link_loss", cfg)


def test_structure_mismatch_rejected(tmp_path):
    """⑦ JSON 合法但结构不符（gain 值非对象/频点键非数值/顶层非对象）→ CalibrationError。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "gain", {"low": -10.0})
    with pytest.raises(CalibrationError, match="power_dbm"):
        load_calibration_table("gain", cfg)
    _write_table(cal, "antenna", {"not-a-number": 1.0})
    with pytest.raises(CalibrationError, match="频点"):
        load_calibration_table("antenna", cfg)
    (cal / "link_loss.json").write_text("[2400, 1.5]", encoding="utf-8")
    with pytest.raises(CalibrationError, match="顶层"):
        load_calibration_table("link_loss", cfg)


def test_invalid_json_rejected(tmp_path):
    """⑧ 非法 JSON（截断文件）→ CalibrationError。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    (cal / "gain.json").write_text('{"low": ', encoding="utf-8")
    with pytest.raises(CalibrationError, match="非法 JSON"):
        load_calibration_table("gain", cfg)


def test_duplicate_json_keys_rejected(tmp_path):
    """⑨ JSON 原始重复键（"2400" 出现两次）→ CalibrationError。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    (cal / "link_loss.json").write_text('{"2400": 1.5, "2400": 2.0}', encoding="utf-8")
    with pytest.raises(CalibrationError, match="重复键"):
        load_calibration_table("link_loss", cfg)


def test_duplicate_freq_after_normalization_rejected(tmp_path):
    """⑩ 键规范化后频点重复（"2400" 与 "2400.0"）→ CalibrationError。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    (cal / "antenna.json").write_text('{"2400": 1.5, "2400.0": 2.0}', encoding="utf-8")
    with pytest.raises(CalibrationError, match="重复"):
        load_calibration_table("antenna", cfg)


def test_missing_table_placeholder_true_returns_placeholder_view(tmp_path):
    """⑪ 缺表 + placeholder=True →【待实测】占位视图：placeholder=True、entries 为空、无预写数字。"""
    cfg, _ = _cfg_with_dir(tmp_path)
    view = load_calibration_table("gain", cfg, placeholder=True)
    assert view["placeholder"] is True
    assert dict(view["entries"]) == {}
    assert view["name"] == "gain"
    assert view["source"] is None
    assert "【待实测】" in view["meta"]["note"]
    assert view["meta"]["entry_count"] == 0


def test_missing_table_placeholder_false_raises(tmp_path):
    """⑫ 缺表 + placeholder=False（默认）→ CalibrationError。"""
    cfg, _ = _cfg_with_dir(tmp_path)
    with pytest.raises(CalibrationError, match="缺失"):
        load_calibration_table("link_loss", cfg)


def test_nonexistent_calibration_dir_raises(tmp_path):
    """⑬ 标定目录不存在 → CalibrationError（即使 placeholder=True 也不占位）。"""
    cfg = {"calibration_dir": str(tmp_path / "nope")}
    with pytest.raises(CalibrationError, match="标定目录不存在"):
        load_calibration_table("gain", cfg)
    with pytest.raises(CalibrationError, match="标定目录不存在"):
        load_calibration_table("gain", cfg, placeholder=True)


def test_unknown_table_name_rejected(tmp_path):
    """⑭ 未知表名 → CalibrationError。"""
    cfg, _ = _cfg_with_dir(tmp_path)
    with pytest.raises(CalibrationError, match="未知标定表名"):
        load_calibration_table("noise_figure", cfg)


def test_default_calibration_dir_when_config_omits_key(tmp_path, monkeypatch):
    """⑮ config 缺 calibration_dir 键 → 回退默认 'fn_work/calibrations'（相对当前目录）。"""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CalibrationError, match=r"fn_work[/\\]calibrations"):
        load_calibration_table("gain", {})


def test_entries_read_only(tmp_path):
    """⑯ entries 只读：改写条目或嵌套 power_dbm 均抛 TypeError。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "gain", {"low": {"power_dbm": -5.0}})
    view = load_calibration_table("gain", cfg)
    with pytest.raises(TypeError):
        view["entries"]["low"] = {"power_dbm": 1.0}
    with pytest.raises(TypeError):
        view["entries"]["low"]["power_dbm"] = 99.0
    assert view["entries"]["low"]["power_dbm"] == -5.0


# ---------------------------------------------------------------------------
# B2 对抗审查缺陷回归（高#5/中#8 + 超大表值）
# ---------------------------------------------------------------------------

def _deep_json_text(layers: int = 50000) -> str:
    """构造 layers 层深嵌套 JSON 数组文本（'[[[…]]]'）。"""
    return "[" * layers + "]" * layers


def test_defect_b2_deeply_nested_json_rejected(tmp_path):
    """高#5：50000 层深嵌套 JSON → CalibrationError（RecursionError 捕获或结构不符兜底），不裸抛。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    (cal / "link_loss.json").write_text(_deep_json_text(), encoding="utf-8")
    with pytest.raises(CalibrationError):
        load_calibration_table("link_loss", cfg)


def test_defect_b2_recursion_depth_json_rejected(tmp_path):
    """高#5 主路径：超过解析递归上限的深嵌套 JSON → RecursionError 被捕获转 CalibrationError。

    深度取递归上限的 150 倍以保证触发 RecursionError；若环境解析器不递归
    （完全迭代解析），则由「顶层应为 JSON 对象」兜底拒绝——两条路径均为 CalibrationError。
    """
    cfg, cal = _cfg_with_dir(tmp_path)
    (cal / "gain.json").write_text(_deep_json_text(sys.getrecursionlimit() * 150), encoding="utf-8")
    with pytest.raises(CalibrationError):
        load_calibration_table("gain", cfg)


def test_defect_b2_gain_numeric_equivalent_keys_rejected(tmp_path):
    """中#8：gain 表 '20' 与 '20.0' 同表（数值等价重复）→ CalibrationError（与频点侧归一检测一致）。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    (cal / "gain.json").write_text(
        '{"20": {"power_dbm": 0.0}, "20.0": {"power_dbm": 5.0}}', encoding="utf-8"
    )
    with pytest.raises(CalibrationError, match="数值等价"):
        load_calibration_table("gain", cfg)


def test_defect_b2_huge_int_table_value_rejected(tmp_path):
    """同族加固：JSON 内 400 位超大整数值 → CalibrationError（视为损坏），不抛 OverflowError。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    (cal / "link_loss.json").write_text('{"2400": 1' + "0" * 400 + "}", encoding="utf-8")
    with pytest.raises(CalibrationError, match="超大"):
        load_calibration_table("link_loss", cfg)
