"""失效电平登记（档位/电平/JSR/KPI 快照）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import time
from copy import deepcopy
from datetime import datetime, timezone

__all__ = ["record_failure_level"]

# 电平取值依据：实测优先 / 回退目标档 / 两路皆缺。
_BASIS_ACHIEVED = "achieved"
_BASIS_TARGET_FALLBACK = "target_fallback"
_BASIS_UNKNOWN = "unknown"
# 字段缺失时的统一补值。
_UNKNOWN = "unknown"


def _monotonic_ms() -> int:
    """当前单调时钟毫秒数（ts_ms 缺失时的替补时间戳口径）。"""
    return time.monotonic_ns() // 1_000_000


def _pick_or_unknown(ctx: dict, key: str, missing_fields: list[str]):
    """取字段：键缺或值为 None → 记入 missing_fields 并补 'unknown'；原值原样透传。"""
    value = ctx.get(key)
    if value is None:
        missing_fields.append(key)
        return _UNKNOWN
    return value


def record_failure_level(failure_ctx: dict) -> dict:
    """失效电平登记：把失效瞬间的档位/电平/JSR/KPI 快照/时间戳固化成失效电平表条目。

    职责口径（GB 42590 §5.11 步进协议，失效即停记 P_crit）：
      - failure_level_db 取 achieved_db（实测电平）优先；缺/None 回退 target_db 并标注
        'level_basis': 'target_fallback'；两路皆缺补 'unknown' 且 missing_fields 含两键。
      - 字段缺失（键缺或值 None）统一补 'unknown' 并把键名列入 'missing_fields'；
        例外：ts_ms 缺 → 补当前单调时钟毫秒数（仍计入 missing_fields）。
      - kpi_snapshot 深拷贝入条目，调用方随后改写原 ctx 不影响已登记条目。
      - recorded_at 登记时刻（timezone-aware UTC ISO 8601）。

    输入：
      - failure_ctx: 失效上下文 dict，期望键：
        {'step': 档号, 'target_db', 'achieved_db'|None, 'jsr_db'|None,
         'per', 'kpi_snapshot': {窗口聚合摘要}, 'style', 'ts_ms'}；多余键忽略。

    输出（失效电平表条目，多样式可累积）：
      {'style', 'step', 'failure_level_db': achieved|target|'unknown',
       'level_basis': 'achieved'|'target_fallback'|'unknown',
       'jsr_db', 'per_at_failure', 'kpi_snapshot'（深拷贝）, 'ts_ms',
       'recorded_at': ISO 时间, 'missing_fields': [真缺键名]}

    错误：
      - failure_ctx 非 dict → ValueError；除此之外不抛。
    """
    if not isinstance(failure_ctx, dict):
        raise ValueError(
            f"failure_ctx 必须是 dict（失效上下文），实际类型 {type(failure_ctx).__name__}: {failure_ctx!r}"
        )

    missing_fields: list[str] = []

    # 电平取值：achieved 优先 → target 回退（标注）→ 两路皆缺补 unknown 并登记两键。
    achieved_db = failure_ctx.get("achieved_db")
    target_db = failure_ctx.get("target_db")
    if achieved_db is not None:
        failure_level_db, level_basis = achieved_db, _BASIS_ACHIEVED
    elif target_db is not None:
        failure_level_db, level_basis = target_db, _BASIS_TARGET_FALLBACK
    else:
        failure_level_db, level_basis = _UNKNOWN, _BASIS_UNKNOWN
        missing_fields.append("achieved_db")
        missing_fields.append("target_db")

    # jsr / per：缺→unknown+登记（per 输出键名换 per_at_failure）。
    jsr_db = _pick_or_unknown(failure_ctx, "jsr_db", missing_fields)
    per_at_failure = _pick_or_unknown(failure_ctx, "per", missing_fields)

    # 其余直传字段。
    style = _pick_or_unknown(failure_ctx, "style", missing_fields)
    step = _pick_or_unknown(failure_ctx, "step", missing_fields)

    # KPI 快照：深拷贝防调用方改写；缺→unknown+登记。
    kpi_snapshot = failure_ctx.get("kpi_snapshot")
    if kpi_snapshot is None:
        missing_fields.append("kpi_snapshot")
        kpi_snapshot_entry = _UNKNOWN
    else:
        kpi_snapshot_entry = deepcopy(kpi_snapshot)

    # 时间戳：缺→当前 monotonic ms（仍计入 missing_fields）。
    ts_ms = failure_ctx.get("ts_ms")
    if ts_ms is None:
        missing_fields.append("ts_ms")
        ts_ms = _monotonic_ms()

    return {
        "style": style,
        "step": step,
        "failure_level_db": failure_level_db,
        "level_basis": level_basis,
        "jsr_db": jsr_db,
        "per_at_failure": per_at_failure,
        "kpi_snapshot": kpi_snapshot_entry,
        "ts_ms": ts_ms,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "missing_fields": missing_fields,
    }
