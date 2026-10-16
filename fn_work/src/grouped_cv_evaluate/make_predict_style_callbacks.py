"""评测对齐回调工厂（R93）——重写规约与签名意图详见 fn_docs/responsibility.md 域二十三功能块。

对齐口径=模板路同源：train_fn 逐折训练集 samples → 类均值模板（label→均值谱向量，
与 train_classifier where='local' 的 class_mean_spectra 同构口径）；predict_fn 样本
features → shared/spectral_template_match（与部署模板路同一实现）出 label。成对返回
满足 grouped_cv_evaluate 既有自定义回调契约（train_fn/predict_fn 须成对提供）。

形状边界（divide 期收敛 2026-10-15）：CV 样本契约=特征向量（时间平均谱），规则路
与门控感知需原始 IQ 不可复现——含门控感知的完整识别行为准确度由 R91/R92 的 sim
识别器级验收承载（pytest 六样式）。
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from src.shared.spectral_template_match import spectral_template_match

from .grouped_cv_evaluate import _parse_features

__all__ = ["make_predict_style_callbacks"]


def make_predict_style_callbacks(
    labels: Any = None,
) -> tuple[Callable[[list], dict], Callable[[dict, dict], str]]:
    """对齐回调工厂（纯适配，无状态）：返回成对 (train_fn, predict_fn)。

    - labels：类名序列作模板键域锚（缺省=训练集实际出现的标签——分组 CV 逐折
      训练集标签域可窄于全集，模板域随折内实际标签，如实不外扩）；
    - train_fn(train_samples: list[dict]) → {label: 均值谱向量} 模板模型；
    - predict_fn(model: dict, test_sample: dict) → label str（经
      spectral_template_match）；
    - 错误：labels 锚定且锚∩折内训练标签为空 → train_fn ValueError（B48/M-1：
      锚配置错本层显式拒——消息含锚与折内标签原文；形状错仍由
      grouped_cv_evaluate 既有校验上游拒，不重复抛）。
    """
    anchor = sorted(set(labels)) if labels is not None else None

    def train_fn(train_samples: list) -> dict:
        """逐折训练集 → 类均值模板（train_classifier local 的 class_mean_spectra 同构）。"""
        vectors: dict[str, list] = {}
        for sample in train_samples:
            vectors.setdefault(sample["label"], []).append(
                _parse_features(sample["features"], "train 样本")
            )
        # 模板键域：缺省=折内实际标签；labels 锚定时=锚∩折内标签（空类不产模板）。
        domain = sorted(vectors) if anchor is None else [
            lab for lab in anchor if lab in vectors
        ]
        if not domain:  # 锚∩折内标签为空：锚配置错本层显式拒（B48/M-1）
            raise ValueError(
                f"labels 锚域与折内训练标签无交集（模板键域为空）："
                f"锚={anchor}，折内标签={sorted(vectors)}——锚配置错"
                "（形状错由 grouped_cv_evaluate 上游拒，锚域错本层显式拒）"
            )
        return {
            lab: [float(v) for v in np.mean(vectors[lab], axis=0)]
            for lab in domain
        }

    def predict_fn(model: dict, test_sample: dict) -> str:
        """样本 features（_parse_features 口径规整为向量）→ 部署模板路同源出 label。"""
        vector = _parse_features(test_sample["features"], "test 样本")
        label, _confidence = spectral_template_match(vector, model, labels=None)
        return label

    return train_fn, predict_fn
