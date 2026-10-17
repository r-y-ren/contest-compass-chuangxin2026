"""目标衰减→粗档(30dB 两态)×软件增益细档组合下发+事件——重写规约与签名意图详见 fn_docs/responsibility.md。

编排职责（纯计算归 plan_attenuator_combo，落盘归 append_event，本函数只做编排）：
- 档位标定口径：cal_table 由调用方直传（细档标称→实际衰减），缺省取 ctx['attenuator_cal']；
  本函数不读文件标定表——gain 表口径是档位→功率、link_loss 表口径是频点→dB，均不适用
  档位级衰减标定（load_calibration_table 由上游构建后经 ctx/参数注入）。
- 下发：backend 鸭子四形态互斥择一（R95）——①有 set_attenuation（程控衰减器后端）
  → set_attenuation(achieved_db) 全量实达值、applied=True、applied_via=
  'set_attenuation'（仪器形态语义不变：粗+细全量由仪器承载）；②有 set_tx_gain+
  get_tx_gain（B210 形态）→ 正增益映射：粗档 30dB 两态折进增益预算（不再由操作面
  手调——"手调两态由操作面执行"旧句至此失真废除），target=resolve_base_tx_gain()
  −achieved_db（基准 60−粗档预算−细档；resolve_base_tx_gain 越界 ValueError 透传）；
  target≥0 → set_tx_gain(target)、applied=True、applied_via='tx_gain'；target<0 →
  增益地板：set_tx_gain(0)、applied='partial'+applied_detail='gain_floor'，实际衰减
  =基准（achieved_db=基准、residual_db=target_db−基准、fine_actual_db=基准−粗档，
  实达组合如实改写，事件与返回不虚报）；③仅有 set_tx_gain 无 get_tx_gain（SimBackend
  名义模型，有意保留）→ 旧相对增量路径 set_tx_gain(−fine_step_db)、applied=
  'unknown_gain'（sim 零改变=演进轮⑤范围外硬约束，逐字节保留）；④backend 缺或
  两方法皆缺→'applied': False+'reason': 'no_backend'。后端方法自身异常不捕获，
  原样透传（操作面失败由调用方处置）。
- 事件：ctx['run_dir'] 存在（非 None）时 append_event(run_dir, {'type': 'attenuation',
  'target_db', **combo, 'applied'}，未下发附 reason)；run_dir 缺省 None→纯计算模式跳过
  事件。事件是测量真值：append_event 失败（EventWriteError）透传，由调用方走停发射路径。
- 不可达（plan 返回 None，含 +inf target）→AttenuationError（本文件定义）附可达域
  [0, 粗档顶值+细档实际顶值]；target/domain/cal_table 形状错→ValueError 透传（plan 抛出）。
"""
from __future__ import annotations

from .plan_attenuator_combo import (
    _DEFAULT_COARSE_DB,
    _DEFAULT_FINE_STEPS_DB,
    plan_attenuator_combo,
)
from src.shared.append_event import EventWriteError, append_event
from src.shared.resolve_base_tx_gain import resolve_base_tx_gain

#: EventWriteError 随错误契约一并重导出（本函数透传不捕获，调用方可就地导入）。
__all__ = ["AttenuationError", "EventWriteError", "set_channel_attenuation"]


class AttenuationError(RuntimeError):
    """目标衰减超出档位可达域（粗档顶值+细档实际顶值之外），附可达域结构化信息。"""

    def __init__(
        self,
        message: str,
        *,
        reachable_max_db: float,
        coarse_top_db: float,
        fine_top_db: float,
        reachable_min_db: float = 0.0,
    ) -> None:
        super().__init__(message)
        self.reachable_min_db = reachable_min_db
        self.reachable_max_db = reachable_max_db
        self.coarse_top_db = coarse_top_db
        self.fine_top_db = fine_top_db


def _reachable_top(domain: dict | None, cal_table: dict | None) -> tuple[float, float, float]:
    """复算 (粗档顶值, 细档实际顶值, 可达域顶值=粗+细顶)。

    仅在 plan_attenuator_combo 判不可达后调用：此时 domain/cal_table 形状已过 plan 校验，
    按 plan 同一口径合并缺省（缺键用默认、细档缺标定键按标称值）复算，不再抛出。
    """
    if domain is None:
        coarse_db = _DEFAULT_COARSE_DB
        fine_steps = list(_DEFAULT_FINE_STEPS_DB)
    else:
        coarse_db = float(domain.get("coarse_db", _DEFAULT_COARSE_DB))
        fine_steps = [float(step) for step in domain.get("fine_steps_db", _DEFAULT_FINE_STEPS_DB)]
    cal = cal_table if cal_table is not None else {}
    fine_top = max((float(cal.get(step, step)) for step in fine_steps), default=0.0)
    return coarse_db, fine_top, coarse_db + fine_top


