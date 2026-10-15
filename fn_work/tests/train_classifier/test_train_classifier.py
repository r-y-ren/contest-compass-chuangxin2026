"""train_classifier 对抗单测：tmp_path+合成谱特征数据集（index_dataset register 造条目+临时 SigMF cf32 单音/噪声对）——slug=train_classifier；远程路径全 mock 不触真 subprocess。

走查 C1+I4 追加（2026-10-15）：跳段归因分列（style 缺失 vs 段长/数据不可读）
单测 + record:true 真产物（manage_run 全生命周期落盘）→rebuild→train 用户路径
端到端封堵用例。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

import src.train_classifier.train_classifier as mod
from src.index_dataset.index_dataset import index_dataset
from src.manage_run.manage_run import manage_run
from src.train_classifier.dispatch_remote_training import RemoteError
from src.train_classifier.train_classifier import TrainError, train_classifier

DEGRADE_HINT = "where='local'"


# --- 合成数据集：临时 SigMF cf32 对（单音/带限噪声）+ index_dataset register ---


def _tone_iq(n=512):
    """0.1fs 单音（complex64，长度 ≥ nfft=64 出有效谱）。"""
    return np.exp(1j * 2.0 * np.pi * 0.1 * np.arange(n)).astype(np.complex64)


def _noise_iq(n=512, seed=11):
    """复高斯噪声（complex64）。"""
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex64)


def _register(tmp_path, index_path, run_id, style, iq, date="20260101"):
    """写 run_id/recordings/rec.sigmf-{data,meta} 对并登记索引。"""
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


def _dataset(tmp_path, per_class=12, classes=("tone", "bandlimited_noise")):
    """两类×per_class 条登记 → (index_path, 条目总数)。IQ 长 512 ≥ nfft=64 全有效。"""
    index_path = tmp_path / "index.json"
    total = 0
    for cls_idx, style in enumerate(classes):
        for i in range(per_class):
            iq = (
                _tone_iq()
                if style == "tone"
                else _noise_iq(seed=100 + cls_idx * 50 + i)
            )
            _register(tmp_path, index_path, f"run{cls_idx:02d}{i:03d}", style, iq)
            total += 1
    return index_path, total


def _hp(tmp_path, index_path, **over):
    """基础超参：tmp 索引/落点+nfft=64（IQ 512 段全有效）。"""
    hp = {
        "index_path": str(index_path),
        "runs_root": str(tmp_path / "runs_root"),
        "nfft": 64,
        "out_path": str(tmp_path / "models" / "style_classifier.json"),
    }
    hp.update(over)
    return hp


def _patch_dispatch(monkeypatch, behavior):
    """哨兵替换 train_classifier 模块内的 dispatch_remote_training；behavior:
    ('return', dict) → 返回该 dict 副本；('raise', RemoteError) → 抛出。返回调用记录列表。"""
    calls = []

    def fake_dispatch(task_package, *, dry_run=False):
        calls.append({"task_package": task_package, "dry_run": dry_run})
        if behavior[0] == "raise":
            raise behavior[1]
        return dict(behavior[1])

    monkeypatch.setattr(mod, "dispatch_remote_training", fake_dispatch)
    return calls


# --- ⑤ local：dummy 训练器产模型文件 ---


def test_train_classifier_local_dummy_model_labels_and_mean_spectra(tmp_path):
    """① local 训练→模型文件存在+labels 含两类+class_mean_spectra 键与 labels 齐且长度=nfft//2+1。"""
    index_path, _ = _dataset(tmp_path, per_class=12)
    result = train_classifier(
        {"style": ["tone", "bandlimited_noise"]},
        hyperparams=_hp(tmp_path, index_path),
        where="local",
    )
    assert result["where"] == "local"
    assert set(result["labels"]) == {"tone", "bandlimited_noise"}
    assert Path(result["model_path"]).is_file()
    model = json.loads(Path(result["model_path"]).read_text(encoding="utf-8"))
    assert set(model["class_mean_spectra"]) == set(result["labels"])
    for label, spec in model["class_mean_spectra"].items():
        assert isinstance(spec, list) and len(spec) == 64 // 2 + 1
        assert all(np.isfinite(spec))


def test_train_classifier_model_json_parses_with_kind_and_labels(tmp_path):
    """⑬ 模型 json 可解析含 kind='cnn_dummy' 与 labels（min_samples 覆盖为小阈值走通）。"""
    index_path, _ = _dataset(tmp_path, per_class=3)
    out = tmp_path / "nested" / "model.json"
    result = train_classifier(
        {"style": ["tone", "bandlimited_noise"]},
        hyperparams=_hp(tmp_path, index_path, min_samples=6, out_path=str(out)),
        where="local",
    )
    model = json.loads(out.read_text(encoding="utf-8"))
    assert model["kind"] == "cnn_dummy"
    assert model["labels"] == result["labels"]
    assert set(model["train_meta"]) >= {"n_samples", "nfft", "per_class"}


