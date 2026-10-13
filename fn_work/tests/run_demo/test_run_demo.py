"""run_demo 对抗用例：R44 CLI 总入口（slug=demo_pipeline）。

两路夹击：
- 真实路径：--demo 内置 sim 场景全流程（中段档判据触发 → exit 1，失效电平
  登记/report.md/溯源执行）、双跑目录去重、坏场景文件 exit 2、未知后端 exit 1；
- 接线路径（叶子依赖 monkeypatch，被测对象 run_demo 自身编排不变）：台账三态
  （ledger_entry 触发/--no-ledger 跳过/LedgerError 仅警告）、dwell 透传、摘要行
  内容、报告失败=运行失败 exit 1（口径断言）、溯源 mismatch 附注但 exit 0、
  status='failed' → exit 1、distance 分派、时钟口径入报告结果、'record' 开关、
  后端显式名决策优先级、argv None 走 sys.argv。
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest

import src.run_demo.run_demo as rd
from src.run_demo.run_demo import run_demo, run_scenario
from src.update_ledger.update_ledger import LedgerError

#: 摘要行正则：⑦ 口径（run_dir/status/失效数/报告路径/溯源 passed/台账）。
_SUMMARY_RE = re.compile(
    r"run_dir=(?P<run_dir>\S+)"
    r" status=(?P<status>completed|failed)"
    r" failure_levels=(?P<n>\d+)"
    r" report=(?P<report>\S+)"
    r" traceability=(?P<trace>passed|failed)"
    r" ledger=(?P<ledger>\S+)"
)


def base_scenario(**over):
    """接线用场景（load_scenario 形状 + 执行信封；ledger_entry 等按用例覆盖）。"""
    scenario = {
        "style": "tone",
        "fs": 1.0e6,
        "freq_hz": 2.4e9,
        "power_dbm": -10.0,
        "backend": "sim",
        "scenario_type": "gb42590",
        "judge_min_samples": 2,
        "dwell_s": 0.0,
        "baseline_samples": 10,
        "record": False,
        "sim_events": [{"type": "power_step", "jsr_db": -20.0, "ts": 0.0}],
        "dut": {"source": "sim", "samples_per_event": 3},
        "bands": [[2400.0, 2483.5]],
        "shielded_box": True,
        "dut_scope": "self_built",
    }
    scenario.update(over)
    return scenario


class _FakeBackend:
    """裸假后端：resolve_clock_reference 真探测（无 GPSDO 传感器→software）。"""


def wire(
    monkeypatch,
    tmp_path,
    *,
    scenario=None,
    execute_result=None,
    verify=None,
    build=None,
    update=None,
):
    """接线 mock：替换 run_demo 模块的叶子依赖（manage_run 仿真回调+状态机最小件）。

    resolve_clock_reference 保持真实（软件钟路径可跑）；返回 caps 捕获字典
    （explicit/es/streams/build/update/states/loaded_path）。
    """
    scenario = scenario if scenario is not None else base_scenario()
    caps = {"explicit": [], "loaded_path": [], "es": [], "streams": [], "build": [], "update": [], "states": []}

    def fake_load(path):
        caps["loaded_path"].append(path)
        return {**scenario}

    def fake_autodetect(explicit=None, params=None):
        caps["explicit"].append(explicit)
        return _FakeBackend(), {"backend": "sim", "decision": "explicit", "explicit": explicit}

    def fake_manage_run(scen, execute, runs_root="runs", backend=None):
        run_dir = tmp_path / "run-0001"
        run_dir.mkdir(exist_ok=True)
        ctx = {
            "run_dir": str(run_dir),
            "scenario": scen,
            "backend": backend,
            "started_at": 0.0,
            "open_files": [],
            "set_state": lambda to: caps["states"].append(to),
            "log": lambda level, message, context=None: None,
        }
        execute(ctx)
        return {"run_dir": str(run_dir), "result": {"finalized": True}, "status": "done"}

    def fake_execute_scenario(ctx, scen=None):
        caps["es"].append((ctx, scen))
        if execute_result is not None:
            return execute_result
        return {
            "status": "completed",
            "result": {"failure_levels": [{"step": 0, "target_db": -5.0}]},
            "streams_note": "wiring",
        }

    def fake_record(ctx, max_kpi_rows=10000, max_monitor_blocks=1000):
        caps["streams"].append(ctx)
        return {
            "kpi_rows": 1,
            "monitor_blocks": 1,
            "stats_rows": 1,
            "alignment": {},
            "recording": None,
            "streams_note": [],
        }

    def fake_build(run_dir, payload):
        caps["build"].append(payload)
        if build is not None:
            return build(run_dir, payload)
        return os.path.join(run_dir, "report.md")

    def fake_verify(report_path, run_dir):
        if isinstance(verify, Exception):
            raise verify
        return verify if verify is not None else {"passed": True, "mismatches": []}

    def fake_update(entry_id, anchor, **kwargs):
        caps["update"].append((entry_id, anchor))
        if isinstance(update, Exception):
            raise update
        return {"updated": True, "line_no": 1, "old_status": "", "new_status": "✅", "anchor": anchor}

    monkeypatch.setattr(rd, "load_scenario", fake_load)
    monkeypatch.setattr(rd, "autodetect_backend", fake_autodetect)
    monkeypatch.setattr(rd, "manage_run", fake_manage_run)
    monkeypatch.setattr(rd, "execute_scenario", fake_execute_scenario)
    monkeypatch.setattr(rd, "record_run_streams", fake_record)
    monkeypatch.setattr(rd, "build_report", fake_build)
    monkeypatch.setattr(rd, "verify_report_traceability", fake_verify)
    monkeypatch.setattr(rd, "update_ledger", fake_update)
    return caps


def _parse_summary(out: str):
    """从 stdout 文本取摘要行（run_demo: 前缀）并按正则解构。"""
    lines = [line for line in out.splitlines() if line.startswith("run_demo: run_dir=")]
    assert lines, f"摘要行缺失: stdout={out!r}"
    match = _SUMMARY_RE.search(lines[-1])
    assert match, f"摘要行不合规约: {lines[-1]!r}"
    return match


def _summary_of(capsys):
    """取（并消费）capsys stdout 后解构摘要行。"""
    return _parse_summary(capsys.readouterr().out)


# ---------- ① 真实路径：--demo 全流程（中段档判据触发） / 双跑 / 坏场景 / 坏后端 ----------


def test_demo_pipeline_demo_full_run_criterion_fires_exit1(tmp_path, monkeypatch, capsys):
    """--demo 全流程回归：中段档判据触发（exit 1）——失效电平登记+报告+溯源照常。

    修复前（误导D）：demo sim 事件恒直给 jsr_db=−20（悬崖左远端），窗口 PER
    恒 0 → 判据永不触发、走完计划 exit 0（"永不失效"假象）。修复后事件按 GB
    阶梯档位携带绝对电平（achieved_db=−25…0 dBm，signal_power_db=−20 →
    jsr=档位+20 随档爬升）：−15dBm 档（index 2，jsr=+5）窗 per=2/20=0.10 恰达
    阈值（≥ 口径判失效）→ status=failed、failure_levels=1、stopped_at=2（中段
    非顶档——计划顶档 0dBm 未及执行）→ exit 1。
    """
    monkeypatch.chdir(tmp_path)  # runs/ 落 tmp，不污染仓库
    rc = run_demo(["--demo"])
    assert rc == 1  # 判据触发=运行失败（演示失效检测真实生效）
    match = _summary_of(capsys)
    assert match["status"] == "failed"
    assert match["n"] == "1"
    run_dir = match["run_dir"]
    assert os.path.isdir(run_dir)
    report = os.path.join(run_dir, "report.md")
    assert os.path.isfile(report)  # 失效路径报告照常生成
    with open(report, encoding="utf-8") as handle:
        report_md = handle.read()
    assert "运行概要" in report_md  # 报告正文真生成
    assert match["trace"] == "passed"  # 溯源已执行且通过（数字纪律闭环）
    with open(os.path.join(run_dir, "result.json"), encoding="utf-8") as handle:
        result_json = json.load(handle)
    assert result_json["traceability"]["passed"] is True  # 'traceability' 附 run result
    inner = result_json["scenario_result"]["result"]
    assert inner["status"] == "failed"
    assert len(inner["failure_levels"]) == 1  # P_crit 失效电平登记 1 条
    assert inner["stopped_at"] == 2  # 中段档（−15dBm，jsr=+5 恰达阈值）
    assert inner["steps_executed"] == 3
    assert inner["plan"]["steps"][-1]["target_db"] == 0.0  # 计划顶档 0dBm
    assert inner["stopped_at"] < len(inner["plan"]["steps"]) - 1  # 非跑顶


def test_demo_pipeline_demo_double_run_distinct_dirs(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert run_demo(["--demo"]) == 1  # 判据触发=exit 1（同 --demo 口径）
    first = _summary_of(capsys)["run_dir"]
    assert run_demo(["--demo"]) == 1
    second = _summary_of(capsys)["run_dir"]
    assert first != second  # 同秒冲突 -2 后缀去重：两次 run_dir 不同
    assert os.path.isfile(os.path.join(first, "report.md"))
    assert os.path.isfile(os.path.join(second, "report.md"))


def test_demo_pipeline_bad_scenario_file_exit2(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("style: quantum\nfs: 1e6\n", encoding="utf-8")  # 未知样式→schema 拒
    rc = run_demo([str(bad)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "场景装载失败" in err  # 摘要行（exit 2 语义）


def test_demo_pipeline_unknown_backend_exit1(capsys):
    rc = run_demo(["--demo", "--backend", "nosuch-backend"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "后端启动失败" in err
    assert "降级" in err  # 附降级建议（不静默）


@pytest.mark.parametrize(
    "case,expected",
    [
        ("success", 0),
        ("backend_error", 1),
        ("validation_error", 2),
    ],
    ids=["exit0-success", "exit1-backend", "exit2-scenario"],
)
def test_demo_pipeline_exit_code_three_way(case, expected, tmp_path, monkeypatch, capsys):
    if case == "success":
        wire(monkeypatch, tmp_path)
        argv = [str(tmp_path / "scene.yaml")]
    elif case == "backend_error":
        argv = ["--demo", "--backend", "nosuch-backend"]
    else:
        argv = [str(tmp_path / "missing.yaml")]  # 文件不存在→LoadScenarioError
    capsys.readouterr()
    assert run_demo(argv) == expected


# ---------- ② CLI 参数域：恰其一/dwell 域/argv None ----------


def test_demo_pipeline_exclusive_demo_or_path_exit2(tmp_path, capsys):
    assert run_demo([]) == 2  # 两者皆缺
    assert run_demo(["--demo", str(tmp_path / "s.yaml")]) == 2  # 两者同给
    assert "恰给其一" in capsys.readouterr().err


def test_demo_pipeline_dwell_negative_rejected_exit2(capsys):
    assert run_demo(["--demo", "--dwell", "-1"]) == 2  # 负 dwell：CLI 早拒（域错）
    assert "--dwell" in capsys.readouterr().err


def test_demo_pipeline_argv_none_uses_sys_argv(tmp_path, monkeypatch, capsys):
    missing = str(tmp_path / "nope.yaml")
    monkeypatch.setattr("sys.argv", ["run_demo", missing])
    assert run_demo() == 2  # None → sys.argv[1:]
    assert "nope.yaml" in capsys.readouterr().err


# ---------- ③ 接线：dwell 透传 / 摘要行 / 后端显式名决策 ----------


def test_demo_pipeline_dwell_passthrough(tmp_path, monkeypatch):
    caps = wire(monkeypatch, tmp_path)
    assert run_demo([str(tmp_path / "scene.yaml"), "--dwell", "0.25"]) == 0
    scenario_seen = caps["es"][0][1]
    assert scenario_seen["dwell_s"] == 0.25  # CLI 覆盖写入 scenario['dwell_s']
    assert caps["loaded_path"] == [str(tmp_path / "scene.yaml")]  # 路径透传装载


def test_demo_pipeline_summary_line_contents(tmp_path, monkeypatch, capsys):
    wire(monkeypatch, tmp_path, scenario=base_scenario(ledger_entry="B1"))
    assert run_demo([str(tmp_path / "scene.yaml")]) == 0
    match = _summary_of(capsys)
    assert match["run_dir"] == str(tmp_path / "run-0001")
    assert match["status"] == "completed"
    assert match["n"] == "1"  # 失效数来自 execute_result.result.failure_levels
    assert match["report"] == str(tmp_path / "run-0001" / "report.md")
    assert match["trace"] == "passed"
    assert match["ledger"] == "updated"


def test_demo_pipeline_backend_selection_precedence(tmp_path, monkeypatch):
    caps = wire(monkeypatch, tmp_path)
    path = str(tmp_path / "scene.yaml")
    assert run_demo([path, "--backend", "sim"]) == 0
    assert caps["explicit"][-1] == "sim"  # --backend 最优先
    assert run_demo([path]) == 0
    assert caps["explicit"][-1] == "sim"  # 缺省回落场景 'backend' 键（非 auto）
    caps_auto = wire(
        monkeypatch,
        tmp_path,
        scenario=base_scenario(backend="auto"),
    )
    assert run_demo([path]) == 0
    assert caps_auto["explicit"][-1] is None  # 'auto' → 自动探测决策


# ---------- ④ 台账三态：触发/跳过/警告 ----------


def test_demo_pipeline_ledger_entry_triggers_update(tmp_path, monkeypatch):
    caps = wire(monkeypatch, tmp_path, scenario=base_scenario(ledger_entry="B1"))
    assert run_demo([str(tmp_path / "scene.yaml")]) == 0
    assert len(caps["update"]) == 1
    entry_id, anchor = caps["update"][0]
    assert entry_id == "B1"
    assert "fn(run_demo)" in anchor and "status:completed" in anchor  # 锚点可回溯


def test_demo_pipeline_no_ledger_flag_skips_update(tmp_path, monkeypatch, capsys):
    caps = wire(monkeypatch, tmp_path, scenario=base_scenario(ledger_entry="B1"))
    assert run_demo([str(tmp_path / "scene.yaml"), "--no-ledger"]) == 0
    assert caps["update"] == []  # --no-ledger：即便场景含 ledger_entry 也不触台账
    assert _summary_of(capsys)["ledger"] == "skipped(--no-ledger)"


def test_demo_pipeline_no_ledger_entry_no_update(tmp_path, monkeypatch, capsys):
    caps = wire(monkeypatch, tmp_path)  # 场景不含 ledger_entry
    assert run_demo([str(tmp_path / "scene.yaml")]) == 0
    assert caps["update"] == []
    assert _summary_of(capsys)["ledger"] == "skipped(no_entry)"


def test_demo_pipeline_ledger_error_warns_not_fails(tmp_path, monkeypatch, capsys):
    wire(
        monkeypatch,
        tmp_path,
        scenario=base_scenario(ledger_entry="B1"),
        update=LedgerError("条目 B1 已 ✅ 未授权覆盖"),
    )
    assert run_demo([str(tmp_path / "scene.yaml")]) == 0  # LedgerError 不失败
    captured = capsys.readouterr()
    assert "台账更新警告" in captured.err
    assert _parse_summary(captured.out)["ledger"] == "warning"


# ---------- ④b 台账路径（阻断C：仓库根锚定 + --ledger 覆盖） ----------


def _tmp_ledger(tmp_path, entry="B1"):
    """tmp 清单（含空状态列的 entry 行）——update_ledger status 形态可写。"""
    ledger = tmp_path / "docs" / "全功能实现清单-技术支持版.md"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        "| 编号 | 描述 | 状态 |\n|---|---|---|\n"
        f"| {entry} | 一键命令编排 |  |\n",
        encoding="utf-8",
    )
    return ledger


def test_ledger_default_path_anchored_to_repo_root():
    """阻断C 回归：默认台账路径锚定仓库根（本测试文件 parents[3]），绝对路径。

    修复前 update_ledger 缺省 'docs/…' 为 cwd 相对路径——从 fn_work 或任意
    非-仓库根 cwd 运行即找不到清单（台账更新只打警告，✅ 永不写入）。
    """
    from pathlib import Path

    repo_root = Path(rd.__file__).resolve().parents[3]
    assert Path(rd.DEFAULT_LEDGER_PATH) == (
        repo_root / "docs" / "全功能实现清单-技术支持版.md"
    )
    assert os.path.isabs(rd.DEFAULT_LEDGER_PATH)


def test_ledger_entry_written_from_foreign_cwd_via_anchored_default(
    tmp_path, monkeypatch, capsys
):
    """阻断C 回归：从无 docs/ 的任意 cwd 跑 ledger_entry 场景 → 缺省路径照常 ✅ 写入。

    cwd 切到 tmp 下无清单的子目录——修复前相对缺省路径在此落空（warning）；
    修复后缺省取仓库根锚定常量（此处以 tmp 清单替身注入验证同一机制），
    台账真写入（✅ + fn(run_demo) 锚点）。
    """
    ledger = _tmp_ledger(tmp_path, entry="B21")
    foreign = tmp_path / "elsewhere"
    foreign.mkdir()
    monkeypatch.chdir(foreign)  # cwd 无 docs/（修复前相对路径即在此找不到清单）
    monkeypatch.setattr(rd, "DEFAULT_LEDGER_PATH", str(ledger))
    scenario = _write_scenario_file(foreign, _GB_FILE_YAML)  # ledger_entry: B21
    assert run_demo([scenario]) == 0
    text = ledger.read_text(encoding="utf-8")
    assert "✅" in text and "fn(run_demo)" in text  # 台账真写入（锚点可回溯）
    assert _summary_of(capsys)["ledger"] == "updated"


def test_ledger_flag_overrides_default_path(tmp_path, monkeypatch, capsys):
    """阻断C 回归：'--ledger' 显式路径覆盖缺省（缺省不可达仍写入指定清单）。"""
    ledger = _tmp_ledger(tmp_path, entry="B21")
    monkeypatch.chdir(tmp_path)
    # 缺省指向不存在的路径——覆盖生效则不受影响（--ledger 优先级见证）
    monkeypatch.setattr(rd, "DEFAULT_LEDGER_PATH", str(tmp_path / "nope" / "missing.md"))
    scenario = _write_scenario_file(tmp_path, _GB_FILE_YAML)
    assert run_demo([scenario, "--ledger", str(ledger)]) == 0
    assert "✅" in ledger.read_text(encoding="utf-8")  # 覆盖路径真写入
    assert _summary_of(capsys)["ledger"] == "updated"


# ---------- ⑤ 运行成败口径：报告失败=exit 1 / 溯源失败≠run 失败 / status=failed ----------


def test_demo_pipeline_report_failure_is_run_failure(tmp_path, monkeypatch, capsys):
    def raise_build(run_dir, payload):
        raise RuntimeError("报告渲染失败（口径见证）")

    caps = wire(monkeypatch, tmp_path, build=raise_build)
    rc = run_demo([str(tmp_path / "scene.yaml")])
    assert rc == 1  # 口径：报告失败=运行失败（异常经 manage_run 停发射收尾标 failed）
    err = capsys.readouterr().err
    assert "运行失败" in err and "报告渲染失败" in err
    assert caps["states"] == ["running"]  # 发射态迁移先于失败（manage_run 内先停发射）
    assert caps["update"] == []  # 失败路径不触台账


def test_demo_pipeline_traceability_mismatch_not_fatal(tmp_path, monkeypatch, capsys):
    # a) mismatch：passed=False 附注——run 仍成功
    wire(
        monkeypatch,
        tmp_path,
        verify={"passed": False, "mismatches": [{"value": -3.5, "unit": "dB", "line_no": 9}]},
    )
    assert run_demo([str(tmp_path / "scene.yaml")]) == 0
    assert _summary_of(capsys)["trace"] == "failed"
    # b) 溯源自身异常（报告缺失 ValueError）：同样不反杀运行
    wire(monkeypatch, tmp_path, verify=ValueError("报告文件不存在"))
    assert run_demo([str(tmp_path / "scene.yaml")]) == 0
    assert _summary_of(capsys)["trace"] == "failed"


def test_demo_pipeline_scenario_failed_status_exit1(tmp_path, monkeypatch, capsys):
    wire(
        monkeypatch,
        tmp_path,
        execute_result={
            "status": "failed",  # 判据触发（gb 口径）——manage_run done 也不算成功
            "result": {"failure_levels": [{"step": 1, "target_db": 0.0}]},
            "streams_note": "wiring",
        },
    )
    assert run_demo([str(tmp_path / "scene.yaml")]) == 1
    match = _summary_of(capsys)
    assert match["status"] == "failed"
    assert match["n"] == "1"


# ---------- ⑥ 分派与结果贯通：distance / 时钟口径 / record 开关 ----------


def test_demo_pipeline_distance_dispatch(tmp_path, monkeypatch):
    scenario = base_scenario(
        scenario_type="distance",
        distances=[1.0, 10.0],
        model_params={"d0_m": 1.0, "l0_db": 20.0, "n": 2.0, "x_sigma": 0.0},
    )
    caps = wire(monkeypatch, tmp_path, scenario=scenario)
    assert run_demo([str(tmp_path / "scene.yaml")]) == 0
    assert caps["es"][0][1]["scenario_type"] == "distance"  # 装载→分派透传


def test_demo_pipeline_clock_ref_into_report_result(tmp_path, monkeypatch):
    caps = wire(monkeypatch, tmp_path)
    assert run_demo([str(tmp_path / "scene.yaml")]) == 0
    payload = caps["build"][0]
    assert payload["clock_ref"] == "software"  # 时基口径入报告结果（真 resolve：无 GPSDO）
    assert payload["backend"] == "sim"
    assert payload["simulated_parts"]  # sim 后端：脚注模拟段声明


def test_demo_pipeline_record_key_switch(tmp_path, monkeypatch):
    caps_default = wire(monkeypatch, tmp_path)
    assert run_demo([str(tmp_path / "scene.yaml")]) == 0
    assert caps_default["streams"][0]["record"] is False  # 'record' 场景键缺省 False
    caps_on = wire(monkeypatch, tmp_path, scenario=base_scenario(record=True))
    assert run_demo([str(tmp_path / "scene.yaml")]) == 0
    assert caps_on["streams"][0]["record"] is True  # 场景 record=True → 采集路开录制
    assert caps_on["streams"][0]["monitor"]["target_band"] == (2400.0, 2483.5)  # bands 首对


# ---------- ⑦ B21 终批复核：场景文件路线（高#1）/ distance 落盘（中#2） ----------


def _write_scenario_file(tmp_path, text, name="scenario.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


#: 高#1 见证场景文件：执行信封键（scenario_type/judge_min_samples/dwell_s/
#: baseline_samples/record/ledger_entry）+ 红线信封键齐备的合法 gb42590 场景。
_GB_FILE_YAML = """\
style: tone
fs: 1.0e6
freq_hz: 2.4e9
power_dbm: -10
duration_s: 0.005
backend: sim
scenario_type: gb42590
judge_min_samples: 2
dwell_s: 0.0
baseline_samples: 10
record: false
ledger_entry: B21
bands:
  - [2400.0, 2483.5]
