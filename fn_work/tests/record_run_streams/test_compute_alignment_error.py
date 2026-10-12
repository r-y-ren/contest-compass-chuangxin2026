"""compute_alignment_error 行为用例：B12 叶子（三路配对时延统计，对抗用例）。

口径要点：注入事件 = type 含 'power_step'/'attenuation' 子串；配对 = 事件后
（timestamp ≥ ts_ms，含相等）最近样本，两路独立；样本先于事件不算；乱序样本
内部按时间戳排序；P50/P95 = 最近秩线性插值（rank = q·(n−1)，numpy 'linear'
口径），n<5 → None 标 'insufficient_pairs'；两路皆无后随样本才进
unpaired_events。分位数值断言用测试内独立复算 ref_percentile（同公式重写，
不复用被测代码路径）+ 手算字面值锚点双保险。
"""
import math

import pytest

from src.record_run_streams.compute_alignment_error import compute_alignment_error

RESULT_KEYS = {
    "pairs",
    "kpi_delay_p50_ms",
    "kpi_delay_p95_ms",
    "monitor_delay_p50_ms",
    "monitor_delay_p95_ms",
    "kpi_delay_note",
    "monitor_delay_note",
    "n_events",
    "n_paired_kpi",
    "n_paired_monitor",
    "unpaired_events",
}
PAIR_KEYS = {"event_ts", "event_type", "kpi_delay_ms", "monitor_delay_ms"}


def _event(ts, etype="power_step"):
    return {"ts_ms": ts, "type": etype}


def _kpi(ts):
    return {"timestamp_ms": ts, "per": 0.01}


def _mon(ts):
    return {"timestamp_ms": ts, "p_total_db": -30.0}


def ref_percentile(values, fraction):
    """独立参考：升序 + rank = fraction·(n−1) 相邻秩线性插值。"""
    ordered = sorted(float(v) for v in values)
    position = fraction * (len(ordered) - 1)
    lo, hi = math.floor(position), math.ceil(position)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def test_three_events_pair_with_exact_delays():
    # 3 注入事件 + 各自跟随样本：逐事件精确时延；n=3<5 → 分位 None+标记。
    streams = {
        "events": [_event(1000), _event(2000, "attenuation"), _event(3000, "power_step_rise")],
        "kpi": [_kpi(1030), _kpi(2050), _kpi(3015)],
        "monitor": [_mon(1010), _mon(2040), _mon(3080)],
    }
    result = compute_alignment_error(streams)
    assert set(result) == RESULT_KEYS
    assert result["n_events"] == 3
    assert result["n_paired_kpi"] == 3
    assert result["n_paired_monitor"] == 3
    assert result["unpaired_events"] == []
    assert [p["kpi_delay_ms"] for p in result["pairs"]] == [30.0, 50.0, 15.0]
    assert [p["monitor_delay_ms"] for p in result["pairs"]] == [10.0, 40.0, 80.0]
    assert [p["event_type"] for p in result["pairs"]] == [
        "power_step",
        "attenuation",
        "power_step_rise",
    ]
    for key in ("kpi_delay_p50_ms", "kpi_delay_p95_ms", "monitor_delay_p50_ms", "monitor_delay_p95_ms"):
        assert result[key] is None
    assert result["kpi_delay_note"] == "insufficient_pairs"
    assert result["monitor_delay_note"] == "insufficient_pairs"


def test_sample_before_event_not_counted():
    # 样本先于事件不算：事件 100 的 kpi 候选 50（先于）与 130（后随）→ 30 而非 −50；
    # 事件 500 后两路均无样本（kpi 50/130、monitor 200 皆先于）→ 完全 unpaired。
    streams = {
        "events": [_event(100), _event(500, "attenuation")],
        "kpi": [_kpi(50), _kpi(130)],
        "monitor": [_mon(200)],
    }
    result = compute_alignment_error(streams)
    assert result["pairs"][0]["kpi_delay_ms"] == 30.0  # 130−100，非 50−100=−50
    assert result["pairs"][0]["monitor_delay_ms"] == 100.0  # 200−100
    assert result["pairs"][1]["kpi_delay_ms"] is None
    assert result["pairs"][1]["monitor_delay_ms"] is None
    assert result["n_paired_kpi"] == 1
    assert result["n_paired_monitor"] == 1
    assert result["unpaired_events"] == [500]


