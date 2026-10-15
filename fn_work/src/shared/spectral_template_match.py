"""谱模板匹配分类（共享）——重写规约与签名意图详见 fn_docs/responsibility.md 共享函数节。

〔新上提·演进轮④ 2026-10-15（R92/R93）：predict_style 模板路（_template_classify）
与 grouped_cv_evaluate 对齐回调（make_predict_style_callbacks 的 predict_fn）的
**同一实现**——"评测的=部署的"由本函数级同源承载。〕

置信度口径：softmax over negative distances（最近质心分类器业内标准，未经校准——
校准需独立校准集，属远期）；确定性：平手取排序最小类（先例沿 R31 _dummy_predict）。
"""
from __future__ import annotations

import math
from numbers import Real
from typing import Any

import numpy as np

__all__ = ["spectral_template_match"]


def _numeric_vector(raw: Any, where: str) -> np.ndarray:
    """raw → 一维 float 向量：list/tuple/ndarray，元素须为非 bool **有限**数值
    （NaN/inf 逐元素拒收——对齐 gen_pulse._finite_real 风格；形状先拒）。"""
    if not isinstance(raw, (list, tuple, np.ndarray)):
        raise ValueError(
            f"{where} 必须为数值向量(list/tuple/ndarray)，实际: {type(raw).__name__}"
        )
    if isinstance(raw, np.ndarray) and raw.ndim != 1:
        raise ValueError(f"{where} 必须为一维向量，实际 ndim={raw.ndim}")
    elements = list(raw)
    if not elements:
        raise ValueError(f"{where} 向量不能为空")
    for value in elements:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            raise ValueError(f"{where} 含非数值元素: {value!r}")
        if not math.isfinite(float(value)):  # NaN/inf 是 Real 须显式拒（B47 双审 I-3）
            raise ValueError(f"{where} 元素须为有限实数（拒 NaN/inf）: {value!r}")
    return np.array([float(value) for value in elements], dtype=float)


def spectral_template_match(
    features: Any, class_mean_spectra: dict, labels: Any = None
) -> tuple[str, float]:
    """谱模板匹配分类纯函数：待测特征向量 vs 各类模板向量 → (label, confidence)。

    - features：数值向量（list/tuple/ndarray；谱向量口径由调用方归一后传入——
      与 class_mean_spectra 训练口径一致）；
    - class_mean_spectra：{label: 模板向量} dict（train_classifier where='local'
      产物同构）；
    - labels：类名序列锚（缺省=模板键排序——确定性）；结果 label 限 labels 域；
    - 置信度 = softmax over negative distances（未校准分数，0–1）；
    - 错误：模板空/向量维度不一致/非数值/NaN/inf → ValueError（形状先拒，不静默
      兜底——NaN/inf 不再走 nan 距离→nan 置信度的静默路径）。
    """
    if not isinstance(class_mean_spectra, dict):
        raise ValueError(
            "class_mean_spectra 必须为 dict(label→模板向量)，"
            f"实际: {type(class_mean_spectra).__name__}"
        )
    if not class_mean_spectra:
        raise ValueError("class_mean_spectra 模板 dict 不能为空")

    vector = _numeric_vector(features, "features")

    # 候选类按排序后 labels 序遍历（平手时 argmin 首个最小即排序最小类）；
    # 显式 labels 锚域外的模板不参与匹配（结果限 labels 域）。
    domain = sorted(class_mean_spectra) if labels is None else sorted(set(labels))
    candidates = [lab for lab in domain if lab in class_mean_spectra]
    if not candidates:
        raise ValueError("labels 锚域与模板键无交集（无可匹配类）")

    means = []
    for lab in candidates:
        template = _numeric_vector(class_mean_spectra[lab], f"模板[{lab!r}]")
        if template.size != vector.size:
            raise ValueError(
                f"维度不一致: features={vector.size}, 模板[{lab!r}]={template.size}"
            )
        means.append(template)

    # 欧氏距离（R31 _dummy_predict 同构口径）→ logits=-distance → 稳定 softmax。
    distances = np.linalg.norm(np.stack(means) - vector, axis=1)
    logits = -distances
    exp = np.exp(logits - logits.max())
    probs = exp / exp.sum()
    best = int(np.argmax(probs))
    return candidates[best], float(probs[best])
