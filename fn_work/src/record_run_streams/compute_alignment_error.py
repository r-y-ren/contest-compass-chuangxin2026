"""三路事件配对时延统计（P50/P95）——B12 叶子（上游 record_run_streams）。

调用方：record_run_streams（对齐误差统计随采集结果入 JSON）。
重写规约与签名意图详见 fn_docs/responsibility.md，落地口径：

- 注入事件筛选：events 中 type（str）含 'power_step' 或 'attenuation' 子串者
  才进统计（attenuation_step / power_step_rise 等子串均命中；link_up /
  tx_stop 等其余事件整体忽略——不计数、不校验其 ts_ms；type 非 str 同忽略，
  大小写敏感）；
- 配对口径：对每个注入事件在 kpi / monitor 两路**各自独立**找事件后最近样本
  ——首个 timestamp_ms ≥ ts_ms（含相等 → 时延 0.0），时延 = 样本时间戳 −
  事件时间戳；样本先于事件一律不算（bisect_left 保证非负时延）；
- 内部排序：两路样本时间戳先校验后升序排序再二分查找（乱序输入不敏感，
  口径：内部按时间戳排序）；
- pairs：每个注入事件一条（按事件输入序），某路未配上则该 delay 字段为
  None；'event_ts'/'unpaired_events' 原值透传事件 ts_ms；
- unpaired_events：**两路皆**无后随样本（流先止）的注入事件 ts_ms（事件序）；
  仅单路未配不进此列——该信息由 pairs 的 None 字段与 n_paired_* 计数承载；
- P50/P95：配对时延升序后最近秩线性插值分位（numpy 'linear' 口径：
  rank = q·(n−1)，相邻秩间内插，对齐 compute_spectrum_stats._percentile）；
  配对数 n < 5 → 对应 p50/p95 置 None 且 *_delay_note = 'insufficient_pairs'
  （可配对事件不足标记，含 0 对的空流）；n ≥ 5 → note 为 None；
- 空流/空事件不抛：n_events / n_paired_* 计 0，分位全 None（note 照标
  'insufficient_pairs'），pairs / unpaired_events 为空表；
- 校验（ValueError，消息含索引）：streams 非 dict；'events'/'kpi'/
  'monitor' 三键缺失或非 list；任一元素非 dict（报 streams['键'][i]）；
  注入事件 ts_ms 或样本 timestamp_ms 缺键 / 非有限实数（bool 不算实数，
  报 streams['键'][i] 同上）。
"""
from __future__ import annotations

import bisect
import math
from numbers import Real

__all__ = ["compute_alignment_error"]

# 注入事件 type 子串标记（命中任一即进统计）。
_EVENT_TYPE_MARKERS = ("power_step", "attenuation")
# 三路键（校验顺序：presence + list 性）。
_STREAM_KEYS = ("events", "kpi", "monitor")
# 分位统计最小配对数：n < 5 → p50/p95 置 None 并标 insufficient_pairs。
_MIN_PAIRS_FOR_PERCENTILE = 5
_INSUFFICIENT_PAIRS_NOTE = "insufficient_pairs"


def _is_valid_ts(value) -> bool:
    """时间戳合法性：有限实数（bool 是 int 子类，不算）。"""
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _sorted_timestamps(stream: list, stream_name: str) -> list[float]:
    """样本流 → 校验后升序时间戳表（乱序输入内部按时间戳排序）。"""
    timestamps: list[float] = []
    for i, row in enumerate(stream):
        if not isinstance(row, dict):
            raise ValueError(
                f"streams['{stream_name}'][{i}] 必须为 dict，got {type(row).__name__}"
            )
        ts = row.get("timestamp_ms")
        if not _is_valid_ts(ts):
            raise ValueError(
                f"streams['{stream_name}'][{i}] timestamp_ms 非法（缺键或非有限实数）"
            )
        timestamps.append(float(ts))
    timestamps.sort()
    return timestamps


def _nearest_delay_after(event_ts: float, sorted_ts: list[float]) -> float | None:
    """事件后最近样本时延：首个 timestamp ≥ event_ts（bisect_left）；流先止 → None。"""
    idx = bisect.bisect_left(sorted_ts, event_ts)
    if idx == len(sorted_ts):
        return None
    return sorted_ts[idx] - event_ts


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """最近秩线性插值分位（numpy 'linear' 口径）：rank = fraction·(n−1)，相邻秩内插。

    与 compute_spectrum_stats._percentile 同口径（本模块为 B12 独立叶子，不跨包引）。
    """
    n = len(sorted_values)
    position = fraction * (n - 1)
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return float(sorted_values[lo])
    weight = position - lo
    return float(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * weight)