def test_unpaired_events_when_streams_end_first():
    # 流先止：末事件后无任何样本 → ts 入 unpaired_events（事件序），counts 对账。
    streams = {
        "events": [_event(1000), _event(1100, "attenuation"), _event(1200)],
        "kpi": [_kpi(1010), _kpi(1110)],
        "monitor": [_mon(1005), _mon(1105)],
    }
    result = compute_alignment_error(streams)
    assert result["n_events"] == 3
    assert result["n_paired_kpi"] == 2
    assert result["n_paired_monitor"] == 2
    assert result["unpaired_events"] == [1200]
    assert [p["kpi_delay_ms"] for p in result["pairs"]] == [10.0, 10.0, None]
    assert [p["monitor_delay_ms"] for p in result["pairs"]] == [5.0, 5.0, None]


def test_p50_p95_against_independent_reference():
    # n=6 两路独立已知时延：与 ref_percentile 逐值对照 + 手算锚点。
    kpi_offsets = [12.0, 34.0, 56.0, 78.0, 90.0, 110.0]
    mon_offsets = [5.0, 15.0, 25.0, 35.0, 45.0, 55.0]
    streams = {
        "events": [_event(10000 * i, "power_step" if i % 2 == 0 else "attenuation") for i in range(6)],
        "kpi": [_kpi(10000 * i + off) for i, off in enumerate(kpi_offsets)],
        "monitor": [_mon(10000 * i + off) for i, off in enumerate(mon_offsets)],
    }
    result = compute_alignment_error(streams)
    assert result["kpi_delay_note"] is None
    assert result["monitor_delay_note"] is None
    assert result["kpi_delay_p50_ms"] == pytest.approx(ref_percentile(kpi_offsets, 0.50))
    assert result["kpi_delay_p95_ms"] == pytest.approx(ref_percentile(kpi_offsets, 0.95))
    assert result["monitor_delay_p50_ms"] == pytest.approx(ref_percentile(mon_offsets, 0.50))
    assert result["monitor_delay_p95_ms"] == pytest.approx(ref_percentile(mon_offsets, 0.95))
    # 手算锚点：kpi p50 rank=2.5 → 56+0.5·22=67；p95 rank=4.75 → 90+0.75·20=105；
    # monitor p50 rank=2.5 → 30；p95 rank=4.75 → 45+0.75·10=52.5。
    assert result["kpi_delay_p50_ms"] == pytest.approx(67.0)
    assert result["kpi_delay_p95_ms"] == pytest.approx(105.0)
    assert result["monitor_delay_p50_ms"] == pytest.approx(30.0)
    assert result["monitor_delay_p95_ms"] == pytest.approx(52.5)


def test_p95_interpolation_anchor_n5():
    # n=5 锚点：时延 {10,20,30,40,100} → p50 rank=2 精确 30；p95 rank=3.8 → 88。
    offsets = [10.0, 20.0, 30.0, 40.0, 100.0]
    streams = {
        "events": [_event(5000 * i) for i in range(5)],
        "kpi": [_kpi(5000 * i + off) for i, off in enumerate(offsets)],
        "monitor": [_mon(5000 * i + off * 2) for i, off in enumerate(offsets)],
    }
    result = compute_alignment_error(streams)
    assert result["kpi_delay_p50_ms"] == pytest.approx(30.0)
    assert result["kpi_delay_p95_ms"] == pytest.approx(88.0)  # 40+0.8·(100−40)
    assert result["monitor_delay_p50_ms"] == pytest.approx(60.0)
    assert result["monitor_delay_p95_ms"] == pytest.approx(176.0)  # 80+0.8·(200−80)


def test_fewer_than_5_pairs_returns_none_marked_insufficient():
    # n=4：pairs/count 正常承载时延，分位 None + 'insufficient_pairs'。
    streams = {
        "events": [_event(1000 * i) for i in range(4)],
        "kpi": [_kpi(1000 * i + 7) for i in range(4)],
        "monitor": [_mon(1000 * i + 3) for i in range(4)],
    }
    result = compute_alignment_error(streams)
    assert result["n_paired_kpi"] == 4
    assert result["n_paired_monitor"] == 4
    assert [p["kpi_delay_ms"] for p in result["pairs"]] == [7.0] * 4
    assert result["kpi_delay_p50_ms"] is None
    assert result["kpi_delay_p95_ms"] is None
    assert result["monitor_delay_p50_ms"] is None
    assert result["monitor_delay_p95_ms"] is None
    assert result["kpi_delay_note"] == "insufficient_pairs"
    assert result["monitor_delay_note"] == "insufficient_pairs"


