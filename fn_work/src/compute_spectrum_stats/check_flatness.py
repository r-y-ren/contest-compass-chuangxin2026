"""带内平坦度核验（≤4dB 判据）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math

__all__ = ["check_flatness"]

# EN 300 328 对 2.4G 宽带传输系统带限噪声功率谱平坦度的默认判据（B.7 条款口径）：
# 带内最大功率 − 最小功率 ≤ 4 dB。
_DEFAULT_FLATNESS_LIMIT_DB = 4.0
# 少于 3 个可用 bin 时 max−min 无统计意义，按不可用返回（不抛）。
_MIN_USABLE_BINS = 3


def _as_finite_number(value) -> float | None:
    """数值归一：bool/非数值/NaN/±inf（含超 float 可表示范围的大 int）一律 None，绝不抛出。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _parse_band(band) -> tuple[float, float]:
    """band 校验：合法返回 (lo, hi) 有限数值对；形状错/数值非法（含 NaN 元素）→ ValueError。

    lo > hi 不算形状错：视为空带（带内 0 bin → 不可用返回），与"带内 bin 不足不抛"口径一致。
    """
    if not isinstance(band, (tuple, list)):
        raise ValueError(
            f"band 必须是 (lo, hi) 数值二元组（tuple/list），实际类型 {type(band).__name__}: {band!r}"
        )
    if len(band) != 2:
        raise ValueError(f"band 必须是 (lo, hi) 二元组，实际长度 {len(band)}: {band!r}")
    lo = _as_finite_number(band[0])
    hi = _as_finite_number(band[1])
    if lo is None or hi is None:
        raise ValueError(f"band 的 lo/hi 必须是有限数值（MHz），实际 band={band!r}")
    return lo, hi


def _parse_limit(limit_db) -> float:
    """limit_db 校验：必须是有限非负数值（dB）；bool/非数值/NaN/±inf/负数 → ValueError。"""
    number = _as_finite_number(limit_db)
    if number is None:
        raise ValueError(
            f"limit_db 必须是有限非负数值（dB），实际 {limit_db!r}"
        )
    if number < 0:
        raise ValueError(f"limit_db 不能为负（dB），实际 {number}")
    return number


def _collect_usable_bins(power_bins, lo: float, hi: float) -> list[tuple[float, float]]:
    """收集带内可用 bin：闭区间 lo ≤ freq_mhz ≤ hi；NaN/inf 功率或缺频点/非数值 bin 跳过。"""
    usable: list[tuple[float, float]] = []
    for bin_item in power_bins:
        if not isinstance(bin_item, dict):
            continue
        freq = _as_finite_number(bin_item.get("freq_mhz"))
        power = _as_finite_number(bin_item.get("power_db"))
        if freq is None or power is None:
            continue
        if lo <= freq <= hi:
            usable.append((freq, power))
    return usable


def check_flatness(power_bins, band: tuple, limit_db: float = _DEFAULT_FLATNESS_LIMIT_DB) -> dict:
    """带内平坦度核验：带内功率谱 bin 的 max−min（dB）与 ≤limit_db 判据比对。

    判据口径：默认 limit_db=4.0 取自 EN 300 328 带限噪声功率谱平坦度判据
    （B.7 带限噪声规范：带内最大最小功率差 ≤4 dB），等值（==limit_db）按通过计。

    输入：
      - power_bins: 功率谱 bin 列表（同 estimate_snr 形状），
        每个 bin 为 {'freq_mhz': float, 'power_db': float}（频率 MHz、功率 dB，
        绝对标度不参与计算，只影响 max−min）；bin 归属带内按闭区间判定。
      - band: (lo, hi) 目标频带（MHz，闭区间）；lo>hi 视为空带（返回不可用，不抛）。
      - limit_db: 平坦度判据（dB），默认 4.0。

    输出（可用时）：
      {'flatness_db': max−min（float）, 'limit_db': 实际判据, 'pass': flatness_db ≤ limit_db,
       'n_bins': 带内可用 bin 数, 'max_at_mhz': 最大功率 bin 频点,
       'min_at_mhz': 最小功率 bin 频点, 'violation': not pass}
      功率并列时 max/min 频点取首个出现者（按 power_bins 给定顺序）。

    输出（带内可用 bin <3 时，不抛）：
      {'available': False, 'n_bins': 带内可用 bin 数, 'reason': 'insufficient_bins',
       'flatness_db': None}
      可用 bin 指带内且功率有限者：NaN/inf 功率或缺字段/非数值 bin 不计入 n_bins。

    错误：
      - power_bins 非 list/tuple 容器 → ValueError；
      - band 形状错（非二元组/非数值/NaN 元素）→ ValueError；
      - limit_db 非有限非负数值（bool/字符串/NaN/inf/负数）→ ValueError。
    """
    lo, hi = _parse_band(band)
    limit = _parse_limit(limit_db)
    if not isinstance(power_bins, (list, tuple)):
        raise ValueError(
            f"power_bins 必须是 bin dict 列表，实际类型 {type(power_bins).__name__}: {power_bins!r}"
        )

    usable = _collect_usable_bins(power_bins, lo, hi)
    if len(usable) < _MIN_USABLE_BINS:
        return {
            "available": False,
            "n_bins": len(usable),
            "reason": "insufficient_bins",
            "flatness_db": None,
        }

    max_power = min_power = usable[0][1]
    max_at_mhz = min_at_mhz = usable[0][0]
    for freq, power in usable:
        if power > max_power:
            max_power, max_at_mhz = power, freq
        if power < min_power:
            min_power, min_at_mhz = power, freq

    flatness_db = max_power - min_power
    passed = flatness_db <= limit
    return {
        "flatness_db": flatness_db,
        "limit_db": limit,
        "pass": passed,
        "n_bins": len(usable),
        "max_at_mhz": max_at_mhz,
        "min_at_mhz": min_at_mhz,
        "violation": not passed,
    }
