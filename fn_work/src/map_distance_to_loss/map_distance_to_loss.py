"""距离序列→L(d) 损耗→档位计划（远场→近场演变）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
from numbers import Real

from .compute_pathloss import compute_pathloss
from src.set_channel_attenuation.plan_attenuator_combo import plan_attenuator_combo

__all__ = ["map_distance_to_loss"]

# 与 plan_attenuator_combo 缺省域保持一致（仅用于不可达提示文案；择档/可达判据仍以该函数为准）
_DEFAULT_COARSE_DB = 30.0
_DEFAULT_FINE_STEPS_DB = [float(step) for step in range(0, 21)]


def _validate_distance(index: int, value: object) -> float:
    """距离元素校验：拒 bool/非实数/NaN/±inf/超 float 域（如 10**400）/≤0，返回 float。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"distances[{index}] 必须为实数（bool/非数值一律拒绝）：{value!r}")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"distances[{index}] 超出 float 可表示域：{value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"distances[{index}] 必须为有限数（拒 NaN/±inf）：{value!r}")
    if number <= 0.0:
        raise ValueError(f"distances[{index}] 必须为正距离（米）：{number!r}")
    return number


def _reachable_ceiling_db(domain: dict | None, cal_table: dict | None) -> float:
    """镜像 plan_attenuator_combo 的可达判据（粗档 + 细档实际最大），仅用于不可达提示。"""
    if isinstance(domain, dict):
        coarse = domain.get("coarse_db", _DEFAULT_COARSE_DB)
        steps = domain.get("fine_steps_db", _DEFAULT_FINE_STEPS_DB)
    else:
        coarse, steps = _DEFAULT_COARSE_DB, _DEFAULT_FINE_STEPS_DB
    cal = cal_table if isinstance(cal_table, dict) else {}
    max_fine = max((float(cal.get(step, step)) for step in steps), default=0.0)
    return float(coarse) + max_fine


def map_distance_to_loss(distances, model_params: dict) -> dict:
    """距离序列→L(d) 损耗→衰减档位计划（纯函数：只产计划，不下发任何仪器操作）。

    逐点口径：
    1. ``compute_pathloss(d, d0_m, l0_db, n, x_sigma, seed)`` 参数透传；**seed 序列口径**
       （文档化，为可复现）：逐点 ``seed = base_seed + i``（``base_seed=None`` → 全部
       ``seed=None``，系统熵播种、可运行但不可复现）——同一 (distances, base_seed)
       两次调用逐点一致。
    2. 损耗即目标衰减：每点 ``plan_attenuator_combo(loss_db, domain, cal_table)`` 择档
       （set_channel_attenuation 的计划语义，本函数不下发）。不可达点（combo 为 None）
       → 该点 ``'reachable': False`` 并附可达域提示（``hint``）；**不抛出**，整计划继续。
    3. ``x_sigma_db = loss_db − 确定部分``（阴影抽样值；``x_sigma`` None/0 时恰为 0.0）。
       单调演变断言不强制——X_σ 抽样可打破损耗随距离单调，如实输出（不排序不整形）。

    :param distances: 距离序列（米），list/tuple；每个元素必须为正有限实数（bool 拒）
    :param model_params: 模型参数 dict——``d0_m``/``l0_db``/``n``/``x_sigma``/``base_seed``
        及 ``domain``/``cal_table``（cal_table 亦经 model_params 传入；缺省均按 None）
    :return: ``{'points': [{'d_m', 'loss_db', 'x_sigma_db', 'combo', 'reachable'
        [, 'hint' 仅不可达点]}...], 'model': {'d0_m', 'l0_db', 'n', 'x_sigma',
        'base_seed'}, 'unreachable_count': N}``
    :raises ValueError: distances 非 list/tuple、为空或含非法距离（≤0/NaN/±inf/bool/
        非实数/超 float 域）；model_params 非 dict；base_seed 非 int/None（bool 拒）；
        compute_pathloss 参数/域错透传（d<d0 的点、n≤0 等）；plan_attenuator_combo
        domain/cal_table 形状错透传。
    """
    if not isinstance(distances, (list, tuple)):
        raise ValueError(f"distances 必须为 list/tuple：{type(distances).__name__}")
    if not distances:
        raise ValueError("distances 不能为空：距离演变场景至少需要一个距离点")
    if not isinstance(model_params, dict):
        raise ValueError(f"model_params 必须为 dict：{type(model_params).__name__}")

    d0_m = model_params.get("d0_m")
    l0_db = model_params.get("l0_db")
    n = model_params.get("n")
    x_sigma = model_params.get("x_sigma")
    base_seed = model_params.get("base_seed")
    domain = model_params.get("domain")
    cal_table = model_params.get("cal_table")

    clean_distances = [_validate_distance(index, d) for index, d in enumerate(distances)]

    # base_seed 提前校验：bool + int 会静默变 int（True+0=1），须显式拒绝
    if base_seed is not None and (isinstance(base_seed, bool) or not isinstance(base_seed, int)):
        raise ValueError(f"base_seed 必须为 int 或 None（bool 拒）：{base_seed!r}")

    points: list[dict] = []
    unreachable_count = 0
    for i, d in enumerate(clean_distances):
        seed_i = None if base_seed is None else base_seed + i  # seed 序列口径
        loss_db = compute_pathloss(d, d0_m, l0_db, n, x_sigma, seed_i)
        deterministic = compute_pathloss(d, d0_m, l0_db, n, None)  # 确定部分（无阴影项）
        combo = plan_attenuator_combo(loss_db, domain, cal_table)
        reachable = combo is not None
        point = {
            "d_m": d,
            "loss_db": loss_db,
            "x_sigma_db": loss_db - deterministic,
            "combo": combo,
            "reachable": reachable,
        }
        if not reachable:
            unreachable_count += 1
            ceiling = _reachable_ceiling_db(domain, cal_table)
            point["hint"] = (
                f"目标衰减 loss_db={loss_db:.3f} dB 超出衰减器可达域上限 {ceiling:.3f} dB"
                "（粗档 + 细档实际最大）；可减小距离、降低模型损耗或扩展 domain/fine_steps_db"
            )
        points.append(point)

    return {
        "points": points,
        "model": {
            "d0_m": d0_m,
            "l0_db": l0_db,
            "n": n,
            "x_sigma": x_sigma,
            "base_seed": base_seed,
        },
        "unreachable_count": unreachable_count,
    }
