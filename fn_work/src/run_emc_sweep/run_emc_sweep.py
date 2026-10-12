"""EMC 步进扫频编排（R35）：plan_frequency_sweep 点表→逐点模拟读数→杂散标记→敏感度口径——重写规约与签名意图详见 fn_docs/responsibility.md。

编排职责（点表归 plan_frequency_sweep、CISPR 式读数归 SimEmiReceiver、声明文案归
make_disclaimer_block、本函数只做编排）：

- 扫描计划：scenario 的 start_hz/stop_hz/step_hz/scale/band **全透传**
  plan_frequency_sweep（缺省键由计划函数补：step 缺省 1e6、scale 缺省 linear）；
  给 band 时无需 start/stop；两者都缺 → scenario 形状 ValueError；计划域错
  （起止颠倒/非法刻度/非法 band 等）以计划函数的 ValueError 原样透传。
- 逐点采集：SimEmiReceiver（ctx['em_receiver'] 注入或内部 open_sim_emi_receiver
  新建）置频（freq_hz 公有属性直写——后端无 set_freq）后 measure——缺省
  measure(None) 底噪读数；scenario['iq_provider'] 为 Callable[freq_hz → iq] 时
  逐点取 IQ 注入（读数取全谱 bin 最大值，最坏口径）；注入实例参数透传
  （scenario 未显式给 detector/rbw_hz 不触碰其状态）；内部新建且未显式给
  rbw_hz 时逐点 set_rbw(None) 按 CISPR 频段缺省刷新（<30MHz→9kHz，≥30MHz→120kHz）。
- 越界裁剪（R35「频率域越界→裁剪并标注」）：计划点超出模拟接收机域
  [1e3, 3e9] Hz 时裁剪到最近边界并记 warnings（裁剪不丢点——n_points 与计划一致）。
- 杂散搜索：读数（dBm）超 scenario['spurious_threshold_dbm']（缺省 −100 dBm）
  的点附 'spurious': True（未超的点不带该键）；**阈值即敏感度口径**
  （sensitivity_note 注明）。
- 全程模拟口径：输出恒带 simulated=True 与 make_disclaimer_block('emc') 声明块。

调用方：build_report（EMC 段）；run_demo。
"""
from __future__ import annotations

import math
from numbers import Real

from src.open_sim_emi_receiver.open_sim_emi_receiver import (
    FREQ_MAX_HZ,
    FREQ_MIN_HZ,
    SimEmiReceiver,
    open_sim_emi_receiver,
)
from src.shared.make_disclaimer_block import make_disclaimer_block

from .plan_frequency_sweep import plan_frequency_sweep

__all__ = ["DEFAULT_SPURIOUS_THRESHOLD_DBM", "run_emc_sweep"]

#: 杂散判定阈值缺省（dBm）——即敏感度口径：读数（模拟）超阈即标记 spurious。
DEFAULT_SPURIOUS_THRESHOLD_DBM = -100.0

#: 计划参数透传键（值非 None 的键才透传，其余由计划函数补缺省）。
_PLAN_KEYS = ("start_hz", "stop_hz", "step_hz", "scale", "band")


def _require_dict(name: str, value: object) -> dict:
    """形状守卫：ctx/scenario 非 dict → ValueError（消息附类型与原值）。"""
    if not isinstance(value, dict):
        raise ValueError(
            f"{name} 必须为 dict，实际为 {type(value).__name__}: {value!r}"
        )
    return value


def _as_finite_real(name: str, raw: object) -> float:
    """数值守卫：拒 bool/非实数/NaN/±inf，返回 float（与后端家族口径一致）。"""
    if isinstance(raw, bool) or not isinstance(raw, Real):
        raise ValueError(f"{name} 必须为实数（bool 与其他类型一律拒绝）: {raw!r}")
    val = float(raw)
    if not math.isfinite(val):
        raise ValueError(f"{name} 必须为有限数（拒 NaN/±inf）: {raw!r}")
    return val


def _resolve_receiver(ctx: dict) -> tuple[SimEmiReceiver, bool]:
    """EMI 接收机解析：ctx['em_receiver'] 注入优先（参数透传），否则内部新建（工厂缺省）。"""
    injected = ctx.get("em_receiver")
    if injected is not None:
        return injected, True
    return open_sim_emi_receiver(), False


