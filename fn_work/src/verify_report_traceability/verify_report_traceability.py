"""报告数字溯源校验（行级回查，不一致列差异）——重写规约与签名意图详见 fn_docs/responsibility.md（R46 顶层）。

校验链：extract_report_numbers 抽取 report.md 全部「数值+单位」→ 逐数字在
run_dir 三数据文件（kpi.csv/events.jsonl/monitor.csv，存在才读）原文中找同值
字符串（候选串集 ``{str(v), f'{v:.1f}', f'{v:.2f}', f'{v:.3f}'}``——float
等价形态：数据 0.300 与报告 0.3 互认）→ 找到计 traced；口径行白名单（该行
以 ``>`` 开头的脚注区，或含「判据/阈值/目标」字样——平台常量非本 run 数据）
计 contextual；两者皆非→差异条目 ``{'value','unit','line_no','context'}``。
报告文件/运行目录不存在 → ValueError。
"""
from __future__ import annotations

import os

from src.verify_report_traceability.extract_report_numbers import extract_report_numbers

__all__ = ["verify_report_traceability"]

#: 回查数据文件（存在才读；缺失文件不阻断——可回查面如实缩小）。
_DATA_FILES = ("kpi.csv", "events.jsonl", "monitor.csv")

#: 口径行白名单关键词（判据/阈值/目标——平台常量非本 run 数据，不算差异）。
_CONTEXTUAL_KEYWORDS = ("判据", "阈值", "目标")


def _as_path_str(value: object, name: str) -> str:
    """路径规整：os.PathLike → str；非 str/PathLike → ValueError（消息附类型）。"""
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str):
        raise ValueError(
            f"{name} 必须为 str/os.PathLike 路径，实际 {type(value).__name__}: {value!r}"
        )
    return value


def _candidate_strings(value: float) -> list[str]:
    """同值候选串集：str(v) 与 .1f/.2f/.3f 定点变体（float 等价形态回查）。"""
    return [str(value), f"{value:.1f}", f"{value:.2f}", f"{value:.3f}"]


def _is_contextual_line(line: str) -> bool:
    """口径行白名单：脚注区（'>' 开头行）或含 判据/阈值/目标 字样的行。"""
    return line.startswith(">") or any(key in line for key in _CONTEXTUAL_KEYWORDS)


def _read_data_text(path: str) -> str:
    """数据文件读回（utf-8 原文——数字纪律：回查按文件原文同值字符串）。"""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def verify_report_traceability(report_path: str, run_dir: str) -> dict:
    """报告数字溯源校验（R46）：逐数字回查数据文件原文，不一致列差异。

    Args:
        report_path: report.md 路径（不存在或不是普通文件 → ValueError）。
        run_dir: 运行目录（kpi.csv/events.jsonl/monitor.csv 回查源；不存在或
            不是目录 → ValueError）。

    Returns:
        ``{'n_numbers': 抽取数字总数, 'n_traced': 可溯回数据文件数,
        'n_contextual': 口径行白名单数（脚注区/判据·阈值·目标行）,
        'mismatches': [{'value','unit','line_no','context'}, ...],
        'passed': mismatches 为空}``——口径行白名单数字不算差异（平台常量）。
    """
    report_path = _as_path_str(report_path, "report_path")
    run_dir = _as_path_str(run_dir, "run_dir")
    if not os.path.isfile(report_path):
        raise ValueError(f"报告文件不存在: {report_path!r}")
    if not os.path.isdir(run_dir):
        raise ValueError(f"运行目录不存在: {run_dir!r}")

    with open(report_path, encoding="utf-8") as handle:
        report_md = handle.read()
    lines = report_md.splitlines()

    entries = extract_report_numbers(report_md)

    data_blob = "\n".join(
        _read_data_text(os.path.join(run_dir, name))
        for name in _DATA_FILES
        if os.path.isfile(os.path.join(run_dir, name))
    )

    n_traced = 0
    n_contextual = 0
    mismatches: list[dict] = []
    for entry in entries:
        line_no = entry["line_no"]
        full_line = (
            lines[line_no - 1] if 1 <= line_no <= len(lines) else entry["context"]
        )
        if _is_contextual_line(full_line):
            n_contextual += 1
            continue
        if any(
            token and token in data_blob
            for token in _candidate_strings(entry["value"])
        ):
            n_traced += 1
        else:
            mismatches.append(
                {
                    "value": entry["value"],
                    "unit": entry["unit"],
                    "line_no": line_no,
                    "context": entry["context"],
                }
            )

    return {
        "n_numbers": len(entries),
        "n_traced": n_traced,
        "n_contextual": n_contextual,
        "mismatches": mismatches,
        "passed": not mismatches,
    }
