"""分组 CV 评测：批次分组防泄漏+混淆矩阵+Macro-F1——重写规约与签名意图详见 fn_docs/responsibility.md。

R31 评测协议（简化签名：本函数收样本数据、不查库——调用方先取数+特征化）：
    samples: list[{'label': str, 'features': 数值向量(list/tuple)|特征 dict, 'batch_key': str|可缺}]
    ——与 train_classifier 的谱特征口径一致（谱向量或特征 dict）；
    ——防泄漏的分组键由数据自带：'batch_key' 缺失归 '_none' 桶（make_group_splits 归一）。

流程：
    ① make_group_splits(batch_key 列表, k) 组粒度分折——同批次绝不跨折（防段级泄漏）；
    ② 逐折 train_fn(train_samples)→model、predict_fn(model, test_sample)→label
       （缺省内置 dummy：类均值最近邻，numpy 实现）；
    ③ 汇总混淆矩阵（labels=真值∪预测标签并集排序）+macro_f1（每类 F1 平均——
       零除类 F1=0 计入）+per_fold {'fold','n_train','n_test','accuracy'}；
    ④ 泄漏自检（自证机制）：固定用内置 dummy 口径，把同一数据在「分组划分」与
       「随机逐样本划分（random.Random(0) 洒点）」下对照——若随机口径 macro_f1 比分组
       口径高出 >0.15 且各折训练集类别覆盖≥2→'leak_suspect': True+警告（段级泄漏会让
       随机口径虚高）；**类饥饿排除**（B14 中#2）：任一折训练集类别覆盖<2 类（少数类
       批次全被分进同一 test 折）时，随机/分组差大属折构造饥饿非泄漏——改报
       'fold_class_starvation': True+饥饿警告文案（区别于泄漏）。对照实验不调用传入的
       自定义 train_fn/predict_fn（不产生隐藏重复调用副作用）；
    ⑤ 内部目标 0.85：macro_f1 < 0.85→'below_target': True 如实记录（不粉饰）。

输入:
    samples: list[dict] —— 如上结构；
    k: int —— 目标折数，透传 make_group_splits 校验（>=2 的 int）；
    train_fn / predict_fn —— 自定义训练/推理回调（须成对提供）；缺省走内置 dummy。

输出:
    dict: {'confusion': {'labels': [...], 'matrix': [[...]]}, 'macro_f1': float,
           'per_fold': [...], 'effective_k': int, 'leak_suspect': bool,
           'fold_class_starvation': bool, 'below_target': bool, 'n_samples': int}

错误:
    ValueError —— samples 非 list/为空/元素非 dict/缺 'label' 或 'features'/label 非 str/
    features 非数值向量或特征 dict（含非数值元素/空/维度不一致）/标签少于 2 类/
    全部样本同属一个批次键（每折训练集为空，分组 CV 不可行）/train_fn 与 predict_fn
    只提供其一；k 或 batch_key 非法由 make_group_splits 透传抛出。
"""
from __future__ import annotations

import random
import warnings
from numbers import Real

import numpy as np

from .make_group_splits import make_group_splits

_INTERNAL_TARGET = 0.85
_LEAK_MARGIN = 0.15


def _parse_features(raw: object, where: str) -> list[float]:
    """features → 数值向量：list/tuple 原样；特征 dict 按键排序取值（键序无关）。"""
    if isinstance(raw, dict):
        if not raw:
            raise ValueError(f"{where}: features 特征 dict 不能为空")
        values = [raw[key] for key in sorted(raw, key=str)]
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        raise ValueError(
            f"{where}: features 必须为数值向量(list/tuple)或特征 dict，"
            f"实际: {type(raw).__name__}"
        )
    if not values:
        raise ValueError(f"{where}: features 向量不能为空")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{where}: features 含非数值元素: {value!r}")
    return [float(value) for value in values]


def _dummy_train(train_samples: list) -> dict:
    """内置 dummy 训练：各类特征均值（numpy）。"""
    vectors: dict[str, list] = {}
    for sample in train_samples:
        vectors.setdefault(sample["label"], []).append(
            _parse_features(sample["features"], "train 样本")
        )
    labels = sorted(vectors)
    means = np.array([np.mean(vectors[lab], axis=0) for lab in labels], dtype=float)
    return {"labels": labels, "means": means}


