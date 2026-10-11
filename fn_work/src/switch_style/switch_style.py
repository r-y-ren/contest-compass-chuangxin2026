"""样式快速切换：取配方→预合成→原子替换（<2s，切换期不发射）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import time

from src.synthesize_style.synthesize_style import synthesize_style

from .lookup_style_recipe import StyleError, lookup_style_recipe

__all__ = ["switch_style"]


def switch_style(ctx: dict, style_name: str, params: dict | None = None) -> dict:
    """样式快速切换：取配方→预合成就绪实例→原子替换 ctx['current_style']。

    安全闸（发射边界）：本函数纯"准备+替换"——不触任何后端（不发配置、
    不发起射、不停在跑发射），切换期间的发射安全由调用方另驱（先停发再
    切换、切完再重发均与本函数无关）；发射链路只消费 ctx['current_style']
    里的就绪实例。

    输入:
        ctx: 运行上下文 dict（调用方持有）——本函数仅在合成成功后以单次
            键赋值原子替换 ctx['current_style']（写入形状恰五键：
            'iq'（complex64 ndarray）/ 'meta'（synthesize_style 的 meta）/
            'style'（规范小写样式名）/ 'prepared_at'（time.time() 纪元秒）/
            'switch_ms'（perf_counter 差，毫秒））；
        style_name: 目标样式名 str（六类在册样式，大小写不敏感）；
        params: 合成参数 dict | None——None 视为空 dict（由配方 defaults
            补齐，如 chirp/sweep 等 defaults 自带 fs 即可直接合成）；
            非 None 时与 {'style': style_name} 合并（显式值优先，但
            'style' 键强制取 style_name——函数即切到该名）。
    输出:
        {'style': 规范小写样式名, 'switch_ms': float（perf_counter 差 ms）,
         'prepared': True, 'samples': int（iq 样本数）}。
    错误:
        ValueError——ctx 非 dict（或 params 非 dict/None）；
        StyleError——①样式名未注册（lookup_style_recipe 附在册清单）；
        ②合成失败（数值域越红线如 power_dbm>0 / 缺必填参数等）。两种失败
        均发生在写 ctx 之前：ctx['current_style'] 保持旧值原对象不变，
        绝无部分写。
    """
    if not isinstance(ctx, dict):
        raise ValueError(
            f"ctx 应为运行上下文 dict（本函数原子替换其 'current_style' 键），"
            f"实际为 {type(ctx).__name__}: {ctx!r}"
        )
    if params is not None and not isinstance(params, dict):
        raise ValueError(
            f"params 应为合成参数 dict 或 None（None 用配方 defaults），"
            f"实际为 {type(params).__name__}: {params!r}"
        )

    # ① 配方校验（未注册名 → StyleError 附在册清单；此时尚未动 ctx）。
    lookup_style_recipe(style_name)

    # ② 预合成：成功才产出就绪实例（iq+meta），perf_counter 差计切换耗时 ms。
    synth_params: dict = dict(params) if params else {}
    synth_params["style"] = style_name
    t_start = time.perf_counter()
    iq, meta = synthesize_style(synth_params)
    switch_ms = (time.perf_counter() - t_start) * 1000.0

    # ③ 原子替换：单次键赋值（读侧要么见旧实例、要么见完整新实例）。
    ctx["current_style"] = {
        "iq": iq,
        "meta": meta,
        "style": meta["style"],
        "prepared_at": time.time(),
        "switch_ms": switch_ms,
    }
    return {
        "style": meta["style"],
        "switch_ms": switch_ms,
        "prepared": True,
        "samples": int(iq.size),
    }
