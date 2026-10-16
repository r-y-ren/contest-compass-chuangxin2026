"""make_predict_style_callbacks 实现测试（R93 对齐回调工厂）：成对回调契约
（train_fn 逐折类均值模板 / predict_fn 经 spectral_template_match 同源）/
折内标签域如实不外扩 / 单样本类模板 / 特征 dict 口径规整 / labels 锚定 /
grouped_cv_evaluate 集成锚。责任规约见 fn_docs/responsibility.md 域二十三功能块。
"""
from __future__ import annotations

import random

from src.grouped_cv_evaluate.grouped_cv_evaluate import grouped_cv_evaluate
from src.grouped_cv_evaluate.make_predict_style_callbacks import (
    make_predict_style_callbacks,
)
from src.shared.spectral_template_match import spectral_template_match


def _separable_two_class_mixed_batches(batches=4, per=2):
    """两类可分合成（中心 ±5、批次混类）：分组 CV 下对齐口径应全对。"""
    data = []
    for bi in range(batches):
        rng = random.Random(100 + bi)
        for _ in range(per):
            data.append(
                {
                    "label": "A",
                    "features": [5.0 + rng.gauss(0.0, 0.1), 0.0],
                    "batch_key": f"b{bi}",
                }
            )
        rng = random.Random(200 + bi)
        for _ in range(per):
            data.append(
                {
                    "label": "B",
                    "features": [-5.0 + rng.gauss(0.0, 0.1), 0.0],
                    "batch_key": f"b{bi}",
                }
            )
    return data


def test_pair_contract_class_mean_template_and_same_source_predict():
    """①成对契约：工厂返回两 callable；train_fn(6 样本 2 类)→{label:均值}（数值
    断言）；predict_fn(近 A 类样本)→'A'——与直调 spectral_template_match 同结果。"""
    train_fn, predict_fn = make_predict_style_callbacks()
    assert callable(train_fn) and callable(predict_fn)

    samples = [
        {"label": "A", "features": [1.0, 2.0]},
        {"label": "A", "features": [3.0, 4.0]},
        {"label": "A", "features": [5.0, 6.0]},
        {"label": "B", "features": [10.0, 0.0]},
        {"label": "B", "features": [8.0, 2.0]},
        {"label": "B", "features": [6.0, 4.0]},
    ]
    model = train_fn(samples)
    assert model == {"A": [3.0, 4.0], "B": [8.0, 2.0]}  # 类均值正确
    # 模板向量为纯 float list（train_classifier local 的 class_mean_spectra 同构）。
    assert all(
        isinstance(v, float) for vec in model.values() for v in vec
    )

    probe = {"label": "?", "features": [2.9, 4.1]}  # 近 A 类
    assert predict_fn(model, probe) == "A"
    # 同源锚：与直调部署模板路同一实现出同一结果。
    assert predict_fn(model, probe) == spectral_template_match(
        [2.9, 4.1], model, labels=None
    )[0]


def test_fold_label_narrowing_no_extension():
    """②折内标签域窄化：全集三类但折内训练集仅 A/B→模板恰两键，C 不外扩。"""
    train_fn, predict_fn = make_predict_style_callbacks()
    full = [
        {"label": "A", "features": [1.0, 1.0], "batch_key": "b0"},
        {"label": "B", "features": [9.0, 9.0], "batch_key": "b0"},
        {"label": "C", "features": [5.0, 0.0], "batch_key": "b1"},  # 全集存在 C
    ]
    fold_train = [s for s in full if s["label"] in ("A", "B")]  # 折内训练子集
    model = train_fn(fold_train)
    assert sorted(model) == ["A", "B"]  # 模板域随折内实际标签，如实不外扩
    assert model["A"] == [1.0, 1.0] and model["B"] == [9.0, 9.0]
    # 预测亦只在有模板的域内（C 无模板不可选）。
    assert predict_fn(model, {"label": "?", "features": [4.9, 0.1]}) in ("A", "B")


def test_single_sample_class_template_is_that_sample():
    """③单样本类→该样本向量即模板（无均值退化歧义）。"""
    train_fn, _predict_fn = make_predict_style_callbacks()
    model = train_fn(
        [
            {"label": "A", "features": [1.0, 2.0, 3.0]},
            {"label": "B", "features": [5.0, 5.0, 5.0]},
        ]
    )
    assert model == {"A": [1.0, 2.0, 3.0], "B": [5.0, 5.0, 5.0]}


def test_feature_dict_normalized_same_as_vector():
    """特征 dict 经 _parse_features 口径规整：键序无关，与等价数值向量同模板同预测。"""
    train_fn, predict_fn = make_predict_style_callbacks()
    dict_model = train_fn(
        [{"label": "A", "features": {"f0100": 3.0, "f0001": 1.0}}]  # 键序打乱
    )
    assert dict_model == {"A": [1.0, 3.0]}  # 按键排序取值
    assert predict_fn(
        dict_model, {"label": "?", "features": {"f0100": 2.9, "f0001": 1.1}}
    ) == predict_fn(dict_model, {"label": "?", "features": [1.1, 2.9]})


def test_grouped_cv_integration_separable_two_class_perfect():
    """④集成锚：对齐回调注入 grouped_cv_evaluate→报告宏结构齐
    （confusion/macro_f1/effective_k）且两类可分时 macro_f1==1.0。"""
    data = _separable_two_class_mixed_batches()  # 4 批 × (2A+2B) = 16
    train_fn, predict_fn = make_predict_style_callbacks()
    res = grouped_cv_evaluate(data, k=2, train_fn=train_fn, predict_fn=predict_fn)

    assert set(res["confusion"]) == {"labels", "matrix"}
    assert res["confusion"]["labels"] == ["A", "B"]
    assert isinstance(res["macro_f1"], float)
    assert res["effective_k"] == 2
    assert res["macro_f1"] == 1.0  # 两类可分→全对
    matrix = res["confusion"]["matrix"]
    assert matrix[0][0] == 8 and matrix[1][1] == 8  # 对角=各类 8 样本
    assert matrix[0][1] == 0 and matrix[1][0] == 0
    assert len(res["per_fold"]) == 2


def test_labels_anchor_restricts_domain():
    """⑤labels 锚定：模板键域限 labels∩折内标签（空类 C 不产模板——predict 如实
    排他）；锚窄于数据时预测限锚域。"""
    fold_train = [
        {"label": "A", "features": [1.0, 1.0]},
        {"label": "B", "features": [9.0, 9.0]},
    ]
    # 锚含全集外无样本的 C：模板恰 {A,B}，C 不产模板。
    train_fn, predict_fn = make_predict_style_callbacks(labels=["C", "A", "B"])
    model = train_fn(fold_train)
    assert sorted(model) == ["A", "B"]
    assert predict_fn(model, {"label": "?", "features": [8.8, 9.1]}) == "B"

    # 锚窄于数据（仅 A）：B 样本在折内也不产模板，预测如实限锚域恒 'A'。
    train_fn_a, predict_fn_a = make_predict_style_callbacks(labels=["A"])
    model_a = train_fn_a(fold_train)
    assert sorted(model_a) == ["A"]
    assert (
        predict_fn_a(model_a, {"label": "?", "features": [9.0, 9.0]}) == "A"
    )
