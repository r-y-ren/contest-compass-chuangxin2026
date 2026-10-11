"""运行全生命周期：状态机+八件套工作区+先停发射收尾+结果 JSON——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Callable
from uuid import uuid4

from .append_run_log import (
    LOG_FILENAME,
    append_run_log,
    drain_buffered_lines,
    restore_stranded_lines,
)
from .create_run_workspace import RunDirError, create_run_workspace
from .finalize_run import finalize_run
from src.shared.stop_transmit_safely import stop_transmit_safely

__all__ = ["VALID_STATES", "LifecycleError", "RunDirError", "manage_run"]

#: 状态机状态集（合法迁移见 _TRANSITIONS）
VALID_STATES = ("starting", "armed", "running", "stopping", "done", "failed")

#: 合法迁移表：starting→armed→running→stopping→done/failed。任意存活状态均可入 stopping
#: （"任何退出路径先停发射"铁律的状态机表达）；done/failed 为终态无出边；跳级（如 armed→done）非法。
_TRANSITIONS: dict[str, frozenset] = {
    "starting": frozenset({"armed", "stopping"}),
    "armed": frozenset({"running", "stopping"}),
    "running": frozenset({"stopping"}),
    "stopping": frozenset({"done", "failed"}),
    "done": frozenset(),
    "failed": frozenset(),
}

#: 终态集合：无出边，再迁移（含 set_state）一律 LifecycleError。
_TERMINAL = frozenset({"done", "failed"})


class LifecycleError(RuntimeError):
    """非法状态迁移（如 done 后再 running、armed 跳级 done、未知状态名）。

    from_state/to_state 属性携带迁移两端，str(exc) 形如 "非法状态迁移: done -> running"。
    """

    def __init__(self, from_state: str, to_state: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"非法状态迁移: {from_state} -> {to_state}")


def _backend_label(backend: Any) -> Any:
    """backend 的 JSON 安全标注：可序列化标量/容器原样（逐层清洗），实例以类名标注。

    result.json 必须写得进去（写不进=收尾失败），而 backend 常是硬件句柄类实例——
    交给 finalize_run 前先收敛为可落盘表示；None 保持 None。
    """
    if backend is None or isinstance(backend, (str, int, float, bool)):
        return backend
    if isinstance(backend, dict):
        return {str(key): _backend_label(value) for key, value in backend.items()}
    if isinstance(backend, (list, tuple)):
        return [_backend_label(value) for value in backend]
    return type(backend).__name__


def _replay_buffered_log_lines(run_dir: str, drained: "list[tuple[str, str]]") -> int:
    """把降级缓冲中的滞留日志行追回 run.log，返回仍滞留条数；绝不写入他运行目录。

    drain 已清空缓冲：落盘成功的行自然移除（不回缓冲）；仍失败的行立即归还——
    归属本运行的行经 append_run_log 归还（其降级语义自然保留：写失败自动再进缓冲，
    偶发恢复则顺势落盘），归属他运行的行原样归还缓冲（B 运行不得收编 A 运行的
    滞留行）。缓冲行本身就是已序列化的完整 JSON 行，按行原样追加（不经
    append_run_log 重放——重序列化会丢失原始 ts/module）。行级 flush 同契约：崩溃不丢已写行。
    """
    stranded = 0
    for owner_dir, line in drained:
        if owner_dir != run_dir:
            restore_stranded_lines([(owner_dir, line)])
            stranded += 1
            continue
        try:
            with open(os.path.join(run_dir, LOG_FILENAME), "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
        except Exception:  # noqa: BLE001 - 行级重放失败立即归还，绝不写入他运行目录
            stranded += 1
            _return_line_via_append(run_dir, line)
    return stranded


def _return_line_via_append(run_dir: str, line: str) -> None:
    """把重放失败的滞留行经 append_run_log 归还缓冲（写失败自动滞留=降级语义自然保留）。

    行损坏到无法解析时退回原样归还（restore_stranded_lines），尽力不丢滞留行。
    """
    try:
        record = json.loads(line)
        append_run_log(run_dir, record.get("level"), record.get("msg", line), record.get("ctx"))
    except Exception:  # noqa: BLE001 - 归还路径尽力而为，绝不抛出
        restore_stranded_lines([(run_dir, line)])


def _mark_result_log_degraded(run_dir: str, result: dict) -> None:
    """滞留行仍存在时把 result.json 的 log_degraded 补正为 True（尽力，失败不抛）。

    finalize_run 只认 run.log 缺失/句柄封存失败两个降级信号，看不到降级缓冲；
    "磁盘恢复不了、行滞留内存而 run.log 仍在"是第三信号，只能在收尾落盘后
    于结果 JSON 上补这一笔（重写沿用 finalize 的 JSON 排版）。
    """
    result_path = result.get("result_path")
    if not isinstance(result_path, str) or not result_path:
        result_path = os.path.join(run_dir, "result.json")
    try:
        with open(result_path, encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict) or payload.get("log_degraded"):
            return
        payload["log_degraded"] = True
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001 - 补正属尽力而为，自身失败不抛
        return


def manage_run(
    scenario: dict,
    execute: Callable[[dict], Any],
    runs_root: str = "runs",
    backend: Any = None,
) -> dict:
    """一次运行的全生命周期管理：建工作区→驱动状态机→执行回调→先停发射收尾→结果 JSON。

    Args:
        scenario: 规范化场景 dict（由 create_run_workspace 落盘为工作区 scenario.yaml 副本）。
        execute: 执行回调，签名 execute(ctx)。ctx 含：
            'run_dir'（运行目录绝对路径）、'scenario'（场景引用）、'backend'（后端引用）、
            'started_at'（epoch 秒）、'open_files'（待收尾封存的句柄清单，可 append）、
            'log'(level, message, context)（run.log 追加封装，降级契约同 append_run_log；
                写失败的滞留行在收尾时尽力重放回 run.log，仍滞留则 result.json 标 log_degraded）、
            'set_state'(to_state)（申请一次合法迁移，非法迁移抛 LifecycleError）。
        runs_root: 运行目录基础路径（默认 'runs'，不存在则自动创建）。
        backend: 发射后端实例，收尾时传给 stop_transmit_safely（可为 None）；每次运行生成
            独立 run_token 传入（运行级幂等）——同一 backend 跨运行复用时，每轮收尾都实际停发射。

    Returns:
        {'run_dir': 运行目录绝对路径, 'result': finalize_run 返回值, 'status': 'done'|'failed'}；
        正常完成返回 status='done'；execute 正常返回但回调已把状态机推至 failed 终态时，
        采纳回调终态返回 status='failed'（result.json 同步 failed）。其余失败路径在停发射+
        落盘完成后原异常重抛，不返回。

    Raises:
        RunDirError: 工作区创建失败（磁盘空间不足/父路径不可创建），退出码 1 语义，直接向上抛出。
        LifecycleError: 非法状态迁移（from-to 见异常属性）；execute 内触发时同样先收尾再透传。
        BaseException: execute 回调抛出的任何异常（含 KeyboardInterrupt/SystemExit）——
            先入 stopping、停发射、落 ERROR 日志、finalize_run(failed)，随后原样重抛；
            收尾段自身被 KI 等打断时先兜底落盘 result.json(failed) 再放行信号。
    """
    # ① 工作区：失败 → RunDirError 直接抛出（调用方以退出码 1 语义处理）
    workspace = create_run_workspace(runs_root, scenario)
    run_dir: str = workspace["run_dir"]
    # 运行级停发射幂等令牌：同一 backend 跨运行复用时，每轮收尾都实际停发射
    run_token = uuid4()

    ctx: dict = {
        "run_dir": run_dir,
        "scenario": scenario,
        "backend": backend,
        "started_at": time.time(),
        "open_files": [],
    }
    _state = {"current": "starting", "visited_running": False}

    def _transition(to_state: str) -> str:
        """执行一次迁移并落一行 INFO 日志；非法（跳级/终态再迁/未知状态名）→ LifecycleError。"""
        frm = _state["current"]
        if to_state not in _TRANSITIONS.get(frm, frozenset()):
            raise LifecycleError(frm, to_state)
        _state["current"] = to_state
        if to_state == "running":
            _state["visited_running"] = True
        append_run_log(
            run_dir,
            "INFO",
            f"状态迁移: {frm} -> {to_state}",
            {"event": "state_transition", "from": frm, "to": to_state},
        )
        return to_state

    def _log(level: str, message: str, context: dict | None = None) -> dict:
        """ctx['log']：回调经此向 run.log 追加结构化行（继承 append_run_log 静默降级契约）。"""
        return append_run_log(run_dir, level, message, context)

    def _enter_stopping(reason: str) -> None:
        """任何退出路径先入 stopping；回调已自行推至终态则仅告警跳过迁移（停发射照常执行）。"""
        if _state["current"] == "stopping":
            return
        if _state["current"] in _TERMINAL:
            append_run_log(
                run_dir,
                "WARN",
                f"回调已将状态机推至终态 {_state['current']}，跳过 stopping 迁移",
                {"event": "skip_stopping", "reason": reason, "state": _state["current"]},
            )
            return
        _transition("stopping")

    def _set_final(final_state: str) -> None:
        """推进到终态 done/failed；回调预先到达（不一致的）终态则告警并保留回调终态。"""
        if _state["current"] in _TERMINAL:
            if _state["current"] != final_state:
                append_run_log(
                    run_dir,
                    "WARN",
                    f"回调预先置终态 {_state['current']}，与收尾语义 {final_state} 不一致，保留回调终态",
                    {
                        "event": "final_state_conflict",
                        "callback_final": _state["current"],
                        "wind_down_final": final_state,
                    },
                )
            return
        _transition(final_state)

    def _bootstrap_after_interrupt() -> None:
        """wind_down 被打断时的兜底：再试 finalize_run 一次；仍失败则向 run.log 直写一行，尽力不抛。"""
        finalized = False
        try:
            result = finalize_run(
                {
                    "run_dir": run_dir,
                    "stop_result": ctx.get("stop_result"),
                    "open_files": ctx.get("open_files"),
                    "started_at": ctx.get("started_at"),
                    "backend": _backend_label(backend),
                },
                "failed",
            )
            finalized = isinstance(result, dict) and bool(result.get("finalized"))
        except BaseException:  # noqa: BLE001 - 兜底自身绝不抛
            finalized = False
        if finalized:
            return
        try:
            record = {
                "ts": time.time(),
                "level": "ERROR",
                "event": "wind_down_interrupted",
                "error": "收尾被打断且 finalize 兜底未落盘",
            }
            with open(os.path.join(run_dir, LOG_FILENAME), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                fh.flush()
        except BaseException:  # noqa: BLE001 - 直写兜底也失败只能吞掉
            pass

    def _wind_down(exit_semantics: str, error: BaseException | None) -> dict:
        """收尾公共段（整体兜底）：入 stopping → 先停发射（结果记入 ctx['stop_result']）→（异常补
        ERROR 行）→ 终态 → 重放降级缓冲滞留行 → finalize（仍有滞留则补正 log_degraded）。

        收尾自身被 KI 等 BaseException 打断时先兜底（再试 finalize 一次，仍失败则向
        run.log 直写一行），尽力把 result.json 落盘后再放行原信号。
        """
        try:
            return _wind_down_steps(exit_semantics, error)
        except BaseException:  # noqa: BLE001 - 收尾中信号也须先兜底落盘再透传
            _bootstrap_after_interrupt()
            raise

    def _wind_down_steps(exit_semantics: str, error: BaseException | None) -> dict:
        """收尾步骤主体（由 _wind_down 整体兜底包裹）。"""
        reason = "execute 回调异常" if error is not None else "正常完成"
        _enter_stopping(reason)
        # done 路径未经 running（回调从未申请发射态）：自动 WARN 留痕，提示疑似漏迁移
        if error is None and not _state["visited_running"]:
            append_run_log(
                run_dir,
                "WARN",
                "正常完成但从未进入 running 状态（未经发射即收尾）",
                {"event": "skipped_running_state"},
            )
        stop_context: dict = {"run_dir": run_dir, "reason": reason}
        if error is not None:
            stop_context["error"] = f"{type(error).__name__}: {error}"
        # 铁律：任何退出路径先停发射，结果落 ctx['stop_result'] 供 finalize 记入 result.json；
        # run_token 为运行级幂等令牌——同 backend 复用的下一轮运行收尾仍实际停发射
        ctx["stop_result"] = stop_transmit_safely(
            backend, context=stop_context, run_token=run_token
        )
        if error is not None:
            append_run_log(
                run_dir,
                "ERROR",
                f"execute 回调异常: {type(error).__name__}: {error}",
                {"event": "execute_error", "error_type": type(error).__name__},
            )
        _set_final("done" if exit_semantics == "done" else "failed")
        # 终态冲突采纳（单向）：execute 正常返回但回调已把状态机推至 failed 终态时，
        # 收尾语义采纳回调终态——result.json status 以状态机为准（WARN 已留痕）；
        # 反向不采纳：execute 异常时恒按 failed 收尾，回调自推 done 不改写失败事实
        if error is None and _state["current"] == "failed":
            exit_semantics = "failed"
        ctx["final_status"] = exit_semantics
        # 降级缓冲接入（运行级归属）：drain 取走并清空缓冲，只重放归属本运行的行进本
        # run.log；他运行滞留行原样归还（绝不写入他运行目录），重放失败立即归还。
        # 磁盘/目录恢复则落盘（链路未降级），仍有滞留则链路降级需在结果 JSON 标记
        stranded = _replay_buffered_log_lines(run_dir, drain_buffered_lines())
        if stranded:
            ctx["log_pending_lines"] = stranded
            append_run_log(  # 尽力向 run.log 留证（可能仍失败再进缓冲，接受）
                run_dir,
                "WARN",
                f"日志链路降级: {stranded} 行滞留内存缓冲未能落盘",
                {"event": "log_degraded", "stranded_lines": stranded},
            )
        finalize_ctx: dict = {
            "run_dir": run_dir,
            "stop_result": ctx.get("stop_result"),
            "open_files": ctx.get("open_files"),
            "started_at": ctx.get("started_at"),
            "backend": _backend_label(backend),
        }
        for optional in ("clock_ref", "alignment_error"):
            if optional in ctx:
                finalize_ctx[optional] = ctx[optional]
        result = finalize_run(finalize_ctx, exit_semantics)
        if stranded and isinstance(result, dict) and result.get("finalized"):
            # finalize_run 看不到降级缓冲（只认 run.log 缺失/封存失败），滞留信号在收尾后补正
            result["log_degraded"] = True
            _mark_result_log_degraded(run_dir, result)
        return result

    ctx["log"] = _log
    ctx["set_state"] = _transition
    append_run_log(
        run_dir,
        "INFO",
        "工作区就绪（八件套骨架已创建）",
        {"event": "workspace_ready", "files": workspace["files"]},
    )
    _transition("armed")

    # ③/④ 执行回调：任何异常（含 KeyboardInterrupt 等 BaseException）都先收尾再透传
    try:
        execute(ctx)
    except BaseException as exc:  # noqa: BLE001 - BaseException 也要先停发射再透传
        _wind_down("failed", exc)
        raise
    finalize_result = _wind_down("done", None)
    # 回调自推 failed 终态后正常返回时，status 采纳回调终态（'failed'）；正常恒为 'done'
    return {"run_dir": run_dir, "result": finalize_result, "status": ctx.get("final_status", "done")}