def _dummy_predict(model: dict, test_sample: dict) -> str:
    """内置 dummy 推理：最近类均值（欧氏距离；平手取排序最小类——确定性）。"""
    vector = np.array(
        _parse_features(test_sample["features"], "test 样本"), dtype=float
    )
    distances = np.linalg.norm(model["means"] - vector, axis=1)
    return model["labels"][int(np.argmin(distances))]


def _run_folds(
    samples: list,
    folds_idx: list,
    train_fn,
    predict_fn,
) -> tuple:
    """逐折跑管线：返回 (全部 (真值, 预测) 对, per_fold 统计列表)。"""
    pairs: list = []
    per_fold: list = []
    for fold_no, (train_idx, test_idx) in enumerate(folds_idx):
        model = train_fn([samples[i] for i in train_idx])
        fold_pairs = [
            (samples[i]["label"], predict_fn(model, samples[i])) for i in test_idx
        ]
        correct = sum(1 for truth, pred in fold_pairs if truth == pred)
        per_fold.append(
            {
                "fold": fold_no,
                "n_train": len(train_idx),
                "n_test": len(test_idx),
                "accuracy": correct / len(test_idx),
            }
        )
        pairs.extend(fold_pairs)
    return pairs, per_fold


def _confusion_matrix(pairs: list, labels: list) -> list:
    """混淆矩阵：行=真值，列=预测（labels 已含 pairs 中出现的全部标签）。"""
    index = {label: i for i, label in enumerate(labels)}
    matrix = [[0] * len(labels) for _ in labels]
    for truth, pred in pairs:
        matrix[index[truth]][index[pred]] += 1
    return matrix


def _macro_f1(matrix: list) -> float:
    """macro F1：每类 F1（零除记 0）的平均——零除类计入分母。"""
    n = len(matrix)
    f1s = []
    for i in range(n):
        tp = matrix[i][i]
        fp = sum(matrix[row][i] for row in range(n)) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp > 0 else 0.0
        recall = tp / (tp + fn) if tp + fn > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall > 0
            else 0.0
        )
        f1s.append(f1)
    return sum(f1s) / len(f1s) if f1s else 0.0


