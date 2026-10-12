"""跨轮失效电平聚合：多样式对比表+薄弱样式/频点定位结论——B13 顶层，R26。

把多轮 record_failure_level 条目（``style``/``failure_level_db``（可能为
'unknown'）/``per_at_failure``/``ts_ms`` 等，可选 ``freq_mhz``）聚合为跨样式
对比与薄弱定位结论，供 build_report（报告结论段）与 run_demo（多场景汇总）
消费：

- 按 style 分组求失效电平中位数：``failure_level_db`` 为 'unknown'（或缺失/
  非数值）的条目不进数值统计，只计入 ``n_unknown``；
- 对比表按中位数升序，每行 ``{'style', 'median_level_db', 'n_runs', 'min_db',
  'max_db'}``——``n_runs`` 为该样式进入数值统计的有效**条目数**（按条目计数，
  非轮次数：一轮测评可产出多条目；unknown 电平条目不计入；全 unknown 的样式
  无数值统计，不出现于表中——B13 复审低#5 口径注明）；
- 薄弱定位：中位数最低的样式为 ``weakest_style``，平手取样式名字典序先并置
  ``tie=True``；条目携带 ``freq_mhz``（数值，或可 float 且有限的字符串数字
  如 ``'2480'``——归一后入频点维，B13 复审低#6）时频点维度同法（按频点分组
  求中位数、取最低者，≥2 个频点才可比）：得 ``weakest_freq_mhz``（恒 float），
  频点中位数平手取较小频点并同样置 ``tie=True``；freq_mhz 在位但归一失败
  （非数字串/NaN/±inf/bool）的条目跳过频点维并计 ``n_freq_invalid``
  （电平维统计不受影响）；
- 降级：仅 1 个可用样式→``comparison`` 置空（无跨样式可比）、结论注明
  '单样式数据——无跨样式对比'（附该样式中位数与有效条目数——文案「有效 N 条
  （按条目计）」）；全部条目 unknown→``weakest_style``/``weakest_freq_mhz``
  为 None、结论注明无法定位；``entries`` 为空→全 None+结论 '无数据'。

``entries`` 非 list 或元素非 dict 抛 :class:`ValueError`。
"""
from __future__ import annotations

import math
import statistics


