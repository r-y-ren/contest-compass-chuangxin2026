"""GB 42590 §5.11 协议编排：样式合成+带宽校验→基线放行→功率阶梯→P_crit 登记——B13 顶层，R23。

调用方：run_demo / serve_console（国标测法编排——与 B12 三路采集 record_run_streams
合体即完整测评闭环）。重写规约与签名意图详见 fn_docs/responsibility.md R23。

顺序化口径（本函数与 record_run_streams 的分工，文档注明）：
- 基线窗口（阶段②）经 record_run_streams 采无干扰段：backend 不发射、jam 事件流
  置空（baseline_ctx['jam_events']=[] 口径见证），kpi.csv 即基线 KPI 行，
  max_kpi_rows 钳基线窗口行数；
- 阶梯判据（阶段③）本函数自管采集（顺序模型，不起线程/后台协作者）：按
  ctx['dut'] 起 DUT 源（sim→simulate_link_degradation；真链路→drive_esp32_link /
  drive_nrf24_link），failure_cb 每档拉 judge_min_samples 个样本→normalize_kpi
  归一→聚合 compute_per→check_failure（EN 300 328 口径 PER≥阈值判失效）；
- 监测谱/录制路不在本函数（GB 判据只看链路 KPI）：run_demo 的 record_run_streams
  另行跑监测/录制，与本函数各司其职。

阶段编排：
① 样式合成与带宽校验：噪声/单音/多音（多音=composite 两单音，分量频偏
  ±tone_separation_hz/2），其余配方样式（sweep/chirp/pulse/partial_band）经
  别名/直名透传 synthesize_style；带宽类样式（bandlimited_noise/partial_band/
  chirp/sweep/composite）对 scenario['victim_bw_hz'] 校验干扰带宽≥链路带宽，
  不足→ProtocolError（附 jam_bw_hz/victim_bw_hz 两值）；单音（tone）/脉冲
  （pulse）窄带/时域样式不适用该校验（口径豁免）；victim_bw_hz 缺失→校验跳过
  并在汇总 note 如实注记；StyleError（合成域错）包装为 ProtocolError（发射前）。
② 基线：record_run_streams 采无干扰窗口→run_baseline_check；不放行→中止返回
  {'status':'baseline_rejected', …}（不抛——退出码语义归调用方）；sim 源基线
  事件缺省自动生成中性无干扰事件（jsr 取 scenario['baseline_jsr_db'] 缺省
  −100dB），也可经 ctx['baseline_sim_events']/ctx['dut']['baseline_events'] 直给。
③ 阶梯：backend.start_tx([iq]) 起发射→run_power_ladder（GB 缺省 −5dB 起 5dB 步、
  0dBm 红线截断；failure_cb=KPI 判据；dwell 透传；ladder 收尾自停发射）。
④ 失效即 record_failure_level 记 P_crit：jsr 取 ctx['jsr_est']（数值或
  {'jsr_db': …} dict）→lookup_jsr(ctx['gain_calibration']) 兜底→两路皆缺则条目
  记 unknown（record_failure_level 的 missing_fields 口径）；实达电平按
  「满增益 0dBm − 实达衰减」口径换算（ladder 组合的 achieved_db 是衰减量）。
⑤ 汇总 {'status': 'completed'|'baseline_rejected'|'failed', 'plan',
  'failure_levels': [条目], 'steps_executed', 'baseline', 'stopped_at', 'note'}；
  判据永不触发走完计划/truncated/max_steps 均 status='completed'（note 标未失效）。

错误契约：ProtocolError（本文件定义：带宽校验/编排形状错——发射前，不涉及停发射）；
阶段②③的下游异常（LinkError/BackendError/AttenuationError/EventWriteError/
ValueError 族）由 record_run_streams / run_power_ladder / drive_* 按「先停发射再
透传」语义上抛，本函数原样透传不吞不换（ladder 判据回调自身的异常同语义）；
阶梯段（含判据回调）异常透传前本函数尽力补 protocol_stop 事件（status='aborted'+
error 摘要；append_event 失败不再二次抛，原异常透传优先——B13 复审低#3）。
"""
from __future__ import annotations

import csv
import math
import os
import time
from numbers import Real

