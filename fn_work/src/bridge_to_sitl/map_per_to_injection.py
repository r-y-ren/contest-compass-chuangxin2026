"""PER→注入参数映射纯函数（分段线性+饱和）——重写规约与签名意图详见 fn_docs/responsibility.md（R53 叶子；调用方 bridge_to_sitl）。

映射口径（R53：PER 台阶→SITL 丢包/时延注入参数表）：

- 丢包通道（分段线性+饱和）：``packet_loss = min(per, max_packet_loss)``——
  ``per < max`` 线性直通；``per >= max`` 饱和钳位至 ``max_packet_loss`` 并标注
  ``'saturated': True``（未饱和档显式落 ``'saturated': False``，全表 schema 统一）；
- 时延通道（|Δlevel| 线性）：``latency_ms = base_latency_ms +
  |level_db - ref_level_db| * latency_per_db_ms``——参考电平 ``ref_level_db``
  取 ``params`` 键，缺省取 ``steps`` 首档 ``level_db``（首档时延即基线）；
- 输出表逐档携带原始 ``per``/``level_db`` 便于溯源对照。

错误契约（ValueError，纯函数不抛其他）：

- ``steps`` 非 list / 档非 dict / 缺 ``per`` 或 ``level_db``；
- ``per`` 为 bool/非实数/NaN/±inf/负(<0)/越界(>1)——合法域 [0, 1] 闭区间；
- ``level_db`` 为 bool/非实数/NaN/±inf；
- ``params`` 非 dict；``max_packet_loss``/``latency_per_db_ms``/``base_latency_ms``/
  ``ref_level_db`` 在且非有限实数，或 ``max_packet_loss`` 越界 (0, 1]、
  时延参数为负；
- ``steps`` 为空 list → 合法输入返回空表 ``[]``（空台阶无注入项）。
"""
from __future__ import annotations

import math
from numbers import Real

__all__ = ["map_per_to_injection"]

#: 丢包饱和上限缺省（PER 电平最高也只注入 95% 丢包——保 SITL 链路可控）。
_DEFAULT_MAX_PACKET_LOSS = 0.95
#: 每 dB 电平差映射的时延增量缺省（ms/dB）。
_DEFAULT_LATENCY_PER_DB_MS = 2.0
#: 基线时延缺省（ms）。
_DEFAULT_BASE_LATENCY_MS = 5.0


def _finite_float(name: str, value: object) -> float:
    """数值校验：拒 bool/非实数/NaN/±inf，返回 float。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} 必须为实数（bool/非数值一律拒绝）：{value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} 必须为有限数（拒 NaN/±inf）：{value!r}")
    return number


def map_per_to_injection(steps: list, params: dict) -> list:
    """PER–电平台阶 → SITL 丢包/时延注入参数表（纯函数，分段线性+饱和）。

    Args:
        steps: 台阶数据 ``[{'per': float∈[0,1], 'level_db': float}, ...]``；
            空 list → 空 表 ``[]``。
        params: 映射参数——``max_packet_loss``（缺省 0.95，域 (0, 1]）、
            ``latency_per_db_ms``（缺省 2.0，≥0）、``base_latency_ms``
            （缺省 5.0，≥0）、``ref_level_db``（缺省取 steps 首档 level_db）。

    Returns:
        ``[{'per', 'level_db', 'packet_loss', 'latency_ms', 'saturated'}, ...]``
        ——逐档一一对应：``packet_loss=min(per, max)``、
        ``latency_ms=base+|level-ref|*k``、``per>=max`` 档 ``saturated=True``。

    Raises:
        ValueError: 形状/数值域错（详见模块 docstring 错误契约）。
    """
    if not isinstance(steps, list):
        raise ValueError(
            f"steps 必须为 list[{'per','level_db'} 台阶 dict]，实际: {type(steps).__name__}"
        )
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(f"params 必须为 dict | None（映射参数），实际: {type(params).__name__}")

    max_loss = _finite_float(
        "params['max_packet_loss']", params.get("max_packet_loss", _DEFAULT_MAX_PACKET_LOSS)
    )
    if not (0.0 < max_loss <= 1.0):
        raise ValueError(f"params['max_packet_loss'] 必须在 (0, 1] 内，实际: {max_loss!r}")
    per_db_ms = _finite_float(
        "params['latency_per_db_ms']",
        params.get("latency_per_db_ms", _DEFAULT_LATENCY_PER_DB_MS),
    )
    if per_db_ms < 0.0:
        raise ValueError(f"params['latency_per_db_ms'] 必须非负，实际: {per_db_ms!r}")
    base_ms = _finite_float(
        "params['base_latency_ms']", params.get("base_latency_ms", _DEFAULT_BASE_LATENCY_MS)
    )
    if base_ms < 0.0:
        raise ValueError(f"params['base_latency_ms'] 必须非负，实际: {base_ms!r}")

    # 参考电平：显式给出则先行校验；缺省延后到首档（空表不取参考）。
    ref_level = (
        _finite_float("params['ref_level_db']", params["ref_level_db"])
        if "ref_level_db" in params
        else None
    )

    injections: list = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"steps[{i}] 必须为 dict，实际: {type(step).__name__}")
        if "per" not in step:
            raise ValueError(f"steps[{i}] 缺 'per' 字段（PER 台阶必填）")
        if "level_db" not in step:
            raise ValueError(f"steps[{i}] 缺 'level_db' 字段（电平台阶必填）")
        per = _finite_float(f"steps[{i}]['per']", step["per"])
        if per < 0.0 or per > 1.0:
            raise ValueError(f"steps[{i}]['per'] 必须在 [0, 1] 内（拒负/越界），实际: {per!r}")
        level = _finite_float(f"steps[{i}]['level_db']", step["level_db"])
        if ref_level is None:  # 缺省参考：首档电平（首档时延即基线）
            ref_level = level
        injections.append(
            {
                "per": per,
                "level_db": level,
                "packet_loss": float(min(per, max_loss)),
                "latency_ms": float(base_ms + abs(level - ref_level) * per_db_ms),
                "saturated": bool(per >= max_loss),
            }
        )
    return injections
