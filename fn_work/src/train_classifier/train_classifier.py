"""七分类训练入口（远程派发/显式本地降级/不足拒训）——重写规约与签名意图详见 fn_docs/responsibility.md（B14 顶层/R30；调用方 run_demo/CLI）。

落地口径：

- 取数：query dict 原样透传 index_dataset('query')；空 matched → TrainError
  「样本不足」附 matched 数；query 未知字段引发的 QueryError 包装为 TrainError
  （含原文），query 本身非 dict → ValueError（形状错先拒）；
- 谱特征：逐条目解析 SigMF cf32 数据（path 为目录→最早 .sigmf-meta 配对
  data；*.sigmf-meta→同名 data；其余按数据文件直读）→ make_spectrogram，
  nfft 透传 hyperparams['nfft']（缺省 256，域错上抛 ValueError）；跳段归因
  分列两类（走查 I4 修复）：「style 缺失」（条目无有效样式标签——标签不
  可考，与数据面无关）与「IQ 段长不足窗长或数据不可读」（含脏 IQ）；
  全跳与有效数不足同走 TrainError，消息如实分列计数，不把 style 缺失
  误报成段长/数据问题；
- 校验：有效谱样本 < min_samples（缺省 20）→ TrainError 附数与阈值；
  唯一标签 < 2 类 → TrainError（七分类至少要两类可分）；
- remote：组装 task_package（code_root 缺省本包目录、entrypoint 缺省
  'seven_cls.train'、data_paths 为有效样本数据文件）派发
  dispatch_remote_training（dry_run 透传，dispatched 透传返回）；
  RemoteError → TrainError 包装含原文与「可显式 where='local' 降级」提示；
- local：dummy 训练器（kind='cnn_dummy'）——每类聚合时间平均谱的均值谱，
  产 {'kind','labels','class_mean_spectra','train_meta'}，供 predict_style
  规则判据后续消费（本批只产模型文件）；
- 落盘：hyperparams['out_path']（缺省 fn_work/models/style_classifier.json，
  目录自动建），写失败 → TrainError（IO）。
"""
from __future__ import annotations

import json
import os

import numpy as np

from .dispatch_remote_training import RemoteError, dispatch_remote_training
from src.index_dataset.index_dataset import QueryError, index_dataset
from src.make_spectrogram.make_spectrogram import make_spectrogram

__all__ = ["TrainError", "train_classifier"]

#: STFT 窗长缺省（与 make_spectrogram 一致）；hyperparams['nfft'] 可覆盖。
_DEFAULT_NFFT = 256

#: 有效谱样本下限缺省；hyperparams['min_samples'] 可覆盖。
_DEFAULT_MIN_SAMPLES = 20

#: 本地模型落点缺省（相对 fn_work 运行目录；测试一律显式传 tmp_path 覆盖）。
_DEFAULT_OUT_PATH = os.path.join("fn_work", "models", "style_classifier.json")

#: 远程训练包缺省入口（模块.函数形状；hyperparams['entrypoint'] 可覆盖）。
_DEFAULT_ENTRYPOINT = "seven_cls.train"

#: 合法执行地。
_WHERE = ("remote", "local")

#: nfft 域干跑预检用空段（长度 0 < 任何合法 nfft → 只走参数校验分支）。
_EMPTY_IQ = np.zeros(0, dtype=np.complex128)

#: cf32_le：float32 实部/虚部交错小端。
_CF32 = np.dtype("<c8")


class TrainError(Exception):
    """训练入口失败：样本不足/类别单类/远程不可达/模型 IO（附原因与关键数）。"""