def grouped_cv_evaluate(samples: list, k: int = 5, train_fn=None, predict_fn=None) -> dict:
    """分组交叉验证评测：批次分组防泄漏+混淆矩阵+Macro-F1+泄漏自检。

    输入/输出/错误契约详见模块 docstring（R31）。
    """
    if not isinstance(samples, list):
        raise ValueError(f"samples 必须为 list，实际: {type(samples).__name__}")
    if not samples:
        raise ValueError("samples 不能为空列表")
    if (train_fn is None) != (predict_fn is None):
        raise ValueError(
            "train_fn 与 predict_fn 必须成对提供（要么都缺省走内置 dummy，要么都自定义）"
        )

    vectors: list[list[float]] = []
    for i, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ValueError(
                f"samples[{i}] 必须为 dict，实际: {type(sample).__name__}"
            )
        if "label" not in sample:
            raise ValueError(f"samples[{i}] 缺 'label' 字段")
        if not isinstance(sample["label"], str):
            raise ValueError(
                f"samples[{i}].label 必须为 str，实际: {type(sample['label']).__name__}"
            )
        if "features" not in sample:
            raise ValueError(f"samples[{i}] 缺 'features' 字段")
        vectors.append(_parse_features(sample["features"], f"samples[{i}]"))

    if len({sample["label"] for sample in samples}) < 2:
        raise ValueError("samples 标签少于 2 类，无法做分类评测")
    dim = len(vectors[0])
    for i, vec in enumerate(vectors):
        if len(vec) != dim:
            raise ValueError(
                f"samples[{i}].features 维度 {len(vec)} 与首个样本维度 {dim} 不一致"
            )

    # ① 组粒度分折：batch_key 缺失→None→'_none' 桶；k/键合法性由 make_group_splits 校验。
    batch_keys = [sample.get("batch_key") for sample in samples]
    splits = make_group_splits(batch_keys, k=k)
    folds_idx = [(fold["train_idx"], fold["test_idx"]) for fold in splits["folds"]]
    for fold_no, (train_idx, _) in enumerate(folds_idx):
        if not train_idx:
            raise ValueError(
                f"折 {fold_no} 训练集为空（全部样本同属一个批次键）——分组交叉验证不可行"
            )

    # ② 逐折训练/推理：缺省内置 dummy（类均值最近邻）。
    use_default = train_fn is None and predict_fn is None
    resolved_train = train_fn if train_fn is not None else _dummy_train
    resolved_predict = predict_fn if predict_fn is not None else _dummy_predict

    # ③ 汇总混淆矩阵+macro F1+per_fold。
    pairs, per_fold = _run_folds(samples, folds_idx, resolved_train, resolved_predict)
    labels = sorted({truth for truth, _ in pairs} | {pred for _, pred in pairs})
    matrix = _confusion_matrix(pairs, labels)
    macro_f1 = _macro_f1(matrix)

    # ④ 泄漏自检：内置 dummy 口径下「分组划分 vs 随机逐样本划分（Random(0) 洒点）」对照。
    if use_default:
        grouped_f1 = macro_f1  # 主口径即 dummy，无需重跑
    else:
        dummy_pairs, _ = _run_folds(samples, folds_idx, _dummy_train, _dummy_predict)
        grouped_f1 = _macro_f1(_confusion_matrix(dummy_pairs, labels))
    n = len(samples)
    k_eff = splits["effective_k"]
    order = list(range(n))
    random.Random(0).shuffle(order)
    random_folds_idx = []
    for fold_no in range(k_eff):
        test_idx = sorted(order[fold_no::k_eff])
        test_set = set(test_idx)
        train_idx = sorted(i for i in range(n) if i not in test_set)
        random_folds_idx.append((train_idx, test_idx))
    random_pairs, _ = _run_folds(samples, random_folds_idx, _dummy_train, _dummy_predict)
    random_f1 = _macro_f1(_confusion_matrix(random_pairs, labels))

    # 类饥饿排除（B14 中#2）：分组口径下任一折训练集类别覆盖<2 类（少数类批次全被
    # 分进同一 test 折）时，随机/分组差大属折构造饥饿非泄漏——leak_suspect 追加
    # 「且各折训练集类别覆盖≥2」，饥饿场景改报 fold_class_starvation+独立警告文案。
    fold_class_starvation = any(
        len({samples[i]["label"] for i in train_idx}) < 2
        for train_idx, _ in folds_idx
    )
    gap = random_f1 - grouped_f1
    leak_suspect = gap > _LEAK_MARGIN and not fold_class_starvation
    if leak_suspect:
        warnings.warn(
            f"分组 CV 泄漏自检：随机逐样本划分 macro_f1={random_f1:.3f} 比分组划分 "
            f"{grouped_f1:.3f} 高出 {gap:.3f}(>0.15)——疑似批次级"
            "段泄漏让随机口径虚高，评测以分组口径为准",
            RuntimeWarning,
            stacklevel=2,
        )
    elif fold_class_starvation:
        warnings.warn(
            f"分组 CV 折构造饥饿：存在训练集类别覆盖<2 类的折（少数类批次全被分进同一 "
            f"test 折）——随机逐样本划分 macro_f1={random_f1:.3f} 与分组划分 "
            f"{grouped_f1:.3f} 的差距属折构造饥饿而非泄漏，建议增加少数类批次数或降低 k；"
            "评测以分组口径为准",
            RuntimeWarning,
            stacklevel=2,
        )

    # ⑤ 内部目标 0.85 如实记录。
    return {
        "confusion": {"labels": labels, "matrix": matrix},
        "macro_f1": macro_f1,
        "per_fold": per_fold,
        "effective_k": splits["effective_k"],
        "leak_suspect": leak_suspect,
        "fold_class_starvation": fold_class_starvation,
        "below_target": macro_f1 < _INTERNAL_TARGET,
        "n_samples": n,
    }
