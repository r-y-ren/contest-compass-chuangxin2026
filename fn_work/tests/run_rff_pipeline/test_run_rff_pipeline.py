"""run_rff_pipeline 对抗单测：slug=rff_pipeline——合成 3 类 SigMF cf32 数据集（tmp 造 24 文件 3 类，B14 train 同口径）→管道 smoke（F1>0.8+endpoint+模型元数据）+run_id 分组+不足拒（零匹配/样本量）+短段跳段+形状错。"""
from __future__ import annotations

import json

import numpy as np
import pytest

from src.index_dataset.index_dataset import index_dataset
from src.run_rff_pipeline.run_rff_pipeline import TrainError, run_rff_pipeline

_STYLES = ("tone_lo", "tone_mid", "tone_hi")  # 3 类：0.1/0.3/0.5 fs 单音
_FREQS = {"tone_lo": 0.1, "tone_mid": 0.3, "tone_hi": 0.5}


def _tone_iq(freq, n=512, seed=0):
    """归一化频点单音（complex64；种子只影响微小加噪，保三类谱峰可分）。"""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    iq = np.exp(1j * 2.0 * np.pi * freq * t) + 0.01 * (
        rng.standard_normal(n) + 1j * rng.standard_normal(n)
    )
    return iq.astype(np.complex64)


def _register(tmp_path, index_path, run_id, style, iq, date="20260101"):
    """写 run_id/recordings/rec.sigmf-{data,meta} 对并登记索引（B14 同口径）。"""
    rec_dir = tmp_path / "runs_root" / run_id / "recordings"
    rec_dir.mkdir(parents=True)
    np.asarray(iq, dtype=np.complex64).tofile(str(rec_dir / "rec.sigmf-data"))
    meta = {
        "global": {
            "core:sample_rate": 1e6,
            "core:datatype": "cf32_le",
            "core:num_samples": int(np.asarray(iq).size),
        },
        "captures": [{"core:sample_start": 0}],
        "annotations": [],
    }
    (rec_dir / "rec.sigmf-meta").write_text(json.dumps(meta), encoding="utf-8")
    index_dataset(
        "register",
        record={
            "run_id": run_id,
            "path": str(rec_dir),
            "style": style,
            "freq_mhz": 100.0,
            "date": date,
            "backend": "sim",
        },
        index_path=str(index_path),
        runs_root=str(tmp_path / "runs_root"),
    )


def _build_dataset(tmp_path, per_class=8, seed_base=0):
    """3 类 × per_class 个 run 的临时 SigMF 数据集+索引，返回配置件。"""
    index_path = tmp_path / "index.json"
    for ci, style in enumerate(_STYLES):
        for k in range(per_class):
            _register(
                tmp_path,
                index_path,
                f"20260101-00000{ci}{k}",
                style,
                _tone_iq(_FREQS[style], seed=seed_base + ci * 100 + k),
            )
    return {
        "query": {"style": list(_STYLES)},
        "index_path": str(index_path),
        "runs_root": str(tmp_path / "runs_root"),
    }


