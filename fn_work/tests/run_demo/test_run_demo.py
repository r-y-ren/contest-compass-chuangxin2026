"""run_demo 对抗用例：R44 CLI 总入口（slug=demo_pipeline）。

两路夹击：
- 真实路径：--demo 内置 sim 场景全流程（run_dir 八件套/report.md/溯源执行/exit 0）、
  双跑目录去重、坏场景文件 exit 2、未知后端 exit 1；
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

import pytest

import src.run_demo.run_demo as rd
from src.run_demo.run_demo import run_demo
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


# ---------- ① 真实路径：--demo 全流程 / 双跑 / 坏场景 / 坏后端 ----------


def test_demo_pipeline_demo_full_run_exit0(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # runs/ 落 tmp，不污染仓库
    rc = run_demo(["--demo"])
    assert rc == 0
    match = _summary_of(capsys)
    assert match["status"] == "completed"
    run_dir = match["run_dir"]
    assert os.path.isdir(run_dir)
    report = os.path.join(run_dir, "report.md")
    assert os.path.isfile(report)
    with open(report, encoding="utf-8") as handle:
        report_md = handle.read()
    assert "运行概要" in report_md  # 非八件套初始骨架——报告正文真生成
    assert match["trace"] == "passed"  # 溯源已执行且通过（数字纪律闭环）
    with open(os.path.join(run_dir, "result.json"), encoding="utf-8") as handle:
        result_json = json.load(handle)
    assert result_json["traceability"]["passed"] is True  # 'traceability' 附 run result


def test_demo_pipeline_demo_double_run_distinct_dirs(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert run_demo(["--demo"]) == 0
    first = _summary_of(capsys)["run_dir"]
    assert run_demo(["--demo"]) == 0
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
