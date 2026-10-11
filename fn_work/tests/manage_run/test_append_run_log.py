"""append_run_log 对抗测试：正常落盘/字段与时间戳规整/非法输入矫正/静默降级/环形缓冲。"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.manage_run import append_run_log as mod
from src.manage_run.append_run_log import append_run_log

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}$")


@pytest.fixture(autouse=True)
def _isolate_module_buffer():
    """模块级降级缓冲在用例间隔离，避免计数串扰。"""
    mod._BUFFER.clear()
    yield
    mod._BUFFER.clear()


def _read_entries(run_dir: Path) -> list[dict]:
    text = (run_dir / mod.LOG_FILENAME).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_normal_append_writes_complete_json_line(tmp_path):
    result = append_run_log(str(tmp_path), "INFO", "hello", {"k": "v"})
    assert result == {"written": True, "degraded": False, "buffered_count": 0}
    raw = (tmp_path / mod.LOG_FILENAME).read_text(encoding="utf-8")
    assert raw.endswith("\n")  # 换行落盘
    assert raw.count("\n") == 1  # 单行 JSON
    entry = json.loads(raw)
    assert set(entry) == {"ts", "level", "module", "msg", "ctx"}  # 字段齐
    assert entry["level"] == "INFO"
    assert entry["msg"] == "hello"
    assert entry["ctx"] == {"k": "v"}
    assert entry["module"] == __name__  # module 取直接调用方模块名


def test_timestamp_iso8601_with_millisecond_precision(tmp_path):
    append_run_log(str(tmp_path), "DEBUG", "ts check")  # context 缺省=None
    entry = _read_entries(tmp_path)[0]
    assert _TS_RE.match(entry["ts"]), entry["ts"]
    assert entry["ctx"] == {}  # 缺省 ctx 置 {}


def test_invalid_level_downgraded_to_warn_and_recorded(tmp_path):
    append_run_log(str(tmp_path), "TRACE", "bad level", {"a": 1})
    entry = _read_entries(tmp_path)[0]
    assert entry["level"] == "WARN"
    assert entry["ctx"] == {"a": 1, "level_rejected": "TRACE"}  # 原字段保留+拒绝记录


def test_non_string_level_rejected_as_warn(tmp_path):
    append_run_log(str(tmp_path), None, "level none")
    entry = _read_entries(tmp_path)[0]
    assert entry["level"] == "WARN"
    assert entry["ctx"]["level_rejected"] is None


def test_int_message_coerced_to_str(tmp_path):
    append_run_log(str(tmp_path), "INFO", 123)
    assert _read_entries(tmp_path)[0]["msg"] == "123"


def test_none_message_coerced_to_str(tmp_path):
    append_run_log(str(tmp_path), "INFO", None)
    assert _read_entries(tmp_path)[0]["msg"] == "None"


def test_non_dict_context_replaced_with_empty_dict(tmp_path):
    append_run_log(str(tmp_path), "INFO", "ctx str", "x")
    assert _read_entries(tmp_path)[0]["ctx"] == {}


def test_write_failure_degrades_silently_without_raise(tmp_path):
    bad_dir = str(tmp_path / "no" / "such" / "dir")  # 目录不存在
    r1 = append_run_log(bad_dir, "INFO", "m1")
    r2 = append_run_log(bad_dir, "ERROR", "m2")
    assert r1 == {"written": False, "degraded": True, "buffered_count": 1}
    assert r2["degraded"] is True
    assert r2["buffered_count"] == 2  # 缓冲计数增
    assert not (tmp_path / "no").exists()  # 未误建目录/文件


def test_buffer_ring_cap_drops_oldest(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "BUFFER_MAX", 2)  # mock 小上限
    bad_dir = str(tmp_path / "gone")
    append_run_log(bad_dir, "INFO", "m1")
    append_run_log(bad_dir, "INFO", "m2")
    r3 = append_run_log(bad_dir, "INFO", "m3")
    assert r3["buffered_count"] == 2  # 封顶
    msgs = [json.loads(line)["msg"] for line in mod.buffered_lines()]
    assert msgs == ["m2", "m3"]  # 最旧 m1 被丢弃，顺序保持


def test_recovers_to_disk_after_dir_becomes_valid(tmp_path):
    bad_dir = str(tmp_path / "vanish")
    r_bad = append_run_log(bad_dir, "INFO", "buffered")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    r_ok = append_run_log(str(run_dir), "INFO", "recovered")
    assert r_bad["degraded"] is True
    assert r_ok == {"written": True, "degraded": False, "buffered_count": 1}
    assert [e["msg"] for e in _read_entries(run_dir)] == ["recovered"]  # 恢复后继续落盘


def test_multiple_appends_preserve_order(tmp_path):
    levels = ["DEBUG", "INFO", "WARN", "ERROR", "INFO"]
    for i, lvl in enumerate(levels):
        append_run_log(str(tmp_path), lvl, f"m{i}")
    entries = _read_entries(tmp_path)
    assert [e["msg"] for e in entries] == [f"m{i}" for i in range(5)]  # 顺序保持
    assert [e["level"] for e in entries] == levels  # 四级合法原样透传
