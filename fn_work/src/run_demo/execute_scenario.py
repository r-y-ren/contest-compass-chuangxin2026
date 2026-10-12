"""单场景执行阶段分派器：按 scenario_type 编排各功能块——重写规约与签名意图详见 fn_docs/responsibility.md R44。

调用方：run_demo（manage_run 内执行阶段）；serve_console（启动运行——runner 经
deps 注入本函数）。产出统一运行结果对象 {'status','result','streams_note'} 供
报告（build_report）与台账消费。

分派口径（scenario['scenario_type']，strip().lower() 归一）：
- 'gb42590'  → execute_gb42590_protocol(ctx, scenario) 透传结果（国标测法编排：
  样式合成+带宽校验→基线窗口→功率阶梯→P_crit 登记，全序在其内部）；
- 'distance'（距离演变，R13）→ map_distance_to_loss 只产计划 → 逐可达档
  set_channel_attenuation 下发衰减 + KPI 采集窗口（复用 drive/sim 拉 DUT 样本——
  简化口径：每档拉 judge_min_samples 个样本经 normalize_kpi 归一）→ 结果
  {'status','distance_plan','kpi_rows'}；不可达点（含负损耗）按 map 口径容忍
  跳过不抛（distance_plan.unreachable_count 如实计数）；
- 'custom'（自定义梯度）→ run_power_ladder（failure_cb 判据接线同 gb 口径：
  每档拉 judge_min_samples 个样本→聚合 compute_per→check_failure；判据工厂/
  DUT 源打开复用 execute_gb42590_protocol 的私有助手，保证两路判据逐字一致）；
- 'emc'（EMC 场景演示）→ run_emc_sweep(ctx, scenario) 透传（模拟接收机步进
  扫频，全程 simulated）；
- 其余（含缺键/非 str）→ ScenarioError（本文件定义的 ValueError 子类，发射前）。

两级回落（scenario > ctx > 缺省，与 gb 口径一致）：'judge_min_samples'（每档
判据/KPI 窗样本数，缺省 10）、'dwell_s'（custom 档间停留，缺省 1.0）。

统一返回：{'status': 外层状态（gb/distance 取内层 'status'；custom 按 ladder
reason 'failure'→'failed' 否则 'completed'；emc 恒 'completed'）, 'result':
各编排结果原对象透传（不拷贝不改写）, 'streams_note': 三路采集分工注记
（record_run_streams 的监测/录制归 run_demo 采集阶段另行执行——本阶段各编排
自管判据路 KPI；gb 路基线窗口亦在协议编排内部经 record_run_streams 采集）}。

错误契约：ScenarioError——ctx 非 dict / scenario 缺失（参数直给与 ctx['scenario']
两路皆缺）或非 dict / scenario_type 缺失、非 str 或未知（发射前，不涉及停发射）；
distance 的 distances/model_params 形状错经 map_distance_to_loss 的 ValueError
透传（ScenarioError 亦 ValueError 子类，调用方 except ValueError 口径兼容）。
其余下游异常（ProtocolError/LinkError/BackendError/AttenuationError/
EventWriteError/SweepError/ValueError 族等）原样透传不吞不换——各编排函数
自带「先停发射再透传」语义（run_power_ladder 收尾/异常路径自停发射；gb 协议
编排同口径），本分派器不另起发射也就不补停发射。
"""
from __future__ import annotations

from src.execute_gb42590_protocol.check_failure import check_failure
from src.execute_gb42590_protocol.execute_gb42590_protocol import (
    _DEFAULT_DWELL_S,
    _DEFAULT_JUDGE_MIN_SAMPLES,
    _DEFAULT_PER_THRESHOLD,
    _make_failure_cb,
    _open_dut_source,
    execute_gb42590_protocol,
)
from src.map_distance_to_loss.map_distance_to_loss import map_distance_to_loss
from src.normalize_kpi.normalize_kpi import normalize_kpi
from src.record_run_streams.record_run_streams import record_run_streams
from src.run_baseline_check.run_baseline_check import run_baseline_check
from src.run_emc_sweep.run_emc_sweep import run_emc_sweep
from src.run_power_ladder.run_power_ladder import run_power_ladder
from src.set_channel_attenuation.set_channel_attenuation import set_channel_attenuation

