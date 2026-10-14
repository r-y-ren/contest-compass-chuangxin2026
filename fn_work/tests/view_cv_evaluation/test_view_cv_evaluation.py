"""view_cv_evaluation 单测（R66）：合成数据→混淆矩阵/Macro-F1/泄漏旗标字段断言+
R31 拒绝族（分组缺失/检索非法/零匹配）EvalError 上屏；端点合约（POST
/api/ai/evaluate）+页区静态资产。用例名统一 ``test_ai_eval_view_`` 前缀
（`pytest -k ai_eval_view` 发现——R66 核验命令真身：合成数据→矩阵字段断言）。

被测实现口径见 src/view_cv_evaluation/view_cv_evaluation.py 模块 docstring
（query 传输键/结果页数据契约/EvalError 族）。
"""
import json
import os

import numpy as np
import pytest

try:  # 端点合约用——fastapi 缺库环境整组端点用例 skip
    from fastapi.testclient import TestClient

    from src.serve_console.create_console_app import create_console_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

from src.index_dataset.index_dataset import index_dataset
from src.view_cv_evaluation.eval_area import build_eval_area
from src.view_cv_evaluation.view_cv_evaluation import EvalError, view_cv_evaluation

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)


# ---- 合成数据集：两类×多 run（批次组键 run_id 互异——分组 CV 可行） ----


def _tone_iq(n=512):
    """0.1fs 单音（可分特征：质心集中）。"""
    return np.exp(1j * 2.0 * np.pi * 0.1 * np.arange(n)).astype(np.complex64)


def _noise_iq(n=512, seed=11):
    """复高斯噪声（可分特征：宽带平坦）。"""
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex64)


def _paths(tmp_path):
    """(index_path, runs_root) 测试落点（一律显式传，不触碰真实目录）。"""
    runs_root = str(tmp_path / "runs")
    return os.path.join(runs_root, "dataset-index.json"), runs_root


def _register(runs_root, index_path, run_id, style, iq):
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
    index_dataset(
        "register",
        record={
            "run_id": run_id,
            "path": rec_dir,
            "style": style,
            "freq_mhz": 2400.0,
            "date": "20260101",
            "backend": "sim",
        },
        index_path=index_path,
        runs_root=runs_root,
    )


def _dataset(tmp_path, per_class=6):
    """两类（tone/bandlimited_noise）×per_class run 登记。"""
    index_path, runs_root = _paths(tmp_path)
    for i in range(per_class):
        _register(runs_root, index_path, f"20260101-{i:06d}", "tone", _tone_iq())
        _register(
            runs_root,
            index_path,
            f"20260102-{i:06d}",
            "bandlimited_noise",
            _noise_iq(seed=500 + i),
        )
    return index_path, runs_root


# ---- 纯函数：合成数据→矩阵/指标/旗标字段（R66 验收真身） ----


def test_ai_eval_view_synthetic_confusion_and_metrics_fields(tmp_path):
    """① 合成两类数据→结果页数据全字段：confusion.labels 两类+方阵、
    macro_f1∈[0,1]、n_samples/matched/skipped、泄漏三旗标 bool、warnings 列表。"""
    index_path, runs_root = _dataset(tmp_path)
    model_path = str(tmp_path / "models" / "style_classifier.json")
    out = view_cv_evaluation(
        {
            "style": ["tone", "bandlimited_noise"],
            "nfft": 64,
            "index_path": index_path,
            "runs_root": runs_root,
        },
        model_path,
    )
    assert out["ok"] is True
    assert out["model_path"] == model_path and out["model_exists"] is False
    assert set(out["confusion"]["labels"]) == {"tone", "bandlimited_noise"}
    matrix = out["confusion"]["matrix"]
    labels = out["confusion"]["labels"]
    assert len(matrix) == len(labels)  # 方阵（行=真值/列=预测）
    assert all(len(row) == len(labels) for row in matrix)
    assert sum(sum(row) for row in matrix) == out["n_samples"] == 12  # 全样本入阵
    assert 0.0 <= out["macro_f1"] <= 1.0
    assert out["matched"] == 12 and out["skipped"] == 0
    for flag in ("leak_suspect", "fold_class_starvation", "below_target"):
        assert isinstance(out[flag], bool)
    assert isinstance(out["warnings"], list)  # 泄漏警告文案如实回显（可空）
    assert out["effective_k"] >= 2 and isinstance(out["per_fold"], list)


def test_ai_eval_view_model_exists_flag(tmp_path):
    """② model_exists 在位标注：文件存在→True（分组 CV 不消费模型本体，仅溯源）。"""
    index_path, runs_root = _dataset(tmp_path)
    model_path = tmp_path / "models" / "style_classifier.json"
    model_path.parent.mkdir()
    model_path.write_text('{"kind": "cnn_dummy", "labels": []}', encoding="utf-8")
    out = view_cv_evaluation(
        {"nfft": 64, "index_path": index_path, "runs_root": runs_root}, str(model_path)
    )
    assert out["model_exists"] is True


def test_ai_eval_view_transport_keys_stripped_from_query_echo(tmp_path):
    """③ 传输键（index_path/runs_root/nfft/k）不进检索条件——query 回显仅含条件。"""
    index_path, runs_root = _dataset(tmp_path)
    out = view_cv_evaluation(
        {
            "style": ["tone", "bandlimited_noise"],
            "nfft": 64,
            "k": 3,
            "index_path": index_path,
            "runs_root": runs_root,
        },
        "models/style_classifier.json",
    )
    assert out["query"] == {"style": ["tone", "bandlimited_noise"]}  # 传输/参数键已剥离
    assert out["effective_k"] == 3  # k 透传生效（make_group_splits 缺省域内）


