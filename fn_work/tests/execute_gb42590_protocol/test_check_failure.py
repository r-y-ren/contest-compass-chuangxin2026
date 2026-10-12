"""check_failure 对抗测试：≥口径/边界恰等/样本不足保守/阈值域/per 域/输入拒收。"""
from __future__ import annotations

import pytest

from src.execute_gb42590_protocol.check_failure import check_failure
from src.normalize_kpi.compute_per import compute_per


def test_per_above_threshold_fails():
    r = check_failure({"per": 0.12, "n_total": 100, "available": True})
    assert r["failed"] is True
    assert r["basis"] == "per_threshold"
    assert r["per"] == pytest.approx(0.12)
    assert r["threshold"] == pytest.approx(0.10)
    assert r["n_total"] == 100
    assert "0.12" in r["detail"] and "0.1" in r["detail"]


def test_per_equal_threshold_fails_ge_semantics():
    r = check_failure({"per": 0.10, "n_total": 50, "available": True})
    assert r["failed"] is True  # 恰等判失效（>= 口径）
    assert r["basis"] == "per_threshold"
    assert "0.1" in r["detail"]


def test_per_below_threshold_not_failed():
    r = check_failure({"per": 0.099, "n_total": 100, "available": True})
    assert r["failed"] is False
    assert r["basis"] == "per_threshold"
    assert r["per"] == pytest.approx(0.099)


def test_per_none_insufficient():
    r = check_failure({"per": None, "n_total": 0, "available": False})
    assert r["failed"] is False
    assert r["basis"] == "insufficient_samples"
    assert r["per"] is None


def test_available_false_insufficient_even_with_per():
    r = check_failure({"per": 0.5, "n_total": 100, "available": False})
    assert r["failed"] is False
    assert r["basis"] == "insufficient_samples"
    assert r["per"] == pytest.approx(0.5)


def test_n_total_zero_insufficient():
    r = check_failure({"per": 0.2, "n_total": 0, "available": True})
    assert r["failed"] is False
    assert r["basis"] == "insufficient_samples"
    assert r["n_total"] == 0


def test_relaxed_threshold_025():
    r = check_failure({"per": 0.12, "n_total": 100, "available": True}, threshold=0.25)
    assert r["failed"] is False
    assert r["threshold"] == pytest.approx(0.25)
    assert "0.25" in r["detail"]
    r2 = check_failure({"per": 0.25, "n_total": 100, "available": True}, threshold=0.25)
    assert r2["failed"] is True  # 恰等仍失效


def test_threshold_upper_boundary_1_valid():
    r = check_failure({"per": 1.0, "n_total": 10, "available": True}, threshold=1)
    assert r["failed"] is True
    assert r["threshold"] == pytest.approx(1.0)
    assert check_failure({"per": 0.99, "n_total": 10, "available": True}, threshold=1)["failed"] is False


def test_compute_per_full_shape_passthrough():
    r = check_failure(compute_per(3, 29))  # per=3/29≈0.1034>=0.10，low_samples 仍 available
    assert r["failed"] is True
    assert r["basis"] == "per_threshold"
    assert r["per"] == pytest.approx(3 / 29)
    assert r["n_total"] == 29


def test_threshold_domain_rejected():
    for bad in (0, 1.5, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            check_failure({"per": 0.05, "n_total": 100, "available": True}, threshold=bad)


def test_threshold_non_numeric_rejected():
    with pytest.raises(ValueError):
        check_failure({"per": 0.05, "n_total": 100, "available": True}, threshold="0.1")


def test_per_domain_rejected():
    for bad_per in (-0.1, 1.2, float("nan")):
        with pytest.raises(ValueError):
            check_failure({"per": bad_per, "n_total": 100, "available": True})


def test_per_non_numeric_rejected():
    with pytest.raises(ValueError):
        check_failure({"per": "0.1", "n_total": 100, "available": True})


def test_non_dict_per_result_rejected():
    for bad in ([0.12], "per=0.12", None, 0.12):
        with pytest.raises(ValueError):
            check_failure(bad)


def test_missing_per_key_rejected():
    with pytest.raises(ValueError):
        check_failure({"n_total": 100, "available": True})


def test_return_shape_and_detail_values():
    r = check_failure({"per": 0.12, "n_total": 100, "available": True})
    assert set(r) == {"failed", "basis", "per", "threshold", "n_total", "detail"}
    assert isinstance(r["failed"], bool)
    assert isinstance(r["detail"], str)
    assert "100" in r["detail"]


def test_insufficient_detail_contains_values():
    r = check_failure({"per": None, "n_total": 0, "available": False})
    assert "insufficient_samples" in r["detail"]
    assert "n_total=0" in r["detail"]
    assert not r["failed"]


def test_zero_per_below_threshold_not_failed():
    r = check_failure(compute_per(0, 100))
    assert r["failed"] is False
    assert r["basis"] == "per_threshold"
    assert r["per"] == 0.0 and r["n_total"] == 100