#: record_run_streams / run_baseline_check 随 gb 路径在
#: execute_gb42590_protocol 内部生效；重导出供上游（run_demo 采集阶段/
#: serve_console）就地导入——与本分派器的 streams_note 分工口径一致。
__all__ = [
    "ScenarioError",
    "execute_scenario",
    "record_run_streams",
    "run_baseline_check",
]


class ScenarioError(ValueError):
    """场景分派域错误（ValueError 子类）：scenario_type 未知 / 场景与上下文形状错（发射前）。"""


#: 在册场景类型（dispatch 白名单，strip().lower() 归一后精确匹配）。
_SCENARIO_TYPES = ("gb42590", "distance", "custom", "emc")

#: kpi 行回填的 set_channel_attenuation 结果子集（溯源用：目标/实达/残差/下发态）。
_ATTENUATION_KEYS = ("target_db", "achieved_db", "residual_db", "applied")


def _positive_int(value: object, name: str) -> int:
    """正整数校验（bool 排除），非法抛 ScenarioError（分派形状错，发射前）。"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ScenarioError(f"{name} 须为正 int，收到 {value!r}")
    return value


def _two_level(scenario: dict, ctx: dict, key: str, default):
    """两级回落取键：scenario > ctx > 缺省（与 execute_gb42590_protocol 口径一致）。"""
    value = scenario.get(key)
    if value is None:
        value = ctx.get(key)
    return default if value is None else value


def _run_gb42590(ctx: dict, scenario: dict) -> dict:
    """GB 42590 §5.11 测法编排透传（基线→阶梯→P_crit 全序在协议编排内部）。"""
    return execute_gb42590_protocol(ctx, scenario)


def _run_distance(ctx: dict, scenario: dict) -> dict:
    """距离演变编排：map_distance_to_loss 产计划→逐可达档下发衰减+KPI 窗口归一。

    档位下发归 set_channel_attenuation（domain/cal_table 取自 model_params——
    与 map 计划同源，保证计划/下发一致；两者缺省 None 时下发回落
    ctx['attenuator_cal']，与 map 按标称计划略有差异属标定口径，事件如实记录）。
    不可达点跳过（不下发不采样——set_channel_attenuation 对超域目标抛
    AttenuationError，容忍语义在 map 层已消化）；DUT 样本源复用 gb 口径的
    _open_dut_source（sim→simulate_link_degradation；真链路→drive_esp32_link/
    drive_nrf24_link），每档拉 judge_min_samples 个样本经 normalize_kpi 归一
    （源耗尽如实计 n_samples，不补不造）。
    """
    distances = scenario.get("distances")
    model_params = scenario.get("model_params")
    plan = map_distance_to_loss(distances, model_params)  # ValueError 族透传
    domain = model_params.get("domain")
    cal_table = model_params.get("cal_table")
    min_samples = _positive_int(
        _two_level(scenario, ctx, "judge_min_samples", _DEFAULT_JUDGE_MIN_SAMPLES),
        "scenario/ctx['judge_min_samples']",
    )
    dut_iter, source = _open_dut_source(ctx, scenario)

    kpi_rows: list[dict] = []
    for point_index, point in enumerate(plan["points"]):
        if not point["reachable"]:
            continue  # 不可达点（含负损耗）：map 口径容忍，跳过不下发不采样
        attenuation = set_channel_attenuation(
            ctx, float(point["loss_db"]), domain=domain, cal_table=cal_table
        )
        pulled: list[dict] = []
        for _ in range(min_samples):
            try:
                pulled.append(next(dut_iter))
            except StopIteration:
                break
        rows = [normalize_kpi(sample, source) for sample in pulled]
        judged = [row["judge_per"] for row in rows if row.get("judge_per") is not None]
        rssi = [row["rssi_dbm"] for row in rows if row.get("rssi_dbm") is not None]
        kpi_rows.append(
            {
                "step": len(kpi_rows),
                "point_index": point_index,
                "d_m": point["d_m"],
                "loss_db": point["loss_db"],
                "combo": point["combo"],
                "attenuation": {key: attenuation.get(key) for key in _ATTENUATION_KEYS},
                "n_samples": len(pulled),
                "judge_per_mean": (sum(judged) / len(judged)) if judged else None,
                "rssi_dbm_mean": (sum(rssi) / len(rssi)) if rssi else None,
            }
        )
    return {"status": "completed", "distance_plan": plan, "kpi_rows": kpi_rows}


def _run_custom(ctx: dict, scenario: dict) -> dict:
    """自定义梯度编排：判据接线同 gb 口径的 run_power_ladder（结果原样透传）。

    判据工厂/DUT 源打开复用 execute_gb42590_protocol 私有助手（_open_dut_source
    + _make_failure_cb），与 gb 路判据逐字一致：每档拉 judge_min_samples 个
    样本→聚合 compute_per→check_failure（EN 300 328 口径，阈值
    scenario['per_threshold'] 缺省 0.10；发射前经 check_failure 预检拒绝坏阈值）。
    ladder 自管衰减下发/事件/收尾停发射（含异常路径「先停发射再透传」）。
    """
    ladder_params = (
        scenario.get("ladder") if isinstance(scenario.get("ladder"), dict) else None
    )
    dwell_s = _two_level(scenario, ctx, "dwell_s", _DEFAULT_DWELL_S)
    min_samples = _positive_int(
        _two_level(scenario, ctx, "judge_min_samples", _DEFAULT_JUDGE_MIN_SAMPLES),
        "scenario/ctx['judge_min_samples']",
    )
    threshold = scenario.get(
        "per_threshold", scenario.get("failure_threshold", _DEFAULT_PER_THRESHOLD)
    )
    check_failure({"per": None}, threshold)  # 阈值域预检（发射前拒绝，ValueError 透传）
    dut_iter, source = _open_dut_source(ctx, scenario)
    state = {
        "dut_iter": dut_iter,
        "source": source,
        "min_samples": min_samples,
        "threshold": threshold,
        "failure": None,
    }
    return run_power_ladder(
        ctx,
        ladder_params,
        failure_cb=_make_failure_cb(state),
        dwell_s=dwell_s,
        link_power_db=ctx.get("link_power_db", 0.0),
    )


def _run_emc(ctx: dict, scenario: dict) -> dict:
    """EMC 场景演示透传：run_emc_sweep(ctx, scenario)（模拟接收机步进扫频）。"""
    return run_emc_sweep(ctx, scenario)


_DISPATCHERS = {
    "gb42590": _run_gb42590,
    "distance": _run_distance,
    "custom": _run_custom,
    "emc": _run_emc,
}

#: streams_note 基注（三路采集分工：record_run_streams 监测/录制归 run_demo
#: 采集阶段；本阶段各编排自管判据路 KPI）。
_STREAMS_NOTES = {
    "gb42590": (
        "gb42590: 判据路 KPI 与基线窗口由协议编排自管采集"
        "（基线经 record_run_streams 无干扰窗）；监测/录制三路（record_run_streams）"
        "归 run_demo 采集阶段另行执行"
    ),
    "distance": (
        "distance: 距离档 KPI 窗口本阶段逐档自管拉取（每档 judge_min_samples 个"
        "样本归一）；监测/录制三路（record_run_streams）归 run_demo 采集阶段另行执行"
    ),
    "custom": (
        "custom: 判据路 KPI 窗口同 GB 口径自管（failure_cb 逐档拉样归一）；"
        "监测/录制三路（record_run_streams）归 run_demo 采集阶段另行执行"
    ),
    "emc": (
        "emc: 模拟接收机步进扫频（run_emc_sweep），本阶段无 DUT 链路流采集；"
        "监测/录制三路（record_run_streams）归 run_demo 采集阶段另行执行"
    ),
}


def _outer_status(scenario_type: str, result: dict) -> str:
    """外层状态归一：gb/distance 取内层 'status'；custom 按 ladder reason；emc 恒完成。"""
    if scenario_type in ("gb42590", "distance"):
        return result["status"]
    if scenario_type == "custom":
        return "failed" if result.get("reason") == "failure" else "completed"
    return "completed"


def _streams_note(scenario_type: str, result: dict) -> str:
    """streams_note 组装：分工基注 + 各编排结果的量化摘要（人读溯源）。"""
    note = _STREAMS_NOTES[scenario_type]
    if scenario_type == "gb42590":
        return f"{note}；协议 status={result.get('status')}"
    if scenario_type == "distance":
        plan = result.get("distance_plan") or {}
        return (
            f"{note}；{len(result.get('kpi_rows', []))} 档执行、"
            f"{plan.get('unreachable_count', 0)} 点不可达跳过"
        )
    if scenario_type == "custom":
        return f"{note}；ladder reason={result.get('reason')}"
    return note


def execute_scenario(ctx: dict, scenario: dict | None = None) -> dict:
    """单场景执行阶段编排（按场景类型分派各功能块）——统一结果供报告与台账消费。

    输入:
        ctx: 运行上下文（manage_run 组装）——'run_dir'（事件/KPI 落盘目录）、
            'backend'（发射/衰减后端）、'scenario'（scenario 参数缺省回落）、
            'dut'（判据路 DUT 源配置：source='sim' 用 ctx['sim_events']/
            dut['events']；'esp32'/'nrf24' 用 dut['serial_config']）、
            'link_power_db'（阶梯基准）、可选 'jam_events'/'judge_min_samples'/
            'dwell_s'/'attenuator_cal' 等（两级回落与标定口径见各编排）；
        scenario: 场景 dict（None=取 ctx['scenario']）——'scenario_type' 必填
            （'gb42590'|'distance'|'custom'|'emc'）；distance 另需 'distances'
            （距离序列）与 'model_params'（map_distance_to_loss 参数，含可选
            domain/cal_table）；custom 另可给 'ladder'（start_db/step_db/
            stop_db/max_steps）、'dwell_s'、'per_threshold'。

    输出:
        {'status': 'completed'|'failed'|'baseline_rejected'（gb 透传）,
        'result': 各编排结果原对象（gb 汇总 / distance {'status','distance_plan',
        'kpi_rows'} / ladder 返回 / emc 扫频汇总）, 'streams_note': 三路采集
        分工注记（含各路量化摘要）}。

    错误:
        ScenarioError: ctx 非 dict；scenario 两路皆缺或非 dict；scenario_type
            缺失/非 str/未知（均发射前）。
        其余下游异常（ProtocolError/SweepError/AttenuationError/EventWriteError/
        LinkError/ValueError 族等）按各编排函数「先停发射再透传」语义原样透传。
    """
    if not isinstance(ctx, dict):
        raise ScenarioError(f"ctx 必须为 dict（manage_run 组装），收到 {type(ctx).__name__}")
    if scenario is None:
        scenario = ctx.get("scenario")
    if not isinstance(scenario, dict):
        raise ScenarioError(
            f"scenario 缺失或非 dict（参数直给或 ctx['scenario']），收到 {scenario!r}"
        )
    raw_type = scenario.get("scenario_type")
    if not isinstance(raw_type, str) or not raw_type.strip():
        raise ScenarioError(
            f"scenario 须提供 'scenario_type'（{list(_SCENARIO_TYPES)}），收到 {raw_type!r}"
        )
    scenario_type = raw_type.strip().lower()
    if scenario_type not in _DISPATCHERS:
        raise ScenarioError(
            f"未知 scenario_type {raw_type!r}（在册: {list(_SCENARIO_TYPES)}）"
        )
    result = _DISPATCHERS[scenario_type](ctx, scenario)
    return {
        "status": _outer_status(scenario_type, result),
        "result": result,
        "streams_note": _streams_note(scenario_type, result),
    }