# ---- R31 拒绝族：EvalError 上屏 ----


def test_ai_eval_view_query_error_wrapped(tmp_path):
    """④ 检索条件非法（未知字段——QueryError）→EvalError 含原文。"""
    index_path, runs_root = _dataset(tmp_path)
    with pytest.raises(EvalError, match="query 条件非法"):
        view_cv_evaluation(
            {
                "no_such_field": 1,
                "index_path": index_path,
                "runs_root": runs_root,
            },
            "m.json",
        )


def test_ai_eval_view_zero_match_rejected(tmp_path):
    """⑤ 查询零匹配→EvalError（附 query 与重建提示）。"""
    index_path, runs_root = _dataset(tmp_path)
    with pytest.raises(EvalError, match="查询零匹配"):
        view_cv_evaluation(
            {"style": "chirp", "index_path": index_path, "runs_root": runs_root},
            "m.json",
        )


def test_ai_eval_view_single_label_rejected(tmp_path):
    """⑥ 标签少于 2 类（单类筛选）→grouped_cv_evaluate 的 R31 拒绝原文上屏。"""
    index_path, runs_root = _dataset(tmp_path)
    with pytest.raises(EvalError, match="标签少于 2 类"):
        view_cv_evaluation(
            {
                "style": "tone",
                "nfft": 64,
                "index_path": index_path,
                "runs_root": runs_root,
            },
            "m.json",
        )


def test_ai_eval_view_shape_errors_value_error(tmp_path):
    """⑦ 形状错 ValueError：query 非 dict / model_path 空 / nfft、k 不可转 int。"""
    index_path, runs_root = _dataset(tmp_path)
    with pytest.raises(ValueError, match="query 必须为 dict"):
        view_cv_evaluation("style=tone", "m.json")
    with pytest.raises(ValueError, match="model_path"):
        view_cv_evaluation({"index_path": index_path, "runs_root": runs_root}, "  ")
    with pytest.raises(ValueError, match="nfft"):
        view_cv_evaluation(
            {"nfft": "wide", "index_path": index_path, "runs_root": runs_root}, "m.json"
        )
    with pytest.raises(ValueError, match="'k'"):
        view_cv_evaluation(
            {"k": [], "index_path": index_path, "runs_root": runs_root}, "m.json"
        )


# ---- 端点合约：POST /api/ai/evaluate ----


def _client(tmp_path):
    """装配真 app（create_console_app→mount_console_extensions）+合成数据集。"""
    index_path, runs_root = _dataset(tmp_path)
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path),
        "report_root": runs_root,
        "static_pages": {},
    }
    return TestClient(create_console_app(deps))


@needs_fastapi
def test_ai_eval_view_endpoint_matrix_fields(tmp_path):
    """⑧ 端点：POST /api/ai/evaluate（默认索引注入）→200 结果页数据（矩阵
    labels/方阵+macro_f1+三旗标+warnings 字段齐备——合成数据字段断言）。"""
    client = _client(tmp_path)
    resp = client.post(
        "/api/ai/evaluate",
        json={"query": {"nfft": 64}, "model_path": "models/style_classifier.json"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    labels = payload["confusion"]["labels"]
    assert set(labels) == {"tone", "bandlimited_noise"}
    matrix = payload["confusion"]["matrix"]
    assert len(matrix) == len(labels) and all(len(r) == len(labels) for r in matrix)
    assert 0.0 <= payload["macro_f1"] <= 1.0
    assert isinstance(payload["leak_suspect"], bool)
    assert isinstance(payload["fold_class_starvation"], bool)
    assert isinstance(payload["below_target"], bool)
    assert isinstance(payload["warnings"], list)
    assert payload["n_samples"] == 12


@needs_fastapi
def test_ai_eval_view_endpoint_rejections_400_with_reason(tmp_path):
    """⑨ 端点拒绝族：EvalError（单类）→400 field='query' 原文上屏；形状错
    （model_path 空）→400 field='model_path'；body 非 JSON→400 field='body'。"""
    client = _client(tmp_path)
    resp = client.post(
        "/api/ai/evaluate",
        json={"query": {"style": "tone", "nfft": 64}, "model_path": "m.json"},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["field"] == "query" and "标签少于 2 类" in detail["error"]

    resp = client.post("/api/ai/evaluate", json={"query": {}, "model_path": ""})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "model_path"

    resp = client.post(
        "/api/ai/evaluate",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400 and resp.json()["detail"]["field"] == "body"


# ---- 页区静态资产（零外链红线+挂载点/端点接线） ----


def test_ai_eval_view_eval_area_zero_external_links_and_wiring():
    """⑩ eval 页区零外链（R56 断网全可用红线）+消费挂载点与端点接线。"""
    block = build_eval_area()
    assert "http://" not in block and "https://" not in block
    assert "'eval-panel'" in block  # 挂载点
    assert "'/api/ai/evaluate'" in block  # 评测数据源
    assert "epa-matrix" in block  # 混淆矩阵表格锚点
    assert "epa-warnings" in block  # 泄漏警告回显锚点
    assert "Macro-F1" in block and "发起评测" in block  # 表单/指标要素
