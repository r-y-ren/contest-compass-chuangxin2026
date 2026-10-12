"""RFF 指纹管道：数据/训练/评测/部署模拟——重写规约与签名意图详见 fn_docs/responsibility.md（R55 顶层；调用方 CLI 入口/二期交付演示）。

落地口径（复用已实现件，B14 train 同数据口径）：

- 取数：``dataset_config['query']``（检索条件 dict）原样透传
  ``index_dataset('query')``——``index_path``/``runs_root`` 取
  ``dataset_config`` 同名键（缺省用 index_dataset 缺省）；空 matched →
  TrainError；QueryError（条件非法）包装为 TrainError（含原文）；
- 特征：逐条目解析 SigMF cf32 数据（path 为目录→最早 .sigmf-meta 配对
  data；*.sigmf-meta→同名 data；其余按数据文件直读——与 train_classifier
  同口径）→ ``make_spectrogram``（nfft 透传 ``hyperparams['nfft']`` 缺省
  256）→ 时间平均谱为特征向量；段长不足/数据不可读/脏 IQ 计入跳段；
- 轻量模型：最近质心分类器（类均值，numpy）——各类特征均值即质心，
  推理取欧氏距离最近类；模型元数据附参数量（质心数×维度）与类别清单；
- 评测：``grouped_cv_evaluate``（k 透传 ``hyperparams['k']`` 缺省 5）——
  samples 构造 ``batch_key=run_id``（每个 run 自成一组，防段级泄漏）；
- 部署模拟：本地推理端点（``'endpoint': 'local-inference'``）+模型元数据
  dict（蒸馏口径：kind/labels/参数量入报告）；
- 数据不足拒训（TrainError 自定义，附数与阈值）：查询零匹配/有效样本
  < ``min_samples``（缺省 20）/类别覆盖 <2 类；
- 形状错 ValueError：dataset_config/hyperparams 非 dict（hyperparams 容
  None）/缺 'query' 或 query 非 dict/nfft、min_samples、k 不可转 int。

返回：``{'model': {'kind': 'centroid', ...}, 'evaluation': grouped_cv_evaluate
结果, 'endpoint': 'local-inference', 'deployment': 部署模拟报告,
'n_samples': 有效样本数, 'skipped': 跳段数}``。
"""
from __future__ import annotations

import os

import numpy as np

from src.grouped_cv_evaluate.grouped_cv_evaluate import grouped_cv_evaluate
from src.index_dataset.index_dataset import QueryError, index_dataset
from src.make_spectrogram.make_spectrogram import make_spectrogram

__all__ = ["TrainError", "run_rff_pipeline"]

#: STFT 窗长缺省（与 make_spectrogram/B14 train_classifier 一致）。
_DEFAULT_NFFT = 256
#: 有效样本下限缺省（不足拒训阈值；hyperparams['min_samples'] 可覆盖）。
_DEFAULT_MIN_SAMPLES = 20
#: 分组 CV 目标折数缺省（hyperparams['k'] 可覆盖，须 ≥2）。
_DEFAULT_K = 5
#: 部署模拟端点（本地推理）。
_ENDPOINT = "local-inference"
#: cf32_le：float32 实部/虚部交错小端。
_CF32 = np.dtype("<c8")
#: nfft 域干跑预检用空段（长度 0 < 任何合法 nfft → 只走参数校验分支）。
_EMPTY_IQ = np.zeros(0, dtype=np.complex128)


class TrainError(Exception):
    """RFF 管道训练失败：查询零匹配/有效样本不足/类别覆盖不足（附原因与关键数）。"""


