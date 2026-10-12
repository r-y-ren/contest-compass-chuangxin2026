"""update_ledger 对抗测试：✅+日期+锚点写入/覆盖授权/▶ 行/原子性/统计节不动。"""
from __future__ import annotations

import inspect
from datetime import date

import pytest

from src.update_ledger.locate_ledger_row import locate_ledger_row
from src.update_ledger.update_ledger import update_ledger
from src.update_ledger.update_ledger import LedgerError

# 样板：含已完成（A2）/未完成（A1、B1）/▶ 前缀（B7）行 + 人工维护统计节。
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

## 统计与说明

- 共 2 个域、4 条（本节人工维护，update_ledger 不滚动）。
"""

B1_LINE = "| B1 | 连续覆盖 | 待开 | r3 |"
B7_LINE = "| ▶ B7 | 功率分辨率 | 标定排队 | r5 |"
A2_LINE = "| A2 | 测评体系 | ✅ 10-01 fn(old_fn) commit aaa111 | r2 |"


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
    assert "- 共 2 个域、4 条（本节人工维护，update_ledger 不滚动）。" in stats


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


def test_ledger_update_signature_contract():
    sig = inspect.signature(update_ledger)
    assert sig.parameters["ledger_path"].default == "docs/全功能实现清单-技术支持版.md"
    assert sig.parameters["overwrite"].default is False
    for name in ("overwrite", "ledger_path"):
        assert sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
