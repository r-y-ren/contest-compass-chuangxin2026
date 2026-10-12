"""56MHz 带宽边界：限带/分段计划+口径说明——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
from collections.abc import Sequence

DEFAULT_DEVICE_BW_MHZ = 56.0
DEFAULT_FREQ_RANGE_MHZ = (70.0, 6000.0)
_SPAN_EXCEEDS_REASON = "span_exceeds_device_bw"


class MonitorError(RuntimeError):
    """目标观测频段不在设备能力域（freq_range_mhz）内时抛出。"""


def _as_finite_pair(value: object, name: str) -> tuple[float, float]:
    """把 (lo, hi) 形状参数校验为有限递增浮点对，形状非法抛 ValueError。"""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a (lo, hi) pair, got {value!r}")
    if len(value) != 2:
        raise ValueError(f"{name} must have exactly 2 elements (lo, hi), got {len(value)}")
    lo_raw, hi_raw = value[0], value[1]
    try:
        lo = float(lo_raw)
        hi = float(hi_raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} elements must be numeric, got {value!r}") from None
    if not (math.isfinite(lo) and math.isfinite(hi)):
        raise ValueError(f"{name} elements must be finite numbers, got {value!r}")
    if lo >= hi:
        raise ValueError(f"{name} requires lo < hi, got ({lo}, {hi})")
    return lo, hi


def _split_into_segments(lo: float, hi: float, device_bw: float) -> list[dict]:
    """从目标下界起按 device_bw 等宽分段：相邻段共享边界频率，末段收窄到上界。"""
    width = hi - lo
    count = max(1, math.ceil(width / device_bw - 1e-9))
    segments: list[dict] = []
    for index in range(count):
        seg_lo = lo + index * device_bw
        seg_hi = min(seg_lo + device_bw, hi)
        segments.append(
            {
                "center_mhz": (seg_lo + seg_hi) / 2.0,
                "span_mhz": seg_hi - seg_lo,
                "covers": (seg_lo, seg_hi),
            }
        )
    return segments


def enforce_bandwidth_limit(
    target_band: tuple[float, float],
    device_bw_mhz: float = DEFAULT_DEVICE_BW_MHZ,
    freq_range_mhz: tuple[float, float] = DEFAULT_FREQ_RANGE_MHZ,
) -> dict:
    """给定目标观测频段与设备实时带宽，产出合法采集计划。

    - 目标频段完整落在设备能力域（freq_range_mhz）内且宽度 <= device_bw_mhz：
      单段计划 [{'center_mhz': 中点, 'span_mhz': 宽度, 'covers': (lo, hi)}]，
      limited=False，note=None。
    - 宽度 > device_bw_mhz（span_exceeds_device_bw）：按 device_bw_mhz 从目标
      下界起分段——相邻段共享边界频率、段宽=device_bw_mhz、末段收窄到目标
      上界；limited=True，note 说明受限口径（reason + requested 宽度）。
    - 目标频段超出设备能力域（整体或部分不在 freq_range_mhz 内）：MonitorError。
    - 形状/数值非法（lo>=hi、device_bw_mhz<=0 或非有限、freq_range_mhz 形状
      非法）：ValueError。

    返回：{'segments': [...], 'limited': bool, 'note': str | None}（MHz 口径）。
    """
    band_lo, band_hi = _as_finite_pair(target_band, "target_band")
    range_lo, range_hi = _as_finite_pair(freq_range_mhz, "freq_range_mhz")

    try:
        device_bw = float(device_bw_mhz)
    except (TypeError, ValueError):
        raise ValueError(f"device_bw_mhz must be a number, got {device_bw_mhz!r}") from None
    if not math.isfinite(device_bw) or device_bw <= 0.0:
        raise ValueError(
            f"device_bw_mhz must be a finite positive number, got {device_bw_mhz!r}"
        )

    if band_lo < range_lo or band_hi > range_hi:
        raise MonitorError(
            f"target_band ({band_lo}, {band_hi}) MHz outside device capability "
            f"freq_range_mhz ({range_lo}, {range_hi})"
        )

    width = band_hi - band_lo
    if width <= device_bw:
        segments = [
            {
                "center_mhz": (band_lo + band_hi) / 2.0,
                "span_mhz": width,
                "covers": (band_lo, band_hi),
            }
        ]
        return {"segments": segments, "limited": False, "note": None}

    segments = _split_into_segments(band_lo, band_hi, device_bw)
    note = (
        f"{_SPAN_EXCEEDS_REASON}: requested {width:g} MHz exceeds device "
        f"real-time bandwidth {device_bw:g} MHz; split into {len(segments)} segments"
    )
    return {"segments": segments, "limited": True, "note": note}
