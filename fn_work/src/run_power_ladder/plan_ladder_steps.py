"""功率阶梯档位计划展开（GB 42590 §5.11：−5dB 起、5dB 步、0dBm 红线截断）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
from numbers import Real

__all__ = ["PlanError", "plan_ladder_steps"]

_GB_START_OFFSET_DB = -5.0  # GB 缺省起始：相对被测链路发射功率 −5dB
_GB_STEP_DB = 5.0  # GB 缺省步长 5dB
_DEFAULT_MAX_STEPS = 30  # 防失控档数上限
_REDLINE_DB = 0.0  # 计划红线：任何档位不得超过 0dBm
_EPS = 1e-9  # 红线/网格命中的浮点容差


class PlanError(Exception):
    """计划域错误：起始档位（或 GB 缺省时被测链路功率本身）高于 0dBm 红线，拒绝出计划。"""


def _finite_float(name: str, value: object) -> float:
    """数值参数校验：拒 bool、非实数、NaN/±inf、超 float 域（如 10**400），返回 float。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} 必须为实数（bool/非数值一律拒绝）：{value!r}")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} 超出 float 可表示域：{value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} 必须为有限数（拒 NaN/±inf）：{value!r}")
    return number


def _rung(index: int, target_db: float, link_db: float, note: str) -> dict:
    """单档记录：序号从 0、绝对目标功率、相对被测链路功率、口径标注。"""
    return {
        "step": index,
        "target_db": float(target_db),
        "relative_db": float(target_db - link_db),
        "note": note,
    }


def plan_ladder_steps(link_power_db: float, params: dict | None = None) -> dict:
    """功率阶梯档位计划展开（纯函数，不做任何仪器操作）。

    GB 42590 §5.11 缺省口径：起始 = link_power_db − 5（相对被测链路发射功率 −5dB）、
    步长 5dB 递增，直至 ``max_steps``（默认 30，防失控）。``params`` 含
    ``start_db``/``step_db``/``stop_db`` 任一键即切换自定义模式（``note='custom'``，
    未给的键仍取 GB 缺省；仅给 ``max_steps`` 不触发自定义，仍为 GB 口径）。

    红线（计划不越 0dBm）：任何档位 ``target_db > 0.0`` → 自该档起截断，返回
    ``truncated_at``（被丢弃档的索引）与 ``redline_hit=True``；``target_db == 0.0``
    恰过红线不截。起始档位本身高于 0 → PlanError；GB 缺省口径下被测链路功率
    ``link_power_db > 0`` 本身即异常（含起始 = link−5 > 0 的情形）→ 同样 PlanError。

    ``stop_db`` 口径：网格命中 stop → 该档恰为 stop 并终止；未命中步进网格 → 补
    最后一档钳位至 stop（最后档恰为 stop、不越 stop）；``stop_db > 0`` 时红线优先
    （截断在 0 红线，不输出越线档）。``max_steps`` 用尽且未触红线视为完整计划
    （``truncated_at=None``、``redline_hit=False``）。

    :param link_power_db: 被测链路发射功率（dBm），有限实数（bool/NaN/±inf 拒绝）
    :param params: 可选覆盖 ``start_db``/``step_db``/``stop_db``/``max_steps``
    :return: ``{'steps': [{'step', 'target_db', 'relative_db', 'note'}, ...],
        'truncated_at': int|None, 'redline_hit': bool, 'note': 'gb42590'|'custom'}``
    :raises PlanError: 起始档位 > 0；GB 口径下 link_power_db > 0（链路功率本身高异常）
    :raises ValueError: link/step/start/stop 为 bool/非实数/NaN/±inf；step_db ≤ 0；
        stop_db < start_db（无法构成上行阶梯）；max_steps 非正 int（bool 拒）
    """
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(f"params 必须为 dict 或 None：{params!r}")

    link = _finite_float("link_power_db", link_power_db)

    custom = any(key in params for key in ("start_db", "step_db", "stop_db"))
    note = "custom" if custom else "gb42590"

    step = _finite_float("step_db", params.get("step_db", _GB_STEP_DB))
    if step <= 0.0:
        raise ValueError(f"step_db 必须为正数（≤0 拒绝）：{step!r}")

    if "start_db" in params:
        start = _finite_float("start_db", params["start_db"])
    else:
        start = link + _GB_START_OFFSET_DB

    stop = _finite_float("stop_db", params["stop_db"]) if "stop_db" in params else None

    max_steps = params.get("max_steps", _DEFAULT_MAX_STEPS)
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps <= 0:
        raise ValueError(f"max_steps 必须为正 int（bool/非 int/≤0 拒绝）：{max_steps!r}")

    if start > _REDLINE_DB + _EPS:
        raise PlanError(f"起始档位 {start:g}dBm 高于 0dBm 红线，拒绝出计划")
    if not custom and link > _REDLINE_DB + _EPS:
        raise PlanError(
            f"被测链路功率 {link:g}dBm 本身高于 0dBm 红线（链路功率高异常），拒绝出计划"
        )
    if stop is not None and stop < start - _EPS:
        raise ValueError(f"stop_db({stop:g}) 低于 start_db({start:g})，无法构成上行阶梯")

    steps: list[dict] = []
    truncated_at: int | None = None
    redline_hit = False

    for index in range(max_steps):
        target = start + index * step
        if target > _REDLINE_DB + _EPS:  # 红线优先于 stop：0.0 恰过不截
            truncated_at = index
            redline_hit = True
            break
        if stop is not None and target >= stop - _EPS:
            final = float(stop)  # 命中/越界统一取 stop：最后档恰为 stop、不越 stop
            if final > _REDLINE_DB + _EPS:  # stop 本身越红线（如 stop_db>0）
                truncated_at = index
                redline_hit = True
                break
            steps.append(_rung(index, final, link, note))
            break
        steps.append(_rung(index, target, link, note))

    return {"steps": steps, "truncated_at": truncated_at, "redline_hit": redline_hit, "note": note}
