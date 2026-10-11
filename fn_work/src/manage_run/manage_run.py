"""运行全生命周期：状态机+八件套工作区+先停发射收尾+结果 JSON——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import time
from typing import Any, Callable

from .append_run_log import append_run_log
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
            'log'(level, message, context)（run.log 追加封装，降级契约同 append_run_log）、
            'set_state'(to_state)（申请一次合法迁移，非法迁移抛 LifecycleError）。
        runs_root: 运行目录基础路径（默认 'runs'，不存在则自动创建）。
        backend: 发射后端实例，收尾时传给 stop_transmit_safely（可为 None）。

    Returns:
        {'run_dir': 运行目录绝对路径, 'result': finalize_run 返回值, 'status': 'done'|'failed'}；
        实际可达的返回 status 恒为 'done'——失败路径在停发射+落盘完成后原异常重抛，不返回。

    Raises:
        RunDirError: 工作区创建失败（磁盘空间不足/父路径不可创建），退出码 1 语义，直接向上抛出。
        LifecycleError: 非法状态迁移（from-to 见异常属性）；execute 内触发时同样先收尾再透传。
        BaseException: execute 回调抛出的任何异常（含 KeyboardInterrupt/SystemExit）——
            先入 stopping、停发射、落 ERROR 日志、finalize_run(failed)，随后原样重抛。
    """
    # ① 工作区：失败 → RunDirError 直接抛出（调用方以退出码 1 语义处理）
    workspace = create_run_workspace(runs_root, scenario)
    run_dir: str = workspace["run_dir"]

    ctx: dict = {
        "run_dir": run_dir,
        "scenario": scenario,
        "backend": backend,
        "started_at": time.time(),
        "open_files": [],
    }
    _state = {"current": "starting"}

    def _transition(to_state: str) -> str:
        """执行一次迁移并落一行 INFO 日志；非法（跳级/终态再迁/未知状态名）→ LifecycleError。"""
        frm = _state["current"]
        if to_state not in _TRANSITIONS.get(frm, frozenset()):
            raise LifecycleError(frm, to_state)
        _state["current"] = to_state
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

    def _wind_down(exit_semantics: str, error: BaseException | None) -> dict:
        """收尾公共段：入 stopping → 先停发射（结果记入 ctx['stop_result']）→（异常补 ERROR 行）→ 终态 → finalize。"""
        reason = "execute 回调异常" if error is not None else "正常完成"
        _enter_stopping(reason)
        stop_context: dict = {"run_dir": run_dir, "reason": reason}
        if error is not None:
            stop_context["error"] = f"{type(error).__name__}: {error}"
        # 铁律：任何退出路径先停发射，结果落 ctx['stop_result'] 供 finalize 记入 result.json
        ctx["stop_result"] = stop_transmit_safely(backend, context=stop_context)
        if error is not None:
            append_run_log(
                run_dir,
                "ERROR",
                f"execute 回调异常: {type(error).__name__}: {error}",
                {"event": "execute_error", "error_type": type(error).__name__},
            )
        _set_final("done" if exit_semantics == "done" else "failed")
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
        return finalize_run(finalize_ctx, exit_semantics)

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
    return {"run_dir": run_dir, "result": finalize_result, "status": "done"}
