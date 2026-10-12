"""measure_refresh_latency 对抗测试：分位数值独立复算对拍、pending 计数、
clock_skew 负钳 0、n<5 样本不足 None、阈值边界（严格大于）、生成器流与坏条目。"""
from __future__ import annotations

import pytest

from src.push_realtime_kpi.measure_refresh_latency import measure_refresh_latency


def _ref_percentile(values, q):
    """测试侧独立复算（同式 pos=(n-1)*q 线性内插——非调用被测函数）。"""
    vals = sorted(values)
    pos = (len(vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def _stamps(deltas, base=1000):
    """按延迟清单造帧戳流：sent=base+i*1000，acked=sent+delta（None 造 pending）。"""
    out = []
    for i, d in enumerate(deltas):
        sent = base + i * 1000
        acked = None if d is None else sent + d
        out.append({"sent_ms": sent, "acked_ms": acked})
    return out


def test_five_measured_quantiles_recomputed():
    """① 5 帧全配对：p50/p95 与独立复算一致，n_measured=5，status='ok'。"""
    deltas = [200, 100, 1000, 120, 480]  # 乱序入流
    res = measure_refresh_latency(_stamps(deltas))
    assert res["n_measured"] == 5 and res["status"] == "ok"
    assert res["p50_ms"] == pytest.approx(_ref_percentile(deltas, 0.50))  # 200
    assert res["p95_ms"] == pytest.approx(_ref_percentile(deltas, 0.95))  # 896
    assert res["threshold_ms"] == 500
    assert res["over_threshold"] is True and res["n_over_threshold"] == 1


def test_pending_frames_counted_not_measured():
    """② 无回执帧→n_pending 计数且不入分布。"""
    deltas = [100, None, 150, None, 300, 700]
    res = measure_refresh_latency(_stamps(deltas))
    assert res["n_pending"] == 2
    assert res["n_measured"] == 4  # 4<5→分位不可信
    assert res["status"] == "insufficient"
    assert res["p50_ms"] is None and res["p95_ms"] is None


def test_clock_skew_negative_clamped_to_zero():
    """③ acked 早于 sent（负延迟）→钳 0 入分布+n_clock_skew 计数，p50 非负。"""
    stamps = _stamps([100, 150, 300, 700, 50])
    stamps[4]["acked_ms"] = stamps[4]["sent_ms"] - 250  # -250ms 回拨
    res = measure_refresh_latency(stamps)
    assert res["n_clock_skew"] == 1
    assert res["n_measured"] == 5
    assert res["p50_ms"] == pytest.approx(_ref_percentile([0, 100, 150, 300, 700], 0.50))
    assert res["p50_ms"] >= 0 and res["p95_ms"] >= 0


def test_insufficient_samples_below_five():
    """④ 已测样本 <5→p50/p95 均 None 且 status='insufficient'。"""
    res = measure_refresh_latency(_stamps([100, 200, 300, 400]))
    assert res["n_measured"] == 4
    assert res["p50_ms"] is None and res["p95_ms"] is None
    assert res["status"] == "insufficient"


def test_empty_stream_all_zero():
    """⑤ 空流→零计样本、分位 None、不超阈。"""
    res = measure_refresh_latency([])
    assert res == {
        "p50_ms": None,
        "p95_ms": None,
        "n_measured": 0,
        "n_pending": 0,
        "n_clock_skew": 0,
        "n_invalid": 0,
        "n_over_threshold": 0,
        "over_threshold": False,
        "threshold_ms": 500,
        "status": "insufficient",
    }


def test_threshold_strictly_greater():
    """⑥ 阈值边界：恰 500ms 不算超阈，500 以上才算（严格大于）。"""
    res_eq = measure_refresh_latency(_stamps([500, 10, 20, 30, 40]))
    assert res_eq["over_threshold"] is False and res_eq["n_over_threshold"] == 0
    res_over = measure_refresh_latency(_stamps([501, 10, 20, 30, 40]))
    assert res_over["over_threshold"] is True and res_over["n_over_threshold"] == 1


def test_generator_input_accepted():
    """⑦ Iterable 契约：生成器流与列表流结果一致。"""
    deltas = [80, 120, 400, 600, 90]
    as_list = measure_refresh_latency(_stamps(deltas))
    as_gen = measure_refresh_latency(s for s in _stamps(deltas))
    assert as_gen == as_list


def test_malformed_entries_counted_invalid():
    """⑧ 坏条目（非 dict/缺 sent_ms/bool 冒充/acked 非数）→n_invalid 丢弃不炸。"""
    stamps = _stamps([100, 120, 200, 480, 1000]) + [
        "not-a-dict",
        {"acked_ms": 5},  # 缺 sent_ms
        {"sent_ms": True, "acked_ms": 2},  # bool 冒充数
        {"sent_ms": 1, "acked_ms": "later"},  # acked 非数
    ]
    res = measure_refresh_latency(stamps)
    assert res["n_invalid"] == 4
    assert res["n_measured"] == 5  # 好样本不受牵连
    assert res["status"] == "ok"
