"""样式配方注册表查询——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

from typing import Callable

# 本文件位于 switch_style 包，生成器在 src.synthesize_style 包——统一绝对导入。
from src.synthesize_style.gen_bandlimited_noise import gen_bandlimited_noise
from src.synthesize_style.gen_chirp import gen_chirp
from src.synthesize_style.gen_partial_band import gen_partial_band
from src.synthesize_style.gen_pulse import gen_pulse
from src.synthesize_style.gen_sweep import gen_sweep
from src.synthesize_style.gen_tone import gen_tone

__all__ = ["RECIPES", "StyleError", "lookup_style_recipe", "register_recipe"]

# 配方形状契约：恰三键（generator 可调用 / defaults dict / required list[str]）。
_RECIPE_KEYS = ("generator", "defaults", "required")


class StyleError(Exception):
    """样式配方域错误：未注册样式名 / 样式名非 str 或空 / 配方形状不合法。"""


# 模块级注册表（单一事实源）：样式名（小写规范键）→ 配方。
# - generator: 该样式的 IQ 生成器函数引用（synthesize_style 分派 / switch_style 预合成共用）；
# - defaults: 该样式合理默认参数（值均通过对应生成器取值域，可整包直调验证）；
# - required: 合成时必须显式提供的参数名（硬需求；seed 这类可 None 的软参数不入列）。
# 新样式 = register_recipe 登记配方，无需改动本表之外的任何代码。
RECIPES: dict[str, dict] = {
    "tone": {
        "generator": gen_tone,
        "defaults": {"freq_offset_hz": 1e3, "n_samples": 4096},
        "required": ["freq_offset_hz", "n_samples"],
    },
    "sweep": {
        "generator": gen_sweep,
        "defaults": {
            "f0": -10e3,
            "f1": 10e3,
            "duration_s": 1e-3,
            "repeats": 1,
            "fs": 1e6,
        },
        "required": ["f0", "f1", "duration_s"],
    },
    "chirp": {
        "generator": gen_chirp,
        "defaults": {
            "center_hz": 0.0,
            "bandwidth_hz": 20e3,
            "period_s": 1e-3,
            "n_samples": 4096,
            "fs": 1e6,
            "shape": "sawtooth",
        },
        "required": ["center_hz", "bandwidth_hz", "period_s", "n_samples"],
    },
    "bandlimited_noise": {
        "generator": gen_bandlimited_noise,
        "defaults": {
            "bandwidth_hz": 20e3,
            "n_samples": 8192,
            "fs": 1e6,
            "center_offset_hz": 0.0,
            "seed": None,
        },
        "required": ["bandwidth_hz", "n_samples"],
    },
    "partial_band": {
        "generator": gen_partial_band,
        "defaults": {
            "fraction": 0.5,
            "victim_bw_hz": 20e3,
            "n_samples": 8192,
            "fs": 1e6,
            "center_offset_hz": 0.0,
            "seed": None,
        },
        "required": ["fraction", "victim_bw_hz", "n_samples"],
    },
    "pulse": {
        "generator": gen_pulse,
        "defaults": {
            "pulse_width_s": 1e-4,
            "repeat_hz": 1e3,
            "n_samples": 8192,
            "fs": 1e6,
            "carrier_hz": 0.0,
        },
        "required": ["pulse_width_s", "repeat_hz", "n_samples"],
    },
}


def _normalize_name(name: object) -> str:
    """样式名归一：非 str / 空 / 纯空白 → StyleError；否则返回 strip+lower 键。"""
    if not isinstance(name, str):
        raise StyleError(
            f"样式名应为非空 str（大小写不敏感），实际为 "
            f"{type(name).__name__}: {name!r}（在册样式 {sorted(RECIPES)}）"
        )
    key = name.strip().lower()
    if not key:
        raise StyleError(
            f"样式名不能为空或纯空白（在册样式 {sorted(RECIPES)}）"
        )
    return key


def _copy_recipe(recipe: dict) -> dict:
    """配方副本：defaults/required 深一层拷贝，generator 引用共享（函数不可变）。"""
    return {
        "generator": recipe["generator"],
        "defaults": dict(recipe["defaults"]),
        "required": list(recipe["required"]),
    }


def _validate_recipe(name: str, recipe: object) -> None:
    """配方形状校验（register_recipe 前置）：恰三键齐 + 各键类型正确，错→StyleError。"""
    if not isinstance(recipe, dict):
        raise StyleError(
            f"配方应为 dict（三键 {_RECIPE_KEYS}），实际为 "
            f"{type(recipe).__name__}: {recipe!r}"
        )
    missing = [key for key in _RECIPE_KEYS if key not in recipe]
    if missing:
        raise StyleError(f"样式 {name!r} 配方缺键 {missing}（须恰含 {_RECIPE_KEYS}）")
    extra = sorted(set(recipe) - set(_RECIPE_KEYS))
    if extra:
        raise StyleError(f"样式 {name!r} 配方含未知键 {extra}（须恰含 {_RECIPE_KEYS}）")
    if not callable(recipe["generator"]):
        raise StyleError(
            f"样式 {name!r} 配方 generator 须为可调用（生成器函数引用），"
            f"实际为 {type(recipe['generator']).__name__}: {recipe['generator']!r}"
        )
    if not isinstance(recipe["defaults"], dict):
        raise StyleError(
            f"样式 {name!r} 配方 defaults 须为 dict（参数名→默认值），"
            f"实际为 {type(recipe['defaults']).__name__}: {recipe['defaults']!r}"
        )
    required = recipe["required"]
    if not isinstance(required, list):
        raise StyleError(
            f"样式 {name!r} 配方 required 须为 list（必填参数名列表），"
            f"实际为 {type(required).__name__}: {required!r}"
        )
    for param in required:
        if not isinstance(param, str) or not param.strip():
            raise StyleError(
                f"样式 {name!r} 配方 required 元素须为非空 str（参数名），"
                f"实际为 {param!r}"
            )


def lookup_style_recipe(name: str) -> dict:
    """样式配方注册表查询（大小写不敏感，名经 strip+lower 归一后查 RECIPES）。

    输入:
        name: 样式名 str（'tone'/'sweep'/'chirp'/'bandlimited_noise'/
            'partial_band'/'pulse'，任意大小写；前后空白容忍）。
    输出:
        {'generator': 生成器 callable, 'defaults': dict 副本,
         'required': list 副本}——副本隔离：外部改写返回值不影响
        注册表与后续查询。
    错误:
        StyleError：name 非 str / 空 / 纯空白；或未注册样式名
        （信息附在册清单，便于调用方自纠或 register_recipe 登记）。
    """
    key = _normalize_name(name)
    try:
        recipe = RECIPES[key]
    except KeyError:
        raise StyleError(
            f"未注册样式 {name!r}（在册样式 {sorted(RECIPES)}；"
            f"新样式请先 register_recipe 登记配方）"
        ) from None
    return _copy_recipe(recipe)


def register_recipe(name: str, recipe: dict, *, override: bool = False) -> dict:
    """登记/覆盖样式配方（扩展点：新样式 = 注册配方，无需改分发代码）。

    输入:
        name: 样式名 str（非空；归一小写后入册，与查询同口径）；
        recipe: {'generator': 可调用, 'defaults': dict, 'required': list}
            ——恰三键齐，形状错即 StyleError（不入册，注册表保持原状）；
        override: 已在册名默认拒绝覆盖（防误覆盖六基础样式），显式
            True 才允许替换。
    输出:
        入册配方的副本（与 lookup_style_recipe 返回同构）。入册存副本：
            登记后调用方改写原 recipe 不影响注册表。
    错误:
        StyleError：name 非 str / 空；配方非 dict / 缺键 / 含未知键 /
        generator 不可调用 / defaults 非 dict / required 非 list 或
        元素非非空 str；重名且 override=False。
    """
    key = _normalize_name(name)
    _validate_recipe(key, recipe)
    if key in RECIPES and not override:
        raise StyleError(
            f"样式 {key!r} 已在册，override=False 拒绝覆盖"
            f"（在册样式 {sorted(RECIPES)}；确需覆盖请显式 override=True）"
        )
    RECIPES[key] = _copy_recipe(recipe)
    return _copy_recipe(RECIPES[key])
