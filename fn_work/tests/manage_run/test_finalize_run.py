"""finalize_run 单元测试——运行收尾：停发射确认、句柄封存、八件套缺项、结果 JSON（永不抛出）。"""
import json
import shutil
import time

from src.manage_run.finalize_run import finalize_run

# 八件套规范名（与被测模块 _EIGHT_ARTIFACTS 的规范名一致）
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

REQUIRED_RESULT_KEYS = {
    "status",
    "exit_semantics",
    "started_at",
    "finished_at",
    "duration_ms",
    "backend",
    "clock_ref",
    "stop_result",
    "missing",
    "log_degraded",
}


def make_workspace(tmp_path, skip=()):
    """在 tmp_path 下建一个八件套齐全的 run 目录，skip 中列出的产物不建。"""
    run_dir = tmp_path / "runs" / "20260101-000000"
    run_dir.mkdir(parents=True)
    for name in EIGHT:
        if name in skip:
            continue
        path = run_dir / name
        if name in ("recordings", "plots"):
            path.mkdir()
        else:
            path.write_text("placeholder\n", encoding="utf-8")
    return run_dir


def make_ctx(run_dir, **overrides):
    ctx = {
        "run_dir": str(run_dir),
        "started_at": time.time() - 0.25,
        "backend": "sim",
        "clock_ref": {"source": "software", "disciplined": False},
        "alignment_error": 0.42,
        "stop_result": {"stopped": True, "reason": "normal"},
        "open_files": [],
    }
    ctx.update(overrides)
    return ctx


def load_result(result_path):
    with open(result_path, encoding="utf-8") as fh:
        return json.load(fh)


class FakeHandle:
    """可控假句柄：可指定 flush/close 抛什么异常，记录自身是否被 close。"""

    def __init__(self, name="events.jsonl", flush_exc=None, close_exc=None):
        self.name = name
        self.closed = False
        self._flush_exc = flush_exc
        self._close_exc = close_exc

    def flush(self):
        if self._flush_exc is not None:
            raise self._flush_exc

    def close(self):
        if self._close_exc is not None:
            raise self._close_exc
        self.closed = True


# ---- 对抗用例 1：完整八件套 → done + missing 空 + result.json 可解析 ----


def test_full_workspace_done_missing_empty_and_parseable(tmp_path):
    run_dir = make_workspace(tmp_path)
    result = finalize_run(make_ctx(run_dir), "done")

    assert result["finalized"] is True
    assert result["missing"] == []
    payload = load_result(result["result_path"])
    assert payload["status"] == "done"
    assert payload["missing"] == []
    assert REQUIRED_RESULT_KEYS <= set(payload.keys())
    # result_path 指向 run_dir 内的 result.json
    assert result["result_path"] == str(run_dir / "result.json")


# ---- 对抗用例 2：缺 recordings 与 plots → missing 恰列两项 ----


def test_missing_recordings_and_plots_listed_exactly(tmp_path):
    run_dir = make_workspace(tmp_path, skip=("recordings", "plots"))
    result = finalize_run(make_ctx(run_dir), "done")

    assert result["finalized"] is True
    assert len(result["missing"]) == 2
    assert set(result["missing"]) == {"recordings", "plots"}
    payload = load_result(result["result_path"])
    assert set(payload["missing"]) == {"recordings", "plots"}


# ---- 对抗用例 3：句柄 flush 抛异常 → finalized 仍 True 且记录 ----


def test_flush_exception_keeps_finalized_true_and_recorded(tmp_path):
    run_dir = make_workspace(tmp_path)
    handle = FakeHandle(flush_exc=OSError("disk full"))
    result = finalize_run(make_ctx(run_dir, open_files=[handle]), "done")

    assert result["finalized"] is True
    # flush 失败被记录，close 仍被执行
    assert handle.closed is True
    payload = load_result(result["result_path"])
    assert len(payload["close_errors"]) == 1
    assert payload["close_errors"][0]["stage"] == "flush"
    assert "disk full" in payload["close_errors"][0]["error"]
    # 非 run.log 句柄封存失败不算日志降级
    assert payload["log_degraded"] is False


# ---- 对抗用例 4：stop_result 缺 → 结果中标注未记录 ----


def test_stop_result_missing_flagged_in_result(tmp_path):
    run_dir = make_workspace(tmp_path)
    ctx = make_ctx(run_dir)
    del ctx["stop_result"]
    result = finalize_run(ctx, "done")

    assert result["finalized"] is True
    payload = load_result(result["result_path"])
    assert payload["stop_result_recorded"] is False
    assert payload["stop_result"] is None


