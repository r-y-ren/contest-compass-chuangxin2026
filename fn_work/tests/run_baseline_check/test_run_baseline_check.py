"""run_baseline_check 对抗测试（slug=baseline_guard）：保守拒绝/超阈中止/RSSI 警告不中止。"""
from __future__ import annotations

import pytest

from src.normalize_kpi.normalize_kpi import normalize_kpi
from src.run_baseline_check.run_baseline_check import run_baseline_check

_RESULT_KEYS = {
    "passed",
    "per_mean",
    "n_samples",
    "n_judged",
    "violations",
    "stop_reason",
    "advice",
}


def _rows(per_values, rssi_values=None, source="esp32"):
    """经 normalize_kpi 归一构造基线行流（判据口径依赖 B11 归一产出）。

    per_values: per_raw 序列（None 表示不可比窗→judge_per=None）；
    rssi_values: 与 per_values 等长的 RSSI 序列（None=该样本无 RSSI）；缺省整段不带。
    """
    rows = []
    for i, per_raw in enumerate(per_values):
        sample = {"timestamp_ms": 1000.0 * i, "per_raw": per_raw}
        if rssi_values is not None:
            sample["rssi_dbm"] = rssi_values[i]
        rows.append(normalize_kpi(sample, source))
    return rows


def test_baseline_guard_healthy_stream_passes():
    result = run_baseline_check(_rows([0.01] * 10, [-60.0] * 10))
    assert set(result) == _RESULT_KEYS
    assert result["passed"] is True
    assert result["per_mean"] == pytest.approx(0.01)
    assert result["n_samples"] == 10 and result["n_judged"] == 10
    assert result["violations"] == [] and result["stop_reason"] is None
    assert "基线健康" in result["advice"]


def test_baseline_guard_per_exceeded_rejects_with_advice():
    result = run_baseline_check(_rows([0.2] * 10))
    assert result["passed"] is False
    assert "baseline_per_exceeded" in result["violations"]
    assert result["stop_reason"] == "baseline_per_exceeded"
    assert result["advice"] == "排查环境噪声或链路自身故障后再测"


def test_baseline_guard_insufficient_samples_conservative_reject():
    result = run_baseline_check(_rows([0.01] * 5))
    assert result["passed"] is False  # 保守拒绝：无法判健康即不放行
    assert "insufficient_baseline_samples" in result["violations"]
    assert result["stop_reason"] == "insufficient_baseline_samples"
    assert result["advice"] == "延长基线采集窗口"


def test_baseline_guard_all_judge_none_is_insufficient():
    rows = _rows([None] * 12)  # per_raw=None → judge_per 全 None（不可比窗）
    result = run_baseline_check(rows)
    assert result["passed"] is False
    assert result["n_judged"] == 0 and result["per_mean"] is None
    assert result["stop_reason"] == "insufficient_baseline_samples"


def test_baseline_guard_exactly_min_samples_judged_passes():
    values = [0.01] * 10 + [None, None]  # 12 行、判据样本恰 10 达 min_samples
    result = run_baseline_check(_rows(values))
    assert result["n_samples"] == 12 and result["n_judged"] == 10
    assert result["passed"] is True and result["violations"] == []


def test_baseline_guard_rssi_spread_warns_without_blocking():
    rows = _rows([0.01] * 10, [-60.0] * 5 + [-35.0] * 5)  # 极差 25dB 超 20dB
    result = run_baseline_check(rows)
    assert result["passed"] is True  # 警告不中止
    warnings = [v for v in result["violations"] if v.startswith("warning")]
    assert warnings and "rssi_unstable" in warnings[0]
    assert result["stop_reason"] is None
    assert "RSSI" in result["advice"]


def test_baseline_guard_missing_rssi_skips_stability():
    result = run_baseline_check(_rows([0.01] * 10))  # 不带 rssi_dbm → None
    assert result["passed"] is True and result["violations"] == []
    nrf = run_baseline_check(_rows([0.02] * 10, source="nrf24"))  # nrf24 恒无 RSSI 口径
    assert nrf["passed"] is True and nrf["violations"] == []


def test_baseline_guard_threshold_override_loosens_per():
    result = run_baseline_check(_rows([0.2] * 10), {"baseline_per_threshold": 0.3})
    assert result["passed"] is True and result["violations"] == []


