"""extract_report_numbers 对抗测试：单值/行多值抽取、单位家族参数化、科学计数、
表格行、行号 1-based、上下文截短 60 字符、无非数值空列表、非 str 拒绝、
重复值保留、单位词界（dBi/samples 不抽）、负号词界（含 U+2212 减号）与
紧贴/隔空白两式、dBµV/dBuV 单位族（µ/u 双形）、复合单位 dBm/Hz 口径。"""
from __future__ import annotations

import pytest

from src.verify_report_traceability.extract_report_numbers import extract_report_numbers


def test_single_value_entry_shape():
    """① 单值抽取：四键 value/unit/line_no/context，类型 float/str/int/str。"""
    entries = extract_report_numbers("电平 -20.5 dBm")
    assert len(entries) == 1
    entry = entries[0]
    assert set(entry) == {"value", "unit", "line_no", "context"}
    assert entry["value"] == -20.5
    assert entry["unit"] == "dBm"
    assert entry["line_no"] == 1
    assert entry["context"] == "电平 -20.5 dBm"


def test_multiple_values_on_one_line():
    """② 行多值逐一抽：同 line_no、按出现顺序。"""
    entries = extract_report_numbers("余量 6.5 dB @ 2437 MHz，占空 50%")
    assert [(e["value"], e["unit"]) for e in entries] == [
        (6.5, "dB"),
        (2437.0, "MHz"),
        (50.0, "%"),
    ]
    assert len({e["line_no"] for e in entries}) == 1


@pytest.mark.parametrize(
    "text,value,unit",
    [
        ("-20.5 dBm", -20.5, "dBm"),
        ("30 dB", 30.0, "dB"),
        ("2437 MHz", 2437.0, "MHz"),
        ("5.8 GHz", 5.8, "GHz"),
        ("120 ms", 120.0, "ms"),
        ("2 s", 2.0, "s"),
        ("50%", 50.0, "%"),
        ("60 Hz", 60.0, "Hz"),
    ],
)
def test_unit_family_parametrized(text, value, unit):
    """③ 单位家族参数化：八类单位各抽一例，值与单位词精确。"""
    entries = extract_report_numbers(text)
    assert len(entries) == 1
    assert entries[0]["value"] == value
    assert entries[0]["unit"] == unit


@pytest.mark.parametrize(
    "text,value,unit",
    [
        ("换算 50 dBµV", 50.0, "dBµV"),  # µ（U+00B5 MICRO SIGN）形
        ("换算 50 dBuV", 50.0, "dBuV"),  # u（ASCII）形
        ("限值 46.2 dBµV 紧贴", 46.2, "dBµV"),
        ("准峰值 39.5 dBuV", 39.5, "dBuV"),
    ],
)
def test_dbuv_family_both_spellings(text, value, unit):
    """③b dBµV/dBuV 单位族（B18 中#4）：µ 与 u 双形各抽一例，单位词原样保留。"""
    entries = extract_report_numbers(text)
    assert len(entries) == 1
    assert entries[0]["value"] == value
    assert entries[0]["unit"] == unit


def test_dbuv_not_truncated_to_db():
    """③c '50 dBµV' 不被截短成 'dB'（长前缀优先）；'46 dBµ'（半截单位）不抽。"""
    entries = extract_report_numbers("换算 50 dBµV，另一处 46 dBµ")
    assert [(e["value"], e["unit"]) for e in entries] == [(50.0, "dBµV")]


def test_composite_unit_dbm_per_hz_kept():
    """③d 复合单位口径（B18 中#4 验证保留）：'-30 dBm/Hz' 抽 (-30, 'dBm')——
    '/' 非 \\w，词界 (?!\\w) 放行，功率谱密度行如实抽出数值侧。"""
    entries = extract_report_numbers("功率谱密度 -30 dBm/Hz")
    assert [(e["value"], e["unit"]) for e in entries] == [(-30.0, "dBm")]


@pytest.mark.parametrize(
    "text,value",
    [
        ("带宽 1e6 Hz", 1_000_000.0),
        ("载波 2.4e9 Hz", 2.4e9),
        ("2.4GHz 紧贴", 2.4),
        ("脉宽 -3.5E-2 ms", -0.035),
    ],
)
def test_scientific_notation_supported(text, value):
    """④ 科学计数（1e6/2.4e9/负指数/大写 E/紧贴单位）按面值换算。"""
    entries = extract_report_numbers(text)
    assert len(entries) == 1
    assert entries[0]["value"] == pytest.approx(value)


