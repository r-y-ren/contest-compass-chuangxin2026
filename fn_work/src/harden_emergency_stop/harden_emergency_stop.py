"""急停硬化序列：先 trigger_emergency_stop（先停发射+事件留痕）再置 stop_flag；停发射失败仍保证标志置位——重写规约与签名意图详见 fn_docs/responsibility.md。

口径（R59）：
- 序不可倒置：① 先调 trigger_emergency_stop(run_ctx, origin=source)——其内部先
  stop_transmit_safely 停发射（backend/run_token 从 run_ctx 直传；console 上下文
  拿不到 backend 时 None→no_backend 幂等口径，不视为失败）并记录急停事件序，再置
  run_ctx['stop']['flag']=True（场景侧停旗）；② 本函数随后才置 stop_flag['flag']
  =True（编排侧终止旗）。发射侧静默先于编排旗标——执行循环不会在发射未静默时就
  进入收尾分支；
- 绝不抛出：trigger_emergency_stop 自身全程不抛，本函数再兜容器腐化（run_ctx/
  stop_flag 非 dict 或赋值被拒）与结果组装异常（BaseException 族全捕获）——急停
  路径不能被异常打断成「半停」且无记录；
- 停发射失败→不豁免编排终止：stop_flag 仍保证置位，结果 status='stop_failed' 且
  error 记录失败原因（发射侧步级明细在 'transmit' 内）；
- 事件落点：急停结果尽力写 run_ctx['emergency_stop']（与 push_realtime_kpi 的
  hub['emergency_stop'] 同口径；容器不可写则跳过）——操控台侧观测口，调用方
  （create_console_app 停止路由）另把结果并入 HTTP 响应供页面按钮状态消费。
"""
from datetime import datetime, timezone

from src.push_realtime_kpi.trigger_emergency_stop import trigger_emergency_stop

__all__ = ["harden_emergency_stop"]


def _flag_snapshot(stop_flag: object) -> bool:
    """读取编排旗当前状态（容器腐化→False，不抛）。"""
    try:
        return stop_flag.get("flag") is True  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 - 腐化容器按「未置位」上报
        return False


def harden_emergency_stop(source: str, run_ctx: dict, stop_flag: dict) -> dict:
    """急停硬化序列：先 trigger_emergency_stop（先停发射+事件留痕）再置 stop_flag；停发射失败仍保证标志置位（详见 fn_docs/responsibility.md 功能块）。

    Args:
        source: 急停来源标识（'console' 页面按钮 / 'api' 直接调用等）——原样入
            结果 'source' 并作为 trigger_emergency_stop 的 origin 进急停事件序。
        run_ctx: 运行上下文 dict（console 侧由 create_console_app 组装/注入，
            形状登记）：'backend'——发射后端句柄（可选；console 上下文拿不到时
            缺省 None，trigger_emergency_stop→stop_transmit_safely 幂等口径兜底，
            None 后端返回 no_backend 不视为失败）；'run_token'——运行级幂等令牌
            （可选；同 (backend, token) 重复急停→already_stopped）；'runs'——
            活跃运行信息容器（可选，操控台 app.state.runs——观测用，本函数不
            消费）。trigger_emergency_stop 另写 run_ctx['stop']['flag']=True
            （场景侧停旗）；本函数把急停结果尽力写 run_ctx['emergency_stop']
            （事件落点；容器不可写则跳过）。
        stop_flag: 编排侧终止旗共享 dict（console 的 deps['stop_flag']）——本
            函数置其 'flag'=True 终止编排；容器腐化时置位失败记入结果不抛出。

    Returns:
        {'source': 来源标识, 'status': 'stopped'|'stop_failed'（顶层——发射侧
        failed、急停路径异常或旗置位失败均 'stop_failed'）, 'stopped_at': UTC
        ISO（急停时刻，trigger 产出缺省本地补）, 'transmit': stop_transmit_safely
        结果（停发射状态/steps，经 trigger 的 'stop_result'）, 'events': 急停
        事件序（trigger 产出：requested→transmit_stopped→stop_flag_set[→
        stop_failed]——事件引用）, 'stop_flag_set': bool（编排旗是否已置 True）,
        'error': 失败原因（无失败为 None；多条以 '; ' 连接）}。

    Raises:
        绝不抛出（BaseException 全兜底——安全路径不允许被异常打断）。
    """
    stopped_at = datetime.now(timezone.utc).isoformat()
    errors: list = []

    # ① 发射侧+场景侧急停（trigger 内部：先 stop_transmit_safely 停发射并记录
    #    急停事件，再置 run_ctx['stop']['flag']——序不可倒置的保证点）。trigger
    #    自身不抛；此层再兜一切意外异常（兜底后编排旗照置，绝不半停无记录）。
    trigger_result: "dict | None" = None
    try:
        trigger_result = trigger_emergency_stop(run_ctx, origin=source)
    except BaseException as exc:  # noqa: BLE001 - 急停路径绝不上抛
        errors.append(f"trigger_emergency_stop 异常: {type(exc).__name__}: {exc}")

    # ② 编排侧终止旗——无条件尝试置位（① 失败/异常均不豁免编排终止）。
    try:
        stop_flag["flag"] = True
    except BaseException as exc:  # noqa: BLE001 - 旗容器腐化→记原因不抛
        errors.append(f"stop_flag 置位失败: {type(exc).__name__}: {exc}")

    # ---- 结果组装（trigger 顶层状态联动+失败原因提取）----
    transmit = trigger_result.get("stop_result") if isinstance(trigger_result, dict) else None
    events = trigger_result.get("events") if isinstance(trigger_result, dict) else []
    if not isinstance(events, list):
        events = []
    stopped_at = (
        trigger_result.get("stopped_at", stopped_at)
        if isinstance(trigger_result, dict)
        else stopped_at
    )
    status = "stopped"
    if trigger_result is None:
        status = "stop_failed"  # ① 异常（errors 已记）
    elif trigger_result.get("status") == "stop_failed":
        # 发射侧 failed 或急停路径异常（含 run_ctx 腐化）——原因优先取事件序内
        # stop_failed.reason，取不到则指向 transmit 步级明细。
        status = "stop_failed"
        reason = None
        for ev in reversed(events):
            if isinstance(ev, dict) and ev.get("event") == "stop_failed":
                reason = ev.get("reason")
                break
        errors.append(f"停发射失败: {reason or '发射侧 failed（步级明细见 transmit）'}")
    if errors:
        status = "stop_failed"  # 旗置位失败等叠加错误同样顶层可读

    result = {
        "source": source,
        "status": status,
        "stopped_at": stopped_at,
        "transmit": transmit,
        "events": events,
        "stop_flag_set": _flag_snapshot(stop_flag),
        "error": "; ".join(errors) if errors else None,
    }

    # ---- 事件落点：急停结果尽力写 run_ctx（容器不可写则跳过，绝不反杀安全路径）。
    try:
        if isinstance(run_ctx, dict):
            run_ctx["emergency_stop"] = result
    except BaseException:  # noqa: BLE001 - 观测落点失败不影响急停结果
        pass
    return result
