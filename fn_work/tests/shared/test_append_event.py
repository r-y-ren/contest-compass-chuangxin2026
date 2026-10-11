"""append_event 对抗测试：严格 JSON 落盘+双时间戳/单调钟递增/NaN 规整/嵌套事件/
形状错（type 缺失或非非空 str、event 非 dict）显式抛出/目录失效与写失败含原因/顺序保持。"""
from __future__ import annotations

import builtins
import copy
import json
import re
import time
from datetime import datetime
from pathlib import Path

import pytest

from src.shared import append_event as mod
from src.shared.append_event import EventWriteError, append_event

_WALLCLOCK_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}$")


def _reject_constant(name: str) -> None:
    """严格解析哨兵：行内出现 NaN/Infinity/-Infinity 字面量即判失败。"""
    raise ValueError(f"非法 JSON 字面量: {name}")


def _read_lines(run_dir: Path) -> list[dict]:
    """逐行严格读回 events.jsonl（parse_constant 拒绝非标准字面量）。"""
    raw = (run_dir / mod.EVENTS_FILENAME).read_text(encoding="utf-8")
    return [json.loads(line, parse_constant=_reject_constant) for line in raw.splitlines()]


def test_written_line_is_strict_json_with_stamps_and_matches_return(tmp_path):
    """① 写入→文件为单行严格 JSON（parse_constant 不触发），补全 ts/wallclock/type，
    返回值与文件行逐字段一致（返回即写入行）。"""
    returned = append_event(str(tmp_path), {"type": "inject_start", "step": 1, "level_dbm": -10.5})
    raw = (tmp_path / mod.EVENTS_FILENAME).read_text(encoding="utf-8")
    assert raw.endswith("\n")  # 换行落盘
    assert raw.count("\n") == 1  # 单行
    line = json.loads(raw, parse_constant=_reject_constant)  # 严格解析不触发
    assert line["type"] == "inject_start"
    assert isinstance(line["ts"], int)  # 单调钟毫秒 int
    assert _WALLCLOCK_RE.match(line["wallclock"]), line["wallclock"]  # ISO8601 毫秒
    assert line == returned  # 返回值=文件行


