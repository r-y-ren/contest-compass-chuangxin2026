"""launch_classifier_training 单测（R65）：任务表+后台线程+拒训终态+模型列表；
端点合约（POST /api/ai/train / GET /api/ai/train/{task_id} / GET /api/ai/models）
+页区静态资产。用例名统一 ``test_ai_train_view_`` 前缀（`pytest -k ai_train_view`
发现——R65 核验命令真身：dry_run 端到端+拒训分支）。

被测实现口径见 src/launch_classifier_training/launch_classifier_training.py
模块 docstring（任务句柄/终态条目/list_model_files 契约）。
"""
import json
import os
import time

import numpy as np
import pytest

try:  # 端点合约用——fastapi 缺库环境整组端点用例 skip
    from fastapi.testclient import TestClient

    from src.serve_console.create_console_app import create_console_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

from src.launch_classifier_training.launch_classifier_training import (
    MODELS_DIRNAME,
    get_training_task,
    launch_classifier_training,
    list_model_files,
)
from src.launch_classifier_training.train_area import build_train_area

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)


# ---- 合成数据集：临时 SigMF cf32 对（单音/带限噪声）+ index_dataset register ----


def _tone_iq(n=512):
    """0.1fs 单音（长度 ≥ nfft=64 出有效谱）。"""
    return np.exp(1j * 2.0 * np.pi * 0.1 * np.arange(n)).astype(np.complex64)


def _noise_iq(n=512, seed=11):
    """复高斯噪声（每 run 换种子——批次组键 run_id 互异）。"""
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex64)


