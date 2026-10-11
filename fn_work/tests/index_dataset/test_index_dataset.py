"""index_dataset 行为用例：验收 slug=dataset_index（register/query/rebuild/list + 损坏自愈）。"""
import json
import logging
import os

import pytest

from src.index_dataset.index_dataset import (
    IndexConflictError,
    IndexEntryError,
    IndexFormatError,
    IndexWriteError,
    index_dataset,
)
from src.index_dataset.query_dataset import QueryError


def _record(**overrides) -> dict:
    """合法登记条目（可覆盖字段）"""
    base = {
        "run_id": "20260101-120000",
        "path": "/data/recordings/run-a",
        "style": "fhss",
        "freq_mhz": 2450.0,
        "date": "20260101",
        "backend": "b210",
        "jsr_db": "/data/jsr/db.json",
        "failed": False,
        "batch_key": "batch-1",
    }
    base.update(overrides)
    return base


def _make_run(runs_root, name: str, *, result=None, recordings=True, corrupt_result=False) -> str:
    """在 runs_root 下造一个 run 目录（result.json + 可选 recordings）"""
    run_dir = os.path.join(str(runs_root), name)
    os.makedirs(run_dir)
    if recordings:
        os.makedirs(os.path.join(run_dir, "recordings"))
    result_path = os.path.join(run_dir, "result.json")
    if corrupt_result:
        with open(result_path, "w", encoding="utf-8") as fh:
            fh.write("{not-json")
    else:
        payload = {"status": "done", "backend": "b210"}
        if result:
            payload.update(result)
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    return run_dir


def test_dataset_index_register_query_roundtrip(tmp_path):
    index_path = str(tmp_path / "index.json")
    out = index_dataset("register", record=_record(), index_path=index_path)
    assert out["registered"]["run_id"] == "20260101-120000"
    assert out["total"] == 1
    hit = index_dataset("query", query={"backend": "b210", "style": "fhss"}, index_path=index_path)
    assert hit["matched"] == 1
    assert hit["entries"][0]["run_id"] == "20260101-120000"
    assert hit["batch_groups"]["batch-1"][0]["run_id"] == "20260101-120000"
    miss = index_dataset("query", query={"backend": "x310"}, index_path=index_path)
    assert miss["matched"] == 0 and miss["entries"] == []


def test_dataset_index_duplicate_run_id_rejected_then_update_overwrites(tmp_path):
    index_path = str(tmp_path / "index.json")
    index_dataset("register", record=_record(), index_path=index_path)
    with pytest.raises(IndexConflictError):
        index_dataset("register", record=_record(style="dsss"), index_path=index_path)
    out = index_dataset(
        "register", record=_record(style="dsss", freq_mhz=5800.0), index_path=index_path, update=True
    )
    assert out["total"] == 1  # 覆盖不追加
    listed = index_dataset("list", index_path=index_path)
    assert listed["total"] == 1
    assert listed["entries"][0]["style"] == "dsss"
    assert listed["entries"][0]["freq_mhz"] == 5800.0


def test_dataset_index_missing_required_field_raises(tmp_path):
    record = _record()
    del record["date"]
    with pytest.raises(IndexEntryError) as excinfo:
        index_dataset("register", record=record, index_path=str(tmp_path / "index.json"))
    assert "date" in str(excinfo.value)


def test_dataset_index_bad_record_shapes_and_types_rejected(tmp_path):
    index_path = str(tmp_path / "index.json")
    with pytest.raises(IndexEntryError):  # record 缺失
        index_dataset("register", index_path=index_path)
    with pytest.raises(IndexEntryError):  # record 非 dict
        index_dataset("register", record="run-a", index_path=index_path)
    with pytest.raises(IndexEntryError):  # bool 冒充数值
        index_dataset("register", record=_record(freq_mhz=True), index_path=index_path)
    with pytest.raises(IndexEntryError):  # backend 非 str
        index_dataset("register", record=_record(backend=123), index_path=index_path)
    with pytest.raises(IndexEntryError):  # failed 非 bool
        index_dataset("register", record=_record(failed="no"), index_path=index_path)


