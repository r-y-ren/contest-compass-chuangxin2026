"""launch_replay_run 单测（R64 L0）：一键回放编排——组装→runner 发起→返回句柄；
装载期拒绝（ScenarioError 先于 runner）/sim 侧端到端（录制→入库→回放 exit 0）。

返回契约（被测实现口径，详见 src/launch_replay_run/launch_replay_run.py 模块
docstring）：{'run_id': 回放运行目录名, 'status', 'exit_code', 'run_dir',
'backend': 'replay', 'scenario': 组装场景, 'result': runner 完整结果}。
"""
import os
from functools import partial

import pytest

from src.launch_replay_run.launch_replay_run import (
    ScenarioError,
    launch_replay_run,
)
from src.run_demo.run_demo import run_scenario

#: 声明齐全的来源场景（组装真值素材——与 build_replay_scenario 契约一致）。
_SOURCE_SCENARIO = {
    "style": "tone",
    "fs": 1.0e6,
    "freq_hz": 2.4e9,
    "power_dbm": -10.0,
    "duration_s": 0.005,
    "backend": "sim",
    "bands": [[2400.0, 2483.5]],
    "shielded_box": True,
    "dut_scope": "self_built",
}


def _make_entry(tmp_path, name="20260101-120000", *, scenario=None):
    """造带 SigMF 真值对与来源场景的录音条目（sigmf_path+source_scenario 直给）。"""
    recordings = tmp_path / "runs" / name / "recordings"
    recordings.mkdir(parents=True)
    meta = recordings / f"{name}.sigmf-meta"
    meta.write_text("{}", encoding="utf-8")
    (recordings / f"{name}.sigmf-data").write_bytes(b"\x00" * 16)
    return {
        "run_id": name,
        "sigmf_path": str(meta),
        "source_scenario": dict(
            scenario if scenario is not None else _SOURCE_SCENARIO
        ),
    }


# ---- 编排契约（fake runner） ----


def test_launch_replay_run_invokes_runner_with_built_scenario(tmp_path):
    """组装场景经 runner 发起（backend/sigmf_path/声明沿用）；返回句柄含
    run_id（run_dir 目录名）/status/exit_code/backend/scenario/result。"""
    entry = _make_entry(tmp_path)
    captured = {}

    def fake_runner(scenario):
        captured.update(scenario)
        return {
            "run_dir": "/tmp/runs/20260102-080000",
            "status": "completed",
            "exit_code": 0,
            "summary": "run_scenario: …",
        }

    out = launch_replay_run(entry, fake_runner)
    assert captured["backend"] == "replay"
    assert captured["sigmf_path"] == entry["sigmf_path"]
    assert captured["shielded_box"] is True and captured["dut_scope"] == "self_built"
    assert out["run_id"] == "20260102-080000"  # run_dir 目录名
    assert out["status"] == "completed" and out["exit_code"] == 0
    assert out["backend"] == "replay"
    assert out["scenario"] == captured  # 组装场景留痕
    assert out["result"]["summary"].startswith("run_scenario")


def test_launch_replay_run_no_run_dir_yields_none_run_id(tmp_path):
    """runner 结果无 run_dir（如校验失败回执）→句柄 run_id=None 不虚构。"""
    entry = _make_entry(tmp_path)
    out = launch_replay_run(
        entry,
        lambda scenario: {"run_dir": None, "status": "validation_failed", "exit_code": 2},
    )
    assert out["run_id"] is None
    assert out["status"] == "validation_failed" and out["exit_code"] == 2


def test_launch_replay_run_scenario_error_before_runner(tmp_path):
    """装载期拒绝（声明缺失）→ScenarioError 上抛且 runner 不被调用（错误进
    操控台响应的编排侧前提）。"""
    broken = {k: v for k, v in _SOURCE_SCENARIO.items() if k != "dut_scope"}
    entry = _make_entry(tmp_path, scenario=broken)
    called = []

    def spy_runner(scenario):  # pragma: no cover - 不应被触达
        called.append(scenario)
        return {}

    with pytest.raises(ScenarioError, match="dut_scope"):
        launch_replay_run(entry, spy_runner)
    assert called == []


def test_launch_replay_run_runner_not_callable_rejected(tmp_path):
    """runner 不可调用→ValueError（编程错误早暴露，先于组装）。"""
    with pytest.raises(ValueError, match="runner"):
        launch_replay_run(_make_entry(tmp_path), "not-callable")


def test_launch_replay_run_runner_result_not_dict_rejected(tmp_path):
    """runner 返回非 dict→ValueError（run_scenario 契约违背指错）。"""
    with pytest.raises(ValueError, match="dict"):
        launch_replay_run(_make_entry(tmp_path), lambda scenario: "oops")


def test_launch_replay_run_runner_exception_propagates(tmp_path):
    """runner 内部异常原样上抛（隔离边界归操控台端点后台线程，不在本层吞）。"""
    def boom(scenario):
        raise RuntimeError("backend blew up")

    with pytest.raises(RuntimeError, match="blew up"):
        launch_replay_run(_make_entry(tmp_path), boom)


# ---- sim 侧端到端：录制→入库→回放 exit 0（R64 tested 策略） ----


def test_launch_replay_run_sim_side_record_register_replay_exit_zero(tmp_path):
    """真链路最小闭环：record:true sim 运行产出 SigMF→索引登记→条目回放经
    run_scenario 真跑 replay 后端→exit_code 0（completed）。"""
    runs_root = tmp_path / "runs"
    recorded = run_scenario(
        {
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
            "record": True,
            "bands": [[2400.0, 2483.5]],
            "shielded_box": True,
            "dut_scope": "self_built",
        },
        out_root=str(runs_root),
    )
    assert recorded["exit_code"] == 0  # 录制运行本身成功（SigMF 真值对产出）
    run_name = os.path.basename(recorded["run_dir"].rstrip(os.sep))

    from src.index_dataset.index_dataset import index_dataset

    index_dataset(
        "register",
        record={
            "run_id": run_name,
            "path": os.path.join(recorded["run_dir"], "recordings"),
            "style": "tone",
            "freq_mhz": 2400.0,
            "date": run_name[:8],
            "backend": "sim",
        },
        index_path=str(tmp_path / "dataset-index.json"),
    )
    entry = next(
        item
        for item in index_dataset(
            "list", index_path=str(tmp_path / "dataset-index.json")
        )["entries"]
        if item["run_id"] == run_name
    )
    out = launch_replay_run(
        entry, partial(run_scenario, out_root=str(runs_root))
    )
    assert out["exit_code"] == 0  # 回放运行 exit 0（R64 验收真身）
    assert out["status"] == "completed"
    assert out["run_id"] and out["run_id"] != run_name  # 新回放运行目录
    assert out["scenario"]["backend"] == "replay"
    assert out["scenario"]["sigmf_path"].endswith(".sigmf-meta")
