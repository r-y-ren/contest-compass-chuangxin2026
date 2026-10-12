"""predict_style 对抗测试（slug=infer_service）：识别推理入口——模型缺失不阻塞、
SigMF/直给/批量 IQ 取数、dummy 规则分类、结果行契约（B14 顶层/R32）。"""
from __future__ import annotations

import json
import re

import numpy as np
import pytest

from src.index_dataset.index_dataset import index_dataset
from src.predict_style.predict_style import predict_style

#: 七类样式标签域（六生成样式 + composite）——dummy 分类器的匹配名集
_LABELS = [
    "tone",
    "sweep",
    "chirp",
    "bandlimited_noise",
    "partial_band",
    "pulse",
    "composite",
]


def _dummy_model(weights=None):
    """本批实现的规则分类器模型（可携带 weights 参与 model_version 摘要）。"""
    model = {"kind": "cnn_dummy", "labels": list(_LABELS)}
    if weights is not None:
        model["weights"] = weights
    return model


def _tone_iq():
    """0.1fs 单音（质心特征主导：正频率轴折合位置 0.2）。"""
    return np.exp(1j * 2.0 * np.pi * 0.1 * np.arange(4096)).astype(np.complex64)


def _wide_noise_iq():
    """宽带噪声（带宽特征主导：占 Nyquist 200k/500k=0.4）。"""
    rng = np.random.default_rng(7)
    n = 8192
    white = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    spec = np.fft.fft(white)
    freqs = np.fft.fftfreq(n, d=1.0 / 1e6)
    return np.fft.ifft(spec * (np.abs(freqs) < 100e3)).astype(np.complex64)


def _write_sigmf_pair(directory, iq, fs=1e6):
    """tmp 下写 cf32 单音 SigMF 对（meta+data），返回 meta 路径。"""
    stem = directory / "rec"
    np.asarray(iq, dtype=np.complex64).tofile(str(stem) + ".sigmf-data")
    meta = {
        "global": {
            "core:sample_rate": fs,
            "core:datatype": "cf32_le",
            "core:num_samples": int(np.asarray(iq).size),
        },
        "captures": [{"core:sample_start": 0}],
        "annotations": [],
    }
    (directory / "rec.sigmf-meta").write_text(
        json.dumps(meta), encoding="utf-8"
    )
    return str(directory / "rec.sigmf-meta")


def test_infer_service_no_model_unrecognized_not_blocking():
    """① 无模型 → no_model 结果行（R32 规约原文 note），不抛异常。"""
    result = predict_style(_tone_iq(), model=None)
    assert result["status"] == "no_model"
    assert result["recognized"] is False
    assert "不阻塞" in result["note"]


def test_infer_service_unreadable_model_path_no_model(tmp_path):
    """② 模型路径坏（文件缺失 / 根非 JSON 对象）→ no_model 语义 + note 含'模型文件不可读'。"""
    missing = predict_style(_tone_iq(), model="/nonexistent/model.json")
    assert missing["status"] == "no_model"
    assert missing["recognized"] is False
    assert "模型文件不可读" in missing["note"]

    not_object = tmp_path / "list_model.json"
    not_object.write_text("[1, 2, 3]", encoding="utf-8")
    listed = predict_style(_tone_iq(), model=str(not_object))
    assert listed["status"] == "no_model"
    assert "模型文件不可读" in listed["note"]


def test_infer_service_corrupt_model_file_no_model(tmp_path):
    """②b 模型文件存在但损坏（非法 JSON）→ no_model + note。"""
    bad = tmp_path / "bad_model.json"
    bad.write_text("{not json", encoding="utf-8")
    result = predict_style(_tone_iq(), model=str(bad))
    assert result["status"] == "no_model"
    assert result["recognized"] is False
    assert "模型文件不可读" in result["note"]


