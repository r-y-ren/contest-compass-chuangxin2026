"""单点退化计算（sigmoid 悬崖，域外夹紧+标注）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math

__all__ = ["apply_cliff_model"]

_DEFAULT_MODEL_PARAMS: dict = {"base_per": 0.01, "threshold_db": 10.0, "softness_db": 2.0}
_JSR_DOMAIN_DB = 100.0  # 有效 JSR 域 [-100, 100] dB，域外夹紧到边界并置 clamped
_PER_CEILING = math.nextafter(1.0, 0.0)  # per ∈ [0,1) 的数值上界（防 sigmoid 舍入到 1.0）


def _as_finite_number(value, name: str) -> float:
    """模型参数归一为有限 float：bool/非数值/NaN/±inf 一律 ValueError（参数域拒绝）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"model_params.{name} 必须为有限数值，收到 {value!r}")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"model_params.{name} 超出 float 可表示范围") from exc
    if not math.isfinite(number):
        raise ValueError(f"model_params.{name} 必须为有限数值（NaN/inf 拒绝），收到 {number!r}")
    return number


def _stable_sigmoid(t: float) -> float:
    """数值稳定 sigmoid S(t)=1/(1+e^−t)：按 t 符号分支，两侧 exp 参数均 ≤0，绝不溢出。"""
    if t >= 0.0:
        return 1.0 / (1.0 + math.exp(-t))
    z = math.exp(t)
    return z / (1.0 + z)


def apply_cliff_model(state: dict, model_params: dict | None) -> dict:
    """单点退化计算（sigmoid 悬崖）。

    PER = base_per + (1−base_per)·S(JSR−threshold)，S(x)=1/(1+exp(−x/softness))。
    - state：{'jsr_db': float, 'style': str}；style 仅记录透传（模型参数统一，不做样式分档）。
    - model_params：None 或缺键时取 {'base_per': 0.01, 'threshold_db': 10.0, 'softness_db': 2.0}。
    - JSR 域 [-100, 100] dB：域外夹紧到边界并在输出置 clamped=True，不抛出。
    - ValueError：state 非 dict / 缺 jsr_db / jsr_db 非有限数值；参数 NaN/inf、softness ≤ 0、
      base_per 超出 [0,1)。
    - 输出：{'per': float∈[0,1), 'jsr_db': 夹紧后有效值, 'clamped': bool, 'style': 透传（若有）}。
    """
    if not isinstance(state, dict):
        raise ValueError(f"state 必须为 dict（含 jsr_db），收到 {type(state).__name__}")
    if "jsr_db" not in state:
        raise ValueError("state 缺 jsr_db 字段，无法计算悬崖退化")

    raw_jsr = state["jsr_db"]
    if isinstance(raw_jsr, bool) or not isinstance(raw_jsr, (int, float)):
        raise ValueError(f"state.jsr_db 必须为有限数值（NaN/inf/非数值拒绝），收到 {raw_jsr!r}")
    try:
        jsr = float(raw_jsr)
    except OverflowError as exc:
        raise ValueError("state.jsr_db 超出 float 可表示范围") from exc
    if not math.isfinite(jsr):
        raise ValueError(f"state.jsr_db 必须为有限数值（NaN/inf 拒绝），收到 {jsr!r}")

    params = dict(_DEFAULT_MODEL_PARAMS)
    if model_params is not None:
        if not isinstance(model_params, dict):
            raise ValueError(
                f"model_params 必须为 dict 或 None，收到 {type(model_params).__name__}"
            )
        for key in _DEFAULT_MODEL_PARAMS:
            if key in model_params:
                params[key] = model_params[key]

    base_per = _as_finite_number(params["base_per"], "base_per")
    threshold_db = _as_finite_number(params["threshold_db"], "threshold_db")
    softness_db = _as_finite_number(params["softness_db"], "softness_db")
    if softness_db <= 0.0:
        raise ValueError(f"model_params.softness_db 必须为正数（悬崖软度），收到 {softness_db!r}")
    if not 0.0 <= base_per < 1.0:
        raise ValueError(f"model_params.base_per 必须落在 [0,1)，收到 {base_per!r}")

    clamped = jsr < -_JSR_DOMAIN_DB or jsr > _JSR_DOMAIN_DB
    effective_jsr = max(-_JSR_DOMAIN_DB, min(_JSR_DOMAIN_DB, jsr))

    sigmoid = _stable_sigmoid((effective_jsr - threshold_db) / softness_db)
    per = base_per + (1.0 - base_per) * sigmoid
    # 数值护栏：sigmoid 下溢到 0/舍入到 1 时把 per 压回 [0,1)
    per = min(max(per, 0.0), _PER_CEILING)

    result = {"per": per, "jsr_db": effective_jsr, "clamped": clamped}
    if "style" in state:
        result["style"] = state["style"]
    return result
