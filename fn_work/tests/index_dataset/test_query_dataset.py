"""query_dataset 行为用例：上游覆盖 slug=dataset_index（对抗用例，fn-implement 阶段填充）。"""
import pytest

from src.index_dataset.query_dataset import QueryError, query_dataset


def _entry(run_id="r1", **overrides):
    entry = {
        "run_id": run_id,
        "path": f"runs/{run_id}/recording.sigmf",
        "style": "chirp",
        "freq_mhz": 2450.0,
        "date": "2026-10-05",
        "backend": "b210",
        "jsr_db": 20.0,
        "failed": False,
    }
    entry.update(overrides)
    return entry


def _sample_index():
    return [
        _entry("r3", style="noise", freq_mhz=900.0, date="2026-10-03", backend="sim",
               failed=True, batch_key="batch-b"),
        _entry("r1", style="chirp", freq_mhz=2400.0, date="2026-10-01", batch_key="batch-a"),
        _entry("r2", style="pulse", freq_mhz=2450.0, date="2026-10-01", batch_key="batch-a"),
        _entry("r4", style="chirp", freq_mhz=2500.0, date="2026-10-11"),
        _entry("r5", style="noise", freq_mhz=433.0, date="2026-10-20", backend="n210",
               failed=True),
        _entry("r6", style="hop", freq_mhz=None, date="2026-10-02", backend="sim"),
    ]


def test_empty_and_none_conditions_return_full_index_sorted():
    index = _sample_index()
    for conditions in (None, {}):
        result = query_dataset(index, conditions)
        assert set(result) == {"entries", "batch_groups", "total", "matched"}
        assert result["total"] == 6
        assert result["matched"] == 6
        # date 升序 + run_id 字典序：10-01(r1,r2) → 10-02(r6) → 10-03(r3) → 10-11(r4) → 10-20(r5)
        assert [e["run_id"] for e in result["entries"]] == ["r1", "r2", "r6", "r3", "r4", "r5"]
        assert len(result["batch_groups"]) == 3


def test_single_style_string_filter():
    result = query_dataset(_sample_index(), {"style": "chirp"})
    assert [e["run_id"] for e in result["entries"]] == ["r1", "r4"]
    assert result["total"] == 6
    assert result["matched"] == 2


def test_style_list_is_multi_value_or():
    result = query_dataset(_sample_index(), {"style": ["chirp", "pulse", "noise"]})
    # 列表内 OR：hop(r6) 未列出被排除
    assert [e["run_id"] for e in result["entries"]] == ["r1", "r2", "r3", "r4", "r5"]
    assert query_dataset(_sample_index(), {"style": []})["matched"] == 0


def test_freq_range_closed_interval_inclusive_bounds():
    result = query_dataset(_sample_index(), {"freq_range": (2400.0, 2500.0)})
    # 两端 2400.0/2500.0 闭区间命中；900/433 排除；None 频点排除
    assert [e["run_id"] for e in result["entries"]] == ["r1", "r2", "r4"]


def test_date_range_closed_interval_string_compare():
    result = query_dataset(_sample_index(), {"date_range": ("2026-10-01", "2026-10-11")})
    # 闭区间：两端日期命中，10-20 排除
    assert [e["run_id"] for e in result["entries"]] == ["r1", "r2", "r6", "r3", "r4"]


def test_backend_and_style_combine_with_and():
    result = query_dataset(_sample_index(), {"backend": "b210", "style": "chirp"})
    # AND：同为 b210 且 chirp 仅 r1/r4；sim 的 noise(r3)、n210(r5) 不因单条件命中混入
    assert [e["run_id"] for e in result["entries"]] == ["r1", "r4"]
    only_sim = query_dataset(_sample_index(), {"backend": "sim"})
    assert [e["run_id"] for e in only_sim["entries"]] == ["r6", "r3"]  # 10-02 < 10-03


