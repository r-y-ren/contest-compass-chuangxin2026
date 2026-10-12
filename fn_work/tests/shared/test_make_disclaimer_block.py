"""make_disclaimer_block 对抗测试：三场景关键词、'> ' 逐行前缀、互异、未知/非 str/大小写拒绝、
幂等内容恒定且每次新对象、report 替换恒含行且不混入 emc 专属句。"""
from __future__ import annotations

import pytest

from src.shared.make_disclaimer_block import (
    EMC_LINES,
    EMERGENCY_LINES,
    REPORT_ALWAYS_LINE,
    REPORT_LINES,
    SIM_ALWAYS_LINE,
    VALID_SCENES,
    make_disclaimer_block,
)


def test_emc_scene_keywords():
    """① emc 场景：含 'CISPR 16-1-1'+'模拟'+'simulated'，且逐字携带模拟恒含行。"""
    block = make_disclaimer_block("emc")
    assert isinstance(block, str)
    assert "CISPR 16-1-1" in block
    assert "模拟" in block
    assert "simulated" in block
    assert SIM_ALWAYS_LINE in block


def test_report_scene_keywords():
    """② report 场景：含 '屏蔽盒'+'自建链路'+'GB 42590'+'方法学预研' 四关键词。"""
    block = make_disclaimer_block("report")
    for kw in ("屏蔽盒", "自建链路", "GB 42590", "方法学预研"):
        assert kw in block


def test_emergency_scene_keyword():
    """③ emergency 场景：含 '停发射' 与模拟恒含行。"""
    block = make_disclaimer_block("emergency")
    assert "停发射" in block
    assert SIM_ALWAYS_LINE in block


def test_quote_prefix_on_every_line():
    """④ '> ' 前缀逐行：三场景全部行带前缀，无空行/裸前缀行/结尾换行。"""
    for scene in VALID_SCENES:
        block = make_disclaimer_block(scene)
        assert block.endswith("\n") is False
        assert "\n\n" not in block
        for line in block.split("\n"):
            assert line.startswith("> "), f"{scene}: 行缺 '> ' 前缀: {line!r}"
            assert len(line) > 2, f"{scene}: 出现裸前缀/空行: {line!r}"


def test_scenes_pairwise_distinct():
    """⑤ 三场景输出互异（两两不等）。"""
    blocks = {scene: make_disclaimer_block(scene) for scene in VALID_SCENES}
    emc, rep, emg = blocks["emc"], blocks["report"], blocks["emergency"]
    assert emc != rep and emc != emg and rep != emg


def test_unknown_scene_rejected_with_enum_list():
    """⑥ 未知 scene→ValueError，消息附全部合法枚举名。"""
    for bad in ("lab", "", "emc ", "report!", "停发射"):
        with pytest.raises(ValueError) as excinfo:
            make_disclaimer_block(bad)
        msg = str(excinfo.value)
        for name in VALID_SCENES:
            assert name in msg, f"错误消息缺枚举 {name}: {msg}"


def test_non_string_scene_rejected():
    """⑦ None/非 str（int/list/dict/对象）一律拒绝（签名错误契约为 ValueError）。"""
    for bad in (None, 7, 3.14, ["emc"], {"scene": "emc"}, b"emc", object()):
        with pytest.raises(ValueError):
            make_disclaimer_block(bad)


def test_fresh_string_each_call_constant_content():
    """⑧ 每次调用返回新 str 对象，内容幂等恒定。"""
    first = make_disclaimer_block("emc")
    second = make_disclaimer_block("emc")
    assert first == second
    assert first is not second


def test_report_replaces_always_line():
    """⑨ report 场景恒含行被替换：带标注行、不带模拟演示恒含行原文。"""
    block = make_disclaimer_block("report")
    assert REPORT_ALWAYS_LINE in block
    assert SIM_ALWAYS_LINE not in block


def test_report_has_no_emc_specific_sentence():
    """⑩ report 不混入 emc 专属句：无 'CISPR 16-1-1'、无 EMC 首行原文。"""
    block = make_disclaimer_block("report")
    assert "CISPR 16-1-1" not in block
    for line in EMC_LINES:
        assert line not in block


def test_scene_enum_case_sensitive():
    """⑪ 场景大小写敏感：'EMC'/'Report'/'EMERGENCY' 等变体均拒。"""
    for bad in ("EMC", "Report", "EMERGENCY", "emc".upper(), "Emergency"):
        with pytest.raises(ValueError):
            make_disclaimer_block(bad)


def test_output_matches_module_level_constants():
    """⑫ 文案常量模块级：输出恰为对应常量逐行加 '> ' 前缀的拼接。"""
    assert make_disclaimer_block("emc") == "\n".join(f"> {l}" for l in EMC_LINES)
    assert make_disclaimer_block("report") == "\n".join(f"> {l}" for l in REPORT_LINES)
    assert make_disclaimer_block("emergency") == "\n".join(f"> {l}" for l in EMERGENCY_LINES)
