"""demo_rff_pipeline 单测（R74）：smoke 四阶段进度（fetch/features/grouped_cv/
deploy 阶段字段）+产物清单（model/evaluation/deployment）+数据不足拒跑分支
（TrainError 原文上抛）+params 形状错拒绝+端点合约（POST /api/demo/rff——索引
落点缺省注入+拒跑 400）+页区静态资产零外链。用例名统一 ``test_rff_view_``
前缀（`pytest -k rff_view` 发现——R74 核验命令真身：阶段字段+拒跑分支）。

被测实现口径见 src/demo_rff_pipeline/demo_rff_pipeline.py 模块 docstring
（run_rff_pipeline smoke 小样本固定参数/TrainError 拒跑口径）。
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

from src.demo_rff_pipeline.demo_rff_pipeline import (
    DEMO_K,
    DEMO_MIN_SAMPLES,
    DEMO_NFFT,
    RFF_STAGES,
    demo_rff_pipeline,
)
from src.demo_rff_pipeline.rff_area import RFF_STAGE_CLASS, build_rff_pipeline_area
from src.index_dataset.index_dataset import index_dataset
from src.run_rff_pipeline.run_rff_pipeline import TrainError

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)

_STYLES = ("tone_lo", "tone_hi")  # 2 类：0.15/0.45 fs 单音（谱峰可分）
_FREQS = {"tone_lo": 0.15, "tone_hi": 0.45}


def _tone_iq(freq, n=512, seed=0):
    """归一化频点单音（complex64——种子只影响微小加噪，保两类谱峰可分）。"""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    iq = np.exp(1j * 2.0 * np.pi * freq * t) + 0.01 * (
        rng.standard_normal(n) + 1j * rng.standard_normal(n)
    )
    return iq.astype(np.complex64)


def _build_dataset(tmp_path, per_class=3):
    """2 类 × per_class 个 run 的临时 SigMF 数据集+索引，返回落点 dict。"""
    runs_root = tmp_path / "runs_root"
    runs_root.mkdir(exist_ok=True)
    index_path = tmp_path / "index.json"
    for ci, style in enumerate(_STYLES):
        for k in range(per_class):
            run_id = f"20260101-0000{ci}{k}"
            rec_dir = runs_root / run_id / "recordings"
            rec_dir.mkdir(parents=True)
            np.asarray(_tone_iq(_FREQS[style], seed=ci * 100 + k)).tofile(
                str(rec_dir / "rec.sigmf-data")
            )
            meta = {
                "global": {
                    "core:sample_rate": 1e6,
                    "core:datatype": "cf32_le",
                    "core:num_samples": 512,
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
                    "date": "20260101",
                    "backend": "sim",
                },
                index_path=str(index_path),
                runs_root=str(runs_root),
            )
    return {"index_path": str(index_path), "runs_root": str(runs_root)}


# ---- 阶段字段（R74 验收真身①） ----


def test_rff_view_stage_fields_and_artifacts(tmp_path):
    """① smoke 四阶段：stages 序=fetch/features/grouped_cv/deploy 全 done
    （逐阶段 detail 带数）+stage_progress '4/4'+产物清单三行（model/
    evaluation/deployment——参数量/折数/latency_note 如实）。"""
    paths = _build_dataset(tmp_path)
    view = demo_rff_pipeline(paths)
    assert view["ok"] is True and view["smoke"] is True
    assert [s["stage"] for s in view["stages"]] == list(RFF_STAGES)
    assert all(s["status"] == "done" for s in view["stages"])
    assert view["stage_progress"] == "4/4"
    fetch, features, cv, deploy = view["stages"]
    assert f"命中 {view['n_samples'] + view['skipped']} 条" in fetch["detail"]
    assert f"nfft={DEMO_NFFT}" in features["detail"] and "跳段" in features["detail"]
    assert f"k={DEMO_K}" in cv["detail"] and "macro_f1=" in cv["detail"]
    assert "local-inference" in deploy["detail"] and "latency_note=simulated" in deploy["detail"]
    assert view["n_samples"] == 6 and view["evaluation"]["macro_f1"] == pytest.approx(1.0)
    names = [a["name"] for a in view["artifacts"]]
    assert names == ["model", "evaluation", "deployment"]
    model_art = view["artifacts"][0]
    assert model_art["n_params"] == view["model_meta"]["n_params"] > 0
    assert view["deployment"]["latency_note"] == "simulated"
    assert "smoke" in view["note"] and "simulated" in view["note"]
    assert view["params_effective"]["nfft"] == DEMO_NFFT
    assert view["params_effective"]["min_samples"] == DEMO_MIN_SAMPLES
    assert view["params_effective"]["k"] == DEMO_K


def test_rff_view_hyperparams_override(tmp_path):
    """② hyperparams 同键覆盖（显式给出则尊重）：k=2 生效并落 params_effective。"""
    paths = _build_dataset(tmp_path, per_class=2)
    view = demo_rff_pipeline({**paths, "hyperparams": {"k": 2}})
    assert view["params_effective"]["k"] == 2
    assert "k=2" in view["stages"][2]["detail"]


def test_rff_view_params_shape_errors(tmp_path):
    """③ params 形状错：非 dict/query 非 dict/hyperparams 非 dict→ValueError。"""
    with pytest.raises(ValueError, match="params 必须"):
        demo_rff_pipeline("nope")
    with pytest.raises(ValueError, match="query"):
        demo_rff_pipeline({"query": "nope"})
    with pytest.raises(ValueError, match="hyperparams"):
        demo_rff_pipeline({"hyperparams": 3})
    paths = _build_dataset(tmp_path)
    with pytest.raises(ValueError, match="index_path"):
        demo_rff_pipeline({**paths, "index_path": "  "})


# ---- 拒跑分支（R74 验收真身②——R55 口径） ----


def test_rff_view_insufficient_data_refused(tmp_path):
    """④ 数据不足拒跑：空索引（查询零匹配）→TrainError 原文上抛（附数与
    提示——不静默不虚构）。"""
    runs_root = tmp_path / "empty_root"
    runs_root.mkdir()
    with pytest.raises(TrainError, match="数据不足拒训"):
        demo_rff_pipeline(
            {"index_path": str(tmp_path / "empty-index.json"), "runs_root": str(runs_root)}
        )


def test_rff_view_min_samples_refused(tmp_path):
    """⑤ 有效样本不足拒跑：min_samples 抬到样本量之上→TrainError 附阈值。"""
    paths = _build_dataset(tmp_path, per_class=2)  # 4 样本
    with pytest.raises(TrainError, match="min_samples=99"):
        demo_rff_pipeline({**paths, "hyperparams": {"min_samples": 99}})


# ---- 端点合约：POST /api/demo/rff ----


@needs_fastapi
def test_rff_view_endpoint_contract(tmp_path):
    """⑥ 端点合约：POST /api/demo/rff（body 可空）→索引落点缺省注入
    report_root 口径——空 report_root 数据不足→400 拒跑提示上屏 field='params'；
    显式 params 指到已建数据集→200 四阶段视图。"""
    report_root = tmp_path / "reports"
    report_root.mkdir()
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path / "scenarios"),
        "report_root": str(report_root),
        "static_pages": {},
    }
    client = TestClient(create_console_app(deps))

    resp = client.post("/api/demo/rff", json={})
    assert resp.status_code == 400  # report_root 无数据：拒跑提示上屏不静默
    detail = resp.json()["detail"]
    assert detail["field"] == "params" and "数据不足拒训" in detail["error"]

    paths = _build_dataset(tmp_path)
    resp = client.post(
        "/api/demo/rff", json={"params": paths}
    )
    assert resp.status_code == 200
    view = resp.json()
    assert view["stage_progress"] == "4/4" and view["ok"] is True

    resp = client.post("/api/demo/rff", json={"params": "nope"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "params"

    resp = client.post(
        "/api/demo/rff", content=b"", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400  # 空 body→缺省注入 report_root（无数据拒跑）


# ---- 页区静态资产（serve_console instruments 页注入的 RFF 管道演示页区） ----


def test_rff_view_area_zero_external_links_and_anchors():
    """⑦ 页区资产：零外链+同源 fetch 端点字面（/api/demo/rff）+区块锚点+
    阶段行 class 锚点+四阶段/产物清单文案。"""
    block = build_rff_pipeline_area()
    assert "http://" not in block and "https://" not in block
    assert 'id="rff-pipeline-area"' in block  # 挂载区块锚点
    assert "'/api/demo/rff'" in block  # 同源相对路径 fetch
    assert RFF_STAGE_CLASS in block  # 阶段进度条目 class 锚点
    assert "阶段进度" in block and "产物清单" in block
    assert "拒跑" in block  # 数据不足拒跑提示文案锚点
