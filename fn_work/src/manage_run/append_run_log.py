"""向 run.log 追加结构化日志行——重写规约与签名意图详见 fn_docs/responsibility.md。

单行 JSON：{"ts": ISO8601 带毫秒, "level": "DEBUG|INFO|WARN|ERROR", "module": 调用方模块名,
"msg": str, "ctx": {...}}。行级落盘（每条即时 flush+换行，崩溃不丢已写行）；非法 level→
记为 WARN 并在 ctx 加 level_rejected；msg 非字符串→str() 化；ctx 非 dict→忽略置 {}；
float NaN/±Inf 序列化前规整为 '__nan__'/'__inf__'/'-__inf__'（json.dumps 统一
allow_nan=False，行内绝不出现非严格 JSON 字面量）；写失败（磁盘满/目录没了）→静默降级：
存入进程级环形内存缓冲（上限 BUFFER_MAX 条，超限丢最旧）并携带归属 run_dir——运行收尾
经 drain_buffered_lines 取走重放，只许写回行自己的运行目录（跨运行不收编），绝不抛出。
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime

#: 合法日志级别；其余一律降级 WARN 并在 ctx 记 level_rejected 原值。
VALID_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")

#: 降级内存缓冲上限（环形：超限丢最旧）；测试可 monkeypatch 小值。
BUFFER_MAX = 1000

#: 运行目录内日志文件名。
LOG_FILENAME = "run.log"

#: 非有限浮点占位（allow_nan=False 严格序列化下的可读替代）。
NAN_TOKEN = "__nan__"
INF_TOKEN = "__inf__"
NEG_INF_TOKEN = "-__inf__"

#: 进程级降级缓冲：[(归属 run_dir, 已序列化日志行), ...]。
#: 归属随行携带——A 运行滞留行只能重放进 A 的 run.log，B 运行 drain 到也不得收编。
_BUFFER: "list[tuple[str, str]]" = []


def buffered_lines() -> list[str]:
    """返回降级缓冲内待落盘日志行的副本（不含归属信息，供观测/测试）。"""
    return [line for _, line in _BUFFER]


def drain_buffered_lines() -> "list[tuple[str, str]]":
    """取走并清空降级缓冲，返回 [(归属 run_dir, 已序列化行), ...]。

    只应在运行收尾（wind_down）调用：取走后缓冲即空，落盘成功的行自然移除；
    仍失败的行须立即归还（本运行行经 append_run_log 归还、他运行行经
    restore_stranded_lines 原样归还），保证滞留行的归属与内容不被破坏。
    """
    drained = list(_BUFFER)
    _BUFFER.clear()
    return drained


def restore_stranded_lines(pairs: "list[tuple[str, str]]") -> None:
    """把 (归属 run_dir, 行) 清单原样归还降级缓冲（环形上限语义同降级路径）。

    供收尾重放失败时立即归还滞留行：行保持原始归属与内容（不重序列化、
    不改 ts/module），后续运行只重放归属自己的行，绝不写入他运行目录。
    """
    for owner_dir, line in pairs:
        _BUFFER.append((owner_dir, line))
    overflow = len(_BUFFER) - BUFFER_MAX
    if overflow > 0:
        del _BUFFER[:overflow]  # 环形：超限丢最旧


def _sanitize_nonfinite(value):
    """递归把 float NaN/±Inf 规整为占位字符串（allow_nan=False 严格序列化前置处理）。

    容器逐层规整；其余类型原样返回（交 json.dumps 的 default=str 兜底）。
    循环引用等病态结构本函数自身会抛 RecursionError——调用点须在 try 内。
    """
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return NAN_TOKEN
        return NEG_INF_TOKEN if value < 0 else INF_TOKEN
    if isinstance(value, dict):
        return {_sanitize_nonfinite(k): _sanitize_nonfinite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_nonfinite(v) for v in value]
    return value


def _caller_module_name() -> str:
    """取 append_run_log 直接调用方的模块名；取不到回退 "unknown"。"""
    try:
        frame = sys._getframe(2)  # 本函数 ← append_run_log ← 调用方
        name = frame.f_globals.get("__name__")
        if isinstance(name, str) and name:
            return name
    except Exception:  # noqa: BLE001 - 取帧失败只影响 module 字段，不影响落日志
        pass
    return "unknown"


def append_run_log(run_dir: str, level: str, message: str, context: dict | None = None) -> dict:
    """向 run_dir/run.log 追加一行结构化 JSON 日志。

    返回 {"written": 本条是否已落盘, "degraded": 本条是否降级进内存缓冲,
    "buffered_count": 当前缓冲内待落盘条数}；任何写失败均静默降级，绝不抛出。
    """
    ctx: dict = dict(context) if isinstance(context, dict) else {}
    if isinstance(level, str) and level in VALID_LEVELS:
        norm_level: str = level
    else:
        norm_level = "WARN"
        ctx["level_rejected"] = level
    record = {
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "level": norm_level,
        "module": _caller_module_name(),
        "msg": message if isinstance(message, str) else str(message),
        "ctx": ctx,
    }
    try:
        line = json.dumps(
            _sanitize_nonfinite(record), ensure_ascii=False, default=str, allow_nan=False
        )
    except Exception:  # noqa: BLE001 - ctx 含循环引用等极端值也不能让日志抛出
        line = json.dumps(
            {
                "ts": record["ts"],
                "level": norm_level,
                "module": record["module"],
                "msg": str(message),
                "ctx": {},
            },
            ensure_ascii=False,
            allow_nan=False,
        )

    owner = _owner_dir(run_dir)
    try:
        path = os.path.join(owner, LOG_FILENAME)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()  # 行级落盘：即时刷出，崩溃不丢已写行
    except Exception:  # noqa: BLE001 - 静默降级契约：磁盘满/目录没了等绝不抛出
        restore_stranded_lines([(owner, line)])
        return {"written": False, "degraded": True, "buffered_count": len(_BUFFER)}
    return {"written": True, "degraded": False, "buffered_count": len(_BUFFER)}


def _owner_dir(run_dir: object) -> str:
    """降级归属键：run_dir 规整为字符串（异常输入回退 repr，本函数绝不抛出）。"""
    try:
        text = os.fspath(run_dir)
        if isinstance(text, bytes):
            return text.decode("utf-8", "replace")
        return text
    except Exception:  # noqa: BLE001 - 归属键取不到也不能破坏降级契约
        try:
            return repr(run_dir)
        except Exception:  # noqa: BLE001 - 连 repr 都炸的异类对象
            return "<unrepresentable-run-dir>"
