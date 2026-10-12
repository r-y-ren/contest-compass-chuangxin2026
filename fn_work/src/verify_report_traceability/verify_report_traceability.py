"""报告数字溯源校验（行级回查，不一致列差异）——重写规约与签名意图详见 fn_docs/responsibility.md（R46 顶层）。

校验链：extract_report_numbers 抽取 report.md 全部「数值+单位」→ 逐数字在
run_dir 三数据文件（kpi.csv/events.jsonl/monitor.csv，存在才读）原文中按
**数字词界正则** ``(?<![\\d.])<候选串>(?![\\d.])`` 找同值字符串（'5.0' 不命中
'15.03'、'0.2' 不命中 '0.25'——子串命中不算回查通过）→ 候选串集为等值形态
``{str(v), 整数形态（v.is_integer() 时）, 科学计数双形（'2.4e9'/'2.4e+09'/
'2.4E9'——mantissa 剥尾零、指数剥 '+' 与前导零）}``（**不含 .1f/.2f/.3f 舍入
形态**——0.25 不再匹配 0.2）→ 命中计 traced；口径行白名单**仅 '>' 开头的
脚注/引用行**（正文测量行数字一律回查——判据/阈值/目标字样不再整行豁免）计
contextual；两者皆非→差异条目 ``{'value','unit','line_no','context'}``。
报告文件/运行目录不存在 → ValueError。
"""
from __future__ import annotations

import os
import re

from src.verify_report_traceability.extract_report_numbers import extract_report_numbers

__all__ = ["verify_report_traceability"]

#: 回查数据文件（存在才读；缺失文件不阻断——可回查面如实缩小）。
_DATA_FILES = ("kpi.csv", "events.jsonl", "monitor.csv")


def _as_path_str(value: object, name: str) -> str:
    """路径规整：os.PathLike → str；非 str/PathLike → ValueError（消息附类型）。"""
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str):
        raise ValueError(
            f"{name} 必须为 str/os.PathLike 路径，实际 {type(value).__name__}: {value!r}"
        )
    return value


def _sci_forms(value: float) -> list[str]:
    """科学计数等值双形：mantissa 剥尾零 + 指数剥 '+' 与前导零（e/E × 紧凑/带号）。

    由 ``f"{value:e}"``（如 ``2.400000e+09``）生成 ``'2.4e9'/'2.4E9'/'2.4e+09'/
    '2.4E+09'``——数据文件写紧凑形（2.4e9）或 repr 形（2.4E+09）均按等值命中。
    """
    mantissa, raw_exp = f"{value:e}".split("e")
    mantissa = mantissa.rstrip("0").rstrip(".") or "0"
    exp_int = str(int(raw_exp))  # '+09'/'-05' → '9'/'-5'（剥 + 与前导零）
    forms = [
        f"{mantissa}e{exp_int}",
        f"{mantissa}E{exp_int}",
        f"{mantissa}e{raw_exp}",
        f"{mantissa}E{raw_exp}",
    ]
    return forms


def _candidate_strings(value: float) -> list[str]:
    """同值候选串集（等值形态，非舍入形态）：str(v)、整数形态、科学计数双形。

    去重保序。**不含 .1f/.2f/.3f 舍入变体**——舍入候选会把报告 0.2 误认成数据
    0.25（B18 高#5）；整数形态覆盖 5.0 ↔ 5；科学计数双形覆盖 2.4e9 ↔ 2.4E+09。
    """
    candidates = [str(value)]
    if value.is_integer():
        candidates.append(str(int(value)))
    candidates.extend(_sci_forms(value))
    seen: set[str] = set()
    ordered: list[str] = []
    for token in candidates:
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def _token_in_blob(token: str, blob: str) -> bool:
    """数字词界命中：``(?<![\\d.])token(?![\\d.])``——子串不算（B18 高#1）。

    '5.0' 不命中 '15.03'（前有数字 '1'），'0.2' 不命中 '0.25'（后有数字 '5'）；
    完整 '15.03' 命中 '15.03'（前后非数字/点）。
    """
    return re.search(rf"(?<![\d.]){re.escape(token)}(?![\d.])", blob) is not None


def _is_contextual_line(line: str) -> bool:
    """口径行白名单：仅 '>' 开头的脚注/引用行（正文测量行一律回查——B18 高#2）。"""
    return line.startswith(">")


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
        ``{'n_numbers': 抽取数字总数, 'n_traced': 可溯回数据文件数（数字词界
        命中——子串不算）, 'n_contextual': 口径行白名单数（仅 '>' 脚注/引用行）,
        'mismatches': [{'value','unit','line_no','context'}, ...],
        'passed': mismatches 为空}``——正文行数字（含判据/阈值/目标字样行）
        一律回查，不再整行豁免；报告自产常量/聚合值由 build_report 以 '> ' 引用
        行呈现（口径区覆盖）。
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
            _token_in_blob(token, data_blob)
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
