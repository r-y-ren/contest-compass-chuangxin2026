"""EMC 三流程演示（传导/辐射/扫频）：参数表单→经操控台 runner 发起→图谱段+强制
模拟口径声明上屏——重写规约与签名意图详见 fn_docs/responsibility.md（R68
demo_emc_flows L0；调用方 mount_console_extensions）。

落地口径（R68）：

- 三流程网页可达：flow ∈ {'conduction','radiation','sweep'}（strip().lower()
  归一，未知值 ValueError）；params dict 仅做**覆盖**——本函数按流程构造
  **完整场景**（走查环 F1 修复，2026-10-14：缺省 {} 也能真跑）：
  scenario = {**_COMMON_DEFAULTS, **_FLOW_DEFAULTS[flow], **params,
  'scenario_type': 'emc', 'emc_flow': flow}（B28 对抗低2→B29 随批①收紧：
  端点保留字 scenario_type/emc_flow 后置——params 携带同名键不再劫持流程
  分派），完整缺省过 validate/guard 红线（style=bandlimited_noise+fs+
  bandwidth_hz+bands 2.4G+双声明+功率合规），EMC 流程键（emc_flow/span_hz
  等 schema 不在册键）经 run_demo._normalize_scenario_object 的 EMC 信封
  摘出通路落位；经 runner（操控台 /api/run 同款后台执行器，scenario
  dict→result dict）发起——缺省 runner 的全载荷分支（含非空 style）直走
  run_scenario 真跑，不再落"薄载荷缺 style 须携 name"分支；
- execute_scenario 的 emc 子类型分派（R68 快速通道改造点，块引言在册）按
  'emc_flow' 落到 run_emc_conduction_sim / run_emc_radiation_sim /
  run_emc_sweep——本函数不直接调编排器（演示运行走操控台运行目录/报告中心，
  与 /api/run 同一执行器与运行表）；
- 图谱段（chart）：从 runner 结果收割 EMC 负载后按流程形态归一——
  conduction → readings（freq_hz/power_dbuv/margin_db）、radiation →
  spectrum（freq_hz/power_db）、sweep → points（freq_hz/power_dbm/spurious）；
  负载收割三通道（按序）：result['emc_payload']（直给契约，测试/程序化复用）→
  result['result']（execute_scenario 形态返回）→ result['run_dir']/result.json
  的 'scenario_result'（run_scenario 形态返回——操控台缺省 runner 的真跑落点，
  B21 中#2 就近补写口径）；三路皆无 → chart=None+如实标注（不虚构不抛）；
- 频率域越界裁剪并标注（沿用 R33–R35）：三个 sim 自带「越域裁剪到最近边界+
  warnings 标注」口径，本函数把负载 warnings 原样并入演示视图（裁剪标注不拒）；
- 强制模拟口径声明：输出恒带 simulated=True 与 make_disclaimer_block('emc')
  声明块——读数绝不冒充实测（与三个 sim 的自带 disclaimer 同源同文）。
"""
import json
import os

from src.shared.make_disclaimer_block import make_disclaimer_block

__all__ = ["EMC_FLOWS", "demo_emc_flows"]

#: 在册 EMC 流程（conduction 传导摸底 / radiation 辐射摸底 / sweep 步进扫频）。
EMC_FLOWS = ("conduction", "radiation", "sweep")

#: 各流程 EMC 负载的形态标记键（收割通道判形用——readings/spectrum/points）。
_PAYLOAD_MARKERS = {
    "conduction": ("readings",),
    "radiation": ("spectrum",),
    "sweep": ("points",),
}

#: 完整场景公共缺省（走查环 F1 修复）：过 validate/guard 红线的最小完整场景——
#: style=bandlimited_noise（EMC 干扰背景最贴切的带限噪声，bandwidth_hz 必填随给）、
#: fs/功率/时长给合规域内值、bands=2.4G 法定频段+双声明（guard 三查绿灯）、
#: backend=sim（全程模拟口径）；freq_hz 缺省 2.4G（sim 后端频率域 [70MHz, 6GHz]
#: 内的合法载频——conduction 流程按需覆写为域内测点频）。
_COMMON_DEFAULTS = {
    "style": "bandlimited_noise",
    "fs": 10.0e6,
    "bandwidth_hz": 2.0e6,
    "freq_hz": 2.4e9,
    "power_dbm": -20.0,
    "duration_s": 0.01,
    "backend": "sim",
    "bands": [[2400.0, 2483.5]],
    "shielded_box": True,
    "dut_scope": "self_built",
}

