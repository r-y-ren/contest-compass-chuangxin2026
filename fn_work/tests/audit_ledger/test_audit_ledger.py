"""audit_ledger 对抗测试：✅锚点核验/false_negative/注释率差距/真清单冒烟。"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.audit_ledger.audit_ledger import COMMENT_RATIO_TARGET, audit_ledger
from src.update_ledger.locate_ledger_row import LedgerError

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LEDGER = REPO_ROOT / "docs" / "全功能实现清单-技术支持版.md"
REAL_CODE_ROOT = REPO_ROOT / "fn_work"

# 10 非空行、3 行注释 → ratio 0.3（可控的注释率语义断言用）。
_KNOWN_RATIO_PY = "\n".join(
    ["# c1", "# c2", "# c3", "x = 1", "y = 2", "z = 3", "w = 4", "v = 5", "u = 6", "t = 7"]
) + "\n"


def _make_code_root(tmp_path: Path) -> str:
    """样板代码树：locate_ledger_row 以内容命中；count_comment_ratio 以文件名命中。"""
    pkg = tmp_path / "src"
    pkg.mkdir()
    (pkg / "ledger_core.py").write_text(
        "# 注释行\ndef locate_ledger_row(entry_id, ledger_path):\n    return {}\n",
        encoding="utf-8",
    )
    (pkg / "count_comment_ratio.py").write_text("def count_comment_ratio(root):\n    return {}\n", encoding="utf-8")
    return str(tmp_path)


def _write_ledger(tmp_path: Path, text: str) -> str:
    p = tmp_path / "ledger.md"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_ledger_audit_clean_report(tmp_path):
    ledger = _write_ledger(
        tmp_path,
        """# 台账样板
| 编号 | 功能 | 状态 | 备注 |
| --- | --- | --- | --- |
| A1 | 定位 | ✅ 10-11 fn(locate_ledger_row) commit 111aaa | r1 |
| A2 | 注释率 | ✅ 10-11 fn(count_comment_ratio) | r2 |
| A3 | 未完成 | 待开 | r3 |
""",
    )
    code_root = _make_code_root(tmp_path)
    res = audit_ledger(ledger, code_root)
    assert res["total_entries"] == 3
    assert res["done_entries"] == 2
    assert res["issues"] == []
    assert res["clean"] is True
    cr = res["comment_ratio"]
    assert cr["target"] == COMMENT_RATIO_TARGET == 0.20
    assert cr["gap"] == round(COMMENT_RATIO_TARGET - cr["ratio"], 4)
    assert cr["meets_target"] == (cr["ratio"] >= COMMENT_RATIO_TARGET)


def test_ledger_audit_dead_anchor_fn_form(tmp_path):
    ledger = _write_ledger(
        tmp_path,
        """| 编号 | 功能 | 状态 | 备注 |
| B1 | 幽灵 | ✅ 10-11 fn(ghost_fn) commit abc1234 | r |
| B2 | 正常 | ✅ 10-11 fn(locate_ledger_row) | r |
""",
    )
    code_root = _make_code_root(tmp_path)
    res = audit_ledger(ledger, code_root)
    assert res["total_entries"] == 2 and res["done_entries"] == 2
    assert res["clean"] is False
    (issue,) = res["issues"]
    assert issue["entry_id"] == "B1" and issue["kind"] == "dead_anchor"
    assert "ghost_fn" in issue["detail"]


def test_ledger_audit_dead_anchor_bare_token(tmp_path):
    ledger = _write_ledger(
        tmp_path,
        """| 编号 | 功能 | 状态 | 备注 |
| B1 | 裸名缺失 | ✅ 10-11 missing_func_tok 已联动 | r |
| B2 | 裸名存在 | ✅ 10-11 locate_ledger_row 已联动 | r |
""",
    )
    code_root = _make_code_root(tmp_path)
    res = audit_ledger(ledger, code_root)
    (issue,) = res["issues"]
    assert issue["entry_id"] == "B1" and issue["kind"] == "dead_anchor"
    assert "missing_func_tok" in issue["detail"]


def test_ledger_audit_anchor_without_names_flagged(tmp_path):
    ledger = _write_ledger(
        tmp_path,
        "| B1 | 无锚 | ✅ 10-11 done commit abc1234 | r |\n",
    )
    res = audit_ledger(ledger, _make_code_root(tmp_path))
    (issue,) = res["issues"]
    assert issue["kind"] == "dead_anchor" and "可核验函数名" in issue["detail"]


def test_ledger_audit_false_negative_in_progress_conflict(tmp_path):
    # ▶ 前缀行 + 状态列 ✅（锚点本身有效，隔离 false_negative 形态）。
    ledger = _write_ledger(
        tmp_path,
        """| 编号 | 功能 | 状态 | 备注 |
| ▶ B2 | 冲突 | ✅ 10-11 fn(locate_ledger_row) | r |
""",
    )
    res = audit_ledger(ledger, _make_code_root(tmp_path))
    (issue,) = res["issues"]
    assert issue["entry_id"] == "B2" and issue["kind"] == "false_negative"
    assert "进行中" in issue["detail"]


def test_ledger_audit_false_negative_leaked_mark(tmp_path):
    # ✅ 泄漏到描述列，状态列自身无 ✅ → 未完成条目却带完成痕迹。
    ledger = _write_ledger(
        tmp_path,
        "| B3 | ✅ 已完成（描述列误标） | 待复核 | r |\n",
    )
    res = audit_ledger(ledger, _make_code_root(tmp_path))
    (issue,) = res["issues"]
    assert issue["entry_id"] == "B3" and issue["kind"] == "false_negative"
    assert "状态列之外" in issue["detail"]


def test_ledger_audit_wired_counts_done_and_anchor_verified(tmp_path):
    # B17 中#5 复测：done 判定同源 has_done_mark——wired 行纳入 done+锚点核验。
    ledger = _write_ledger(
        tmp_path,
        """| 编号 | 功能 | 状态 | 备注 |