def _delay_stats(delays: list[float]) -> tuple[float | None, float | None, str | None]:
    """一路配对时延 → (p50_ms, p95_ms, note)；n<5 → (None, None, 'insufficient_pairs')。"""
    if len(delays) < _MIN_PAIRS_FOR_PERCENTILE:
        return None, None, _INSUFFICIENT_PAIRS_NOTE
    ordered = sorted(delays)
    return _percentile(ordered, 0.50), _percentile(ordered, 0.95), None


def compute_alignment_error(streams: dict) -> dict:
    """三路事件配对时延统计（P50/P95）。

    输入 streams = {'events': [{'ts_ms', 'type', …}], 'kpi': [{'timestamp_ms', …}],
    'monitor': [{'timestamp_ms', …}]}；对每个注入事件（type 含 'power_step'/
    'attenuation'）在两路样本流各自找事件后最近样本并计 时延 = 样本时间戳 −
    事件时间戳。输出：{'pairs': [{'event_ts', 'event_type', 'kpi_delay_ms',
    'monitor_delay_ms'}…]（事件输入序，未配那路为 None）, 'kpi_delay_p50_ms'/
    'kpi_delay_p95_ms'/'monitor_delay_p50_ms'/'monitor_delay_p95_ms': float|None,
    'kpi_delay_note'/'monitor_delay_note': None|'insufficient_pairs', 'n_events',
    'n_paired_kpi', 'n_paired_monitor', 'unpaired_events': [两路皆无后随样本的
    事件 ts…]}。形状错 / 元素非 dict / 时间戳非法 → ValueError（含索引）。
    """
    if not isinstance(streams, dict):
        raise ValueError(f"streams 必须为 dict，got {type(streams).__name__}")
    for key in _STREAM_KEYS:
        if key not in streams:
            raise ValueError(f"streams['{key}'] 缺失，须为 list")
        if not isinstance(streams[key], list):
            raise ValueError(
                f"streams['{key}'] 必须为 list，got {type(streams[key]).__name__}"
            )

    events = streams["events"]
    kpi_ts = _sorted_timestamps(streams["kpi"], "kpi")
    monitor_ts = _sorted_timestamps(streams["monitor"], "monitor")

    pairs: list[dict] = []
    kpi_delays: list[float] = []
    monitor_delays: list[float] = []
    unpaired_events: list = []

    for i, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(
                f"streams['events'][{i}] 必须为 dict，got {type(event).__name__}"
            )
        event_type = event.get("type")
        if not isinstance(event_type, str) or not any(
            marker in event_type for marker in _EVENT_TYPE_MARKERS
        ):
            continue  # 非注入事件（link_up/tx_stop/缺 type 等）：整体忽略
        ts = event.get("ts_ms")
        if not _is_valid_ts(ts):
            raise ValueError(
                f"streams['events'][{i}] 注入事件 ts_ms 非法（缺键或非有限实数）"
            )
        event_ts = float(ts)
        kpi_delay = _nearest_delay_after(event_ts, kpi_ts)
        monitor_delay = _nearest_delay_after(event_ts, monitor_ts)
        if kpi_delay is not None:
            kpi_delays.append(kpi_delay)
        if monitor_delay is not None:
            monitor_delays.append(monitor_delay)
        if kpi_delay is None and monitor_delay is None:
            unpaired_events.append(event["ts_ms"])  # 两路皆流先止（原值透传）
        pairs.append(
            {
                "event_ts": event["ts_ms"],
                "event_type": event_type,
                "kpi_delay_ms": kpi_delay,
                "monitor_delay_ms": monitor_delay,
            }
        )

    kpi_p50, kpi_p95, kpi_note = _delay_stats(kpi_delays)
    monitor_p50, monitor_p95, monitor_note = _delay_stats(monitor_delays)
    return {
        "pairs": pairs,
        "kpi_delay_p50_ms": kpi_p50,
        "kpi_delay_p95_ms": kpi_p95,
        "monitor_delay_p50_ms": monitor_p50,
        "monitor_delay_p95_ms": monitor_p95,
        "kpi_delay_note": kpi_note,
        "monitor_delay_note": monitor_note,
        "n_events": len(pairs),
        "n_paired_kpi": len(kpi_delays),
        "n_paired_monitor": len(monitor_delays),
        "unpaired_events": unpaired_events,
    }