def test_failed_filter_missing_failed_counts_as_not_failed():
    index = [_entry("r1"), _entry("r2", failed=True)]
    missing = _entry("r3")
    del missing["failed"]
    index.append(missing)
    kept = query_dataset(index, {"failed": False})
    assert [e["run_id"] for e in kept["entries"]] == ["r1", "r3"]
    broken = query_dataset(index, {"failed": True})
    assert [e["run_id"] for e in broken["entries"]] == ["r2"]


def test_batch_groups_bucket_none_for_missing_batch_key():
    result = query_dataset(_sample_index())
    groups = result["batch_groups"]
    assert set(groups) == {"batch-a", "batch-b", "_none"}
    assert [e["run_id"] for e in groups["batch-a"]] == ["r1", "r2"]
    assert [e["run_id"] for e in groups["batch-b"]] == ["r3"]
    # 无 batch_key 字段的 r4/r5/r6 归 '_none'，组内同样按 date+run_id 排序
    assert [e["run_id"] for e in groups["_none"]] == ["r6", "r4", "r5"]


def test_unknown_condition_field_raises_queryerror_with_supported_list():
    with pytest.raises(QueryError) as excinfo:
        query_dataset(_sample_index(), {"style": "chirp", "duty_cycle": 0.5})
    message = str(excinfo.value)
    assert "duty_cycle" in message
    for field in ("style", "freq_range", "date_range", "backend", "failed", "batch_key"):
        assert field in message  # 附完整支持字段清单


def test_none_or_missing_freq_mhz_excluded_under_freq_range():
    index = [_entry("r1", freq_mhz=None), _entry("r2"), _entry("r3", freq_mhz=100.0)]
    del index[1]["freq_mhz"]  # 键整个缺失
    result = query_dataset(index, {"freq_range": (0.0, 200.0)})
    # 缺频点/None 频点在 freq_range 条件下排除，不抛错
    assert [e["run_id"] for e in result["entries"]] == ["r3"]
    assert result["matched"] == 1
    assert result["total"] == 3


def test_sort_stable_date_then_run_id():
    index = [
        _entry("b2", date="2026-10-02"),
        _entry("a1", date="2026-10-01", style="marker-1"),
        _entry("b1", date="2026-10-02"),
        _entry("a1", date="2026-10-01", style="marker-2"),
        _entry("a2", date="2026-10-01"),
    ]
    result = query_dataset(index)
    # 同 date 按 run_id 字典序；同 (date, run_id) 保持原始相对顺序（marker-1 先于 marker-2）
    assert [(e["date"], e["run_id"], e["style"]) for e in result["entries"]] == [
        ("2026-10-01", "a1", "marker-1"),
        ("2026-10-01", "a1", "marker-2"),
        ("2026-10-01", "a2", "chirp"),
        ("2026-10-02", "b1", "chirp"),
        ("2026-10-02", "b2", "chirp"),
    ]


def test_index_not_list_raises_queryerror():
    for bad in ("not-a-list", ("r1",), {"run_id": "r1"}, 7, None):
        with pytest.raises(QueryError):
            query_dataset(bad)


def test_entry_not_dict_raises_queryerror():
    with pytest.raises(QueryError) as excinfo:
        query_dataset([_entry("r1"), "oops", 3])
    assert "#1" in str(excinfo.value)  # 定位首个坏条目位置


def test_batch_key_condition_filters_by_effective_group_key():
    by_group = query_dataset(_sample_index(), {"batch_key": "batch-a"})
    assert [e["run_id"] for e in by_group["entries"]] == ["r1", "r2"]
    ungrouped = query_dataset(_sample_index(), {"batch_key": "_none"})
    assert [e["run_id"] for e in ungrouped["entries"]] == ["r6", "r4", "r5"]


def test_no_match_returns_empty_entries_and_groups():
    result = query_dataset(_sample_index(), {"style": "fsk"})
    assert result["entries"] == []
    assert result["batch_groups"] == {}
    assert result["matched"] == 0
    assert result["total"] == 6