def test_table_row_cells_extracted():
    """⑤ 表格行：'| -20.5 dBm | 30 dB |' 两单元格各成一entry。"""
    entries = extract_report_numbers("| 频点 | 读数 | 余量 |\n| 2437 MHz | -20.5 dBm | 30 dB |")
    assert [(e["value"], e["unit"]) for e in entries] == [
        (2437.0, "MHz"),
        (-20.5, "dBm"),
        (30.0, "dB"),
    ]
    assert all(e["line_no"] == 2 for e in entries)


def test_line_numbers_one_based_across_lines():
    """⑥ 行号正确：1-based，空行/无数字行也占行号。"""
    md = "# 报告\n\n电平 -95 dBm\n\n\n时延 120 ms"
    entries = extract_report_numbers(md)
    assert [(e["line_no"], e["value"]) for e in entries] == [(3, -95.0), (6, 120.0)]


def test_context_truncated_to_60_chars():
    """⑦ 上下文截短：超 60 字符行取前 60 字符，与原文前缀逐字相等。"""
    line = "前缀" + "x" * 80 + " -20.5 dBm"
    entries = extract_report_numbers(line)
    assert len(entries[0]["context"]) == 60
    assert entries[0]["context"] == line[:60]
    short = "短行 -20.5 dBm"
    assert extract_report_numbers(short)[0]["context"] == short


def test_no_numeric_lines_yield_empty_list():
    """⑧ 无非数值行/空文本/纯文字数字无单位→空列表。"""
    assert extract_report_numbers("全是文字，没有数字。") == []
    assert extract_report_numbers("") == []
    assert extract_report_numbers("编号 2026 与批次 42 无单位") == []


def test_non_string_report_rejected():
    """⑨ 非 str（None/int/list/dict/bytes）→ ValueError。"""
    for bad in (None, 42, ["-20.5 dBm"], {"md": "x"}, b"-20.5 dBm"):
        with pytest.raises(ValueError, match="str"):
            extract_report_numbers(bad)


def test_duplicate_values_retained():
    """⑩ 重复值保留：同行两处与跨行重现各成独立条目。"""
    entries = extract_report_numbers("限值 30 dB，读数 30 dB\n复测 30 dB")
    assert len(entries) == 3
    assert [e["line_no"] for e in entries] == [1, 1, 2]


def test_unit_word_boundary_not_truncated():
    """⑪ 单位词界：'10 dBi'/'4 MHzx'/'5 samples' 均不抽（不截短单位）。"""
    for text in ("天线增益 10 dBi", "伪单位 4 MHzx", "采样 5 samples"):
        assert extract_report_numbers(text) == []


def test_dbm_not_misread_as_db():
    """⑫ dBm 不被 dB 截短：'-95 dBm' 单位为 'dBm'；同行 '30 dB' 单位为 'dB'。"""
    entries = extract_report_numbers("底噪 -95 dBm，增益 30 dB")
    assert [(e["value"], e["unit"]) for e in entries] == [(-95.0, "dBm"), (30.0, "dB")]


def test_minus_sign_word_boundary():
    """⑬ 负号词界：'3-4 dB' 取 4 不取 -4（区间连字符非负号）；'(-20.5 dBm)' 取负值。"""
    entries = extract_report_numbers("扫频 3-4 dB")
    assert [e["value"] for e in entries] == [4.0]
    assert extract_report_numbers("括号 (-20.5 dBm) 内")[0]["value"] == -20.5


def test_unicode_minus_u2212_negative_value():
    """⑬b U+2212 减号（B18 中#3）：'−20.5 dBm'（UNICODE MINUS SIGN）取 -20.5。"""
    entries = extract_report_numbers("电平 −20.5 dBm")
    assert len(entries) == 1
    assert entries[0]["value"] == -20.5
    assert entries[0]["unit"] == "dBm"


def test_unicode_minus_range_hyphen_not_negative():
    """⑬c U+2212 区间减号非负号：'3−4 dB' 取 4 不取 -4（与 ASCII '-' 同规）。"""
    entries = extract_report_numbers("扫频 3−4 dB")
    assert [e["value"] for e in entries] == [4.0]


def test_spacing_between_number_and_unit_both_forms():
    """⑭ 紧贴（'2.4GHz'）与隔空白（'2.4 GHz'）两式均抽取。"""
    tight = extract_report_numbers("载波 2.4GHz")
    loose = extract_report_numbers("载波 2.4 GHz")
    assert tight[0]["value"] == loose[0]["value"] == 2.4
    assert tight[0]["unit"] == loose[0]["unit"] == "GHz"
