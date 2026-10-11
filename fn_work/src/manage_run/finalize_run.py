"""运行收尾：确认停发射结果、封存数据文件句柄、八件套缺项检查、写结果 JSON——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Any

# 八件套产物清单：(规范名, 可接受别名元组)。检查顺序即 missing 报告顺序；
# recordings/plots 为目录、其余为文件，存在性判定统一用 os.path.exists。
# 场景副本落盘名约定为 scenario.yaml（兼容 scenario.yml 拼写）。
_EIGHT_ARTIFACTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("scenario.yaml", ("scenario.yaml", "scenario.yml")),
    ("kpi.csv", ("kpi.csv",)),
    ("events.jsonl", ("events.jsonl",)),
    ("monitor.csv", ("monitor.csv",)),
    ("recordings", ("recordings",)),
    ("report.md", ("report.md",)),
    ("plots", ("plots",)),
    ("run.log", ("run.log",)),
)

_RESULT_FILENAME = "result.json"
_RUN_LOG_FILENAME = "run.log"

# 违例/句柄标签携带原值 repr 的最大长度（超出截断，避免超长对象撑爆结果 JSON）
_LABEL_REPR_LIMIT = 80


def _is_finite_real(value: object) -> bool:
    """数值判定：int/float 且非 bool 且有限（bool 是 int 子类但语义是开关，不算时间戳）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _jsonable(value: object, _seen: set[int] | None = None) -> Any:
    """递归转换为可 JSON 序列化的值：dict/list/tuple/set 容器化，异常转 '类型: 消息'，其余转 repr。

    结果 JSON 必须写得进去（写不进=收尾失败），故 ctx 里任何奇怪对象都不得让 json.dump 炸掉；
    循环引用以 '<circular reference>' 占位，防止无限递归。
    """
    if _seen is None:
        _seen = set()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        marker = id(value)
        if marker in _seen:
            return "<circular reference>"
        _seen.add(marker)
        return {str(k): _jsonable(v, _seen) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        marker = id(value)
        if marker in _seen:
            return "<circular reference>"
        _seen.add(marker)
        return [_jsonable(v, _seen) for v in value]
    if isinstance(value, Exception):
        return f"{type(value).__name__}: {value}"
    text = repr(value)
    return text if len(text) <= _LABEL_REPR_LIMIT else text[:_LABEL_REPR_LIMIT]


def _handle_label(handle: object) -> str:
    """句柄的人类可读标识：优先文件名（file 对象的 name 属性），否则 repr 截断。"""
    name = getattr(handle, "name", None)
    if isinstance(name, str) and name:
        return name
    text = repr(handle)
    return text if len(text) <= _LABEL_REPR_LIMIT else text[:_LABEL_REPR_LIMIT]


def _is_run_log_label(label: str) -> bool:
    """句柄是否指向 run.log（用于判定日志链路是否降级）。"""
    return os.path.basename(label) == _RUN_LOG_FILENAME


def _seal_open_files(open_files: object) -> tuple[list[dict], bool]:
    """逐个封存数据文件句柄：flush 后 close，单个失败记录并继续。

    Returns:
        (close_errors, run_log_seal_failed)：
        close_errors 每项 {"file": 标识, "stage": "flush"|"close", "error": 描述}；
        run_log_seal_failed 表示 run.log 句柄封存失败（日志链路降级信号之一）。
    """
    close_errors: list[dict] = []
    run_log_seal_failed = False

    if open_files is None:
        open_files = []
    if not isinstance(open_files, (list, tuple)):
        close_errors.append(
            {
                "file": _short_repr(open_files),
                "stage": "seal",
                "error": "形状错误: ctx['open_files'] 不是清单（list/tuple），无法逐个封存",
            }
        )
        return close_errors, run_log_seal_failed

    for handle in open_files:
        label = _handle_label(handle)
        # flush 是尽力而为：句柄没有 flush 方法（如某些包装对象）不算失败，close 仍尝试
        flush_method = getattr(handle, "flush", None)
        if callable(flush_method):
            try:
                flush_method()
            except Exception as exc:  # noqa: BLE001 - 单个失败必须记录后继续
                close_errors.append(
                    {
                        "file": label,
                        "stage": "flush",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                if _is_run_log_label(label):
                    run_log_seal_failed = True
        close_method = getattr(handle, "close", None)
        if not callable(close_method):
            close_errors.append(
                {
                    "file": label,
                    "stage": "close",
                    "error": "对象缺少 close 方法，句柄未封存",
                }
            )
            continue
        try:
            close_method()
        except Exception as exc:  # noqa: BLE001 - 单个失败必须记录后继续
            close_errors.append(
                {
                    "file": label,
                    "stage": "close",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            if _is_run_log_label(label):
                run_log_seal_failed = True
    return close_errors, run_log_seal_failed


def _check_missing(run_dir: str) -> list[str]:
    """八件套缺项检查：任一别名存在即算该产物在，缺哪个列哪个（按规范名、清单顺序）。"""
    missing: list[str] = []
    for canonical, aliases in _EIGHT_ARTIFACTS:
        if not any(os.path.exists(os.path.join(run_dir, name)) for name in aliases):
            missing.append(canonical)
    return missing


def _write_run_log_line(run_dir: str, record: dict) -> bool:
    """兜底：向 run.log 追加一行结构化 JSON。成败以布尔返回，绝不抛出。"""
    try:
        line = json.dumps(record, ensure_ascii=False, default=repr)
        with open(os.path.join(run_dir, _RUN_LOG_FILENAME), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return True
    except Exception:  # noqa: BLE001 - 兜底路径自身失败只能吞掉
        return False


def _short_repr(value: object) -> str:
    text = repr(value)
    return text if len(text) <= _LABEL_REPR_LIMIT else text[:_LABEL_REPR_LIMIT]


def _failure(message: str, missing: list[str] | None = None) -> dict:
    return {
        "finalized": False,
        "result_path": None,
        "missing": list(missing or []),
        "error": message,
    }


def _finalize(ctx: dict, exit_semantics: str) -> dict:
    if not isinstance(ctx, dict):
        return _failure(f"形状错误: ctx 不是 dict（{type(ctx).__name__}），无法收尾")

    run_dir = ctx.get("run_dir")
    if not isinstance(run_dir, str) or not run_dir:
        return _failure("形状错误: ctx['run_dir'] 缺失或不是字符串，result.json 无处可写")

    # ① 确认停发射结果：缺省视为未记录，结果 JSON 中以 stop_result_recorded=False 标注
    stop_recorded = "stop_result" in ctx
    stop_result = ctx["stop_result"] if stop_recorded else None

    # ② 封存数据文件句柄（先于八件套检查：句柄未 flush/close 前，数据可能尚未落盘/建档）
    close_errors, run_log_seal_failed = _seal_open_files(ctx.get("open_files"))

    # ③ 八件套缺项检查
    missing = _check_missing(run_dir)

    # 时间口径：started_at 取 ctx（无效则空）；finished_at 优先取 ctx（便于测试注入），否则当前时刻；
    # duration_ms 折算为毫秒整数，下限钳到 1——已收尾的运行至少经历 1ms（钟粒度），保证恒为正
    started_at_raw = ctx.get("started_at")
    started_at = float(started_at_raw) if _is_finite_real(started_at_raw) else None
    finished_at_raw = ctx.get("finished_at")
    finished_at = float(finished_at_raw) if _is_finite_real(finished_at_raw) else time.time()
    if started_at is not None:
        duration_ms = max(int(round((finished_at - started_at) * 1000.0)), 1)
    else:
        duration_ms = None

    payload: dict = {
        "status": "done" if exit_semantics == "done" else "failed",
        "exit_semantics": exit_semantics,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "backend": ctx.get("backend"),
        "clock_ref": _jsonable(ctx.get("clock_ref")),
        "stop_result": _jsonable(stop_result),
        "stop_result_recorded": stop_recorded,
        "missing": missing,
        "log_degraded": ("run.log" in missing) or run_log_seal_failed,
        "close_errors": close_errors,
    }
    # alignment_error 仅在 ctx 提供时携带（对齐误差口径来自时钟决策，可能未测）
    if "alignment_error" in ctx:
        payload["alignment_error"] = _jsonable(ctx["alignment_error"])

    # ④ 写结果 JSON；写不进→尽力向 run.log 落一行后返回 finalized=False，不抛出
    result_path = os.path.join(run_dir, _RESULT_FILENAME)
    try:
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001 - 收尾自身失败不得向上抛
        fallback_ok = _write_run_log_line(
            run_dir,
            {
                "ts": time.time(),
                "level": "error",
                "event": "finalize_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "result_path": result_path,
            },
        )
        message = f"result.json 写入失败: {type(exc).__name__}: {exc}"
        if not fallback_ok:
            message += "（run.log 兜底行亦写入失败）"
        return _failure(message, missing)

    return {"finalized": True, "result_path": result_path, "missing": missing}


def finalize_run(ctx: dict, exit_semantics: str) -> dict:
    """运行收尾：确认停发射结果、封存数据文件句柄、八件套缺项检查、写结果 JSON。

    Args:
        ctx: 运行上下文，至少含 "run_dir"（结果 JSON 与八件套的落点）；可选键——
            "stop_result"（停发射结果，缺省视为未记录并在结果中标注）、
            "open_files"（待封存的文件句柄清单，逐个 flush+close，单个失败记录后继续）、
            "started_at"/"finished_at"（epoch 秒；finished_at 缺省取当前时刻）、
            "backend"、"clock_ref"、"alignment_error"（有时才写入结果）。
        exit_semantics: 退出语义（'done' | 'failed' | 退出码语义描述），原样透传入结果 JSON；
            仅字面 'done' 映射 status='done'，其余一律 'failed'。

    Returns:
        {"finalized": bool, "result_path": str | None, "missing": list}；
        自身失败（result.json 写不进等）时 finalized=False 并追加 "error" 键。

    永不抛出：任何内部异常都被收敛为 finalized=False 的返回值；result.json 写不进时
    尽力向 run.log 追加一行结构化错误后返回。
    """
    try:
        return _finalize(ctx, exit_semantics)
    except Exception as exc:  # noqa: BLE001 - 对外承诺：收尾永不抛出
        return _failure(f"finalize_run 兜底异常: {type(exc).__name__}: {exc}")