| B1 | wired 联动 | wired fn(locate_ledger_row) commit 111aaa | r1 |
| B2 | 未完成 | 待开 | r2 |
""",
    )
    res = audit_ledger(ledger, _make_code_root(tmp_path))
    assert res["done_entries"] == 1  # wired 行计入 done（修复前只认 ✅ 漏统）
    assert res["issues"] == [] and res["clean"] is True  # 锚点核验通过


def test_ledger_audit_wired_dead_anchor_flagged(tmp_path):
    ledger = _write_ledger(
        tmp_path, "| B1 | wired 幽灵 | wired fn(ghost_fn) | r |\n"
    )
    res = audit_ledger(ledger, _make_code_root(tmp_path))
    assert res["done_entries"] == 1
    (issue,) = res["issues"]
    assert issue["entry_id"] == "B1" and issue["kind"] == "dead_anchor"
    assert "ghost_fn" in issue["detail"]


def test_ledger_audit_wired_without_names_flagged(tmp_path):
    # wired-only 且锚点正文不含可核验函数名 → dead_anchor（口径与 ✅ 行一致）。
    ledger = _write_ledger(tmp_path, "| B1 | wired 无锚 | wired：骨架已联动 | r |\n")
    res = audit_ledger(ledger, _make_code_root(tmp_path))
    (issue,) = res["issues"]
    assert issue["kind"] == "dead_anchor" and "可核验函数名" in issue["detail"]


def test_ledger_audit_ambiguous_duplicate_entry(tmp_path):
    ledger = _write_ledger(
        tmp_path,
        "| B1 | 甲 | 待开 | r |\n| B1 | 乙 | 待开 | r |\n",
    )
    res = audit_ledger(ledger, _make_code_root(tmp_path))
    assert res["clean"] is False
    (issue,) = res["issues"]
    assert issue["entry_id"] == "B1" and issue["kind"] == "ambiguous"


def test_ledger_audit_empty_ledger(tmp_path):
    ledger = _write_ledger(tmp_path, "# 空台账\n\n只有说明文字，无条目行。\n")
    code_root = _make_code_root(tmp_path)
    res = audit_ledger(ledger, code_root)
    assert res["total_entries"] == 0 and res["done_entries"] == 0
    assert res["issues"] == [] and res["clean"] is True
    assert res["comment_ratio"]["n_files"] == 2  # 注释率照算（代码树无关条目）


def test_ledger_audit_missing_file_rejected(tmp_path):
    with pytest.raises(LedgerError) as ei:
        audit_ledger(str(tmp_path / "nope.md"), _make_code_root(tmp_path))
    assert "nope.md" in str(ei.value)


def test_ledger_audit_comment_ratio_gap_semantics(tmp_path):
    ledger = _write_ledger(tmp_path, "| A1 | 未完成 | 待开 | r |\n")
    root = tmp_path / "code"
    root.mkdir()
    (root / "known.py").write_text(_KNOWN_RATIO_PY, encoding="utf-8")
    res = audit_ledger(ledger, str(root))
    cr = res["comment_ratio"]
    assert cr["total_lines"] == 10 and cr["comment_lines"] == 3
    assert cr["ratio"] == pytest.approx(0.3)
    assert cr["target"] == 0.20
    assert cr["gap"] == pytest.approx(-0.1)  # 超额为负（gap = target - ratio）
    assert cr["meets_target"] is True  # ≥20% 结题口径达标


def test_ledger_audit_empty_code_root_ratio_none(tmp_path):
    ledger = _write_ledger(
        tmp_path, "| A1 | 未完成 | 待开 | r |\n"
    )
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    res = audit_ledger(ledger, str(empty_root))
    cr = res["comment_ratio"]
    assert cr["total_lines"] == 0 and cr["ratio"] is None
    assert cr["gap"] is None and cr["meets_target"] is None
    assert res["clean"] is True


def test_ledger_audit_real_ledger_and_fn_work_smoke():
    # 真清单 + 真 fn_work：结果如实（当前清单 100 条全未 ✅ → clean；后续进位后
    # issues 如实上抛，本用例只锁结构不变量，不粉饰差异）。
    assert REAL_LEDGER.exists() and REAL_CODE_ROOT.is_dir()
    res = audit_ledger(str(REAL_LEDGER), str(REAL_CODE_ROOT))
    assert res["total_entries"] == 100  # 12 域 100 条（与清单自述一致）
    assert isinstance(res["done_entries"], int) and res["done_entries"] >= 0
    assert res["done_entries"] <= res["total_entries"]
    for issue in res["issues"]:
        assert set(issue) == {"entry_id", "kind", "detail"}
        assert issue["kind"] in {"dead_anchor", "false_negative", "ambiguous"}
    assert res["clean"] == (not res["issues"])
    cr = res["comment_ratio"]
    assert cr["n_files"] > 100  # 真代码树 300+ py 文件入统
    assert isinstance(cr["ratio"], float) and cr["ratio"] > 0
    assert cr["gap"] == round(COMMENT_RATIO_TARGET - cr["ratio"], 4)
