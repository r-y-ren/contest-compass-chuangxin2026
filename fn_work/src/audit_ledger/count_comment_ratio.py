"""代码注释率统计（≥20% 结题口径）——重写规约与签名意图详见 fn_docs/responsibility.md。

统计口径（结题审计对照）：
- 全库口径：tests/ 一并计入（不排除）；仅排除 __pycache__/.git 生成物目录与第三方
  目录（路径段为 site-packages/venv/.venv 时整棵跳过）。
- 分母 = 非空物理行（strip 后非空的行；空行不计分母）。
- 分子 = # 行注释行（tokenize 的 COMMENT token，含行尾注释）+ docstring 行。
- docstring 简化判定：STRING token 起始于所在行首个非空白字符（行首 strip 后为
  引号或字符串前缀开头）即视为独立成行字符串，其跨占的非空物理行计入
  docstring_lines；行中字符串（如赋值右侧 'x'）不计。括号续行首列的字符串按
  此简化会误计，属已知可接受偏差。
- 二进制/坏 utf-8/不可 tokenize 的文件跳过不计数（不计入 n_files）。
"""
from __future__ import annotations

import io
import os
import re
import tokenize

__all__ = ["count_comment_ratio"]

#: 目录名黑名单：__pycache__/.git（生成物）+ 第三方（site-packages/venv/.venv）。
#: 注意不排除 tests——全库口径（tests 里的注释也是注释）。
_SKIPPED_DIRS = frozenset({"__pycache__", ".git", "site-packages", "venv", ".venv"})

#: 独立成行字符串的行首形态：可选字符串前缀（r/b/u/f 组合，≤3 字符）+ 引号。
_STANDALONE_STR_RE = re.compile(r"""^(?:[rRbBuUfF]{1,3})?['"]""")

#: worst_files 入围门槛与条数：仅 total>50 行的文件入围，取 ratio 最低前 5。
_WORST_MIN_LINES = 50
_WORST_LIMIT = 5


def _count_file(path: str) -> tuple[int, int, int] | None:
    """统计单文件 → (非空总行, #注释行, docstring 行)。

    读取失败（二进制/坏 utf-8）或 tokenize 失败（语法坏文件）→ None（调用方跳过）。
    """
    try:
        with tokenize.open(path) as fh:
            source = fh.read()
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (OSError, ValueError, SyntaxError, tokenize.TokenError):
        # UnicodeDecodeError ⊂ ValueError；IndentationError ⊂ SyntaxError。
        return None
    lines = source.splitlines()
    # 非空物理行行号集合（1 基）：分母，并用于 docstring 跨行时空行不计数。
    nonempty = {i for i, ln in enumerate(lines, start=1) if ln.strip()}
    comment = 0
    docstring = 0
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            comment += 1
        elif tok.type == tokenize.STRING:
            first_line = tok.line.split("\n", 1)[0] if tok.line else ""
            indent = len(first_line) - len(first_line.lstrip())
            standalone = (
                tok.start[1] == indent
                and bool(_STANDALONE_STR_RE.match(first_line.lstrip()))
            )
            if standalone:
                docstring += sum(
                    1
                    for row in range(tok.start[0], tok.end[0] + 1)
                    if row in nonempty
                )
    return len(nonempty), comment, docstring


def count_comment_ratio(code_root: str) -> dict:
    """代码注释率统计（≥20% 结题口径）。

    输入: code_root 源码树根目录 / 输出: {'total_lines'（非空物理行）,
    'comment_lines'（#+docstring）, 'docstring_lines', 'ratio'（total 0→None）,
    'worst_files'（total>50 行中 ratio 最低前 5，含相对路径）, 'n_files'} /
    错误: code_root 不存在或非目录→ValueError。
    """
    if not os.path.isdir(code_root):
        raise ValueError(f"code_root 不存在或不是目录: {code_root!r}")
    total_lines = 0
    comment_lines = 0
    docstring_lines = 0
    n_files = 0
    per_file: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(code_root):
        # 原地剪枝：黑名单目录整棵不进（含其下全部 .py）。
        dirnames[:] = [d for d in dirnames if d not in _SKIPPED_DIRS]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            counted = _count_file(path)
            if counted is None:
                continue
            total, comment, doc = counted
            file_comment = comment + doc
            n_files += 1
            total_lines += total
            comment_lines += file_comment
            docstring_lines += doc
            per_file.append(
                {
                    "path": os.path.relpath(path, code_root).replace(os.sep, "/"),
                    "total": total,
                    "comment": file_comment,
                    "ratio": file_comment / total if total else None,
                }
            )
    ratio = comment_lines / total_lines if total_lines else None
    worst_files = sorted(
        (e for e in per_file if e["total"] > _WORST_MIN_LINES),
        key=lambda e: e["ratio"],
    )[:_WORST_LIMIT]
    return {
        "total_lines": total_lines,
        "comment_lines": comment_lines,
        "docstring_lines": docstring_lines,
        "ratio": ratio,
        "worst_files": worst_files,
        "n_files": n_files,
    }