#: 各流程测量缺省（三 sim 实际消费键的最小集——params 仅做覆盖）：
#: - conduction：freq_hz（测点频——100MHz 在 sim 后端域与 CISPR 传导段交叠内）
#:   + limit_line_dbmv（全点同限标量）；
#: - radiation：center_hz/span_hz（两必需键，SpanRsa513a 分析窗）；
#: - sweep：band（CISPR 频段便捷参数，无需 start/stop）+ step_hz。
_FLOW_DEFAULTS = {
    "conduction": {"freq_hz": 100.0e6, "limit_line_dbmv": 60.0},
    "radiation": {"center_hz": 100.0e6, "span_hz": 1.0e6},
    "sweep": {"band": "cispr_b", "step_hz": 5.0e6},
}

#: 演示视图的诚实基注（超模型域/模拟口径总口径——与 R39–R43 家族口径一致）。
_SIM_NOTE = (
    "EMC 三流程演示为模拟后端读数（simulated），非 CISPR 16-1-1 测量接收机实测值；"
    "频率域越界点按 R33–R35 口径裁剪并标注（warnings 原文上屏），不拒跑"
)


def _normalize_flow(flow: object) -> str:
    """flow 归一：strip().lower() 后须落在 EMC_FLOWS，未知/非 str → ValueError。"""
    if not isinstance(flow, str) or flow.strip().lower() not in EMC_FLOWS:
        raise ValueError(
            f"flow 必须为 {list(EMC_FLOWS)} 之一（EMC 演示流程类型，大小写不敏感），"
            f"实际: {flow!r}"
        )
    return flow.strip().lower()


def _is_payload(flow: str, candidate: object) -> bool:
    """EMC 负载判形：dict 且携带该流程的形态标记键（readings/spectrum/points）。"""
    return isinstance(candidate, dict) and any(
        key in candidate for key in _PAYLOAD_MARKERS[flow]
    )


def _harvest_payload(flow: str, result: dict):
    """runner 结果 → EMC 负载收割（三通道按序，皆无 → None 如实标注不虚构）。

    ① result['emc_payload']——直给契约（测试/程序化复用通道）；
    ② result['result']——execute_scenario 形态（{'status','result','streams_note'}，
       内层即 sim 编排结果）；
    ③ result['run_dir'] 下 result.json 的 'scenario_result'——run_scenario 形态
       （操控台缺省 runner 真跑后 manage_run 就近补写，B21 中#2 口径）；
    读盘失败/键缺/形态不符一律回落 None（演示态继续，不抛不虚构）。
    """
    direct = result.get("emc_payload")
    if _is_payload(flow, direct):
        return direct
    nested = result.get("result")
    if _is_payload(flow, nested):
        return nested
    run_dir = result.get("run_dir")
    if isinstance(run_dir, str) and run_dir.strip():
        try:
            with open(
                os.path.join(run_dir, "result.json"), encoding="utf-8"
            ) as handle:
                scenario_result = json.load(handle).get("scenario_result")
        except (OSError, ValueError):
            return None
        if isinstance(scenario_result, dict):
            inner = scenario_result.get("result")
            if _is_payload(flow, inner):
                return inner
    return None


def _chart_segment(flow: str, payload):
    """EMC 负载 → 图谱段（页区渲染口径：x/y 平行列表，None → None）。"""
    if not isinstance(payload, dict):
        return None
    if flow == "conduction":
        readings = payload.get("readings")
        if isinstance(readings, list) and readings:
            return {
                "kind": "conduction_readings",
                "freq_hz": [r.get("freq_hz") for r in readings],
                "power_dbuv": [r.get("power_dbuv") for r in readings],
                "margin_db": [r.get("margin_db") for r in readings],
            }
        return None
    if flow == "radiation":
        spectrum = payload.get("spectrum")
        if isinstance(spectrum, dict):
            return {
                "kind": "radiation_spectrum",
                "freq_hz": list(spectrum.get("freqs") or []),
                "power_db": list(spectrum.get("power_db") or []),
            }
        return None
    points = payload.get("points")
    if isinstance(points, list) and points:
        return {
            "kind": "sweep_points",
            "freq_hz": [p.get("freq_hz") for p in points],
            "power_dbm": [p.get("power_dbm") for p in points],
            "spurious": [bool(p.get("spurious")) for p in points],
        }
    return None


