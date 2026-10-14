"""infer_style_entry 单测（R67）：已知样式样本→正确标签+真值双源对照+hit 判定；
模型缺失提示态不阻塞（R32 口径）；端点合约（POST /api/ai/infer——缺省模型
回落）+页区静态资产。用例名统一 ``test_ai_infer_view_`` 前缀（`pytest -k
ai_infer_view` 发现——R67 核验命令真身：已知样式样本→正确标签上页）。

被测实现口径见 src/infer_style_entry/infer_style_entry.py 模块 docstring
（source 三选一/真值双源/提示态行契约）。
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
from src.infer_style_entry.infer_area import build_infer_area
from src.infer_style_entry.infer_style_entry import infer_style_entry
from src.predict_style.predict_style import SEVEN_STYLE_LABELS

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)

#: 本批实现的规则分类器模型（cnn_dummy——labels 七类缺省域）。
_DUMMY_MODEL = {"kind": "cnn_dummy", "labels": list(SEVEN_STYLE_LABELS)}


def _tone_iq(n=4096):
    """0.1fs 单音（predict_style dummy 分类器判定 tone 的已知样本）。"""
    return np.exp(1j * 2.0 * np.pi * 0.1 * np.arange(n)).astype(np.complex64)


def _make_run(runs_root, run_id, style="tone", *, with_annotation=True, with_copy=True):
    """造带 SigMF 真值对的运行目录（jam:style 标注+场景副本可选）并登记索引。"""
    rec_dir = os.path.join(runs_root, run_id, "recordings")
    os.makedirs(rec_dir, exist_ok=True)
    iq = _tone_iq()
    np.asarray(iq, dtype=np.complex64).tofile(os.path.join(rec_dir, "rec.sigmf-data"))
    annotations = []
    if with_annotation:
        annotations.append(
            {
                "core:sample_start": 0,
                "core:sample_count": int(iq.size),
                "jam:style": style,  # SigMF 真值标注（标准答案源①）
            }
        )
    meta = {
        "global": {
            "core:sample_rate": 1e6,
            "core:datatype": "cf32_le",
            "core:num_samples": int(iq.size),
        },
        "captures": [{"core:sample_start": 0}],
        "annotations": annotations,
    }
    with open(os.path.join(rec_dir, "rec.sigmf-meta"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    if with_copy:
        import yaml

        with open(os.path.join(runs_root, run_id, "scenario.yaml"), "w") as fh:
            yaml.safe_dump(
                {
                    "style": style,  # 场景副本（标准答案源②）
                    "fs": 1.0e6,
                    "freq_hz": 2.4e9,
                    "power_dbm": -10.0,
                    "duration_s": 0.005,
                    "backend": "sim",
                    "bands": [[2400.0, 2483.5]],
                    "shielded_box": True,
                    "dut_scope": "self_built",
                },
                fh,
            )
    index_dataset(
        "register",
        record={
            "run_id": run_id,
            "path": rec_dir,
            "style": style,
            "freq_mhz": 2400.0,
            "date": run_id[:8],
            "backend": "sim",
        },
        index_path=os.path.join(runs_root, "dataset-index.json"),
        runs_root=runs_root,
    )
    return os.path.join(rec_dir, "rec.sigmf-meta")


def _src(runs_root, **over):
    """run_id 路的 source 底座：索引落点传输键显式注入（不触碰真实目录）。"""
    source = {
        "index_path": os.path.join(runs_root, "dataset-index.json"),
        "runs_root": runs_root,
    }
    source.update(over)
    return source


# ---- 纯函数：已知样式样本→正确标签+真值对照（R67 验收真身） ----


def test_ai_infer_view_known_sample_correct_label_and_hit(tmp_path):
    """① 已知样式样本（0.1fs 单音）→label='tone'+置信度+SigMF 标注真值对照
    hit=True（识别行字段：model_version/features/iq_source 齐备）。"""
    runs_root = str(tmp_path / "runs")
    meta = _make_run(runs_root, "20260101-000000", style="tone")
    row = infer_style_entry(
        _src(runs_root, run_id="20260101-000000", model=_DUMMY_MODEL, nfft=256)
    )
    assert row["status"] == "ok" and row["recognized"] is True
    assert row["label"] == "tone"  # 已知样式样本→正确标签
    assert 0.0 < row["confidence"] <= 1.0
    assert row["truth"] == {"source": "sigmf_annotation", "style": "tone"}
    assert row["hit"] is True  # 对照标准答案命中
    assert row["model_version"].startswith("cnn_dummy")
    assert meta in row["iq_source"]  # 来源摘要指明消费的 SigMF


def test_ai_infer_view_model_missing_hint_not_blocking(tmp_path):
    """② 模型缺失（R32 口径）→no_model 提示态行（非报错）：note 附「先训练」
    指引，真值对照照常（hit=None 不判定）。"""
    runs_root = str(tmp_path / "runs")
    _make_run(runs_root, "20260101-000000", style="tone")
    row = infer_style_entry(_src(runs_root, run_id="20260101-000000"))  # model 缺省 None
    assert row["status"] == "no_model" and row["recognized"] is False
    assert "发起训练" in row["note"] and "不阻塞" in row["note"]  # 「先训练」指引
    assert row["truth"] == {"source": "sigmf_annotation", "style": "tone"}
    assert row["hit"] is None


def test_ai_infer_view_scenario_copy_truth_fallback(tmp_path):
    """③ 真值源②：SigMF 无 jam:style 标注→场景副本 scenario.yaml 真值
    （source='scenario_copy'）——双源按序回落。"""
    runs_root = str(tmp_path / "runs")
    _make_run(runs_root, "20260102-000000", style="tone", with_annotation=False)
    row = infer_style_entry(
        _src(runs_root, run_id="20260102-000000", model=_DUMMY_MODEL)
    )
    assert row["status"] == "ok"
    assert row["truth"] == {"source": "scenario_copy", "style": "tone"}
    assert row["hit"] is True


def test_ai_infer_view_no_truth_hit_none(tmp_path):
    """④ 真值双源皆缺→truth.style=None 如实标注（不虚构）——hit=None。"""
    runs_root = str(tmp_path / "runs")
    _make_run(runs_root, "20260103-000000", with_annotation=False, with_copy=False)
    row = infer_style_entry(
        _src(runs_root, run_id="20260103-000000", model=_DUMMY_MODEL)
    )
    assert row["status"] == "ok" and row["label"] == "tone"
    assert row["truth"] == {"source": None, "style": None}
    assert row["hit"] is None


def test_ai_infer_view_truth_disagrees_hit_false(tmp_path):
    """⑤ 真值与识别不一致（标注 style='chirp' 的单音录音）→hit=False 如实
    （对照语义不粉饰）。"""
    runs_root = str(tmp_path / "runs")
    _make_run(runs_root, "20260104-000000", style="chirp")  # 标注与实际样式不符
    row = infer_style_entry(
        _src(runs_root, run_id="20260104-000000", model=_DUMMY_MODEL)
    )
    assert row["label"] == "tone"  # 识别按 IQ 实际特征
    assert row["truth"]["style"] == "chirp"
    assert row["hit"] is False


def test_ai_infer_view_sigmf_path_and_query_sources(tmp_path):
    """⑥ 源三选一：sigmf_path 直给与 query 检索两路均定位同一录音并识别。"""
    runs_root = str(tmp_path / "runs")
    meta = _make_run(runs_root, "20260105-000000", style="tone")
    row = infer_style_entry({"sigmf_path": meta, "model": _DUMMY_MODEL})
    assert row["status"] == "ok" and row["hit"] is True
    row = infer_style_entry(
        _src(runs_root, query={"style": "tone"}, model=_DUMMY_MODEL)
    )
    assert row["status"] == "ok" and row["label"] == "tone"


def test_ai_infer_view_unknown_run_status_row(tmp_path):
    """⑦ 条目不在库→no_iq 提示态行（原因注进 note），不抛不 500。"""
    runs_root = str(tmp_path / "runs")
    _make_run(runs_root, "20260106-000000", style="tone")
    row = infer_style_entry(
        _src(runs_root, run_id="19700101-000000", model=_DUMMY_MODEL)
    )
    assert row["status"] == "no_iq" and row["recognized"] is False
    assert "不在库" in row["note"]
    assert row["hit"] is None


def test_ai_infer_view_short_iq_status_kept(tmp_path):
    """⑧ 样本过短（< nfft）→predict_style 的 short_iq 行原样（R32 跳段口径）。"""
    runs_root = str(tmp_path / "runs")
    rec_dir = os.path.join(runs_root, "20260107-000000", "recordings")
    os.makedirs(rec_dir)
    np.zeros(8, dtype=np.complex64).tofile(os.path.join(rec_dir, "rec.sigmf-data"))
    with open(os.path.join(rec_dir, "rec.sigmf-meta"), "w", encoding="utf-8") as fh:
        json.dump(
            {
                "global": {
                    "core:sample_rate": 1e6,
                    "core:datatype": "cf32_le",
                    "core:num_samples": 8,
                },
                "captures": [{"core:sample_start": 0}],
                "annotations": [
                    {"core:sample_start": 0, "core:sample_count": 8, "jam:style": "tone"}
                ],
            },
            fh,
        )
    row = infer_style_entry(
        {
            "sigmf_path": os.path.join(rec_dir, "rec.sigmf-meta"),
            "model": _DUMMY_MODEL,
        }
    )
    assert row["status"] == "short_iq" and row["recognized"] is False
    assert "不足" in row["note"]
    assert row["truth"]["style"] == "tone"  # 真值对照独立于推理成败
    assert row["hit"] is None


def test_ai_infer_view_bad_source_shape_value_error(tmp_path):
    """⑨ 源形状错 ValueError：source 非 dict/三选一全缺/sigmf_path 空/nfft 非 int。"""
    with pytest.raises(ValueError, match="source 必须为 dict"):
        infer_style_entry("run_id=x")
    with pytest.raises(ValueError, match="三选一"):
        infer_style_entry({"model": _DUMMY_MODEL})
    with pytest.raises(ValueError, match="sigmf_path"):
        infer_style_entry({"sigmf_path": "  "})
    with pytest.raises(ValueError, match="nfft"):
        infer_style_entry({"sigmf_path": "x.sigmf-meta", "nfft": "wide"})


# ---- 端点合约：POST /api/ai/infer（缺省模型回落） ----


def _client(tmp_path, with_model=True):
    """装配真 app+合成运行目录；with_model=True 时预置缺省模型文件
    （report_root/models/style_classifier.json——端点回落对象）。"""
    runs_root = str(tmp_path / "runs")
    _make_run(runs_root, "20260101-000000", style="tone")
    if with_model:
        models_dir = os.path.join(runs_root, "models")
        os.makedirs(models_dir, exist_ok=True)
        with open(os.path.join(models_dir, "style_classifier.json"), "w", encoding="utf-8") as fh:
            json.dump(_DUMMY_MODEL, fh)
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path),
        "report_root": runs_root,
        "static_pages": {},
    }
    return TestClient(create_console_app(deps))


@needs_fastapi
def test_ai_infer_view_endpoint_default_model_and_hit(tmp_path):
    """⑩ 端点：POST /api/ai/infer {'run_id'}→200 识别行——缺省模型回落
    （models/style_classifier.json 在位即用）+真值对照 hit=True 上页。"""
    client = _client(tmp_path)
    resp = client.post("/api/ai/infer", json={"run_id": "20260101-000000"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok" and payload["label"] == "tone"
    assert payload["truth"] == {"source": "sigmf_annotation", "style": "tone"}
    assert payload["hit"] is True


@needs_fastapi
def test_ai_infer_view_endpoint_no_model_hint_state(tmp_path):
    """⑪ 端点模型缺失（models/ 无文件）→200 no_model 提示态（不阻塞——
    非 500/400），note 含「先训练」指引。"""
    client = _client(tmp_path, with_model=False)
    resp = client.post("/api/ai/infer", json={"run_id": "20260101-000000"})
    assert resp.status_code == 200  # 提示态非报错（R67/R32 口径）
    payload = resp.json()
    assert payload["status"] == "no_model"
    assert "发起训练" in payload["note"]  # 「先训练」指引


@needs_fastapi
def test_ai_infer_view_endpoint_bad_shape_400(tmp_path):
    """⑫ 端点形状错→400：source 缺三选一键 field='source'；body 非 JSON
    field='body'。"""
    client = _client(tmp_path)
    resp = client.post("/api/ai/infer", json={"model": "x.json"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "source"
    resp = client.post(
        "/api/ai/infer", content=b"not-json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400 and resp.json()["detail"]["field"] == "body"


# ---- 页区静态资产（零外链红线+挂载点/端点接线） ----


def test_ai_infer_view_infer_area_zero_external_links_and_wiring():
    """⑬ infer 页区零外链（R56 断网全可用红线）+消费挂载点与端点接线。"""
    block = build_infer_area()
    assert "http://" not in block and "https://" not in block
    assert "'infer-panel'" in block  # 挂载点
    assert "'/api/ai/infer'" in block  # 推理数据源
    assert "标准答案" in block and "命中" in block  # 真值对照要素
    assert "识别" in block  # 表单按钮
