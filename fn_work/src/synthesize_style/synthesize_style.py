"""六类样式合成总入口：校验→配方分派→J(t) 合成出 IQ——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import inspect
import math
from functools import lru_cache
from numbers import Real

import numpy as np

from .check_style_params import check_style_params
from .compose_jamming import compose_jamming
from src.switch_style.lookup_style_recipe import StyleError, lookup_style_recipe

__all__ = ["COMPOSITE_STYLE", "DEFAULT_COMPOSITE_MAX_DEPTH", "synthesize_style"]

# 合成模式样式名（大小写不敏感）：注册为 synthesize_style 的合成模式而非配方——
# 不走 RECIPES（无 defaults/required），由本函数分支处理 components 逐分量递归合成
# 后经 compose_jamming 叠加。即使有人 register_recipe 注册了同名配方，模式分支优先。
COMPOSITE_STYLE = "composite"

#: composite 递归深度上限缺省（B8中#2）：顶层 composite 记深度 1，嵌套逐层 +1，
#: 超过上限 → StyleError（防病态深嵌套耗尽栈/内存；可经 composite_max_depth 调）。
DEFAULT_COMPOSITE_MAX_DEPTH = 8


@lru_cache(maxsize=None)
def _accepted_kwargs(generator) -> frozenset:
    """生成器签名形参名集合：合并参数按此过滤后调用（style/power_dbm/components
    等非波形键不入生成器——各生成器自带域校验，未知键直接 TypeError 不可取）。"""
    return frozenset(inspect.signature(generator).parameters)


def _require_positive_fs(name: str, value: object) -> float:
    """采样率数值域：有限实数且 >0（拒 bool/NaN/±inf/非数值/≤0）——错抛 StyleError。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise StyleError(f"{name} 应为有限正实数（>0，采样率），实际为 {value!r}")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise StyleError(f"{name} 数值超出 float 可表示范围: {value!r}") from None
    if not math.isfinite(number) or number <= 0.0:
        raise StyleError(f"{name} 应为有限正实数（>0，采样率），实际为 {value!r}")
    return number


