"""功率阶梯执行：计划→逐档衰减下发+事件→失效即停→收尾停发射——重写规约与签名意图详见 fn_docs/responsibility.md。

编排职责（计划归 plan_ladder_steps、档位下发归 set_channel_attenuation、落盘归
append_event、停发射归 stop_transmit_safely，本函数只做编排）：
- 衰减口径：阶梯档位 target_db（干扰注入电平 dBm，≤0）按「衰减量=|target_db|」直接
  作为衰减请求交 set_channel_attenuation（−5dB 档→衰减 5dB、0dB 档→衰减 0dB），即
  干扰功率=后端满增益功率−衰减；组合择档/可达域/attenuation 事件语义全由
  set_channel_attenuation 承载（本函数不另发衰减指令、不另算组合）。
- 逐档次序：下发→power_step 事件（step/target_db/dwell_s+组合字段）→dwell
  （time.sleep(dwell_s)，0 合法可测）→failure_cb(该档记录的副本)。返回
  {'failed': True} 即先 stop_transmit_safely 再终止；返回形状错（非 dict 或缺
  'failed' 键）视为未失效并在该档执行记录记 warning；failure_cb 自身异常与
  下发/落盘异常同走「先停发射再透传」。
- 终止留痕：失效终止与走完全档收尾均在停发射之后追加 ladder_stop 事件（事件流
  末行见证 stop_tx 先于终止记录——安全动作先于终止语义落盘）；判据形状错 warning
  留痕于该档执行记录与 ladder_stop 事件（'judge_warning' 字段，B9低#4）；异常路径
  不补终止事件（落盘本身可能即失败源），仅停发射后原样透传。
- reason 口径：'failure'=判据触发（stopped_at=触发档索引）；'truncated'=计划被
  0dBm 红线截断（truncated_at 非 None，截断档未执行）；'max_steps'=max_steps 用尽
  且未触红线的完整步数（truncated_at None 且步数==max_steps，B9低#5）；
  'complete'=stop_db 命中的完整计划。
- 每轮停发射保真（B9中#1）：ctx 未提供 run_token（缺键或 None）时每次调用自生成
  uuid4().hex 写入 ctx 并贯通 set_channel_attenuation（经 ctx）/stop_transmit_safely
  （经参数）链路——同 backend 连续多轮阶梯各配独立 token，停发射按 (backend, token)
  运行级幂等，每轮收尾均实际停发射（缺省 None 会退化为进程级幂等，二轮
  already_stopped 即漏停）。
- 发射前拒绝（无需停发射）：dwell_s 为 bool/非实数/NaN/±inf/负 → ValueError；
  计划域错误（PlanError/ValueError）与 failure_cb 不可调用（TypeError）在发射前透传。
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable
from numbers import Real
from uuid import uuid4

from .plan_ladder_steps import _DEFAULT_MAX_STEPS, PlanError, plan_ladder_steps
from src.set_channel_attenuation.set_channel_attenuation import (
    AttenuationError,
    set_channel_attenuation,
)
from src.shared.append_event import EventWriteError, append_event
from src.shared.stop_transmit_safely import stop_transmit_safely

#: 错误契约随本函数透传不捕获，重导出供调用方就地导入。
__all__ = [
    "AttenuationError",
    "EventWriteError",
    "PlanError",
    "run_power_ladder",
]


def _dwell_seconds(dwell_s: float) -> float:
    """dwell_s 规整校验：拒 bool/非实数/NaN/±inf/负数，返回非负 float。"""
    if isinstance(dwell_s, bool) or not isinstance(dwell_s, Real):
        raise ValueError(f"dwell_s 必须为实数（bool/非数值一律拒绝）：{dwell_s!r}")
    dwell = float(dwell_s)
    if not math.isfinite(dwell):
        raise ValueError(f"dwell_s 必须为有限数（拒 NaN/±inf）：{dwell_s!r}")
    if dwell < 0.0:
        raise ValueError(f"dwell_s 不能为负（档间停留时长），实际: {dwell}")
    return dwell


def _consult_failure_cb(failure_cb: Callable | None, record: dict) -> dict:
    """征询失效判据：返回 {'failed', 'detail', 'warning'}（形状错→未失效+warning）。

    判据以该档记录的**副本**入参（判据侧改写不污染执行记录）；返回非 dict 或缺
    'failed' 键视为形状错——按未失效处理并在 warning 中如实记录原始返回值，
    不让半截判据静默当作"未失效"而无痕。
    """
    if failure_cb is None:
        return {"failed": False, "detail": None, "warning": None}
    verdict = failure_cb(dict(record))
    if not isinstance(verdict, dict) or "failed" not in verdict:
        return {
            "failed": False,
            "detail": None,
            "warning": (
                f"failure_cb 返回形状错（非 dict 或缺 'failed' 键），视为未失效: {verdict!r}"
            ),
        }
    return {"failed": bool(verdict["failed"]), "detail": verdict.get("detail"), "warning": None}


def run_power_ladder(
    ctx: dict,
    ladder_params: dict | None,
    failure_cb: Callable | None = None,
    dwell_s: float = 1.0,
    link_power_db: float = 0.0,
) -> dict:
    """执行功率阶梯：计划展开→逐档（下发+事件+dwell+判据）→失效即停/走完收尾停发射。

    :param ctx: 运行上下文（backend/run_dir/run_token/attenuator_cal 等，直传
        set_channel_attenuation；run_dir 亦为本函数事件落盘目录，缺省 None=纯执行不落事件；
        未提供 run_token（缺键或 None）时自生成 uuid4().hex 写入 ctx 并贯通下发/停发射
        链路——每轮独立 token 保证同 backend 连续多轮每轮实停，B9中#1）
    :param ladder_params: 梯度参数（start_db/step_db/stop_db/max_steps），None=GB 缺省口径
    :param failure_cb: 失效判据回调，逐档以该档记录 dict 征询，返回
        {'failed': bool, 'detail': …}；None=永不失效；形状错视为未失效记 warning
        （该档记录与 ladder_stop 事件 'judge_warning' 字段均留痕，B9低#4）
    :param dwell_s: 档间停留时长（秒），负/bool/非实数/NaN/±inf → ValueError（发射前拒绝）
    :param link_power_db: 被测链路发射功率（dBm），GB 缺省口径的阶梯基准
    :return: ``{'executed': [各档记录], 'stopped_at': 触发档索引|None,
        'reason': 'complete'|'failure'|'truncated'|'max_steps', 'plan': 计划,
        'stop_result': 停发射结果}``
    :raises PlanError/ValueError/TypeError: 发射前拒绝（计划域/停留时长/判据形态），透传不停发射
    :raises AttenuationError/EventWriteError/Exception: 档间任何异常（含后端方法与判据自身
        异常）——先 stop_transmit_safely 再原样透传
    """
    dwell = _dwell_seconds(dwell_s)
    if failure_cb is not None and not callable(failure_cb):
        raise TypeError(f"failure_cb 必须为可调用或 None，实际: {type(failure_cb).__name__}")

    # ① 计划：PlanError/ValueError 透传（尚未发射，无需停发射路径）
    plan = plan_ladder_steps(link_power_db, ladder_params)

    # ctx 形状容错取键：异常路径停发射需要 backend/run_token；ctx 非 dict 时取 None
    # （set_channel_attenuation 会对非 dict ctx 显式 ValueError，届时同样走停发射透传）
    ctx_fields = ctx if isinstance(ctx, dict) else {}
    backend = ctx_fields.get("backend")
    run_dir = ctx_fields.get("run_dir")
    # 每轮停发射保真（B9中#1）：未提供 token 时自生成并写入 ctx——同 backend 连续
    # 多轮各配独立 token，停发射按 (backend, token) 运行级幂等每轮实停；缺省 None
    # 会退化为进程级幂等，第二轮收尾 already_stopped 即漏停。
    run_token = ctx_fields.get("run_token")
    if run_token is None:
        run_token = uuid4().hex
        ctx_fields["run_token"] = run_token

    executed: list[dict] = []
    stopped_at: int | None = None
    failure_detail = None
    judge_warning: str | None = None

    # ② 逐档：下发→power_step 事件→dwell→判据；任何异常先停发射再透传
    try:
        for rung in plan["steps"]:
            combo = set_channel_attenuation(ctx, abs(rung["target_db"]))
            record: dict = {
                "step": rung["step"],
                "target_db": rung["target_db"],
                "dwell_s": dwell,
                **combo,
            }
            executed.append(record)
            if run_dir is not None:
                append_event(run_dir, {"type": "power_step", **record})
            time.sleep(dwell)
            verdict = _consult_failure_cb(failure_cb, record)
            if verdict["warning"] is not None:
                record["warning"] = verdict["warning"]
                judge_warning = verdict["warning"]  # 终止事件留痕（B9低#4）
            if verdict["failed"]:
                stopped_at = rung["step"]
                record["failed"] = True
                failure_detail = verdict["detail"]
                if failure_detail is not None:
                    record["failure_detail"] = failure_detail
                break
    except BaseException as exc:  # noqa: BLE001 - 先停发射再透传（含 KI/SystemExit 族）
        stop_transmit_safely(
            backend,
            context={
                "origin": "run_power_ladder",
                "reason": "error",
                "error": f"{type(exc).__name__}: {exc}",
            },
            run_token=run_token,
        )
        raise

    # ③ reason 判定：判据触发 > 红线截断 > max_steps 用尽 > stop_db 命中完整计划。
    # max_steps 细分（B9低#5）：truncated_at 为 None 但步数恰用尽 max_steps（未触
    # 红线也未命中 stop_db 提前收尾）——与 stop_db 命中的 complete 区分。
    if stopped_at is not None:
        reason = "failure"
    elif plan["truncated_at"] is not None:
        reason = "truncated"
    else:
        params = ladder_params if isinstance(ladder_params, dict) else {}
        max_steps = params.get("max_steps", _DEFAULT_MAX_STEPS)
        reason = "max_steps" if len(plan["steps"]) == max_steps else "complete"

    # ③/②失效 统一收尾：先停发射，终止语义其后落盘（末行见证停发射在先）
    stop_result = stop_transmit_safely(
        backend,
        context={"origin": "run_power_ladder", "reason": reason},
        run_token=run_token,
    )
    if run_dir is not None:
        stop_event: dict = {
            "type": "ladder_stop",
            "reason": reason,
            "stopped_at": stopped_at,
            "steps_executed": len(executed),
            "stop_status": stop_result["status"],
        }
        if failure_detail is not None:
            stop_event["failure_detail"] = failure_detail
        if judge_warning is not None:
            stop_event["judge_warning"] = judge_warning
        append_event(run_dir, stop_event)

    # ④ 返回
    return {
        "executed": executed,
        "stopped_at": stopped_at,
        "reason": reason,
        "plan": plan,
        "stop_result": stop_result,
    }