def test_wallclock_is_local_iso8601_near_now(tmp_path):
    """② wallclock 取本地墙钟且贴近当前时刻（人读时间不走单调钟）。"""
    before = datetime.now()
    returned = append_event(str(tmp_path), {"type": "tick"})
    after = datetime.now()
    wall = datetime.fromisoformat(returned["wallclock"])
    # wallclock 截断到毫秒，下界同步截断比较
    before_ms = before.replace(microsecond=(before.microsecond // 1000) * 1000)
    assert before_ms <= wall <= after  # 落在调用前后窗内（本地时钟）


def test_ts_strictly_increasing_three_appends_within_monotonic_bounds(tmp_path):
    """③ 连续三次追加 ts 严格递增，且数值确实取自主机单调钟（落在前后界内）。"""
    before = int(time.monotonic() * 1000)
    stamps = []
    for i in range(3):
        stamps.append(append_event(str(tmp_path), {"type": "tick", "i": i})["ts"])
        time.sleep(0.002)  # 隔开毫秒窗：让严格递增可稳定判定
    after = int(time.monotonic() * 1000)
    assert stamps[0] < stamps[1] < stamps[2]  # 单调钟严格递增
    assert all(before <= ts <= after for ts in stamps)  # 取自真实 monotonic 毫秒


def test_nan_inf_values_normalized_to_placeholder_tokens(tmp_path):
    """④ float NaN/±Inf（含嵌套）→ '__nan__'/'__inf__'/'-__inf__' 占位串，
    行内绝不出现非严格 JSON 字面量，返回值同步规整。"""
    event = {
        "type": "meas",
        "snr": float("nan"),
        "peak": float("inf"),
        "floor": float("-inf"),
        "nested": {"deep": [float("nan"), float("inf")]},
    }
    returned = append_event(str(tmp_path), event)
    line = _read_lines(tmp_path)[0]
    assert line["snr"] == mod.NAN_TOKEN
    assert line["peak"] == mod.INF_TOKEN
    assert line["floor"] == mod.NEG_INF_TOKEN
    assert line["nested"] == {"deep": [mod.NAN_TOKEN, mod.INF_TOKEN]}  # 嵌套同口径
    assert returned == line
    assert "ts" in line and "wallclock" in line  # 规整不影响盖戳


def test_nested_dict_event_roundtrip_and_input_not_mutated(tmp_path):
    """⑤ 嵌套 dict/list 事件逐层保真往返；入参 dict 不被原地盖戳/规整。"""
    original = {
        "type": "ladder_step",
        "meta": {"gain_db": 12, "tags": ["a", "b"], "inner": {"jsr": 3.5}},
        "combo": (30, 0),  # 元组→JSON 数组
        "note": None,
    }
    snapshot = copy.deepcopy(original)
    returned = append_event(str(tmp_path), original)
    line = _read_lines(tmp_path)[0]
    assert line["meta"] == {"gain_db": 12, "tags": ["a", "b"], "inner": {"jsr": 3.5}}
    assert line["combo"] == [30, 0]
    assert line["note"] is None
    assert returned == line
    assert "ts" not in original and "wallclock" not in original  # 入参不被原地盖戳
    assert original == snapshot  # NaN 规整也只作用在拷贝上


def test_missing_type_raises_and_writes_nothing(tmp_path):
    """⑥ type 缺失（形状错）→EventWriteError 显式抛出，且未落半行/未建文件。"""
    with pytest.raises(EventWriteError) as ei:
        append_event(str(tmp_path), {"level_dbm": 0})
    assert "type" in str(ei.value)
    assert not (tmp_path / mod.EVENTS_FILENAME).exists()  # 校验先于任何 I/O


@pytest.mark.parametrize("bad_type", ["", 7, None])
def test_blank_or_non_str_type_raises(tmp_path, bad_type):
    """⑦ type 为空串/非 str→形状错显式抛出（规约：非空 str）。"""
    with pytest.raises(EventWriteError) as ei:
        append_event(str(tmp_path), {"type": bad_type})
    assert ei.value.reason


@pytest.mark.parametrize("bad_event", [[("type", "x")], "type=x", 42, None])
def test_non_dict_event_raises(tmp_path, bad_event):
    """⑧ event 非 dict（list/str/int/None）→EventWriteError。"""
    with pytest.raises(EventWriteError):
        append_event(str(tmp_path), bad_event)
    assert not (tmp_path / mod.EVENTS_FILENAME).exists()


def test_missing_run_dir_raises_with_path(tmp_path):
    """⑨ run_dir 不存在→EventWriteError，path 指向预期事件文件，且不误建目录。"""
    missing = str(tmp_path / "no" / "such")
    with pytest.raises(EventWriteError) as ei:
        append_event(missing, {"type": "x"})
    assert ei.value.path == str(tmp_path / "no" / "such" / mod.EVENTS_FILENAME)
    assert "不存在" in ei.value.reason  # 原因可读
    assert not (tmp_path / "no").exists()


def test_run_dir_is_regular_file_raises(tmp_path):
    """⑩ run_dir 指向普通文件（非目录）→同样显式抛出。"""
    as_file = tmp_path / "not_a_dir"
    as_file.write_text("x", encoding="utf-8")
    with pytest.raises(EventWriteError) as ei:
        append_event(str(as_file), {"type": "x"})
    assert ei.value.path.endswith(mod.EVENTS_FILENAME)


def test_target_file_is_directory_raises_with_reason(tmp_path):
    """⑪ events.jsonl 位置被目录占用（写失败）→EventWriteError 携带路径与底层原因。"""
    target = tmp_path / mod.EVENTS_FILENAME
    target.mkdir()
    with pytest.raises(EventWriteError) as ei:
        append_event(str(tmp_path), {"type": "x"})
    assert ei.value.path == str(target)  # 路径
    assert "IsADirectoryError" in ei.value.reason  # 原因（底层 OS 错误类型）


def test_oserror_during_write_wrapped_with_path_and_reason(tmp_path, monkeypatch):
    """⑫ open 阶段 OSError（如磁盘满）→包装为 EventWriteError，原因与路径不丢。"""
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(builtins, "open", _boom)
    with pytest.raises(EventWriteError) as ei:
        append_event(str(tmp_path), {"type": "x"})
    assert "disk full" in ei.value.reason
    assert ei.value.path.endswith(mod.EVENTS_FILENAME)


def test_unencodable_surrogate_value_raises(tmp_path):
    """⑬ 值含孤立代理字符（utf-8 不可编码）→写失败显式抛出，不静默缓冲。"""
    with pytest.raises(EventWriteError) as ei:
        append_event(str(tmp_path), {"type": "x", "note": "\ud800"})
    assert ei.value.path.endswith(mod.EVENTS_FILENAME)
    target = tmp_path / mod.EVENTS_FILENAME
    assert (not target.exists()) or target.stat().st_size == 0  # 失败行不留半截（open 可能已建空文件）


def test_preset_stamps_overwritten_by_authority(tmp_path):
    """⑭ 调用方预置 ts/wallclock 被权威盖戳覆盖（统一主机钟，杜绝陈旧时间戳）。"""
    returned = append_event(
        str(tmp_path),
        {"type": "x", "ts": 1, "wallclock": "2000-01-01T00:00:00.000"},
    )
    line = _read_lines(tmp_path)[0]
    assert line["ts"] != 1 and isinstance(line["ts"], int)
    assert line["wallclock"] != "2000-01-01T00:00:00.000"
    assert _WALLCLOCK_RE.match(line["wallclock"])
    assert returned == line


def test_multiple_appends_preserve_order_and_timeline_sorted(tmp_path):
    """⑮ 多行追加：文件行序=写入序，ts 时间线不回退。"""
    written = [append_event(str(tmp_path), {"type": "step", "i": i})["i"] for i in range(5)]
    assert written == list(range(5))  # 返回顺序
    lines = _read_lines(tmp_path)
    assert [line["i"] for line in lines] == list(range(5))  # 文件行序保持
    stamps = [line["ts"] for line in lines]
    assert stamps == sorted(stamps)  # 时间线不回退（严格性由③专测）


def test_pathlike_run_dir_accepted(tmp_path):
    """⑯ pathlib.Path 形态的 run_dir 直接可用（os.PathLike 宽容）。"""
    returned = append_event(tmp_path, {"type": "x"})
    assert returned["type"] == "x"
    assert (tmp_path / mod.EVENTS_FILENAME).exists()
