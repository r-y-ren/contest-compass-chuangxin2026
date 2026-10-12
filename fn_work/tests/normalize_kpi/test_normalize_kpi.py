"""normalize_kpi 对抗测试（slug=kpi_model）：三源归一/口径元数据/异源冲突拒/判据 PER。"""
from __future__ import annotations

import pytest

from src.normalize_kpi.normalize_kpi import KpiError, normalize_kpi

_ROW_KEYS = {
    "timestamp_ms",
    "link",
    "source",
    "per",
    "retries",
    "rssi_dbm",
    "judge_per",
    "rpd",
    "jsr_db",
    "meta",
}


def test_kpi_model_esp32_rssi_passthrough_rpd_none():
    row = normalize_kpi(
        {
            "timestamp_ms": 1234.5,
            "per_raw": 0.02,
            "retries": 7,
            "rssi_dbm": -58.5,
            "seq": 42,
        },
        "esp32",
    )
    assert set(row) == _ROW_KEYS
    assert row["rssi_dbm"] == -58.5
    assert row["rpd"] is None and row["jsr_db"] is None
    assert row["source"] == "esp32" and row["per"] == 0.02 and row["retries"] == 7


def test_kpi_model_esp32_missing_rssi_becomes_none():
    row = normalize_kpi({"per_raw": 0.0}, "esp32")
    assert row["rssi_dbm"] is None


def test_kpi_model_nrf24_rssi_none_rpd_passthrough():
    row = normalize_kpi(
        {"per_raw": 0.05, "retries": 3, "rpd": True}, "nrf24"
    )
    assert row["rssi_dbm"] is None  # nrf24 无 RSSI 口径
    assert row["rpd"] is True
    assert row["jsr_db"] is None


def test_kpi_model_nrf24_with_rssi_key_conflict_rejected():
    with pytest.raises(KpiError) as exc:
        normalize_kpi({"per_raw": 0.05, "rssi_dbm": -60.0}, "nrf24")
    msg = str(exc.value)
    assert "nrf24" in msg and "rssi_dbm" in msg  # 指明源与字段


def test_kpi_model_sim_jsr_passthrough_per_model_in_meta():
    row = normalize_kpi(
        {"per_raw": 0.3, "per_model": 0.28, "jsr_db": 6.5}, "sim"
    )
    assert row["jsr_db"] == 6.5
    assert row["rssi_dbm"] is None and row["rpd"] is None
    assert row["per"] == 0.3
    assert row["meta"]["per_model"] == 0.28  # sim 模型 PER 落 meta


def test_kpi_model_sim_rssi_passthrough_when_present():
    assert normalize_kpi({"per_raw": 0.1, "rssi_dbm": -70.0}, "sim")[
        "rssi_dbm"
    ] == -70.0


def test_kpi_model_missing_per_raw_rejected():
    with pytest.raises(KpiError, match="per_raw"):
        normalize_kpi({"retries": 1, "rssi_dbm": -60.0}, "esp32")


def test_kpi_model_non_dict_sample_rejected():
    with pytest.raises(KpiError, match="dict"):
        normalize_kpi([("per_raw", 0.1)], "esp32")  # type: ignore[arg-type]


def test_kpi_model_unknown_source_rejected_with_source_list():
    with pytest.raises(KpiError) as exc:
        normalize_kpi({"per_raw": 0.1}, "lte")
    msg = str(exc.value)
    for name in ("esp32", "nrf24", "sim"):
        assert name in msg


def test_kpi_model_retries_default_zero():
    assert normalize_kpi({"per_raw": 0.01}, "nrf24")["retries"] == 0


def test_kpi_model_timestamp_link_passthrough():
    row = normalize_kpi(
        {"timestamp_ms": 99.9, "link": "bench-a", "per_raw": 0.0}, "esp32"
    )
    assert row["timestamp_ms"] == 99.9 and row["link"] == "bench-a"


def test_kpi_model_link_default_mapped_by_source():
    assert normalize_kpi({"per_raw": 0.0}, "esp32")["link"] == "dut_esp32"
    assert normalize_kpi({"per_raw": 0.0}, "nrf24")["link"] == "dut_nrf24"
    assert normalize_kpi({"per_raw": 0.0}, "sim")["link"] == "dut_sim"


def test_kpi_model_judge_per_recomputed_low_samples_note():
    row = normalize_kpi(
        {"per_raw": 0.5, "n_error": 3, "n_total": 20}, "esp32"
    )
    assert row["per"] == 0.5  # 样本 per_raw 原样
    assert row["judge_per"] == pytest.approx(3 / 20)  # 判据 PER 经 compute_per
    assert row["meta"]["judge_note"] == "low_samples(<30)"


def test_kpi_model_judge_per_sufficient_samples_note_empty():
    row = normalize_kpi(
        {"per_raw": 0.9, "n_error": 4, "n_total": 200}, "nrf24"
    )
    assert row["judge_per"] == pytest.approx(4 / 200)
    assert row["meta"]["judge_note"] == ""
    assert row["meta"]["judge_basis"] == "compute_per(n_error,n_total)"


def test_kpi_model_judge_per_no_samples_unavailable():
    row = normalize_kpi({"per_raw": 0.4, "n_error": 0, "n_total": 0}, "sim")
    assert row["judge_per"] is None
    assert row["meta"]["judge_note"] == "no_samples"


def test_kpi_model_judge_per_per_raw_only_note():
    row = normalize_kpi({"per_raw": 0.07}, "esp32")
    assert row["judge_per"] == 0.07
    assert row["meta"]["judge_note"] == "per_raw_only"
    assert row["meta"]["judge_basis"] == "per_raw"