def test_stop_result_present_recorded_flag_true(tmp_path):
    run_dir = make_workspace(tmp_path)
    result = finalize_run(make_ctx(run_dir), "done")

    payload = load_result(result["result_path"])
    assert payload["stop_result_recorded"] is True
    assert payload["stop_result"] == {"stopped": True, "reason": "normal"}


# ---- 对抗用例 5：结果 JSON 目标目录被删 → finalized=False 不抛 ----


def test_result_target_dir_deleted_finalized_false_no_raise(tmp_path):
    run_dir = make_workspace(tmp_path)
    ctx = make_ctx(run_dir)
    shutil.rmtree(run_dir)

    result = finalize_run(ctx, "done")  # 不得抛出

    assert result["finalized"] is False
    assert result["result_path"] is None
    assert isinstance(result["error"], str) and result["error"]
    assert "result.json" in result["error"]


# ---- 对抗用例 6：duration_ms > 0 ----


def test_duration_ms_positive(tmp_path):
    run_dir = make_workspace(tmp_path)
    result = finalize_run(make_ctx(run_dir, started_at=time.time() - 0.5), "done")
    payload = load_result(result["result_path"])
    assert isinstance(payload["duration_ms"], int)
    assert payload["duration_ms"] > 0


def test_duration_ms_positive_even_for_zero_elapsed(tmp_path):
    # started_at 与 finished_at 同刻：钟粒度截断为 0 时钳到下限 1ms，保证恒为正
    run_dir = make_workspace(tmp_path)
    now = time.time()
    result = finalize_run(make_ctx(run_dir, started_at=now, finished_at=now), "done")
    payload = load_result(result["result_path"])
    assert payload["duration_ms"] >= 1


# ---- 对抗用例 7：exit_semantics 透传 + status 映射 ----


def test_exit_semantics_passthrough_and_status_mapping(tmp_path):
    run_dir = make_workspace(tmp_path)

    result = finalize_run(make_ctx(run_dir), "done")
    assert load_result(result["result_path"])["exit_semantics"] == "done"

    result = finalize_run(make_ctx(run_dir), "failed")
    payload = load_result(result["result_path"])
    assert payload["exit_semantics"] == "failed"
    assert payload["status"] == "failed"

    # 退出码语义描述原样透传，status 映射为 failed
    semantics = "exit_code=2 语义异常（红线校验拒则）"
    result = finalize_run(make_ctx(run_dir), semantics)
    payload = load_result(result["result_path"])
    assert payload["exit_semantics"] == semantics
    assert payload["status"] == "failed"


# ---- 对抗用例 8：open_files 空清单正常 ----


def test_empty_open_files_list_ok(tmp_path):
    run_dir = make_workspace(tmp_path)
    result = finalize_run(make_ctx(run_dir, open_files=[]), "done")

    assert result["finalized"] is True
    payload = load_result(result["result_path"])
    assert payload["close_errors"] == []


# ---- 补充：真实句柄 flush+close 落盘 ----


def test_real_handle_flushed_and_closed_by_finalize(tmp_path):
    run_dir = make_workspace(tmp_path)
    handle = open(run_dir / "events.jsonl", "w", encoding="utf-8")
    handle.write('{"event": "inject", "level": 3}')

    result = finalize_run(make_ctx(run_dir, open_files=[handle]), "done")

    assert result["finalized"] is True
    assert handle.closed is True
    # 未显式 flush 的内容经收尾封存后可完整读回
    assert json.loads((run_dir / "events.jsonl").read_text(encoding="utf-8")) == {
        "event": "inject",
        "level": 3,
    }


def test_close_exception_recorded_and_continues(tmp_path):
    run_dir = make_workspace(tmp_path)
    bad = FakeHandle(name="kpi.csv", close_exc=OSError("handle broken"))
    good = FakeHandle(name="monitor.csv")
    result = finalize_run(make_ctx(run_dir, open_files=[bad, good]), "done")

    assert result["finalized"] is True
    # 单个失败记录后继续：后面的句柄仍被封存
    assert good.closed is True
    payload = load_result(result["result_path"])
    assert len(payload["close_errors"]) == 1
    assert payload["close_errors"][0]["stage"] == "close"
    assert payload["close_errors"][0]["file"].endswith("kpi.csv")


# ---- 补充：日志降级口径 ----


def test_run_log_missing_marks_log_degraded(tmp_path):
    run_dir = make_workspace(tmp_path, skip=("run.log",))
    result = finalize_run(make_ctx(run_dir), "done")

    payload = load_result(result["result_path"])
    assert payload["log_degraded"] is True
    assert "run.log" in payload["missing"]


