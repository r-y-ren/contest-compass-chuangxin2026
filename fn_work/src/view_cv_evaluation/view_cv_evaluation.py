"""评测可视化：grouped_cv_evaluate 触发+混淆矩阵表格化+Macro-F1+泄漏检测警告如实回显——重写规约与签名意图详见 fn_docs/responsibility.md（R66 view_cv_evaluation L0；调用方 mount_console_extensions）。

落地口径（R66）：

- 取数+特征化：``query``（数据集筛选，原样透传 index_dataset('query')——支持
  style/freq_range/date_range/backend/failed/batch_key；另收两个传输键
  ``index_path``/``runs_root``（索引落点，取数前剥离不进检索条件）与评测
  参数键 ``nfft``/``k``（缺省 256/5）及 ``protocol``（B48/I-2 端点透传通道：
  覆盖 protocol 参数缺省——POST body 的 query dict 既有通道直进，端点零改动；
  取数前剥离不进检索条件））→ 逐条目 SigMF cf32 →
  make_spectrogram 时间平均谱向量 → samples ``{'label': style, 'features':
  向量, 'batch_key': run_id}``（与 run_rff_pipeline 的谱特征口径一致——
  每 run 自成一组，分组 CV 防段级泄漏的组键）；
- 评测：grouped_cv_evaluate（R31）→ 混淆矩阵（行=真值/列=预测）/Macro-F1/
  per_fold/effective_k/泄漏三旗标+eval_protocol 口径标注原样透传；**泄漏自检与
  折构造饥饿的 RuntimeWarning 文案捕获入 ``warnings`` 列表如实回显**（不吞不
  粉饰）；评测口径（R93）：默认=对齐模板路（注入 make_predict_style_callbacks
  部署同源回调——评测的=部署的）；可选 protocol='intrinsic_dummy' 走内置
  dummy 对照；
- ``model_path``（模型标识）：结果页回显+``model_exists`` 在位标注（分组 CV
  逐折自训自评，不消费模型文件本体——标识用于溯源对照）；
- 分组信息缺失（单批次键/每折训练集空）、检索条件非法、样本不足/标签少于
  2 类等 R31 拒绝 → ``EvalError``（含原文上屏——沿用 R31 口径）。
"""
import warnings

import numpy as np

from src.grouped_cv_evaluate.grouped_cv_evaluate import grouped_cv_evaluate
from src.grouped_cv_evaluate.make_predict_style_callbacks import (
    make_predict_style_callbacks,
)
from src.index_dataset.index_dataset import (
    IndexFormatError,
    IndexWriteError,
    QueryError,
    index_dataset,
)
from src.make_spectrogram.make_spectrogram import make_spectrogram

__all__ = ["EvalError", "view_cv_evaluation"]

#: 谱图窗长缺省（query['nfft'] 可覆盖——与 train_classifier 同域）。
_DEFAULT_NFFT = 256

#: 分组 CV 目标折数缺省（query['k'] 可覆盖——make_group_splits 域校验）。
_DEFAULT_K = 5

#: query 的传输/评测参数键（取数前剥离，不进 index_dataset 检索条件）；
#: protocol（B48/I-2）：评测口径传输键——覆盖 protocol 参数缺省（端点透传通道）。
_QUERY_META_KEYS = ("index_path", "runs_root", "nfft", "k", "protocol")

#: 评测口径合法取值（R93）：aligned_template=注入部署同源对齐回调（缺省）；
#: intrinsic_dummy=不注入回调走内置 dummy（对照口径）。
_EVAL_PROTOCOLS = ("aligned_template", "intrinsic_dummy")

#: cf32_le：float32 实部/虚部交错小端。
_CF32 = np.dtype("<c8")

#: nfft 域干跑预检用空段（长度 0 < 任何合法 nfft → 只走参数校验分支）。
_EMPTY_IQ = np.zeros(0, dtype=np.complex128)


class EvalError(RuntimeError):
    """评测入口失败：检索条件非法/查询零匹配/样本不足/分组信息缺失（R31 拒绝原文透传）。"""


