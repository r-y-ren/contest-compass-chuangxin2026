"""台账自检：完成锚点存在（dead_anchor）/进行中冲突与✅泄漏（false_negative）/注释率附差距
——重写规约与签名意图详见 fn_docs/responsibility.md。

done 同源口径（B17 中#5）：完成判定复用 locate_ledger_row 的 has_done_mark
（✅ 或 wired 字样）——wired 行同样纳入 done 计数与锚点核验，不再漏统。

统计节一致性：update_ledger 申报简化为不滚动统计节（人工维护），故本自检
不核对「- 共 .* 函数/条」行与实际条数——TODO(manual)：结题轮人工核对。
"""
from __future__ import annotations

import os
import re

from src.update_ledger.locate_ledger_row import LedgerError, locate_ledger_row

from .count_comment_ratio import count_comment_ratio

__all__ = ["COMMENT_RATIO_TARGET", "audit_ledger"]

#: 注释率结题口径目标（≥20%）。
COMMENT_RATIO_TARGET = 0.20

# A–L 条目行（含 ▶ 前缀变体——与 locate_ledger_row 同口径的扫描超集；
# 规约正则 ^\|\s*[A-L]\d{1,2}\s*\| 命中的平铺行是其真子集）。
_DOMAIN_ROW_RE = re.compile(r"^\|\s*(?:▶\s*)?([A-L]\d{1,2})\s*\|")

# ✅ 锚点中的函数名：fn(name) 显式形式优先（如 'fn(open_b210_backend) commit abc1234'）。
_FN_ANCHOR_RE = re.compile(r"\bfn\(\s*([A-Za-z_]\w*)\s*\)")
# 无 fn() 时的裸函数名 token（snake_case：len≥4 且含 '_'，天然滤掉日期 10-12、
# 'commit'、提交哈希 'abc1234' 等非函数 token）。
_BARE_TOKEN_RE = re.compile(r"\b([A-Za-z_]\w*)\b")

# 代码树索引的目录黑名单（与 count_comment_ratio 同口径：生成物+第三方）。
_SKIPPED_DIRS = frozenset({"__pycache__", ".git", "site-packages", "venv", ".venv"})

#: 差异清单合法 kind 集（dead_anchor=锚点失效；false_negative=不应存在的完成标注；
#: ambiguous=条目多处命中——locate_ledger_row 定位歧义）。
ISSUE_KINDS = frozenset({"dead_anchor", "false_negative", "ambiguous"})


class _CodeIndex:
    """code_root 一次性索引：锚点函数名在文件名或文件内容中命中即存在。

    目录树只走一遍；文件内容按需惰性读取并缓存（首个 miss 触发全文扫描）。
    不可读文件按空内容处理（不炸自检）。台账文件自身被排除——锚点文本必然
    出现在台账里，自引用命中不算「代码树中存在」。
    """

    def __init__(self, code_root: str, exclude: frozenset[str] | set[str] = frozenset()) -> None:
        self._paths: list[str] = []
        self._texts: dict[str, str] | None = None
        self._exclude = {os.path.abspath(p) for p in exclude}
        for dirpath, dirnames, filenames in os.walk(code_root):
            dirnames[:] = [d for d in dirnames if d not in _SKIPPED_DIRS]
            for name in filenames:
                path = os.path.join(dirpath, name)
                if os.path.abspath(path) in self._exclude:
                    continue
                self._paths.append(path)

    def exists(self, needle: str) -> bool:
        """文件名或文件内容含 needle 即真。"""
        for path in self._paths:
            if needle in os.path.basename(path):
                return True
        if self._texts is None:
            self._texts = {}
        for path in self._paths:
            if path not in self._texts:
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        self._texts[path] = fh.read()
                except OSError:
                    self._texts[path] = ""
            if needle in self._texts[path]:
                return True
        return False


def _anchor_names(anchor_text: str) -> list[str]:
    """从锚点文本提取待核验函数名清单。

    口径：含 fn(name) 显式锚点 → 只核验这些 name（日期/commit/哈希等伴生
    token 不核验）；否则退回裸 snake_case token（len≥4 且含 '_'）。
    """
    fn_names = _FN_ANCHOR_RE.findall(anchor_text)
    if fn_names:
        return fn_names
    return [t for t in _BARE_TOKEN_RE.findall(anchor_text) if len(t) >= 4 and "_" in t]


# wired-only 完成标记（大小写不敏感）——done 判定与 locate_ledger_row 同口径后，
# 状态列可只带 wired 不带 ✅，锚点正文取 wired 之后文本。
_WIRED_RE = re.compile(r"wired", re.IGNORECASE)


def _anchor_text_of(status: str) -> str:
    """状态列文本剥去完成标记（✅ 优先，wired-only 次之）取锚点正文。"""
    if "✅" in status:
        rest = status.split("✅", 1)[1]
    else:
        parts = _WIRED_RE.split(status, maxsplit=1)
        rest = parts[1] if len(parts) == 2 else status
    return rest.strip().lstrip("：:，, ").strip()


