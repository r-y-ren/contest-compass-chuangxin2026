"""启动后端决策：探测→b210/降级 sim/显式失败不静默——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import logging

# BackendError 单源在注册表包：open_b210_backend 侧同源导入（经
# src.manage_backend_registry.register_backend），本模块按依赖声明从 lookup 侧
# 取同一异常类；lookup_backend 负责别名归一与未知名相近提示。
from src.manage_backend_registry.lookup_backend import BackendError, lookup_backend
from src.open_b210_backend.open_b210_backend import open_b210_backend
from src.open_sim_backend.open_sim_backend import open_sim_backend

from .probe_uhd_devices import probe_uhd_devices

__all__ = ["autodetect_backend"]

_LOGGER = logging.getLogger(__name__)

# 降级建议统一文案：显式打开失败与探测命中但打开失败两处 BackendError 均附（不静默）。
_FALLBACK_ADVICE = "可改用 --backend sim 降级"
# 探测摘要长度上限（防异常工具输出撑爆 BackendError 消息，量级同 open_b210_backend）。
_PROBE_SUMMARY_MAX = 300


def autodetect_backend(
    explicit: str | None = None, params: dict | None = None
) -> tuple[object, dict]:
    """启动后端决策：显式名解析打开 / 探测→b210 / 探测不可用降级 sim（失败不静默）。

    输入: explicit 显式后端名（None/空/空白/'auto' 大小写不敏感 → 自动探测）；
    params 透传后端打开参数 dict（None 视同 {}）。
    输出: (backend 实例, selection dict)——选择记录按决策路径定形，供日志/UI/报告贯通：
      - 显式命中: {'backend': 规范名（meta.kind，缺则原名）, 'decision': 'explicit',
        'explicit': 原始显式名}；
      - 探测命中: {'backend': 'b210', 'decision': 'probe_hit', 'probe': 探测结果}；
      - 自动降级: {'backend': 'sim', 'decision': 'auto_fallback', 'probe': 探测结果,
        'reason': 探测 error 或 'no_device'}。
    错误: BackendError——显式名未知（lookup_backend 的相近名提示原样透传）、显式
    打开失败、探测命中但 open_b210_backend 失败（如设备被占用）；后两类消息附
    原始错误与探测摘要及"可改用 --backend sim 降级"建议，绝不静默降级 sim。
    sim 降级路径的 params 域错由 open_sim_backend 以 ValueError 原样上抛（调用方
    参数笔误，非决策错误）。
    """
    open_params: dict = {} if params is None else params
    if isinstance(explicit, str) and not explicit.strip():
        explicit = None  # 空/空白显式名视同 auto
    if explicit is not None:
        name = explicit.strip() if isinstance(explicit, str) else explicit
        factory, meta = lookup_backend(name)  # 未知名/非法名 BackendError（含相近提示）透传
        if factory is not None:  # 保留名 'auto' 时 factory 为 None → 交探测决策
            return _open_explicit(explicit, factory, meta, open_params)
    return _autodetect_via_probe(open_params)


def _open_explicit(explicit, factory, meta, open_params: dict) -> tuple[object, dict]:
    """显式路径：注册表工厂打开，失败 BackendError 附降级建议（不静默），记录原始名。"""
    try:
        backend = factory(open_params)
    except Exception as exc:
        raise BackendError(
            f"显式指定后端 {explicit!r} 打开失败（{type(exc).__name__}: {exc}）——"
            f"显式指定失败，{_FALLBACK_ADVICE}"
        ) from exc
    kind = meta.get("kind") if isinstance(meta, dict) else None
    backend_name = kind if isinstance(kind, str) and kind else explicit
    _LOGGER.info("后端决策：显式指定 %r → %r", explicit, backend_name)
    return backend, {"backend": backend_name, "decision": "explicit", "explicit": explicit}


def _autodetect_via_probe(open_params: dict) -> tuple[object, dict]:
    """自动路径：探测→在位且无 error 尝试 b210；不可用降级 sim（探测依据入选择记录）。"""
    probe = probe_uhd_devices()
    if not probe.get("available") or probe.get("error"):
        # 探测不可用：available False（无设备段/工具缺失/超时）或探测带 error（退出码
        # 非零等）——均不碰真机，降级 sim；原因进 selection['reason'] 供报告贯通。
        reason = probe.get("error") or "no_device"
        _LOGGER.warning("后端决策：自动探测不可用（%s），降级 sim", reason)
        backend = open_sim_backend(open_params)
        return backend, {
            "backend": "sim",
            "decision": "auto_fallback",
            "probe": probe,
            "reason": reason,
        }
    try:
        backend = open_b210_backend(open_params)
    except Exception as exc:
        # 探测命中但打开失败（典型：设备被其他进程占用）——显式报错，绝不静默 sim。
        raise BackendError(
            f"探测命中 B210 在位但打开失败（探测摘要: {_probe_summary(probe)}）——"
            f"{type(exc).__name__}: {exc}；不静默降级，{_FALLBACK_ADVICE}"
        ) from exc
    _LOGGER.info("后端决策：自动探测命中 B210（%s）", _probe_summary(probe))
    return backend, {"backend": "b210", "decision": "probe_hit", "probe": probe}


def _probe_summary(probe: dict) -> str:
    """探测结果摘要：设备段逐台 index/serial/product/type 紧凑串，超长截断。"""
    devices = probe.get("devices") or []
    parts = [
        f"#{dev.get('index')} serial={dev.get('serial')} "
        f"product={dev.get('product')} type={dev.get('type')}"
        for dev in devices
        if isinstance(dev, dict)
    ]
    summary = "; ".join(parts)
    if not summary:
        return "无设备段"
    if len(summary) > _PROBE_SUMMARY_MAX:
        return summary[:_PROBE_SUMMARY_MAX] + "...(截断)"
    return summary