def _copy_params(params: dict) -> dict:
    """合并后参数深副本（B8中#3）：递归拷 dict/list/tuple 容器层（叶值共享——
    标量与 ndarray 等引用不变），保证改写 meta['params']（含嵌套 components、
    列表参数）不回染调用方原始 params——浅拷仅护顶层键，嵌套容器仍共享可回染。"""
    def _copy(value):
        if isinstance(value, dict):
            return {_copy(k): _copy(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_copy(v) for v in value]
        if isinstance(value, tuple):
            return tuple(_copy(v) for v in value)
        return value

    return _copy(params)


def synthesize_style(
    params: dict,
    composite_max_depth: int = DEFAULT_COMPOSITE_MAX_DEPTH,
) -> tuple[np.ndarray, dict]:
    """六类样式合成总入口：校验→配方分派→生成器出 IQ（composite 模式递归合成）。

    输入:
        params: dict，必含 'style'（str：六类样式名或合成模式 'composite'，
            大小写不敏感）与采样率 'fs'（数值>0——六类样式可经配方缺省补齐
            〔如 sweep 缺省 fs=1e6〕，composite 无配方故须显式提供）。其余键：
            - 生成器形参名直传（freq_offset_hz / f0 / f1 / center_hz /
              bandwidth_hz / pulse_width_s / repeat_hz / fraction /
              victim_bw_hz / n_samples / seed / amplitude / ...）：显式值优先于
              配方 defaults 合并，required 全齐（缺 → StyleError 列缺参名）；
            - 'power_dbm'：合规域 [-100, 0] dBm（0 为红线，等号通过）——
              仅记录入 meta['params']，不参与幅度缩放：数模转换（dBm→V）归
              后端增益级（发射链路）负责，本函数输出保持生成器标称幅度；
            - 'components'：仅 style='composite' 时生效——非空
              list[分量 params dict]，每分量递归本函数合成（分量未显式给
              'fs' 时继承顶层 fs）。
        composite_max_depth: composite 递归深度上限（B8中#2，缺省
            DEFAULT_COMPOSITE_MAX_DEPTH=8）：顶层 composite 记深度 1、嵌套
            逐层 +1，超限 → StyleError（文案附当前深度与上限）；对六类配方
            样式无影响。

    输出:
        (iq, meta)：iq 为 complex64 一维 ndarray；meta = {'style'（规范小写名）,
        'n_samples', 'params'（defaults+显式合并后的参数副本——与调用方 dict
        及后续调用互不污染）, **生成器元数据（noise/partial/pulse 实测带宽/
        占空比等；composite 为 compose_jamming 的 n_components/power_share 等）,
        composite 另附 'components_meta': [各分量 meta]}。

    错误:
        StyleError——①params 非 dict / 缺 'style' 或非 str；②check_style_params
        数值域校验 errors 非空（power 越红线 / 带宽超 56MHz / fs≤0 等，附
        errors 清单；'style' 键不参与该校验——样式合法性由配方注册表判定，
        register_recipe 扩展样式可经本入口合成）；③lookup_style_recipe
        未注册样式（附在册清单）；④合并后 required 缺参（附缺参名列表）或
        缺 'fs'；⑤生成器防御纵深域错（如 bandwidth>fs/2 物理域，归一为
        StyleError）；⑥composite：components 非法 / 分量递归合成失败（附
        来源分量序号）/ 递归深度超 composite_max_depth（文案附当前深度与
        上限）/ compose_jamming 合成失败（如各分量 iq 长度不一致）。
    """
    if not isinstance(params, dict):
        raise StyleError(
            f"params 应为 dict，实际为 {type(params).__name__}: {params!r}"
        )
    if "style" not in params:
        raise StyleError(
            "params 必含 'style'（六类样式或合成模式 'composite'）与 'fs'（采样率，"
            "数值>0）：当前缺 'style'"
        )
    style_name = params["style"]
    if not isinstance(style_name, str) or not style_name.strip():
        raise StyleError(
            f"params['style'] 应为非空 str（六类样式或 'composite'，大小写不敏感），"
            f"实际为 {style_name!r}"
        )
    key = style_name.strip().lower()
    if key == COMPOSITE_STYLE:
        return _synthesize_composite(params, composite_max_depth, depth=1)
    return _synthesize_recipe_style(key, params)


def _synthesize_recipe_style(key: str, params: dict) -> tuple[np.ndarray, dict]:
    """单配方样式路径：数值域校验→配方分派→defaults 合并→生成器调用→(iq, meta)。"""
    # ② 数值域校验：'fs' 映射为 sample_rate_hz 入检（>0 域经 check_style_params）。
    # 'style' 键刻意不入检：样式合法性由 ③ 配方注册表判定（register_recipe 扩展
    # 样式可经本入口合成），且 check 的带限类 bandwidth_hz 必填联动与生成器参数
    # 名不一致（如 pulse 用 pulse_width_s/repeat_hz）——故 check 对缺 style 键记
    # 的"style 缺失"一条不采纳，仅采纳数值域 errors。
    check_input = {k: v for k, v in params.items() if k != "style"}
    if "fs" in check_input:
        check_input["sample_rate_hz"] = check_input.pop("fs")
    verdict = check_style_params(check_input)
    numeric_errors = [e for e in verdict["errors"] if not e.startswith("style 缺失")]
    if numeric_errors:
        raise StyleError(
            f"样式 {key!r} 参数校验失败（{len(numeric_errors)} 项）: "
            + "; ".join(numeric_errors)
        )

    # ③ 配方分派（未注册样式 → StyleError 附在册清单）。
    recipe = lookup_style_recipe(key)

    # ④ 合并 defaults+显式参数（显式优先）；required 全齐（缺 → 列缺参名）。
    merged = {**recipe["defaults"], **params}
    missing = [name for name in recipe["required"] if name not in merged]
    if missing:
        raise StyleError(
            f"样式 {key!r} 缺必填参数 {missing}（显式参数与配方缺省合并后仍未齐）"
        )
    if "fs" not in merged:
        raise StyleError(
            f"样式 {key!r} 缺采样率参数 'fs'（数值>0）：显式参数与配方缺省均未提供"
        )
    _require_positive_fs(f"样式 {key!r} 参数 'fs'", merged["fs"])

    # ⑤ 调用生成器：合并参数按生成器签名过滤；生成器防御纵深域错（如
    # bandwidth>fs/2）归一为 StyleError，保持本入口错误契约单一。
    generator = recipe["generator"]
    accepted = _accepted_kwargs(generator)
    kwargs = {k: v for k, v in merged.items() if k in accepted}
    try:
        out = generator(**kwargs)
    except (TypeError, ValueError) as exc:
        raise StyleError(
            f"样式 {key!r} 生成器 {generator.__name__} 域错: {exc}"
        ) from exc
    if isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], dict):
        iq, gen_meta = out  # noise / partial_band / pulse：带实测元数据
    else:
        iq, gen_meta = out, {}  # tone / sweep / chirp：裸 ndarray

    iq = np.asarray(iq, dtype=np.complex64)
    meta = {
        "style": key,
        "n_samples": int(iq.size),
        "params": _copy_params(merged),  # 深副本：调用方与注册表均不受改写影响（B8中#3）
    }
    meta.update(gen_meta)
    return iq, meta


