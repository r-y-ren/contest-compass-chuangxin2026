"""record_failure_level 对抗单测：验收 slug=gb42590_executor（B13 叶子，失效电平登记）。"""
import time
from datetime import datetime

import pytest

from src.execute_gb42590_protocol.record_failure_level import record_failure_level

ENTRY_KEYS = {
    "style",
    "step",
    "failure_level_db",
    "level_basis",
    "jsr_db",
    "per_at_failure",
    "kpi_snapshot",
    "ts_ms",
    "recorded_at",
    "missing_fields",
}


def _full_ctx(**overrides):
    """完整失效上下文（GB 42590 §5.11 失效瞬间：−5dB 起 5dB 递增，第 3 档失效）。"""
    ctx = {
        "style": "noise",
        "step": 3,
        "target_db": 5.0,
        "achieved_db": 4.8,
        "jsr_db": 12.5,
        "per": 0.13,
        "kpi_snapshot": {"per": 0.13, "throughput": 0.4e6, "n_bits": 20000},
        "ts_ms": 123456789,
    }
    ctx.update(overrides)
    return ctx


def _without(*keys):
    """完整 ctx 去掉指定键。"""
    ctx = _full_ctx()
    for key in keys:
        ctx.pop(key, None)
    return ctx


def test_full_ctx_all_fields_and_achieved_preferred():
    # 完整 ctx：条目全字段齐、achieved 优先于 target、无缺失登记。
    entry = record_failure_level(_full_ctx())
    assert set(entry) == ENTRY_KEYS
    assert entry["style"] == "noise"
    assert entry["step"] == 3
    assert entry["failure_level_db"] == pytest.approx(4.8)  # achieved 优先，非 target 5.0
    assert entry["level_basis"] == "achieved"
    assert entry["jsr_db"] == pytest.approx(12.5)
    assert entry["per_at_failure"] == pytest.approx(0.13)
    assert entry["kpi_snapshot"] == {"per": 0.13, "throughput": 0.4e6, "n_bits": 20000}
    assert entry["ts_ms"] == 123456789  # 在场 ts 原样透传
    assert entry["missing_fields"] == []


def test_achieved_missing_falls_back_to_target():
    # achieved 缺键 → 回退 target 并标注 level_basis=target_fallback；target 在场不算缺。
    entry = record_failure_level(_without("achieved_db"))
    assert entry["failure_level_db"] == pytest.approx(5.0)
    assert entry["level_basis"] == "target_fallback"
    assert entry["missing_fields"] == []


def test_achieved_none_falls_back_to_target():
    # achieved_db=None 与缺键同口径：回退 target。
    entry = record_failure_level(_full_ctx(achieved_db=None))
    assert entry["failure_level_db"] == pytest.approx(5.0)
    assert entry["level_basis"] == "target_fallback"


def test_per_and_jsr_missing_filled_unknown_and_listed():
    # per/jsr 缺 → 输出 'unknown' 且 missing_fields 恰含两键。
    entry = record_failure_level(_without("per", "jsr_db"))
    assert entry["per_at_failure"] == "unknown"
    assert entry["jsr_db"] == "unknown"
    assert set(entry["missing_fields"]) == {"per", "jsr_db"}


def test_ts_missing_filled_with_current_monotonic_ms():
    # ts_ms 缺 → 补当前 monotonic ms（夹逼在调用前后时钟读数间），且计入 missing_fields。
    before = time.monotonic_ns() // 1_000_000
    entry = record_failure_level(_without("ts_ms"))
    after = time.monotonic_ns() // 1_000_000
    assert isinstance(entry["ts_ms"], int)
    assert before <= entry["ts_ms"] <= after
    assert entry["missing_fields"] == ["ts_ms"]


def test_kpi_snapshot_is_deep_copy_of_ctx():
    # kpi_snapshot 深拷贝：登记后改写/清空原 ctx（含嵌套）不影响条目，对象亦非同一。
    ctx = _full_ctx()
    entry = record_failure_level(ctx)
    assert entry["kpi_snapshot"] is not ctx["kpi_snapshot"]
    ctx["kpi_snapshot"]["per"] = 0.99
    ctx["kpi_snapshot"]["injected"] = True
    ctx["kpi_snapshot"] = {}
    assert entry["kpi_snapshot"] == {"per": 0.13, "throughput": 0.4e6, "n_bits": 20000}


def test_kpi_snapshot_missing_filled_unknown():
    entry = record_failure_level(_without("kpi_snapshot"))
    assert entry["kpi_snapshot"] == "unknown"
    assert entry["missing_fields"] == ["kpi_snapshot"]


def test_both_levels_missing_unknown_and_both_keys_listed():
    # achieved/target 两路皆缺 → failure_level_db='unknown'，missing 含两键。
    entry = record_failure_level(_without("achieved_db", "target_db"))
    assert entry["failure_level_db"] == "unknown"
    assert entry["level_basis"] == "unknown"
    assert set(entry["missing_fields"]) == {"achieved_db", "target_db"}


def test_non_dict_ctx_rejected():
    # failure_ctx 非 dict → ValueError（None/list/str/数值各拒一次）。
    for bad in (None, [], ["style"], "noise", 3):
        with pytest.raises(ValueError):
            record_failure_level(bad)


def test_recorded_at_parseable_iso_with_tz():
    # recorded_at 为可 fromisoformat 解析的 ISO 时刻，且带时区信息。
    entry = record_failure_level(_full_ctx())
    parsed = datetime.fromisoformat(entry["recorded_at"])
    assert parsed.tzinfo is not None


def test_missing_fields_exactly_lists_all_truly_missing_keys():
    # 除电平两键外全缺（achieved 在场撑住 failure_level_db）→ missing 恰列真缺键、各补 unknown。
    entry = record_failure_level(
        {
            "achieved_db": 4.8,
            "target_db": 5.0,
        }
    )
    assert entry["failure_level_db"] == pytest.approx(4.8)  # achieved 在场不受其余缺失影响
    assert set(entry["missing_fields"]) == {
        "style",
        "step",
        "jsr_db",
        "per",
        "kpi_snapshot",
        "ts_ms",
    }
    assert entry["style"] == "unknown"
    assert entry["step"] == "unknown"
    assert entry["jsr_db"] == "unknown"
    assert entry["per_at_failure"] == "unknown"
    assert entry["kpi_snapshot"] == "unknown"
    assert isinstance(entry["ts_ms"], int)  # ts_ms 走补当前口径而非 unknown
