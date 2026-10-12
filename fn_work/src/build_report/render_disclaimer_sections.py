"""口径脚注组装（复用共享声明块）——重写规约与签名意图详见 fn_docs/responsibility.md。

基座为 make_disclaimer_block('report') 全局口径块（屏蔽盒/仅自建链路/GB 42590 预研/
非 CISPR/数字纪律）；报告上下文（后端/时钟/运行标识/口径选择/模拟段清单）以 '> '
引用行追加其后（多行字段值逐行补 '> ' 前缀、'|' 转义 '\\|'——注入字段不破坏引用
块结构，B18 中#8/#9）；simulated_parts 非空（涉及模拟段）时整块拼接
make_disclaimer_block('emc')（emc 级声明，含非 CISPR 16-1-1 测量接收机句），
两级声明文案互不混写；simulated_parts 去重保序（B18 低#14）。上下文字段缺失/
空白补"未记录"（不虚构上下文）；report_ctx 非 dict 或已给字段类型错→ValueError。
"""
from __future__ import annotations

from src.shared.make_disclaimer_block import make_disclaimer_block

__all__ = ["render_disclaimer_sections"]

#: 上下文 str 字段缺失/空白时的如实占位（绝不虚构后端/时钟/运行标识）。
MISSING_TOKEN = "未记录"

#: PER 口径声明句（per_basis=True 时追加：BER→PER 换算口径，非直接测得 BER）。
BER_TO_PER_LINE = "口径：误码指标以 PER（分组差错率）呈现，由 BER 换算得到，非直接测得的 BER。"

#: 模拟段清单行前缀（simulated_parts 非空时列出涉及段，随后拼 emc 级声明整块）。
SIM_PARTS_PREFIX = "报告涉及模拟段："


def _escape_pipe(text: str) -> str:
    """行内消毒：'|' → '\\|'（markdown 表格/引用块定界符转义——防注入破结构）。"""
    return text.replace("|", "\\|")


def _sanitize_inline(text: str) -> str:
    """行内文本消毒：'|' 转义 + 换行折叠 ' / '（单行嵌入场景——模拟段清单等）。"""
    return _escape_pipe(text.replace("\n", " / "))


def _context_field_lines(label: str, value: str) -> list[str]:
    """上下文字段 → 引用行组：首行带标签，多行值逐行补 '> '（保持引用块完整）。

    '\n' 不再原样透传（防注入伪造脚注区外行——B18 中#8/#9）；每行 '|' 转义。
    """
    parts = value.split("\n")
    lines = [f"> 报告上下文：{label} = {_escape_pipe(parts[0])}"]
    lines.extend(f"> {_escape_pipe(part)}" for part in parts[1:])
    return lines


def _dedupe_in_order(parts: list[str]) -> list[str]:
    """去重保序（B18 低#14）：重复段名只留首次出现位。"""
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        if part not in seen:
            seen.add(part)
            ordered.append(part)
    return ordered


def _context_text(report_ctx: dict, key: str) -> str:
    """取上下文 str 字段：缺失/空白→MISSING_TOKEN；给了但非 str→ValueError。"""
    raw = report_ctx.get(key)
    if raw is None:
        return MISSING_TOKEN
    if not isinstance(raw, str):
        raise ValueError(
            f"report_ctx[{key!r}] 必须为 str，实际 {type(raw).__name__}: {raw!r}"
        )
    return raw if raw.strip() else MISSING_TOKEN


def render_disclaimer_sections(report_ctx: dict) -> str:
    """口径脚注组装（复用共享声明块）。

    组装顺序（各段之间空行分隔，上下文行逐行带 '> ' 前缀）：
    1. 基座：make_disclaimer_block('report') 全局口径块原文；
    2. 上下文：后端/时钟基准/运行标识三行（字段缺失或空白补"未记录"；多行值
       逐行补 '> ' 前缀、'|' 转义——注入不破坏引用块），per_basis=True 追加
       BER→PER 声明句，simulated_parts 非空（去重保序）追加模拟段清单行；
    3. 模拟段：simulated_parts 非空时整块拼接 make_disclaimer_block('emc')。

    report_ctx 非 dict、str 字段（backend/clock_ref/run_id）非 str、per_basis 非
    bool、simulated_parts 非 list 或元素非 str → ValueError（形状错显式拒，
    消息附字段名与实际类型）。
    """
    if not isinstance(report_ctx, dict):
        raise ValueError(
            f"report_ctx 必须为 dict，实际 {type(report_ctx).__name__}: {report_ctx!r}"
        )

    backend = _context_text(report_ctx, "backend")
    clock_ref = _context_text(report_ctx, "clock_ref")
    run_id = _context_text(report_ctx, "run_id")

    per_basis = report_ctx.get("per_basis", False)
    if not isinstance(per_basis, bool):
        raise ValueError(
            f"report_ctx['per_basis'] 必须为 bool，实际 {type(per_basis).__name__}: {per_basis!r}"
        )

    simulated_parts = report_ctx.get("simulated_parts", [])
    if not isinstance(simulated_parts, list):
        raise ValueError(
            f"report_ctx['simulated_parts'] 必须为 list[str]，"
            f"实际 {type(simulated_parts).__name__}: {simulated_parts!r}"
        )
    for idx, part in enumerate(simulated_parts):
        if not isinstance(part, str):
            raise ValueError(
                f"report_ctx['simulated_parts'][{idx}] 必须为 str，"
                f"实际 {type(part).__name__}: {part!r}"
            )

    context_lines: list[str] = []
    for label, value in (
        ("后端", backend),
        ("时钟基准", clock_ref),
        ("运行标识", run_id),
    ):
        context_lines.extend(_context_field_lines(label, value))
    if per_basis:
        context_lines.append(f"> {BER_TO_PER_LINE}")
    if simulated_parts:
        parts_line = "、".join(
            _sanitize_inline(part) for part in _dedupe_in_order(simulated_parts)
        )
        context_lines.append(f"> {SIM_PARTS_PREFIX}{parts_line}（读数适用下方 emc 级声明）")
    sections = [make_disclaimer_block("report"), "\n".join(context_lines)]
    if simulated_parts:
        sections.append(make_disclaimer_block("emc"))
    return "\n\n".join(sections)