def test_empty_events_counts_zero():
    # 空事件：n_events 0、pairs 空，不抛；分位 None（0 对 < 5）。
    streams = {"events": [], "kpi": [_kpi(10), _kpi(20)], "monitor": [_mon(30)]}
    result = compute_alignment_error(streams)
    assert result["n_events"] == 0
    assert result["pairs"] == []
    assert result["unpaired_events"] == []
    assert result["n_paired_kpi"] == 0
    assert result["n_paired_monitor"] == 0
    assert result["kpi_delay_p50_ms"] is None
    assert result["kpi_delay_note"] == "insufficient_pairs"


def test_empty_sample_streams_all_unpaired():
    # 两路样本全空：注入事件全 unpaired，分位 None，不抛。
    streams = {
        "events": [_event(100), _event(200, "attenuation")],
        "kpi": [],
        "monitor": [],
    }
    result = compute_alignment_error(streams)
    assert result["n_events"] == 2
    assert result["n_paired_kpi"] == 0
    assert result["n_paired_monitor"] == 0
    assert result["unpaired_events"] == [100, 200]
    assert all(p["kpi_delay_ms"] is None and p["monitor_delay_ms"] is None for p in result["pairs"])
    assert result["monitor_delay_p95_ms"] is None
    assert result["monitor_delay_note"] == "insufficient_pairs"


def test_unsorted_sample_input_sorted_internally():
    # 乱序样本流：内部按时间戳排序后配对。事件 1100 的 kpi 候选 {1160, 1250}
    # → 最近 1160（时延 60，非负）；若不排序直接二分会取到 1030 得负时延。
    streams = {
        "events": [_event(1000), _event(1100, "attenuation")],
        "kpi": [_kpi(1250), _kpi(1030), _kpi(1160)],
        "monitor": [_mon(1115), _mon(1005), _mon(1270)],
    }
    result = compute_alignment_error(streams)
    assert [p["kpi_delay_ms"] for p in result["pairs"]] == [30.0, 60.0]
    assert [p["monitor_delay_ms"] for p in result["pairs"]] == [5.0, 15.0]
    assert result["unpaired_events"] == []
    assert all(d is None or d >= 0.0 for p in result["pairs"] for d in (p["kpi_delay_ms"], p["monitor_delay_ms"]))


@pytest.mark.parametrize("stream_name", ["events", "kpi", "monitor"])
def test_non_dict_element_rejected_with_index(stream_name):
    # 元素非 dict → ValueError 且消息含 streams['键'][索引]。
    streams = {
        "events": [_event(1000), _event(2000)],
        "kpi": [_kpi(1010), _kpi(2010)],
        "monitor": [_mon(1010), _mon(2010)],
    }
    streams[stream_name][1] = 42
    with pytest.raises(ValueError, match=rf"streams\['{stream_name}'\]\[1\]"):
        compute_alignment_error(streams)


@pytest.mark.parametrize(
    "streams_obj, pattern",
    [
        (None, r"streams 必须为 dict"),
        ([_event(1)], r"streams 必须为 dict"),
        ({"events": [], "kpi": []}, r"streams\['monitor'\] 缺失"),
        ({"events": (), "kpi": [], "monitor": []}, r"streams\['events'\] 必须为 list"),
        ({"events": [], "kpi": {}, "monitor": []}, r"streams\['kpi'\] 必须为 list"),
    ],
)
def test_streams_shape_validation(streams_obj, pattern):
    with pytest.raises(ValueError, match=pattern):
        compute_alignment_error(streams_obj)


def test_kpi_and_monitor_delays_independent():
    # 两路独立：kpi 跟随（n=5 出分位）、monitor 全空（全 None+标记）；
    # kpi 已配上 → 不进 unpaired_events。
    streams = {
        "events": [_event(1000 * i) for i in range(5)],
        "kpi": [_kpi(1000 * i + off) for i, off in enumerate([10.0, 20.0, 30.0, 40.0, 50.0])],
        "monitor": [],
    }
    result = compute_alignment_error(streams)
    assert result["n_paired_kpi"] == 5
    assert result["n_paired_monitor"] == 0
    assert [p["kpi_delay_ms"] for p in result["pairs"]] == [10.0, 20.0, 30.0, 40.0, 50.0]
    assert all(p["monitor_delay_ms"] is None for p in result["pairs"])
    assert result["kpi_delay_p50_ms"] == pytest.approx(30.0)
    assert result["kpi_delay_p95_ms"] == pytest.approx(48.0)  # 40+0.8·10
    assert result["kpi_delay_note"] is None
    assert result["monitor_delay_p50_ms"] is None
    assert result["monitor_delay_p95_ms"] is None
    assert result["monitor_delay_note"] == "insufficient_pairs"
    assert result["unpaired_events"] == []


