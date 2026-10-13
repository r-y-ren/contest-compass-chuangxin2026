"""CLI 总入口：场景→后端→时钟→manage_run（执行+采集）→报告→溯源→台账，退出码 0/1/2——重写规约与签名意图详见 fn_docs/responsibility.md R44。

双入口共享同一执行管线（_execute_pipeline/_execute_stage，避免复制）：
- run_demo(argv)——CLI（文件/--demo 装载 + 退出码 + stdout 摘要行 + 台账缺省开）；
- run_scenario(scenario, *, backend, out_root, dwell_s, ledger, stop)——无头入口
  （收已解析场景 dict；validate→guard→normalize 同 load_scenario 三件套口径；
  一切入返回值 {'run_dir','status','report_path','exit_code','failure_levels',
  'summary'}，台账缺省不动）——网页操控台（serve_console 缺省 runner）与
  程序化复用由此进入，不打印不退出。

急停协作停（B24 C1，R59 规约「旗要终止编排」的兑现）：run_scenario 可选参数
stop=共享停容器 {'flag': bool, 'backend': …}——后端打开后管线把发射后端句柄写回
stop['backend']（急停方直停真后端的通道，docstring 见 run_scenario）；管线在
功率档间（sim 事件流逐事件检查）与阶段边界（运行启动/采集/报告前）协作检查
stop['flag']，置位即抛 EmergencyStopRequested 走既有「先停发射再退出」中止路径
（ladder/协议编排异常路径自停发射+manage_run 收尾铁律），run_scenario 归一
status='stopped'（exit_code=1 未完成口径）并在 events.jsonl 落 emergency_stop 事件。

编排链（一键命令串联主链，分阶段退出码；任何异常先停发射经 manage_run 收尾）：
① load_scenario（'--demo' 用内置 sim 场景）——LoadScenarioError → exit 2 摘要行；
② autodetect_backend（explicit 来自 --backend，缺省回落场景 'backend' 键，
  'auto'/缺省才探测）——BackendError → exit 1 附降级建议；
③ resolve_clock_reference（永不抛）——clock_ref 口径贯通报告脚注与 result.json；
④ manage_run 全生命周期，execute 回调内：ctx['set_state']('running') →
  execute_scenario（四类型分派：gb42590/distance/custom/emc——判据路 KPI 与
  gb 基线窗由各编排自管；distance 档 KPI 行/事件自管落盘）→ record_run_streams
  （监测/录制采集路——'record' 开关取场景键，缺省 False；其 'w' 重写 kpi.csv
  后 distance 档 KPI 行按结果对象重追加，B21 中#2）→ build_report →
  verify_report_traceability；execute 返回并入 ctx['result'] 并在收尾后就近
  补写 result.json 的 'scenario_result' 键（尽力而为，B21 中#2）；
⑤ 溯源失败不致 run 失败：'traceability' 结果附 run result（result.json 就近
  补写（尽力而为，排版同 finalize）+摘要行与 run.log 三处留痕），build_report
  失败口径=运行失败 exit 1（异常经 manage_run 先停发射收尾标 failed 后重抛）；
⑥ 台账：--no-ledger 缺省时，场景含 'ledger_entry' 键（如 'B1'）才调
  update_ledger（anchor=fn(run_demo) run:<目录名> status:<终态>；路径
  '--ledger' 覆盖 > 仓库根锚定缺省 DEFAULT_LEDGER_PATH——与运行 cwd 无关）；
  LedgerError/ValueError 只打警告不改变退出码；
⑦ 摘要行 stdout：run_dir/status（completed|failed）/失效数/报告路径/溯源
  passed/台账状态。

退出码：0=成功（manage_run 终态 done 且场景执行 status='completed'——判据
触发（'failed'）与 baseline_rejected 均计运行失败）；1=运行失败（BackendError/
RunDirError/execute 阶段任何异常（经 manage_run 停发射收尾后重抛）/场景执行
未完成）；2=校验失败（场景装载/CLI 参数域）。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from numbers import Real
from pathlib import Path

from src.autodetect_backend.autodetect_backend import autodetect_backend
from src.build_report.build_report import build_report
from src.guard_compliance.guard_compliance import guard_compliance
from src.load_scenario.load_scenario import _ENVELOPE_KEYS
from src.load_scenario.load_scenario import load_scenario
from src.load_scenario.load_scenario import ScenarioError as LoadScenarioError
from src.load_scenario.normalize_scenario import DEFAULT_POWER_DBM, normalize_scenario
from src.load_scenario.validate_scenario_schema import validate_scenario_schema
from src.manage_backend_registry.lookup_backend import BackendError
from src.manage_run.manage_run import RunDirError, manage_run
from src.resolve_clock_reference.resolve_clock_reference import resolve_clock_reference
from src.update_ledger.update_ledger import LedgerError, update_ledger
from src.verify_report_traceability.verify_report_traceability import (
    verify_report_traceability,
)

from src.shared.append_event import append_event

from .execute_scenario import append_distance_kpi_rows, execute_scenario, record_run_streams

__all__ = ["EmergencyStopRequested", "run_demo", "run_scenario"]


class EmergencyStopRequested(RuntimeError):
    """急停协作中止信号（B24 C1）：共享停容器 stop['flag'] 被置位后，管线在
    协作检查点（功率档间 sim 事件流逐事件/采集与报告等阶段边界）抛出——沿
    既有「先停发射再退出」中止路径传播（ladder/协议编排的异常路径自停发射，
    manage_run 收尾铁律再兜），run_scenario 捕获后归一 status='stopped'。"""


def _stop_requested(stop: object) -> bool:
    """协作停判定：stop 为 dict 且 'flag' 为真（None/非 dict 形状忽略，不抛）。"""
    return isinstance(stop, dict) and bool(stop.get("flag"))


def _raise_if_stopped(stop: object, where: str) -> None:
    """阶段边界协作检查（B24 C1）：停旗已置位即抛 EmergencyStopRequested——
    异常沿 manage_run 收尾路径先停发射再退出（发射侧静默由收尾铁律保证）。"""
    if _stop_requested(stop):
        raise EmergencyStopRequested(
            f"急停旗已置位（stop['flag']=True，{where}——协作中止）"
        )


def _stop_checked_events(events, stop: object):
    """sim 事件流的协作停包装（B24 C1 功率档间检查点）：逐事件产出前检查停旗，
    置位即抛 EmergencyStopRequested——判据窗每档拉样必经此流，异常沿
    ladder「先停发射再透传」路径接管中止（档间即时生效，不等阶梯走完）。

    覆盖口径（如实登记）：检查点=逐事件拉取；事件流耗尽后判据窗拉样得
    StopIteration（源耗尽如实计，属既有语义），档间检查随之不再触发——
    此后急停退化为下一阶段边界中止（结果仍 stopped，但等待阶梯走完）。
    缺省 _sim_events 产 10 事件 ≥ GB 缺省阶梯 6 档，常规场景全覆盖。"""
    for event in events:
        if _stop_requested(stop):
            raise EmergencyStopRequested(
                "急停旗已置位（stop['flag']=True，sim 事件流档间检查——协作中止）"
            )
        yield event

#: 退出码三态（R44 签名意图：校验失败=2；运行失败=1；均已停发射）。
EXIT_OK = 0
EXIT_RUN_FAILED = 1
EXIT_VALIDATION_FAILED = 2

#: 运行目录基础路径（相对 CWD；manage_run 自动创建，同秒冲突 -2/-3 去重）。
RUNS_ROOT = "runs"

#: 台账清单文件名（与 update_ledger.locate_ledger_row 缺省同源）。
_LEDGER_FILENAME = "全功能实现清单-技术支持版.md"

#: 默认台账路径：锚定仓库根（本文件 fn_work/src/run_demo/run_demo.py 的
#: parents[3] 即仓库根）——从 fn_work、仓库根或任意其他 cwd 运行都指向同一份
#: 清单（修复前 update_ledger 缺省 'docs/…' 为 cwd 相对路径，离开仓库根就
#: 找不到台账）；CLI '--ledger' 可显式覆盖透传 update_ledger(ledger_path=…)。
DEFAULT_LEDGER_PATH = str(
    Path(__file__).resolve().parents[3] / "docs" / _LEDGER_FILENAME
)

#: BackendError 统一降级建议（与 autodetect_backend 文案同口径，不重复附）。
_FALLBACK_ADVICE = "可改用 --backend sim 降级"

#: 监测路缺省目标频段（MHz，2.4G 法定频段；场景 'bands' 首对优先）。
_DEFAULT_MONITOR_BAND_MHZ = (2400.0, 2483.5)

#: 内置 --demo 快路径参数（判据演示：阶梯档位驱动 JSR 爬升过悬崖）。
_DEMO_N_EVENTS = 10
#: sim 事件缺省兜底 JSR（悬崖左远端，'sim_events' 缺失时 _sim_events 生成）。
_DEMO_JSR_DB = -20.0
#: 被测链路发射功率（阶梯基准：link−5 起、5dB 步）与判据路信号电平同值
#: （jsr=档位绝对电平−信号电平 → 0dBm 顶档 jsr=+20 → per≈1，悬崖右翼）。
_DEMO_LINK_POWER_DB = -20.0
_DEMO_SIGNAL_POWER_DB = -20.0
#: 判据窗样本数与每事件样本数对齐（2=2）：1 个 sim 事件恰供 1 个档位判据窗
#: （事件与阶梯档位一一对应，不跨档混窗）。
_DEMO_JUDGE_MIN_SAMPLES = 2
_DEMO_SAMPLES_PER_EVENT = 2
#: GB 缺省阶梯口径（与 plan_ladder_steps 缺省一致：link−5 起、5dB 步、0dBm 红线）。
_DEMO_LADDER_START_OFFSET_DB = -5.0
_DEMO_LADDER_STEP_DB = 5.0
_DEMO_LADDER_REDLINE_DB = 0.0


def _demo_ladder_levels_db() -> list:
    """内置 demo 的 GB 阶梯档位表（link−5 起、5dB 步、0dBm 红线内）。

    与 plan_ladder_steps(link_power_db, None) 缺省计划同口径——demo 的 sim
    事件按此表逐档携带绝对干扰电平（achieved_db），判据窗 JSR 随档位爬升。
    """
    levels: list[float] = []
    level = _DEMO_LINK_POWER_DB + _DEMO_LADDER_START_OFFSET_DB
    while level <= _DEMO_LADDER_REDLINE_DB:
        levels.append(float(level))
        level += _DEMO_LADDER_STEP_DB
    return levels


def _demo_scenario() -> dict:
    """内置 '--demo' 完整样例场景：tone / sim / gb42590（快路径 <5s）。

    与 load_scenario 规范化输出同形状（场景字段+红线信封键），另携执行信封
    （scenario_type/judge_min_samples/dwell_s/baseline_samples/record/sim_events/
    dut——内置场景不经文件装载，不受 schema 未知键约束）；judge_min_samples=2、
    dwell_s=0、baseline_samples=10 保证全流程秒级完成。

    判据演示口径（修复「--demo 永不失效」）：sim 事件不再直给恒定 jsr_db=−20
    （悬崖左远端，窗口 PER 恒 0），改为按 GB 阶梯档位携带**绝对干扰电平**
    （achieved_db=−25…0 dBm），signal_power_db=−20 与链路功率同值 → JSR=
    档位−信号随档爬升（−25dBm 档 jsr=−5 … 0dBm 档 jsr=+20，悬崖阈值 10dB
    右翼 per→≈1）；samples_per_event 与 judge_min_samples 对齐（1 事件=1 档窗）。
    判据于第 3 档（index 2，−15dBm，jsr=+5）触发：per_model≈0.085 → err=1/
    样本 → 窗 per=2/20=0.10 恰达阈值（EN 300 328 ≥ 口径判失效，阈值缺省
    0.10 与 judge_per_threshold 声明同值）——status='failed'、failure_levels=1、
    stopped_at=2（中段档，0dBm 顶档未及执行）→ exit 1（判据真触发+失效电平登记）。
    """
    sim_events = [
        {"type": "power_step", "achieved_db": level, "ts": float(index)}
        for index, level in enumerate(_demo_ladder_levels_db())
    ]
    return {
        # ---- 场景字段（normalize_scenario 键序） ----
        "style": "tone",
        "fs": 1.0e6,
        "freq_hz": 2.4e9,
        "power_dbm": -10.0,
        "duration_s": 0.005,
        "backend": "sim",
        "judge_per_threshold": 0.10,
        # ---- 执行信封（内置场景直携） ----
        "scenario_type": "gb42590",
        "judge_min_samples": _DEMO_JUDGE_MIN_SAMPLES,
        "dwell_s": 0.0,
        "baseline_samples": 10,
        "signal_power_db": _DEMO_SIGNAL_POWER_DB,
        "link_power_db": _DEMO_LINK_POWER_DB,
        "record": False,
        "sim_events": sim_events,
        "dut": {"source": "sim", "samples_per_event": _DEMO_SAMPLES_PER_EVENT},
        # ---- 红线信封（guard 口径同形状：band/声明键在位） ----
        "bands": [[2400.0, 2483.5]],
        "shielded_box": True,
        "dut_scope": "self_built",
    }


def _build_parser() -> argparse.ArgumentParser:
    """CLI 参数：[场景路径 | --demo] 恰其一 + --backend/--dwell/--ledger/--no-ledger。"""
    parser = argparse.ArgumentParser(
        prog="run_demo",
        description=(
            "一键命令编排器：场景装载→后端决策→时基→运行（执行+采集）→报告→"
            "溯源→台账；退出码 0=成功/1=运行失败/2=校验失败。"
        ),
    )
    parser.add_argument(
        "scenario_path",
        nargs="?",
        default=None,
        help="场景 YAML 文件路径（或改用 --demo 内置 sim 场景，恰给其一）",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="使用内置 tone/sim/gb42590 完整样例（judge 2/dwell 0/baseline 10 快路径；"
        "阶梯档位驱动 JSR 爬升，中段档判据触发 → exit 1 演示失效电平登记）",
    )
    parser.add_argument(
        "--backend",
        default=None,
        help="显式后端名（sim/b210/replay）；缺省回落场景 'backend' 键，'auto' 才探测",
    )
    parser.add_argument(
        "--dwell",
        type=float,
        default=None,
        help="档间停留秒（CLI 覆盖：写入 scenario['dwell_s']，两级回落最高层）",
    )
    parser.add_argument(
        "--ledger",
        default=None,
        help="台账 md 路径覆盖（缺省锚定仓库根 docs/全功能实现清单-技术支持版.md，"
        "与运行 cwd 无关）",
    )
    parser.add_argument(
        "--no-ledger",
        action="store_true",
        help="跳过台账更新（缺省在场景含 ledger_entry 键时更新）",
    )
    return parser


def _err(message: str) -> None:
    """失败摘要行 → stderr（成功摘要行走 stdout，见 _summary）。"""
    print(f"run_demo: {message}", file=sys.stderr)


def _is_finite_nonneg_seconds(value: object) -> bool:
    """--dwell 域校验：非 bool 有限实数且非负（负 dwell 发射前才拒，CLI 早拒）。"""
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _explicit_backend_name(name: str | None, scenario: dict) -> str | None:
    """显式后端名决策：显式名（CLI --backend / run_scenario backend 参数）>
    场景 'backend'（'auto'/空/非 str → None 探测）。"""
    if name is not None:
        stripped = name.strip() if isinstance(name, str) else name
        return stripped if stripped else None
    from_scenario = scenario.get("backend")
    if (
        isinstance(from_scenario, str)
        and from_scenario.strip()
        and from_scenario.strip().lower() != "auto"
    ):
        return from_scenario.strip()
    return None


def _backend_params(scenario: dict) -> dict:
    """后端打开参数：场景 freq_hz 为正有限实数时透传（sim 域校验归后端工厂）。"""
    freq = scenario.get("freq_hz")
    if (
        isinstance(freq, Real)
        and not isinstance(freq, bool)
        and math.isfinite(float(freq))
        and float(freq) > 0.0
    ):
        return {"freq_hz": float(freq)}
    return {}


def _sim_events(scenario: dict) -> list:
    """sim 注入事件源：场景 'sim_events' 直给，缺省生成 10 事件（jsr=-20 不失效）。"""
    given = scenario.get("sim_events")
    if isinstance(given, list) and given:
        return given
    return [
        {"type": "power_step", "jsr_db": _DEMO_JSR_DB, "ts": float(index)}
        for index in range(_DEMO_N_EVENTS)
    ]


def _monitor_params(scenario: dict) -> dict:
    """监测路采集参数：场景 'monitor' 直给（平铺或 {'params': …} 均收），缺省
    target_band 取场景 'bands' 首对（不合法回落 2.4G 法定频段）。"""
    given = scenario.get("monitor")
    if isinstance(given, dict):
        nested = given.get("params")
        return nested if isinstance(nested, dict) else given
    band = None
    bands = scenario.get("bands")
    if isinstance(bands, (list, tuple)) and bands:
        first = bands[0]
        if isinstance(first, (list, tuple)) and len(first) == 2:
            lo, hi = first[0], first[1]
            if (
                isinstance(lo, Real)
                and isinstance(hi, Real)
                and not isinstance(lo, bool)
                and not isinstance(hi, bool)
                and float(lo) < float(hi)
            ):
                band = (float(lo), float(hi))
    if band is None:
        band = _DEFAULT_MONITOR_BAND_MHZ
    return {"target_band": band}


def _failure_levels(execute_result: dict) -> list:
    """失效电平条目数：gb 路内层 result['failure_levels']（其余类型空）。"""
    inner = execute_result.get("result") if isinstance(execute_result, dict) else None
    if isinstance(inner, dict) and isinstance(inner.get("failure_levels"), list):
        return inner["failure_levels"]
    return []


def _report_payload(
    run_dir: str, run_out: dict, scenario: dict, selection: dict, clock_ref: str
) -> dict:
    """报告结果对象（数字纪律：全部读回自本 run 结果对象/选择记录）：
    run_id/backend/clock_ref（脚注与概要）、failure_levels（失效对比段）、
    emc 场景扫频结果适配 'emc' 段形状（readings←points，如实不虚构）、
    sim 后端附 simulated_parts（脚注模拟段声明）。"""
    inner = run_out.get("result") if isinstance(run_out.get("result"), dict) else {}
    payload = {
        "run_id": os.path.basename(run_dir.rstrip(os.sep)) or run_dir,
        "backend": selection.get("backend") if isinstance(selection, dict) else None,
        "clock_ref": clock_ref,
        "failure_levels": _failure_levels(run_out),
    }
    scenario_type = scenario.get("scenario_type")
    if (
        isinstance(scenario_type, str)
        and scenario_type.strip().lower() == "emc"
        and isinstance(inner, dict)
        and "points" in inner
    ):
        payload["emc"] = {**inner, "readings": inner.get("points")}
    if isinstance(selection, dict) and selection.get("backend") == "sim":
        payload["simulated_parts"] = ["sim 后端全流程（模拟链路演示）"]
    return payload


def _ledger_anchor(run_dir: str, overall: str) -> str:
    """台账锚点：单行、无管道符、远低于 120 字符上限。"""
    name = os.path.basename(run_dir.rstrip(os.sep)) or run_dir
    return f"fn(run_demo) run:{name} status:{overall}"


def _execute_stage(
    ctx: dict,
    scenario: dict,
    selection: dict,
    clock_ref: str,
    state: dict,
    stop: object = None,
) -> None:
    """manage_run 的 execute 回调主体（发射态迁移→执行分派→采集→报告→溯源）。

    任何异常上抛给 manage_run（先入 stopping、停发射、finalize failed 后原样
    重抛）——run_demo 捕获后按运行失败 exit 1；其中 build_report 失败同口径
    （报告失败=运行失败）。溯源自捕获：失败只标注（'traceability' 附 run
    结果——state/run.log/摘要行三处留痕），绝不反杀运行。

    急停协作检查（B24 C1）：stop=共享停容器时——①运行启动（running 置位后）、
    采集阶段前、报告阶段前三个阶段边界检查 stop['flag']，置位即抛
    EmergencyStopRequested（沿 manage_run「先停发射再退出」收尾传播）；
    ②sim 事件流包 _stop_checked_events（判据窗每档拉样必经——功率档间检查点）；
    ③采集路 record_run_streams 的协作停凭据透传（streams_ctx['stop']=stop，
    其三路 drain 原生支持）。stop=None（CLI/无急停方）时一切保持既有语义。
    """
    run_dir = ctx["run_dir"]
    state["run_dir"] = run_dir
    ctx["set_state"]("running")
    _raise_if_stopped(stop, "运行启动边界（running 置位后）")
    ctx["clock_ref"] = clock_ref  # result.json 口径贯通（finalize 拷贝该键）

    # ---- 判据路 DUT 源接线（两级回落 scenario>ctx>缺省 sim；sim 源事件兜底生成） ----
    dut = scenario.get("dut") if isinstance(scenario.get("dut"), dict) else None
    if dut is None:
        dut = ctx.get("dut") if isinstance(ctx.get("dut"), dict) else None
    if not isinstance(dut, dict) or "source" not in dut:
        dut = {"source": "sim", "samples_per_event": _DEMO_SAMPLES_PER_EVENT}
    ctx["dut"] = dut
    if dut.get("source") == "sim":
        if ctx.get("sim_events") is None:
            ctx["sim_events"] = _sim_events(scenario)
        if stop is not None:
            # 功率档间检查点：判据窗逐档拉样必经 sim 事件流——包装后逐事件查停旗
            ctx["sim_events"] = _stop_checked_events(ctx["sim_events"], stop)
    if "link_power_db" not in ctx:
        ctx["link_power_db"] = scenario.get("link_power_db", _DEMO_LINK_POWER_DB)
    if ctx.get("monitor") is None:  # gb 基线窗（协议编排内部）同用监测参数
        ctx["monitor"] = _monitor_params(scenario)

    # ---- 场景执行阶段（四类型分派；判据路 KPI/gb 基线窗由各编排自管） ----
    run_out = execute_scenario(ctx, scenario)
    state["execute_result"] = run_out
    ctx["result"] = run_out  # B21 中#2：execute 返回并入 ctx['result']（result.json 口径）

    # ---- 监测/录制采集路（'record' 开关场景键；不继承停检凭据/基线录制关） ----
    _raise_if_stopped(stop, "采集阶段边界（execute→streams）")
    streams_ctx = dict(ctx)
    streams_ctx["record"] = bool(scenario.get("record", False))
    streams_ctx["stop"] = stop  # B24 C1：协作停凭据透传（None=既有不停检口径）
    state["streams"] = record_run_streams(streams_ctx)

    # ---- distance 档 KPI 行重追加（B21 中#2）：record_run_streams 以 'w' 重写
    # kpi.csv，_run_distance 执行期写入的距离档行被截——采集后按结果对象重追加
    # （列映射同 KPI_HEADER，与执行期逐档追加同一实现）。
    scenario_type = scenario.get("scenario_type")
    inner = run_out.get("result") if isinstance(run_out.get("result"), dict) else {}
    if (
        isinstance(scenario_type, str)
        and scenario_type.strip().lower() == "distance"
        and isinstance(inner.get("kpi_rows"), list)
    ):
        append_distance_kpi_rows(run_dir, inner["kpi_rows"])

    # ---- 报告（口径：报告失败=运行失败——异常经 manage_run 收尾 failed → exit 1） ----
    _raise_if_stopped(stop, "报告阶段边界（streams→report）")
    payload = _report_payload(run_dir, run_out, scenario, selection, clock_ref)
    report_path = build_report(run_dir, payload)
    state["report_path"] = report_path

    # ---- 溯源（失败不致 run 失败：结果附注） ----
    try:
        trace = verify_report_traceability(report_path, run_dir)
    except Exception as exc:  # noqa: BLE001 - 溯源绝不反杀运行（含报告缺失等 ValueError）
        trace = {
            "passed": False,
            "mismatches": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    state["traceability"] = trace
    ctx["log"]("INFO", f"溯源校验: passed={trace.get('passed')}")


def _attach_traceability(run_record: dict, state: dict) -> None:
    """'traceability' 结果附 run result：result.json 就近补写（尽力而为不抛）。

    finalize 在 execute 返回后才落盘，溯源结果无法经 finalize_ctx 携带——收尾
    后读回 result.json 补 'traceability' 键（排版对齐 finalize：indent=2、
    ensure_ascii=False，同 manage_run 的 log_degraded 补正手法）；补写失败仅
    放弃（摘要行与 run.log 已留痕，不反杀运行）。
    """
    trace = state.get("traceability")
    result = run_record.get("result")
    if not isinstance(trace, dict) or not isinstance(result, dict):
        return
    path = result.get("result_path")
    if not isinstance(path, str) or not path:
        path = os.path.join(run_record.get("run_dir", ""), "result.json")
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return
        payload["traceability"] = trace
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001 - 附注尽力而为：绝不反杀已成功的运行
        return


def _attach_scenario_result(run_record: dict, state: dict) -> None:
    """场景执行结果附 run result（B21 中#2）：result.json 就近补写（尽力而为不抛）。

    execute 回调把 execute_scenario 返回并入 ctx['result']，但 finalize 的
    payload 只认停发射/时钟等收尾键——场景结果（distance 的 distance_plan/
    kpi_rows 等）须在收尾后读回 result.json 补 'scenario_result' 键（排版对齐
    finalize：indent=2、ensure_ascii=False，同 _attach_traceability 手法）；
    补写失败仅放弃（执行结果已在 events/kpi.csv/result 对象三处留痕，不反杀）。
    """
    execute_result = state.get("execute_result")
    if not isinstance(execute_result, dict):
        return
    result = run_record.get("result")
    path = None
    if isinstance(result, dict):
        path = result.get("result_path")
    if not isinstance(path, str) or not path:
        path = os.path.join(run_record.get("run_dir", ""), "result.json")
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return
        payload["scenario_result"] = execute_result
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001 - 附注尽力而为：绝不反杀已成功的运行
        return


def _summary(
    run_record: dict,
    state: dict,
    completed: bool,
    ledger_status: str,
    prog: str = "run_demo",
) -> str:
    """⑦ 摘要行（stdout）：run_dir/status/失效数/报告路径/溯源 passed/台账。

    prog 前缀区分入口（CLI 'run_demo' / 无头入口 'run_scenario'），字段口径同构。
    """
    trace = state.get("traceability")
    trace_passed = isinstance(trace, dict) and bool(trace.get("passed"))
    execute_result = state.get("execute_result") if isinstance(state.get("execute_result"), dict) else {}
    return (
        f"{prog}: run_dir={run_record['run_dir']}"
        f" status={'completed' if completed else 'failed'}"
        f" failure_levels={len(_failure_levels(execute_result))}"
        f" report={state.get('report_path')}"
        f" traceability={'passed' if trace_passed else 'failed'}"
        f" ledger={ledger_status}"
    )


def _backend_error_text(exc: Exception) -> str:
    """BackendError 统一失败文案（附降级建议，消息已有则不重复）。"""
    message = str(exc)
    advice = "" if _FALLBACK_ADVICE in message else f"；{_FALLBACK_ADVICE}"
    return f"后端启动失败（运行失败，exit 1）: {message}{advice}"


def _normalize_scenario_object(scenario: dict) -> dict:
    """场景 dict → 规范化场景对象（validate→guard→normalize+信封键落位）。

    与 load_scenario(path) 装载后的三件套同构（validate_scenario_schema →
    guard_compliance → normalize_scenario，信封键 bands/shielded_box/dut_scope/
    declarations 摘出后落位），差异仅在入口：本函数收已解析 dict（网页/API
    直给），文件读与 YAML 解析归调用方（serve_console 薄载荷合并路径先经
    load_scenario 全口径装载）。未知键/红线拒绝同样抛 LoadScenarioError——
    场景进入系统的唯一形状纪律不因入口放宽。
    """
    if not isinstance(scenario, dict):
        raise LoadScenarioError(
            f"场景必须为 dict（完整场景对象），实际 {type(scenario).__name__}: {scenario!r}"
        )
    nested = scenario.get("declarations")
    declarations = nested if isinstance(nested, dict) else {}
    shielded_box = declarations.get("shielded_box", scenario.get("shielded_box"))
    dut_scope = declarations.get("dut_scope", scenario.get("dut_scope"))
    bands = scenario.get("bands")
    scenario_fields = {k: v for k, v in scenario.items() if k not in _ENVELOPE_KEYS}

    errors = validate_scenario_schema(scenario_fields)
    if errors:
        numbered = "\n".join(f"  {i}. {e}" for i, e in enumerate(errors, start=1))
        raise LoadScenarioError(f"场景字段校验未通过（{len(errors)} 处）:\n{numbered}")

    guard_config = {
        "power": {"power_dbm": scenario_fields.get("power_dbm", DEFAULT_POWER_DBM)},
        "bands": bands,
        "declarations": {"shielded_box": shielded_box, "dut_scope": dut_scope},
    }
    verdict = guard_compliance(guard_config)
    if verdict["status"] == "rejected":
        violation_lines = "\n".join(f"  - {v}" for v in verdict["violations"])
        raise LoadScenarioError(
            f"红线校验拒绝（guard_compliance）:\n{violation_lines}"
        )

    normalized = normalize_scenario(scenario_fields)
    normalized["bands"] = bands
    normalized["shielded_box"] = shielded_box
    normalized["dut_scope"] = dut_scope
    return normalized


def _execute_pipeline(
    scenario: dict,
    state: dict,
    *,
    backend: str | None,
    runs_root: str,
    stop: object = None,
) -> "tuple[dict, bool]":
    """共享执行管线（CLI run_demo 与无头入口 run_scenario 同构，避免复制）：
    后端决策→时基→manage_run 全生命周期（execute 回调=执行分派+采集+报告+
    溯源，见 _execute_stage）→运行成败归一（manage_run 终态+场景执行 status
    双确认）→溯源/场景结果附注 result.json（尽力而为）。

    state 由调用方创建并传入（run_dir/execute_result/report_path/
    traceability 就地落位）——异常路径（经 manage_run 先停发射收尾后重抛）
    调用方仍能从 state 取到已建 run_dir 等进展留痕。

    stop=共享停容器（B24 C1）：后端打开后把句柄写回 stop['backend']（急停方
    直停真后端的注册通道——此后 trigger_emergency_stop/stop_transmit_safely
    经该句柄实停，不再是 no_backend 空转）；容器随后贯通 _execute_stage 的
    协作检查点（档间/阶段边界）。None=无急停方，既有语义不变。

    返回 (run_record, completed)；异常原样上抛（BackendError/RunDirError/
    execute 阶段任何异常（后者已经 manage_run 先停发射收尾）——含
    EmergencyStopRequested（协作中止，run_scenario 捕获归一 stopped））——
    失败语义归调用方：CLI 转 exit 1 摘要行，run_scenario 转 failed 返回 dict。
    """
    backend_obj, selection = autodetect_backend(
        _explicit_backend_name(backend, scenario), _backend_params(scenario)
    )
    if stop is not None:
        # 后端句柄注册（B24 C1）：写回共享停容器——急停方经 stop['backend']
        # 直停真后端（形状登记见 run_scenario docstring）。
        stop["backend"] = backend_obj
    clock_ref = resolve_clock_reference(backend_obj)["clock_ref"]

    def _execute(ctx: dict) -> None:
        _execute_stage(ctx, scenario, selection, clock_ref, state, stop)

    run_record = manage_run(scenario, _execute, runs_root=runs_root, backend=backend_obj)
    execute_result = (
        state.get("execute_result") if isinstance(state.get("execute_result"), dict) else {}
    )
    completed = (
        run_record.get("status") == "done"
        and execute_result.get("status") == "completed"
    )
    _attach_traceability(run_record, state)
    _attach_scenario_result(run_record, state)
    return run_record, completed


def _ledger_status_for(
    scenario: dict,
    run_record: dict,
    completed: bool,
    *,
    enabled: bool,
    ledger_path: str | None = None,
) -> "tuple[str, str | None]":
    """台账状态归一（CLI --no-ledger / run_scenario ledger=False 同构）：
    skipped(ledger_off)|skipped(no_entry)|updated|warning。

    仅场景含 'ledger_entry' 键且未显式关 ledger 时调 update_ledger（anchor=
    fn(run_demo) run:<目录名> status:<终态>；路径 ledger_path 覆盖 > 缺省
    DEFAULT_LEDGER_PATH 仓库根锚定——动态回落模块全局，与运行 cwd 无关）。
    LedgerError/ValueError 只降 warning 不反杀运行。

    Returns:
        (状态, 警告文本|None)：warning 分支携异常文本——CLI 打 stderr 警告行，
        无头入口并入失败口径忽略（台账绝不反杀运行）。
    """
    if not enabled:
        return "skipped(ledger_off)", None
    entry_id = scenario.get("ledger_entry")
    if not (isinstance(entry_id, str) and entry_id.strip()):
        return "skipped(no_entry)", None
    if ledger_path is None:  # 动态回落模块全局（monkeypatch 友好；绝对锚定与 cwd 无关）
        ledger_path = DEFAULT_LEDGER_PATH
    try:
        update_ledger(
            entry_id.strip(),
            _ledger_anchor(run_record["run_dir"], "completed" if completed else "failed"),
            ledger_path=ledger_path,
        )
    except (LedgerError, ValueError) as exc:
        return "warning", f"{type(exc).__name__}: {exc}"
    return "updated", None


def _result_json_field(run_record: dict, key: str) -> str:
    """从 run 目录的 result.json 读取字段（backend/clock_ref），读不到返回 '?'。"""
    import json as _json
    run_dir = run_record.get("run_dir")
    if not run_dir:
        return "?"
    try:
        with open(os.path.join(run_dir, "result.json"), encoding="utf-8") as fh:
            data = _json.load(fh)
        return str(data.get(key, "?"))
    except Exception:  # noqa: BLE001 - 字段缺失/读取失败静默降级
        return "?"


def _stopped_result(state: dict, exc: EmergencyStopRequested) -> dict:
    """急停协作中止的结果归一（B24 C1）：status='stopped'、exit_code=1（未完成
    口径——中断语义沿用「场景执行未完成即 exit 1」）；events.jsonl 就近补一条
    emergency_stop 事件留痕（尽力而为——发射侧静默已由传播路径的停发射铁律
    完成，事件写失败不反杀 stopped 结果）。"""
    run_dir = state.get("run_dir")
    execute_result = (
        state.get("execute_result")
        if isinstance(state.get("execute_result"), dict)
        else {}
    )
    if isinstance(run_dir, str) and run_dir:
        try:
            append_event(
                run_dir,
                {
                    "type": "emergency_stop",
                    "status": "stopped",
                    "reason": str(exc),
                },
            )
        except Exception:  # noqa: BLE001 - 留痕尽力而为：不反杀 stopped 归一
            pass
    return {
        "run_dir": run_dir,
        "status": "stopped",
        "report_path": state.get("report_path"),
        "exit_code": EXIT_RUN_FAILED,
        "backend": _result_json_field({"run_dir": run_dir}, "backend"),
        "clock_ref": _result_json_field({"run_dir": run_dir}, "clock_ref"),
        "failure_levels": len(_failure_levels(execute_result)),
        "summary": (
            f"run_scenario: 急停协作中止（status=stopped，未完成口径 exit 1）"
            f": run_dir={run_dir or '<未建>'} {exc}"
        ),
        "error": str(exc),
    }


def run_scenario(
    scenario: dict,
    *,
    backend: str | None = None,
    out_root: str = RUNS_ROOT,
    dwell_s: float | None = None,
    ledger: bool = False,
    stop: "dict | None" = None,
) -> dict:
    """无头单场景运行入口（网页操控台/程序化复用；不打印不退出，一切入返回值）。

    与 CLI run_demo 同构的编排链（共享 _execute_pipeline/_execute_stage）：
    场景校验+规范化（validate→guard→normalize，load_scenario 三件套同口径）
    → 后端决策（backend 参数 > 场景 'backend' > 自动探测） → 时基 →
    manage_run（执行分派+采集+报告+溯源）→ 附注 result.json；台账缺省不动
    （ledger=False；True 时同 CLI --no-ledger 未给口径：场景含 ledger_entry
    才更新，LedgerError 只降 warning）。

    Args:
        scenario: 完整场景 dict（含声明等信封键；已由调用方保证形状——网页侧
            薄载荷的名解析与文件合并在 serve_console 缺省 runner 完成）。
        backend: 显式后端名（sim/b210/replay）；None=回落场景 'backend' 键，
            'auto' 才探测。
        out_root: 运行目录基础路径（manage_run runs_root，自动创建；缺省
            'runs' 相对 cwd——操控台传 config['report_root']）。
        dwell_s: 档间停留秒覆盖（None=不覆盖；非法值 ValueError 早拒）。
        ledger: 是否在场景含 ledger_entry 时更新台账（缺省 False——操控台
            不动台账，CLI 语义归 run_demo）。
        stop: 急停协作停共享容器（B24 C1，缺省 None=无急停方）。形状登记：
            {'flag': bool}——编排终止旗，急停方置 True 后管线在功率档间
            （sim 事件流逐事件）与阶段边界（运行启动/采集/报告前）协作检查，
            触发即走既有「先停发射再退出」中止路径（本函数归一
            status='stopped'，exit_code=1 未完成口径，events.jsonl 落
            emergency_stop 事件）；'backend'——后端打开后由管线写回发射后端
            句柄（急停方直停真后端的通道：serve_console 停止路由同步进
            run_ctx 供 trigger_emergency_stop 消费）；其余键不消费。运行
            生命周期外该容器由调用方管理（操控台 /api/run 启动即复位旗）。

    Returns:
        {'run_dir': str|None（校验失败/后端失败为 None）, 'status':
        'completed'|'failed'|'stopped'|'validation_failed', 'report_path': str|None,
        'exit_code': 0|1|2（与 CLI 三态同口径；stopped=1 未完成口径）,
        'failure_levels': int, 'summary': 摘要行文本, 'error': 失败/中止原因
        （仅失败与 stopped 分支携带）}。
        预期失败路径不抛（返回失败 dict）；仅入参形状错（非 dict 场景/非法
        dwell_s/stop 非 dict）抛 ValueError——调用方编程错误早暴露。

    Raises:
        ValueError: scenario 非 dict / dwell_s 非非负有限秒 / stop 非 dict|None。
    """
    if not isinstance(scenario, dict):
        raise ValueError(
            f"scenario 必须为 dict（完整场景对象），实际 {type(scenario).__name__}: {scenario!r}"
        )
    if dwell_s is not None and not _is_finite_nonneg_seconds(dwell_s):
        raise ValueError(f"dwell_s 须为非负有限秒数，实际 {dwell_s!r}")
    if stop is not None and not isinstance(stop, dict):
        raise ValueError(
            f"stop 须为共享停容器 dict（{{'flag': bool}}）或 None，实际 "
            f"{type(stop).__name__}: {stop!r}"
        )

    def _failed(text: str, exc: BaseException | None) -> dict:
        execute_result = (
            state.get("execute_result")
            if isinstance(state.get("execute_result"), dict)
            else {}
        )
        result = {
            "run_dir": state.get("run_dir"),
            "status": "failed",
            "report_path": state.get("report_path"),
            "exit_code": EXIT_RUN_FAILED,
            "failure_levels": len(_failure_levels(execute_result)),
            "summary": f"run_scenario: {text}",
        }
        if exc is not None:
            result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    # ---- ① 场景校验+规范化（validate→guard→normalize；未知键/红线拒绝 exit 2 口径） ----
    state: dict = {}
    try:
        prepared = _normalize_scenario_object(scenario)
    except LoadScenarioError as exc:
        return {
            "run_dir": None,
            "status": "validation_failed",
            "report_path": None,
            "exit_code": EXIT_VALIDATION_FAILED,
            "failure_levels": 0,
            "summary": f"run_scenario: 场景校验失败（校验失败，exit 2）: {exc}",
            "error": f"{type(exc).__name__}: {exc}",
        }
    if dwell_s is not None:  # 覆盖透传（两级回落 scenario>ctx>缺省最高层）
        prepared["dwell_s"] = float(dwell_s)

    # ---- ②③④ 共享执行管线（后端→时基→manage_run→附注；异常转失败 dict） ----
    try:
        run_record, completed = _execute_pipeline(
            prepared, state, backend=backend, runs_root=out_root, stop=stop
        )
    except EmergencyStopRequested as exc:
        # B24 C1：急停协作中止——发射侧静默已由传播路径完成（ladder/协议编排
        # 异常路径+manage_run 收尾铁律），此处归一 stopped（exit 1 未完成口径）。
        return _stopped_result(state, exc)
    except BackendError as exc:
        return _failed(_backend_error_text(exc), exc)
    except RunDirError as exc:
        return _failed(f"运行目录创建失败（运行失败，exit 1）: {exc}", exc)
    except Exception as exc:  # noqa: BLE001 - execute 阶段异常经 manage_run 停发射收尾后重抛
        return _failed(
            f"运行失败（exit 1）: run_dir={state.get('run_dir') or '<未建>'}"
            f" {type(exc).__name__}: {exc}",
            exc,
        )
    ledger_status, _ledger_warning = _ledger_status_for(
        prepared, run_record, completed, enabled=ledger
    )
    return {
        "run_dir": run_record.get("run_dir"),
        "status": "completed" if completed else "failed",
        "report_path": state.get("report_path"),
        "exit_code": EXIT_OK if completed else EXIT_RUN_FAILED,
        "backend": _result_json_field(run_record, "backend"),
        "clock_ref": _result_json_field(run_record, "clock_ref"),
        "failure_levels": len(
            _failure_levels(
                state.get("execute_result")
                if isinstance(state.get("execute_result"), dict)
                else {}
            )
        ),
        "summary": _summary(run_record, state, completed, ledger_status, prog="run_scenario"),
    }


def run_demo(argv: list | None = None) -> int:
    """CLI 总入口（R44）：场景→后端→步进→采集→报告→台账，退出码 0/1/2。

    输入:
        argv: 参数清单（None → sys.argv[1:]）——[场景路径 | '--demo'] 恰其一，
            可选 '--backend' 名 / '--dwell' 秒（CLI 覆盖 scenario['dwell_s']）/
            '--ledger' 台账 md 路径覆盖（缺省仓库根锚定 DEFAULT_LEDGER_PATH）/
            '--no-ledger'。

    输出:
        int 退出码：0=成功（manage_run 终态 done 且场景执行 status='completed'）；
        1=运行失败（后端打开失败/运行目录失败/execute 阶段任何异常（均已经
        manage_run 先停发射收尾）/场景执行未完成（判据触发/baseline_rejected））；
        2=校验失败（CLI 参数域/场景装载 LoadScenarioError）。

    错误:
        不抛（一切转退出码；argparse 用法错/--help 的 SystemExit 就地转码；
        KeyboardInterrupt 例外——manage_run 停发射收尾后原样放行信号）。
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else list(argv))
    except SystemExit as exc:  # argparse 用法错（2）/--help（0）：转退出码不抛
        code = exc.code
        return EXIT_OK if code in (0, None) else int(code)

    # ---- ① 场景装载（'--demo' 内置样例；恰其一 + --dwell 域 → 校验失败 2） ----
    if bool(args.demo) == (args.scenario_path is not None):
        _err("须恰给其一：场景 YAML 路径 或 --demo（校验失败，exit 2）")
        return EXIT_VALIDATION_FAILED
    if args.dwell is not None and not _is_finite_nonneg_seconds(args.dwell):
        _err(f"--dwell 须为非负有限秒数（校验失败，exit 2），收到 {args.dwell!r}")
        return EXIT_VALIDATION_FAILED
    try:
        scenario = _demo_scenario() if args.demo else load_scenario(args.scenario_path)
    except LoadScenarioError as exc:
        _err(f"场景装载失败（校验失败，exit 2）: {exc}")
        return EXIT_VALIDATION_FAILED
    if args.dwell is not None:  # CLI 覆盖透传（两级回落 scenario>ctx>缺省最高层）
        scenario["dwell_s"] = float(args.dwell)

    # ---- ②③④ 共享执行管线（后端→时基→manage_run（执行+采集+报告+溯源）→附注） ----
    state: dict = {}
    try:
        run_record, completed = _execute_pipeline(
            scenario, state, backend=args.backend, runs_root=RUNS_ROOT
        )
    except BackendError as exc:
        _err(_backend_error_text(exc))
        return EXIT_RUN_FAILED
    except RunDirError as exc:
        _err(f"运行目录创建失败（运行失败，exit 1）: {exc}")
        return EXIT_RUN_FAILED
    except Exception as exc:  # noqa: BLE001 - execute 阶段异常经 manage_run 停发射收尾后重抛
        _err(
            f"运行失败（exit 1）: run_dir={state.get('run_dir') or '<未建>'}"
            f" {type(exc).__name__}: {exc}"
        )
        return EXIT_RUN_FAILED

    # ---- ⑥ 台账（--no-ledger 缺省启用；场景含 'ledger_entry' 才更新；失败仅警告） ----
    if args.no_ledger:
        ledger_status, ledger_warning = "skipped(--no-ledger)", None
    else:
        # 台账路径：'--ledger' 覆盖 > 仓库根锚定缺省（DEFAULT_LEDGER_PATH，
        # 与运行 cwd 无关——从 fn_work/任意目录跑都指向同一份清单）。
        ledger_status, ledger_warning = _ledger_status_for(
            scenario,
            run_record,
            completed,
            enabled=True,
            ledger_path=str(args.ledger) if args.ledger else None,
        )
    if ledger_warning:
        print(
            f"run_demo: 台账更新警告（不影响退出码）: {ledger_warning}",
            file=sys.stderr,
        )

    # ---- ⑦ 摘要行 stdout + 退出码 ----
    print(_summary(run_record, state, completed, ledger_status))
    return EXIT_OK if completed else EXIT_RUN_FAILED