def _resolve_data_file(path: object) -> str | None:
    """条目 path → 单个 cf32 数据文件路径（B14 train_classifier 同口径）。

    目录 → 其中最早 .sigmf-meta 的同名 .sigmf-data（无 meta 则最早
    .sigmf-data）；*.sigmf-meta → 同名 data；其余按数据文件直读。
    path 非 str/解析不到现存文件 → None（调用方计跳段）。
    """
    if not isinstance(path, str) or not path:
        return None
    if os.path.isdir(path):
        names = sorted(os.listdir(path))
        for name in names:
            if name.endswith(".sigmf-meta"):
                data = os.path.join(path, name[: -len(".sigmf-meta")] + ".sigmf-data")
                if os.path.isfile(data):
                    return data
        for name in names:
            if name.endswith(".sigmf-data") and os.path.isfile(os.path.join(path, name)):
                return os.path.join(path, name)
        return None
    if path.endswith(".sigmf-meta"):
        data = path[: -len(".sigmf-meta")] + ".sigmf-data"
        return data if os.path.isfile(data) else None
    return path if os.path.isfile(path) else None


def _read_cf32(path: str) -> np.ndarray | None:
    """cf32 数据文件 → complex 一维数组；读失败/空文件 → None（计跳段不抛）。"""
    try:
        iq = np.fromfile(path, dtype=_CF32)
    except OSError:
        return None
    return iq if iq.size else None


def _hyper_int(hp: dict, key: str, default: int) -> int:
    """hyperparams 整型超参提取：缺省用 default；不可转 int → ValueError（形状错）。"""
    raw = hp.get(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"hyperparams[{key!r}] 必须为可转 int 的数值，得到 {raw!r}") from None


