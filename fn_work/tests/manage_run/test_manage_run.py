"""manage_run 对抗测试：状态机生命周期+八件套工作区+先停发射收尾+异常透传（slug=run_lifecycle）。"""
import json
import os
import shutil

import pytest

from src.manage_run import append_run_log as append_run_log_module
from src.manage_run.create_run_workspace import RunDirError
from src.manage_run.manage_run import LifecycleError, manage_run

# 八件套规范名（与 create_run_workspace.WORKSPACE_FILES 一致）
EIGHT = [
    "scenario.yaml",
    "kpi.csv",
    "events.jsonl",
    "monitor.csv",
    "recordings",
    "report.md",
    "plots",
    "run.log",
]


class MockBackend:
    """记录调用的发射后端 mock：stop_tx 与 set_tx_gain(0) 全成功。"""

    def __init__(self):
        self.calls = []

    def stop_tx(self):
        self.calls.append("stop_tx")

    def set_tx_gain(self, value):
        self.calls.append(("set_tx_gain", value))


def read_run_log(run_dir):
    """解析 run.log 为记录清单（每行一个 JSON 对象）。"""
    records = []
    with open(os.path.join(run_dir, "run.log"), encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw:
                records.append(json.loads(raw))
    return records


def log_transitions(run_dir):
    """按落盘顺序提取状态迁移序 [(from, to), ...]。"""
    return [
        (rec["ctx"]["from"], rec["ctx"]["to"])
        for rec in read_run_log(run_dir)
        if rec.get("ctx", {}).get("event") == "state_transition"
    ]


def read_result_json(run_dir):
    with open(os.path.join(run_dir, "result.json"), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(autouse=True)
def isolated_log_buffer(monkeypatch):
    """模块级隔离 append_run_log 的进程级降级缓冲：每个测试拿到空缓冲，测试后复原。"""
    monkeypatch.setattr(append_run_log_module, "_BUFFER", [])


def run_once(tmp_path, execute, backend=None):
    """以 tmp_path 隔离的 runs_root 跑一次 manage_run。"""
    return manage_run(
        {"freq_mhz": 1000, "style": "tone", "power_db": 0},
        execute,
        runs_root=str(tmp_path / "runs"),
        backend=backend,
    )


def test_run_lifecycle_normal_done(tmp_path):
    """正常路径：execute 返回 → done + 八件套齐 + result.json status=done + run.log 含迁移序。"""
    out = run_once(tmp_path, lambda ctx: "返回值不入结果")
    assert out["status"] == "done"
    assert out["result"]["finalized"] is True
    assert out["result"]["missing"] == []
    run_dir = out["run_dir"]
    assert os.path.isdir(run_dir)
    for name in EIGHT:
        assert os.path.exists(os.path.join(run_dir, name)), f"八件套缺: {name}"
    result = read_result_json(run_dir)
    assert result["status"] == "done"
    assert result["exit_semantics"] == "done"
    assert log_transitions(run_dir) == [
        ("starting", "armed"),
        ("armed", "stopping"),
        ("stopping", "done"),
    ]


def test_run_lifecycle_execute_error_failed(tmp_path):
    """execute 抛 RuntimeError → 停发射+ERROR 日志+finalize(failed) 后原异常类型保真重抛。"""
    backend = MockBackend()
    holder = {}

    def boom(ctx):
        holder["run_dir"] = ctx["run_dir"]
        raise RuntimeError("链路失步")

    with pytest.raises(RuntimeError, match="链路失步"):
        run_once(tmp_path, boom, backend=backend)

    assert "stop_tx" in backend.calls  # 先停发射
    assert ("set_tx_gain", 0) in backend.calls
    result = read_result_json(holder["run_dir"])
    assert result["status"] == "failed"
    assert result["stop_result_recorded"] is True  # stop_result 在案
    assert result["stop_result"]["status"] == "stopped"
    assert any(
        step["op"] == "stop_tx" and step["ok"] for step in result["stop_result"]["steps"]
    )
    errors = [rec for rec in read_run_log(holder["run_dir"]) if rec["level"] == "ERROR"]
    assert len(errors) == 1
    assert "RuntimeError" in errors[0]["msg"] and "链路失步" in errors[0]["msg"]
    assert log_transitions(holder["run_dir"])[-1] == ("stopping", "failed")


def test_run_lifecycle_set_state_running_legal(tmp_path):
    """execute 内 ctx['set_state']('running') 为合法迁移，全程迁移序完整落盘。"""
    out = run_once(tmp_path, lambda ctx: ctx["set_state"]("running"))
    assert out["status"] == "done"
    assert log_transitions(out["run_dir"]) == [
        ("starting", "armed"),
        ("armed", "running"),
        ("running", "stopping"),
        ("stopping", "done"),
    ]


def test_run_lifecycle_done_then_set_state_rejected(tmp_path):
    """done 后再 set_state → LifecycleError（from/to 保真），且先走完失败收尾再透传。"""
    holder = {}

    def execute(ctx):
        ctx["set_state"]("running")
        ctx["set_state"]("stopping")
        ctx["set_state"]("done")
        holder["run_dir"] = ctx["run_dir"]
        ctx["set_state"]("running")  # 终态再迁移：非法

    with pytest.raises(LifecycleError) as excinfo:
        run_once(tmp_path, execute)
    assert excinfo.value.from_state == "done"
    assert excinfo.value.to_state == "running"
    assert "done -> running" in str(excinfo.value)
    assert read_result_json(holder["run_dir"])["status"] == "failed"  # 异常路径已收尾落盘


def test_run_lifecycle_skip_level_transition_rejected(tmp_path):
    """armed 直接跳级 done → LifecycleError（只允许经 stopping 入终态）。"""
    with pytest.raises(LifecycleError) as excinfo:
        run_once(tmp_path, lambda ctx: ctx["set_state"]("done"))
    assert excinfo.value.from_state == "armed"
    assert excinfo.value.to_state == "done"


def test_run_lifecycle_unknown_state_name_rejected(tmp_path):
    """迁移到未知状态名 → LifecycleError，to_state 保真。"""
    with pytest.raises(LifecycleError) as excinfo:
        run_once(tmp_path, lambda ctx: ctx["set_state"]("teleport"))
    assert excinfo.value.from_state == "armed"
    assert excinfo.value.to_state == "teleport"


def test_run_lifecycle_ctx_log_writes_run_log(tmp_path):
    """execute 内经 ctx['log'] 记的日志落到 run.log（level/msg/ctx 字段保真）。"""
    holder = {}

    def execute(ctx):
        ctx["log"]("INFO", "回调自定义日志", {"stage": "mid"})
        holder["run_dir"] = ctx["run_dir"]

    run_once(tmp_path, execute)
    hits = [rec for rec in read_run_log(holder["run_dir"]) if rec["msg"] == "回调自定义日志"]
    assert len(hits) == 1
    assert hits[0]["level"] == "INFO"
    assert hits[0]["ctx"]["stage"] == "mid"


def test_run_lifecycle_backend_stopped_on_normal_path(tmp_path):
    """正常路径同样停发射：backend mock 的 stop_tx/set_tx_gain(0) 被调且结果入 result.json。"""
    backend = MockBackend()
    out = run_once(tmp_path, lambda ctx: None, backend=backend)
    assert "stop_tx" in backend.calls
    assert ("set_tx_gain", 0) in backend.calls
    result = read_result_json(out["run_dir"])
    assert result["stop_result_recorded"] is True
    assert result["stop_result"]["status"] == "stopped"
    assert result["backend"] == "MockBackend"  # 句柄实例以类名入 JSON


def test_run_lifecycle_runs_root_is_file_raises_run_dir_error(tmp_path):
    """runs_root 父路径为文件 → create_run_workspace 抛 RunDirError 原样透传（退出码 1 语义）。"""
    blocker = tmp_path / "blocker"
    blocker.write_text("占位文件", encoding="utf-8")
    with pytest.raises(RunDirError):
        manage_run({}, lambda ctx: None, runs_root=str(blocker))


def test_run_lifecycle_missing_plots_still_done(tmp_path):
    """finalize 缺件（execute 删掉 plots）→ result.missing 含 plots 但 status 仍 done。"""
    out = run_once(
        tmp_path, lambda ctx: shutil.rmtree(os.path.join(ctx["run_dir"], "plots"))
    )
    assert out["status"] == "done"
    assert "plots" in out["result"]["missing"]
    result = read_result_json(out["run_dir"])
    assert result["status"] == "done"
    assert "plots" in result["missing"]


def test_run_lifecycle_two_runs_independent(tmp_path):
    """二次调用互不干扰：两次 run_dir 不同，各自八件套+result.json 完整。"""
    out1 = run_once(tmp_path, lambda ctx: None)
    out2 = run_once(tmp_path, lambda ctx: None)
    assert out1["run_dir"] != out2["run_dir"]
    expected = set(EIGHT) | {"result.json"}
    for out in (out1, out2):
        assert out["status"] == "done"
        assert set(os.listdir(out["run_dir"])) == expected


def test_run_lifecycle_keyboard_interrupt_stops_then_reraises(tmp_path):
    """回调抛 KeyboardInterrupt（BaseException）→ 同样先停发射+落盘 failed 再透传。"""
    backend = MockBackend()
    holder = {}

    def interrupt(ctx):
        holder["run_dir"] = ctx["run_dir"]
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_once(tmp_path, interrupt, backend=backend)
    assert "stop_tx" in backend.calls  # 先停发射再透传
    result = read_result_json(holder["run_dir"])
    assert result["status"] == "failed"
    assert any(rec["level"] == "ERROR" for rec in read_run_log(holder["run_dir"]))


def test_run_lifecycle_degraded_lines_replayed_to_run_log(tmp_path):
    """运行中 run.log 写失败进降级缓冲 → wind_down 重放落盘：run.log 含该行且 log_degraded=False。"""
    holder = {}

    def execute(ctx):
        holder["run_dir"] = ctx["run_dir"]
        log_path = os.path.join(ctx["run_dir"], "run.log")
        os.remove(log_path)
        os.mkdir(log_path)  # run.log 变目录 → 追加失败 → 静默降级进内存缓冲
        degraded = ctx["log"]("WARN", "磁盘满期间滞留的日志", {"stage": "mid-run"})
        assert degraded["written"] is False and degraded["degraded"] is True
        os.rmdir(log_path)  # 磁盘恢复：run.log 重新可写
        with open(log_path, "w", encoding="utf-8"):
            pass

    out = run_once(tmp_path, execute)
    assert out["status"] == "done"
    hits = [
        rec for rec in read_run_log(out["run_dir"]) if rec["msg"] == "磁盘满期间滞留的日志"
    ]
    assert len(hits) == 1  # 缓冲行重放恰好落盘一次，不重复
    assert hits[0]["level"] == "WARN"
    assert hits[0]["ctx"]["stage"] == "mid-run"
    result = read_result_json(out["run_dir"])
    assert result["log_degraded"] is False  # 重放成功：日志链路未降级
    assert "log_degraded" not in out["result"]  # finalize 返回值未被无端注入


def test_run_lifecycle_degraded_lines_stranded_marks_log_degraded(tmp_path):
    """缓冲行重放仍失败（run.log 一直是目录）→ result.json 的 log_degraded 补正为 True。

    该场景 run.log 存在（目录也算存在，不入 missing）且无句柄封存失败，
    finalize_run 自身只会判 False——正是降级缓冲信号要接入的缺口。
    """
    holder = {}

    def execute(ctx):
        holder["run_dir"] = ctx["run_dir"]
        log_path = os.path.join(ctx["run_dir"], "run.log")
        os.remove(log_path)
        os.mkdir(log_path)  # 持续占位：wind_down 的重放也失败 → 行滞留内存
        assert ctx["log"]("ERROR", "彻底滞留的日志", None)["degraded"] is True

    out = run_once(tmp_path, execute)
    assert out["status"] == "done"
    result = read_result_json(out["run_dir"])
    assert result["status"] == "done"
    assert result["missing"] == []  # 八件套齐全：降级标记并非来自缺件
    assert result["log_degraded"] is True  # 来自滞留行信号的补正
    assert out["result"]["log_degraded"] is True  # 返回值同步修正
    assert append_run_log_module.buffered_lines()  # 行确实滞留在内存缓冲


def test_run_lifecycle_buffer_recovered_not_polluting_next_run(tmp_path):
    """跨运行缓冲（A 降级+恢复）：A 的滞留行由 A 自己的 wind_down 落回 A 的 run.log；
    缓冲清空，B 运行的 run.log 绝不含 A 的行。"""
    holder = {}

    def execute_a(ctx):
        holder["a_dir"] = ctx["run_dir"]
        log_path = os.path.join(ctx["run_dir"], "run.log")
        os.remove(log_path)
        os.mkdir(log_path)  # run.log 变目录 → A 运行日志降级进缓冲
        assert ctx["log"]("WARN", "A 运行滞留行", {"run": "A"})["degraded"] is True
        os.rmdir(log_path)  # A 恢复：A 自己收尾时重放应成功
        with open(log_path, "w", encoding="utf-8"):
            pass

    out_a = run_once(tmp_path, execute_a)
    assert out_a["status"] == "done"
    assert any(rec["msg"] == "A 运行滞留行" for rec in read_run_log(holder["a_dir"]))
    assert append_run_log_module.buffered_lines() == []  # 重放成功后缓冲已清空

    out_b = run_once(tmp_path, lambda ctx: None)
    assert out_b["run_dir"] != holder["a_dir"]
    b_msgs = [rec["msg"] for rec in read_run_log(out_b["run_dir"])]
    assert "A 运行滞留行" not in b_msgs  # B 的 run.log 不收编 A 的行
    assert append_run_log_module.buffered_lines() == []  # B 运行后缓冲仍空


def test_run_lifecycle_stranded_lines_not_absorbed_by_next_run(tmp_path):
    """跨运行缓冲（A 持续失败）：A 的滞留行留在内存缓冲不被 B 运行收编——
    B 的 run.log 不含 A 的行，行仍滞留缓冲且归属 A（B 的 drain 只归还不落盘）。"""
    holder = {}

    def execute_a(ctx):
        holder["a_dir"] = ctx["run_dir"]
        log_path = os.path.join(ctx["run_dir"], "run.log")
        os.remove(log_path)
        os.mkdir(log_path)  # A 的 run.log 持续是目录：A 收尾重放也失败 → 行滞留缓冲
        assert ctx["log"]("ERROR", "A 运行彻底滞留", {"run": "A"})["degraded"] is True

    out_a = run_once(tmp_path, execute_a)
    assert out_a["status"] == "done"
    assert append_run_log_module.buffered_lines()  # A 的行滞留内存缓冲

    out_b = run_once(tmp_path, lambda ctx: None)  # B 运行目录完全健康
    assert out_b["status"] == "done"
    b_msgs = [rec["msg"] for rec in read_run_log(out_b["run_dir"])]
    assert "A 运行彻底滞留" not in b_msgs  # B 不收编 A 的滞留行
    stranded = append_run_log_module.buffered_lines()
    assert any("A 运行彻底滞留" in line for line in stranded)  # 行仍在缓冲（归属未变）
    # 归属仍是 A：B 的 drain 把他运行行原样归还（run_dir 字段为 A 目录）
    drained = append_run_log_module.drain_buffered_lines()
    try:
        assert drained and all(owner == holder["a_dir"] for owner, _ in drained)
    finally:
        append_run_log_module.restore_stranded_lines(drained)  # 复原：不污染后续用例


def test_run_lifecycle_same_backend_second_run_actually_stops(tmp_path):
    """同一 backend 连跑两轮 manage_run：每轮独立 run_token，第二轮收尾实际调用
    stop_tx 且增益归零（stop_result.status='stopped' 而非 'already_stopped'）。"""
    backend = MockBackend()
    out1 = run_once(tmp_path, lambda ctx: None, backend=backend)
    out2 = run_once(tmp_path, lambda ctx: None, backend=backend)
    assert backend.calls.count("stop_tx") == 2  # 两轮各实际停发射一次
    assert backend.calls.count(("set_tx_gain", 0)) == 2
    r1 = read_result_json(out1["run_dir"])
    r2 = read_result_json(out2["run_dir"])
    assert r1["stop_result"]["status"] == "stopped"
    assert r2["stop_result"]["status"] == "stopped"  # 第二轮不是 already_stopped


def test_run_lifecycle_ki_during_wind_down_still_finalizes(tmp_path, monkeypatch):
    """收尾段自身被 KI 打断（停发射步抛 KI 直穿）：兜底再 finalize 一次 →
    result.json 仍落盘（status=failed），随后 KI 继续透传（信号保留）。"""
    import src.manage_run.manage_run as mr_module

    def stop_raises_ki(backend=None, context=None, **kwargs):
        raise KeyboardInterrupt("停发射步被打断")

    monkeypatch.setattr(mr_module, "stop_transmit_safely", stop_raises_ki)
    holder = {}

    def execute(ctx):
        holder["run_dir"] = ctx["run_dir"]

    with pytest.raises(KeyboardInterrupt):
        run_once(tmp_path, execute)
    payload = read_result_json(holder["run_dir"])  # 兜底 finalize 已落盘
    assert payload["status"] == "failed"
    assert payload["exit_semantics"] == "failed"


def test_run_lifecycle_callback_self_failed_normal_return(tmp_path):
    """终态冲突：回调自推 failed 终态后正常返回 → wind_down 采纳回调终态，
    result.json status=failed（run.log 的 skip_stopping/final_state_conflict WARN 保留）。"""
    def execute(ctx):
        ctx["set_state"]("running")
        ctx["set_state"]("stopping")
        ctx["set_state"]("failed")  # 回调自判失败

    out = run_once(tmp_path, execute)
    payload = read_result_json(out["run_dir"])
    assert payload["status"] == "failed"  # 采纳回调终态，而非正常返回的 done
    assert payload["exit_semantics"] == "failed"
    assert out["status"] == "failed"  # 返回口径与 result.json 一致
    events = [rec.get("ctx", {}).get("event") for rec in read_run_log(out["run_dir"])]
    assert "skip_stopping" in events  # WARN 留痕
    assert "final_state_conflict" in events


def test_run_lifecycle_done_without_running_logs_skip_warning(tmp_path):
    """done 路径未经 running（回调从未申请发射态）→ run.log 自动 WARN
    skipped_running_state；经过 running 的运行不产生该 WARN。"""
    out = run_once(tmp_path, lambda ctx: None)  # 未 set_state('running')
    warns = [
        rec
        for rec in read_run_log(out["run_dir"])
        if rec.get("ctx", {}).get("event") == "skipped_running_state"
    ]
    assert len(warns) == 1
    assert warns[0]["level"] == "WARN"

    out_ran = run_once(tmp_path, lambda ctx: ctx["set_state"]("running"))
    assert not [
        rec
        for rec in read_run_log(out_ran["run_dir"])
        if rec.get("ctx", {}).get("event") == "skipped_running_state"
    ]