def _is_number(value: object) -> bool:
    """数值判定（bool 不算——失效电平/频点口径不接受布尔）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_freq_mhz(value: object) -> float | None:
    """freq_mhz 归一为 float：数值直取；str 可 float 且有限→转数值；否则 None。

    B13 复审低#6：字符串数字频点（如 '2480'）归一后进频点维；归一失败
    （非数字串/NaN/±inf/bool）返回 None，由调用方跳过频点维并计 n_freq_invalid。
    """
    if _is_number(value):
        return float(value)
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        if math.isfinite(number):
            return number
    return None


def compare_failure_boundaries(entries: list) -> dict:
    """跨轮失效电平聚合：多样式对比表+薄弱样式/频点定位结论（R26）。

    Args:
        entries: 多轮 record_failure_level 条目 list[dict]，每条至少含
            ``style`` 与 ``failure_level_db``（数值 dB，或 'unknown'），可携带
            ``per_at_failure``/``ts_ms`` 等透传字段与可选 ``freq_mhz``（数值，
            或可 float 且有限的字符串数字——归一后入频点维，B13 复审低#6）。

    Returns:
        dict::

            {'comparison': [行…],               # 按中位数升序；行键
                                                # style/median_level_db/n_runs/min_db/max_db
                                                # n_runs=有效条目数（按条目计，非轮次数）
             'weakest_style': str | None,       # 中位数最低样式；平手字典序先
             'weakest_freq_mhz': float | None,  # 频点维度同法（≥2 频点）
             'tie': bool,                       # 最薄弱中位数平手（样式或频点任一）
             'n_unknown': int,                  # unknown/非数值电平条目计数
             'n_freq_invalid': int,             # freq_mhz 在位但归一失败的条目计数
             'conclusion': str}                 # 中文结论段（最弱样式+电平、n_unknown 提示）

    Raises:
        ValueError: ``entries`` 非 list，或其中元素非 dict。
    """
    if not isinstance(entries, list):
        raise ValueError(
            f"entries must be list, got {type(entries).__name__}: {entries!r}"
        )
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(
                f"entries[{idx}] must be dict, got {type(entry).__name__}: {entry!r}"
            )

    if not entries:
        return {
            "comparison": [],
            "weakest_style": None,
            "weakest_freq_mhz": None,
            "tie": False,
            "n_unknown": 0,
            "n_freq_invalid": 0,
            "conclusion": "无数据",
        }

    by_style: dict[object, list[float]] = {}
    by_freq: dict[float, list[float]] = {}
    n_unknown = 0
    n_freq_invalid = 0
    for entry in entries:
        level = entry.get("failure_level_db")
        if not _is_number(level):
            # 'unknown'（或缺电平/非数值）条目不进数值统计，只计数——全 unknown
            # 的样式/频点分组无从求中位数，自然不出现于对比与定位。
            n_unknown += 1
            continue
        by_style.setdefault(entry.get("style"), []).append(level)
        freq_raw = entry.get("freq_mhz")
        if freq_raw is not None:
            freq = _normalize_freq_mhz(freq_raw)
            if freq is None:
                # B13 复审低#6：频点在位但归一失败（非数字串/NaN/±inf/bool）——
                # 跳过频点维并计数（电平维统计不受影响）。
                n_freq_invalid += 1
            else:
                by_freq.setdefault(freq, []).append(level)

    comparison = [
        {
            "style": style,
            "median_level_db": statistics.median(levels),
            "n_runs": len(levels),
            "min_db": min(levels),
            "max_db": max(levels),
        }
        for style, levels in by_style.items()
    ]
    # 升序表：中位数同序时按样式名字典序排——保证平手时字典序先者居首。
    comparison.sort(key=lambda row: (row["median_level_db"], str(row["style"])))

    # 降级：仅 1 个可用样式——对比表置空（无跨样式可比），单样式统计进结论。
    single_row = None
    if len(comparison) == 1:
        single_row = comparison[0]
        comparison = []

    weakest_style = None
    style_tie = False
    if len(comparison) >= 2:
        weakest_style = comparison[0]["style"]
        style_tie = (
            comparison[1]["median_level_db"] == comparison[0]["median_level_db"]
        )

    weakest_freq_mhz = None
    weakest_freq_median = None
    freq_tie = False
    freq_rows = sorted(
        (
            {"freq_mhz": freq, "median_level_db": statistics.median(levels)}
            for freq, levels in by_freq.items()
        ),
        key=lambda row: (row["median_level_db"], row["freq_mhz"]),
    )
    if len(freq_rows) >= 2:
        weakest_freq_mhz = float(freq_rows[0]["freq_mhz"])
        weakest_freq_median = freq_rows[0]["median_level_db"]
        freq_tie = (
            freq_rows[1]["median_level_db"] == freq_rows[0]["median_level_db"]
        )

    parts: list[str] = []
    if comparison:
        lead = comparison[0]
        parts.append(
            f"跨样式对比（按失效电平中位数升序）：最薄弱样式为 {lead['style']}"
            f"（失效电平中位数 {lead['median_level_db']} dB）"
        )
        if style_tie:
            parts.append("最薄弱中位数并列，按样式名字典序取先")
    elif single_row is not None:
        parts.append(
            f"单样式数据——无跨样式对比；样式 {single_row['style']} 失效电平"
            f"中位数 {single_row['median_level_db']} dB"
            f"（有效 {single_row['n_runs']} 条（按条目计））"  # B13 复审低#5 口径
        )
    else:
        parts.append(
            f"全部 {n_unknown} 条条目失效电平均为 unknown——无法定位薄弱样式/频点"
        )

    if weakest_freq_mhz is not None:
        parts.append(
            f"最薄弱频点为 {weakest_freq_mhz} MHz"
            f"（失效电平中位数 {weakest_freq_median} dB）"
        )
    if n_unknown and (comparison or single_row is not None):
        parts.append(f"另有 {n_unknown} 条 unknown 电平条目未纳入数值统计")
    if n_freq_invalid:
        parts.append(f"另有 {n_freq_invalid} 条频点不可归一条目未纳入频点统计")

    return {
        "comparison": comparison,
        "weakest_style": weakest_style,
        "weakest_freq_mhz": weakest_freq_mhz,
        "tie": style_tie or freq_tie,
        "n_unknown": n_unknown,
        "n_freq_invalid": n_freq_invalid,
        "conclusion": "；".join(parts) + "。",
    }