def run_rff_pipeline(dataset_config: dict, hyperparams: dict) -> dict:
    """RFF 指纹全管道：取数→谱特征→最近质心训练→分组 CV 评测→部署模拟。

    Args:
        dataset_config: ``{'query': 检索条件 dict（必填，透传
            index_dataset('query')）, 'index_path'/'runs_root': 可选索引落点}``。
        hyperparams: ``nfft``（缺省 256）、``min_samples``（缺省 20）、
            ``k``（缺省 5，≥2）；None 视同 {}。

    Returns:
        见模块 docstring 返回口径（evaluation 为 grouped_cv_evaluate 完整结果）。

    Raises:
        ValueError: dataset_config/hyperparams/query 形状错、超参不可转 int、
            k<2、nfft 域错（make_spectrogram 上抛同语义）。
        TrainError: 查询零匹配/有效样本不足/类别覆盖 <2 类。
    """
    if not isinstance(dataset_config, dict):
        raise ValueError(
            f"dataset_config 必须为 dict（数据集配置），实际: {type(dataset_config).__name__}"
        )
    if hyperparams is None:
        hyperparams = {}
    if not isinstance(hyperparams, dict):
        raise ValueError(
            f"hyperparams 必须为 dict | None（训练超参），实际: {type(hyperparams).__name__}"
        )
    query = dataset_config.get("query")
    if not isinstance(query, dict):
        raise ValueError(
            "dataset_config['query'] 必须为 dict（检索条件，透传 index_dataset('query')），"
            f"实际: {type(query).__name__}"
        )

    hp = dict(hyperparams)
    nfft = _hyper_int(hp, "nfft", _DEFAULT_NFFT)
    min_samples = _hyper_int(hp, "min_samples", _DEFAULT_MIN_SAMPLES)
    k = _hyper_int(hp, "k", _DEFAULT_K)
    if min_samples < 1:
        raise ValueError(f"hyperparams['min_samples'] 必须 ≥1，得到 {min_samples!r}")
    if k < 2:
        raise ValueError(f"hyperparams['k'] 必须 ≥2（分组折数），得到 {k!r}")
    make_spectrogram(_EMPTY_IQ, nfft=nfft)  # nfft 域干跑预检（空段只走参数校验分支）

    # ① 取数：query 原样透传；QueryError（未知字段等）包装 TrainError 含原文。
    index_kwargs = {
        key: dataset_config[key] for key in ("index_path", "runs_root") if key in dataset_config
    }
    try:
        found = index_dataset("query", query=query, **index_kwargs)
    except QueryError as exc:
        raise TrainError(f"数据集检索失败（query 条件非法）: {exc}") from exc
    entries = found.get("entries", [])
    matched = int(found.get("matched", len(entries)))
    if matched == 0:
        raise TrainError(f"数据不足拒训：查询匹配 0 条（query={query!r}）")

    # ② 谱特征：逐条目 SigMF cf32 → make_spectrogram → 时间平均谱向量；
    #    batch_key=run_id（每个 run 自成一组——分组 CV 防段级泄漏的组键）。
    samples: list = []
    skipped = 0
    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        style = entry.get("style")
        run_id = entry.get("run_id")
        data = _resolve_data_file(entry.get("path"))
        if data is None or not isinstance(style, str) or not style:
            skipped += 1
            continue
        iq = _read_cf32(data)
        if iq is None:
            skipped += 1
            continue
        try:
            spec_res = make_spectrogram(iq, nfft=nfft)
        except ValueError:  # 脏 IQ（NaN/inf）等条目级数据问题：计跳段不短路
            skipped += 1
            continue
        if spec_res["skipped"]:
            skipped += 1
            continue
        profile = np.asarray(spec_res["spec"], dtype=np.float64).mean(axis=1)  # 时间平均谱
        samples.append(
            {
                "label": style,
                "features": [float(v) for v in profile],
                "batch_key": run_id if isinstance(run_id, str) else None,
            }
        )

    # ③ 数据量与类别覆盖校验（不足拒训，附数与阈值）。
    if len(samples) < min_samples:
        hint = (
            "（全部条目被跳过：IQ 段长不足窗长或数据不可读）"
            if not samples and skipped
            else ""
        )
        raise TrainError(
            f"数据不足拒训：有效样本 {len(samples)} < min_samples={min_samples}"
            f"（matched {matched} 条，跳段 {skipped} 条）{hint}"
        )
    labels = sorted({sample["label"] for sample in samples})
    if len(labels) < 2:
        raise TrainError(
            f"数据不足拒训：类别覆盖仅 {len(labels)} 类 {labels!r}"
            f"（RFF 分类至少需 2 类可分；matched {matched} 条，跳段 {skipped} 条）"
        )

    # ④ 评测：grouped_cv_evaluate（batch_key=run_id 分组，防段级泄漏）。
    evaluation = grouped_cv_evaluate(samples, k=k)

    # ⑤ 轻量模型：最近质心分类器（类均值，numpy）。
    buckets: dict[str, list[list[float]]] = {}
    for sample in samples:
        buckets.setdefault(sample["label"], []).append(sample["features"])
    centroids = {
        label: [float(v) for v in np.mean(np.stack(vecs), axis=0)]
        for label, vecs in buckets.items()
    }
    n_features = len(next(iter(centroids.values())))
    per_class = {label: len(vecs) for label, vecs in buckets.items()}
    model = {
        "kind": "centroid",
        "labels": labels,
        "centroids": centroids,
        "train_meta": {
            "n_samples": len(samples),
            "nfft": nfft,
            "n_features": n_features,
            "per_class": per_class,
            "skipped": skipped,
        },
    }

    # ⑥ 部署模拟：本地推理端点+模型元数据（蒸馏口径：参数量入报告）。
    deployment = {
        "endpoint": _ENDPOINT,
        "deployed": True,
        "model_meta": {
            "kind": "centroid",
            "labels": labels,
            "n_features": n_features,
            "n_centroids": len(centroids),
            "n_params": len(centroids) * n_features,  # 质心参数量（类数×维度）
            "n_train_samples": len(samples),
        },
    }

    return {
        "model": model,
        "evaluation": evaluation,
        "endpoint": _ENDPOINT,
        "deployment": deployment,
        "n_samples": len(samples),
        "skipped": skipped,
    }