def _dispatch_backend(
    backend: object, combo: dict, target_db: float
) -> tuple[dict, bool | str, str | None, str | None, str | None]:
    """鸭子下发四形态互斥择一：①set_attenuation 全量；②B210 正增益映射；③sim 旧路径；④no_backend。

    返回 (实达组合, applied, applied_via, applied_detail, reason)：backend 缺或两方法
    皆缺/不可调用→(combo, False, None, None, 'no_backend')。形态互斥择一
    （set_attenuation 已承载全量实达值，再调 set_tx_gain 会重复计细档）；后端方法
    自身异常不捕获原样透传，resolve_base_tx_gain 的 ValueError 同样透传。

    形态②（set_tx_gain+get_tx_gain 双在，B210，R95）：正增益映射——粗档折进增益
    预算，target=resolve_base_tx_gain()−achieved_db（基准−粗档预算−细档）；get_tx_gain
    在场兼作形态判据（R96 鸭子特征名），绝对映射无需先读当前增益。target≥0 →
    set_tx_gain(target)、applied=True、applied_via='tx_gain'；target<0 → 增益地板：
    set_tx_gain(0)、applied='partial'+applied_detail='gain_floor'，实际衰减=基准
    （achieved_db=基准、residual_db=target_db−基准、fine_actual_db=基准−粗档，
    实达组合如实改写，事件与返回不虚报）。

    形态③（仅有 set_tx_gain 无 get_tx_gain，SimBackend）：旧相对增量路径逐字节保留
    ——set_tx_gain(−fine_step_db)、applied='unknown_gain'、applied_via='set_tx_gain'
    （有意保留=名义模型口径非缺陷，演进轮⑤登记防误判）。
    """
    if backend is not None:
        set_attenuation = getattr(backend, "set_attenuation", None)
        if callable(set_attenuation):
            set_attenuation(float(combo["achieved_db"]))
            return combo, True, "set_attenuation", None, None
        set_tx_gain = getattr(backend, "set_tx_gain", None)
        if callable(set_tx_gain):
            get_tx_gain = getattr(backend, "get_tx_gain", None)
            if not callable(get_tx_gain):
                # 无增益可读：地板是否夹 0 无法判定——下发照做，applied 如实标不确定
                set_tx_gain(-float(combo["fine_step_db"]))
                return combo, "unknown_gain", "set_tx_gain", None, None
            # 形态②（B210）：正增益映射——粗档折进增益预算，下发绝对增益=基准−实达衰减
            base_db = resolve_base_tx_gain()  # 基准 60−粗档预算−细档；ValueError 透传
            target_gain_db = base_db - float(combo["achieved_db"])
            if target_gain_db < 0.0:
                # 增益地板：请求实达 > 基准 → 增益 0 封底，实际衰减=基准（组合如实改写）
                set_tx_gain(0)
                floored = dict(combo)
                floored["fine_actual_db"] = base_db - float(combo["coarse_db"])
                floored["achieved_db"] = base_db
                floored["residual_db"] = float(target_db) - base_db
                return floored, "partial", "tx_gain", "gain_floor", None
            set_tx_gain(target_gain_db)
            return combo, True, "tx_gain", None, None
    return combo, False, None, None, "no_backend"


def set_channel_attenuation(
    ctx: dict,
    target_db: float,
    domain: dict | None = None,
    cal_table: dict | None = None,
) -> dict:
    """目标衰减→（粗档二态×软件增益细档）组合下发+事件；超可达域→AttenuationError。

    ctx 可含 backend/run_dir/attenuator_cal；domain/cal_table 直传（优先于 ctx）。
    返回 combo（coarse/coarse_db/fine_step_db/fine_actual_db/achieved_db/residual_db/
    fine_from）+ applied（+applied_via 或 reason）；tx_gain 下发路径 applied 另有
    'partial'（附 applied_detail='gain_floor'——B210 形态请求实达超基准，实际衰减
    =基准，实达组合如实改写）与 'unknown_gain'（sim 形态无 get_tx_gain 无法判定
    地板，旧路径有意保留）两态。
    """
    if not isinstance(ctx, dict):
        raise ValueError(f"ctx 必须为 dict，实际: {type(ctx).__name__}")

    # ① 档位计算：cal_table 直传优先，缺省取 ctx['attenuator_cal']（不读文件标定表）
    effective_cal = cal_table if cal_table is not None else ctx.get("attenuator_cal")
    combo = plan_attenuator_combo(target_db, domain=domain, cal_table=effective_cal)
    if combo is None:  # ④ 不可达（含 +inf target）：拒绝并附可达域
        coarse_top, fine_top, reachable_max = _reachable_top(domain, effective_cal)
        raise AttenuationError(
            f"目标衰减 {float(target_db)} dB 超出可达域 [0, {reachable_max}] dB"
            f"（粗档顶值 {coarse_top} dB + 细档顶值 {fine_top} dB）",
            reachable_max_db=reachable_max,
            coarse_top_db=coarse_top,
            fine_top_db=fine_top,
        )

    # ② 下发：鸭子四形态互斥择一，缺则 applied=False/reason='no_backend'（方法异常与
    #    resolve_base_tx_gain 的 ValueError 透传）；B210 正增益映射/增益地板、sim 旧
    #    路径增益不可读如实标注（R95/B9中#3）
    dispatched, applied, applied_via, applied_detail, reason = _dispatch_backend(
        ctx.get("backend"), combo, float(target_db)
    )

    # ③ 事件：run_dir 缺省 None→纯计算模式跳过；写失败 EventWriteError 透传（测量真值）
    run_dir = ctx.get("run_dir")
    if run_dir is not None:
        event: dict = {
            "type": "attenuation",
            "target_db": float(target_db),
            **dispatched,
            "applied": applied,
        }
        if applied_detail is not None:
            event["applied_detail"] = applied_detail
        if reason is not None:
            event["reason"] = reason
        append_event(run_dir, event)

    # ⑤ 返回 实达组合+applied（成功附 applied_via、地板附 applied_detail、未下发附 reason）
    result = dict(dispatched)
    result["applied"] = applied
    if applied_via is not None:
        result["applied_via"] = applied_via
    if applied_detail is not None:
        result["applied_detail"] = applied_detail
    if reason is not None:
        result["reason"] = reason
    return result
