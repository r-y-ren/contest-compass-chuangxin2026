"""端到端刷新延迟统计（P50/P95/超阈率）——重写规约与签名意图详见 fn_docs/responsibility.md。

口径（R49：<500ms 判据）：
- 配对：每帧 {'sent_ms', 'acked_ms'|None}——acked 在→延迟=acked−sent；
  负值（时钟回拨/对端快钟）钳 0 并计 n_clock_skew（样本仍入分布，值 0）；
- 无回执（acked_ms None）→n_pending 计数，不入分布；
- 形状坏的条目（非 dict/缺 sent_ms/数值类型不符/bool 冒充数）→n_invalid 丢弃；
- 分位：线性插值（与 numpy.percentile 默认 'linear' 同式），已测样本 <5
  →p50/p95 置 None 且 status='insufficient'（样本不足标记）；
- 超阈：延迟 > threshold_ms(=500) 计入——恰好等于阈值不算超（严格大于）。
"""
from __future__ import annotations

from collections.abc import Iterable

__all__ = ["measure_refresh_latency", "THRESHOLD_MS", "MIN_SAMPLES_FOR_QUANTILE"]

#: 端到端延迟判据（R49：事件→页面可达 <500ms）。
THRESHOLD_MS = 500

#: 分位数可信所需最小已测样本数（不足→p50/p95 为 None）。
MIN_SAMPLES_FOR_QUANTILE = 5


def _percentile(sorted_values: list, q: float) -> float:
    """升序样本的线性插值分位：pos=(n-1)*q，落在相邻两样本间按分数内插。

    与 numpy.percentile 默认 'linear' 口径一致（测试可独立复算对拍）。
    """
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    pos = (n - 1) * q
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return float(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac)


def _is_number(value: object) -> bool:
    """数值判定：int/float 可，bool 冒充（True==1）不算。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def measure_refresh_latency(frame_stamps: Iterable[dict]) -> dict:
    """帧戳流→端到端延迟统计（P50/P95/超阈判定，供结果 JSON 落档）。

    Args:
        frame_stamps: 帧戳可迭代流，逐项 {'sent_ms': 数值, 'acked_ms': 数值|None}。

    Returns:
        {'p50_ms','p95_ms'（不足 MIN_SAMPLES_FOR_QUANTILE 时 None）, 'n_measured',
        'n_pending','n_clock_skew','n_invalid','n_over_threshold','over_threshold',
        'threshold_ms': 500, 'status': 'ok'|'insufficient'}。
    """
    latencies: list[float] = []
    n_pending = n_clock_skew = n_invalid = 0

    for stamp in frame_stamps:
        if not isinstance(stamp, dict):
            n_invalid += 1
            continue
        sent = stamp.get("sent_ms")
        if not _is_number(sent):
            n_invalid += 1
            continue
        acked = stamp.get("acked_ms")
        if acked is None:  # 无回执——样本不足语义由 pending 计数承载
            n_pending += 1
            continue
        if not _is_number(acked):
            n_invalid += 1
            continue
        delta = float(acked) - float(sent)
        if delta < 0:  # 时钟回拨/对端快钟：钳 0 入分布，另计 skew 次数
            delta = 0.0
            n_clock_skew += 1
        latencies.append(delta)

    latencies.sort()
    n_measured = len(latencies)
    enough = n_measured >= MIN_SAMPLES_FOR_QUANTILE
    n_over = sum(1 for v in latencies if v > THRESHOLD_MS)
    return {
        "p50_ms": _percentile(latencies, 0.50) if enough else None,
        "p95_ms": _percentile(latencies, 0.95) if enough else None,
        "n_measured": n_measured,
        "n_pending": n_pending,
        "n_clock_skew": n_clock_skew,
        "n_invalid": n_invalid,
        "n_over_threshold": n_over,
        "over_threshold": n_over > 0,
        "threshold_ms": THRESHOLD_MS,
        "status": "ok" if enough else "insufficient",
    }
