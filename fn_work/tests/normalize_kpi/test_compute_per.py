"""compute_per 对抗测试：比值/边界/样本量标记/窗口透传/输入拒收。"""
from __future__ import annotations

import pytest

from src.normalize_kpi.compute_per import compute_per


def test_zero_errors_over_100():
    r = compute_per(0, 100)
    assert r["per"] == 0.0
    assert r["n_error"] == 0 and r["n_total"] == 100
    assert r["available"] is True and r["samples_note"] == ""
    assert r["window"] == {"type": "cumulative"}


def test_ratio_30_over_100():
    assert compute_per(30, 100)["per"] == 0.3


def test_no_samples_returns_unavailable():
    r = compute_per(0, 0)
    assert r["per"] is None
    assert r["available"] is False
    assert r["samples_note"] == "no_samples"
    assert r["n_total"] == 0 and r["n_error"] == 0


def test_29_total_flagged_low_samples_but_available():
    r = compute_per(3, 29)
    assert r["samples_note"] == "low_samples(<30)"
    assert r["available"] is True
    assert r["per"] == pytest.approx(3 / 29)


def test_30_total_exactly_not_flagged():
    assert compute_per(3, 30)["samples_note"] == ""


def test_error_exceeding_total_rejected():
    with pytest.raises(ValueError):
        compute_per(5, 3)


@pytest.mark.parametrize("n_error,n_total", [(-1, 100), (1, -100), (-5, -3)])
def test_negative_counts_rejected(n_error, n_total):
    with pytest.raises(ValueError):
        compute_per(n_error, n_total)


@pytest.mark.parametrize("n_error,n_total", [(True, 100), (1, True), (False, False)])
def test_bool_counts_rejected(n_error, n_total):
    with pytest.raises(ValueError):
        compute_per(n_error, n_total)


@pytest.mark.parametrize("n_error,n_total", [(float("nan"), 100), (1, float("nan"))])
def test_nan_counts_rejected(n_error, n_total):
    with pytest.raises(ValueError):
        compute_per(n_error, n_total)


def test_window_passthrough_and_default():
    w = {"type": "interval", "last_n": 10}
    assert compute_per(1, 50, window=w)["window"] == w
    assert compute_per(1, 50, window=None)["window"] == {"type": "cumulative"}
    # 无样本时同样透传口径
    assert compute_per(0, 0, window=w)["window"] == w


def test_per_always_within_unit_interval():
    assert compute_per(100, 100)["per"] == 1.0
    assert compute_per(0, 1)["available"] is True
    for n_total in (1, 29, 30, 1000):
        for n_error in range(0, n_total + 1, max(1, n_total // 25)):
            assert 0.0 <= compute_per(n_error, n_total)["per"] <= 1.0


def test_result_shape_exact_keys():
    r = compute_per(1, 50)
    assert set(r) == {"per", "n_error", "n_total", "window", "available", "samples_note"}
    assert isinstance(r["samples_note"], str)
    assert isinstance(r["available"], bool)