def run_emc_sweep(ctx: dict, scenario: dict) -> dict:
    """EMC 步进扫频编排：计划点表 → 逐点模拟读数 → 杂散标记/计数 → 敏感度口径声明（R35）。

    :param ctx: 运行上下文 dict——'em_receiver' 可注入 SimEmiReceiver 实例
        （注入实例参数透传：scenario 未显式给 detector/rbw_hz 时不触碰其状态；
        仪器域错 ValueError 原样透传）；缺省内部 open_sim_emi_receiver() 新建
    :param scenario: 扫描场景 dict——
        - 'start_hz'/'stop_hz'（无 band 时必需）：起止频率，透传计划函数；
        - 'step_hz'（可选）：线性刻度绝对步长 / 对数刻度每步相对增量，透传；
        - 'scale'（可选）：'linear'|'log'，透传；'band'（可选）：
          'cispr_a'|'cispr_b' 频段便捷参数，透传（给定时无需 start/stop）；
        - 'detector'/'rbw_hz'（可选）：显式检波器/RBW（域错透传）；
        - 'iq_provider'（可选）：Callable[freq_hz → iq]，逐点注入 IQ
          （非可调用非 None → TypeError）；
        - 'spurious_threshold_dbm'（可选）：杂散判定阈（缺省 −100.0，即敏感度口径）。
    :return: ``{'points': [{'freq_hz', 'power_dbm', 'spurious'?}, …], 'n_points': int,
        'n_spurious': int, 'plan': 计划函数原样返回, 'disclaimer':
        make_disclaimer_block('emc'), 'simulated': True, 'sensitivity_note': str,
        'warnings': [计划警告（single_point 等）+ 越界裁剪标注…]}``——
        freq_hz 为裁剪后实测频率；'spurious': True 仅附在超阈点上。
    :raises ValueError: ctx/scenario 非 dict；无 band 又缺 start/stop；
        spurious_threshold_dbm 非法；计划域错与仪器域错原样透传。
    :raises TypeError: iq_provider 给定但不可调用。
    """
    _require_dict("ctx", ctx)
    _require_dict("scenario", scenario)

    # ① 计划：start/stop/step/scale/band 全透传（值非 None 的键才进计划函数）
    plan_kwargs = {key: scenario[key] for key in _PLAN_KEYS if scenario.get(key) is not None}
    if "band" not in plan_kwargs and not {"start_hz", "stop_hz"} <= plan_kwargs.keys():
        raise ValueError(
            "scenario 缺 'start_hz'/'stop_hz'（或改用 'band' 频段便捷参数）"
        )
    if "band" in plan_kwargs:
        # band 给定时计划函数忽略 start/stop——缺省补 0 占位满足位置形参（频段值覆盖）
        plan_kwargs.setdefault("start_hz", 0)
        plan_kwargs.setdefault("stop_hz", 0)
    plan = plan_frequency_sweep(**plan_kwargs)  # 计划域错（起止颠倒等）ValueError 透传

    threshold = _as_finite_real(
        "spurious_threshold_dbm",
        scenario.get("spurious_threshold_dbm", DEFAULT_SPURIOUS_THRESHOLD_DBM),
    )
    iq_provider = scenario.get("iq_provider")
    if iq_provider is not None and not callable(iq_provider):
        raise TypeError(
            "scenario['iq_provider'] 须为 Callable[freq_hz → iq] 或缺省 None，"
            f"实际为 {type(iq_provider).__name__}: {iq_provider!r}"
        )

    receiver, injected = _resolve_receiver(ctx)
    detector_given = scenario.get("detector")
    if detector_given is not None:
        receiver.set_detector(detector_given)  # 域错透传
    rbw_given = scenario.get("rbw_hz")
    if rbw_given is not None:
        receiver.set_rbw(rbw_given)  # 域错透传

    warnings = [str(w) for w in plan.get("warnings", [])]
    points: list[dict] = []
    n_spurious = 0

    # ② 逐点采集（底噪或 iq_provider 注入）＋ 越界裁剪＋ ③ 杂散标记
    for freq_req in plan["points_hz"]:
        if FREQ_MIN_HZ <= freq_req <= FREQ_MAX_HZ:
            freq_meas = freq_req
        else:
            freq_meas = min(max(freq_req, FREQ_MIN_HZ), FREQ_MAX_HZ)
            warnings.append(
                f"计划点 {freq_req!r} Hz 超出模拟接收机域 "
                f"[{FREQ_MIN_HZ!r}, {FREQ_MAX_HZ!r}] Hz，已裁剪至 {freq_meas!r}"
                "（R35 越界裁剪+标注口径）"
            )
        # 置频：后端未提供 set_freq——freq_hz 公有属性直写（值已由裁剪保证域内）
        receiver.freq_hz = freq_meas
        if not injected and rbw_given is None:
            # 内部新建且未显式给 RBW：按 CISPR 频段缺省逐点刷新
            receiver.set_rbw(None)
        iq = iq_provider(freq_meas) if iq_provider is not None else None
        reading = receiver.measure(iq)  # iq=None → 底噪读数；给 iq → 逐 bin 频域检波
        power_raw = reading.get("power_dbm")
        if isinstance(power_raw, list):
            power_dbm = float(max(power_raw))  # iq 路径：全谱 bin 最大值（最坏口径）
        else:
            power_dbm = float(power_raw)
        point: dict = {"freq_hz": freq_meas, "power_dbm": power_dbm}
        if power_dbm > threshold:
            point["spurious"] = True
            n_spurious += 1
        points.append(point)

    # ④ 输出（阈值即敏感度口径——sensitivity_note 注明）
    return {
        "points": points,
        "n_points": len(points),
        "n_spurious": n_spurious,
        "plan": plan,
        "disclaimer": make_disclaimer_block("emc"),
        "simulated": True,
        "sensitivity_note": (
            f"敏感度口径：杂散判定阈值 spurious_threshold_dbm={threshold!r} dBm 即本演示"
            "的灵敏度口径——读数（模拟）超阈的频点标记 spurious=True"
        ),
        "warnings": warnings,
    }