def test_run_log_handle_flush_failure_marks_log_degraded(tmp_path):
    run_dir = make_workspace(tmp_path)
    handle = FakeHandle(name=str(run_dir / "run.log"), flush_exc=OSError("log io error"))
    result = finalize_run(make_ctx(run_dir, open_files=[handle]), "done")

    payload = load_result(result["result_path"])
    assert payload["log_degraded"] is True


# ---- 补充：不可序列化对象不得阻断 result.json ----


def test_unserializable_stop_result_still_writes_result(tmp_path):
    run_dir = make_workspace(tmp_path)
    ctx = make_ctx(
        run_dir,
        stop_result={"stopped": True, "exception": ValueError("boom"), "tags": {"a", "b"}},
    )
    result = finalize_run(ctx, "failed")

    assert result["finalized"] is True
    payload = load_result(result["result_path"])
    assert payload["stop_result"]["stopped"] is True
    assert "ValueError" in payload["stop_result"]["exception"]
    assert sorted(payload["stop_result"]["tags"]) == ["a", "b"]


# ---- 补充：形状错 ----


def test_missing_run_dir_key_finalized_false_no_raise(tmp_path):
    ctx = make_ctx(tmp_path)
    del ctx["run_dir"]
    result = finalize_run(ctx, "done")  # 不得抛出

    assert result["finalized"] is False
    assert result["result_path"] is None
    assert "run_dir" in result["error"]


def test_result_payload_schema_and_optional_keys(tmp_path):
    run_dir = make_workspace(tmp_path)
    result = finalize_run(make_ctx(run_dir), "done")
    payload = load_result(result["result_path"])

    assert payload["backend"] == "sim"
    assert payload["clock_ref"] == {"source": "software", "disciplined": False}
    assert payload["alignment_error"] == 0.42
    assert payload["started_at"] is not None
    assert payload["finished_at"] is not None
    assert payload["log_degraded"] is False


def test_alignment_error_absent_when_not_provided(tmp_path):
    run_dir = make_workspace(tmp_path)
    ctx = make_ctx(run_dir)
    del ctx["alignment_error"]
    result = finalize_run(ctx, "done")

    payload = load_result(result["result_path"])
    assert "alignment_error" not in payload


# ---- 补充：NaN/Inf 严格 JSON（allow_nan=False + 占位规整） ----


def test_nonfinite_values_normalized_result_strict_json(tmp_path):
    """stop_result/alignment_error 含 float NaN/±Inf → result.json 无 NaN/Infinity
    字面量（严格 parse_constant=raise 可解析），非有限值规整为占位字符串。"""
    run_dir = make_workspace(tmp_path)
    ctx = make_ctx(
        run_dir,
        alignment_error=float("nan"),
        stop_result={"ok": False, "snr": float("inf"), "floor": float("-inf"),
                     "deep": [{"v": float("nan")}]},
        backend=float("nan"),
    )
    result = finalize_run(ctx, "done")

    assert result["finalized"] is True
    text = (run_dir / "result.json").read_text(encoding="utf-8")

    def _reject(name):
        raise ValueError(f"非法 JSON 字面量: {name}")

    payload = json.loads(text, parse_constant=_reject)  # 严格解析不触发
    assert payload["alignment_error"] == "__nan__"
    assert payload["stop_result"]["snr"] == "__inf__"
    assert payload["stop_result"]["floor"] == "-__inf__"
    assert payload["stop_result"]["deep"] == [{"v": "__nan__"}]
    assert payload["backend"] == "__nan__"


# ---- 补充：时钟回拨（started_at > finished_at） ----


def test_clock_rollback_duration_floor_and_flag(tmp_path):
    """started_at > finished_at（时钟回拨）→ duration_ms 钳到 1 且结果标
    clock_rollback=true；正常时序不带该键。"""
    run_dir = make_workspace(tmp_path)
    result = finalize_run(
        make_ctx(run_dir, started_at=1000.0, finished_at=999.5), "done"
    )
    payload = load_result(result["result_path"])
    assert payload["duration_ms"] == 1
    assert payload["clock_rollback"] is True

    result_ok = finalize_run(
        make_ctx(run_dir, started_at=1000.0, finished_at=1000.5), "done"
    )
    payload_ok = load_result(result_ok["result_path"])
    assert payload_ok["duration_ms"] >= 1
    assert "clock_rollback" not in payload_ok  # 正常时序不加键
