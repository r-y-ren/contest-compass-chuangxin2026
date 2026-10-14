"""B26 对抗中2 转 B27 随批整改②：索引入口 runs_root 路径围栏+source_scenario
白名单收缩——POST /api/run/replay 的条目消费边界（mount_console_extensions
R64 注册块 ``_fence_replay_entry``）端点合约。

- 围栏：索引条目（register 透传 sigmf_path / path）解析出的录音 meta 在解析
  后必须落在 runs_root（realpath）内——越界→ScenarioError→400 错误信息进
  响应上屏；
- 收缩：index register 额外键原样透传的 'source_scenario' 仅保留白名单键
  （style/fs/freq_hz/power_dbm/duration_s/bands/shielded_box/dut_scope）——
  全为越权键时整键剥除（回落场景副本路），白名单键保留其覆盖语义。

模块名 test_replay_run_fence（`pytest -k replay_run` 经模块关键字发现）。
"""
import json
import os
import time

import pytest

try:  # 端点合约用——fastapi 缺库环境整组 skip
    from fastapi.testclient import TestClient

    from src.serve_console.create_console_app import create_console_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)

#: 声明齐全的来源场景（白名单键内——build_replay_scenario 可消费形状）。
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


def _write_pair(directory, name, num_samples=32):
    """tmp 下写 cf32 SigMF 对（num_samples 样本），返回 meta 路径。"""
    import numpy as np

    os.makedirs(directory, exist_ok=True)
    stem = os.path.join(directory, name)
    np.zeros(num_samples, dtype=np.complex64).tofile(stem + ".sigmf-data")
    meta = {
        "global": {
            "core:sample_rate": 1e6,
            "core:datatype": "cf32_le",
            "core:num_samples": num_samples,
        },
        "captures": [{"core:sample_start": 0}],
        "annotations": [],
    }
    with open(stem + ".sigmf-meta", "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    return stem + ".sigmf-meta"


def _write_scenario_copy(run_dir, style="tone"):
    """来源运行目录落场景副本（声明齐全——副本路真值来源）。"""
    import yaml

    body = dict(_SOURCE_SCENARIO)
    body["style"] = style
    with open(os.path.join(run_dir, "scenario.yaml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump(body, fh)


def _client(tmp_path, captured=None):
    """装配真 app+合成 runs_root（含声明齐全运行目录）；captured 非 None 时
    runner 捕获组装场景（验收缩语义——不真跑 replay 后端）。"""
    root = tmp_path / "reports"
    run_dir = root / "20260101-000000"
    _write_pair(run_dir / "recordings", "20260101-000000")
    _write_scenario_copy(run_dir)

    def _runner(scenario):
        if captured is not None:
            captured.update(scenario)
            return {"run_dir": None, "status": "completed", "exit_code": 0}
        raise AssertionError("本组用例 runner 仅捕获不真跑")  # pragma: no cover

    deps = {
        "runner": _runner,
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path),
        "report_root": str(root),
        "static_pages": {},
    }
    return TestClient(create_console_app(deps)), str(root)


def _register_entry(tmp_path, runs_root, record_extra=None):
    """index register 登记条目（额外键原样透传——含 sigmf_path/source_scenario）。

    索引落点=runs_root/dataset-index.json（dataset_index_path 派生——POST
    /api/run/replay 的消费口径，测试显式对齐）。"""
    from src.index_dataset.index_dataset import index_dataset

    record = {
        "run_id": "fenced-01",
        "path": os.path.join(runs_root, "20260101-000000", "recordings"),
        "style": "tone",
        "freq_mhz": 2400.0,
        "date": "20260101",
        "backend": "sim",
    }
    if record_extra:
        record.update(record_extra)
    index_dataset(
        "register",
        record=record,
        index_path=os.path.join(runs_root, "dataset-index.json"),
        runs_root=runs_root,
    )


def _poll_done(client, run_id, timeout_s=10.0) -> dict:
    """轮询 GET /api/runs/{id} 至终态（done/failed），返回终态条目。"""
    deadline = time.monotonic() + timeout_s
    entry = client.get(f"/api/runs/{run_id}").json()
    while entry["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        entry = client.get(f"/api/runs/{run_id}").json()
    return entry


@needs_fastapi
def test_replay_run_fence_sigmf_path_outside_runs_root_rejected(tmp_path):
    """围栏①：条目显式 sigmf_path 指向 runs_root 外（库外路径）→400 越界
    （ScenarioError 语义进响应上屏），不发起回放。"""
    outside = tmp_path / "outside"
    meta = _write_pair(outside, "secret")
    client, runs_root = _client(tmp_path)
    _register_entry(tmp_path, runs_root, {"sigmf_path": str(meta)})
    resp = client.post("/api/run/replay", json={"run_id": "fenced-01"})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["field"] == "run_id"
    assert "越界" in detail["error"] and "runs_root 围栏" in detail["error"]


@needs_fastapi
def test_replay_run_fence_path_traversal_recordings_rejected(tmp_path):
    """围栏②：条目 'path'（recordings 目录）指向 runs_root 外——解析出目录内
    最早 meta 后同样越界→400（围栏覆盖 path 解析路，不只在显式 sigmf_path）。"""
    outside = tmp_path / "smuggled" / "recordings"
    _write_pair(outside, "a")
    client, runs_root = _client(tmp_path)
    _register_entry(tmp_path, runs_root, {"path": str(outside)})
    resp = client.post("/api/run/replay", json={"run_id": "fenced-01"})
    assert resp.status_code == 400
    assert "越界" in resp.json()["detail"]["error"]


@needs_fastapi
def test_replay_run_fence_inside_root_passthrough(tmp_path):
    """围栏③：条目在 runs_root 内（正常 rebuild 口径形状）→围栏放行——
    装载期组装+后台发起照常（202；runner 捕获到 replay 场景）。"""
    captured: dict = {}
    client, runs_root = _client(tmp_path, captured=captured)
    _register_entry(tmp_path, runs_root)
    resp = client.post("/api/run/replay", json={"run_id": "fenced-01"})
    assert resp.status_code == 202
    assert resp.json()["replay_of"] == "fenced-01"
    entry = _poll_done(client, resp.json()["run_id"])
    assert entry["status"] == "done"
    assert captured.get("backend") == "replay"  # 组装场景已交 runner（围栏未误伤）


@needs_fastapi
def test_replay_run_fence_source_scenario_shrunk_to_whitelist(tmp_path):
    """收缩①：source_scenario 白名单键保留+越权键剥除——register 透传夹带的
    越权键（rogue_key）不得进入组装场景（runner 捕获场景无该键，白名单覆盖
    语义 style='chirp' 照常生效）。"""
    captured: dict = {}
    client, runs_root = _client(tmp_path, captured=captured)
    _register_entry(
        tmp_path,
        runs_root,
        {
            "source_scenario": {
                **_SOURCE_SCENARIO,
                "style": "chirp",  # 白名单键——覆盖语义保留
                "rogue_key": "poison",  # 越权键——收缩剥除
                "sigmf_path": "/etc/passwd",  # 越权键（不消费）——剥除
            }
        },
    )
    resp = client.post("/api/run/replay", json={"run_id": "fenced-01"})
    assert resp.status_code == 202
    entry = _poll_done(client, resp.json()["run_id"])
    assert entry["status"] == "done"
    assert captured.get("style") == "chirp"  # 白名单覆盖语义保留
    assert "rogue_key" not in captured  # 越权键未进组装场景
    # sigmf_path 消费的是条目解析值（runs_root 内），非来源场景夹带值
    assert captured.get("sigmf_path", "").startswith(str(tmp_path))


@needs_fastapi
def test_replay_run_fence_source_scenario_all_rogue_falls_back_to_copy(tmp_path):
    """收缩②：source_scenario 仅越权键（无白名单键）→整键剥除——组装回落
    场景副本路（scenario.yaml 真值 style='tone'），夹带 dict 不再被消费。"""
    captured: dict = {}
    client, runs_root = _client(tmp_path, captured=captured)
    _register_entry(
        tmp_path,
        runs_root,
        {"source_scenario": {"rogue_only": {"inject": True}}},
    )
    resp = client.post("/api/run/replay", json={"run_id": "fenced-01"})
    assert resp.status_code == 202
    entry = _poll_done(client, resp.json()["run_id"])
    assert entry["status"] == "done"
    assert captured.get("style") == "tone"  # 副本真值（夹带 dict 被收缩剥除）


@needs_fastapi
def test_replay_run_fence_data_symlink_outside_runs_root_rejected(tmp_path):
    """围栏④（B27 对抗中1 转 B28 随批整改①）：meta 在界而配对 .sigmf-data 软链
    出界（指向库外真值对）——「半对走私」同样拦下→400 越界，不发起回放。"""
    client, runs_root = _client(tmp_path)
    _register_entry(tmp_path, runs_root)
    # 库外真值对：outside/secret.sigmf-{data,meta}（越界目标存在——isfile 过、
    # realpath 出界拦）
    outside = tmp_path / "outside"
    meta = _write_pair(outside, "secret", num_samples=64)
    data_inside = os.path.join(
        runs_root, "20260101-000000", "recordings", "20260101-000000.sigmf-data"
    )
    os.remove(data_inside)
    os.symlink(os.path.join(str(outside), "secret.sigmf-data"), data_inside)
    assert meta  # 库外 meta 仅作伴对（data 目标在位即可）
    resp = client.post("/api/run/replay", json={"run_id": "fenced-01"})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["field"] == "run_id"
    assert "越界" in detail["error"] and "runs_root 围栏" in detail["error"]


@needs_fastapi
def test_replay_run_fence_data_symlink_inside_runs_root_passthrough(tmp_path):
    """围栏⑤（整改①不误伤）：.sigmf-data 软链指向 runs_root 界内共享存储
    （realpath 仍落根内）→围栏放行——202+后台发起照常（runner 捕获 replay 场景）。"""
    captured: dict = {}
    client, runs_root = _client(tmp_path, captured=captured)
    _register_entry(tmp_path, runs_root)
    shared = tmp_path / "reports" / "shared"
    shared.mkdir()
    blob = shared / "blob.sigmf-data"
    import numpy as np

    np.zeros(32, dtype=np.complex64).tofile(str(blob))
    data_inside = os.path.join(
        runs_root, "20260101-000000", "recordings", "20260101-000000.sigmf-data"
    )
    os.remove(data_inside)
    os.symlink(str(blob), data_inside)
    resp = client.post("/api/run/replay", json={"run_id": "fenced-01"})
    assert resp.status_code == 202  # 界内软链不拦
    entry = _poll_done(client, resp.json()["run_id"])
    assert entry["status"] == "done"
    assert captured.get("backend") == "replay"  # 组装场景照常交 runner