from .check_failure import check_failure
from .record_failure_level import record_failure_level
from src.drive_esp32_link.drive_esp32_link import drive_esp32_link
from src.drive_nrf24_link.drive_nrf24_link import drive_nrf24_link
from src.lookup_jsr.lookup_jsr import lookup_jsr
from src.normalize_kpi.compute_per import compute_per
from src.normalize_kpi.normalize_kpi import normalize_kpi
from src.record_run_streams.record_run_streams import record_run_streams
from src.run_baseline_check.run_baseline_check import run_baseline_check
from src.run_power_ladder.run_power_ladder import run_power_ladder
from src.simulate_link_degradation.simulate_link_degradation import (
    simulate_link_degradation,
)
from src.shared.append_event import append_event
from src.shared.stop_transmit_safely import stop_transmit_safely
from src.synthesize_style.synthesize_style import synthesize_style
from src.switch_style.lookup_style_recipe import StyleError

__all__ = ["ProtocolError", "execute_gb42590_protocol"]


class ProtocolError(RuntimeError):
    """GB 42590 编排域错误：干扰带宽低于链路带宽 / 场景与编排形状错（发射前）。

    带宽校验失败时附结构化事实 ``jam_bw_hz`` / ``victim_bw_hz``（附两值口径）；
    其余编排形状错无附加属性。
    """

    def __init__(self, message: str, **facts) -> None:
        super().__init__(message)
        for name, value in facts.items():
            setattr(self, name, value)


#: 缺省采样率（composite 无配方缺省，场景未给 fs 时兜底，与六类配方缺省同域）。
_DEFAULT_FS_HZ = 1e6
#: 判据路每档窗口最小样本数（拉取 DUT 样本数，聚合一个 PER 窗口）。
_DEFAULT_JUDGE_MIN_SAMPLES = 10
#: 基线窗口行数（record_run_streams max_kpi_rows 钳位）。
_DEFAULT_BASELINE_SAMPLES = 10
#: 失效判据 PER 阈值（EN 300 328 口径，与 check_failure 缺省一致）。
_DEFAULT_PER_THRESHOLD = 0.10
#: 档间停留缺省（与 run_power_ladder 缺省一致；场景 'dwell_s' 覆盖）。
_DEFAULT_DWELL_S = 1.0
#: sim 源基线缺省中性无干扰 JSR（悬崖左远端，PER≈base_per）。
_NEUTRAL_BASELINE_JSR_DB = -100.0

#: 场景样式名（小写）→ synthesize_style 规范样式名。GB §5.11 三口径：噪声/单音/
#: 多音（多音=composite 两单音）；其余配方样式直名透传。
_STYLE_ALIASES = {
    "noise": "bandlimited_noise",
    "bandlimited_noise": "bandlimited_noise",
    "tone": "tone",
    "multi_tone": "composite",
    "multitone": "composite",
    "multi-tone": "composite",
    "composite": "composite",
    "sweep": "sweep",
    "chirp": "chirp",
    "pulse": "pulse",
    "partial_band": "partial_band",
}

#: 场景键→合成参数直传白名单（生成器形参名 + power_dbm 合规域记录键）。
_STYLE_PARAM_KEYS = (
    "power_dbm",
    "n_samples",
    "seed",
    "amplitude",
    "freq_offset_hz",
    "center_offset_hz",
    "bandwidth_hz",
    "victim_bw_hz",
    "fraction",
    "f0",
    "f1",
    "duration_s",
    "repeats",
    "center_hz",
    "period_s",
    "shape",
    "pulse_width_s",
    "repeat_hz",
    "carrier_hz",
)

_DUT_SOURCES = ("esp32", "nrf24", "sim")


