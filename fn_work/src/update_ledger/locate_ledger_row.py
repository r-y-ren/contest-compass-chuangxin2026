"""清单条目行定位（结构感知，返回现状）——重写规约与签名意图详见 fn_docs/responsibility.md。

列语义自适应（B17 高#1）：条目行向上找最近表头行（表头＝紧邻分隔行的管道行）——
表头含「状态」列 → 状态列取该列（table_form='status'）；表头无状态列（真清单
4 列形态 `| 编号 | 功能要求 | 技术支持与实现路径 | 分期 |`）→ 'append' 形态：
状态语义恒空（描述列绝不被误读为状态），由 update_ledger 动态补「完成状态」列；
无表头（畸形/无表头样板）→ 'legacy' 兜底：第 3 管道列旧口径。补列后表头含
「完成状态」→ 自动回到 'status' 形态，✅ 判定来自新列（完成状态列含 ✅）。
列解析 Markdown 感知（B17 中#2）：\\| 转义管道先占位再切分，描述列含 \\| 不再错列。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

#: 默认台账路径：锚定仓库根（本文件 fn_work/src/update_ledger/locate_ledger_row.py
#: 的 parents[3] 即仓库根）——与 run_demo.DEFAULT_LEDGER_PATH 同式，从 fn_work、
#: 仓库根或任意其他 cwd 调用都指向同一份清单（修复前 'docs/…' 为 cwd 相对路径，
#: 离开仓库根即 LedgerError「台账文件不存在」）。运行时以本模块全局名为解析
#: 来源（ledger_path=None 哨兵动态回落），测试可 monkeypatch 指向 tmp 副本。
DEFAULT_LEDGER_PATH = str(
    Path(__file__).resolve().parents[3] / "docs" / "全功能实现清单-技术支持版.md"
)

_ENTRY_ID_RE = re.compile(r"^[A-L]\d{1,2}$")
# 台账行形如 `| B5 | 描述 | 状态 | … |`，含 ▶ 前缀变体 `| ▶ B5 | … |`（A–L 域）。
_DOMAIN_ROW_RE = re.compile(r"^\|\s*(?:▶\s*)?([A-L]\d{1,2})\s*\|")

# 无表头（legacy）兜底口径：split 后取第 4 段（index 3）为状态列。
_STATUS_COLUMN_INDEX = 3
# 表头列名含此字样即状态列（兼容「状态」/「完成状态」/「当前状态」等；补列后
# 表头自动落回 status 形态）。状态列不可能早于第 2 管道列（前两列为编号+描述）。
_STATUS_HEADER_MARK = "状态"
_MIN_HEADER_STATUS_COL = 2

# Markdown 转义管道占位符（\x00 在台账正文中不会出现）——切列前先占位、
# 回拼/取文本后还原为字面 `\|`，保证描述列含 \| 时列不错位（中#2）。
_PIPE_PLACEHOLDER = "\x00"
_ESCAPED_PIPE = "\\|"

# 分隔行单元格：`:---`/`---`/`---:`/`:-:`（至少一横，可选冒号与空白）。
_SEP_CELL_RE = re.compile(r"^:?-+:?$")


def _split_md_cells(line: str) -> list[str]:
    """Markdown 感知列切分：`\|`（转义管道）先占位再按 '|' 切分。

    返回的各段仍含占位符——改写单元格后须以 _join_md_cells 回拼还原。
    """
    return line.replace(_ESCAPED_PIPE, _PIPE_PLACEHOLDER).split("|")


def _join_md_cells(parts: list[str]) -> str:
    """按 '|' 回拼各段并还原转义管道（与 _split_md_cells 互逆）。"""
    return "|".join(parts).replace(_PIPE_PLACEHOLDER, _ESCAPED_PIPE)


def _restore_cell(text: str) -> str:
    """单元格文本还原转义管道（供对外展示的状态列文本）。"""
    return text.replace(_PIPE_PLACEHOLDER, _ESCAPED_PIPE)


def _is_separator_row(line: str) -> bool:
    """Markdown 表格分隔行判定：管道行且全部内容单元为 `:---` 形横线。"""
    if not line.startswith("|"):
        return False
    cells = [c.strip() for c in _split_md_cells(line)]
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return bool(cells) and all(_SEP_CELL_RE.match(c) is not None for c in cells)


def _status_column_of_header(header_line: str) -> int | None:
    """表头行中状态列的管道列索引；无「状态」字样列（真清单形态）→ None。"""
    cells = _split_md_cells(header_line)
    for idx, cell in enumerate(cells):
        if idx >= _MIN_HEADER_STATUS_COL and _STATUS_HEADER_MARK in cell.strip():
            return idx
    return None


def _find_header_index(lines: list[str], entry_idx: int) -> int | None:
    """条目行向上最近的表头行（0 基索引）；无表头 → None。

    自条目行向上走：途经行均为管道行；首个分隔行的上一行即表头（表头自身
    须为管道行且非分隔行）。先遇非管道行（空行/正文）或文件顶 → 无表头。
    """
    j = entry_idx - 1
    while j >= 1:
        line = lines[j]
        if not line.startswith("|"):
            return None
        if (
            _is_separator_row(line)
            and lines[j - 1].startswith("|")
            and not _is_separator_row(lines[j - 1])
        ):
            return j - 1
        j -= 1
    return None


def _status_text_at(line: str, col_index: int | None) -> str:
    """取行内第 col_index 管道列文本（还原转义管道）；列不足/无列 → 空串。"""
    if col_index is None or col_index < 0:
        return ""
    parts = _split_md_cells(line)
    if len(parts) <= col_index:
        return ""
    return _restore_cell(parts[col_index].strip())


class LedgerError(Exception):
    """台账定位失败：文件缺失 / 零命中（附同域编号提示）/ 多处命中（附各处行号）。"""


def locate_ledger_row(entry_id: str, ledger_path: str | None = None) -> dict[str, Any]:
    """清单条目行定位（结构感知，返回现状）——只定位不改写（纯读）。

    Args:
        entry_id: 条目编号，如 'B5'/'G3'/'L8'（须匹配 ^[A-L]\\d{1,2}$）。
        ledger_path: 台账 md 路径；None（缺省）→ 调用时回落模块全局
            DEFAULT_LEDGER_PATH（仓库根锚定，与运行 cwd 无关）。

    Returns:
        {'line_no': 1-based 行号, 'line': 行原文, 'status_text': 状态列文本,
         'has_done_mark': 状态列含 ✅ 或 'wired', 'in_progress': ▶ 前缀行或
         状态列含 ▶/进行中, 'table_form': 'status'|'append'|'legacy',
         'status_col_index': 状态列管道列索引（append 形态为 None）,
         'header_line_no': 所在表表头 1-based 行号（无表头为 None）,
         'header_line': 表头行原文（无表头为 None）}
        列语义自适应：表头含「状态」列 → status 形态取该列；表头无状态列
        （真清单 4 列形态）→ append 形态（状态文本恒空——描述列不被误读）；
        无表头 → legacy 形态兜底第 3 管道列。

    Raises:
        ValueError: entry_id 形状非法（空/非 str/不匹配 ^[A-L]\\d{1,2}$）。
        LedgerError: 文件不存在 / 零命中（附同字母域现有编号提示）/ 多处命中（附各处行号）。
    """
    if not isinstance(entry_id, str):
        raise ValueError(f"entry_id 必须为 str，实际收到 {type(entry_id).__name__}: {entry_id!r}")
    if not _ENTRY_ID_RE.match(entry_id):
        raise ValueError(f"entry_id 形状非法（须匹配 ^[A-L]\\d{{1,2}}$，如 'B5'/'G3'/'L8'）: {entry_id!r}")
    if ledger_path is None:  # 动态回落模块全局（monkeypatch 友好；绝对锚定与 cwd 无关）
        ledger_path = DEFAULT_LEDGER_PATH

    try:
        with open(ledger_path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        raise LedgerError(f"台账文件不存在或不可读: {ledger_path}（{exc}）") from exc

    # 精确边界：`| B1 |` 不得命中 `| B10 |`——id 后必须紧跟可选空白再接 `|`。
    row_re = re.compile(r"^\|\s*(?:▶\s*)?" + re.escape(entry_id) + r"\s*\|")

    hits: list[tuple[int, str, bool]] = []  # (1-based 行号, 行原文, 是否 ▶ 前缀行)
    domain_ids: list[str] = []  # 同字母域现有编号（零命中提示用）
    for line_no, line in enumerate(lines, start=1):
        m = _DOMAIN_ROW_RE.match(line)
        if m is None:
            continue
        found_id = m.group(1)
        if found_id[0] == entry_id[0] and found_id not in domain_ids:
            domain_ids.append(found_id)
        if found_id != entry_id:
            continue
        first_cell = _split_md_cells(line)[1] if "|" in line else ""
        prefix_mark = first_cell.strip().startswith("▶")
        hits.append((line_no, line, prefix_mark))

    if len(hits) > 1:
        where = "、".join(str(no) for no, _, _ in hits)
        raise LedgerError(
            f"条目 {entry_id} 在台账中多处命中（第 {where} 行），拒绝定位以防歧义: {ledger_path}"
        )
    if not hits:
        if domain_ids:
            hint = "、".join(sorted(domain_ids, key=lambda x: int(x[1:])))
        else:
            hint = "（该字母域当前无任何条目）"
        raise LedgerError(
            f"未在台账中找到条目 {entry_id}；同字母域（{entry_id[0]}）现有编号: {hint} —— 请核对编号是否笔误: {ledger_path}"
        )

    line_no, line, prefix_mark = hits[0]

    # ---- 列语义自适应：表头检测 → 状态列归属 ----
    header_idx = _find_header_index(lines, line_no - 1)
    if header_idx is None:
        table_form, status_col, header_line_no = "legacy", _STATUS_COLUMN_INDEX, None
        header_line = None
    else:
        header_line = lines[header_idx]
        header_line_no = header_idx + 1
        status_col = _status_column_of_header(header_line)
        if status_col is None:
            table_form = "append"  # 真清单形态：无状态列（状态文本恒空）
        else:
            table_form = "status"

    status_text = "" if table_form == "append" else _status_text_at(line, status_col)
    return {
        "line_no": line_no,
        "line": line,
        "status_text": status_text,
        "has_done_mark": ("✅" in status_text) or ("wired" in status_text.lower()),
        "in_progress": prefix_mark or ("▶" in status_text) or ("进行中" in status_text),
        "table_form": table_form,
        "status_col_index": status_col,
        "header_line_no": header_line_no,
        "header_line": header_line,
    }