def test_non_injection_events_ignored():
    # type 过滤：link_up/tx_stop/缺 type/非 str type（含大写不命中，大小写敏感）
    # 全忽略——不计数、不校验 ts；attenuation_step/power_step_rise 子串命中。
    streams = {
        "events": [
            {"ts_ms": 1, "type": "link_up"},
            {"ts_ms": 2, "type": "tx_stop"},
            {"ts_ms": 3},  # 缺 type
            {"type": 123},  # 非 str type 且无 ts——整体忽略不抛
            {"ts_ms": 5, "type": "POWER_STEP"},  # 大小写敏感 → 不命中
            _event(6, "attenuation_step"),
            _event(7, "power_step_rise"),
        ],
        "kpi": [_kpi(10)],
        "monitor": [_mon(10)],
    }
    result = compute_alignment_error(streams)
    assert result["n_events"] == 2
    assert [p["event_ts"] for p in result["pairs"]] == [6, 7]
    assert [p["event_type"] for p in result["pairs"]] == ["attenuation_step", "power_step_rise"]
    assert [p["kpi_delay_ms"] for p in result["pairs"]] == [4.0, 3.0]


def test_sample_exactly_at_event_ts_pairs_with_zero_delay():
    # timestamp == ts_ms（≥ 含相等）→ 时延 0.0（配上，非 None）。
    streams = {
        "events": [_event(1000)],
        "kpi": [_kpi(1000)],
        "monitor": [_mon(1000)],
    }
    result = compute_alignment_error(streams)
    assert result["pairs"][0]["kpi_delay_ms"] == 0.0
    assert result["pairs"][0]["monitor_delay_ms"] == 0.0
    assert result["n_paired_kpi"] == 1
    assert result["unpaired_events"] == []


@pytest.mark.parametrize(
    "streams_obj, pattern",
    [
        # 注入事件 ts_ms：bool / 缺键 / NaN → 拒（含索引）。
        ({"events": [{"ts_ms": True, "type": "power_step"}], "kpi": [], "monitor": []}, r"events'\]\[0\]"),
        ({"events": [{"type": "attenuation"}], "kpi": [], "monitor": []}, r"events'\]\[0\]"),
        ({"events": [_event(1), {"ts_ms": float("nan"), "type": "power_step"}], "kpi": [], "monitor": []}, r"events'\]\[1\]"),
        # 样本 timestamp_ms：缺键 / None / NaN / +inf → 拒（含索引）。
        ({"events": [], "kpi": [{"per": 0.1}], "monitor": []}, r"kpi'\]\[0\]"),
        ({"events": [], "kpi": [_kpi(10), {"timestamp_ms": None}], "monitor": []}, r"kpi'\]\[1\]"),
        ({"events": [], "kpi": [], "monitor": [{"timestamp_ms": float("nan")}]}, r"monitor'\]\[0\]"),
        ({"events": [], "kpi": [], "monitor": [_mon(1.0), _mon(2.0), {"timestamp_ms": float("inf")}]}, r"monitor'\]\[2\]"),
    ],
)
def test_invalid_timestamps_rejected_with_index(streams_obj, pattern):
    with pytest.raises(ValueError, match=pattern):
        compute_alignment_error(streams_obj)


def test_pair_entry_key_set_and_event_order_preserved():
    # pairs 每条字段齐整；事件输入序保留（含夹在中间的 unpaired 事件）。
    streams = {
        "events": [_event(3000, "attenuation"), _event(9000), _event(9500)],
        "kpi": [_kpi(3010), _kpi(9010)],
        "monitor": [_mon(3010), _mon(9010)],
    }
    result = compute_alignment_error(streams)
    assert all(set(p) == PAIR_KEYS for p in result["pairs"])
    assert [p["event_ts"] for p in result["pairs"]] == [3000, 9000, 9500]
    assert result["unpaired_events"] == [9500]