def _finite_number(value: object) -> bool:
    """有限实数判定（bool 不算）。"""
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _positive_int(value: object, name: str) -> int:
    """正整数校验（bool 是 int 子类一并排除），非法抛 ProtocolError（编排形状错）。"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProtocolError(f"{name} 须为正 int，收到 {value!r}")
    return value


def _resolve_fs(scenario: dict) -> float:
    """采样率解析：fs > sample_rate > sample_rate_hz，均须有限正数；缺省 1e6。"""
    for key in ("fs", "sample_rate", "sample_rate_hz"):
        value = scenario.get(key)
        if _finite_number(value) and float(value) > 0.0:
            return float(value)
    return _DEFAULT_FS_HZ


def _build_style_params(scenario: dict) -> tuple[str, dict]:
    """场景→synthesize_style 参数：样式别名归一 + 白名单键直传 + GB 三口径构参。

    多音（multi_tone）无显式 components 时按两单音 composite 构造：分量频偏
    ±tone_separation_hz/2（缺省回落 jam_bw_hz → victim_bw_hz，须为正数）；
    噪声缺省带宽回落 victim_bw_hz（干扰带宽≥链路带宽的缺省满足构造）；
    scenario['params'] 嵌套 dict 合并进合成参数（平铺波形键优先，B13 复审中#1）。
    """
    raw_style = scenario.get("style")
    if raw_style is None:
        raw_style = scenario.get("jamming_style")
    if not isinstance(raw_style, str) or not raw_style.strip():
        raise ProtocolError(
            f"scenario 须提供 'style'（噪声/单音/多音或配方样式名），收到 {raw_style!r}"
        )
    key = raw_style.strip().lower()
    if key not in _STYLE_ALIASES:
        raise ProtocolError(
            f"未知样式 {raw_style!r}（别名在册: {sorted(set(_STYLE_ALIASES))}）"
        )
    canonical = _STYLE_ALIASES[key]
    fs = _resolve_fs(scenario)
    params: dict = {"style": canonical, "fs": fs}
    for name in _STYLE_PARAM_KEYS:
        if name in scenario:
            params[name] = scenario[name]

    if canonical == "composite":
        components = scenario.get("components")
        if isinstance(components, list) and components:
            params["components"] = components  # 显式分量直给：合成语义归 synthesize_style
        else:
            separation = scenario.get("tone_separation_hz")
            if separation is None:
                separation = scenario.get("jam_bw_hz")
            if separation is None:
                separation = scenario.get("victim_bw_hz")
            if not _finite_number(separation) or float(separation) <= 0.0:
                raise ProtocolError(
                    "多音样式须提供正 'tone_separation_hz'（缺省回落 jam_bw_hz/"
                    f"victim_bw_hz），收到 {separation!r}"
                )
            half = float(separation) / 2.0
            params["components"] = [
                {"style": "tone", "fs": fs, "freq_offset_hz": half},
                {"style": "tone", "fs": fs, "freq_offset_hz": -half},
            ]
    elif canonical == "bandlimited_noise" and "bandwidth_hz" not in params:
        victim = scenario.get("victim_bw_hz")
        if _finite_number(victim) and float(victim) > 0.0:
            params["bandwidth_hz"] = float(victim)

    # B13 复审中#1：'params' 嵌套 dict 合并进合成参数——平铺波形键优先
    # （{**scenario['params'], **平铺参数}，与 synthesize_style「显式参数优先于
    # defaults」/switch_style 同口径）；嵌套-only 键（如 n_samples/freq_offset_hz）
    # 生效，合并结果经实际合成反映进 meta（protocol_start 的 n_samples 即实际
    # 合成点数，非配方缺省）。
    nested = scenario.get("params")
    if isinstance(nested, dict):
        params = {**nested, **params}
    return canonical, params


def _jam_bandwidth_hz(canonical: str, meta: dict) -> float | None:
    """由合成 meta/合并参数推导干扰占用带宽（Hz）；窄带/时域样式返回 None（豁免）。

    - bandlimited_noise：声明的 bandwidth_hz 优先（测量值 measured_bw_hz 兜底）；
    - partial_band：occupied_bw_hz（bin 计数实测）优先，fraction×victim_bw 兜底；
    - chirp：bandwidth_hz；sweep：|f1−f0|；
    - composite（多音）：分量频偏极差（max−min，两单音即间距；单分量/同频=0）。
    """
    merged = meta.get("params") if isinstance(meta.get("params"), dict) else {}
    if canonical == "bandlimited_noise":
        for value in (merged.get("bandwidth_hz"), meta.get("measured_bw_hz")):
            if _finite_number(value) and float(value) >= 0.0:
                return float(value)
        return None
    if canonical == "partial_band":
        occupied = meta.get("occupied_bw_hz")
        if _finite_number(occupied):
            return float(occupied)
        fraction, victim = merged.get("fraction"), merged.get("victim_bw_hz")
        if _finite_number(fraction) and _finite_number(victim):
            return float(fraction) * float(victim)
        return None
    if canonical == "chirp":
        value = merged.get("bandwidth_hz")
        return float(value) if _finite_number(value) else None
    if canonical == "sweep":
        f0, f1 = merged.get("f0"), merged.get("f1")
        if _finite_number(f0) and _finite_number(f1):
            return abs(float(f1) - float(f0))
        return None
    if canonical == "composite":
        components = merged.get("components")
        if isinstance(components, list) and components:
            offsets = [
                float(comp.get("freq_offset_hz", 0.0))
                if isinstance(comp, dict) and _finite_number(comp.get("freq_offset_hz", 0.0))
                else 0.0
                for comp in components
            ]
            return max(offsets) - min(offsets)
        return None
    return None  # tone / pulse：窄带/时域样式，带宽校验口径豁免


def _check_bandwidth(canonical: str, meta: dict, scenario: dict) -> float | None:
    """干扰带宽≥链路带宽校验（GB 42590 §5.11）：不足抛 ProtocolError 附两值。

    victim_bw_hz 缺失→跳过（返回 None，由调用方 note 注记）；非正有限数→
    ProtocolError（无法诚实校验）；非带宽类样式（jam_bw=None）→豁免返回 None。
    """
    victim = scenario.get("victim_bw_hz")
    if victim is None:
        return None
    if not _finite_number(victim) or float(victim) <= 0.0:
        raise ProtocolError(
            f"scenario['victim_bw_hz'] 须为正有限实数（链路带宽），收到 {victim!r}"
        )
    jam_bw = _jam_bandwidth_hz(canonical, meta)
    if jam_bw is None:
        return None
    if jam_bw < float(victim):
        raise ProtocolError(
            f"干扰带宽 {jam_bw:g} Hz 低于链路带宽 {float(victim):g} Hz"
            "（GB 42590 §5.11：干扰带宽须不低于链路带宽）",
            jam_bw_hz=jam_bw,
            victim_bw_hz=float(victim),
        )
    return jam_bw


def _baseline_sim_events(dut: dict, scenario: dict, n_rows: int) -> list[dict]:
    """sim 源基线缺省事件：中性无干扰（jsr 悬崖左远端）× ceil(行数/每事件样本数)。"""
    per_event = dut.get("samples_per_event", 3)
    if isinstance(per_event, bool) or not isinstance(per_event, int) or per_event <= 0:
        per_event = 3
    n_events = max(1, math.ceil(n_rows / per_event))
    jsr = scenario.get("baseline_jsr_db", _NEUTRAL_BASELINE_JSR_DB)
    if not _finite_number(jsr):
        jsr = _NEUTRAL_BASELINE_JSR_DB
    return [
        {"type": "baseline", "jsr_db": float(jsr), "ts": float(index)}
        for index in range(n_events)
    ]


def _opt_float(text: object) -> float | None:
    """CSV 单元格→float|None：空/坏值 None（不可比窗不计判据，保守口径）。"""
    if text is None or text == "":
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _baseline_rows(run_dir: str) -> list[dict]:
    """基线窗口 KPI 行读回：kpi.csv → run_baseline_check 输入行（judge_per/rssi_dbm）。"""
    path = os.path.join(run_dir, "kpi.csv")
    rows: list[dict] = []
    if not os.path.isfile(path):
        return rows
    with open(path, newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            rows.append(
                {
                    "judge_per": _opt_float(record.get("judge_per")),
                    "rssi_dbm": _opt_float(record.get("rssi_dbm")),
                }
            )
    return rows


def _open_dut_source(ctx: dict, scenario: dict) -> tuple[object, str]:
    """按 ctx['dut'] 起 DUT 源（判据路采集）：返回 (样本生成器, source 名)。

    sim→simulate_link_degradation（事件源 ctx['sim_events'] 缺省回落
    dut['events']，信号电平取 scenario['signal_power_db']）；真链路→
    drive_esp32_link / drive_nrf24_link（serial_config，ctx 透传共享停发射凭据）。
    配置形状错由各驱动急切校验抛 ValueError/LinkError（发射前直抛）。
    """
    dut = ctx.get("dut")
    if not isinstance(dut, dict):
        raise ProtocolError(
            f"ctx['dut'] 必须为 dict（source/serial_config/events…），"
            f"收到 {type(dut).__name__}"
        )
    source = dut.get("source")
    if source == "sim":
        events = ctx.get("sim_events")
        if events is None:
            events = dut.get("events")
        if events is None:
            raise ProtocolError(
                "source='sim' 需要注入事件源：ctx['sim_events']（或 ctx['dut']['events']）"
                "须为 Iterable[dict]（调用方构造）"
            )
        sim_ctx = None
        if "signal_power_db" in scenario:
            sim_ctx = {"signal_power_db": scenario["signal_power_db"]}
        generator = simulate_link_degradation(
            events,
            model_params=dut.get("model_params"),
            ctx=sim_ctx,
            samples_per_event=dut.get("samples_per_event", 3),
        )
        return generator, "sim"
    if source in ("esp32", "nrf24"):
        driver = drive_esp32_link if source == "esp32" else drive_nrf24_link
        # ctx 整体透传：drive 取 backend/run_token 停发射凭据（错误路径实停）。
        return driver(dut.get("serial_config"), ctx), source
    raise ProtocolError(
        f"ctx['dut']['source'] 须为 {list(_DUT_SOURCES)} 之一，收到 {source!r}"
    )


def _aggregate_window(samples: list[dict], source: str) -> tuple[int, int]:
    """窗口样本→(n_error, n_total) 聚合计数（compute_per 输入口径）。

    计数优先级：样本自带 sent/err 整数计数（sim 口径，精确累计）＞判据行
    judge_per 比值（esp32/nrf24 per_raw-only 口径：一行记一"样本"，错误数取
    比值和四舍五入——文档化近似）；judge_per=None（不可比窗）不计入。
    """
    n_total = 0
    n_error_exact = 0
    ratio_sum = 0.0
    ratio_rows = 0
    for sample in samples:
        row = normalize_kpi(sample, source)  # KpiError 上抛→ladder 停发射透传
        sent, err = sample.get("sent"), sample.get("err")
        if (
            isinstance(sent, int)
            and not isinstance(sent, bool)
            and isinstance(err, int)
            and not isinstance(err, bool)
            and sent >= 0
            and err >= 0
        ):
            n_total += sent
            n_error_exact += err
            continue
        judge = row["judge_per"]
        if judge is not None:
            ratio_rows += 1
            ratio_sum += judge
    n_total += ratio_rows
    return n_error_exact + int(round(ratio_sum)), n_total


def _make_failure_cb(state: dict):
    """判据回调工厂：每档拉 state['min_samples'] 个 DUT 样本→聚合→check_failure。

    失效时把该档记录副本+PER 窗口快照存入 state['failure']（P_crit 登记素材）；
    样本不足（源耗尽/全不可比窗）→check_failure insufficient_samples 保守继续。
    """

    def failure_cb(step_record: dict) -> dict:
        pulled: list[dict] = []
        for _ in range(state["min_samples"]):
            try:
                pulled.append(next(state["dut_iter"]))
            except StopIteration:
                break
        n_error, n_total = _aggregate_window(pulled, state["source"])
        per_result = compute_per(
            n_error, n_total, window={"type": "interval", "last_n": len(pulled)}
        )
        verdict = check_failure(per_result, state["threshold"])
        if verdict["failed"]:
            state["failure"] = {
                "record": dict(step_record),
                "per_result": per_result,
                "verdict": verdict,
            }
        return {"failed": verdict["failed"], "detail": verdict["detail"]}

    return failure_cb


def _estimate_jsr_db(ctx: dict, scenario: dict, record: dict) -> float | None:
    """失效档 JSR 估计：ctx['jsr_est']（数值或 {'jsr_db'} dict）→lookup_jsr 兜底。

    lookup_jsr 仅在 ctx['gain_calibration']（标定表 config dict）在位时尝试
    （档位取 ladder 组合 fine_step_db、频率取 scenario freq_hz/freq_mhz、信号
    电平取 scenario['signal_power_db'] 缺省 ctx['link_power_db']）；lookup_jsr
    一切异常转 status 返回不抛；两路皆缺→None（条目记 unknown）。
    """
    estimate = ctx.get("jsr_est")
    if isinstance(estimate, dict):
        jsr = estimate.get("jsr_db")
        if _finite_number(jsr):
            return float(jsr)
    elif _finite_number(estimate):
        return float(estimate)
    config = ctx.get("gain_calibration")
    if isinstance(config, dict):
        freq_hz = scenario.get("freq_hz")
        if not _finite_number(freq_hz):
            freq_mhz = scenario.get("freq_mhz")
            freq_hz = float(freq_mhz) * 1e6 if _finite_number(freq_mhz) else 0.0
        signal = scenario.get("signal_power_db")
        if not _finite_number(signal):
            signal = ctx.get("link_power_db")
        if _finite_number(signal):
            outcome = lookup_jsr(
                record.get("fine_step_db"), freq_hz, float(signal), config
            )
            if outcome.get("status") == "ok" and _finite_number(outcome.get("jsr_db")):
                return float(outcome["jsr_db"])
    return None


def _record_failure_entry(
    state: dict, ctx: dict, scenario: dict, style: str
) -> dict:
    """失效档→record_failure_level 条目：档位/电平/JSR/KPI 快照/时间戳固化。

    电平口径：ladder 组合 achieved_db 是**衰减量**——实达干扰电平按满增益 0dBm
    口径取负值（achieved_level=−achieved_attenuation）；target_db 为档位目标
    干扰功率（dBm）。两值均入 kpi_snapshot 溯源。
    """
    failure = state["failure"]
    record = failure["record"]
    achieved_att = record.get("achieved_db")
    achieved_level = (
        -float(achieved_att) if _finite_number(achieved_att) else None
    )
    per_result = failure["per_result"]
    return record_failure_level(
        {
            "step": record.get("step"),
            "target_db": record.get("target_db"),
            "achieved_db": achieved_level,
            "jsr_db": _estimate_jsr_db(ctx, scenario, record),
            "per": per_result.get("per"),
            "kpi_snapshot": {
                "target_db": record.get("target_db"),
                "achieved_attenuation_db": (
                    float(achieved_att) if _finite_number(achieved_att) else None
                ),
                "achieved_level_db": achieved_level,
                "per_result": per_result,
                "verdict_detail": failure["verdict"]["detail"],
            },
            "style": style,
            "ts_ms": int(time.monotonic() * 1000),
        }
    )


#: 汇总返回键集（精确口径，调用方/报告消费方依赖）。
_RESULT_KEYS = (
    "status",
    "plan",
    "failure_levels",
    "steps_executed",
    "baseline",
    "stopped_at",
    "note",
)

_COMPLETED_NOTES = {
    "truncated": "ladder truncated: 计划触及 0dBm 红线截断，判据未触发（未失效）",
    "max_steps": "ladder max_steps: 档数上限用尽，判据未触发（未失效）",
    "complete": "ladder complete: 计划完整执行，判据未触发（未失效）",
}


def execute_gb42590_protocol(ctx: dict, scenario: dict | None = None) -> dict:
    """GB 42590 §5.11 测法编排：样式合成+带宽校验→基线→功率阶梯→失效电平表。

    输入:
        ctx: 运行上下文——'run_dir'（事件/基线落盘目录）、'backend'（发射/衰减后端，
            start_tx 起干扰发射、set_attenuation/set_tx_gain 由 ladder 下发）、
            'scenario'（scenario 参数缺省回落）、'dut'（判据路 DUT 源配置：
            source='sim' 用 ctx['sim_events']/dut['events']；'esp32'/'nrf24' 用
            dut['serial_config']——lines 源须可重复迭代，基线与判据路各起一份）、
            'link_power_db'（被测链路发射功率 dBm，阶梯基准）、可选 'jsr_est'/
            'gain_calibration'（失效档 JSR）、'attenuator_cal'（ladder 细档标定）；
        scenario: 场景 dict，None=取 ctx['scenario']——'style'（噪声/单音/多音/
            配方样式名）、'fs'、'victim_bw_hz'（链路带宽，带宽校验基准）、
            'bandwidth_hz'（噪声干扰带宽，缺省回落 victim_bw_hz）、
            'tone_separation_hz'（多音两单音间距，缺省回落 jam_bw_hz/victim_bw_hz）、
            'components'（composite 显式分量直给）、'params'（嵌套合成参数 dict：
            合并进合成参数，平铺波形键优先——嵌套-only 键如 n_samples/
            freq_offset_hz 生效，protocol_start 的 n_samples 反映实际合成，
            B13 复审中#1）、'baseline_samples'（基线窗口
            行数，缺省 10）、'baseline'（run_baseline_check 阈值覆盖 dict）、
            'per_threshold'（失效判据阈，缺省 0.10）、'judge_min_samples'（判据路
            每档窗口，缺省 10；scenario 缺键回落 ctx 同名键，两级
            scenario>ctx>缺省——B13 复审低#2）、'dwell_s'（档间停留，缺省 1.0；
            同两级回落 ctx['dwell_s']）、'ladder'
            （ladder_params 覆盖：start_db/step_db/stop_db/max_steps）。

    输出:
        {'status': 'completed'|'baseline_rejected'|'failed', 'plan': 阶梯计划
        （baseline_rejected 时 None）, 'failure_levels': [record_failure_level 条目],
        'steps_executed': int, 'baseline': run_baseline_check 报告, 'stopped_at':
        失效档索引|None, 'note': 人读汇总注（含 ladder reason/带宽校验跳过注记）}。

    错误:
        ProtocolError: 干扰带宽<链路带宽（附 jam_bw_hz/victim_bw_hz）/ 场景与
        编排形状错 / StyleError 合成域错包装——均在发射前（不涉及停发射）；
        其余下游异常（LinkError/BackendError/AttenuationError/EventWriteError/
        ValueError 族）按各编排函数「先停发射再透传」语义原样透传；其中阶梯段
        （含判据回调）异常透传前尽力补 protocol_stop 事件（status='aborted'+
        error 摘要；append_event 失败不再二次抛——B13 复审低#3）。
    """
    if not isinstance(ctx, dict):
        raise ProtocolError(f"ctx 必须为 dict，收到 {type(ctx).__name__}")
    if scenario is None:
        scenario = ctx.get("scenario")
    if not isinstance(scenario, dict):
        raise ProtocolError(
            f"scenario 缺失或非 dict（参数直给或 ctx['scenario']），收到 {scenario!r}"
        )
    run_dir_raw = ctx.get("run_dir")
    if run_dir_raw is None or not isinstance(run_dir_raw, (str, os.PathLike)):
        raise ProtocolError(
            f"ctx['run_dir'] 缺失或非路径（基线采集与事件落盘目录），收到 {run_dir_raw!r}"
        )
    run_dir = os.fspath(run_dir_raw)
    backend = ctx.get("backend")
    link_power_db = ctx.get("link_power_db", 0.0)
    if not _finite_number(link_power_db):
        raise ProtocolError(
            f"ctx['link_power_db'] 须为有限实数（被测链路发射功率 dBm），"
            f"收到 {link_power_db!r}"
        )

    # ---------- ① 样式合成 + 带宽校验（发射前，ProtocolError 域） ----------
    canonical, params = _build_style_params(scenario)
    try:
        iq, meta = synthesize_style(params)
    except StyleError as exc:
        raise ProtocolError(
            f"干扰样式合成失败（style={canonical!r}）: {exc}"
        ) from exc
    jam_bw_hz = _check_bandwidth(canonical, meta, scenario)
    bandwidth_skip_note = (
        None if scenario.get("victim_bw_hz") is not None else "victim_bw_hz 缺失，带宽校验跳过"
    )
    append_event(
        run_dir,
        {
            "type": "protocol_start",
            "style": meta.get("style", canonical),
            "victim_bw_hz": scenario.get("victim_bw_hz"),
            "jam_bw_hz": jam_bw_hz,
            "link_power_db": float(link_power_db),
            "n_samples": meta.get("n_samples"),
        },
    )

    # ---------- ② 基线窗口：record_run_streams 无干扰采集→run_baseline_check ----------
    baseline_samples = _positive_int(
        scenario.get("baseline_samples", _DEFAULT_BASELINE_SAMPLES),
        "scenario['baseline_samples']",
    )
    threshold_cfg = scenario.get("baseline")
    if not isinstance(threshold_cfg, dict):
        threshold_cfg = ctx.get("baseline") if isinstance(ctx.get("baseline"), dict) else None
    baseline_ctx = dict(ctx)
    baseline_ctx["scenario"] = scenario  # 直给 scenario 时共享给采集（信号电平等）
    baseline_ctx["record"] = False  # 基线段不录制（录制归 run_demo 采集阶段）
    baseline_ctx["stop"] = None  # 不继承调用方停检凭据
    baseline_ctx["jam_events"] = []  # 无干扰窗口：jam 事件流空（口径见证）
    if isinstance(ctx.get("dut"), dict) and ctx["dut"].get("source") == "sim":
        dedicated = ctx.get("baseline_sim_events")
        if dedicated is None:
            dedicated = ctx["dut"].get("baseline_events")
        if dedicated is None:
            dedicated = _baseline_sim_events(ctx["dut"], scenario, baseline_samples)
        baseline_ctx["sim_events"] = dedicated
    record_run_streams(baseline_ctx, max_kpi_rows=baseline_samples)
    baseline = run_baseline_check(_baseline_rows(run_dir), threshold_cfg)
    append_event(
        run_dir,
        {
            "type": "baseline",
            "passed": baseline["passed"],
            "per_mean": baseline["per_mean"],
            "n_judged": baseline["n_judged"],
            "stop_reason": baseline["stop_reason"],
        },
    )
    if not baseline["passed"]:
        # 不放行→中止（不抛——退出码语义归调用方）；未起发射无需停发射。
        append_event(
            run_dir,
            {
                "type": "protocol_stop",
                "status": "baseline_rejected",
                "stopped_at": None,
                "steps_executed": 0,
            },
        )
        return {
            "status": "baseline_rejected",
            "plan": None,
            "failure_levels": [],
            "steps_executed": 0,
            "baseline": baseline,
            "stopped_at": None,
            "note": (
                f"baseline_rejected: {baseline['stop_reason']}"
                f"（{baseline['advice']}）"
            ),
        }

    # ---------- ③ 阶梯：判据路自管 DUT 采集，start_tx 起发射→run_power_ladder ----------
    threshold = scenario.get(
        "per_threshold", scenario.get("failure_threshold", _DEFAULT_PER_THRESHOLD)
    )
    check_failure({"per": None}, threshold)  # 阈值域预检（发射前拒绝）
    # B13 复审低#2：判据窗样本数两级回落 scenario > ctx > 缺省（同 dwell_s）。
    min_samples_value = scenario.get("judge_min_samples")
    if min_samples_value is None:
        min_samples_value = ctx.get("judge_min_samples")
    if min_samples_value is None:
        min_samples_value = _DEFAULT_JUDGE_MIN_SAMPLES
    min_samples = _positive_int(
        min_samples_value, "scenario/ctx['judge_min_samples']"
    )
    dut_iter, source = _open_dut_source(ctx, scenario)

    start_tx = getattr(backend, "start_tx", None) if backend is not None else None
    if callable(start_tx):
        try:
            start_tx([iq])  # 干扰波形装载发射（功率由 ladder 衰减档调制）
        except BaseException as exc:  # noqa: BLE001 - 先停发射再透传（含信号族）
            stop_transmit_safely(
                backend,
                context={
                    "origin": "execute_gb42590_protocol",
                    "reason": "start_tx_error",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                run_token=ctx.get("run_token"),
            )
            raise

    state = {
        "dut_iter": dut_iter,
        "source": source,
        "min_samples": min_samples,
        "threshold": threshold,
        "failure": None,
    }
    ladder_params = (
        scenario.get("ladder") if isinstance(scenario.get("ladder"), dict) else None
    )
    # B13 复审低#2：档间停留两级回落 scenario > ctx > 缺省（域校验归
    # run_power_ladder 发射前拒绝：负/bool/NaN/±inf → ValueError）。
    dwell_s = scenario.get("dwell_s")
    if dwell_s is None:
        dwell_s = ctx.get("dwell_s")
    if dwell_s is None:
        dwell_s = _DEFAULT_DWELL_S
    # ladder 收尾（失效/走完/异常）均自停发射；判据回调异常同走先停发射再透传。
    try:
        ladder = run_power_ladder(
            ctx,
            ladder_params,
            failure_cb=_make_failure_cb(state),
            dwell_s=dwell_s,
            link_power_db=link_power_db,
        )
    except BaseException as exc:  # noqa: BLE001 - 透传前尽力补 aborted 终止事件
        # B13 复审低#3：判据回调/阶梯异常透传路径补 protocol_stop（status=
        # 'aborted'，error 摘要）尽力落盘——append_event 失败不再二次抛（原异常
        # 透传优先；停发射已由 ladder 内部「先停发射再透传」完成）。
        try:
            append_event(
                run_dir,
                {
                    "type": "protocol_stop",
                    "status": "aborted",
                    "stopped_at": None,
                    "steps_executed": None,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
        except Exception:  # noqa: BLE001 - 落盘尽力而为：绝不掩盖原异常
            pass
        raise

    # ---------- ④ 失效登记（P_crit）——发射已由 ladder 收尾停止 ----------
    failure_levels: list[dict] = []
    if ladder["reason"] == "failure" and state["failure"] is not None:
        entry = _record_failure_entry(state, ctx, scenario, canonical)
        failure_levels.append(entry)
        append_event(run_dir, {"type": "failure_level", **entry})

    # ---------- ⑤ 汇总 ----------
    reason = ladder["reason"]
    stopped_at = ladder["stopped_at"]
    steps_executed = len(ladder["executed"])
    if reason == "failure":
        status = "failed"
        note = (
            f"ladder failure: 判据于第 {stopped_at} 档触发"
            f"（stopped_at={stopped_at}），失效电平已登记 P_crit"
        )
    else:
        status = "completed"
        note = _COMPLETED_NOTES.get(
            reason, f"ladder {reason}: 判据未触发（未失效）"
        )
    if bandwidth_skip_note is not None:
        note = f"{note}；{bandwidth_skip_note}"
    append_event(
        run_dir,
        {
            "type": "protocol_stop",
            "status": status,
            "stopped_at": stopped_at,
            "steps_executed": steps_executed,
        },
    )
    return {
        "status": status,
        "plan": ladder["plan"],
        "failure_levels": failure_levels,
        "steps_executed": steps_executed,
        "baseline": baseline,
        "stopped_at": stopped_at,
        "note": note,
    }