def test_rff_pipeline_end_to_end_three_class_high_f1(tmp_path):
    """端到端 smoke：24 文件 3 类→F1>0.8+centroid 模型+endpoint+n_samples。"""
    cfg = _build_dataset(tmp_path)
    out = run_rff_pipeline(cfg, {"nfft": 64, "k": 5})
    assert out["n_samples"] == 24
    assert out["skipped"] == 0
    # 评测：分组 CV（batch_key=run_id）macro F1 高分可分
    ev = out["evaluation"]
    assert ev["macro_f1"] > 0.8
    assert ev["n_samples"] == 24
    assert ev["effective_k"] == 5  # 24 个 run 组 ≥ k=5，无降级
    assert ev["leak_suspect"] is False
    # 模型：最近质心+类清单+时间平均谱维度
    assert out["model"]["kind"] == "centroid"
    assert out["model"]["labels"] == sorted(_STYLES)
    assert len(out["model"]["centroids"]["tone_lo"]) == 64 // 2 + 1
    # 部署模拟：本地推理端点+模型元数据
    assert out["endpoint"] == "local-inference"
    dep = out["deployment"]
    assert dep["endpoint"] == "local-inference"
    assert dep["deployed"] is True
    meta = dep["model_meta"]
    assert meta["kind"] == "centroid"
    assert meta["n_centroids"] == 3
    assert meta["n_params"] == 3 * (64 // 2 + 1)


def test_rff_pipeline_batch_grouping_uses_run_id(tmp_path):
    """run_id 分组口径：每 run 自成一组——折叠数与组数一致（24 组、k=4→4 折）。"""
    cfg = _build_dataset(tmp_path)
    out = run_rff_pipeline(cfg, {"nfft": 64, "k": 4})
    ev = out["evaluation"]
    assert ev["effective_k"] == 4
    assert sum(f["n_test"] for f in ev["per_fold"]) == 24
    # 组粒度划分：每折 test 样本数=分到该折的 run 数（每 run 恰 1 样本）
    assert all(0 < f["n_test"] <= 24 - 4 + 1 for f in ev["per_fold"])


def test_rff_pipeline_insufficient_samples_rejected(tmp_path):
    """数据不足拒训：有效样本 < min_samples → TrainError（附数与阈值）。"""
    cfg = _build_dataset(tmp_path, per_class=1)  # 仅 3 条
    with pytest.raises(TrainError, match="min_samples"):
        run_rff_pipeline(cfg, {"nfft": 64})
    # 显式抬高阈值同样拒
    full = _build_dataset(tmp_path / "full")
    with pytest.raises(TrainError, match="50"):
        run_rff_pipeline(full, {"nfft": 64, "min_samples": 50})


def test_rff_pipeline_zero_match_rejected(tmp_path):
    """零匹配拒训：查询无命中 → TrainError（附 0 条）。"""
    cfg = _build_dataset(tmp_path)
    cfg = {**cfg, "query": {"style": "nonexistent"}}
    with pytest.raises(TrainError, match="0 条"):
        run_rff_pipeline(cfg, {"nfft": 64})


def test_rff_pipeline_single_class_rejected(tmp_path):
    """类别覆盖不足拒训：单类样本（≥min_samples）→ TrainError。"""
    index_path = tmp_path / "index.json"
    for k in range(6):
        _register(tmp_path, index_path, f"20260102-00000{k}", "tone_lo", _tone_iq(0.1, seed=k))
    cfg = {
        "query": {"style": "tone_lo"},
        "index_path": str(index_path),
        "runs_root": str(tmp_path / "runs_root"),
    }
    with pytest.raises(TrainError, match="2 类"):
        run_rff_pipeline(cfg, {"nfft": 64, "min_samples": 5})


def test_rff_pipeline_short_segments_counted_skipped(tmp_path):
    """短段跳段：IQ 段长不足窗长计入 skipped、不短路管道。"""
    index_path = tmp_path / "index.json"
    for ci, style in enumerate(_STYLES):
        for k in range(8):
            _register(
                tmp_path,
                index_path,
                f"20260103-0000{ci}{k}",
                style,
                _tone_iq(_FREQS[style], seed=ci * 10 + k),
            )
    # 两条脏 run：段长 32 < nfft=64 → make_spectrogram skipped=1 计跳段
    _register(tmp_path, index_path, "20260103-short01", "tone_lo", _tone_iq(0.1, n=32, seed=1))
    _register(tmp_path, index_path, "20260103-short02", "tone_mid", _tone_iq(0.3, n=32, seed=2))
    cfg = {
        "query": {"style": list(_STYLES)},
        "index_path": str(index_path),
        "runs_root": str(tmp_path / "runs_root"),
    }
    out = run_rff_pipeline(cfg, {"nfft": 64, "k": 5})
    assert out["n_samples"] == 24
    assert out["skipped"] == 2
    assert out["evaluation"]["macro_f1"] > 0.8


def test_rff_pipeline_shape_errors():
    """形状错 ValueError：dataset_config/hyperparams/query/超参不可转 int/k<2。"""
    with pytest.raises(ValueError):
        run_rff_pipeline(None, {})
    with pytest.raises(ValueError):
        run_rff_pipeline({}, {})
    with pytest.raises(ValueError):
        run_rff_pipeline({"query": "style=tone"}, {})
    with pytest.raises(ValueError):
        run_rff_pipeline({"query": {}}, ["hp"])
    with pytest.raises(ValueError):
        run_rff_pipeline({"query": {}}, {"nfft": "wide"})
    with pytest.raises(ValueError):
        run_rff_pipeline({"query": {}}, {"min_samples": 0})
    with pytest.raises(ValueError):
        run_rff_pipeline({"query": {}}, {"k": 1})
