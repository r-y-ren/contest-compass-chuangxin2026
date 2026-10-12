"""compare_failure_boundaries 对抗测试（slug=boundary_compare）：中位数聚合/升序表/平手字典序/unknown 口径/薄弱频点/降级与拒收。"""
from __future__ import annotations

import pytest

from src.compare_failure_boundaries.compare_failure_boundaries import (
    compare_failure_boundaries,
)

_ROW_KEYS = {"style", "median_level_db", "n_runs", "min_db", "max_db"}


def _entry(style, level, freq=None):
    """record_failure_level 形条目：透传 per_at_failure/ts_ms，freq 可选。"""
    entry = {
        "style": style,
        "failure_level_db": level,
        "per_at_failure": 0.1,
        "ts_ms": 1234.5,
    }
    if freq is not None:
        entry["freq_mhz"] = freq
    return entry


def _median(values):
    """独立复算中位数（不经 statistics 模块）：奇数取中位、偶数取两中均。"""
    ordered = sorted(values)
    n = len(ordered)
    return ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2


def test_boundary_compare_three_styles_table_sorted_and_weakest():
    levels_by_style = {
        "tone": [-20, -22],
        "pulse": [-15, -17, -16, -14],
        "chirp": [-8, -12, -10],
    }
    entries = [
        _entry("chirp", -8),
        _entry("chirp", -12),
        _entry("chirp", -10),
        _entry("tone", -20),
        _entry("tone", -22),
        _entry("pulse", -15),
        _entry("pulse", -17),
        _entry("pulse", -16),
        _entry("pulse", -14),
    ]
    result = compare_failure_boundaries(entries)

    medians = [row["median_level_db"] for row in result["comparison"]]
    assert medians == sorted(medians)  # 升序表
    assert medians == [-21.0, -15.5, -10]
    assert [row["style"] for row in result["comparison"]] == [
        "tone",
        "pulse",
        "chirp",
    ]
    for row in result["comparison"]:
        assert set(row) == _ROW_KEYS
        levels = levels_by_style[row["style"]]  # 独立复算（含偶数轮 .5 中位）
        assert row["median_level_db"] == _median(levels)
        assert row["min_db"] == min(levels)
        assert row["max_db"] == max(levels)
        assert row["n_runs"] == len(levels)
    assert result["weakest_style"] == "tone"  # 中位数最低者
    assert result["tie"] is False and result["n_unknown"] == 0
    assert result["weakest_freq_mhz"] is None  # 无 freq_mhz 字段


def test_boundary_compare_tie_picks_lexicographic_first_and_flags():
    entries = [
        _entry("noise", -10),
        _entry("noise", -14),
        _entry("chirp", -14),
        _entry("chirp", -10),
        _entry("tone", -6),
        _entry("tone", -4),
    ]
    result = compare_failure_boundaries(entries)
    assert result["weakest_style"] == "chirp"  # -12.0 并列，字典序先
    assert result["tie"] is True
    assert result["comparison"][0]["style"] == "chirp"


def test_boundary_compare_unknown_entries_excluded_from_stats_counted():
    missing_level = {"style": "tone", "per_at_failure": 0.05, "ts_ms": 9.0}
    entries = [
        _entry("tone", -10),
        _entry("tone", "unknown"),
        _entry("tone", -20),
        _entry("tone", "unknown"),
        missing_level,  # 缺电平键同样按 unknown 口径计
        _entry("chirp", -30),
    ]
    result = compare_failure_boundaries(entries)
    tone_rows = [r for r in result["comparison"] if r["style"] == "tone"]
    assert tone_rows == [
        {
            "style": "tone",
            "median_level_db": -15.0,
            "n_runs": 2,
            "min_db": -20,
            "max_db": -10,
        }
    ]
    assert result["n_unknown"] == 3
    assert result["weakest_style"] == "chirp"


def test_boundary_compare_all_unknown_cannot_locate():
    entries = [
        _entry("tone", "unknown"),
        _entry("chirp", "unknown"),
        _entry("pulse", "unknown"),
    ]
    result = compare_failure_boundaries(entries)
    assert result["comparison"] == []
    assert result["weakest_style"] is None and result["weakest_freq_mhz"] is None
    assert result["tie"] is False and result["n_unknown"] == 3
    assert "无法定位" in result["conclusion"]


def test_boundary_compare_single_style_degrades_to_no_cross_comparison():
    entries = [
        _entry("chirp", -10),
        _entry("chirp", -12),
        _entry("chirp", -11),
        _entry("chirp", "unknown"),
    ]
    result = compare_failure_boundaries(entries)
    assert result["comparison"] == []  # 降级：对比表置空
    assert result["weakest_style"] is None and result["tie"] is False
    assert result["n_unknown"] == 1
    assert "单样式数据——无跨样式对比" in result["conclusion"]
    assert "中位数 -11 dB" in result["conclusion"]  # 单样式统计仍进结论
    assert "unknown" in result["conclusion"]


