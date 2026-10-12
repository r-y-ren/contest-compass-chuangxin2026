"""默认值填充与单位规范化，产出下游唯一场景形状——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import copy
import math
from numbers import Integral

from .validate_scenario_schema import SCENARIO_STYLE_WHITELIST, ScenarioError

__all__ = ["BACKEND_WHITELIST", "normalize_scenario"]

# 后端白名单（strip().lower() 归一后比对）。
BACKEND_WHITELIST = frozenset({"auto", "b210", "sim", "replay"})

# 缺省值常量（上游 validate_scenario_schema 已把过关，此处只补缺不判域）。
DEFAULT_POWER_DBM = -10.0
DEFAULT_DURATION_S = 1.0
DEFAULT_DUTY_CYCLE = 0.5  # pulse 占空比缺省；统一填充保证场景形状唯一
DEFAULT_REPEATS = 1
DEFAULT_BACKEND = "auto"
DEFAULT_JUDGE_PER_THRESHOLD = 0.10  # PER>10% 判据缺省

# 输出键的规范顺序（未知键排在末尾按原序透传）。
_CANONICAL_KEY_ORDER = (
    "style",
    "fs",
    "freq_hz",
    "bandwidth_hz",
    "power_dbm",
    "duration_s",
    "duty_cycle",
    "repeats",
    "components",
    "backend",
    "judge_per_threshold",
)


def _to_float(field: str, value: object) -> float:
    """数值化宽容：int/float（拒 bool）与可解析数字 str（如 '2450'）均收为
    float；仍冲突（非数字 str/None/list/NaN/inf 等）抛 ScenarioError。"""
    if isinstance(value, bool):
        raise ScenarioError(
            f"{field} 类型冲突: 期望数值（int/float 或数字 str），"
            f"实际为 bool: {value!r}"
        )
    if isinstance(value, Integral):
        return float(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ScenarioError(
                f"{field} 数值非法: NaN/inf 无法规范化，实际值 {value!r}"
            )
        return value
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            raise ScenarioError(
                f"{field} 类型冲突: 仅数字 str 可宽容数值化，"
                f"实际为不可解析的 str: {value!r}"
            ) from None
        if not math.isfinite(parsed):
            raise ScenarioError(
                f"{field} 数值非法: str {value!r} 解析为 NaN/inf，无法规范化"
            )
        return parsed
    raise ScenarioError(
        f"{field} 类型冲突: 期望数值（int/float 或数字 str），"
        f"实际为 {type(value).__name__}: {value!r}"
    )


def _to_positive_int(field: str, value: object) -> int:
    """整型化宽容：Integral / 整值 float / 整数 str（含 '3.0'）均收为 int；
    仍冲突（bool/小数 str/None 等）抛 ScenarioError。"""
    if isinstance(value, bool):
        raise ScenarioError(
            f"{field} 类型冲突: 期望正 int，实际为 bool: {value!r}"
        )
    if isinstance(value, Integral):
        return int(value)
    parsed: float | None = None
    if isinstance(value, float):
        if math.isfinite(value):
            parsed = value
    elif isinstance(value, str):
        try:
            candidate = float(value.strip())
        except ValueError:
            candidate = None
        if candidate is not None and math.isfinite(candidate):
            parsed = candidate
    if parsed is not None and parsed.is_integer():
        return int(parsed)
    raise ScenarioError(
        f"{field} 类型冲突: 期望正 int（整值 float/整数 str 可宽容），"
        f"实际为 {type(value).__name__}: {value!r}"
    )


def normalize_scenario(valid: dict) -> dict:
    """默认值填充与规范化，产出下游唯一依赖的场景对象形状。

    输入: valid: dict，经 validate_scenario_schema 校验通过的场景 dict——
      - style: str，strip().lower() 小写归一（'TONE'→'tone'）；
      - fs: 必填数值化 float（无缺省——缺失即冲突）；
      - freq_hz: 若存在则数值化 float（'2450'→2450.0 宽容）；
      - bandwidth_hz: 若存在则数值化 float（带限类 bandwidth_hz 数值化）；
      - power_dbm: 缺省 -10.0；
      - duration_s: 缺省 1.0；
      - duty_cycle: 缺省 0.5（pulse 占空比，统一填充保形状唯一）；
      - repeats: 缺省 1（整型化宽容：整值 float/整数 str 亦收）；
      - backend: 缺省 'auto'；显式值 strip().lower() 归一（'SIM'→'sim'）
        后须落白名单 {'auto','b210','sim','replay'}；
      - judge_per_threshold: 缺省 0.10（PER>10% 判据）；
      - components: composite 必填；list 内 dict 分量递归同口径规范化；
      - 未知键保留透传（已由 validate 拒——此处保留防御）。
    输出: 全新深拷贝 dict（键按规范序排列）——任何改写都不污染入参。
    错误: ScenarioError——valid 非 dict / style 缺失或未知 / fs 缺失 /
      数值键类型仍冲突（宽容失败）/ backend 归一后不在白名单 /
      components 形状冲突；消息含字段名与原因。
    """
    if not isinstance(valid, dict):
        raise ScenarioError(
            f"输入形状错: 场景应为 dict，实际为 {type(valid).__name__}: {valid!r}"
        )

    # 深拷贝起步：所有改写落在副本上，绝不污染入参（含未知键与嵌套分量）。
    out = copy.deepcopy(valid)

    # style：小写归一（switch_style/synthesize_style 口径）；未知仍冲突。
    style = out.get("style")
    if not isinstance(style, str) or not style.strip():
        raise ScenarioError(
            f"style 类型冲突: 期望非空 str（七类白名单 "
            f"{sorted(SCENARIO_STYLE_WHITELIST)}），"
            f"实际为 {type(style).__name__}: {style!r}"
        )
    style_key = style.strip().lower()
    if style_key not in SCENARIO_STYLE_WHITELIST:
        raise ScenarioError(
            f"style 未知样式 {style!r}（七类白名单 "
            f"{sorted(SCENARIO_STYLE_WHITELIST)}，大小写不敏感）"
        )
    out["style"] = style_key

    # fs：必填数值化（fs 无缺省——缺失即冲突）。
    if "fs" not in out:
        raise ScenarioError("fs 缺失: 场景必含采样率 'fs'（数值 Hz），无缺省可填")
    out["fs"] = _to_float("fs", out["fs"])

    # 可选数值键：存在即数值化宽容（缺失不填缺省——freq/bandwidth 无缺省语义）。
    if "freq_hz" in out:
        out["freq_hz"] = _to_float("freq_hz", out["freq_hz"])
    if "bandwidth_hz" in out:
        out["bandwidth_hz"] = _to_float("bandwidth_hz", out["bandwidth_hz"])

    # 带缺省数值键：缺则填默认，有则数值化宽容。
    out["power_dbm"] = (
        _to_float("power_dbm", out["power_dbm"])
        if "power_dbm" in out
        else DEFAULT_POWER_DBM
    )
    out["duration_s"] = (
        _to_float("duration_s", out["duration_s"])
        if "duration_s" in out
        else DEFAULT_DURATION_S
    )
    out["duty_cycle"] = (
        _to_float("duty_cycle", out["duty_cycle"])
        if "duty_cycle" in out
        else DEFAULT_DUTY_CYCLE
    )
    out["repeats"] = (
        _to_positive_int("repeats", out["repeats"])
        if "repeats" in out
        else DEFAULT_REPEATS
    )
    out["judge_per_threshold"] = (
        _to_float("judge_per_threshold", out["judge_per_threshold"])
        if "judge_per_threshold" in out
        else DEFAULT_JUDGE_PER_THRESHOLD
    )

    # backend：缺省 'auto'；显式值 str 归一小写后须落白名单。
    if "backend" in out:
        backend = out["backend"]
        if not isinstance(backend, str):
            raise ScenarioError(
                f"backend 类型冲突: 期望 str，"
                f"实际为 {type(backend).__name__}: {backend!r}"
            )
        backend_key = backend.strip().lower()
        if backend_key not in BACKEND_WHITELIST:
            raise ScenarioError(
                f"backend 未知后端 {backend!r}（白名单 "
                f"{sorted(BACKEND_WHITELIST)}，归一小写后比对）"
            )
        out["backend"] = backend_key
    else:
        out["backend"] = DEFAULT_BACKEND

    # components：在册即递归规范化（分量同口径：缺省填充+归一+深拷贝）；
    # composite 必填（缺失即冲突——上游 validate 已拒，此处防御）。
    if "components" in out:
        components = out["components"]
        if not isinstance(components, list):
            raise ScenarioError(
                f"components 类型冲突: 期望 list，"
                f"实际为 {type(components).__name__}: {components!r}"
            )
        normalized_components = []
        for index, component in enumerate(components):
            if not isinstance(component, dict):
                raise ScenarioError(
                    f"components[{index}] 类型冲突: 期望 dict（分量场景），"
                    f"实际为 {type(component).__name__}: {component!r}"
                )
            normalized_components.append(normalize_scenario(component))
        out["components"] = normalized_components
    elif style_key == "composite":
        raise ScenarioError(
            "components 缺失: style='composite' 必含非空分量清单"
        )

    # 规范键序输出；未知键按原序保留透传（已由 validate 拒——此处防御保留）。
    normalized: dict = {key: out[key] for key in _CANONICAL_KEY_ORDER if key in out}
    for key, value in out.items():
        if key not in normalized:
            normalized[key] = value
    return normalized
