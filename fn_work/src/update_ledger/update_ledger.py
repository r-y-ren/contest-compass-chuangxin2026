"""清单台账更新：✅+日期+锚点写入——重写规约与签名意图详见 fn_docs/responsibility.md。

统计节滚动申报简化：本函数只改条目行（第 3 管道列＝状态列），文件尾部
「## 统计与说明」节（含「- 共 .* 函数/条」进度行）为人工维护、不自动滚动——
TODO(manual)：统计节滚动归人工/结题轮，自检一致性核对归 audit_ledger（R51）。
"""
from __future__ import annotations

import os
from datetime import date

from .locate_ledger_row import LedgerError, locate_ledger_row

__all__ = ["update_ledger"]

# split('|') 第 4 段（第 3 内容列）＝状态列——与 locate_ledger_row 同口径。
_STATUS_COLUMN_INDEX = 3
# 状态列原位替换要求行至少含 3 个真实内容列（split('|') ≥ 5 段：
# ['', ' id ', ' 描述 ', ' 状态 ', ...]），否则视为状态列缺失拒绝改写。
_MIN_PARTS_FOR_STATUS = _STATUS_COLUMN_INDEX + 2


def _build_status(anchor: str) -> str:
    """构造新状态列文本：`✅ MM-DD <anchor>`（月-日 + 实现锚点，单行内）。"""
    return f"✅ {date.today().strftime('%m-%d')} {anchor}"


def _replace_status_column(line: str, new_status: str) -> str:
    """行内替换第 3 内容列（状态列），保持列数与其余列原文不变。

    列数不足（无第 3 内容列的畸形行）→ LedgerError 拒绝（不得借机增列）。
    """
    parts = line.split("|")
    if len(parts) < _MIN_PARTS_FOR_STATUS:
        raise LedgerError(
            f"条目行状态列缺失（第 3 管道列），无法原位替换（列数不足）: {line!r}"
        )
    parts[_STATUS_COLUMN_INDEX] = f" {new_status} "
    return "|".join(parts)


def _atomic_write(ledger_path: str, text: str) -> None:
    """原子写回：先写同目录 tmp 文件再 os.replace 换入——任何一步失败，原文件不动。"""
    tmp = ledger_path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, ledger_path)
    except OSError as exc:
        try:
            os.unlink(tmp)  # 残留 tmp 清理（清理失败不掩盖原错误）
        except OSError:
            pass
        raise LedgerError(f"台账写回失败（原子写保护，原文件未动）: {ledger_path}（{exc}）") from exc


def update_ledger(
    entry_id: str,
    anchor: str,
    *,
    overwrite: bool = False,
    ledger_path: str = "docs/全功能实现清单-技术支持版.md",
) -> dict:
    """清单台账更新：✅+日期+锚点写入（条目行状态列原位替换，统计节不滚动）。

    流程：①locate_ledger_row 定位条目行（缺文件/零命中/多处命中→LedgerError，
    entry_id 形状非法→ValueError，均透传）；②状态列改写——已带完成标记
    （✅/wired）且未显式 overwrite → LedgerError「已 ✅ 未授权覆盖」；构造
    `✅ MM-DD <anchor>` 新状态列；③行内替换（只改第 3 管道列，列数不变；
    「## 统计与说明」节不改动——人工维护，滚动记 TODO(manual)）；④原子写回
    （tmp+rename，写失败→LedgerError 且原文件不变）。

    Args:
        entry_id: 条目编号（^[A-L]\\d{1,2}$，如 'B5'/'G3'）。
        anchor: 实现锚点，如 'fn(open_b210_backend) commit abc1234'——须为非空
            单行 str 且不含管道符 '|'（管道会破坏表格列数：选择拒绝而非转义）。
        overwrite: 已 ✅ 条目覆盖须显式传 True。
        ledger_path: 台账 md 路径，默认仓库根真实清单。

    Returns:
        {'updated': True, 'line_no': 1-based 行号, 'old_status': 原状态列文本,
         'new_status': 新状态列文本, 'anchor': 去除首尾空白后的锚点}

    Raises:
        ValueError: anchor 非 str/空白/含换行/含管道符；entry_id 形状非法（透传自 locate）。
        LedgerError: 台账文件不存在/条目零命中/多处命中/已 ✅ 未授权覆盖/
            状态列缺失/写回失败（原子保护）。
    """
    # ---- anchor 前置校验（写文件之前，拒得越早副作用越小） ----
    if not isinstance(anchor, str):
        raise ValueError(
            f"anchor 必须为 str，实际收到 {type(anchor).__name__}: {anchor!r}"
        )
    anchor = anchor.strip()
    if not anchor:
        raise ValueError(
            "anchor 不能为空（须携带可回溯的实现锚点，"
            "如 'fn(open_b210_backend) commit abc1234'）"
        )
    if "\n" in anchor or "\r" in anchor:
        raise ValueError(f"anchor 必须单行（不得含换行符）: {anchor!r}")
    if "|" in anchor:
        raise ValueError(
            f"anchor 不得含管道符 '|'（会破坏台账表格列数，本函数选择拒绝而非转义）: {anchor!r}"
        )

    # ---- ① 定位（复用 locate_ledger_row：结构感知+精确边界） ----
    located = locate_ledger_row(entry_id, ledger_path)
    old_status = located["status_text"]

    # ---- ② 已完成条目：未显式授权不得覆盖 ----
    if located["has_done_mark"] and not overwrite:
        raise LedgerError(
            f"条目 {entry_id} 已 ✅（状态列: {old_status!r}）——未授权覆盖；"
            f"确需覆盖请显式传 overwrite=True"
        )

    new_status = _build_status(anchor)
    new_line = _replace_status_column(located["line"], new_status)

    # ---- ③④ 读全文→定位行漂移核对→只换目标行→原子写回 ----
    try:
        with open(ledger_path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise LedgerError(f"台账文件不存在或不可读: {ledger_path}（{exc}）") from exc

    newline = "\r\n" if "\r\n" in text else "\n"  # 行尾口径跟随原文件
    lines = text.split(newline)
    idx = located["line_no"] - 1
    if idx >= len(lines) or lines[idx] != located["line"]:
        raise LedgerError(
            f"台账在定位后被外部改动（第 {located['line_no']} 行内容漂移），拒绝写入: {ledger_path}"
        )
    lines[idx] = new_line
    _atomic_write(ledger_path, newline.join(lines))

    return {
        "updated": True,
        "line_no": located["line_no"],
        "old_status": old_status,
        "new_status": new_status,
        "anchor": anchor,
    }