def test_dataset_index_query_unknown_field_raises_query_error(tmp_path):
    index_path = str(tmp_path / "index.json")
    index_dataset("register", record=_record(), index_path=index_path)
    with pytest.raises(QueryError):  # 未知条件字段由 query_dataset 原样透传
        index_dataset("query", query={"nope": 1}, index_path=index_path)


def test_dataset_index_corrupt_index_auto_rebuild_then_query(tmp_path):
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "20260102-080000", result={"backend": "replay"})
    index_path = tmp_path / "index.json"
    index_path.write_text("<<<损坏>>>", encoding="utf-8")
    out = index_dataset(
        "query", query={"backend": "replay"}, index_path=str(index_path), runs_root=str(runs_root)
    )
    assert out["matched"] == 1
    assert out["entries"][0]["run_id"] == "20260102-080000"
    assert out["entries"][0]["date"] == "20260102"  # 日期补自目录名


def test_dataset_index_corrupt_index_without_runs_raises_format_error(tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text("[]", encoding="utf-8")  # 合法 JSON 但结构错
    with pytest.raises(IndexFormatError):
        index_dataset(
            "list", index_path=str(index_path), runs_root=str(tmp_path / "no-such-runs")
        )


def test_dataset_index_manual_rebuild_counts(tmp_path):
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "20260103-090000")
    _make_run(runs_root, "20260104-090000", result={"status": "failed"})
    _make_run(runs_root, "20260105-090000", corrupt_result=True)
    out = index_dataset(
        "rebuild", index_path=str(tmp_path / "index.json"), runs_root=str(runs_root)
    )
    assert out == {"rebuilt": 2, "skipped": 1}
    entries = {e["run_id"]: e for e in index_dataset("list", index_path=str(tmp_path / "index.json"))["entries"]}
    assert entries["20260104-090000"]["failed"] is True
    assert entries["20260103-090000"]["failed"] is False


def test_dataset_index_rebuild_skips_missing_recordings(tmp_path):
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "20260106-090000", recordings=False)
    out = index_dataset(
        "rebuild", index_path=str(tmp_path / "index.json"), runs_root=str(runs_root)
    )
    assert out == {"rebuilt": 0, "skipped": 1}


def test_dataset_index_rebuild_fills_date_from_dirname(tmp_path):
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "20260105-090000", result={"style": "fhss", "freq_mhz": 2450.0})
    index_path = str(tmp_path / "index.json")
    index_dataset("rebuild", index_path=index_path, runs_root=str(runs_root))
    entry = index_dataset("list", index_path=index_path)["entries"][0]
    assert entry["date"] == "20260105"  # result.json 无 date → 补目录名日期
    assert entry["style"] == "fhss"  # 透传可得字段
    out = index_dataset(
        "query", query={"date_range": ("20260101", "20260131")}, index_path=index_path
    )
    assert out["matched"] == 1


def test_dataset_index_list_all_entries(tmp_path):
    index_path = str(tmp_path / "index.json")
    index_dataset("register", record=_record(run_id="r1"), index_path=index_path)
    index_dataset("register", record=_record(run_id="r2", batch_key=None), index_path=index_path)
    out = index_dataset("list", index_path=index_path)
    assert out["total"] == 2
    assert {e["run_id"] for e in out["entries"]} == {"r1", "r2"}


def test_dataset_index_unknown_action_lists_supported(tmp_path):
    with pytest.raises(IndexEntryError) as excinfo:
        index_dataset("frobnicate", index_path=str(tmp_path / "index.json"))
    message = str(excinfo.value)
    for known in ("register", "query", "rebuild", "list"):
        assert known in message


def test_dataset_index_write_failure_raises_write_error(tmp_path):
    index_path = str(tmp_path)  # 指向已存在目录：open('w') 必炸
    with pytest.raises(IndexWriteError) as excinfo:
        index_dataset("register", record=_record(), index_path=index_path)
    assert index_path in str(excinfo.value)
    with pytest.raises(IndexWriteError):  # rebuild 落盘同口径
        index_dataset("rebuild", index_path=index_path, runs_root=str(tmp_path))


