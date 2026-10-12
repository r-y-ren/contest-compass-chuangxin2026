"""sim KPI 发生器：注入事件驱动 PER 退化（含悬崖）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
from collections.abc import Iterable, Iterator

from .apply_cliff_model import apply_cliff_model

__all__ = ["simulate_link_degradation"]

_SIM_TICK_MS = 100.0       # 仿真钟步进：每样本 +100ms，保证 timestamp_ms 严格单调递增
_PACKETS_PER_SAMPLE = 10   # 包级统计口径：每样本 sent=10（err=round(per*10) → per_raw≈per_model）
_ABSOLUTE_LEVEL_NOTE = "absolute_level_assumed"


def _finite_float(value, what: str) -> float:
    """归一为有限 float：bool/非数值/NaN/±inf 一律 ValueError（口径拒绝）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} 必须为有限数值，收到 {value!r}")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{what} 超出 float 可表示范围") from exc
    if not math.isfinite(number):
        raise ValueError(f"{what} 必须为有限数值（NaN/inf 拒绝），收到 {number!r}")
    return number


def _derive_jsr(event: dict, signal_power_db: float | None) -> tuple[float, str | None]:
    """事件 → (推导 JSR, 口径注记或 None)。

    事件电平三级优先：'jsr_db' 直给 > 'achieved_db' > 'target_db'。
    - 'jsr_db' 直给：字段本就是 JSR，不做电平换算，与 signal_power_db 无关；
    - 'achieved_db'/'target_db'（绝对干扰电平 dBm）：有 ctx['signal_power_db'] →
      JSR = 干扰电平 − 信号电平（dB）；无 → 按绝对电平口径（JSR=电平值）并注
      absolute_level_assumed（不隐式代换记录口径常见的 −20dBm 信号假设）。
    """
    if "jsr_db" in event:
        return _finite_float(event["jsr_db"], "event.jsr_db"), None
    for key in ("achieved_db", "target_db"):
        if key in event:
            level = _finite_float(event[key], f"event.{key}")
            if signal_power_db is None:
                return level, _ABSOLUTE_LEVEL_NOTE
            return level - signal_power_db, None
    raise ValueError("事件缺少可用电平字段（jsr_db/achieved_db/target_db），无法推导 JSR")


def simulate_link_degradation(
    events: Iterable[dict],
    model_params: dict | None = None,
    ctx: dict | None = None,
    samples_per_event: int = 3,
) -> Iterator[dict]:
    """sim KPI 发生器（生成器）：订阅注入事件流，按悬崖退化模型逐样本产出 KPI。

    - events：注入事件流 Iterable[dict]，各事件 {'type': 'power_step'/'attenuation',
      'jsr_db'/'achieved_db'/'target_db', 'ts', …}；
    - JSR 推导三级优先（'jsr_db' 直给 > 'achieved_db' > 'target_db'），绝对电平档与
      ctx['signal_power_db'] 求 JSR=干扰电平−信号电平（dB；记录口径常见假设信号
      −20dBm，但本函数不隐式代换）；缺 signal_power_db → 按绝对电平并注
      'jsr_note': 'absolute_level_assumed'；
    - model_params：【待实测】校准位，原样透传 apply_cliff_model（None/缺键取其缺省）；
    - 每事件产出 samples_per_event 个包级统计样本（timestamp_ms 单调递增）：
      per = apply_cliff_model(jsr)；sent=10、err=round(per*10)、per_raw=err/sent
      （构造使 per_raw ≈ per_model，量化步长 0.1）；
    - 样本字段：{'timestamp_ms'（内部单调仿真钟，+100ms/样本）, 'link': 'sim',
      'seq'（全局递增）, 'sent': 10, 'err', 'per_raw', 'per_model', 'jsr_db'（推导值，
      域外夹紧见 jsr_clamped）, 'jsr_clamped', 'source': 'sim', 'event_ts'（事件 ts 透传）
      [, 'jsr_note']}；
    - 事件流耗尽自然结束（生成器逐样本惰性产出）；
    - ValueError：events 不可迭代（含 str/bytes）/ 事件非 dict 或缺电平字段 / 电平或
      ctx.signal_power_db 非有限数值 / samples_per_event 非正 int / model_params 参数域
      非法（由 apply_cliff_model 透传拒绝）。
    """
    # 参数域校验急切执行：坏参数在调用点立刻 ValueError，不等到首次 next()
    if (
        isinstance(samples_per_event, bool)
        or not isinstance(samples_per_event, int)
        or samples_per_event <= 0
    ):
        raise ValueError(f"samples_per_event 必须为正 int，收到 {samples_per_event!r}")
    if ctx is not None and not isinstance(ctx, dict):
        raise ValueError(f"ctx 必须为 dict 或 None，收到 {type(ctx).__name__}")
    if isinstance(events, (str, bytes)):
        raise ValueError(f"events 必须为事件 dict 的可迭代流，收到 {type(events).__name__}")
    try:
        event_iter = iter(events)
    except TypeError as exc:
        raise ValueError(
            f"events 必须可迭代（事件流），收到 {type(events).__name__}"
        ) from exc

    signal_power_db = None
    if ctx is not None and "signal_power_db" in ctx:
        signal_power_db = _finite_float(ctx["signal_power_db"], "ctx.signal_power_db")

    return _generate_samples(event_iter, model_params, signal_power_db, samples_per_event)


def _generate_samples(
    event_iter: Iterator[dict],
    model_params: dict | None,
    signal_power_db: float | None,
    samples_per_event: int,
) -> Iterator[dict]:
    """内层生成器：逐事件 → 逐样本（事件流耗尽自然结束）。"""
    seq = 0
    clock_ms = 0.0
    for event in event_iter:
        if not isinstance(event, dict):
            raise ValueError(f"事件必须为 dict，收到 {type(event).__name__}")
        jsr, note = _derive_jsr(event, signal_power_db)
        model_out = apply_cliff_model({"jsr_db": jsr}, model_params)
        per = model_out["per"]
        err = round(per * _PACKETS_PER_SAMPLE)  # 构造使 per_raw ≈ per_model
        for _ in range(samples_per_event):
            sample = {
                "timestamp_ms": clock_ms,
                "link": "sim",
                "seq": seq,
                "sent": _PACKETS_PER_SAMPLE,
                "err": err,
                "per_raw": err / _PACKETS_PER_SAMPLE,
                "per_model": per,
                "jsr_db": jsr,
                "jsr_clamped": model_out["clamped"],
                "source": "sim",
                "event_ts": event.get("ts"),
            }
            if note is not None:
                sample["jsr_note"] = note
            yield sample
            seq += 1
            clock_ms += _SIM_TICK_MS
