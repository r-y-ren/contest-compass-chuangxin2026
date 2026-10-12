"""enforce_bandwidth_limit 对抗测试：56MHz 带宽边界（B10 叶子，上游 capture_monitor_spectrum）。"""
import math

import pytest

from src.capture_monitor_spectrum.enforce_bandwidth_limit import (
    MonitorError,
    enforce_bandwidth_limit,
)


def test_single_5mhz_channel_inside_58g_band_is_one_segment():
    # 5.8G 5725-5829 频段内的单信道 5MHz -> 单段，不限带
    plan = enforce_bandwidth_limit((5725.0, 5730.0))
    assert plan["limited"] is False
    assert plan["note"] is None
    assert len(plan["segments"]) == 1
    seg = plan["segments"][0]
    assert seg["center_mhz"] == pytest.approx(5727.5)
    assert seg["span_mhz"] == pytest.approx(5.0)
    assert seg["covers"] == (5725.0, 5730.0)


def test_ism2400_band_83_5mhz_splits_into_two_seamless_segments():
    plan = enforce_bandwidth_limit((2400.0, 2483.5))
    segs = plan["segments"]
    assert plan["limited"] is True
    assert len(segs) == 2
    first, last = segs
    assert first["span_mhz"] == pytest.approx(56.0)
    assert first["covers"] == (2400.0, 2456.0)
    assert last["covers"] == (2456.0, 2483.5)
    assert last["span_mhz"] == pytest.approx(27.5)
    # 衔接无缝：首段 hi == 末段 lo（逐位相等，非近似）
    assert first["covers"][1] == last["covers"][0]


def test_full_58g_band_104mhz_also_limits():
    plan = enforce_bandwidth_limit((5725.0, 5829.0))
    segs = plan["segments"]
    assert plan["limited"] is True
    assert len(segs) == 2
    assert segs[0]["covers"] == (5725.0, 5781.0)
    assert segs[1]["covers"] == (5781.0, 5829.0)
    assert segs[1]["span_mhz"] == pytest.approx(48.0)


def test_exactly_56mhz_stays_single_segment():
    plan = enforce_bandwidth_limit((2400.0, 2456.0))
    assert plan["limited"] is False
    assert plan["note"] is None
    assert len(plan["segments"]) == 1
    seg = plan["segments"][0]
    assert seg["span_mhz"] == pytest.approx(56.0)
    assert seg["center_mhz"] == pytest.approx(2428.0)
    assert seg["covers"] == (2400.0, 2456.0)


def test_55_9mhz_stays_single_segment():
    plan = enforce_bandwidth_limit((100.0, 155.9))
    assert plan["limited"] is False
    assert len(plan["segments"]) == 1
    seg = plan["segments"][0]
    assert seg["span_mhz"] == pytest.approx(55.9)
    assert seg["center_mhz"] == pytest.approx(127.95)


def test_band_fully_outside_freq_range_raises_monitor_error():
    with pytest.raises(MonitorError) as excinfo:
        enforce_bandwidth_limit((6100.0, 6200.0))
    assert "6100" in str(excinfo.value)


def test_band_partially_outside_freq_range_raises_monitor_error():
    with pytest.raises(MonitorError):
        enforce_bandwidth_limit((5900.0, 6100.0))


def test_monitor_error_is_runtime_error_subclass():
    assert issubclass(MonitorError, RuntimeError)


@pytest.mark.parametrize("band", [(2450.0, 2400.0), (100.0, 100.0)])
def test_lo_not_below_hi_raises_value_error(band):
    with pytest.raises(ValueError):
        enforce_bandwidth_limit(band)


@pytest.mark.parametrize(
    "bad_bw", [0.0, 0, -56.0, float("nan"), float("inf")]
)
def test_invalid_device_bw_raises_value_error(bad_bw):
    with pytest.raises(ValueError):
        enforce_bandwidth_limit((2400.0, 2440.0), device_bw_mhz=bad_bw)


@pytest.mark.parametrize(
    "bad_range",
    [
        (6000.0, 70.0),
        (70.0,),
        (70.0, 6000.0, 9000.0),
        (float("nan"), 6000.0),
        (70.0, float("inf")),
    ],
)
def test_invalid_freq_range_shape_raises_value_error(bad_range):
    with pytest.raises(ValueError):
        enforce_bandwidth_limit((2400.0, 2440.0), freq_range_mhz=bad_range)


def test_bad_target_band_shape_raises_value_error():
    with pytest.raises(ValueError):
        enforce_bandwidth_limit((2400.0,))
    with pytest.raises(ValueError):
        enforce_bandwidth_limit([2400.0, 2410.0, 2420.0])
    with pytest.raises(ValueError):
        enforce_bandwidth_limit((float("nan"), 2410.0))