def _register(runs_root, index_path, run_id, style, iq, date="20260101"):
    """写 run_id/recordings/rec.sigmf-{data,meta} 对并登记索引。"""
    rec_dir = os.path.join(runs_root, run_id, "recordings")
    os.makedirs(rec_dir, exist_ok=True)
    np.asarray(iq, dtype=np.complex64).tofile(os.path.join(rec_dir, "rec.sigmf-data"))
    meta = {
        "global": {
            "core:sample_rate": 1e6,
            "core:datatype": "cf32_le",
            "core:num_samples": int(np.asarray(iq).size),
        },
        "captures": [{"core:sample_start": 0}],
        "annotations": [],
    }
    with open(os.path.join(rec_dir, "rec.sigmf-meta"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    from src.index_dataset.index_dataset import index_dataset

    index_dataset(
        "register",
        record={
            "run_id": run_id,
            "path": rec_dir,
            "style": style,
            "freq_mhz": 2400.0,
            "date": date,
            "backend": "sim",
        },
        index_path=index_path,
        runs_root=runs_root,
    )


def _dataset(tmp_path, per_class=8, classes=("tone", "bandlimited_noise")):
    """两类×per_class run 登记 → (index_path, runs_root, models_dir)。"""
    runs_root = str(tmp_path / "runs")
    index_path = os.path.join(runs_root, "dataset-index.json")
    for cls_idx, style in enumerate(classes):
        for i in range(per_class):
            iq = _tone_iq() if style == "tone" else _noise_iq(seed=300 + cls_idx * 40 + i)
            _register(runs_root, index_path, f"2026010{cls_idx + 1}-{i:06d}", style, iq)
    return index_path, runs_root, os.path.join(str(tmp_path), "runs", MODELS_DIRNAME)


def _params(index_path, runs_root, models_dir, **over):
    """基础训练参数（tmp 索引/模型落点+nfft=64——IQ 512 段全有效）。"""
    params = {
        "query": {"style": ["tone", "bandlimited_noise"]},
        "where": "local",
        "dry_run": False,
        "hyperparams": {
            "index_path": index_path,
            "runs_root": runs_root,
            "nfft": 64,
            "min_samples": 4,
            "out_path": os.path.join(models_dir, "style_classifier.json"),
        },
    }
    params.update(over)
    return params


def _wait_task(task_id, timeout_s=30.0) -> dict:
    """轮询任务表至终态（done/failed），返回终态条目。"""
    deadline = time.monotonic() + timeout_s
    task = get_training_task(task_id)
    while task is not None and task["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        task = get_training_task(task_id)
    assert task is not None and task["status"] != "running", f"任务未在 {timeout_s}s 内终态"
    return task


# ---- 纯函数：任务句柄+终态（local 真训练产模型） ----


def test_ai_train_view_local_task_handle_and_done_result(tmp_path):
    """① local 训练任务：句柄 running+终态 done 附 train_classifier 完整返回
    （model_path/labels/n_samples）；任务表可轮询。"""
    index_path, runs_root, models_dir = _dataset(tmp_path)
    handle = launch_classifier_training(
        _params(index_path, runs_root, models_dir)
    )
    assert handle["status"] == "running"  # 立即返回（后台线程）
    assert handle["where"] == "local" and handle["dry_run"] is False
    assert handle["task_id"] and get_training_task(handle["task_id"])["status"] in (
        "running",
        "done",
    )
    task = _wait_task(handle["task_id"])
    assert task["status"] == "done"
    result = task["result"]
    assert set(result["labels"]) == {"tone", "bandlimited_noise"}
    assert result["n_samples"] == 16
    assert os.path.isfile(result["model_path"])  # 模型真落盘


def test_ai_train_view_insufficient_rejected_task_failed_with_reason(tmp_path):
    """② 拒训分支（R30 口径）：查询零匹配→终态 failed，error 原文含
    TrainError 与「样本不足拒训」——信息原样上屏不吞不改写。"""
    index_path, runs_root, models_dir = _dataset(tmp_path)
    handle = launch_classifier_training(
        _params(
            index_path,
            runs_root,
            models_dir,
            query={"style": "chirp"},  # 库内无 chirp——零匹配拒训
        )
    )
    task = _wait_task(handle["task_id"])
    assert task["status"] == "failed"
    assert "TrainError" in task["error"]
    assert "样本不足拒训" in task["error"] and "0 条" in task["error"]


def test_ai_train_view_min_samples_reject_branch(tmp_path):
    """③ 拒训分支（有效样本不足）：min_samples 抬过有效样本数→failed 附数与阈值。"""
    index_path, runs_root, models_dir = _dataset(tmp_path, per_class=3)
    params = _params(index_path, runs_root, models_dir)
    params["hyperparams"]["min_samples"] = 99  # 有效 6 < 99——不足拒训
    handle = launch_classifier_training(params)
    task = _wait_task(handle["task_id"])
    assert task["status"] == "failed"
    assert "有效谱样本 6 < min_samples=99" in task["error"]


def test_ai_train_view_shape_errors_rejected_before_task(tmp_path):
    """④ 形状错注册前先拒（ValueError——不建任务不启线程）：params 非 dict/
    query 非 dict/where 非法/dry_run 非 bool/hyperparams 非 dict。"""
    index_path, runs_root, models_dir = _dataset(tmp_path, per_class=2)
    good = _params(index_path, runs_root, models_dir)
    with pytest.raises(ValueError, match="params 必须为 dict"):
        launch_classifier_training(["not-a-dict"])
    bad_query = dict(good, query="style=tone")
    with pytest.raises(ValueError, match="query"):
        launch_classifier_training(bad_query)
    with pytest.raises(ValueError, match="where"):
        launch_classifier_training(dict(good, where="cloud"))
    with pytest.raises(ValueError, match="dry_run"):
        launch_classifier_training(dict(good, dry_run="yes"))
    with pytest.raises(ValueError, match="hyperparams"):
        launch_classifier_training(dict(good, hyperparams=[64]))


def test_ai_train_view_get_unknown_task_none():
    """⑤ 未知 task_id/非 str → None（GET 404 判据）。"""
    assert get_training_task("no-such-task") is None
    assert get_training_task(None) is None


def test_ai_train_view_model_listing(tmp_path):
    """⑥ list_model_files：*.json 条目（新在前，labels 读取）+损坏文件 labels=None
    如实标注+目录缺失空列表。"""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    with open(models_dir / "old.json", "w", encoding="utf-8") as fh:
        json.dump({"kind": "cnn_dummy", "labels": ["tone", "pulse"]}, fh)
    os.utime(models_dir / "old.json", (1_000_000, 1_000_000))  # 旧时间戳
    with open(models_dir / "new.json", "w", encoding="utf-8") as fh:
        json.dump({"kind": "cnn_dummy", "labels": ["chirp"]}, fh)
    (models_dir / "broken.json").write_text("{not json", encoding="utf-8")
    (models_dir / "notes.txt").write_text("ignored", encoding="utf-8")
    rows = list_model_files(str(models_dir))
    names = [row["name"] for row in rows]
    assert names[0] == "broken.json"  # mtime 新在前（最后写入者）
    assert names[-1] == "old.json"  # utime 旧时间戳垫底
    assert "new.json" in names
    assert "notes.txt" not in names  # 仅 *.json
    by_name = {row["name"]: row for row in rows}
    assert by_name["old.json"]["labels"] == ["tone", "pulse"]
    assert by_name["new.json"]["size_bytes"] > 0
    assert by_name["broken.json"]["labels"] is None  # 损坏如实标注不剔除
    assert list_model_files(str(tmp_path / "no-such-dir")) == []


# ---- 端点合约：POST /api/ai/train + GET /api/ai/train/{task_id} + GET /api/ai/models ----


def _client(tmp_path):
    """装配真 app（create_console_app→mount_console_extensions）+合成数据集。"""
    index_path, runs_root, models_dir = _dataset(tmp_path)
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path),
        "report_root": runs_root,  # 操控台运行根=数据集 runs_root（R63 同口径）
        "static_pages": {},
    }
    return TestClient(create_console_app(deps)), index_path, runs_root, models_dir


def _poll_endpoint(client, task_id, timeout_s=30.0) -> dict:
    """轮询 GET /api/ai/train/{task_id} 至终态，返回终态任务条目。"""
    deadline = time.monotonic() + timeout_s
    task = client.get(f"/api/ai/train/{task_id}").json()
    while task.get("status") == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        task = client.get(f"/api/ai/train/{task_id}").json()
    assert task.get("status") != "running", "训练任务未在时限内终态"
    return task


@needs_fastapi
def test_ai_train_view_endpoint_dry_run_end_to_end(tmp_path):
    """⑦ dry_run 端到端（R65 验收真身）：POST /api/ai/train（where=remote+
    dry_run）→202 任务句柄→GET 轮询至 done——dispatched=False（不真派发）、
    n_samples>0、labels 两类；GET /api/ai/models 空列表提示态（未产模型）。"""
    client, index_path, runs_root, models_dir = _client(tmp_path)
    resp = client.post(
        "/api/ai/train",
        json={
            "query": {"style": ["tone", "bandlimited_noise"]},
            "where": "remote",
            "dry_run": True,
            "hyperparams": {"nfft": 64, "min_samples": 4},
        },
    )
    assert resp.status_code == 202
    handle = resp.json()
    assert handle["status"] == "running" and handle["dry_run"] is True
    assert handle["where"] == "remote"
    task = _poll_endpoint(client, handle["task_id"])
    assert task["status"] == "done"
    result = task["result"]
    assert result["dispatched"] is False  # dry_run：不真派发（CI 无 remote-compute）
    assert result["where"] == "remote"
    assert result["n_samples"] == 16 and set(result["labels"]) == {
        "tone",
        "bandlimited_noise",
    }
    models = client.get("/api/ai/models").json()
    assert models["count"] == 0 and models["models"] == []  # remote dry_run 无模型


@needs_fastapi
def test_ai_train_view_endpoint_reject_branch_failed_with_reason(tmp_path):
    """⑧ 拒训分支（端点侧）：零匹配查询→任务终态 failed，error 原文
    （TrainError 样本不足拒训）进轮询响应上屏——非 500。"""
    client, *_ = _client(tmp_path)
    resp = client.post(
        "/api/ai/train",
        json={
            "query": {"style": "sweep"},  # 库内无 sweep
            "where": "remote",
            "dry_run": True,
            "hyperparams": {"nfft": 64},
        },
    )
    assert resp.status_code == 202  # 受理（拒训在后台任务终态呈现）
    task = _poll_endpoint(client, resp.json()["task_id"])
    assert task["status"] == "failed"
    assert "样本不足拒训" in task["error"]
    assert "TrainError" in task["error"]


@needs_fastapi
def test_ai_train_view_endpoint_local_train_then_models_listed(tmp_path):
    """⑨ local 端到端：POST where=local→done 产模型→GET /api/ai/models 出
    条目（labels/大小/时间）——模型列表与训练任务闭环。"""
    client, index_path, runs_root, models_dir = _client(tmp_path)
    resp = client.post(
        "/api/ai/train",
        json={
            "query": {},
            "where": "local",
            "hyperparams": {"nfft": 64, "min_samples": 4},
        },
    )
    assert resp.status_code == 202
    task = _poll_endpoint(client, resp.json()["task_id"])
    assert task["status"] == "done"
    assert task["result"]["model_path"].endswith("style_classifier.json")
    models = client.get("/api/ai/models").json()
    assert models["count"] == 1
    entry = models["models"][0]
    assert entry["name"] == "style_classifier.json"
    assert set(entry["labels"]) == {"tone", "bandlimited_noise"}
    assert entry["size_bytes"] > 0


@needs_fastapi
def test_ai_train_view_endpoint_status_404_and_bad_shapes(tmp_path):
    """⑩ GET 未知任务→404；body 形状错（query 非 dict/where 越域/dry_run 非
    bool/hyperparams 非 dict/非 JSON 对象）→400 字段级指错。"""
    client, *_ = _client(tmp_path)
    assert client.get("/api/ai/train/no-such-task").status_code == 404
    bad_bodies = [
        ({"query": "tone"}, "query"),
        ({"query": {}, "where": "cloud"}, "where"),
        ({"query": {}, "dry_run": "yes"}, "dry_run"),
        ({"query": {}, "hyperparams": [64]}, "hyperparams"),
    ]
    for body, field in bad_bodies:
        resp = client.post("/api/ai/train", json=body)
        assert resp.status_code == 400, body
        assert resp.json()["detail"]["field"] == field
    resp = client.post(
        "/api/ai/train", content=b"not-json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400 and resp.json()["detail"]["field"] == "body"


# ---- 页区静态资产（零外链红线+挂载点/端点接线） ----


def test_ai_train_view_train_area_zero_external_links_and_wiring():
    """⑪ train 页区零外链（R56 断网全可用红线）+消费挂载点与端点接线。"""
    block = build_train_area()
    assert "http://" not in block and "https://" not in block
    assert "'train-panel'" in block  # 挂载点
    assert "'/api/ai/train'" in block  # 发起+轮询数据源
    assert "'/api/ai/models'" in block  # 模型列表数据源
    assert "发起训练" in block and "dry_run" in block  # 表单要素
    assert "model-row" in block  # 模型条目锚点