def _synthesize_composite(
    params: dict,
    composite_max_depth: int = DEFAULT_COMPOSITE_MAX_DEPTH,
    depth: int = 1,
) -> tuple[np.ndarray, dict]:
    """composite 合成模式（不走配方）：分量递归合成 → compose_jamming 叠加。

    B8中#2：depth 记当前 composite 嵌套深度（顶层 1、嵌套逐层 +1），超过
    composite_max_depth → StyleError（文案附当前深度与上限），防病态深嵌套。

    分量参数中的 'freq_offset_hz' / 'phase_rad' 取出传给 compose_jamming 作
    合成级 Δf_k / θ_k（缺省 0.0）。注意 'freq_offset_hz' 在 tone 分量上双重
    身份：它既是 gen_tone 的生成载波频率、又作合成级频偏再偏置——净频位 =
    生成频率 + 合成级频偏（对噪声/脉冲等分量则仅作合成级频偏，其生成器无同名
    形参，经签名过滤自然不入生成器）。
    """
    if depth > composite_max_depth:
        raise StyleError(
            f"composite 递归深度超限：当前深度 {depth} 超上限 {composite_max_depth}"
            f"（可用 synthesize_style 的 composite_max_depth 参数调整）"
        )
    if "fs" not in params:
        raise StyleError(
            "composite 合成模式顶层必含 'fs'（采样率，数值>0）：当前缺失"
        )
    # 顶层数值域（style='composite' 不在六类白名单，check 只喂数值键；
    # 其对缺 style 键记的"style 缺失"一条同样不采纳——口径与配方路径一致）。
    check_input: dict = {"sample_rate_hz": params["fs"]}
    if "power_dbm" in params:
        check_input["power_dbm"] = params["power_dbm"]
    verdict = check_style_params(check_input)
    numeric_errors = [e for e in verdict["errors"] if not e.startswith("style 缺失")]
    if numeric_errors:
        raise StyleError(
            "composite 顶层参数校验失败: " + "; ".join(numeric_errors)
        )
    fs = _require_positive_fs("composite 顶层 'fs'", params["fs"])

    components = params.get("components")
    if not isinstance(components, list) or not components:
        raise StyleError(
            "composite 合成模式 params['components'] 应为非空 list[分量 params dict]，"
            f"实际为 {type(components).__name__}: {components!r}"
        )

    triples = []  # (原始分量参数, 分量 iq, 分量 meta)
    for idx, comp in enumerate(components):
        if not isinstance(comp, dict):
            raise StyleError(
                f"composite components[{idx}] 应为分量 params dict，"
                f"实际为 {type(comp).__name__}: {comp!r}"
            )
        effective = dict(comp)  # 不改写调用方分量 dict
        effective.setdefault("fs", fs)  # 分量未显式给采样率 → 继承顶层 fs
        # 嵌套 composite 直入合成分支并 depth+1（经公共入口会重置深度记账，
        # 失去上限约束）；其余样式走公共入口（校验/配方路径完整复用）。
        comp_style = comp.get("style")
        nested_composite = (
            isinstance(comp_style, str)
            and comp_style.strip().lower() == COMPOSITE_STYLE
        )
        try:
            if nested_composite:
                iq_k, meta_k = _synthesize_composite(
                    effective, composite_max_depth, depth + 1
                )
            else:
                iq_k, meta_k = synthesize_style(
                    effective, composite_max_depth=composite_max_depth
                )
        except StyleError as exc:
            raise StyleError(
                f"composite 分量[{idx}]（style={comp.get('style')!r}）"
                f"递归合成失败: {exc}"
            ) from exc
        triples.append((comp, iq_k, meta_k))

    compose_input = [
        {
            "iq": iq_k,
            "freq_offset_hz": comp.get("freq_offset_hz", 0.0),
            "phase_rad": comp.get("phase_rad", 0.0),
        }
        for comp, iq_k, _ in triples
    ]
    try:
        iq, compose_meta = compose_jamming(compose_input, fs=fs)
    except ValueError as exc:
        raise StyleError(f"composite 合成失败（compose_jamming）: {exc}") from exc

    iq = np.asarray(iq, dtype=np.complex64)
    meta = {
        "style": COMPOSITE_STYLE,
        "n_samples": int(iq.size),
        "params": _copy_params(params),
    }
    meta.update(compose_meta)
    meta["components_meta"] = [meta_k for _, _, meta_k in triples]
    return iq, meta
