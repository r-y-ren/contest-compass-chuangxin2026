"""count_comment_ratio 对抗单测：口径（非空行分母/#+docstring 分子）与目录剪枝。"""
from pathlib import Path

import pytest

from src.audit_ledger.count_comment_ratio import count_comment_ratio


def _write(root: Path, rel: str, content: str) -> Path:
    """在 tmp 树写文本文件并返回路径（自动建父目录）。"""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_pure_comment_file_ratio_one(tmp_path):
    _write(tmp_path, "only_comments.py", "# a\n# b\n# c\n")
    report = count_comment_ratio(str(tmp_path))
    assert report["n_files"] == 1
    assert report["total_lines"] == 3
    assert report["comment_lines"] == 3
    assert report["docstring_lines"] == 0
    assert report["ratio"] == 1.0


def test_no_comments_ratio_zero(tmp_path):
    _write(tmp_path, "plain.py", "x = 1\ny = x + 2\nz = y * 3\n")
    report = count_comment_ratio(str(tmp_path))
    assert report["comment_lines"] == 0
    assert report["docstring_lines"] == 0
    assert report["total_lines"] == 3
    assert report["ratio"] == 0.0


def test_docstrings_counted(tmp_path):
    # 模块 docstring 1 行 + 函数 docstring 跨 3 行；def/return 为普通代码行。
    _write(
        tmp_path,
        "d.py",
        "'''Module doc.'''\n"
        "def f():\n"
        "    '''Fn doc\n"
        "    spanning.\n"
        "    '''\n"
        "    return 1\n",
    )
    report = count_comment_ratio(str(tmp_path))
    assert report["docstring_lines"] == 4
    assert report["comment_lines"] == 4  # # 注释 0 + docstring 4
    assert report["total_lines"] == 6
    assert report["ratio"] == pytest.approx(4 / 6)


def test_rhs_string_literal_not_docstring(tmp_path):
    # 赋值右侧字符串（行首判定不满足）不计 docstring。
    _write(tmp_path, "rhs.py", "x = 'rhs'\ny = \"b\"\nz = x + 1\n")
    report = count_comment_ratio(str(tmp_path))
    assert report["docstring_lines"] == 0
    assert report["comment_lines"] == 0
    assert report["ratio"] == 0.0


def test_blank_lines_excluded_from_denominator(tmp_path):
    _write(tmp_path, "blanks.py", "x = 1\n\n\n# c\n\ny = 2\n")
    report = count_comment_ratio(str(tmp_path))
    assert report["total_lines"] == 3  # 两处空行不计分母
    assert report["comment_lines"] == 1
    assert report["ratio"] == pytest.approx(1 / 3)


def test_inline_comment_counts(tmp_path):
    _write(tmp_path, "inline.py", "x = 1  # note\ny = 2\n")
    report = count_comment_ratio(str(tmp_path))
    assert report["comment_lines"] == 1
    assert report["total_lines"] == 2


def test_nested_directories_aggregate(tmp_path):
    _write(tmp_path, "a.py", "x = 1\n# c1\n")
    _write(tmp_path, "sub/deep/c.py", "# c2\n# c3\n")
    report = count_comment_ratio(str(tmp_path))
    assert report["n_files"] == 2
    assert report["total_lines"] == 4
    assert report["comment_lines"] == 3
    assert report["ratio"] == pytest.approx(3 / 4)


def test_generated_and_thirdparty_dirs_skipped(tmp_path):
    _write(tmp_path, "keep.py", "# k\nx = 1\n")
    for rel in (
        "__pycache__/s1.py",
        ".git/s2.py",
        "venv/s3.py",
        ".venv/s4.py",
        "site-packages/s5.py",
        "pkg/site-packages/s6.py",
    ):
        _write(tmp_path, rel, "# skipped\n" * 5)
    report = count_comment_ratio(str(tmp_path))
    assert report["n_files"] == 1
    assert report["total_lines"] == 2
    assert report["comment_lines"] == 1


def test_bad_utf8_file_skipped(tmp_path):
    # 坏 utf-8 二进制文件：跳过不炸，不影响好文件统计。
    bad = tmp_path / "bad.py"
    bad.write_bytes(b"\x80\x81\x82 garbage\n# not counted\n")
    _write(tmp_path, "ok.py", "# c\nx = 1\n")
    report = count_comment_ratio(str(tmp_path))
    assert report["n_files"] == 1
    assert report["total_lines"] == 2
    assert report["comment_lines"] == 1
    assert report["ratio"] == pytest.approx(0.5)


def test_empty_tree_ratio_none(tmp_path):
    report = count_comment_ratio(str(tmp_path))
    assert set(report) == {
        "total_lines",
        "comment_lines",
        "docstring_lines",
        "ratio",
        "worst_files",
        "n_files",
    }
    assert report["n_files"] == 0
    assert report["total_lines"] == 0
    assert report["comment_lines"] == 0
    assert report["ratio"] is None
    assert report["worst_files"] == []


def test_blank_only_file_zero_total(tmp_path):
    _write(tmp_path, "blank.py", "\n\n   \n\t\n\n")
    report = count_comment_ratio(str(tmp_path))
    assert report["n_files"] == 1
    assert report["total_lines"] == 0
    assert report["ratio"] is None  # 无可统计行→None 而非除零


def test_worst_files_lowest_ratio_big_files(tmp_path):
    # 三个 >50 行文件比率各异 + 一个 ≤50 行零注释文件（不得入围）。
    def big(name: str, n_comments: int) -> None:
        lines = [f"x{i} = {i}" for i in range(60)]
        lines += [f"# c{i}" for i in range(n_comments)]
        _write(tmp_path, name, "\n".join(lines) + "\n")

    big("big_low.py", 0)
    big("big_mid.py", 6)
    big("big_high.py", 30)
    _write(tmp_path, "small_zero.py", "a = 1\n" * 10)

    report = count_comment_ratio(str(tmp_path))
    worst = report["worst_files"]
    assert [e["path"] for e in worst] == ["big_low.py", "big_mid.py", "big_high.py"]
    assert all(set(e) == {"path", "total", "comment", "ratio"} for e in worst)
    assert worst[0]["ratio"] == 0.0
    assert worst[1]["ratio"] == pytest.approx(6 / 66)
    assert worst[2]["ratio"] == pytest.approx(30 / 90)
    assert all(e["total"] > 50 for e in worst)
    assert all(e["path"] != "small_zero.py" for e in worst)
    assert len(worst) <= 5


def test_real_fn_work_src_smoke():
    src_root = Path(__file__).resolve().parents[2] / "src"
    report = count_comment_ratio(str(src_root))
    assert report["n_files"] > 50
    assert report["ratio"] is not None and report["ratio"] > 0
    assert report["docstring_lines"] > 0
    assert len(report["worst_files"]) <= 5


def test_missing_root_raises_valueerror(tmp_path):
    with pytest.raises(ValueError, match="code_root"):
        count_comment_ratio(str(tmp_path / "no_such_dir"))
