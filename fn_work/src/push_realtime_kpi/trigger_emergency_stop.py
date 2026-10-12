"""急停路径：直调停发射→停场景→广播→记录——重写规约与签名意图详见 fn_docs/responsibility.md。

安全路径设计（R49：急停本地直达，不经任何队列）：
- 序不可换：先 stop_transmit_safely（backend/run_token 从 ctx 直传，发射侧唯一
  出口）→再置 ctx['stop']['flag']=True（停场景执行）——场景侧旗标绝不能先于
  发射侧静默（否则执行循环可能在发射未静默时进入收尾分支）；
- 绝不上抛：全程 BaseException 捕获（含 KeyboardInterrupt/SystemExit 族），
  失败只以 status='stop_failed'+events 记录原因返回——急停路径本身不能被
  异常打断成「半停」且无记录；
- stop 子 dict 缺失→就地创建（setdefault）；已存在但为垃圾类型（不可按
  dict 赋值）→该步记 stop_failed 原因（不静默替换，腐化要留痕）。
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.shared.stop_transmit_safely import stop_transmit_safely

__all__ = ["trigger_emergency_stop"]


def trigger_emergency_stop(ctx: dict, origin: str) -> dict:
    """急停路径：直调停发射→置场景停旗→记录事件序（安全路径不抛出）。

    Args:
        ctx: 运行上下文——消费 'backend'（发射后端，可 None）、'run_token'
            （运行级幂等令牌）；写入 'stop' 子 dict 的 'flag'=True（缺则创建）。
        origin: 急停来源标识（如 'ui-button'/'watchdog'），原样入结果与事件。

    Returns:
        {'stopped_at': UTC ISO, 'origin', 'stop_result': stop_transmit_safely
        返回值（发射侧结果，含 status），'events': 有序事件列表
        [requested→transmit_stopped→stop_flag_set（失败时追加 stop_failed）],
        'status': 'stopped'|'stop_failed'}。
    """
    stopped_at = datetime.now(timezone.utc).isoformat()
    events: list[dict] = [{"event": "emergency_stop_requested", "origin": origin, "ts": stopped_at}]
    stop_result: dict | None = None
    status = "stopped"
    try:
        # ① 发射侧先行（不经队列直调；backend/run_token 语义由 ctx 直传）。
        backend = ctx.get("backend") if isinstance(ctx, dict) else None
        run_token = ctx.get("run_token") if isinstance(ctx, dict) else None
        stop_result = stop_transmit_safely(
            backend=backend, context={"origin": origin}, run_token=run_token
        )
        events.append(
            {"event": "transmit_stopped", "result_status": stop_result.get("status")}
        )

        # ② 场景侧停旗（缺 stop 子 dict→建；垃圾类型→赋值炸→记 stop_failed）。
        stop_box = ctx.setdefault("stop", {}) if isinstance(ctx, dict) else None
        if stop_box is None:
            raise TypeError(f"ctx 不可按下标写入（{type(ctx).__name__}），无法置停旗")
        stop_box["flag"] = True
        events.append({"event": "stop_flag_set", "stop": {"flag": True}})
    except BaseException as exc:  # noqa: BLE001 - 急停安全路径绝不上抛（含信号族）
        status = "stop_failed"
        events.append(
            {"event": "stop_failed", "reason": f"{type(exc).__name__}: {exc}"}
        )
    return {
        "stopped_at": stopped_at,
        "origin": origin,
        "stop_result": stop_result,
        "events": events,
        "status": status,
    }