def _hyper_int(raw: object, key: str, default: int) -> int:
    """评测参数整型提取：缺省用 default；不可转 int → ValueError（形状错）。"""
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"query[{key!r}] 必须为可转 int 的数值，得到 {raw!r}") from None


def _resolve_data_file(path: object) -> "str | None":
    """条目 path → 单个 cf32 数据文件路径（与 train_classifier 同口径：
    目录→最早 .sigmf-meta 的同名 data；*.sigmf-meta→同名 data；其余直读；
    解析不到现存文件 → None——调用方计跳段）。"""
    import os

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


def _read_cf32(path: str) -> "np.ndarray | None":
    """cf32 数据文件 → complex 一维数组；读失败/空文件 → None（计跳段不抛）。"""
    try:
        iq = np.fromfile(path, dtype=_CF32)
    except OSError:
        return None
    return iq if iq.size else None


def view_cv_evaluation(
    query: dict, model_path: str, protocol: str = "aligned_template"
) -> dict:
    """评测可视化：grouped_cv_evaluate 触发+混淆矩阵表格化+Macro-F1+泄漏检测警告如实回显（详见 fn_docs/responsibility.md 功能块）。

    评测口径（R93）：默认=对齐模板路（注入 make_predict_style_callbacks 部署
    同源回调——评测的=部署的）；可选 protocol='intrinsic_dummy' 走内置 dummy
    对照（不注入回调）。

    输入:
        query: 数据集筛选 dict——检索条件原样透传 index_dataset('query')
            （style/freq_range/date_range/backend/failed/batch_key）；另收
            传输键 index_path/runs_root（索引落点，缺省 index_dataset 缺省）
            与评测参数键 nfft（缺省 256）/k（缺省 5）/protocol（评测口径
            传输键——存在时覆盖 protocol 参数缺省，合法取值同 protocol 参数），
            取数前剥离不进检索条件。
        model_path: 模型标识 str（非空）——结果页回显溯源；分组 CV 逐折自训
            自评不消费模型文件本体，仅在位性如实标注 model_exists。
        protocol: 评测口径 str——取值 {'aligned_template'（缺省：注入部署
            同源对齐回调）, 'intrinsic_dummy'（内置 dummy 对照——不注入回调，
            eval_protocol 缺省）}；其他取值 ValueError（含合法取值提示）。

    输出:
        {'ok': True, 'model_path': 回显, 'model_exists': bool, 'query':
        检索条件回显（剥离传输键后）, 'matched': 索引命中数, 'skipped':
        跳段数, 'n_samples': 有效样本数, 'confusion': {'labels': [...],
        'matrix': [[...]]}（行=真值/列=预测）, 'macro_f1': float, 'per_fold':
        [...], 'effective_k': int, 'leak_suspect': bool,
        'fold_class_starvation': bool, 'below_target': bool, 'eval_protocol':
        str（评测口径标注——透传 grouped_cv_evaluate 报告值）, 'warnings':
        [泄漏自检/折构造饥饿警告文案…——RuntimeWarning 捕获如实回显]}。

    错误:
        ValueError: query 非 dict / model_path 非非空 str / protocol 取值
            非法（合法取值 {'aligned_template', 'intrinsic_dummy'}）/ nfft、k
            不可转 int（nfft 域错由 make_spectrogram 上抛同语义）。
        EvalError: 检索条件非法（QueryError 含原文）/索引损坏不可自愈/
            查询零匹配/样本不足或标签少于 2 类/分组信息缺失（单批次键、
            每折训练集空——grouped_cv_evaluate 的 R31 拒绝含原文上屏）。
    """
    import os

    if not isinstance(query, dict):
        raise ValueError(
            f"query 必须为 dict（数据集筛选），实际 {type(query).__name__}: {query!r}"
        )
    if not isinstance(model_path, str) or not model_path.strip():
        raise ValueError(
            f"model_path 必须为非空 str（模型标识），实际 {model_path!r}"
        )
    model_path = model_path.strip()
    # protocol 传输键（B48/I-2 端点透传通道）：query['protocol'] 覆盖参数缺省——
    # POST body 的 query dict 经端点既有通道直进（端点零改动）；缺省/显式 null
    # 不覆盖；非法值由下方取值校验 ValueError 自然拒（端点 ValueError→400 既有路径）。
    raw_protocol = query.get("protocol")
    if raw_protocol is not None:
        protocol = raw_protocol
    if protocol not in _EVAL_PROTOCOLS:
        raise ValueError(
            f"protocol 必须为 {'/'.join(_EVAL_PROTOCOLS)} 之一（评测口径），"
            f"实际: {protocol!r}"
        )

    conditions = {k: v for k, v in query.items() if k not in _QUERY_META_KEYS}
    index_kwargs = {
        key: query[key] for key in ("index_path", "runs_root") if key in query
    }
    nfft = _hyper_int(query.get("nfft"), "nfft", _DEFAULT_NFFT)
    k = _hyper_int(query.get("k"), "k", _DEFAULT_K)
    make_spectrogram(_EMPTY_IQ, nfft=nfft)  # nfft 域干跑预检（先于取数）

    # ① 取数：检索条件透传；QueryError/索引损坏 → EvalError（含原文上屏）。
    try:
        found = index_dataset("query", query=conditions or None, **index_kwargs)
    except QueryError as exc:
        raise EvalError(f"数据集检索失败（query 条件非法）: {exc}") from exc
    except (IndexFormatError, IndexWriteError) as exc:
        raise EvalError(f"数据集索引不可用: {exc}") from exc
    entries = found.get("entries", [])
    matched = int(found.get("matched", len(entries)))
    if matched == 0:
        raise EvalError(
            f"评测数据不足：查询零匹配（query={conditions!r}）——先重建索引或放宽筛选"
        )

    # ② 谱特征：逐条目时间平均谱向量；batch_key=run_id（分组 CV 组键）。
    samples: list = []
    skipped = 0
    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        style = entry.get("style")
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
        except ValueError:  # 脏 IQ 等条目级数据问题：计跳段不短路
            skipped += 1
            continue
        if spec_res["skipped"]:
            skipped += 1
            continue
        profile = np.asarray(spec_res["spec"], dtype=np.float64).mean(axis=1)
        run_id = entry.get("run_id")
        samples.append(
            {
                "label": style,
                "features": [float(v) for v in profile],
                "batch_key": run_id if isinstance(run_id, str) else None,
            }
        )

    # ③ 评测：grouped_cv_evaluate（R31）——泄漏/饥饿 RuntimeWarning 捕获回显。
    # 口径（R93）：默认注入部署同源对齐回调（评测的=部署的）；intrinsic_dummy
    # → 现状缺省调用（不注入回调，eval_protocol 缺省）。
    if protocol == "aligned_template":
        train_fn, predict_fn = make_predict_style_callbacks()
        eval_kwargs = {
            "train_fn": train_fn,
            "predict_fn": predict_fn,
            "eval_protocol": "aligned_template",
        }
    else:
        eval_kwargs = {}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            outcome = grouped_cv_evaluate(samples, k=k, **eval_kwargs)
        except ValueError as exc:  # 分组缺失/样本形状/标签<2 类——R31 拒绝上屏
            raise EvalError(f"分组评测不可行: {exc}") from exc
    warning_texts = [
        str(item.message) for item in caught if issubclass(item.category, RuntimeWarning)
    ]

    return {
        "ok": True,
        "model_path": model_path,
        "model_exists": os.path.isfile(model_path),
        "query": conditions,
        "matched": matched,
        "skipped": skipped,
        "n_samples": outcome["n_samples"],
        "confusion": outcome["confusion"],
        "macro_f1": outcome["macro_f1"],
        "per_fold": outcome["per_fold"],
        "effective_k": outcome["effective_k"],
        "leak_suspect": outcome["leak_suspect"],
        "fold_class_starvation": outcome["fold_class_starvation"],
        "below_target": outcome["below_target"],
        "eval_protocol": outcome["eval_protocol"],
        "warnings": warning_texts,
    }