def audit_ledger(ledger_path: str, code_root: str) -> dict:
    """台账自检：✅ 锚点存在 / 未完成条目不应带 ✅ / 注释率附 target 差距。

    流程：①扫清单 A–L 全条目行（含 ▶ 变体）并逐条复用 locate_ledger_row 定位
    （状态列与标记判定同口径；多处命中→'ambiguous'）；②完成条目（done 判定
    ＝locate 的 has_done_mark：✅ 或 wired——B17 中#5 同源口径）收集锚点
    （状态列剥去 ✅/wired 标记后的文本）→提取函数名（fn(name) 优先，其次裸
    snake_case token）→在 code_root 下核验（文件名或内容命中）——不存在→
    'dead_anchor'；③未完成条目的完成标注异常→'false_negative'（不应有——
    locate 已判口径）：进行中标注（▶）与 ✅/wired 并存、或 ✅ 泄漏到状态列
    之外；④count_comment_ratio 附于 'comment_ratio' 键（含 target 0.20 与
    差距 gap）。

    Args:
        ledger_path: 台账 md 路径（如 docs/全功能实现清单-技术支持版.md）。
        code_root: 源码树根目录（锚点核验+注释率统计共用）。

    Returns:
        {'total_entries': 唯一条目数, 'done_entries': 完成条目数（✅ 或 wired
         ——与 locate/update 同源口径）, 'issues': [{'entry_id', 'kind',
         'detail'}, ...]（kind ∈ dead_anchor/false_negative/ambiguous）,
         'comment_ratio': count_comment_ratio 报告 + {'target': 0.20,
         'gap': target-ratio（ratio None→None）, 'meets_target': ratio≥target},
         'clean': issues 为空}

    Raises:
        LedgerError: 台账文件不存在或不可读。
        ValueError: code_root 不存在或非目录（count_comment_ratio 口径透传）。
    """
    # ---- ① 扫全条目行 ----
    try:
        with open(ledger_path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        raise LedgerError(f"台账文件不存在或不可读: {ledger_path}（{exc}）") from exc

    entry_ids: dict[str, None] = {}  # 有序去重（dict 保插入序）
    for line in lines:
        m = _DOMAIN_ROW_RE.match(line)
        if m is not None:
            entry_ids.setdefault(m.group(1), None)

    issues: list[dict] = []
    done_entries = 0
    index: _CodeIndex | None = None  # 惰性：无 ✅ 条目时不扫代码树

    for entry_id in sorted(entry_ids):
        try:
            # 复用定位：行/状态列/完成与进行中标记的判定与 update_ledger 同源。
            info = locate_ledger_row(entry_id, ledger_path)
        except LedgerError as exc:
            # id 来自本文件（零命中不可能）；仅剩多处命中→定位歧义如实上报。
            issues.append({"entry_id": entry_id, "kind": "ambiguous", "detail": str(exc)})
            continue

        status = info["status_text"]
        done = info["has_done_mark"]  # ✅ 或 wired——与 locate/update 同源（中#5）

        # ---- ③ false_negative：未完成条目不应带完成标注 ----
        if info["in_progress"] and done:
            issues.append(
                {
                    "entry_id": entry_id,
                    "kind": "false_negative",
                    "detail": f"进行中标注（▶）与完成标记（✅/wired）并存（不应有）: 状态列 {status!r}",
                }
            )
        if not done and "✅" in info["line"]:
            issues.append(
                {
                    "entry_id": entry_id,
                    "kind": "false_negative",
                    "detail": (
                        f"✅ 泄漏到状态列之外（状态列 {status!r} 无 ✅，行内却含 ✅）: "
                        f"{info['line']!r}"
                    ),
                }
            )
        if not done:
            continue

        # ---- ② 完成条目（✅/wired）：锚点收集与核验 ----
        done_entries += 1
        anchor_text = _anchor_text_of(status)
        names = _anchor_names(anchor_text)
        if not names:
            issues.append(
                {
                    "entry_id": entry_id,
                    "kind": "dead_anchor",
                    "detail": (
                        f"锚点不含可核验函数名（fn(name) 或 snake_case token）: {anchor_text!r}"
                    ),
                }
            )
            continue
        if index is None:
            index = _CodeIndex(code_root, exclude={ledger_path})
        for name in names:
            if not index.exists(name):
                issues.append(
                    {
                        "entry_id": entry_id,
                        "kind": "dead_anchor",
                        "detail": (
                            f"锚点函数 {name} 在代码树中不存在（文件名与内容均未命中）: "
                            f"{code_root}"
                        ),
                    }
                )

    # ---- ④ 注释率附 target 差距 ----
    ratio_report = count_comment_ratio(code_root)
    ratio = ratio_report.get("ratio")
    comment_ratio = dict(ratio_report)
    comment_ratio["target"] = COMMENT_RATIO_TARGET
    comment_ratio["gap"] = (
        None if ratio is None else round(COMMENT_RATIO_TARGET - ratio, 4)
    )
    comment_ratio["meets_target"] = (
        None if ratio is None else ratio >= COMMENT_RATIO_TARGET
    )

    return {
        "total_entries": len(entry_ids),
        "done_entries": done_entries,
        "issues": issues,
        "comment_ratio": comment_ratio,
        "clean": not issues,
    }
