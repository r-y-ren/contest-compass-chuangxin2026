"""安全停发射唯一出口：幂等静默+事件记录，安全路径不抛出——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import weakref
from datetime import datetime, timezone

# 已成功静默的 (backend, run_token) 登记：正常对象走弱引用键表（不延长生命周期）；
# 不可弱引用/不可哈希的异类对象退回强持有列表（防 id 复用造成误判 already_stopped）。
# 登记键含 run_token（运行级幂等）：同一 backend 跨运行各配独立 token，
# 第二轮运行收尾仍实际停发射；token 缺省（None）维持进程级幂等的向后兼容语义。
_stopped_tokens: "weakref.WeakKeyDictionary[object, set]" = weakref.WeakKeyDictionary()
_stopped_hard: "list[tuple[object, object]]" = []


def _is_stopped(backend: object, run_token: object) -> bool:
    """该 (backend, run_token) 组合是否已被成功静默过（幂等判定）。

    回退列表须先查：WeakKeyDictionary 对不可弱引用对象查询抛 TypeError，
    不能依赖弱键表异常分支以外的路径来命中回退登记。
    """
    if any(obj is backend and tok == run_token for obj, tok in _stopped_hard):
        return True
    try:
        return run_token in _stopped_tokens.get(backend, frozenset())
    except TypeError:  # 不可弱引用/不可哈希等异类：弱键表两处操作均不可能
        return False


def _remember_stopped(backend: object, run_token: object) -> None:
    """登记成功静默的 (backend, run_token)，供同 token 下次调用直接 already_stopped。"""
    try:
        _stopped_tokens.setdefault(backend, set()).add(run_token)
    except TypeError:
        _stopped_hard.append((backend, run_token))


def stop_transmit_safely(
    backend=None, context: dict | None = None, run_token: object = None
) -> dict:
    """安全停发射唯一出口：幂等静默+事件记录，安全路径不抛出。

    对 backend（鸭子类型，可缺 stop_tx/set_tx_gain 任意方法，可为 None）依次执行
    stop_tx() 与 set_tx_gain(0)；单步失败仅记录原因不打断后续步骤——包括
    KeyboardInterrupt/SystemExit 等 BaseException 族（安全路径完整优先于信号透传：
    记录该步失败后继续执行剩余停发射步，最终返回 failed，不穿透）；永不抛出。
    幂等按 (backend, run_token) 运行级登记：同一 (backend, token) 成功静默后再次调用
    返回 already_stopped；换 token（新一轮运行）则重新全流程执行。失败不登记、下次重试。
    run_token 缺省 None 时维持进程级幂等（同一 backend 二次调用 already_stopped），向后兼容。
    """
    ts = datetime.now(timezone.utc).isoformat()

    if backend is None:
        return {"status": "no_backend", "steps": [], "ts": ts, "context": context}

    if _is_stopped(backend, run_token):
        return {"status": "already_stopped", "steps": [], "ts": ts, "context": context}

    steps: list[dict] = []

    def _attempt(op: str, attr: str, *args: object, ok_detail: str = "ok") -> None:
        # 探测+调用一体：属性探测或调用抛出的一切异常（含 KI/SystemExit）均记为该步
        # 失败，绝不让异常打断安全路径；方法缺失（或为 None）则跳过该步。
        try:
            method = getattr(backend, attr, None)
        except BaseException as exc:  # noqa: BLE001 - 安全路径须捕获一切异常
            steps.append({"op": op, "ok": False, "detail": f"probe {attr}: {type(exc).__name__}: {exc}"})
            return
        if method is None:
            return
        try:
            method(*args)
        except BaseException as exc:  # noqa: BLE001 - 安全路径须捕获一切异常（含信号族）
            steps.append({"op": op, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
            return
        steps.append({"op": op, "ok": True, "detail": ok_detail})

    _attempt("stop_tx", "stop_tx")
    _attempt("set_tx_gain", "set_tx_gain", 0, ok_detail="tx_gain=0")

    all_ok = all(step["ok"] for step in steps)
    if all_ok:
        _remember_stopped(backend, run_token)

    return {
        "status": "stopped" if all_ok else "failed",
        "steps": steps,
        "ts": ts,
        "context": context,
    }