shielded_box: true
dut_scope: self_built
"""

#: 中#2 见证场景文件：distance 场景（执行信封 distances/model_params 随文件进出）。
_DISTANCE_FILE_YAML = """\
style: tone
fs: 1.0e6
freq_hz: 2.4e9
power_dbm: -10
duration_s: 0.005
backend: sim
scenario_type: distance
judge_min_samples: 2
distances:
  - 1.0
  - 10.0
model_params:
  d0_m: 1.0
  l0_db: 20.0
  n: 2.0
  x_sigma: 0.0
bands:
  - [2400.0, 2483.5]
shielded_box: true
dut_scope: self_built
"""


def test_b21_high1_scenario_file_with_envelope_keys_full_run_exit0(
    tmp_path, monkeypatch, capsys
):
    """高#1 回归：含 scenario_type 等执行信封键的合法场景文件经 run_demo 真跑 exit 0。

    修复前 validate 未知键全拒（scenario_type/judge_min_samples/dwell_s/
    baseline_samples/record/ledger_entry 均报「未知键」）——场景文件路线整条
    死路；修复后装载通过、sim 后端全流程完成（真 run_dir/报告/台账 updated）。
    """
    monkeypatch.chdir(tmp_path)  # runs/ 落 tmp，不污染仓库
    # 台账文件就位（--ledger 显式指向 tmp 清单）：B21 行真实可更新（updated 见证）
    ledger = tmp_path / "docs" / "全功能实现清单-技术支持版.md"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        "| 编号 | 描述 | 状态 |\n|---|---|---|\n| B21 | 一键命令编排 |  |\n",
        encoding="utf-8",
    )
    path = _write_scenario_file(tmp_path, _GB_FILE_YAML)
    rc = run_demo([path, "--ledger", str(ledger)])
    assert rc == 0
    match = _summary_of(capsys)
    assert match["status"] == "completed"
    assert match["ledger"] == "updated"  # ledger_entry: B21 生效（台账真更新）
    run_dir = match["run_dir"]
    assert os.path.isfile(os.path.join(run_dir, "report.md"))  # 全流程走完
    with open(os.path.join(run_dir, "result.json"), encoding="utf-8") as handle:
        result_json = json.load(handle)
    # execute 返回并入 result（B21 中#2 机制对全类型生效）：gb 内层结果可见
    assert result_json["scenario_result"]["result"]["status"] == "completed"


def test_b21_mid2_distance_run_leaves_traces_in_all_three_artifacts(
    tmp_path, monkeypatch, capsys
):
    """中#2 回归：distance 真跑后 events.jsonl/kpi.csv/result.json 各含 distance 痕迹。

    修复前 distance 结果（distance_plan/kpi_rows）只活在返回对象里不落盘；
    修复后每档一条 type='distance_step' 事件 + kpi.csv 距离档行（record_run_streams
    'w' 重写后重追加保住）+ result.json 'scenario_result' 携 distance_plan。
    """
    monkeypatch.chdir(tmp_path)
    path = _write_scenario_file(tmp_path, _DISTANCE_FILE_YAML)
    rc = run_demo([path, "--no-ledger"])
    assert rc == 0
    match = _summary_of(capsys)
    assert match["status"] == "completed"
    run_dir = match["run_dir"]

    # a) events.jsonl：每档一条 distance_step 事件（d_m/loss_db/attenuation/judge_per_mean）
    with open(os.path.join(run_dir, "events.jsonl"), encoding="utf-8") as handle:
        events = [json.loads(line) for line in handle if line.strip()]
    step_events = [e for e in events if e.get("type") == "distance_step"]
    assert len(step_events) == 2  # distances 两个可达档
    assert [e["d_m"] for e in step_events] == [1.0, 10.0]
    assert all("attenuation" in e and "judge_per_mean" in e and "loss_db" in e for e in step_events)

    # b) kpi.csv：距离档 KPI 行（采集路 'w' 重写后重追加仍在）
    with open(os.path.join(run_dir, "kpi.csv"), encoding="utf-8") as handle:
        kpi_text = handle.read()
    assert kpi_text.count("distance_step") == 2  # per_note 列携档位溯源
    header_cells = kpi_text.splitlines()[0].split(",")
    assert header_cells[:3] == ["timestamp_ms", "link", "source"]  # record_run_streams 表头
    distance_rows = [line for line in kpi_text.splitlines() if "distance_step" in line]
    cells = distance_rows[0].split(",")
    assert cells[header_cells.index("link")] == "distance"
    assert cells[header_cells.index("per")] == cells[header_cells.index("judge_per")]

    # c) result.json：'scenario_result' 携 distance_plan/kpi_rows
    with open(os.path.join(run_dir, "result.json"), encoding="utf-8") as handle:
        result_json = json.load(handle)
    inner = result_json["scenario_result"]["result"]
    assert [p["d_m"] for p in inner["distance_plan"]["points"]] == [1.0, 10.0]
    assert len(inner["kpi_rows"]) == 2


# ---------- ⑧ 无头入口 run_scenario（阻断①(a)）：真跑/三态返回/台账缺省不动 ----------


def headless_scenario(**over):
    """run_scenario 入参形状：完整场景 dict（含声明信封键）——未知键零容忍，
    不含执行期私有键 'dut'（该键仅 --demo 内置场景直携）。"""
    scenario = {
        "style": "tone",
        "fs": 1.0e6,
        "freq_hz": 2.4e9,
        "power_dbm": -10.0,
        "duration_s": 0.005,
        "backend": "sim",
        "scenario_type": "gb42590",
        "judge_min_samples": 2,
        "dwell_s": 0.0,
        "baseline_samples": 10,
        "record": False,
        "sim_events": [{"type": "power_step", "jsr_db": -20.0, "ts": 0.0}],
        "bands": [[2400.0, 2483.5]],
        "shielded_box": True,
        "dut_scope": "self_built",
    }
    scenario.update(over)
    return scenario


def test_run_scenario_real_run_completed_report_generated(tmp_path, monkeypatch):
    """run_scenario 真跑：完整场景 dict→completed/exit 0，out_root 下 run 目录+
    report.md 真实生成（与 CLI 共享 _execute_pipeline，场景执行全真实）。"""
    monkeypatch.chdir(tmp_path)  # 其余副作用（若有）落 tmp
    out_root = tmp_path / "reports"
    result = run_scenario(headless_scenario(), out_root=str(out_root))
    assert result["status"] == "completed"
    assert result["exit_code"] == 0
    assert result["failure_levels"] == 0
    run_dir = Path(result["run_dir"])
    assert run_dir.is_dir() and str(run_dir).startswith(str(out_root))  # out_root 生效
    assert (run_dir / "report.md").is_file()  # 报告真实生成
    assert result["report_path"] == str(run_dir / "report.md")
    assert result["summary"].startswith("run_scenario: run_dir=")
    assert "ledger=skipped(ledger_off)" in result["summary"]  # 台账缺省不动


def test_run_scenario_validation_failed_returns_exit2():
    """校验失败（未知样式）不抛：返回 validation_failed dict（exit_code=2 口径）。"""
    result = run_scenario(headless_scenario(style="quantum"))
    assert result["status"] == "validation_failed"
    assert result["exit_code"] == 2
    assert result["run_dir"] is None
    assert result["report_path"] is None
    assert "style" in result["error"]


def test_run_scenario_guard_rejected_returns_exit2():
    """红线拒绝（power 超 0dBm）同走校验失败口径：[power] 条款可见。"""
    result = run_scenario(headless_scenario(power_dbm=10.0))
    assert result["status"] == "validation_failed"
    assert result["exit_code"] == 2
    assert "[power]" in result["error"]


def test_run_scenario_unknown_backend_failed_exit1():
    """后端失败：failed dict（exit_code=1）+ 降级建议（不抛）。"""
    result = run_scenario(headless_scenario(), backend="nosuch-backend")
    assert result["status"] == "failed"
    assert result["exit_code"] == 1
    assert result["run_dir"] is None
    assert "后端启动失败" in result["summary"]
    assert "降级" in result["summary"]


def test_run_scenario_bad_input_raises_valueerror():
    """入参形状错（非 dict 场景/负 dwell）抛 ValueError——编程错误早暴露。"""
    with pytest.raises(ValueError):
        run_scenario("tone.yaml")  # 非 dict（名解析归 serve_console，不在此收 str）
    with pytest.raises(ValueError):
        run_scenario(headless_scenario(), dwell_s=-1.0)


def test_run_scenario_dwell_passthrough(tmp_path, monkeypatch):
    """dwell_s 覆盖透传 scenario['dwell_s']（CLI --dwell 同口径）。"""
    caps = wire(monkeypatch, tmp_path)
    assert run_scenario(headless_scenario(), dwell_s=0.25)["exit_code"] == 0
    assert caps["es"][0][1]["dwell_s"] == 0.25  # 覆盖写入场景对象


def test_run_scenario_ledger_default_off_opt_in(tmp_path, monkeypatch):
    """台账口径：缺省 ledger=False 不动台账（操控台语义）；显式 True 时场景含
    ledger_entry 才更新（同 CLI --no-ledger 未给口径）。"""
    caps = wire(monkeypatch, tmp_path, scenario=headless_scenario(ledger_entry="B1"))
    result = run_scenario(headless_scenario(ledger_entry="B1"))
    assert result["exit_code"] == 0
    assert caps["update"] == []  # 缺省不动台账
    assert "ledger=skipped(ledger_off)" in result["summary"]
    result_on = run_scenario(headless_scenario(ledger_entry="B1"), ledger=True)
    assert result_on["exit_code"] == 0
    assert len(caps["update"]) == 1  # opt-in：ledger_entry 触发一次
    entry_id, anchor = caps["update"][0]
    assert entry_id == "B1" and "fn(run_demo)" in anchor
    assert "ledger=updated" in result_on["summary"]


def test_run_scenario_backend_param_precedence_over_scenario_key(tmp_path, monkeypatch):
    """backend 参数 > 场景 'backend' 键 > 'auto' 探测（CLI --backend 同决策序）。"""
    caps = wire(monkeypatch, tmp_path)
    assert run_scenario(headless_scenario(), backend="sim")["exit_code"] == 0
    assert caps["explicit"][-1] == "sim"  # 参数最优先
    assert run_scenario(headless_scenario())["exit_code"] == 0
    assert caps["explicit"][-1] == "sim"  # 缺省回落场景键（非 auto）
    assert run_scenario(headless_scenario(backend="auto"))["exit_code"] == 0
    assert caps["explicit"][-1] is None  # 'auto' → 探测


# ---------- B24 C1：run_scenario 急停协作停（stop 容器贯通/档间检查/归一 stopped） ----------


def test_run_scenario_stop_none_keeps_existing_semantics(tmp_path, monkeypatch):
    """stop=None（缺省，无急停方）语义不变：正常 completed，容器不参与。"""
    caps = wire(monkeypatch, tmp_path)
    result = run_scenario(headless_scenario(), out_root=str(tmp_path / "r"))
    assert result["status"] == "completed" and result["exit_code"] == 0
    assert caps["es"]  # 执行分派照常发生


def test_run_scenario_stop_container_receives_backend_handle(tmp_path, monkeypatch):
    """后端句柄注册：stop 容器传入后，autodetect 打开的后端写回 stop['backend']
    ——急停方直停真后端的通道（B24 C1）。"""
    wire(monkeypatch, tmp_path)
    stop = {"flag": False}
    assert run_scenario(headless_scenario(), out_root=str(tmp_path / "r"), stop=stop)[
        "status"
    ] == "completed"
    assert isinstance(stop.get("backend"), _FakeBackend)  # 真实句柄写回


def test_run_scenario_stop_bad_shape_raises_valueerror():
    """stop 非 dict|None→ValueError（入参形状错早暴露，同 dwell_s 口径）。"""
    with pytest.raises(ValueError, match="stop"):
        run_scenario(headless_scenario(), stop=["flag"])


def test_run_scenario_preset_stop_flag_aborts_at_stage_boundary(tmp_path, monkeypatch):
    """旗先置位（阶段边界检查）：运行启动边界即协作中止——status='stopped'、
    exit_code=1（未完成口径）、events.jsonl 落 emergency_stop 事件留痕。"""
    caps = wire(monkeypatch, tmp_path)
    stop = {"flag": True}
    result = run_scenario(headless_scenario(), out_root=str(tmp_path / "r"), stop=stop)
    assert result["status"] == "stopped"
    assert result["exit_code"] == 1  # 中断语义：场景执行未完成
    assert result["run_dir"] and Path(result["run_dir"]).is_dir()
    assert "急停" in result["summary"] and "stopped" in result["summary"]
    assert result["error"] and "协作中止" in result["error"]
    assert caps["es"] == []  # 执行分派前即中止（运行启动边界）
    events_path = Path(result["run_dir"]) / "events.jsonl"
    lines = [json.loads(x) for x in events_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert any(e.get("type") == "emergency_stop" and e.get("status") == "stopped" for e in lines)


def test_run_scenario_stop_between_stages_aborts_before_report(tmp_path, monkeypatch):
    """阶段边界检查（采集→报告）：执行完成后、报告前置旗——报告不落盘，
    归一 stopped（事件留痕同口径）。"""
    caps = wire(monkeypatch, tmp_path)
    stop = {"flag": False}

    def _raise_after_streams(ctx, max_kpi_rows=10000, max_monitor_blocks=1000):
        caps["streams"].append(ctx)
        stop["flag"] = True  # 采集完成后置旗（下一阶段边界=报告前）
        return {"kpi_rows": 0, "monitor_blocks": 0, "stats_rows": 0,
                "alignment": {}, "recording": None, "streams_note": []}

    monkeypatch.setattr(rd, "record_run_streams", _raise_after_streams)
    result = run_scenario(headless_scenario(), out_root=str(tmp_path / "r"), stop=stop)
    assert result["status"] == "stopped" and result["exit_code"] == 1
    assert caps["es"]  # 执行分派已发生
    assert caps["build"] == []  # 报告前中止——build_report 未被调
    assert result["report_path"] is None


def test_stop_checked_events_generator_raises_when_flag_set():
    """sim 事件流协作停包装（功率档间检查点）：旗置位后下一次拉事件即抛
    EmergencyStopRequested；旗未置位时事件原样透传。"""
    events = [{"type": "power_step", "jsr_db": -20.0, "ts": float(i)} for i in range(4)]
    stop = {"flag": False}
    wrapped = rd._stop_checked_events(iter(events), stop)
    assert next(wrapped) == events[0]  # 旗未置位：透传
    stop["flag"] = True
    with pytest.raises(rd.EmergencyStopRequested, match="档间检查"):
        next(wrapped)
    # stop=None（非 dict）形状忽略：永远透传
    plain = list(rd._stop_checked_events(iter(events), None))
    assert plain == events


def test_run_scenario_mid_ladder_stop_real_sim_terminates_early(tmp_path):
    """真管线档间急停（决定性单测路径）：dwell 0.4×6 档自然时长 ≥2.4s，运行
    ~0.55s 置旗——sim 事件流档间检查触发「先停发射再退出」，wall time 明显
    短于自然时长，结果归一 stopped（status/事件/提前终止三要素齐）。"""
    import threading

    out_root = tmp_path / "reports"
    stop = {"flag": False}
    # 事件源须覆盖阶梯（档间检查点=逐事件拉取；缺省 _sim_events 10 事件 ≥ 6 档）：
    # jsr=-20 恒不触发判据，6 档全走 = 自然时长 ≥6×dwell。
    scenario = headless_scenario(
        dwell_s=0.4,
        sim_events=[
            {"type": "power_step", "jsr_db": -20.0, "ts": float(i)} for i in range(10)
        ],
    )
    timer = threading.Timer(0.55, lambda: stop.update(flag=True))
    timer.start()
    started = time.monotonic()
    try:
        result = run_scenario(scenario, out_root=str(out_root), stop=stop)
    finally:
        timer.cancel()
    elapsed = time.monotonic() - started
    assert result["status"] == "stopped" and result["exit_code"] == 1
    assert elapsed < 2.2  # 明显短于自然时长（≥2.4s 纯 dwell + 基线/收尾）
    run_dir = Path(result["run_dir"])
    events = [
        json.loads(x)
        for x in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    types = [e.get("type") for e in events]
    assert "emergency_stop" in types  # 急停原因入事件流
    assert "power_step" in types  # 确曾进入阶梯（档间中止而非启动边界）
    assert types.count("power_step") < 6  # 阶梯未走完（提前终止实证）
