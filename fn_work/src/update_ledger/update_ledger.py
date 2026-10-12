"""清单台账更新：✅+日期+锚点写入——重写规约与签名意图详见 fn_docs/responsibility.md。

列语义自适应写侧（B17 高#1，按定位 table_form 分流）：
- 'status'（表头含「状态」列）：状态列原位替换，列数与其余列原文不变；同表
  先前行补列造成的参差行（行尾空槽恰对齐状态列）→ 写入该槽＝对该行追加列；
- 'append'（真清单 4 列形态，表头无状态列）：表头行与分隔行各追加
  `完成状态 |` / `---|` 列，条目行尾追加 ` ✅ MM-DD anchor |`——描述列零破坏，
  表格结构保持合法；补列一次后表头含「完成状态」，同表后续写入走 status 形态；
- 'legacy'（无表头兜底）：第 3 管道列原位替换，列数不足拒绝（不得借机增列）。
行尾字节保持（B17 中#3）：读写均 newline=''——CRLF 原样往返，不混入裸 LF。
anchor 上限（B17 低#6）：超 120 字符拒绝。列解析 Markdown 感知（中#2）：
\\| 转义管道不破列。

统计节滚动申报简化：本函数只改条目行（状态列），文件尾部「## 统计与说明」节
（含「- 共 .* 函数/条」进度行）为人工维护、不自动滚动——TODO(manual)：统计节
滚动归人工/结题轮，自检一致性核对归 audit_ledger（R51）。
"""
from __future__ import annotations

import os
from datetime import date

from .locate_ledger_row import (
    LedgerError,
    _is_separator_row,
    _join_md_cells,
    _split_md_cells,
    locate_ledger_row,
)

__all__ = ["update_ledger"]

# 状态列索引来自定位结果（locate_ledger_row 的 status_col_index：表头检测列
# 或 legacy 第 3 管道列）——本文件不再自带列号常量。原位替换要求行至少含
# col_index+2 段（该列为真实内容列），否则视为状态列缺失拒绝改写。

# append 形态（真清单无状态列）动态补列的表头列名与分隔单元。
_APPENDED_STATUS_HEADER = "完成状态"
_APPENDED_SEPARATOR_CELL = "---"

#: anchor 长度上限（单行可读性口径，B17 低#6）。
ANCHOR_MAX_LEN = 120


def _build_status(anchor: str) -> str:
    """构造新状态列文本：`✅ MM-DD <anchor>`（月-日 + 实现锚点，单行内）。"""
    return f"✅ {date.today().strftime('%m-%d')} {anchor}"


def _replace_status_column(
    line: str, col_index: int, new_status: str, *, allow_trailing_append: bool = False
) -> str:
    """行内替换第 col_index 管道列（状态列），保持列数与其余列原文不变。

    Markdown 感知切分/回拼（\\| 转义管道不破列，中#2）。列数不足（无该列的
    畸形行）→ LedgerError 拒绝；allow_trailing_append（status 形态）：行尾
    空槽（末个空单元）恰对齐状态列时写入该槽＝对该行追加状态列（同表先行
    补列造成的参差行）。
    """
    parts = _split_md_cells(line)
    has_real_cell = len(parts) >= col_index + 2
    trailing_empty_slot = (
        allow_trailing_append
        and len(parts) == col_index + 1
        and parts[col_index].strip() == ""
    )
    if not (has_real_cell or trailing_empty_slot):
        raise LedgerError(
            f"条目行状态列缺失（第 {col_index} 管道列），无法原位替换（列数不足）: {line!r}"
        )
    parts[col_index] = f" {new_status} "
    if trailing_empty_slot:
        parts.append("")  # 行尾空槽原为闭合 `|` 后空串——写入内容后补 '' 闭合管道
    return _join_md_cells(parts)