def test_boundary_compare_freq_dimension_weakest_freq():
    entries = [
        _entry("chirp", -10, freq=900),
        _entry("chirp", -12, freq=900),
        _entry("tone", -20, freq=2400),
        _entry("tone", -24, freq=2400),
        _entry("tone", -22, freq=2400),
        _entry("pulse", -30, freq=5800),
        _entry("pulse", -28, freq=5800),
    ]
    result = compare_failure_boundaries(entries)
    assert result["weakest_freq_mhz"] == 5800.0
    assert isinstance(result["weakest_freq_mhz"], float)
    assert result["weakest_style"] == "pulse"  # 样式维度互不干扰
    assert "5800" in result["conclusion"] and "MHz" in result["conclusion"]


def test_boundary_compare_freq_median_tie_flags_and_picks_smaller_freq():
    entries = [
        _entry("chirp", -10, freq=900),
        _entry("chirp", -20, freq=900),
        _entry("tone", -14, freq=2400),
        _entry("pulse", -16, freq=2400),
    ]
    result = compare_failure_boundaries(entries)
    # 频点中位数并列 -15.0→取较小频点；样式维最弱 pulse(-16) 无并列
    assert result["weakest_freq_mhz"] == 900.0
    assert result["weakest_style"] == "pulse"
    assert result["tie"] is True


def test_boundary_compare_single_freq_group_freq_none():
    entries = [
        _entry("tone", -20, freq=900),
        _entry("chirp", -10, freq=900),
    ]
    result = compare_failure_boundaries(entries)
    assert result["weakest_freq_mhz"] is None  # 仅 1 个频点：无跨频点可比
    assert result["weakest_style"] == "tone"


def test_boundary_compare_empty_list_returns_no_data():
    result = compare_failure_boundaries([])
    assert result == {
        "comparison": [],
        "weakest_style": None,
        "weakest_freq_mhz": None,
        "tie": False,
        "n_unknown": 0,
        "n_freq_invalid": 0,
        "conclusion": "无数据",
    }


def test_boundary_compare_non_dict_element_rejected():
    good = _entry("tone", -10)
    with pytest.raises(ValueError) as exc:
        compare_failure_boundaries([good, 42])
    assert "entries[1]" in str(exc.value)  # 指明位置


def test_boundary_compare_entries_not_list_rejected():
    with pytest.raises(ValueError):
        compare_failure_boundaries((_entry("tone", -10),))  # tuple 非 list
    with pytest.raises(ValueError):
        compare_failure_boundaries(None)
    with pytest.raises(ValueError):
        compare_failure_boundaries({"style": "tone"})


def test_boundary_compare_conclusion_numeric_text_and_unknown_hint():
    entries = [
        _entry("tone", -20),
        _entry("tone", -22),
        _entry("chirp", -8),
        _entry("chirp", -10),
        _entry("chirp", -12),
        _entry("pulse", "unknown"),
    ]
    result = compare_failure_boundaries(entries)
    assert result["weakest_style"] == "tone"
    assert "tone" in result["conclusion"]
    assert "中位数 -21.0 dB" in result["conclusion"]  # 数值文案
    assert "unknown" in result["conclusion"] and "1 条" in result["conclusion"]
    assert result["n_unknown"] == 1


# ---------------------------------------------------------------------------
# B13 复审低#5：n_runs 口径按条目计数（docstring+结论文案「有效 N 条（按条目计）」）
# ---------------------------------------------------------------------------
def test_boundary_compare_n_runs_wording_counts_entries():
    entries = [
        _entry("chirp", -10),
        _entry("chirp", -12),
        _entry("chirp", -11),
        _entry("chirp", "unknown"),
    ]
    result = compare_failure_boundaries(entries)
    assert result["comparison"] == []  # 单样式降级：统计进结论
    assert "有效 3 条（按条目计）" in result["conclusion"]  # 非「轮」口径


# ---------------------------------------------------------------------------
# B13 复审低#6：freq_mhz 字符串数字归一入频点维（'2480' 参与 weakest）；
# 归一失败跳过频点维并计 n_freq_invalid（电平维不受影响）
# ---------------------------------------------------------------------------
def test_boundary_compare_string_freq_participates_in_weakest():
    entries = [
        _entry("tone", -20, freq="2480"),  # 字符串数字 → 归一 2480.0
        _entry("tone", -24, freq="2480"),
        _entry("chirp", -10, freq=2400),
        _entry("chirp", -12, freq=2400),
    ]
    result = compare_failure_boundaries(entries)
    assert result["weakest_freq_mhz"] == 2480.0  # '2480' 归一后参与 weakest
    assert isinstance(result["weakest_freq_mhz"], float)
    assert result["n_freq_invalid"] == 0
    assert result["weakest_style"] == "tone"


def test_boundary_compare_invalid_freq_skipped_and_counted():
    entries = [
        _entry("tone", -20, freq="not-a-number"),  # 非数字串 → 归一失败
        _entry("tone", -22, freq="nan"),  # 可 float 但非有限 → 归一失败
        _entry("chirp", -10, freq=2400),
        _entry("chirp", -12, freq=2400),
    ]
    result = compare_failure_boundaries(entries)
    assert result["n_freq_invalid"] == 2
    assert result["weakest_freq_mhz"] is None  # 仅 1 个有效频点：无跨频点可比
    assert result["weakest_style"] == "tone"  # 电平维统计不受频点归一失败影响
    assert "2 条频点不可归一" in result["conclusion"]
