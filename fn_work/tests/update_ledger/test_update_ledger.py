"""update_ledger 对抗测试：✅+日期+锚点写入/覆盖授权/▶ 行/原子性/统计节不动。"""
from __future__ import annotations

import inspect
from datetime import date

import pytest

from src.update_ledger.locate_ledger_row import locate_ledger_row
from src.update_ledger.update_ledger import update_ledger
from src.update_ledger.update_ledger import LedgerError

# 样板：含已完成（A2）/未完成（A1、B1）/▶ 前缀（B7）/\| 转义管道（B8）行 +
# 真清单形态 C 域（表头无状态列，4 列）+ 人工维护统计节。
SAMPLE = """# 全功能实现清单（样板）

## A 域——平台骨架
| 编号 | 功能 | 状态 | 备注 |
| --- | --- | --- | --- |
| A1 | 全维度平台 | 待开 | r1 |
| A2 | 测评体系 | ✅ 10-01 fn(old_fn) commit aaa111 | r2 |

## B 域——干扰生成
| 编号 | 功能 | 状态 | 备注 |
| --- | --- | --- | --- |
| B1 | 连续覆盖 | 待开 | r3 |
| ▶ B7 | 功率分辨率 | 标定排队 | r5 |
| B8 | 频率准确度 \\| 相位噪声 | 待开 | r6 |

## C 域——真清单形态（表头无状态列）
| 编号 | 功能要求 | 技术支持与实现路径 | 分期 |
|----|----|----|----|
| C1 | 混频扩展至 13GHz | 远期⑤混频器仪表到位后实施（§5.5 L139） | 远期⑤ |
| C2 | 谐波精细化表征 | CH2 监测通道验平坦度 \\| 实际注入谱 | 一期（监测级） |

## 统计与说明

- 共 3 个域、7 条（本节人工维护，update_ledger 不滚动）。
"""

B1_LINE = "| B1 | 连续覆盖 | 待开 | r3 |"
B7_LINE = "| ▶ B7 | 功率分辨率 | 标定排队 | r5 |"
A2_LINE = "| A2 | 测评体系 | ✅ 10-01 fn(old_fn) commit aaa111 | r2 |"
B8_LINE = "| B8 | 频率准确度 \\| 相位噪声 | 待开 | r6 |"
C_HEADER = "| 编号 | 功能要求 | 技术支持与实现路径 | 分期 |"
C_SEP = "|----|----|----|----|"
C1_LINE = "| C1 | 混频扩展至 13GHz | 远期⑤混频器仪表到位后实施（§5.5 L139） | 远期⑤ |"
C2_LINE = "| C2 | 谐波精细化表征 | CH2 监测通道验平坦度 \\| 实际注入谱 | 一期（监测级） |"


def _line_no(line: str) -> int:
    return SAMPLE.splitlines().index(line) + 1


@pytest.fixture()
def ledger_path(tmp_path):
    p = tmp_path / "ledger.md"
    p.write_text(SAMPLE, encoding="utf-8")
    return str(p)


def test_ledger_update_normal_write_and_readback(ledger_path):
    anchor = "fn(open_b210_backend) commit abc1234"
    res = update_ledger("B1", anchor, ledger_path=ledger_path)

    today = date.today().strftime("%m-%d")
    assert res == {
        "updated": True,
        "line_no": _line_no(B1_LINE),
        "old_status": "待开",
        "new_status": f"✅ {today} {anchor}",
        "anchor": anchor,
    }
    # 文件侧：目标行含 ✅+anchor，列数不变（管道数一致），其余列原样。
    lines = open(ledger_path, encoding="utf-8").read().splitlines()
    new_line = lines[_line_no(B1_LINE) - 1]
    assert "✅" in new_line and anchor in new_line
    assert new_line.count("|") == B1_LINE.count("|")
    assert new_line.startswith("| B1 | 连续覆盖 |") and new_line.endswith("| r3 |")
    # 读回定位核验：locate 复核新状态。
    back = locate_ledger_row("B1", ledger_path)
    assert back["has_done_mark"] is True
    assert back["in_progress"] is False
    assert back["status_text"] == res["new_status"]