def test_kpi_model_per_raw_none_no_delta_esp32_judge_unavailable():
    """中#2 判据口径透传：esp32 no_delta 窗（per_raw=None）→ per/judge_per 均 None、
    judge_note='per_unavailable'（不得误标 'per_raw_only'）、per_note 透传 meta。"""
    row = normalize_kpi(
        {"per_raw": None, "per_note": "no_delta", "rssi_dbm": -60.0}, "esp32"
    )
    assert row["per"] is None
    assert row["judge_per"] is None
    assert row["meta"]["judge_note"] == "per_unavailable"
    assert row["meta"]["judge_basis"] == "per_raw"
    assert row["meta"]["per_note"] == "no_delta"


def test_kpi_model_per_raw_none_no_delta_nrf24_judge_unavailable():
    """中#2 补例（nrf24 侧 no_delta）：同口径——judge_per=None+'per_unavailable'。"""
    row = normalize_kpi(
        {"per_raw": None, "per_note": "no_delta", "retries": 2, "rpd": False}, "nrf24"
    )
    assert row["per"] is None and row["judge_per"] is None
    assert row["meta"]["judge_note"] == "per_unavailable"
    assert row["meta"]["per_note"] == "no_delta"


def test_kpi_model_per_raw_none_counter_reset_nrf24_judge_unavailable():
    """中#2 补例（nrf24 counter_reset 窗）：judge_per=None+'per_unavailable'+注记透传。"""
    row = normalize_kpi(
        {"per_raw": None, "per_note": "counter_reset", "retries": 0, "rpd": True}, "nrf24"
    )
    assert row["per"] is None and row["judge_per"] is None
    assert row["meta"]["judge_note"] == "per_unavailable"
    assert row["meta"]["per_note"] == "counter_reset"


def test_kpi_model_per_raw_none_without_note_still_unavailable():
    """per_raw=None 但样本未带 per_note：判据口径同 'per_unavailable'，meta 不设 per_note 键。"""
    row = normalize_kpi({"per_raw": None}, "esp32")
    assert row["judge_per"] is None
    assert row["meta"]["judge_note"] == "per_unavailable"
    assert "per_note" not in row["meta"]


def test_kpi_model_per_note_absent_meta_has_no_per_note_key():
    """样本无 per_note 时 meta 不设 per_note 键（数值在位场景照旧 'per_raw_only'）。"""
    meta = normalize_kpi({"per_raw": 0.1, "retries": 1}, "esp32")["meta"]
    assert "per_note" not in meta
    assert meta["judge_note"] == "per_raw_only"


def test_kpi_model_delta_overflow_note_passthrough():
    """delta_overflow 窗注记透传：judge_per=None（不可比窗不得成为判据证据）。"""
    row = normalize_kpi({"per_raw": None, "per_note": "delta_overflow"}, "esp32")
    assert row["judge_per"] is None
    assert row["meta"]["judge_note"] == "per_unavailable"
    assert row["meta"]["per_note"] == "delta_overflow"


def test_kpi_model_partial_counts_ignored_falls_back_to_per_raw():
    """低#7 半指定计数：n_error/n_total 只给其一半→忽略计数落回 per_raw 口径。"""
    row = normalize_kpi({"per_raw": 0.05, "n_error": 3}, "nrf24")  # 只有 n_error
    assert row["judge_per"] == 0.05
    assert row["meta"]["judge_note"] == "partial_counts_ignored"
    assert row["meta"]["judge_basis"] == "per_raw"
    row2 = normalize_kpi({"per_raw": 0.02, "n_total": 100}, "esp32")  # 只有 n_total
    assert row2["judge_per"] == 0.02
    assert row2["meta"]["judge_note"] == "partial_counts_ignored"
    assert row2["meta"]["judge_basis"] == "per_raw"


def test_kpi_model_full_counts_still_win_over_partial_paths():
    """n_error/n_total 双全时仍经 compute_per 重算（半指定口径不侵蚀全指定路径）。"""
    row = normalize_kpi({"per_raw": 0.5, "n_error": 3, "n_total": 20}, "esp32")
    assert row["judge_per"] == pytest.approx(3 / 20)
    assert row["meta"]["judge_note"] == "low_samples(<30)"


def test_kpi_model_invalid_counts_wrapped_kpierror():
    with pytest.raises(KpiError, match="n_error"):
        normalize_kpi({"per_raw": 0.1, "n_error": 5, "n_total": 2}, "esp32")


def test_kpi_model_meta_style_declares_ber_caliber():
    style = normalize_kpi({"per_raw": 0.0}, "sim")["meta"]["style"]
    for fragment in ("PER 包级", "EN 300 328", "PER≤10%", "BER", "F13", "R21"):
        assert fragment in style


def test_kpi_model_meta_source_fields_records_sample_keys():
    sample = {"timestamp_ms": 1.0, "per_raw": 0.1, "seq": 3, "rssi_dbm": -60.0}
    meta = normalize_kpi(sample, "esp32")["meta"]
    assert set(meta["source_fields"]) == set(sample)


def test_kpi_model_cross_source_conflicts_generalized():
    with pytest.raises(KpiError) as exc:
        normalize_kpi({"per_raw": 0.1, "rpd": True}, "esp32")
    assert "esp32" in str(exc.value) and "rpd" in str(exc.value)
    with pytest.raises(KpiError) as exc:
        normalize_kpi({"per_raw": 0.1, "jsr_db": 3.0}, "nrf24")
    assert "nrf24" in str(exc.value) and "jsr_db" in str(exc.value)
