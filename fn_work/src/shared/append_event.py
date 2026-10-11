"""events.jsonl 追加注入事件（单调钟毫秒+ISO 墙钟盖戳，行级落盘）——重写规约与签名意图详见 fn_docs/responsibility.md。

NaN/±Inf 占位与 allow_nan=False 严格序列化与 append_run_log 同套口径，但错误语义
相反：事件是测量真值，run_dir 无效/写失败/形状不合法一律显式抛 EventWriteError
（本文件定义，含路径与原因，由调用方走停发射路径），绝不静默缓冲。
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime

__all__ = ["EventWriteError", "append_event"]

#: 运行目录内事件文件名。
EVENTS_FILENAME = "events.jsonl"

#: 非有限浮点占位（与 append_run_log 同套口径，allow_nan=False 严格序列化下的可读替代）。
NAN_TOKEN = "__nan__"
INF_TOKEN = "__inf__"
NEG_INF_TOKEN = "-__inf__"


class EventWriteError(RuntimeError):
    """事件写入失败：run_dir 无效、写/序列化失败或事件形状不合法（event 非 dict、type 缺失或非非空 str）。

    与 append_run_log 的静默降级语义不同：事件是测量真值，写失败必须显式抛出
    （调用方走停发射路径），不做任何内存缓冲。reason 为失败原因，path 为事发
    路径（运行目录或事件文件路径）；str(exc) 形如 "reason: path"。
    """

    def __init__(self, reason: str, path: str = "") -> None:
        super().__init__(f"{reason}: {path}" if path else reason)
        self.reason = reason
        self.path = path


def _sanitize_nonfinite(value, _visited: set | None = None):
    """递归把 float NaN/±Inf 规整为占位字符串（与 append_run_log 同套口径）。

    容器逐层规整且不改动原容器；其余类型原样返回（交 json.dumps 的 default=str
    兜底）。B8高#1：自引用/相互引用的容器（循环引用）在此拦截——沿当前递归
    路径记已访问容器 id 集合（出栈即移除：同层共享引用/DAG 放行，仅真环拒），
    遇重复 id 抛 ValueError，由 append_event 统一包装为 EventWriteError，
    绝不让 RecursionError 逃逸。
    """
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return NAN_TOKEN
        return NEG_INF_TOKEN if value < 0 else INF_TOKEN
    if isinstance(value, (dict, list, tuple)):
        if _visited is None:
            _visited = set()
        if id(value) in _visited:
            raise ValueError(
                f"事件含循环引用（容器 {type(value).__name__} 自引用/相互引用，"
                f"id={id(value)} 在递归路径上重复出现）"
            )
        _visited.add(id(value))
        try:
            if isinstance(value, dict):
                return {
                    _sanitize_nonfinite(k, _visited): _sanitize_nonfinite(v, _visited)
                    for k, v in value.items()
                }
            return [_sanitize_nonfinite(v, _visited) for v in value]
        finally:
            _visited.discard(id(value))  # 出栈：仅拦真环，DAG 共享引用放行
    return value


def _owner_dir(run_dir: object) -> str:
    """run_dir 规整为字符串路径（str/bytes/PathLike 之外的异类回退 repr，本函数绝不抛出）。"""
    try:
        text = os.fspath(run_dir)
        if isinstance(text, bytes):
            return text.decode("utf-8", "replace")
        return text
    except Exception:  # noqa: BLE001 - 路径规整失败不能掩盖事件自身的错误
        try:
            return repr(run_dir)
        except Exception:  # noqa: BLE001 - 连 repr 都炸的异类对象
            return "<unrepresentable-run-dir>"


def append_event(run_dir: str, event: dict) -> dict:
    """向 run_dir/events.jsonl 追加一条注入事件，返回写入的事件行 dict。

    事件必填 'type'（非空 str；缺失/非 str/空串均为形状错，显式抛出，不落半行）；
    本函数权威盖戳并一律覆盖预置值——'ts'（time.monotonic() 毫秒 int，单调钟供
    三路对齐）与 'wallclock'（ISO8601 毫秒本地时间，人读）；float NaN/±Inf 递归
    规整为占位字符串（allow_nan=False，行内绝不出现非严格 JSON 字面量）；单行
    JSON 追加+即时 flush（行级落盘，崩溃不丢已写行）；入参 event 不被原地修改，
    返回值为该行的逐字段等价重新解析结果（与文件内容一致）。run_dir 无效
    （不存在/非目录）、写/序列化失败或事件含循环引用（自引用/相互引用容器）→
    EventWriteError（含路径与原因）。
    """
    if not isinstance(event, dict):
        raise EventWriteError(
            f"事件必须为 dict，实际 {type(event).__name__}", _owner_dir(run_dir)
        )
    event_type = event.get("type")
    if not isinstance(event_type, str) or not event_type:
        raise EventWriteError(
            f"事件必填 'type'（非空 str），实际 {event_type!r}", _owner_dir(run_dir)
        )

    owner = _owner_dir(run_dir)
    path = os.path.join(owner, EVENTS_FILENAME)

    # B8高#1：消毒+盖戳+序列化同一 try——循环引用（消毒 ValueError）与不可序列化
    # 键等病态事件统一包装 EventWriteError（含路径与原因），RecursionError 不逃逸。
    try:
        line_dict = _sanitize_nonfinite(dict(event))  # 规整落在浅拷贝上：入参不被原地修改
        line_dict["ts"] = int(time.monotonic() * 1000)  # 单调钟毫秒：三路对齐基准
        line_dict["wallclock"] = datetime.now().isoformat(timespec="milliseconds")  # 人读墙钟
        line = json.dumps(line_dict, ensure_ascii=False, default=str, allow_nan=False)
    except Exception as exc:  # noqa: BLE001 - 循环引用/不可序列化键等病态事件
        raise EventWriteError(f"事件序列化失败 {type(exc).__name__}: {exc}", path) from exc

    try:
        if not os.path.isdir(owner):
            raise NotADirectoryError(f"运行目录不存在或不是目录: {owner}")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()  # 行级落盘：即时刷出，崩溃不丢已写行
    except Exception as exc:  # noqa: BLE001 - 事件是测量真值：写失败显式抛，绝不静默缓冲
        raise EventWriteError(f"事件写入失败 {type(exc).__name__}: {exc}", path) from exc

    return json.loads(line)