def test_baseline_guard_min_samples_override_tightens():
    result = run_baseline_check(_rows([0.01] * 10), {"min_samples": 20})
    assert result["passed"] is False
    assert "insufficient_baseline_samples" in result["violations"]


def test_baseline_guard_non_dict_row_rejected_mid_stream():
    rows = _rows([0.01] * 3) + ["not-a-row"] + _rows([0.01] * 7)
    with pytest.raises(ValueError) as exc:
        run_baseline_check(rows)
    msg = str(exc.value)
    assert "3" in msg and "dict" in msg  # 指明行号与类型，消费即中止


def test_baseline_guard_non_iterable_samples_rejected():
    with pytest.raises(ValueError, match="iterable"):
        run_baseline_check(42)  # type: ignore[arg-type]


def test_baseline_guard_invalid_threshold_rejected():
    with pytest.raises(ValueError, match="threshold"):
        run_baseline_check(_rows([0.01] * 10), threshold=0.05)  # type: ignore[arg-type]


def test_baseline_guard_out_of_order_timestamps_tolerated():
    values = [0.01, 0.02, 0.0, 0.01, 0.02, 0.0, 0.01, 0.0, 0.02, 0.01]
    in_order = run_baseline_check(_rows(values))
    rows = _rows(values)
    rows.reverse()  # 时间戳乱序
    shuffled = run_baseline_check(iter(rows))  # 单遍迭代器亦可
    assert in_order["passed"] is True and shuffled["passed"] is True
    assert shuffled["per_mean"] == pytest.approx(in_order["per_mean"])
    assert shuffled["n_judged"] == in_order["n_judged"] == 10
    assert shuffled["violations"] == in_order["violations"] == []


def test_baseline_guard_counts_and_mean_accurate():
    # 12 行：2 行不可比窗不计判据；2 行走 n_error/n_total 计数口径（judge 经
    # compute_per 重算），其余 per_raw 口径——n_judged 与均值只认 judge_per。
    rows = _rows([0.0, 0.01, 0.03, 0.0, 0.0, 0.0, 0.0, None, None, 0.0])
    rows.append(normalize_kpi({"per_raw": 0.5, "n_error": 2, "n_total": 100}, "esp32"))
    rows.append(normalize_kpi({"per_raw": 0.5, "n_error": 4, "n_total": 100}, "esp32"))
    result = run_baseline_check(rows)
    assert result["n_samples"] == 12 and result["n_judged"] == 10
    assert result["per_mean"] == pytest.approx((0.01 + 0.03 + 0.02 + 0.04) / 10)
    assert result["passed"] is True  # 均值 0.01 < 0.05


def test_baseline_guard_insufficient_reports_partial_mean():
    rows = _rows([0.01] * 7 + [None] * 3)  # 仅 7 行可判
    result = run_baseline_check(rows)
    assert result["passed"] is False
    assert result["stop_reason"] == "insufficient_baseline_samples"
    assert result["n_judged"] == 7 and result["per_mean"] == pytest.approx(0.01)


def test_baseline_guard_equal_threshold_is_not_healthy():
    # 健康要求严格低于阈值：均值恰等于阈值按超阈处理
    result = run_baseline_check(_rows([0.05]), {"min_samples": 1})
    assert result["passed"] is False
    assert "baseline_per_exceeded" in result["violations"]
    # RSSI 极差恰等于阈同样告警（仍不中止）
    rssi_edge = run_baseline_check(_rows([0.01] * 10, [-60.0] * 5 + [-40.0] * 5))
    assert rssi_edge["passed"] is True
    assert any(v.startswith("warning") and "rssi_unstable" in v for v in rssi_edge["violations"])


def test_baseline_guard_ten_rows_exact_threshold_rejected_fsum():
    # B12 中#2 回归：十行恰 0.05 的朴素 += 累加均值 0.049999999999999996 < 0.05
    # 被误放行；math.fsum 精确舍入恰得 0.05 → 按恰等阈口径正确拒绝。
    result = run_baseline_check(_rows([0.05] * 10))
    assert result["n_judged"] == 10
    assert result["per_mean"] == 0.05  # fsum 均值恰等于阈值（无累积误差）
    assert result["passed"] is False
    assert result["stop_reason"] == "baseline_per_exceeded"
    assert "baseline_per_exceeded" in result["violations"]