def test_train_classifier_custom_out_path_auto_creates_directory(tmp_path):
    """⑥ out_path 自定义+父目录不存在→目录自动建且文件落位，model_path 原样返回。"""
    index_path, _ = _dataset(tmp_path, per_class=3)
    out = tmp_path / "deep" / "a" / "b" / "cls.json"
    result = train_classifier(
        {"style": ["tone", "bandlimited_noise"]},
        hyperparams=_hp(tmp_path, index_path, min_samples=6, out_path=str(out)),
        where="local",
    )
    assert result["model_path"] == str(out)
    assert out.parent.is_dir()
    assert out.is_file()


# --- ③ 样本量/类别覆盖校验（不足拒训） ---


def test_train_classifier_insufficient_samples_below_default_20(tmp_path):
    """② 有效样本 10 < 缺省 min_samples=20 → TrainError 附 10 与 20 两数。"""
    index_path, _ = _dataset(tmp_path, per_class=5)
    with pytest.raises(TrainError) as excinfo:
        train_classifier(
            {"style": ["tone", "bandlimited_noise"]},
            hyperparams=_hp(tmp_path, index_path),
            where="local",
        )
    msg = str(excinfo.value)
    assert "10" in msg and "20" in msg


def test_train_classifier_zero_matched_rejected_with_count(tmp_path):
    """①b 查询零匹配（未知样式）→ TrainError「样本不足」附 matched 0。"""
    index_path, _ = _dataset(tmp_path, per_class=12)
    with pytest.raises(TrainError) as excinfo:
        train_classifier(
            {"style": "no_such_style"}, hyperparams=_hp(tmp_path, index_path), where="local"
        )
    assert "0" in str(excinfo.value)


def test_train_classifier_all_segments_skipped_rejected(tmp_path):
    """⑦ 全跳（IQ 段 32 < nfft 64）→ TrainError 附有效数 0 与阈值 20。"""
    index_path = tmp_path / "index.json"
    for i in range(6):
        style = "tone" if i % 2 == 0 else "bandlimited_noise"
        _register(tmp_path, index_path, f"short{i:03d}", style, _tone_iq(n=32))
    with pytest.raises(TrainError) as excinfo:
        train_classifier(
            {"style": ["tone", "bandlimited_noise"]},
            hyperparams=_hp(tmp_path, index_path),
            where="local",
        )
    msg = str(excinfo.value)
    assert "0" in msg and "20" in msg


def test_train_classifier_single_class_rejected(tmp_path):
    """③ 单类（22 条全 tone）→ TrainError 类别覆盖不足。"""
    index_path = tmp_path / "index.json"
    for i in range(22):
        _register(tmp_path, index_path, f"one{i:03d}", "tone", _tone_iq())
    with pytest.raises(TrainError) as excinfo:
        train_classifier({"style": "tone"}, hyperparams=_hp(tmp_path, index_path), where="local")
    assert "类别" in str(excinfo.value)


# --- 计数口径 ---


def test_train_classifier_n_samples_equals_matched_minus_skipped(tmp_path):
    """⑨ 混 3 条短段：n_samples = matched(27) - skipped(3)，skipped 计数透传。"""
    index_path, total = _dataset(tmp_path, per_class=12)
    for i in range(3):
        _register(tmp_path, index_path, f"tail{i:03d}", "tone", _tone_iq(n=32))
    total += 3
    result = train_classifier(
        {"style": ["tone", "bandlimited_noise"]},
        hyperparams=_hp(tmp_path, index_path),
        where="local",
    )
    assert total == 27
    assert result["skipped"] == 3
    assert result["n_samples"] == 27 - 3


def test_train_classifier_train_meta_per_class_counts(tmp_path):
    """⑩ train_meta.per_class 每类计数与 nfft 透传正确。"""
    index_path, _ = _dataset(tmp_path, per_class=12)
    result = train_classifier(
        {"style": ["tone", "bandlimited_noise"]},
        hyperparams=_hp(tmp_path, index_path),
        where="local",
    )
    assert result["train_meta"]["per_class"] == {"tone": 12, "bandlimited_noise": 12}
    assert result["train_meta"]["nfft"] == 64
    assert result["train_meta"]["n_samples"] == 24


# --- ④ remote：mock 派发（不触真 subprocess） ---