def test_each_segment_center_is_its_own_midpoint():
    plan = enforce_bandwidth_limit((2400.0, 2483.5))
    assert len(plan["segments"]) >= 2
    for seg in plan["segments"]:
        lo, hi = seg["covers"]
        assert seg["center_mhz"] == pytest.approx((lo + hi) / 2.0)
        assert seg["center_mhz"] - lo == pytest.approx(seg["span_mhz"] / 2.0)


def test_note_carries_reason_and_requested_width():
    plan = enforce_bandwidth_limit((2400.0, 2483.5))
    note = plan["note"]
    assert isinstance(note, str)
    assert "span_exceeds_device_bw" in note
    assert "83.5" in note
    unlimited = enforce_bandwidth_limit((2400.0, 2430.0))
    assert unlimited["note"] is None


@pytest.mark.parametrize(
    ("width", "expected"),
    [(5.0, 1), (56.0, 1), (56.1, 2), (83.5, 2), (104.0, 2), (112.0, 2), (168.0, 3)],
)
def test_segment_count_follows_ceil_formula(width, expected):
    plan = enforce_bandwidth_limit((1000.0, 1000.0 + width))
    assert len(plan["segments"]) == math.ceil(width / 56.0)
    assert len(plan["segments"]) == expected


def test_custom_widened_freq_range_admits_formerly_out_of_range_band():
    plan = enforce_bandwidth_limit((6100.0, 6200.0), freq_range_mhz=(70.0, 7000.0))
    segs = plan["segments"]
    assert plan["limited"] is True  # 100MHz > 56MHz，仍分段
    assert len(segs) == 2
    assert segs[0]["covers"] == (6100.0, 6156.0)
    assert segs[1]["covers"] == (6156.0, 6200.0)


def test_output_and_segment_shape():
    plan = enforce_bandwidth_limit((2400.0, 2483.5))
    assert set(plan) == {"segments", "limited", "note"}
    for seg in plan["segments"]:
        assert set(seg) == {"center_mhz", "span_mhz", "covers"}
        assert isinstance(seg["covers"], tuple)


def test_integer_inputs_accepted():
    plan = enforce_bandwidth_limit((2400, 2456), device_bw_mhz=56)
    assert plan["limited"] is False
    assert plan["segments"][0]["span_mhz"] == pytest.approx(56.0)


def test_segments_cover_target_exactly_without_gaps_or_overlap():
    lo, hi = 950.0, 1075.5
    plan = enforce_bandwidth_limit((lo, hi), device_bw_mhz=30.0)
    segs = plan["segments"]
    assert plan["limited"] is True
    assert segs[0]["covers"][0] == lo
    assert segs[-1]["covers"][1] == hi
    for a, b in zip(segs, segs[1:]):
        assert a["covers"][1] == b["covers"][0]  # 无缝：无重叠也无缝隙
    total = sum(s["span_mhz"] for s in segs)
    assert total == pytest.approx(hi - lo)


# ---------------------------------- B10 对抗审查回归（恰界容差/note 精度）


def test_just_over_bw_within_relative_tolerance_stays_single_segment():
    """低#3 回归：宽度=56·(1+1e-12)（浮点噪声级超出，≤1e-9 相对容差）→ 单段
    limited=False 且完整覆盖带顶（旧口径误判受限，且分段把带顶 5.6e-11 MHz 截丢）。"""
    lo = 2400.0
    hi = lo + 56.0 * (1.0 + 1e-12)
    assert hi - lo > 56.0  # 前置：确属"恰界超出一丝"
    plan = enforce_bandwidth_limit((lo, hi))
    assert plan["limited"] is False
    assert plan["note"] is None
    assert len(plan["segments"]) == 1
    seg = plan["segments"][0]
    assert seg["covers"] == (lo, hi)  # 完整覆盖，不丢带顶
    assert seg["span_mhz"] == pytest.approx(hi - lo, rel=1e-12)
    assert seg["center_mhz"] == pytest.approx((lo + hi) / 2.0)


def test_clearly_over_bw_just_above_tolerance_splits_two_segments():
    """低#3 对照：56.001 MHz（超 1e-9 容差）→ 仍两段受限，末段收窄 0.001 MHz。"""
    plan = enforce_bandwidth_limit((2400.0, 2456.001))
    assert plan["limited"] is True
    assert len(plan["segments"]) == 2
    assert plan["segments"][0]["covers"] == (2400.0, 2456.0)
    assert plan["segments"][1]["covers"] == (2456.0, 2456.001)
    assert plan["segments"][1]["span_mhz"] == pytest.approx(0.001)


def test_note_reports_full_precision_width_without_truncation():
    """低#3 回归：note 宽度用 repr 全精度——100.0000001 MHz 不被 :g 截成 100。"""
    plan = enforce_bandwidth_limit((1000.0, 1100.0000001))
    note = plan["note"]
    assert "span_exceeds_device_bw" in note
    assert "100.0000001" in note
