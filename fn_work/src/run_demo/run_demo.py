"""CLI 总入口：场景→后端→时钟→manage_run（执行+采集）→报告→溯源→台账，退出码 0/1/2——重写规约与签名意图详见 fn_docs/responsibility.md R44。

编排链（一键命令串联主链，分阶段退出码；任何异常先停发射经 manage_run 收尾）：
① load_scenario（'--demo' 用内置 sim 场景）——LoadScenarioError → exit 2 摘要行；
② autodetect_backend（explicit 来自 --backend，缺省回落场景 'backend' 键，
  'auto'/缺省才探测）——BackendError → exit 1 附降级建议；
③ resolve_clock_reference（永不抛）——clock_ref 口径贯通报告脚注与 result.json；
④ manage_run 全生命周期，execute 回调内：ctx['set_state']('running') →
  execute_scenario（四类型分派：gb42590/distance/custom/emc——判据路 KPI 与
  gb 基线窗由各编排自管）→ record_run_streams（监测/录制采集路——'record'
  开关取场景键，缺省 False）→ build_report → verify_report_traceability；
⑤ 溯源失败不致 run 失败：'traceability' 结果附 run result（result.json 就近
  补写（尽力而为，排版同 finalize）+摘要行与 run.log 三处留痕），build_report
  失败口径=运行失败 exit 1（异常经 manage_run 先停发射收尾标 failed 后重抛）；
⑥ 台账：--no-ledger 缺省时，场景含 'ledger_entry' 键（如 'B1'）才调
  update_ledger（anchor=fn(run_demo) run:<目录名> status:<终态>）；LedgerError/
  ValueError 只打警告不改变退出码；
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

from src.autodetect_backend.autodetect_backend import autodetect_backend
from src.build_report.build_report import build_report
from src.load_scenario.load_scenario import load_scenario
from src.load_scenario.load_scenario import ScenarioError as LoadScenarioError
from src.manage_backend_registry.lookup_backend import BackendError
from src.manage_run.manage_run import RunDirError, manage_run
from src.resolve_clock_reference.resolve_clock_reference import resolve_clock_reference
from src.update_ledger.update_ledger import LedgerError, update_ledger
from src.verify_report_traceability.verify_report_traceability import (
    verify_report_traceability,
)

from .execute_scenario import execute_scenario, record_run_streams

__all__ = ["run_demo"]

#: 退出码三态（R44 签名意图：校验失败=2；运行失败=1；均已停发射）。
EXIT_OK = 0
EXIT_RUN_FAILED = 1
EXIT_VALIDATION_FAILED = 2

#: 运行目录基础路径（相对 CWD；manage_run 自动创建，同秒冲突 -2/-3 去重）。
RUNS_ROOT = "runs"

#: BackendError 统一降级建议（与 autodetect_backend 文案同口径，不重复附）。
_FALLBACK_ADVICE = "可改用 --backend sim 降级"

#: 监测路缺省目标频段（MHz，2.4G 法定频段；场景 'bands' 首对优先）。
_DEFAULT_MONITOR_BAND_MHZ = (2400.0, 2483.5)

#: 内置 --demo 快路径参数：判据永不触发的悬崖左远端 JSR + 事件量。
_DEMO_JSR_DB = -20.0
_DEMO_N_EVENTS = 10
_DEMO_SAMPLES_PER_EVENT = 3
_DEMO_LINK_POWER_DB = -20.0


def _demo_scenario() -> dict:
    """内置 '--demo' 完整样例场景：tone / sim / gb42590（快路径 <10s）。

    与 load_scenario 规范化输出同形状（场景字段+红线信封键），另携执行信封
    （scenario_type/judge_min_samples/dwell_s/baseline_samples/record/sim_events/
    dut——内置场景不经文件装载，不受 schema 未知键约束）；judge_min_samples=2、
    dwell_s=0、baseline_samples=10 保证全流程秒级完成，jsr=-20（悬崖左远端）
    使判据永不触发——阶梯走完 0dBm 红线截断，status='completed'（exit 0）。
    """
    sim_events = [
        {"type": "power_step", "jsr_db": _DEMO_JSR_DB, "ts": float(index)}
        for index in range(_DEMO_N_EVENTS)
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
        "judge_min_samples": 2,
        "dwell_s": 0.0,
        "baseline_samples": 10,
        "signal_power_db": _DEMO_LINK_POWER_DB,
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
    """CLI 参数：[场景路径 | --demo] 恰其一 + --backend/--dwell/--no-ledger。"""
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
        help="使用内置 tone/sim/gb42590 完整样例（judge 2/dwell 0/baseline 10 快路径）",
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


def _explicit_backend(args: argparse.Namespace, scenario: dict) -> str | None:
    """显式后端名决策：--backend > 场景 'backend'（'auto'/空/非 str → None 探测）。"""
    if args.backend is not None:
        name = args.backend.strip() if isinstance(args.backend, str) else args.backend
        return name if name else None
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
) -> None:
    """manage_run 的 execute 回调主体（发射态迁移→执行分派→采集→报告→溯源）。

    任何异常上抛给 manage_run（先入 stopping、停发射、finalize failed 后原样
    重抛）——run_demo 捕获后按运行失败 exit 1；其中 build_report 失败同口径
    （报告失败=运行失败）。溯源自捕获：失败只标注（'traceability' 附 run
    结果——state/run.log/摘要行三处留痕），绝不反杀运行。
    """
    run_dir = ctx["run_dir"]
    state["run_dir"] = run_dir
    ctx["set_state"]("running")
    ctx["clock_ref"] = clock_ref  # result.json 口径贯通（finalize 拷贝该键）

    # ---- 判据路 DUT 源接线（两级回落 scenario>ctx>缺省 sim；sim 源事件兜底生成） ----
    dut = scenario.get("dut") if isinstance(scenario.get("dut"), dict) else None
    if dut is None:
        dut = ctx.get("dut") if isinstance(ctx.get("dut"), dict) else None
    if not isinstance(dut, dict) or "source" not in dut:
        dut = {"source": "sim", "samples_per_event": _DEMO_SAMPLES_PER_EVENT}
    ctx["dut"] = dut
    if dut.get("source") == "sim" and ctx.get("sim_events") is None:
        ctx["sim_events"] = _sim_events(scenario)
    if "link_power_db" not in ctx:
        ctx["link_power_db"] = scenario.get("link_power_db", _DEMO_LINK_POWER_DB)
    if ctx.get("monitor") is None:  # gb 基线窗（协议编排内部）同用监测参数
        ctx["monitor"] = _monitor_params(scenario)

    # ---- 场景执行阶段（四类型分派；判据路 KPI/gb 基线窗由各编排自管） ----
    run_out = execute_scenario(ctx, scenario)
    state["execute_result"] = run_out

    # ---- 监测/录制采集路（'record' 开关场景键；不继承停检凭据/基线录制关） ----
    streams_ctx = dict(ctx)
    streams_ctx["record"] = bool(scenario.get("record", False))
    streams_ctx["stop"] = None
    state["streams"] = record_run_streams(streams_ctx)

    # ---- 报告（口径：报告失败=运行失败——异常经 manage_run 收尾 failed → exit 1） ----
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


def _summary(
    run_record: dict, state: dict, completed: bool, ledger_status: str
) -> str:
    """⑦ 摘要行（stdout）：run_dir/status/失效数/报告路径/溯源 passed/台账。"""
    trace = state.get("traceability")
    trace_passed = isinstance(trace, dict) and bool(trace.get("passed"))
    execute_result = state.get("execute_result") if isinstance(state.get("execute_result"), dict) else {}
    return (
        f"run_demo: run_dir={run_record['run_dir']}"
        f" status={'completed' if completed else 'failed'}"
        f" failure_levels={len(_failure_levels(execute_result))}"
        f" report={state.get('report_path')}"
        f" traceability={'passed' if trace_passed else 'failed'}"
        f" ledger={ledger_status}"
    )


def run_demo(argv: list | None = None) -> int:
    """CLI 总入口（R44）：场景→后端→步进→采集→报告→台账，退出码 0/1/2。

    输入:
        argv: 参数清单（None → sys.argv[1:]）——[场景路径 | '--demo'] 恰其一，
            可选 '--backend' 名 / '--dwell' 秒（CLI 覆盖 scenario['dwell_s']）/
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

    # ---- ② 启动后端（显式 --backend > 场景 backend > 自动探测；失败不静默） ----
    try:
        backend, selection = autodetect_backend(
            _explicit_backend(args, scenario), _backend_params(scenario)
        )
    except BackendError as exc:
        message = str(exc)
        advice = "" if _FALLBACK_ADVICE in message else f"；{_FALLBACK_ADVICE}"
        _err(f"后端启动失败（运行失败，exit 1）: {message}{advice}")
        return EXIT_RUN_FAILED

    # ---- ③ 时基决策（探测→驯服或软件钟降级，永不抛） ----
    clock_reference = resolve_clock_reference(backend)
    clock_ref = clock_reference["clock_ref"]

    # ---- ④ manage_run 全生命周期（execute 内含执行分派/采集/报告/溯源） ----
    state: dict = {}

    def _execute(ctx: dict) -> None:
        _execute_stage(ctx, scenario, selection, clock_ref, state)

    try:
        run_record = manage_run(scenario, _execute, runs_root=RUNS_ROOT, backend=backend)
    except RunDirError as exc:
        _err(f"运行目录创建失败（运行失败，exit 1）: {exc}")
        return EXIT_RUN_FAILED
    except Exception as exc:  # noqa: BLE001 - execute 阶段异常经 manage_run 停发射收尾后重抛
        _err(
            f"运行失败（exit 1）: run_dir={state.get('run_dir') or '<未建>'}"
            f" {type(exc).__name__}: {exc}"
        )
        return EXIT_RUN_FAILED

    # ---- 运行成败归一：manage_run 终态 + 场景执行 status 双确认 ----
    execute_result = (
        state.get("execute_result") if isinstance(state.get("execute_result"), dict) else {}
    )
    completed = (
        run_record.get("status") == "done"
        and execute_result.get("status") == "completed"
    )
    _attach_traceability(run_record, state)  # 'traceability' 附 run result（尽力）

    # ---- ⑥ 台账（--no-ledger 缺省启用；场景含 'ledger_entry' 才更新；失败仅警告） ----
    if args.no_ledger:
        ledger_status = "skipped(--no-ledger)"
    else:
        entry_id = scenario.get("ledger_entry")
        if isinstance(entry_id, str) and entry_id.strip():
            try:
                update_ledger(
                    entry_id.strip(),
                    _ledger_anchor(run_record["run_dir"], "completed" if completed else "failed"),
                )
            except (LedgerError, ValueError) as exc:
                print(
                    f"run_demo: 台账更新警告（不影响退出码）: {exc}",
                    file=sys.stderr,
                )
                ledger_status = "warning"
            else:
                ledger_status = "updated"
        else:
            ledger_status = "skipped(no_entry)"

    # ---- ⑦ 摘要行 stdout + 退出码 ----
    print(_summary(run_record, state, completed, ledger_status))
    return EXIT_OK if completed else EXIT_RUN_FAILED