def test_train_classifier_remote_dry_run_no_real_dispatch(tmp_path, monkeypatch):
    """④ remote dry_run→dispatch mock 哨兵：只调一次且 dry_run=True 透传、
    包形状合法（code_root 存在/data_paths=24/entrypoint str），返回 dispatched=False 且不写模型。"""
    index_path, _ = _dataset(tmp_path, per_class=12)
    out = tmp_path / "remote_model.json"
    calls = _patch_dispatch(
        monkeypatch,
        ("return", {"dispatched": False, "dry_run": True, "runner_found": False, "package_summary": {}}),
    )
    result = train_classifier(
        {"style": ["tone", "bandlimited_noise"]},
        hyperparams=_hp(tmp_path, index_path, out_path=str(out)),
        where="remote",
        dry_run=True,
    )
    assert len(calls) == 1
    assert calls[0]["dry_run"] is True
    package = calls[0]["task_package"]
    assert Path(package["code_root"]).is_dir()
    assert len(package["data_paths"]) == 24
    assert isinstance(package["entrypoint"], str) and package["entrypoint"]
    assert isinstance(package["hyperparams"], dict)
    assert result["where"] == "remote"
    assert result["dispatched"] is False  # dispatched False 透传
    assert result["train_meta"]["dispatch"]["dry_run"] is True
    assert not out.exists()  # remote 路径不落本地模型


def test_train_classifier_remote_error_wrapped_with_local_hint(tmp_path, monkeypatch):
    """⑤ remote RemoteError（mock）→ TrainError 含原文与 where='local' 降级提示。"""
    index_path, _ = _dataset(tmp_path, per_class=12)
    _patch_dispatch(
        monkeypatch, ("raise", RemoteError("远程算力不可达——探活退出码 127"))
    )
    with pytest.raises(TrainError) as excinfo:
        train_classifier(
            {"style": ["tone", "bandlimited_noise"]},
            hyperparams=_hp(tmp_path, index_path),
            where="remote",
        )
    msg = str(excinfo.value)
    assert "探活退出码 127" in msg  # 原文包装
    assert DEGRADE_HINT in msg  # 降级提示


# --- 形状错先拒（ValueError） ---


def test_train_classifier_hyperparams_non_dict_rejected(tmp_path):
    """⑪ hyperparams 非 dict（且非 None）→ ValueError。"""
    index_path, _ = _dataset(tmp_path, per_class=3)
    with pytest.raises(ValueError):
        train_classifier(
            {"style": "tone"},
            hyperparams=[("nfft", 64), ("index_path", str(index_path))],
            where="local",
        )


def test_train_classifier_invalid_where_rejected(tmp_path):
    """⑫ where 非法（'gpu'）→ ValueError。"""
    index_path, _ = _dataset(tmp_path, per_class=3)
    with pytest.raises(ValueError):
        train_classifier(
            {"style": "tone"}, hyperparams=_hp(tmp_path, index_path), where="gpu"
        )


def test_train_classifier_query_non_dict_rejected():
    """query 形状错（list）→ ValueError（先于任何取数）。"""
    with pytest.raises(ValueError):
        train_classifier([("style", "tone")], hyperparams={}, where="local")


def test_train_classifier_unknown_query_field_wrapped_as_train_error(tmp_path):
    """⑧ query 未知字段（'foo'）→ QueryError 包装 TrainError，消息含原文字段名。"""
    index_path, _ = _dataset(tmp_path, per_class=12)
    with pytest.raises(TrainError) as excinfo:
        train_classifier(
            {"style": "tone", "foo": 1}, hyperparams=_hp(tmp_path, index_path), where="local"
        )
    assert "foo" in str(excinfo.value)


# --- 走查 I4 修复：跳段归因分列（style 缺失 vs 段长/数据不可读） ---


def _write_sigmf_pair(rec_dir, iq):
    """往 recordings 目录写 SigMF cf32 对（rec.sigmf-{data,meta}，与 _register 同形状）。"""
    rec_dir.mkdir(parents=True, exist_ok=True)
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


def test_train_classifier_skip_attribution_separates_missing_style_from_data(tmp_path):
    """I4：数据面完好（IQ 段充足可读）仅条目缺 style（rebuild 条目真跑口径：
    result.json 无 style 且无场景副本）→ 拒训消息归因「style 缺失 N 条」，
    不再误报「IQ 段长不足窗长或数据不可读」。"""
    runs_root = tmp_path / "runs_root"
    for i in range(2):
        run_dir = runs_root / f"20260101-00000{i}"
        _write_sigmf_pair(run_dir / "recordings", _tone_iq())  # 512 点段充足
        (run_dir / "result.json").write_text(
            json.dumps({"status": "done", "backend": "sim"}), encoding="utf-8"
        )  # 真跑 finalize 键集：无 style
    index_path = tmp_path / "index.json"
    index_dataset("rebuild", index_path=str(index_path), runs_root=str(runs_root))
    with pytest.raises(TrainError) as excinfo:
        train_classifier(
            {},
            hyperparams={
                "index_path": str(index_path),
                "runs_root": str(runs_root),
                "nfft": 64,
                "min_samples": 2,
            },
            where="local",
        )
    message = str(excinfo.value)
    assert "style 缺失 2 条" in message  # 归因如实分列
    assert "段长不足" not in message  # 数据面无恙：不得误报段长/不可读


