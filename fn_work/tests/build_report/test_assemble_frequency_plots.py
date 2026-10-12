"""assemble_frequency_plots 对抗测试：5 图满足、缺额注记如实列缺、空/全缺、bool
False 排除、路径表项落盘实测、未登记键计缺、登记数不足口径、超 5 满足、
非 dict/键类型错/表项异类拒绝、输出键集合恰为五键。"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.build_report.assemble_frequency_plots import assemble_frequency_plots


def _five_keys() -> list[str]:
    return ["ch2412", "ch2437", "ch2462", "ch2484", "band58_monitor"]


def test_five_available_satisfied():
    """① 5 图全在：slots=5/satisfied=True/note 空串/images 依 freq_mhz 顺序。"""
    keys = _five_keys()
    plots = {"freq_mhz": keys, "images": {k: True for k in keys}}
    result = assemble_frequency_plots(plots)
    assert result["slots"] == 5
    assert result["required"] == 5
    assert result["satisfied"] is True
    assert result["deficit_note"] == ""
    assert result["images"] == keys


def test_three_available_two_deficit_lists_missing():
    """② 3 在 2 缺：note 含 '缺 2 个频点图' 且如实列出缺失键；images 只含可用 3 键。"""
    keys = _five_keys()
    images = {k: True for k in keys}
    images["ch2462"] = False
    images["band58_monitor"] = False
    result = assemble_frequency_plots({"freq_mhz": keys, "images": images})
    assert result["slots"] == 3
    assert result["satisfied"] is False
    assert "缺 2 个频点图" in result["deficit_note"]
    assert "ch2462" in result["deficit_note"]
    assert "band58_monitor" in result["deficit_note"]
    assert result["images"] == ["ch2412", "ch2437", "ch2484"]


def test_empty_plots_zero_slots_with_note():
    """③ 空 plots：slots=0+注记（含 '缺 5 个频点图'），不满足。"""
    result = assemble_frequency_plots({})
    assert result["slots"] == 0
    assert result["required"] == 5
    assert result["satisfied"] is False
    assert "缺 5 个频点图" in result["deficit_note"]
    assert result["images"] == []


def test_all_missing_zero_slots_lists_every_key():
    """④ 全缺（全部 False）：slots=0，note 列出全部五个键。"""
    keys = _five_keys()
    result = assemble_frequency_plots({"freq_mhz": keys, "images": {k: False for k in keys}})
    assert result["slots"] == 0
    assert result["satisfied"] is False
    for key in keys:
        assert key in result["deficit_note"]


def test_false_entries_excluded_true_kept():
    """⑤ images 值 False 排除、True 采信（混合登记，可用键不含 False 键）。"""
    result = assemble_frequency_plots(
        {"freq_mhz": ["a", "b"], "images": {"a": True, "b": False}}
    )
    assert result["images"] == ["a"]
    assert result["slots"] == 1


def test_path_entries_measured_on_disk(tmp_path: Path):
    """⑥ 路径表项落盘实测：存在的 str/Path 路径采信，不存在的计缺。"""
    real = tmp_path / "ch2412.png"
    real.write_text("png", encoding="utf-8")
    result = assemble_frequency_plots(
        {
            "freq_mhz": ["real_str", "real_path", "gone"],
            "images": {
                "real_str": str(real),
                "real_path": real,
                "gone": str(tmp_path / "nope.png"),
            },
        }
    )
    assert result["images"] == ["real_str", "real_path"]
    assert result["slots"] == 2
    assert "gone" in result["deficit_note"]


def test_keys_absent_from_images_count_missing():
    """⑦ freq_mhz 中未在 images 登记的键计入缺失。"""
    result = assemble_frequency_plots(
        {"freq_mhz": ["a", "b"], "images": {"a": True}}
    )
    assert result["slots"] == 1
    assert result["images"] == ["a"]
    assert "b" in result["deficit_note"]


def test_registered_but_too_few_all_available():
    """⑧ 登记 3 键全可用但不足 5：仍如实注记缺 2（登记数不足口径）。"""
    result = assemble_frequency_plots(
        {"freq_mhz": ["a", "b", "c"], "images": {"a": True, "b": True, "c": True}}
    )
    assert result["slots"] == 3
    assert result["satisfied"] is False
    assert "缺 2 个频点图" in result["deficit_note"]
    assert "登记数不足" in result["deficit_note"]


def test_more_than_five_satisfied():
    """⑨ 超 5（6 可用）：slots=6/satisfied=True/note 空串。"""
    keys = [f"ch{i}" for i in range(6)]
    result = assemble_frequency_plots({"freq_mhz": keys, "images": {k: True for k in keys}})
    assert result["slots"] == 6
    assert result["satisfied"] is True
    assert result["deficit_note"] == ""


def test_result_key_set_exactly_five_fields():
    """⑩ 输出键集合恰为 slots/required/images/deficit_note/satisfied 五键。"""
    result = assemble_frequency_plots({})
    assert set(result) == {"slots", "required", "images", "deficit_note", "satisfied"}
    assert isinstance(result["slots"], int) and isinstance(result["satisfied"], bool)


def test_non_dict_plots_rejected():
    """⑪ plots 非 dict（None/list/str/int）→ ValueError。"""
    for bad in (None, ["ch2412"], "ch2412", 5):
        with pytest.raises(ValueError, match="plots"):
            assemble_frequency_plots(bad)


def test_bad_freq_mhz_shape_rejected():
    """⑫ freq_mhz 非 list 或元素非 str（int/None/bool）→ ValueError。"""
    for bad in ("ch2412", {"0": "ch2412"}, None):
        with pytest.raises(ValueError, match="freq_mhz"):
            assemble_frequency_plots({"freq_mhz": bad})
    with pytest.raises(ValueError, match="freq_mhz"):
        assemble_frequency_plots({"freq_mhz": ["ch2412", 2412]})
    with pytest.raises(ValueError, match="freq_mhz"):
        assemble_frequency_plots({"freq_mhz": ["ch2412", None]})


def test_bad_images_shape_and_entry_type_rejected():
    """⑬ images 非 dict、或表项既非 bool 也非路径（int）→ ValueError。"""
    for bad in (["x"], "x", None, 3):
        with pytest.raises(ValueError, match="images"):
            assemble_frequency_plots({"freq_mhz": ["a"], "images": bad})
    with pytest.raises(ValueError, match="images"):
        assemble_frequency_plots({"freq_mhz": ["a"], "images": {"a": 2412}})
