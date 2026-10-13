"""locate_ledger_row 对抗测试：定位/状态列解析/▶ 变体/边界与错误路径。"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from src.update_ledger.locate_ledger_row import LedgerError, locate_ledger_row

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LEDGER = REPO_ROOT / "docs" / "全功能实现清单-技术支持版.md"

# 样板：A–L 各域表格（两类表头形态：含状态列 / 真清单 4 列无状态列）+ 一条
# ▶ 前缀行 + 描述列含 \| 转义管道行 + 数字域指标表（不应被 A–L 定位误伤）。
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
| B8 | 频率准确度 \\| 相位噪声 \\| 双指标 | 待开 | r7 |

## C 域——真清单形态（表头无状态列，4 列）
| 编号 | 功能要求 | 技术支持与实现路径 | 分期 |
| --- | --- | --- | --- |
| C1 | 混频扩展至 13GHz | 远期⑤混频器仪表到位后实施（§5.5 L139） | 远期⑤ |
| C2 | 谐波与微弱干扰表征 | CH2 监测通道验平坦度 \\| 实际注入谱 | 一期（监测级） |

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
B8_LINE = "| B8 | 频率准确度 \\| 相位噪声 \\| 双指标 | 待开 | r7 |"
C_HEADER = "| 编号 | 功能要求 | 技术支持与实现路径 | 分期 |"
C_SEP = "| --- | --- | --- | --- |"
C1_LINE = "| C1 | 混频扩展至 13GHz | 远期⑤混频器仪表到位后实施（§5.5 L139） | 远期⑤ |"
C2_LINE = "| C2 | 谐波与微弱干扰表征 | CH2 监测通道验平坦度 \\| 实际注入谱 | 一期（监测级） |"
B_HEADER = "| 编号 | 功能 | 状态 | 备注 |"


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


def test_status_column_form_detected_from_header(ledger_path):
    # 有状态列表头（样板 A/B/G/L 域）→ status 形态：状态列＝表头「状态」列。
    res = locate_ledger_row("B1", ledger_path)
    assert res["table_form"] == "status"
    assert res["status_col_index"] == 3
    assert res["header_line"] == B_HEADER
    assert 0 < res["header_line_no"] < res["line_no"]
    sample_lines = SAMPLE.splitlines()
    assert sample_lines[res["header_line_no"] - 1] == B_HEADER  # 表头行号与原文互核
    assert res["status_text"] == "✅ done"


def test_real_ledger_form_no_status_column(ledger_path):
    # 真清单形态（表头 4 列无「状态」）→ append 形态：状态语义恒空（描述列
    # 绝不被误读为状态——B17 高#1 读侧），加列写侧归 update_ledger。
    res = locate_ledger_row("C1", ledger_path)
    assert res["line_no"] == _sample_line_no(C1_LINE)
    assert res["table_form"] == "append"
    assert res["status_col_index"] is None
    assert res["header_line_no"] == _sample_line_no(C_HEADER)
    assert res["header_line"] == C_HEADER
    assert res["status_text"] == ""
    assert res["has_done_mark"] is False and res["in_progress"] is False


def test_escaped_pipe_in_description_keeps_columns(ledger_path):
    # 描述列含 \|（转义管道）——不参与切列（B17 中#2），状态列仍取第 3 管道列。
    res = locate_ledger_row("B8", ledger_path)
    assert res["table_form"] == "status" and res["status_col_index"] == 3
    assert res["status_text"] == "待开"  # 若 \| 误切列，此处会读到 '相位噪声 \| 双指标'
    # 真清单形态下 \| 在技术路径列——append 判定同样不受影响。
    res2 = locate_ledger_row("C2", ledger_path)
    assert res2["table_form"] == "append" and res2["status_text"] == ""


def test_headerless_table_falls_back_to_legacy_column(tmp_path):
    # 无表头（无「表头+分隔行」结构）→ legacy 兜底：旧口径第 3 管道列。
    p = tmp_path / "headerless.md"
    p.write_text("| B1 | 连续覆盖 | ✅ done | r |\n", encoding="utf-8")
    res = locate_ledger_row("B1", str(p))
    assert res["table_form"] == "legacy"
    assert res["header_line_no"] is None and res["header_line"] is None
    assert res["status_col_index"] == 3
    assert res["status_text"] == "✅ done" and res["has_done_mark"] is True


def test_appended_status_column_rediscovered_as_status_form(tmp_path):
    # 补列后表头含「完成状态」→ 自动回到 status 形态，✅ 判定来自新列。
    text = SAMPLE.replace(
        C_HEADER, C_HEADER + " 完成状态 |"
    ).replace(
        C_SEP, C_SEP + " --- |"
    ).replace(
        C1_LINE, C1_LINE + " ✅ 10-12 fn(demo_impl) |"
    )
    p = tmp_path / "appended.md"
    p.write_text(text, encoding="utf-8")
    res = locate_ledger_row("C1", str(p))
    assert res["table_form"] == "status"
    assert res["status_col_index"] == 5
    assert res["status_text"] == "✅ 10-12 fn(demo_impl)"
    assert res["has_done_mark"] is True
    # 同表未补列的行：状态列为空（不算 done），描述列原样。
    res2 = locate_ledger_row("C2", str(p))
    assert res2["table_form"] == "status" and res2["status_text"] == ""
    assert res2["has_done_mark"] is False
    assert res2["line"] == C2_LINE


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
    # 真清单是活文档：回写会补「完成状态」列（table_form 由 append 回到 status、行尾
    # 追 ✅）。冒烟只验证定位与解析自洽——状态无关断言，不绑定回写前后某个快照。
    assert REAL_LEDGER.exists()
    res = locate_ledger_row("B5", str(REAL_LEDGER))  # 存在且唯一（否则上方已抛 LedgerError）
    raw_lines = REAL_LEDGER.read_text(encoding="utf-8").splitlines()
    assert res["line_no"] > 0
    assert res["line_no"] <= len(raw_lines)
    assert raw_lines[res["line_no"] - 1] == res["line"]  # 1-based 行号与真文件互核
    assert res["line"].startswith("| B5")
    # 表头检测的两种合法形态：回写前 append（4 列无状态列）／补列后 status。
    assert res["table_form"] in ("append", "status")
    assert isinstance(res["has_done_mark"], bool)
    if res["has_done_mark"]:
        assert "✅" in res["status_text"]  # done 判定须出自状态列原文
    assert isinstance(res["in_progress"], bool)
    assert res["header_line_no"] is not None and "分期" in res["header_line"]


def test_default_ledger_path_contract():
    """缺省路径契约（误导③修订）：ledger_path 缺省 None 哨兵（调用时回落模块
    全局 DEFAULT_LEDGER_PATH，monkeypatch 友好）；模块常量锚定仓库根绝对路径
    （locate_ledger_row.py 的 parents[3]）——从任意 cwd 调用都指向同一份清单。"""
    from pathlib import Path

    import src.update_ledger.locate_ledger_row as locate_mod

    default = inspect.signature(locate_ledger_row).parameters["ledger_path"].default
    assert default is None  # None 哨兵 → 调用时动态回落模块全局
    repo_root = Path(locate_mod.__file__).resolve().parents[3]
    assert Path(locate_mod.DEFAULT_LEDGER_PATH) == (
        repo_root / "docs" / "全功能实现清单-技术支持版.md"
    )
    assert Path(locate_mod.DEFAULT_LEDGER_PATH).is_absolute()
