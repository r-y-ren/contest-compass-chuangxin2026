"""纯计算：目标衰减→（粗档二态 × 细档标定）组合与残差，不可达返回 None——规约详见 fn_docs/responsibility.md。

择优规则（文档化）：
- 候选全集 = {粗档旁路(0), 粗档接入(coarse_db)} × fine_steps_db 各档位；细档实际值优先取
  cal_table[档位]（测量值），缺键按标称并标注 fine_from='nominal'；cal_table 键与档位列表
  完全不匹配（0 键命中）→ 结果另附 'cal_unused': True（部分命中不标，B8低#5）。
- 取 |residual_db| 最小者胜（残差最小者优先）；跨态平手选粗档接入（'in'）；同态平手按
  fine_steps_db 列表序靠前者胜（升序列即较小档位/正残差欠衰减）。经验法则
  "target ≥ coarse_db/2 用粗档"被残差最优先涵盖并在细档更优时被修正（如 16.5dB）。
- 不可达：target > coarse_db + max(细档实际值)（空档表 max=0）→ 返回 None（上层转
  AttenuationError）。cal_table 单调性不检查（B2 单调工具属另函数）。
- 校验：target 为 bool/非数/NaN/负 → ValueError（+inf 视为超域 → None）；domain 形状错
  （非 dict、coarse_db 非 positive 有限数、fine_steps_db 非 list/tuple、档位元素非有限非负数、
  fine_granularity_db 非正有限数）→ ValueError；cal_table 非 dict 或值非有限数 → ValueError。
  fine_granularity_db 仅描述步进特征，不参与计算（档位以 fine_steps_db 列表为准，按序判可达）。
"""
from __future__ import annotations

import math

_DEFAULT_COARSE_DB = 30.0
_DEFAULT_FINE_STEPS_DB = [float(step) for step in range(0, 21)]  # 0.0..20.0，步进 1.0
_DEFAULT_FINE_GRANULARITY_DB = 1.0


def _is_real(value: object) -> bool:
    """真整数/浮点（排除 bool）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite_float(name: str, value: object) -> float:
    if not _is_real(value) or not math.isfinite(value):
        raise ValueError(f"{name} 必须为有限实数，实际: {value!r}")
    return float(value)


def plan_attenuator_combo(
    target_db: float,
    domain: dict | None = None,
    cal_table: dict | None = None,
) -> dict | None:
    """目标衰减→档位组合纯计算：粗档二态 × 细档标定择档 + 实达/残差；不可达返回 None。"""
    # ---- target 校验：bool/非数/NaN/负 → ValueError ----
    if not _is_real(target_db):
        raise ValueError(f"target_db 必须为实数，实际: {target_db!r}")
    target = float(target_db)
    if math.isnan(target):
        raise ValueError("target_db 不能为 NaN")
    if target < 0.0:
        raise ValueError(f"target_db 不能为负，实际: {target}")

    # ---- domain 合并缺省（缺键用默认）并校验形状 ----
    if domain is None:
        coarse_db, fine_steps_raw, fine_granularity_db = (
            _DEFAULT_COARSE_DB,
            list(_DEFAULT_FINE_STEPS_DB),
            _DEFAULT_FINE_GRANULARITY_DB,
        )
    else:
        if not isinstance(domain, dict):
            raise ValueError(f"domain 必须为 dict，实际: {type(domain).__name__}")
        coarse_db = _finite_float("domain['coarse_db']", domain.get("coarse_db", _DEFAULT_COARSE_DB))
        steps = domain.get("fine_steps_db", _DEFAULT_FINE_STEPS_DB)
        if not isinstance(steps, (list, tuple)):
            raise ValueError(f"domain['fine_steps_db'] 必须为 list/tuple，实际: {type(steps).__name__}")
        fine_steps_raw = list(steps)
        fine_granularity_db = _finite_float(
            "domain['fine_granularity_db']", domain.get("fine_granularity_db", _DEFAULT_FINE_GRANULARITY_DB)
        )
    if coarse_db <= 0.0:
        raise ValueError(f"domain['coarse_db'] 必须为正，实际: {coarse_db}")
    if fine_granularity_db <= 0.0:
        raise ValueError(f"domain['fine_granularity_db'] 必须为正，实际: {fine_granularity_db}")
    fine_steps: list[float] = []
    for index, step in enumerate(fine_steps_raw):
        value = _finite_float(f"domain['fine_steps_db'][{index}]", step)
        if value < 0.0:
            raise ValueError(f"细档档位不能为负，实际: {value}")
        fine_steps.append(value)

    # ---- cal_table：键=细档标称档位，值=实际衰减；缺键→标称（逐档标注）----
    cal: dict[float, float] = {}
    if cal_table is not None:
        if not isinstance(cal_table, dict):
            raise ValueError(f"cal_table 必须为 dict 或 None，实际: {type(cal_table).__name__}")
        for key, actual in cal_table.items():
            cal[key] = _finite_float(f"cal_table[{key!r}]", actual)

    def resolve(step: float) -> tuple[float, str]:
        if step in cal:
            return cal[step], "calibrated"
        return step, "nominal"

    candidates: list[tuple[float, str]] = [resolve(step) for step in fine_steps]
    max_fine_actual = max((actual for actual, _ in candidates), default=0.0)

    # B8低#5：cal_table 键与档位列表完全不匹配（0 键命中——如步进/口径错表）→
    # 结果如实标注 'cal_unused': True（静默全回退标称易掩盖用错标定表）；部分命中不标。
    cal_unused = bool(cal) and not any(source == "calibrated" for _, source in candidates)

    # ---- 不可达：超出 粗档最大 + 细档实际最大（按实际值判域顶）→ None ----
    if target > coarse_db + max_fine_actual:
        return None

    def best_for(coarse_value: float) -> tuple[float, float, str, float]:
        """返回 (|残差|, 细档实际值, fine_from, 细档标称档位)；空档表→细档按 0 标称。"""
        best: tuple[float, float, str, float] | None = None
        for step, (actual, source) in zip(fine_steps, candidates):
            error = abs(target - (coarse_value + actual))
            if best is None or error < best[0]:  # 严格小于：列表序靠前者平手胜
                best = (error, actual, source, step)
        if best is None:
            return (abs(target - coarse_value), 0.0, "nominal", 0.0)
        return best

    in_best = best_for(coarse_db)
    bypass_best = best_for(0.0)
    if in_best[0] <= bypass_best[0]:  # 跨态平手选粗档接入
        coarse_state, coarse_value, chosen = "in", coarse_db, in_best
    else:
        coarse_state, coarse_value, chosen = "bypass", 0.0, bypass_best
    _, fine_actual, fine_from, fine_step = chosen
    achieved = coarse_value + fine_actual
    result = {
        "coarse": coarse_state,
        "coarse_db": coarse_value,
        "fine_step_db": fine_step,
        "fine_actual_db": fine_actual,
        "achieved_db": achieved,
        "residual_db": target - achieved,  # 正=欠衰减
        "fine_from": fine_from,
    }
    if cal_unused:
        result["cal_unused"] = True  # 标定表整体未用上（0 键命中档位列表）
    return result
