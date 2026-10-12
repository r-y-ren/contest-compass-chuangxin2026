"""locate_ledger_row 对抗测试：定位/状态列解析/▶ 变体/边界与错误路径。"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from src.update_ledger.locate_ledger_row import LedgerError, locate_ledger_row

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LEDGER = REPO_ROOT / "docs" / "全功能实现清单-技术支持版.md"

# 样板：A–L 各域表格 + 一条 ▶ 前缀行 + 数字域指标表（不应被 A–L 定位误伤）。
SAMPLE = """# 全功能实现清单（样板）

## A 域——平台骨架
| 编号 | 功能 | 状态 | 备注 |
| --- | --- | --- | --- |
| A1 | 全维度平台 | wired：骨架已联动 | r1 |
| A2 | 测评体系 | 待开 | r2 |

## B 域——干扰生成
| 编号 | 功能 | 状态 | 备注 |
| --- | --- | --- | --- |
| B1 | 连续覆盖 | ✅ done | r3 |
| B2 | 多调制样式 | ▶ 进行中：样式 5/6 | r4 |
| ▶ B7 | 功率分辨率 | 标定排队 | r5 |
| B10 | 信号源 | 远期 | r6 |

## G 域——扫谱统计
| 编号 | 功能 | 状态 | 备注 |
| --- | --- | --- | --- |
| G3 | 谱统计 | ✅ 已联动 | r7 |

## L 域——能力清单
| 编号 | 能力 | 状态 | 分期 |
| --- | --- | --- | --- |
| L8 | 合规操作规约内置 | 一期 | 一期 |

## 指标表（数字域，不应匹配 A–L）
| 序号 | 指标 | 目标 | 达标路径 |
| --- | --- | --- | --- |
| 1 | 频率覆盖 | 1MHz–10GHz | 远期② |
| 11 | 刷新周期 | <500ms | 一期 |
"""

B1_LINE = "| B1 | 连续覆盖 | ✅ done | r3 |"
B2_LINE = "| B2 | 多调制样式 | ▶ 进行中：样式 5/6 | r4 |"
B7_LINE = "| ▶ B7 | 功率分辨率 | 标定排队 | r5 |"
B10_LINE = "| B10 | 信号源 | 远期 | r6 |"


def _sample_line_no(line: str) -> int:
    return SAMPLE.splitlines().index(line) + 1


@pytest.fixture()
def ledger_path(tmp_path):
    p = tmp_path / "ledger.md"
    p.write_text(SAMPLE, encoding="utf-8")
    return str(p)


def test_normal_entry_location_and_status_parse(ledger_path):
    res = locate_ledger_row("B1", ledger_path)
    assert res["line_no"] == _sample_line_no(B1_LINE)
    assert res["line"] == B1_LINE  # 原文原样返回
    assert res["status_text"] == "✅ done"  # split('|') 第 4 段 strip
    assert res["has_done_mark"] is True
    assert res["in_progress"] is False


def test_wired_status_counts_as_done(ledger_path):
    res = locate_ledger_row("A1", ledger_path)  # 状态列无 ✅、仅 'wired'
    assert res["status_text"] == "wired：骨架已联动"
    assert res["has_done_mark"] is True
    assert res["in_progress"] is False


def test_prefix_row_flagged_in_progress(ledger_path):
    res = locate_ledger_row("B7", ledger_path)  # ▶ 前缀行，状态列无 ▶/进行中
    assert res["line_no"] == _sample_line_no(B7_LINE)
    assert res["line"] == B7_LINE
    assert res["in_progress"] is True
    assert res["has_done_mark"] is False


def test_status_column_in_progress_text(ledger_path):
    res = locate_ledger_row("B2", ledger_path)  # 状态列含 ▶ 与 进行中
    assert res["line_no"] == _sample_line_no(B2_LINE)
    assert res["status_text"] == "▶ 进行中：样式 5/6"
    assert res["in_progress"] is True
    assert res["has_done_mark"] is False


def test_similar_ids_do_not_cross_match(ledger_path):
    b1 = locate_ledger_row("B1", ledger_path)
    b10 = locate_ledger_row("B10", ledger_path)
    assert b1["line"] == B1_LINE and b10["line"] == B10_LINE  # 正则边界：B1 不误配 B10
    assert b1["line_no"] != b10["line_no"]
    assert b1["status_text"] != b10["status_text"]
    g3 = locate_ledger_row("G3", ledger_path)  # 其他字母域正常
    assert g3["has_done_mark"] is True


def test_zero_match_error_lists_same_domain_ids(ledger_path):
    with pytest.raises(LedgerError) as ei:
        locate_ledger_row("B9", ledger_path)  # B 域存在但 B9 无
    msg = str(ei.value)
    for hint in ("B1", "B2", "B7", "B10"):
        assert hint in msg  # 同字母域现有编号列表
    assert "B9" in msg
    assert "A1" not in msg  # 不混入他域编号
    with pytest.raises(LedgerError) as ei2:
        locate_ledger_row("H1", ledger_path)  # H 域整体不存在
    assert "H" in str(ei2.value)


def test_ambiguous_double_match_rejected(tmp_path):
    text = SAMPLE.replace(
        B1_LINE,
        B1_LINE + "\n| B1 | 重复行 | x | y |",
    )
    p = tmp_path / "dup.md"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(LedgerError) as ei:
        locate_ledger_row("B1", str(p))
    msg = str(ei.value)
    assert "B1" in msg
    assert "多处命中" in msg
    nos = [_sample_line_no(B1_LINE), _sample_line_no(B1_LINE) + 1]
    assert f"第 {'、'.join(str(n) for n in nos)} 行" in msg  # 附各处行号


def test_missing_file_rejected(tmp_path):
    missing = tmp_path / "nope.md"
    with pytest.raises(LedgerError) as ei:
        locate_ledger_row("B5", str(missing))
    assert "nope.md" in str(ei.value)


@pytest.mark.parametrize("bad", ["M1", "a1", "", "B123", "B", "1B", "B-1"])
def test_malformed_string_ids_rejected(ledger_path, bad):
    with pytest.raises(ValueError):
        locate_ledger_row(bad, ledger_path)


@pytest.mark.parametrize("bad", [None, 42])
def test_non_string_ids_rejected(ledger_path, bad):
    with pytest.raises(ValueError):
        locate_ledger_row(bad, ledger_path)


def test_real_ledger_b5_smoke():
    assert REAL_LEDGER.exists()
    res = locate_ledger_row("B5", str(REAL_LEDGER))  # 存在且唯一（否则上方已抛 LedgerError）
    raw_lines = REAL_LEDGER.read_text(encoding="utf-8").splitlines()
    assert 1 <= res["line_no"] <= len(raw_lines)
    assert raw_lines[res["line_no"] - 1] == res["line"]  # 1-based 行号与真文件互核
    assert res["line"].startswith("| B5 |")
    assert res["status_text"]  # 状态列（第 3 管道列）非空
    assert isinstance(res["has_done_mark"], bool)
    assert isinstance(res["in_progress"], bool)


def test_default_ledger_path_contract():
    default = inspect.signature(locate_ledger_row).parameters["ledger_path"].default
    assert default == "docs/全功能实现清单-技术支持版.md"