def test_train_classifier_skip_attribution_lists_both_categories(tmp_path):
    """I4：混合跳段（1 条缺 style + 1 条段长 32 < nfft 64）→ 拒训消息两类
    分列各附计数。"""
    runs_root = tmp_path / "runs_root"
    rec_a = runs_root / "a" / "recordings"
    _write_sigmf_pair(rec_a, _tone_iq())  # 段充足但条目 style=None
    rec_b = runs_root / "b" / "recordings"
    _write_sigmf_pair(rec_b, _tone_iq(n=32))  # style 在但短段
    entries = [
        {
            "run_id": "a",
            "path": str(rec_a),
            "style": None,  # 缺失口径（list 读路径不做必填校验）
            "freq_mhz": 100.0,
            "date": "20260101",
            "backend": "sim",
        },
        {
            "run_id": "b",
            "path": str(rec_b),
            "style": "tone",
            "freq_mhz": 100.0,
            "date": "20260101",
            "backend": "sim",
        },
    ]
    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps({"version": 1, "entries": entries}, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(TrainError) as excinfo:
        train_classifier(
            {},
            hyperparams={
                "index_path": str(index_path),
                "runs_root": str(runs_root),
                "nfft": 64,
                "min_samples": 2,
            },
            where="local",
        )
    message = str(excinfo.value)
    assert "style 缺失 1 条" in message
    assert "IQ 段长不足窗长或数据不可读 1 条" in message


# --- 走查 C1+I4 用户路径端到端封堵：record:true 真产物 → rebuild → train ---


def _manage_record_true_run(runs_root, style, iq):
    """manage_run 真落一个 record:true 形状运行目录（不走手写 result.json 捷径）：

    八件套骨架+场景副本由 create_run_workspace 落盘，result.json 由 finalize_run
    落盘——其固定键集不含 style/freq_mhz（C1 断链现场）；execute 回调把 SigMF
    cf32 对写进 recordings/（record_run_streams record=true 的落盘形状）。
    返回 run_dir。
    """
    scenario = {
        "style": style,
        "fs": 1.0e6,
        "freq_hz": 2.4e9,
        "power_dbm": -10.0,
        "duration_s": 0.005,
        "backend": "sim",
        "bands": [[2400.0, 2483.5]],
        "shielded_box": True,
        "dut_scope": "self_built",
    }

    def execute(ctx):
        _write_sigmf_pair(
            Path(ctx["run_dir"]) / "recordings", iq
        )

    record = manage_run(dict(scenario), execute, runs_root=str(runs_root))
    assert record["status"] == "done"
    assert record["result"]["finalized"] is True
    return record["run_dir"]


def test_defect_c1_i4_record_true_run_rebuild_then_train(tmp_path):
    """C1+I4 端到端：record:true 真产物（manage_run 全生命周期，finalize_run 落盘
    的 result.json 无 style/freq_mhz）→ index_dataset('rebuild') → 条目自场景副本
    补全 style 非 None → train_classifier（/api/ai/train 同款底层入口）演练有效
    样本 > 0——「样本不足拒训：有效谱样本 0」的用户断链不再复现。"""
    runs_root = tmp_path / "runs_root"
    _manage_record_true_run(runs_root, "tone", _tone_iq())
    _manage_record_true_run(runs_root, "bandlimited_noise", _noise_iq())
    index_path = str(tmp_path / "index.json")

    rebuilt = index_dataset("rebuild", index_path=index_path, runs_root=str(runs_root))
    assert rebuilt == {"rebuilt": 2, "skipped": 0}
    entries = index_dataset("list", index_path=index_path)["entries"]
    assert len(entries) == 2
    for entry in entries:
        assert entry["style"] in ("tone", "bandlimited_noise")  # 副本补全非 None
        assert entry["freq_mhz"] == 2400.0  # 副本 freq_hz→MHz

    result = train_classifier(
        {"style": ["tone", "bandlimited_noise"]},
        hyperparams={
            "index_path": index_path,
            "runs_root": str(runs_root),
            "nfft": 64,
            "min_samples": 2,
        },
        where="local",
        dry_run=True,
    )
    assert result["n_samples"] == 2  # 用户路径终点：可训（此前恒 0）
    assert result["skipped"] == 0
    assert set(result["labels"]) == {"tone", "bandlimited_noise"}
