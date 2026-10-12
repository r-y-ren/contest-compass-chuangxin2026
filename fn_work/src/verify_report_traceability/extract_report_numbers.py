"""抽取报告关键数字与行号——重写规约与签名意图详见 fn_docs/responsibility.md。

正则逐行扫「数值+单位」模式（dBm/dB/dBµV/dBuV/MHz/GHz/ms/s/%/Hz；表格单元格
"| x dBm |" 属普通行，天然覆盖）：数值支持整数/小数/科学计数（1e6/2.4e9/
-3.5E-2），负号字符类 [-−] 兼容 U+2212（−20.5），可隔空白紧贴单位；输出
[{'value': float, 'unit': str, 'line_no': 1-based, 'context': 该行截短 60 字符}]，
行内多数字逐一抽、重复值多处出现如实保留、无非数值行贡献空。
report_md 非 str → ValueError；正常文本不抛出（无匹配返回空列表）。
"""
from __future__ import annotations

import re

__all__ = ["extract_report_numbers"]

#: 上下文行截短上限（字符）。
CONTEXT_MAX_CHARS = 60

#: Unicode 减号（U+2212）——报告文本常见形，float() 前归一为 ASCII '-'。
_UNICODE_MINUS = "−"

#: 数值+单位模式：符号仅在不紧跟在字词/点后时视为负号（"3-4 dB"/"3−4 dB" 取 4
#: 不取 -4——区间连字符/减号非负号）；负号字符类 [-−] 含 U+2212；单位交替按
#: 长前缀优先排序（dBµV/dBuV 先于 dBm/dB、dBm 先于 dB、MHz/GHz 先于 Hz、
#: ms 先于 s）；(?!\w) 词界防截短单位误匹配（"10 dBi"/"4 MHzx" 不抽）；
#: '/' 非 \w——复合单位 "-30 dBm/Hz" 抽 (-30, 'dBm') 如实保留（功率谱密度口径）。
_NUMBER_UNIT_RE = re.compile(
    r"(?P<value>(?<![\w.])[-−]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"\s*(?P<unit>dBµV|dBuV|dBm|dB|MHz|GHz|ms|Hz|s|%)(?!\w)"
)


def _to_float(raw: str) -> float:
    """数值文本 → float：U+2212 减号先归一为 ASCII '-'（float 不认 U+2212）。"""
    return float(raw.replace(_UNICODE_MINUS, "-"))


def extract_report_numbers(report_md: str) -> list:
    """抽取报告关键数字与行号。

    逐行 finditer：每个「数值+单位」命中产出一个条目（行内多值逐一抽、重复值
    保留），条目含 'value'（float，科学计数按面值换算，负号兼容 U+2212）、
    'unit'（命中的单位词，dBµV/dBuV 双形等同族）、'line_no'（1-based 行号）、
    'context'（该行截短至 CONTEXT_MAX_CHARS 字符）。
    表格行（如 "| -20.5 dBm | 30 dB |"）按普通行扫描即覆盖。report_md 非 str →
    ValueError；str 输入绝不抛出，无非数值行/空文本返回空列表。
    """
    if not isinstance(report_md, str):
        raise ValueError(
            f"report_md 必须为 str，实际 {type(report_md).__name__}: {report_md!r}"
        )

    entries: list[dict] = []
    for line_no, line in enumerate(report_md.splitlines(), start=1):
        context = line[:CONTEXT_MAX_CHARS]
        for match in _NUMBER_UNIT_RE.finditer(line):
            entries.append(
                {
                    "value": _to_float(match.group("value")),
                    "unit": match.group("unit"),
                    "line_no": line_no,
                    "context": context,
                }
            )
    return entries
