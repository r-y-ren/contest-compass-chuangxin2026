"""档位→功率单调性校验（违例列表）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math


def _is_finite_real(value: object) -> bool:
    """有限实数判定：int/float 且非 bool；float 还须有限（NaN/±inf 一律非法）。

    int 天然有限（不经过 float 转换，天文数字也不抛 OverflowError），
    bool 是 int 的子类但语义上是开关而非量值，故显式排除。
    超出 float 表示范围的超大 int 由此处的 _as_float 兜底按形状错拒收。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _as_float(value: int | float) -> float:
    """把已通过有限实数判定的量值转为 float；超大 int 触发 OverflowError 由调用方按形状错处理。"""
    return float(value)


def _shape(detail: str) -> list[dict]:
    """形状错统一出口：单条 {error: 'shape', detail: ...}，结果由上层转拒用。"""
    return [{"error": "shape", "detail": detail}]


def check_monotonicity(points: list, tolerance_db: float = 0.0) -> list:
    """档位→功率单调性纯校验（违例列表）。

    对有序 (gain_step, power_dbm) 序列做非降校验：后续档功率不得低于前档，
    允许 tolerance_db 容差（默认 0.0 即严格非降；降幅恰等于容差不算违例）。
    逐点只比较相邻元素，只按传入顺序、绝不按档位键排序（档位可为 str 或数值，
    仅作为标签透传）。返回逐点违例列表，空列表即单调。

    每条违例含：index（违例点下标）、gain_step（档位）、power_dbm（本点功率）、
    prev_power_dbm（前点功率）、drop_db（降幅=前点-本点）。

    不抛异常：形状错（points 非序列/空序列/元素非二元组/功率非有限实数或为
    bool/容差非法或为负/功率超出 float 可表示范围）返回单条违例
    {error: 'shape', detail: ...} 并短路。
    """
    if not _is_finite_real(tolerance_db):
        return _shape(f"容差 tolerance_db 应为有限实数，实际为 {tolerance_db!r}")
    if tolerance_db < 0:  # -0.0 < 0 为 False，按 0 对待不违例
        return _shape(f"容差 tolerance_db 须为非负数，实际为 {tolerance_db!r}")
    if not isinstance(points, (list, tuple)):
        return _shape(f"points 应为 (档位, 功率) 序列，实际为 {type(points).__name__}")
    if len(points) == 0:
        return _shape("points 为空序列：单调性校验至少需要一个 (档位, 功率) 样本")

    prev_power = None
    prev_power_float: float | None = None
    violations: list[dict] = []
    for index, item in enumerate(points):
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            return _shape(f"第 {index} 个元素应为 (档位, 功率) 二元组，实际为 {item!r}")
        step, power = item
        if not _is_finite_real(power):
            return _shape(
                f"第 {index} 个元素功率应为有限实数（bool 除外），实际为 {power!r}"
            )
        try:
            power_float = _as_float(power)
        except OverflowError:
            return _shape(
                f"第 {index} 个元素功率超出 float 可表示范围（超大数值无法比较降幅），"
                f"实际为 {power!r}"
            )
        if prev_power is not None:
            drop_db = prev_power_float - power_float
            if drop_db > tolerance_db:
                violations.append(
                    {
                        "index": index,
                        "gain_step": step,
                        "power_dbm": power,
                        "prev_power_dbm": prev_power,
                        "drop_db": drop_db,
                    }
                )
        prev_power = power
        prev_power_float = power_float
    return violations