def demo_emc_flows(flow: str, params: dict, runner) -> dict:
    """EMC 三流程演示（传导/辐射/扫频）：表单参数→经操控台 runner 发起→图谱段+
    强制模拟口径声明（详见 fn_docs/responsibility.md 功能块）。

    输入:
        flow: EMC 流程类型——'conduction'（LISN 传导摸底）| 'radiation'（屏蔽
            环境辐射摸底）| 'sweep'（模拟接收机步进扫频）；大小写不敏感，
            未知值 ValueError（端点层转 400 上屏）。
        params: 流程参数 dict|None（**仅做覆盖**——本函数按流程先构造完整场景
            缺省（_COMMON_DEFAULTS+_FLOW_DEFAULTS：style=bandlimited_noise/
            fs/bands 2.4G/双声明/功率合规——走查环 F1 修复：缺省 {} 经操控台
            缺省 runner 真跑不再必败），params 同名键后置覆盖；保留字
            scenario_type/emc_flow 恒后置覆写，params 同名键不劫持流程分派
            （B29 随批①收紧）；conduction 常覆盖
            freq_hz/limit_line_dbmv/rbw_hz/detector；radiation 常覆盖 center_hz/
            span_hz/compensation_tables/peak_drop_db；sweep 常给 band 或
            start_hz/stop_hz/step_hz/scale/spurious_threshold_dbm）。
        runner: 操控台运行执行器 callable（scenario dict→result dict——/api/run
            的后台线程同款 deps['runner']；缺省装配为 serve_console 真实运行器，
            emc 场景经 run_scenario→execute_scenario 按 emc_flow 分派真跑）。

    输出:
        演示视图 dict：{'ok': True, 'flow', 'scenario': 发起场景（审计留痕）,
        'run': {'run_id','status','exit_code','run_dir'}（runner 结果运行学摘要）,
        'simulated': True, 'disclaimer': make_disclaimer_block('emc'),
        'chart': 图谱段（freq/power 平行列表；负载不可得 → None）, 'payload':
        sim 编排结果原对象（收割所得；None=未读到）, 'warnings': 裁剪/收割标注
        清单（sim warnings 原文并入）, 'note': 诚实基注}。

    错误:
        ValueError: flow 未知/params 非 dict|None/runner 不可调用/runner 返回
            非 dict（形状错先拒——端点层转 400 错误信息上屏）。
        其余 runner 内部异常（ScenarioError/SweepError/ValueError 族等）原样
        上抛（场景非法→校验错误上屏，不吞不换——端点后台线程落运行表）。
    """
    flow_key = _normalize_flow(flow)
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(
            f"params 必须为 dict | None（EMC 流程表单参数），实际 "
            f"{type(params).__name__}: {params!r}"
        )
    if not callable(runner):
        raise ValueError(
            f"runner 必须可调用（scenario dict→result dict，操控台 /api/run 同款"
            f" 执行器），实际: {runner!r}"
        )

    scenario = {
        **_COMMON_DEFAULTS,
        **_FLOW_DEFAULTS[flow_key],
        **params,
        "scenario_type": "emc",
        "emc_flow": flow_key,
    }
    result = runner(scenario)
    if not isinstance(result, dict):
        raise ValueError(
            f"runner 返回值必须为结果 dict（run_scenario 契约），实际 "
            f"{type(result).__name__}: {result!r}"
        )

    payload = _harvest_payload(flow_key, result)
    chart = _chart_segment(flow_key, payload)

    warnings: list = []
    if isinstance(payload, dict) and isinstance(payload.get("warnings"), list):
        warnings.extend(str(item) for item in payload["warnings"])
    notes = [_SIM_NOTE]
    if payload is None:
        notes.append(
            "未读到 EMC 结果负载（runner 结果无 emc_payload/result 形态键，且 "
            "run_dir/result.json 的 scenario_result 不可得）——chart=None，如实标注"
        )
    run_dir = result.get("run_dir")
    run_id = None
    if isinstance(run_dir, str) and run_dir.strip():
        run_id = os.path.basename(run_dir.rstrip(os.sep)) or None
    return {
        "ok": True,
        "flow": flow_key,
        "scenario": scenario,
        "run": {
            "run_id": run_id,
            "status": result.get("status"),
            "exit_code": result.get("exit_code"),
            "run_dir": run_dir if isinstance(run_dir, str) else None,
        },
        "simulated": True,
        "disclaimer": make_disclaimer_block("emc"),
        "chart": chart,
        "payload": payload,
        "warnings": warnings,
        "note": "；".join(notes),
    }
