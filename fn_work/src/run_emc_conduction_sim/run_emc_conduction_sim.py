"""EMC 传导摸底模拟（R33）：LISN 模拟读数→限值线裕量→模拟口径声明——重写规约与签名意图详见 fn_docs/responsibility.md。

编排职责（CISPR 式读数归 SimEmiReceiver、声明文案归 make_disclaimer_block、本函数只做编排）：

- LISN 模拟读数链：scenario['freq_hz']（单点数值或非空序列——sweep 小段口径）逐点
  经 SimEmiReceiver（ctx['em_receiver'] 注入或内部 open_sim_emi_receiver 新建）置频
  （后端未提供 set_freq 方法——频率经 freq_hz 公有属性直写）后 measure：
  - 缺 scenario['iq'] → measure(None) 底噪口径（−150 dBm/Hz + 10·log10(rbw)）；
  - 给 scenario['iq']（电流探头模拟 IQ，同一序列逐点复测）→ 频域检波读数
    （逐 bin 列表），该点读数取全谱 bin 最大值——最坏发射口径（worst-case）。
- 限值线比较：scenario['limit_line_dbmv']（dBµV）支持标量（全点同限）或
  {freq_hz: dBµV} 映射（逐点限值，键须覆盖全部测点，缺频点 ValueError）；
  读数换算 dBµV = dBm + 107（50Ω 口径：0 dBm = 1 mW = √(1e-3·50) V ≈ 223.6 mV
  = 107 dBµV）；margin_db = 限值 − 读数 dBµV。
- 'passed' 口径：全部裕量非负（margin ≥ 0）→ True，任一为负 → False；未提供限值
  → None（无法判定但不抛——演示态继续）；**演示口径注明非认证**（compliance_note
  恒随裕量输出，非符合性判定）。
- 频域裁剪（R33「场景频段超模拟域→裁剪+标注」）：测点超出模拟接收机域
  [1e3, 3e9] Hz 时裁剪到最近域边界并记 warnings 条目（读数 freq_hz 为裁剪后
  实测频率，请求频率保留在 warnings 原文里）。
- ctx['em_receiver'] 注入实例参数透传：scenario 未显式给 detector/rbw_hz 时
  不触碰注入实例的检波器/RBW 状态（注入口径优先）；仪器域错
  （set_detector/set_rbw 抛 ValueError）原样透传；内部新建且未显式给 rbw_hz
  时逐点 set_rbw(None) 按 CISPR 频段缺省刷新（<30MHz→9kHz，≥30MHz→120kHz）。
- 全程模拟口径（R33 规约「要求真仪表而后端 sim→标明模拟口径继续」）：输出恒带
  simulated=True 与 make_disclaimer_block('emc') 声明块，读数绝不冒充实测。

调用方：build_report（EMC 段）；run_demo（EMC 场景）。
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from numbers import Real

from src.open_sim_emi_receiver.open_sim_emi_receiver import (
    FREQ_MAX_HZ,
    FREQ_MIN_HZ,
    SimEmiReceiver,
    open_sim_emi_receiver,
)
from src.shared.make_disclaimer_block import make_disclaimer_block

__all__ = ["DBMV_PER_DBM", "run_emc_conduction_sim"]

#: dBm → dBµV 换算常数（50Ω 口径）：0 dBm = 1 mW = √(1e-3·50) V ≈ 223.6 mV = 107 dBµV。
DBMV_PER_DBM = 107.0

#: passed 口径注记（随裕量输出——演示口径，非认证）。
_COMPLIANCE_NOTE = (
    "passed 口径：全部频点裕量非负（margin_db ≥ 0）记为合规——演示口径，非认证符合性判定"
)

#: 未提供限值线时的注记（margin_db=None、passed=None，演示态继续不抛）。
_NO_LIMIT_NOTE = (
    "scenario 未提供 limit_line_dbmv：margin_db=None、passed=None（无法判定，演示态继续）"
)

#: iq 注入路径的读数口径注记。
_IQ_WORST_CASE_NOTE = "iq 注入路径读数为全谱 bin 最大值（最坏发射口径）"


def _as_finite_real(name: str, raw: object) -> float:
    """数值守卫：拒 bool/非实数/NaN/±inf，返回 float（与后端家族口径一致）。"""
    if isinstance(raw, bool) or not isinstance(raw, Real):
        raise ValueError(f"{name} 必须为实数（bool 与其他类型一律拒绝）: {raw!r}")
    val = float(raw)
    if not math.isfinite(val):
        raise ValueError(f"{name} 必须为有限数（拒 NaN/±inf）: {raw!r}")
    return val


def _require_dict(name: str, value: object) -> dict:
    """形状守卫：ctx/scenario 非 dict → ValueError（消息附类型与原值）。"""
    if not isinstance(value, dict):
        raise ValueError(
            f"{name} 必须为 dict，实际为 {type(value).__name__}: {value!r}"
        )
    return value


def _scenario_freq_points(scenario: dict) -> list[float]:
    """scenario['freq_hz'] → 非空测点列表（单点数值或非空序列；缺键/空/非法元素 → ValueError）。"""
    raw = scenario.get("freq_hz")
    if raw is None:
        raise ValueError("scenario 缺 'freq_hz'（传导摸底测点：单点数值或非空序列）")
    if isinstance(raw, Real) and not isinstance(raw, bool):
        items = [raw]
    elif isinstance(raw, (list, tuple)):
        if not raw:
            raise ValueError("scenario['freq_hz'] 为空序列（至少一个测点）")
        items = list(raw)
    else:
        raise ValueError(
            f"scenario['freq_hz'] 须为数值或非空数值序列，"
            f"实际为 {type(raw).__name__}: {raw!r}"
        )
    return [_as_finite_real(f"freq_hz[{i}]", f) for i, f in enumerate(items)]


def _resolve_limits(limit_spec: object, requested: list[float]) -> list[float | None]:
    """限值线解析：None→全 None；标量 dBµV 全点同限；Mapping 逐点取限（缺频点 ValueError）。"""
    if limit_spec is None:
        return [None] * len(requested)
    if isinstance(limit_spec, Real) and not isinstance(limit_spec, bool):
        value = _as_finite_real("limit_line_dbmv", limit_spec)
        return [value] * len(requested)
    if isinstance(limit_spec, Mapping):
        limits: list[float | None] = []
        for freq in requested:
            if freq not in limit_spec:
                raise ValueError(
                    f"limit_line_dbmv 映射缺频点 {freq!r} 的限值（须覆盖全部测点）"
                )
            limits.append(
                _as_finite_real(f"limit_line_dbmv[{freq!r}]", limit_spec[freq])
            )
        return limits
    raise ValueError(
        f"limit_line_dbmv 须为标量 dBµV 或 {{freq_hz: dBµV}} 映射，"
        f"实际为 {type(limit_spec).__name__}: {limit_spec!r}"
    )


def _clip_freq(freq_hz: float) -> tuple[float, str | None]:
    """测点裁剪到模拟接收机域 [1e3, 3e9] Hz：域内原样；域外取最近边界并附标注文案。"""
    if FREQ_MIN_HZ <= freq_hz <= FREQ_MAX_HZ:
        return freq_hz, None
    clipped = min(max(freq_hz, FREQ_MIN_HZ), FREQ_MAX_HZ)
    return clipped, (
        f"freq_hz {freq_hz!r} 超出模拟接收机域 [{FREQ_MIN_HZ!r}, {FREQ_MAX_HZ!r}] Hz，"
        f"已裁剪至 {clipped!r}（R33 裁剪+标注口径）"
    )


def _resolve_receiver(ctx: dict) -> tuple[SimEmiReceiver, bool]:
    """EMI 接收机解析：ctx['em_receiver'] 注入优先（参数透传），否则内部新建（工厂缺省）。"""
    injected = ctx.get("em_receiver")
    if injected is not None:
        return injected, True
    return open_sim_emi_receiver(), False


def run_emc_conduction_sim(ctx: dict, scenario: dict) -> dict:
    """EMC 传导摸底模拟：LISN 模拟读数 → 限值线裕量 → 模拟口径声明（R33，演示流程）。

    :param ctx: 运行上下文 dict——'em_receiver' 可注入 SimEmiReceiver 实例
        （注入实例参数透传：scenario 未显式给 detector/rbw_hz 时不触碰其状态；
        仪器域错 ValueError 原样透传）；缺省内部 open_sim_emi_receiver() 新建
    :param scenario: EMC 传导摸底场景 dict——
        - 'freq_hz'（必需）：单点数值或非空数值序列（sweep 小段口径）；
        - 'rbw_hz'（可选）：显式 RBW（正有限实数，非法由 set_rbw 拒）；
        - 'detector'（可选）：'peak'|'quasi_peak'|'average'（非法由 set_detector 拒）；
        - 'iq'（可选）：电流探头模拟 IQ 序列（同一序列逐点复测）；
        - 'limit_line_dbmv'（可选）：标量 dBµV 或 {freq_hz: dBµV} 映射。
    :return: ``{'readings': [{'freq_hz', 'power_dbm', 'power_dbuv', 'margin_db',
        'rbw_hz'}, ...], 'detector': 生效检波器, 'passed': bool|None, 'simulated': True,
        'disclaimer': make_disclaimer_block('emc'), 'conversion_note': dBµV 换算口径,
        'warnings': [裁剪标注…], 'compliance_note'|'limit_note', 'reading_note'?}``——
        裕量全部非负 → passed=True（演示口径非认证）；未给限值 → margin/passed=None。
    :raises ValueError: ctx/scenario 非 dict；缺/非法 'freq_hz'；limit_line_dbmv
        形状错或映射缺频点；仪器（注入或内部）参数域错（set_detector/set_rbw、
        iq 形状错）原样透传。
    """
    _require_dict("ctx", ctx)
    _require_dict("scenario", scenario)

    requested = _scenario_freq_points(scenario)
    limits = _resolve_limits(scenario.get("limit_line_dbmv"), requested)

    receiver, injected = _resolve_receiver(ctx)

    detector_given = scenario.get("detector")
    if detector_given is not None:
        receiver.set_detector(detector_given)  # 域错透传
    rbw_given = scenario.get("rbw_hz")
    if rbw_given is not None:
        receiver.set_rbw(rbw_given)  # 域错透传

    iq = scenario.get("iq")
    warnings: list[str] = []
    readings: list[dict] = []
    effective_detector: str | None = None

    for index, freq_req in enumerate(requested):
        freq_meas, warning = _clip_freq(freq_req)
        if warning is not None:
            warnings.append(warning)
        # 置频：后端未提供 set_freq——freq_hz 公有属性直写（值已由裁剪保证域内）
        receiver.freq_hz = freq_meas
        if not injected and rbw_given is None:
            # 内部新建且未显式给 RBW：按 CISPR 频段缺省逐点刷新（<30MHz→9kHz，≥30MHz→120kHz）
            receiver.set_rbw(None)
        reading = receiver.measure(iq)  # iq=None → 底噪口径标量；给 iq → 逐 bin 频域检波
        if effective_detector is None:
            effective_detector = reading.get("detector")
        power_raw = reading.get("power_dbm")
        if isinstance(power_raw, list):
            power_dbm = float(max(power_raw))  # iq 路径：全谱 bin 最大值（最坏发射口径）
        else:
            power_dbm = float(power_raw)
        power_dbuv = power_dbm + DBMV_PER_DBM
        limit = limits[index]
        margin_db = None if limit is None else limit - power_dbuv
        readings.append(
            {
                "freq_hz": freq_meas,
                "power_dbm": power_dbm,
                "power_dbuv": power_dbuv,
                "margin_db": margin_db,
                "rbw_hz": reading.get("rbw_hz"),
            }
        )

    margins = [r["margin_db"] for r in readings if r["margin_db"] is not None]
    passed = all(m >= 0.0 for m in margins) if margins else None

    result = {
        "readings": readings,
        "detector": effective_detector,
        "passed": passed,
        "simulated": True,
        "disclaimer": make_disclaimer_block("emc"),
        "conversion_note": (
            f"功率换算口径：dBµV = dBm + {DBMV_PER_DBM:.0f}"
            "（50Ω：0 dBm = 1 mW ≈ 223.6 mV = 107 dBµV）"
        ),
        "warnings": warnings,
    }
    if iq is not None:
        result["reading_note"] = _IQ_WORST_CASE_NOTE
    if margins:
        result["compliance_note"] = _COMPLIANCE_NOTE
    else:
        result["limit_note"] = _NO_LIMIT_NOTE
    return result