def test_infer_service_single_tone_label_tone():
    """③ 0.1fs 单音 IQ → label='tone'（质心特征主导，折合位置≈0.2）。"""
    result = predict_style(_tone_iq(), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["recognized"] is True
    assert result["label"] == "tone"
    assert abs(result["features"]["centroid_hz"] - 0.2) < 0.05


def test_infer_service_wideband_noise_label_bandlimited_noise():
    """④ 宽带噪声 IQ → label='bandlimited_noise'（带宽特征宽，>0.1 正频率轴）。"""
    result = predict_style(_wide_noise_iq(), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "bandlimited_noise"
    assert result["features"]["bandwidth_3db"] > 0.1


def test_infer_service_none_iq_status_no_iq():
    """⑤ iq_source=None（模型有效）→ no_iq，不抛。"""
    result = predict_style(None, model=_dummy_model())
    assert result["status"] == "no_iq"
    assert result["recognized"] is False


def test_infer_service_sigmf_path_recognizes_tone(tmp_path):
    """⑥ SigMF meta 路径（tmp cf32 单音对）→ ok+tone，iq_source 摘要带 sigmf 前缀。"""
    meta_path = _write_sigmf_pair(tmp_path, _tone_iq())
    result = predict_style(meta_path, model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    assert result["iq_source"].startswith("sigmf:")


def test_infer_service_cnn_kind_unsupported():
    """⑦ kind='cnn'（真网络归远期）→ unsupported_model，recognized=False，不抛。"""
    inline = predict_style(_tone_iq(), model={"kind": "cnn", "labels": list(_LABELS)})
    assert inline["status"] == "unsupported_model"
    assert inline["recognized"] is False
    assert "not_implemented_yet" in inline["note"]

    unknown = predict_style(_tone_iq(), model={"kind": "svm"})
    assert unknown["status"] == "unsupported_model"


def test_infer_service_batch_list_per_item_results():
    """⑧ 批量 list[单源] → 结果 list 且逐源独立（ok/no_iq/ok）。"""
    results = predict_style(
        [_tone_iq(), None, _wide_noise_iq()], model=_dummy_model()
    )
    assert isinstance(results, list)
    assert len(results) == 3
    assert results[0]["status"] == "ok" and results[0]["label"] == "tone"
    assert results[1]["status"] == "no_iq"
    assert results[2]["status"] == "ok" and results[2]["label"] == "bandlimited_noise"


def test_infer_service_confidence_within_unit_range():
    """⑨ confidence ∈ [0,1]（tone 与宽带噪声两路）。"""
    for iq in (_tone_iq(), _wide_noise_iq()):
        result = predict_style(iq, model=_dummy_model())
        assert 0.0 <= result["confidence"] <= 1.0


def test_infer_service_features_key_set_and_range():
    """⑩ features 键集恰 {centroid_hz, bandwidth_3db}，相对量纲均在 [0,1]。"""
    result = predict_style(_tone_iq(), model=_dummy_model())
    assert set(result["features"]) == {"centroid_hz", "bandwidth_3db"}
    for value in result["features"].values():
        assert isinstance(value, float)
        assert 0.0 <= value <= 1.0


def test_infer_service_model_version_format():
    """⑪ model_version：有 weights → kind-8 位十六进制摘要且同 weights 稳定；
    无 weights → 'cnn_dummy-dummy'。"""
    with_weights = predict_style(_tone_iq(), model=_dummy_model({"rule": "v1"}))
    assert re.fullmatch(r"cnn_dummy-[0-9a-f]{8}", with_weights["model_version"])
    again = predict_style(_tone_iq(), model=_dummy_model({"rule": "v1"}))
    assert again["model_version"] == with_weights["model_version"]
    changed = predict_style(_tone_iq(), model=_dummy_model({"rule": "v2"}))
    assert changed["model_version"] != with_weights["model_version"]

    bare = predict_style(_tone_iq(), model=_dummy_model())
    assert bare["model_version"] == "cnn_dummy-dummy"


def test_infer_service_invalid_nfft_value_error():
    """⑫ nfft 非法（0 / <8）→ ValueError 透传（make_spectrogram 域校验）。"""
    with pytest.raises(ValueError):
        predict_style(_tone_iq(), model=_dummy_model(), nfft=0)
    with pytest.raises(ValueError):
        predict_style(_tone_iq(), model=_dummy_model(), nfft=4)


def test_infer_service_broken_sigmf_bad_iq(tmp_path):
    """⑬ 坏 SigMF（meta 在 data 缺 / 路径不存在）→ bad_iq，recognized=False，不抛。"""
    meta_only = tmp_path / "half.sigmf-meta"
    meta_only.write_text(
        json.dumps(
            {
                "global": {
                    "core:sample_rate": 1e6,
                    "core:datatype": "cf32_le",
                    "core:num_samples": 16,
                },
                "captures": [{"core:sample_start": 0}],
                "annotations": [],
            }
        ),
        encoding="utf-8",
    )
    truncated = predict_style(str(meta_only), model=_dummy_model())
    assert truncated["status"] == "bad_iq"
    assert truncated["recognized"] is False

    missing = predict_style(str(tmp_path / "nope.sigmf-meta"), model=_dummy_model())
    assert missing["status"] == "bad_iq"
    assert missing["recognized"] is False


def test_infer_service_short_iq_status():
    """⑭ 段长不足一个窗长（16 < nfft=256）→ short_iq，不参与分类。"""
    result = predict_style(np.zeros(16, dtype=np.complex64), model=_dummy_model())
    assert result["status"] == "short_iq"
    assert result["recognized"] is False


def test_infer_service_list_iq_direct():
    """⑮ list 形态 IQ（complex 样本 list）直用 → 单段 ok（非批量路径）。"""
    result = predict_style(_tone_iq().tolist(), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    assert result["iq_source"].startswith("list[")


def test_infer_service_dataset_query_optional_path(tmp_path, monkeypatch):
    """⑯ 可选数据集取数路径：dict 检索条件 → 索引命中 recordings 内 SigMF → tone。

    chdir 到 tmp 使 index_dataset 缺省相对索引落点（fn_work/dataset/index.json）
    解析在 tmp 下，不触碰真实目录（与 index_dataset 测试同口径）。
    """
    runs_root = tmp_path / "fn_work" / "dataset" / "runs"
    rec_dir = runs_root / "20260101-000000" / "recordings"
    rec_dir.mkdir(parents=True)
    _write_sigmf_pair(rec_dir, _tone_iq())
    (runs_root / "20260101-000000" / "result.json").write_text(
        json.dumps(
            {
                "status": "done",
                "style": "tone",
                "freq_mhz": 100.0,
                "backend": "sim",
                "date": "20260101",
            }
        ),
        encoding="utf-8",
    )
    index_dataset(
        "rebuild",
        index_path=str(tmp_path / "fn_work" / "dataset" / "index.json"),
        runs_root=str(runs_root),
    )
    monkeypatch.chdir(tmp_path)

    result = predict_style({"style": "tone"}, model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    assert result["iq_source"].startswith("sigmf:")
