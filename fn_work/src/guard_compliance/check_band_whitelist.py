"""频段白名单校验（2.4G/5.8G 法定频段）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math

# 无人机法定频段白名单（MHz，闭区间，边界值本身合法）
# 依据：工信部无〔2023〕252 号文——2.4G: 2400–2483.5 MHz；5.8G: 5725–5829 MHz
BAND_WHITELIST: tuple[tuple[float, float], ...] = (
    (2400.0, 2483.5),
    (5725.0, 5829.0),
)

_SHAPE_ERRORS = (
    "形状错误: band_config 不是 dict 或缺失 'bands' 键",
    "形状错误: bands 为空列表",
    "形状错误: bands 不是 list/tuple",
)

# 形状错违例携带原值 repr 的最大长度（超出截断，避免超长输入撑爆违例清单）
_SHAPE_VALUE_REPR_LIMIT = 60


def _short_repr(value: object, limit: int = _SHAPE_VALUE_REPR_LIMIT) -> str:
    """repr 截断到 limit 字符：形状错违例须携带原值便于审计定位，但不无限长。"""
    text = repr(value)
    return text if len(text) <= limit else text[:limit]


def _is_finite_real(value: object) -> bool:
    """端点数值判定：int/float 且非 bool 且有限。

    字符串/bytes 不得经 float() 强转后混入白名单比较（"2400" 不是频段端点），
    bool 是 int 子类但语义是开关（True→1.0 会误报越界而非形状错），NaN/±inf
    无法参与区间比较——以上一律判形状错。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def check_band_whitelist(band_config: dict) -> dict:
    """频段白名单纯校验：目标频段必须完全落在法定白名单内（闭区间，边界合法）。

    Args:
        band_config: {"bands": [(start, stop), ...]}，单位 MHz，每个元素为 (start, stop)。

    Returns:
        {
            "status": "pass" | "violation",
            "violations": [{"band": (start, stop) | 原始值, "reason": str}, ...],
            "whitelist": [(2400.0, 2483.5), (5725.0, 5829.0)],
        }

    不抛异常：bands 缺失/空/元素逆序等形状错误一律计入 violations 并返回 violation；
    bands 整体形状错时 reason 携带原值 repr（截断），端点必须是非 bool 的有限数值。
    """
    violations: list[dict] = []

    if not isinstance(band_config, dict) or "bands" not in band_config:
        return {
            "status": "violation",
            "violations": [
                {
                    "band": None,
                    "reason": f"{_SHAPE_ERRORS[0]}（原值: {_short_repr(band_config)}）",
                }
            ],
            "whitelist": list(BAND_WHITELIST),
        }

    bands = band_config["bands"]
    if not isinstance(bands, (list, tuple)):
        return {
            "status": "violation",
            "violations": [
                {
                    "band": bands,
                    "reason": f"{_SHAPE_ERRORS[2]}（原值: {_short_repr(bands)}）",
                }
            ],
            "whitelist": list(BAND_WHITELIST),
        }
    if len(bands) == 0:
        return {
            "status": "violation",
            "violations": [{"band": [], "reason": _SHAPE_ERRORS[1]}],
            "whitelist": list(BAND_WHITELIST),
        }

    for band in bands:
        if not (isinstance(band, (list, tuple)) and len(band) == 2):
            violations.append(
                {"band": band, "reason": f"形状错误: 频段元素不是 (start, stop) 二元组: {band!r}"}
            )
            continue
        start, stop = band
        # 端点严格要求数值类型：不得让 "2400"/b"2400"/True/NaN 借 float() 强转混入比较
        if not (_is_finite_real(start) and _is_finite_real(stop)):
            violations.append(
                {
                    "band": band,
                    "reason": f"形状错误: 频段端点非法（须为非 bool 的有限数值）: {band!r}",
                }
            )
            continue
        try:
            start_f, stop_f = float(start), float(stop)
        except OverflowError:
            violations.append(
                {
                    "band": band,
                    "reason": f"形状错误: 频段端点数值超出可表示范围: {band!r}",
                }
            )
            continue
        if start_f > stop_f:
            violations.append(
                {
                    "band": (start_f, stop_f),
                    "reason": f"形状错误: 频段端点逆序 (start > stop): {start_f} > {stop_f}",
                }
            )
            continue
        # 完全落在任一白名单区间内（闭区间，边界值合法）
        if not any(lo <= start_f and stop_f <= hi for lo, hi in BAND_WHITELIST):
            violations.append(
                {
                    "band": (start_f, stop_f),
                    "reason": (
                        f"频段 {start_f}–{stop_f} MHz 未完全落在法定频段白名单内"
                        "（2.4G: 2400–2483.5 MHz；5.8G: 5725–5829 MHz，"
                        "依据工信部无〔2023〕252 号文，闭区间）"
                    ),
                }
            )

    return {
        "status": "pass" if not violations else "violation",
        "violations": violations,
        "whitelist": list(BAND_WHITELIST),
    }