def _append_status_cell(line: str, text: str) -> str:
    """行尾追加一个表格单元：`… | <text> |`（表头/分隔行/条目行通用）。"""
    base = line.rstrip()
    if not base.endswith("|"):
        base += " |"
    return f"{base} {text} |"


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
    """清单台账更新：✅+日期+锚点写入（状态列按表头形态自适应改写，统计节不滚动）。

    流程：①locate_ledger_row 定位条目行并做表头检测（缺文件/零命中/多处命中→
    LedgerError，entry_id 形状非法→ValueError，均透传）；②已完成判定——已带
    完成标记（✅/wired，含 append 补列后「完成状态」列含 ✅）且未显式
    overwrite → LedgerError「已 ✅ 未授权覆盖」；构造 `✅ MM-DD <anchor>` 新
    状态文本；③改写（按 table_form 分流，见模块 docstring：status 原位替换/
    行尾补槽、append 表头+分隔行+条目行三行各追加一列、legacy 第 3 管道列
    原位替换；「## 统计与说明」节不改动——人工维护，滚动记 TODO(manual)）；
    ④原子写回（tmp+rename，newline='' 保行尾字节——CRLF 原样往返；写失败→
    LedgerError 且原文件不变）。

    Args:
        entry_id: 条目编号（^[A-L]\\d{1,2}$，如 'B5'/'G3'）。
        anchor: 实现锚点，如 'fn(open_b210_backend) commit abc1234'——须为非空
            单行 str、不含管道符 '|'（管道会破坏表格列数：选择拒绝而非转义）
            且长度 ≤120 字符。
        overwrite: 已 ✅ 条目覆盖须显式传 True。
        ledger_path: 台账 md 路径，默认仓库根真实清单。

    Returns:
        {'updated': True, 'line_no': 1-based 行号, 'old_status': 原状态列文本
         （append 形态首写为 ''）, 'new_status': 新状态列文本,
         'anchor': 去除首尾空白后的锚点}

    Raises:
        ValueError: anchor 非 str/空白/含换行/含管道符/超 120 字符；entry_id
            形状非法（透传自 locate）。
        LedgerError: 台账文件不存在/条目零命中/多处命中/已 ✅ 未授权覆盖/
            状态列缺失（legacy 及畸形行）/表头漂移/写回失败（原子保护）。
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
    if len(anchor) > ANCHOR_MAX_LEN:
        raise ValueError(
            f"anchor 过长（{len(anchor)} 字符 > 上限 {ANCHOR_MAX_LEN}）——"
            f"台账单行可读性口径，请精简锚点: {anchor!r}"
        )

    # ---- ① 定位（复用 locate_ledger_row：结构感知+精确边界+表头检测） ----
    located = locate_ledger_row(entry_id, ledger_path)
    old_status = located["status_text"]

    # ---- ② 已完成条目：未显式授权不得覆盖 ----
    if located["has_done_mark"] and not overwrite:
        raise LedgerError(
            f"条目 {entry_id} 已 ✅（状态列: {old_status!r}）——未授权覆盖；"
            f"确需覆盖请显式传 overwrite=True"
        )

    new_status = _build_status(anchor)

    # ---- ③④ 读全文（newline='' 保行尾字节）→漂移核对→按形态改写→原子写回 ----
    try:
        with open(ledger_path, "r", encoding="utf-8", newline="") as fh:
            text = fh.read()
    except OSError as exc:
        raise LedgerError(f"台账文件不存在或不可读: {ledger_path}（{exc}）") from exc

    newline = "\r\n" if "\r\n" in text else "\n"  # 行尾口径跟随原文件（字节保持）
    lines = text.split(newline)
    idx = located["line_no"] - 1
    if idx >= len(lines) or lines[idx] != located["line"]:
        raise LedgerError(
            f"台账在定位后被外部改动（第 {located['line_no']} 行内容漂移），拒绝写入: {ledger_path}"
        )

    if located["table_form"] == "append":
        # 真清单形态：表头/分隔行/条目行各追加一列（描述列零破坏，中#1 修复写侧）。
        header_idx = located["header_line_no"] - 1
        sep_idx = header_idx + 1
        if (
            header_idx >= len(lines)
            or lines[header_idx] != located["header_line"]
            or sep_idx >= len(lines)
            or not _is_separator_row(lines[sep_idx])
        ):
            raise LedgerError(
                f"台账在定位后被外部改动（第 {located['header_line_no']} 行表头/分隔行漂移），"
                f"拒绝写入: {ledger_path}"
            )
        lines[header_idx] = _append_status_cell(lines[header_idx], _APPENDED_STATUS_HEADER)
        lines[sep_idx] = _append_status_cell(lines[sep_idx], _APPENDED_SEPARATOR_CELL)
        lines[idx] = _append_status_cell(lines[idx], new_status)
    else:
        col_index = located["status_col_index"]
        lines[idx] = _replace_status_column(
            lines[idx],
            col_index,
            new_status,
            allow_trailing_append=(located["table_form"] == "status"),
        )
    _atomic_write(ledger_path, newline.join(lines))

    return {
        "updated": True,
        "line_no": located["line_no"],
        "old_status": old_status,
        "new_status": new_status,
        "anchor": anchor,
    }
