"""实时流枢纽：source 帧逐条→hub 广播（<500ms 判据/积压降频）——重写规约与签名意图详见 fn_docs/responsibility.md。

口径（R49）：
- source 迭代出的帧 dict 逐条 send_json 到 hub['sockets']；发送异常→该 socket
  即时移除并计入 n_disconnected（断连计数）；广播异常率>50%（严格大于）→
  degraded=True 且在 hub['degraded'] 落降频标志（生产侧据此降频+标注）；
- 帧缺 'sent_ms'→盖当前毫秒墙钟戳（已有则保留事件原戳，端到端口径不低估）；
- {'type': 'emergency_stop'} 控制帧不走广播——直调 trigger_emergency_stop
  （急停本地直达，不经任何队列；ctx 取帧内 'ctx'→hub['ctx']→hub 逐级兜底），
  结果记 hub['emergency_stop']，并向在线端点广播急停通知帧；
- hub['history'] 环形保最近 100 条（deque(maxlen) 自动；list/无界 deque 手动
  截尾，尾部保新）；无订阅者→帧照常消费计数，不报错；
- 收尾 drain hub['acks']（回执戳流）喂 measure_refresh_latency 入 'latency'；
  source 异常同样先 drain（acks 清空、降频标志落 hub、history 留痕）再透传原异常。
"""
from __future__ import annotations

import asyncio
import inspect
import time
from collections import deque

from .measure_refresh_latency import measure_refresh_latency
from .trigger_emergency_stop import trigger_emergency_stop

__all__ = ["DEGRADE_FAIL_RATE", "HISTORY_MAX", "push_realtime_kpi"]

#: hub['history'] 环形上限（保最近 N 条，不无界增长）。
HISTORY_MAX = 100

#: 积压降频判据：广播异常率严格大于该值（50%）才降频——恰好一半不触发。
DEGRADE_FAIL_RATE = 0.5


def _now_ms() -> float:
    """当前墙钟毫秒戳（与回执 acked_ms 同源时钟，延迟差方可为正）。"""
    return round(time.time() * 1000.0, 3)


def _drop_socket(sockets: object, sock: object) -> None:
    """从 sockets 容器（set|list 鸭子类型）移除失效连接，形态差异各自兜底。"""
    discard = getattr(sockets, "discard", None)
    if callable(discard):
        discard(sock)
        return
    try:
        sockets.remove(sock)
    except (ValueError, KeyError, AttributeError):
        pass


def _send_json(sock: object, frame: dict) -> bool:
    """单连接 send_json：成功 True；任何异常 False（调用方移除+计数）。

    异步 send（starlette WS 的 send_json 返回协程）以 asyncio.run 驱动——本函数
    为同步枢纽契约；在运行中事件循环线程内调用属集成层职责，不在本层兜底。
    """
    try:
        result = sock.send_json(frame)
        if inspect.isawaitable(result):
            asyncio.run(result)
        return True
    except Exception:  # noqa: BLE001 - 掉线/坏帧属广播常态，移除由调用方处理
        return False


def _append_history(history: object, frame: dict) -> None:
    """history 追加一条并维持环形上限（deque(maxlen) 自动，list/无界 deque 截尾）。"""
    append = getattr(history, "append", None)
    if not callable(append):
        return
    append(frame)
    if isinstance(history, deque) and history.maxlen:
        return  # 有界 deque 追加即环形
    while len(history) > HISTORY_MAX:
        if isinstance(history, deque):
            history.popleft()
        elif isinstance(history, list):
            del history[0]
        else:
            break


def _drain(acks: object) -> list:
    """排空回执容器（保到达序），返回回执列表；容器形态鸭子类型兜底。"""
    items: list = []
    while True:
        try:
            if isinstance(acks, deque):
                items.append(acks.popleft())
            elif isinstance(acks, list):
                items.append(acks.pop(0))
            else:
                popleft = getattr(acks, "popleft", None)
                if not callable(popleft):
                    break
                items.append(popleft())
        except (IndexError, KeyError):
            break
    return items


def push_realtime_kpi(source, hub) -> dict:
    """实时流枢纽：source 帧流→hub 广播+回执延迟统计+积压降频。

    Args:
        source: 帧 dict 可迭代流（KPI 样本/帧；{'type': 'emergency_stop'} 为急停
            控制帧，本地直达急停路径，不进广播队列）。
        hub: 实时流枢纽 dict——'sockets'（set|list）、'history'（环形 100 条，
            缺省自动建）、'acks'（回执戳流 [{'sent_ms','acked_ms'}]，收尾排空）、
            可选 'ctx'（急停运行上下文兜底）。降频标志落 hub['degraded']。

    Returns:
        {'n_pushed': 消费广播帧数, 'n_disconnected': 断连移除计数,
        'latency': measure_refresh_latency 结果（hub['acks'] 回执戳流）,
        'degraded': 广播异常率>50% 标志}。

    Raises:
        ValueError: hub 非 dict。
        source 迭代异常透传（透传前先 drain hub：acks 清空、降频标志落 hub）。
    """
    if not isinstance(hub, dict):
        raise ValueError(
            f"hub 必须为 dict（sockets/history/acks），实际 {type(hub).__name__}: {hub!r}"
        )
    hub.setdefault("sockets", set())
    history = hub.setdefault("history", deque(maxlen=HISTORY_MAX))
    acks = hub.setdefault("acks", deque())

    n_pushed = 0
    n_disconnected = 0
    n_attempts = 0
    n_failures = 0
    failure: "BaseException | None" = None
    drained_acks: list = []

    try:
        for raw in source:
            if not isinstance(raw, dict):
                continue  # 形状坏条目丢弃（流不因单条中断）
            if raw.get("type") == "emergency_stop":
                # 急停本地直达（不经广播队列）：直调急停路径→结果记 hub→通知帧外发。
                stop_ctx = raw.get("ctx")
                if not isinstance(stop_ctx, dict):
                    stop_ctx = hub.get("ctx") if isinstance(hub.get("ctx"), dict) else hub
                stop_result = trigger_emergency_stop(
                    stop_ctx, origin=str(raw.get("origin", "realtime-stream"))
                )
                hub["emergency_stop"] = stop_result
                frame = {
                    "type": "emergency_stopped",
                    "origin": stop_result.get("origin"),
                    "status": stop_result.get("status"),
                    "stopped_at": stop_result.get("stopped_at"),
                }
            else:
                frame = raw
            if "sent_ms" not in frame:
                frame["sent_ms"] = _now_ms()

            for sock in list(hub["sockets"]):
                n_attempts += 1
                if _send_json(sock, frame):
                    continue
                n_failures += 1
                n_disconnected += 1
                _drop_socket(hub["sockets"], sock)
            n_pushed += 1
            _append_history(history, frame)
    except BaseException as exc:  # noqa: BLE001 - 先 drain hub 再透传（绝不吞）
        failure = exc
    finally:
        # 收尾 drain（正常与异常路径同口径）：acks 排空、降频标志落 hub。
        drained_acks = _drain(acks)
        degraded = n_attempts > 0 and (n_failures / n_attempts) > DEGRADE_FAIL_RATE
        if degraded:
            hub["degraded"] = True

    if failure is not None:
        raise failure

    return {
        "n_pushed": n_pushed,
        "n_disconnected": n_disconnected,
        "latency": measure_refresh_latency(drained_acks),
        "degraded": degraded,
    }
