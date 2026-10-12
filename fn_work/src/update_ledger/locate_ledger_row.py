"""清单条目行定位（结构感知，返回现状）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import re
from typing import Any

DEFAULT_LEDGER_PATH = "docs/全功能实现清单-技术支持版.md"

_ENTRY_ID_RE = re.compile(r"^[A-L]\d{1,2}$")
# 台账行形如 `| B5 | 描述 | 状态 | … |`，含 ▶ 前缀变体 `| ▶ B5 | … |`（A–L 域）。
_DOMAIN_ROW_RE = re.compile(r"^\|\s*(?:▶\s*)?([A-L]\d{1,2})\s*\|")

# '| id | 描述 | 状态列 | …' → split('|') 后取第 4 段（index 3）为状态列。
_STATUS_COLUMN_INDEX = 3


class LedgerError(Exception):
    """台账定位失败：文件缺失 / 零命中（附同域编号提示）/ 多处命中（附各处行号）。"""


def _status_text_of(line: str) -> str:
    """取行内第 3 个管道列（状态列）文本；列不足时返回空串。"""
    parts = line.split("|")
    if len(parts) <= _STATUS_COLUMN_INDEX:
        return ""
    return parts[_STATUS_COLUMN_INDEX].strip()


def locate_ledger_row(entry_id: str, ledger_path: str = DEFAULT_LEDGER_PATH) -> dict[str, Any]:
    """清单条目行定位（结构感知，返回现状）——只定位不改写（纯读）。

    Args:
        entry_id: 条目编号，如 'B5'/'G3'/'L8'（须匹配 ^[A-L]\\d{1,2}$）。
        ledger_path: 台账 md 路径，默认相对仓库根的真实清单。

    Returns:
        {'line_no': 1-based 行号, 'line': 行原文, 'status_text': 状态列文本,
         'has_done_mark': 状态列含 ✅ 或 'wired', 'in_progress': ▶ 前缀行或状态列含 ▶/进行中}

    Raises:
        ValueError: entry_id 形状非法（空/非 str/不匹配 ^[A-L]\\d{1,2}$）。
        LedgerError: 文件不存在 / 零命中（附同字母域现有编号提示）/ 多处命中（附各处行号）。
    """
    if not isinstance(entry_id, str):
        raise ValueError(f"entry_id 必须为 str，实际收到 {type(entry_id).__name__}: {entry_id!r}")
    if not _ENTRY_ID_RE.match(entry_id):
        raise ValueError(f"entry_id 形状非法（须匹配 ^[A-L]\\d{{1,2}}$，如 'B5'/'G3'/'L8'）: {entry_id!r}")

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
        first_cell = line.split("|")[1] if "|" in line else ""
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
    status_text = _status_text_of(line)
    return {
        "line_no": line_no,
        "line": line,
        "status_text": status_text,
        "has_done_mark": ("✅" in status_text) or ("wired" in status_text.lower()),
        "in_progress": prefix_mark or ("▶" in status_text) or ("进行中" in status_text),
    }
