"""向 run.log 追加结构化日志行——重写规约与签名意图详见 fn_docs/responsibility.md。

单行 JSON：{"ts": ISO8601 带毫秒, "level": "DEBUG|INFO|WARN|ERROR", "module": 调用方模块名,
"msg": str, "ctx": {...}}。行级落盘（每条即时 flush+换行，崩溃不丢已写行）；非法 level→
记为 WARN 并在 ctx 加 level_rejected；msg 非字符串→str() 化；ctx 非 dict→忽略置 {}；
写失败（磁盘满/目录没了）→静默降级：存入进程级环形内存缓冲（上限 BUFFER_MAX 条，超限丢
最旧），返回 degraded=True 供运行收尾在结果 JSON 标日志不完整，绝不抛出。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

#: 合法日志级别；其余一律降级 WARN 并在 ctx 记 level_rejected 原值。
VALID_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")

#: 降级内存缓冲上限（环形：超限丢最旧）；测试可 monkeypatch 小值。
BUFFER_MAX = 1000

#: 运行目录内日志文件名。
LOG_FILENAME = "run.log"

#: 进程级降级缓冲（已序列化的日志行；运行收尾据此在结果 JSON 标日志不完整）。
_BUFFER: list[str] = []


def buffered_lines() -> list[str]:
    """返回降级缓冲内待落盘日志行的副本（供运行收尾读取）。"""
    return list(_BUFFER)


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
        line = json.dumps(record, ensure_ascii=False, default=str)
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
        )

    try:
        path = os.path.join(os.fspath(run_dir), LOG_FILENAME)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()  # 行级落盘：即时刷出，崩溃不丢已写行
    except Exception:  # noqa: BLE001 - 静默降级契约：磁盘满/目录没了等绝不抛出
        _BUFFER.append(line)
        overflow = len(_BUFFER) - BUFFER_MAX
        if overflow > 0:
            del _BUFFER[:overflow]  # 环形：超限丢最旧
        return {"written": False, "degraded": True, "buffered_count": len(_BUFFER)}
    return {"written": True, "degraded": False, "buffered_count": len(_BUFFER)}