def test_dataset_index_register_total_counts_up(tmp_path):
    index_path = str(tmp_path / "index.json")
    assert index_dataset("register", record=_record(), index_path=index_path)["total"] == 1
    assert index_dataset("register", record=_record(run_id="r2"), index_path=index_path)["total"] == 2


# ---- B6 对抗审查缺陷回归 ----


def test_defect_b6_4_dirty_run_skipped_without_short_circuit(tmp_path):
    """中#4：脏 run（NaN/inf 频点、非 str 字段）计 skipped 不短路 rebuild——
    排序在脏 run 之后的合法 run 照常入索引。"""
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "20260101-000000", result={"freq_mhz": float("nan")})  # NaN 频点
    _make_run(runs_root, "20260102-000000", result={"backend": 123})  # backend 非 str
    _make_run(runs_root, "20260103-000000", result={"freq_mhz": float("inf")})  # inf 频点
    _make_run(runs_root, "20260104-000000", result={"style": ""})  # 空串按脏口径拒
    _make_run(runs_root, "20260105-000000", result={"freq_mhz": 2450.0, "backend": "b210"})
    index_path = str(tmp_path / "index.json")
    out = index_dataset("rebuild", index_path=index_path, runs_root=str(runs_root))
    assert out == {"rebuilt": 1, "skipped": 4}  # 逐条跳过且不短路
    listed = index_dataset("list", index_path=index_path)
    assert [e["run_id"] for e in listed["entries"]] == ["20260105-000000"]
    # 落盘无 NaN：脏频点不再混入 allow_nan=False 的持久化路径
    assert "NaN" not in index_path_file_text(index_path)


def index_path_file_text(index_path: str) -> str:
    with open(index_path, encoding="utf-8") as fh:
        return fh.read()


def test_defect_b6_4_read_path_selfheal_validates_each_entry(tmp_path):
    """中#4：读路径自愈 rebuild 同样逐条校验——脏 run 被剔除，合法 run 可查。"""
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "20260101-000000", result={"freq_mhz": float("nan")})
    _make_run(runs_root, "20260102-000000", result={"backend": "replay"})
    index_path = tmp_path / "index.json"
    index_path.write_text("{bad-json", encoding="utf-8")
    out = index_dataset(
        "query", query={"backend": "replay"}, index_path=str(index_path), runs_root=str(runs_root)
    )
    assert out["matched"] == 1
    assert out["entries"][0]["run_id"] == "20260102-000000"
    data = json.loads(index_path_file_text(str(index_path)))  # 自愈落盘同样无脏条目
    assert [e["run_id"] for e in data["entries"]] == ["20260102-000000"]


def test_defect_b6_7_read_path_rebuild_warns_and_persists(tmp_path, caplog):
    """低#7：读路径自动 rebuild 记一条 warning（含 index_path 与重建计数）并落盘
    重建结果（修复磁盘损坏态，二次读不再触发重建）。"""
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "20260101-080000", result={"backend": "b210"})
    _make_run(runs_root, "20260102-080000", result={"backend": "b210"})
    index_path = tmp_path / "index.json"
    index_path.write_text("<<<损坏>>>", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="src.index_dataset.index_dataset"):
        out = index_dataset("list", index_path=str(index_path), runs_root=str(runs_root))
    assert out["total"] == 2
    rebuild_warnings = [r for r in caplog.records if "自动重建" in r.getMessage()]
    assert len(rebuild_warnings) == 1  # 恰一条
    message = rebuild_warnings[0].getMessage()
    assert str(index_path) in message  # 含 index_path
    assert "重建 2 条" in message  # 含重建计数
    healed = json.loads(index_path_file_text(str(index_path)))  # 落盘修复磁盘损坏态
    assert healed["version"] == 1
    assert len(healed["entries"]) == 2
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="src.index_dataset.index_dataset"):
        again = index_dataset("list", index_path=str(index_path), runs_root=str(runs_root))
    assert again["total"] == 2
    assert not [r for r in caplog.records if "自动重建" in r.getMessage()]  # 二次读直接命中落盘索引