def test_ledger_update_single_line_diff_only_entry_row(ledger_path):
    before = SAMPLE.splitlines()
    update_ledger("B1", "fn(x1_y1)", ledger_path=ledger_path)
    after = open(ledger_path, encoding="utf-8").read().splitlines()
    diff = [(i, a, b) for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(diff) == 1  # 全文只有条目行这一行变化
    assert diff[0][0] + 1 == _line_no(B1_LINE)
    assert len(before) == len(after)  # 行数不变（无增删行）


def test_ledger_update_already_done_blocks_without_overwrite(ledger_path):
    snapshot = open(ledger_path, encoding="utf-8").read()
    with pytest.raises(LedgerError) as ei:
        update_ledger("A2", "fn(new_fn)", ledger_path=ledger_path)
    msg = str(ei.value)
    assert "已 ✅" in msg and "未授权覆盖" in msg and "overwrite=True" in msg
    assert open(ledger_path, encoding="utf-8").read() == snapshot  # 文件未被改动


def test_ledger_update_overwrite_explicit_replaces(ledger_path):
    anchor = "fn(new_fn) commit bbb222"
    res = update_ledger("A2", anchor, overwrite=True, ledger_path=ledger_path)
    assert res["old_status"] == "✅ 10-01 fn(old_fn) commit aaa111"
    assert res["new_status"].startswith("✅ ") and anchor in res["new_status"]
    line = open(ledger_path, encoding="utf-8").read().splitlines()[_line_no(A2_LINE) - 1]
    assert "old_fn" not in line and anchor in line
    assert locate_ledger_row("A2", ledger_path)["status_text"] == res["new_status"]


def test_ledger_update_in_progress_prefix_row(ledger_path):
    res = update_ledger("B7", "fn(calib_probe)", ledger_path=ledger_path)
    line = open(ledger_path, encoding="utf-8").read().splitlines()[_line_no(B7_LINE) - 1]
    # 只改第 3 列段：▶ 前缀的编号格原样保留，其余列不动，列数不变。
    assert line.startswith("| ▶ B7 | 功率分辨率 | ✅ ")
    assert line.endswith("| r5 |")
    assert line.count("|") == B7_LINE.count("|")
    assert locate_ledger_row("B7", ledger_path)["status_text"] == res["new_status"]


def test_ledger_update_stats_section_untouched(ledger_path):
    update_ledger("A1", "fn(a1_impl)", ledger_path=ledger_path)
    after = open(ledger_path, encoding="utf-8").read()
    # 「## 统计与说明」节（含「- 共 .* 条」进度行）人工维护——函数只改条目行。
    stats = after.split("## 统计与说明", 1)[1]
    assert "- 共 3 个域、7 条（本节人工维护，update_ledger 不滚动）。" in stats


def test_ledger_update_atomic_failure_keeps_original(ledger_path, monkeypatch):
    before = open(ledger_path, "rb").read()

    def boom(src, dst):
        raise OSError("disk full (simulated)")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(LedgerError) as ei:
        update_ledger("B1", "fn(x2_y2)", ledger_path=ledger_path)
    assert "写回失败" in str(ei.value) and "原子" in str(ei.value)
    assert open(ledger_path, "rb").read() == before  # 原文件不变
    # 残留 tmp 已清理。
    import glob

    assert glob.glob(ledger_path + ".tmp*") == []


def test_ledger_update_anchor_with_pipe_rejected(ledger_path):
    snapshot = open(ledger_path, encoding="utf-8").read()
    with pytest.raises(ValueError) as ei:
        update_ledger("B1", "fn(x) | 注入列", ledger_path=ledger_path)
    assert "管道符" in str(ei.value)
    assert open(ledger_path, encoding="utf-8").read() == snapshot


@pytest.mark.parametrize(
    "bad_anchor",
    ["", "   ", "fn(x)\n第二行", "fn(x)\r第二行", 42, None],
)
def test_ledger_update_malformed_anchors_rejected(ledger_path, bad_anchor):
    with pytest.raises(ValueError):
        update_ledger("B1", bad_anchor, ledger_path=ledger_path)


def test_ledger_update_entry_not_found_or_file_missing(tmp_path, ledger_path):
    with pytest.raises(LedgerError) as ei:  # 零命中（同域提示由 locate 提供）
        update_ledger("B9", "fn(x)", ledger_path=ledger_path)
    assert "B9" in str(ei.value)
    with pytest.raises(LedgerError):  # 文件不存在
        update_ledger("B1", "fn(x)", ledger_path=str(tmp_path / "nope.md"))
    with pytest.raises(ValueError):  # entry_id 形状非法（locate 透传）
        update_ledger("B123", "fn(x)", ledger_path=ledger_path)


def test_ledger_update_row_without_status_column_rejected(tmp_path):
    p = tmp_path / "thin.md"
    p.write_text("| 编号 | 功能 |\n| A1 | 只有描述 |\n", encoding="utf-8")
    with pytest.raises(LedgerError) as ei:
        update_ledger("A1", "fn(x)", ledger_path=str(p))
    assert "状态列缺失" in str(ei.value)
    assert p.read_text(encoding="utf-8") == "| 编号 | 功能 |\n| A1 | 只有描述 |\n"


def test_ledger_update_real_ledger_form_appends_status_column(ledger_path):
    # B17 高#1 复测：真清单形态（表头 4 列无状态列）——动态加列而非覆写第 3 列。
    anchor = "fn(open_b210_backend) commit abc1234"
    res = update_ledger("C1", anchor, ledger_path=ledger_path)
    today = date.today().strftime("%m-%d")
    assert res["old_status"] == ""  # 加列前无状态语义
    assert res["new_status"] == f"✅ {today} {anchor}"
    lines = open(ledger_path, encoding="utf-8").read().splitlines()
    header = lines[_line_no(C_HEADER) - 1]
    sep = lines[_line_no(C_SEP) - 1]
    c1 = lines[_line_no(C1_LINE) - 1]
    c2 = lines[_line_no(C2_LINE) - 1]
    # 表头/分隔行各追加一列；条目行尾追加状态单元——三行改动。
    assert header == C_HEADER + " 完成状态 |"
    assert sep == C_SEP + " --- |"
    assert c1 == C1_LINE + f" ✅ {today} {anchor} |"
    # 描述列零破坏 + 同表未更新行原样（保持 4 列）。
    assert C1_LINE.split("|")[3] in c1  # 技术支持与实现路径列原样完整
    assert c2 == C2_LINE
    # 读回：表头已含「完成状态」→ status 形态，✅ 判定来自新列（含覆盖保护）。
    back = locate_ledger_row("C1", ledger_path)
    assert back["table_form"] == "status" and back["has_done_mark"] is True
    assert back["status_text"] == res["new_status"]
    with pytest.raises(LedgerError) as ei:  # 已 ✅ 未授权不再可写
        update_ledger("C1", "fn(other_fn)", ledger_path=ledger_path)
    assert "未授权覆盖" in str(ei.value)


def test_ledger_update_real_ledger_form_second_row_in_place(ledger_path):
    # 同表第二条：表头已含「完成状态」→ 只在行尾补状态槽，表头/分隔行不再改。
    update_ledger("C1", "fn(a1_b1)", ledger_path=ledger_path)
    after_first = open(ledger_path, encoding="utf-8").read().splitlines()
    today = date.today().strftime("%m-%d")
    res = update_ledger("C2", "fn(a2_b2)", ledger_path=ledger_path)
    after_second = open(ledger_path, encoding="utf-8").read().splitlines()
    assert after_second[_line_no(C_HEADER) - 1] == after_first[_line_no(C_HEADER) - 1]
    assert after_second[_line_no(C_SEP) - 1] == after_first[_line_no(C_SEP) - 1]
    assert after_second[_line_no(C2_LINE) - 1] == C2_LINE + f" ✅ {today} fn(a2_b2) |"
    assert locate_ledger_row("C2", ledger_path)["status_text"] == res["new_status"]


def test_ledger_update_escaped_pipe_description_preserved(ledger_path):
    # B17 中#2 复测：描述列含 \|——改写状态列后转义管道原样保留、列不错位。
    update_ledger("B8", "fn(esc_fn)", ledger_path=ledger_path)  # 有状态列表头
    line = open(ledger_path, encoding="utf-8").read().splitlines()[_line_no(B8_LINE) - 1]
    assert line == B8_LINE.replace(" 待开 ", " ✅ " + date.today().strftime("%m-%d") + " fn(esc_fn) ")
    assert line.count("|") == B8_LINE.count("|")  # \| 不计为列界
    assert line.startswith("| B8 | 频率准确度 \\| 相位噪声 | ✅ ")
    update_ledger("C2", "fn(esc2_fn)", ledger_path=ledger_path)  # 真清单形态（加列路径）
    c2 = open(ledger_path, encoding="utf-8").read().splitlines()[_line_no(C2_LINE) - 1]
    assert "平坦度 \\| 实际注入谱" in c2  # 技术路径列的 \| 原样
    assert c2.count("|") == C2_LINE.count("|") + 1  # 只多出追加的状态列


def test_ledger_update_crlf_line_endings_roundtrip(tmp_path):
    # B17 中#3 复测：CRLF 台账写入往返——行尾字节保持，不混入裸 LF。
    p = tmp_path / "crlf.md"
    p.write_bytes(SAMPLE.replace("\n", "\r\n").encode("utf-8"))
    update_ledger("B1", "fn(crlf_fn)", ledger_path=str(p))
    raw = p.read_bytes().decode("utf-8")
    assert "\r\n" in raw
    assert "\n" not in raw.replace("\r\n", "")  # 无裸 LF 混入
    new_line = raw.split("\r\n")[_line_no(B1_LINE) - 1]
    assert new_line.startswith("| B1 | 连续覆盖 | ✅ ") and new_line.endswith("| r3 |")


def test_ledger_update_anchor_too_long_rejected(ledger_path):
    snapshot = open(ledger_path, encoding="utf-8").read()
    with pytest.raises(ValueError) as ei:  # 低#6：>120 字符拒绝
        update_ledger("B1", "fn(a) " + "x" * 130, ledger_path=ledger_path)
    msg = str(ei.value)
    assert "过长" in msg and "120" in msg
    assert open(ledger_path, encoding="utf-8").read() == snapshot  # 文件未动
    assert update_ledger("B1", "x" * 120, ledger_path=ledger_path)["updated"] is True  # 等长通过


def test_ledger_update_signature_contract():
    sig = inspect.signature(update_ledger)
    assert sig.parameters["ledger_path"].default == "docs/全功能实现清单-技术支持版.md"
    assert sig.parameters["overwrite"].default is False
    for name in ("overwrite", "ledger_path"):
        assert sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