def _resolve_data_file(path: object) -> str | None:
    """条目 path → 单个 cf32 数据文件路径。

    口径与 predict_style 的数据集消费一致：目录 → 其中最早 .sigmf-meta 的同名
    .sigmf-data（无 meta 则最早 .sigmf-data）；*.sigmf-meta → 同名 data；
    其余按数据文件直读。path 非 str/解析不到现存文件 → None（调用方计跳段）。
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


def _skip_reasons_note(skipped: int, skipped_no_style: int) -> str:
    """跳段归因分列注记（走查 I4 修复）：跳段 > 0 时返回「（跳段归因: …）」，
    style 缺失与段长/数据两类各附计数；无跳段返回空串。

    归因口径：条目无有效 style（含非 dict 条目——标签不可考）计 style 缺失；
    其余（数据文件不可解析/不可读/脏 IQ/段长不足窗长）计段长/数据侧。
    """
    if skipped <= 0:
        return ""
    parts: list[str] = []
    if skipped_no_style:
        parts.append(f"style 缺失 {skipped_no_style} 条")
    data_side = skipped - skipped_no_style
    if data_side:
        parts.append(f"IQ 段长不足窗长或数据不可读 {data_side} 条")
    return f"（跳段归因: {'；'.join(parts)}）"


def train_classifier(
    query: dict,
    hyperparams: dict | None = None,
    where: str = "remote",
    dry_run: bool = False,
) -> dict:
    """七分类训练入口（远程派发/显式本地降级/不足拒训）。

    Args:
        query: 数据集检索条件（原样透传 index_dataset('query')，支持
            style/freq_range/date_range/backend/failed/batch_key）。
        hyperparams: 训练超参与落点选项——nfft（缺省 256）、min_samples（缺省
            20）、out_path（缺省 fn_work/models/style_classifier.json）、
            index_path/runs_root（索引落点，缺省用 index_dataset 缺省）、
            code_root/entrypoint（远程包）；其余键原样进远程包 hyperparams。
        where: 'remote'（默认，派发 remote-compute）| 'local'（显式本地降级）。
        dry_run: 透传 dispatch_remote_training——不真派发，返回 dispatched=False。

    Returns:
        {'model_path': str|None（remote 不落本地模型）、'labels': 出现过的类别
        列表、'n_samples': 有效谱样本数、'where': 'remote'|'local'、'train_meta':
        {'n_samples','nfft','per_class'（local 另附整体模型同款）,'dispatch'（remote）}、
        'skipped': 跳段数、'dispatched': bool（remote 派发结果透传；local 恒 False）}。

    Raises:
        ValueError: query/hyperparams 形状错（非 dict）、nfft/min_samples 不可转
            int、where 非法（nfft 域错由 make_spectrogram 上抛同语义）。
        TrainError: 查询零匹配/有效样本不足（附数与阈值）/类别单类/远程不可达
            （含 where='local' 降级提示）/模型落盘 IO 失败/query 条件非法
            （QueryError 包装，含原文）。
    """
    if not isinstance(query, dict):
        raise ValueError(f"query 必须为 dict（检索条件），得到 {type(query).__name__}")
    if hyperparams is None:
        hyperparams = {}
    if not isinstance(hyperparams, dict):
        raise ValueError(
            f"hyperparams 必须为 dict | None（训练超参），得到 {type(hyperparams).__name__}"
        )
    if not isinstance(where, str) or where not in _WHERE:
        raise ValueError(f"where 必须为 {' 或 '.join(_WHERE)}，得到 {where!r}")

    hp = dict(hyperparams)
    nfft = _hyper_int(hp, "nfft", _DEFAULT_NFFT)
    min_samples = _hyper_int(hp, "min_samples", _DEFAULT_MIN_SAMPLES)
    # nfft 域干跑预检（空段只走参数校验分支）：域错在取数前以 ValueError 拒。
    make_spectrogram(_EMPTY_IQ, nfft=nfft)

    # ① 取数：query 原样透传；QueryError（未知字段等）包装 TrainError 含原文。
    index_kwargs = {
        key: hp[key] for key in ("index_path", "runs_root") if key in hp
    }
    try:
        found = index_dataset("query", query=query, **index_kwargs)
    except QueryError as exc:
        raise TrainError(f"数据集检索失败（query 条件非法）: {exc}") from exc
    entries = found.get("entries", [])
    matched = int(found.get("matched", len(entries)))
    if matched == 0:
        raise TrainError(f"样本不足拒训：查询匹配 0 条（query={query!r}）")

    # ② 谱特征：逐条目 make_spectrogram；跳段计数分列归因（style 缺失 vs
    # 段长不足/数据不可读/脏 IQ——走查 I4：style 缺失不得误报为段长问题）。
    samples: list[tuple[str, np.ndarray]] = []  # (style, 时间平均谱向量)
    data_paths: list[str] = []
    skipped = 0
    skipped_no_style = 0
    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1  # 非 dict 条目连 style 都不可考 → 归 style 缺失
            skipped_no_style += 1
            continue
        style = entry.get("style")
        if not isinstance(style, str) or not style:
            skipped += 1
            skipped_no_style += 1
            continue
        data = _resolve_data_file(entry.get("path"))
        if data is None:
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
        spec = np.asarray(spec_res["spec"], dtype=np.float64)
        samples.append((style, spec.mean(axis=1)))  # 时间平均谱 → 均值谱聚合基元
        data_paths.append(data)

    # ③ 样本量与类别覆盖校验（不足拒训，附数与阈值；跳段归因分列计数）。
    if len(samples) < min_samples:
        raise TrainError(
            f"样本不足拒训：有效谱样本 {len(samples)} < min_samples={min_samples}"
            f"（matched {matched} 条，跳段 {skipped} 条）"
            f"{_skip_reasons_note(skipped, skipped_no_style)}"
        )
    labels: list[str] = []
    for style, _prof in samples:
        if style not in labels:
            labels.append(style)
    if len(labels) < 2:
        raise TrainError(
            f"类别覆盖不足拒训：有效样本仅覆盖 {len(labels)} 类 {labels!r}"
            f"（七分类训练至少需 2 类可分；matched {matched} 条，跳段 {skipped} 条）"
            f"{_skip_reasons_note(skipped, skipped_no_style)}"
        )
    per_class = {label: sum(1 for style, _ in samples if style == label) for label in labels}
    train_meta = {"n_samples": len(samples), "nfft": nfft, "per_class": per_class}

    # ④ remote：组装 task_package 派发；RemoteError → TrainError（附降级提示）。
    if where == "remote":
        package_hp = dict(hp)
        package_hp["nfft"] = nfft
        package_hp["min_samples"] = min_samples
        task_package = {
            "code_root": hp.get("code_root", os.path.dirname(os.path.abspath(__file__))),
            "data_paths": list(data_paths),
            "hyperparams": package_hp,
            "entrypoint": hp.get("entrypoint", _DEFAULT_ENTRYPOINT),
        }
        if "runner" in hp:
            task_package["runner"] = hp["runner"]
        try:
            dispatch = dispatch_remote_training(task_package, dry_run=dry_run)
        except RemoteError as exc:
            raise TrainError(
                f"远程训练派发失败: {exc}——可显式 where='local' 降级本地训练"
            ) from exc
        return {
            "model_path": None,  # 模型产物在远端，本批不落本地模型文件
            "labels": labels,
            "n_samples": len(samples),
            "where": "remote",
            "train_meta": {**train_meta, "dispatch": dispatch},
            "skipped": skipped,
            "dispatched": bool(dispatch.get("dispatched", False)),
        }

    # ⑤ local：dummy 训练器——每类均值谱（时间平均谱再按类平均）。
    # B27 对抗中1 转 B28 随批整改②：local 分支消费 dry_run——演练口径不落
    # 模型文件（此前仅 remote 分支消费，网页 local+dry_run 复选框失联），返回
    # 标注 dry_run（model_path=None，演练不产模型）。
    if dry_run:
        return {
            "model_path": None,  # 演练口径：不落模型文件
            "labels": labels,
            "n_samples": len(samples),
            "where": "local",
            "dry_run": True,
            "train_meta": {
                **train_meta,
                "dry_run_note": (
                    "local+dry_run 演练：样本校验/谱特征全流程走通，"
                    "模型不落盘（dry_run 消费——B28 整改）"
                ),
            },
            "skipped": skipped,
            "dispatched": False,
        }
    buckets: dict[str, list[np.ndarray]] = {label: [] for label in labels}
    for style, prof in samples:
        buckets[style].append(prof)
    class_mean_spectra = {
        label: [float(v) for v in np.mean(np.stack(vecs), axis=0)]
        for label, vecs in buckets.items()
    }
    model = {
        "kind": "cnn_dummy",
        "labels": labels,
        "class_mean_spectra": class_mean_spectra,
        "train_meta": dict(train_meta),
    }

    # ⑥ 模型落盘（目录自动建；写失败 → TrainError IO）。
    out_path = hp.get("out_path", _DEFAULT_OUT_PATH)
    if not isinstance(out_path, str) or not out_path:
        raise ValueError(f"hyperparams['out_path'] 必须为非空 str，得到 {out_path!r}")
    try:
        parent = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(parent, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(model, fh, ensure_ascii=False, indent=2, allow_nan=False)
    except (OSError, ValueError, TypeError) as exc:
        raise TrainError(
            f"模型落盘失败: {out_path}: {type(exc).__name__}: {exc}"
        ) from exc

    return {
        "model_path": out_path,
        "labels": labels,
        "n_samples": len(samples),
        "where": "local",
        "train_meta": dict(train_meta),
        "skipped": skipped,
        "dispatched": False,
    }
