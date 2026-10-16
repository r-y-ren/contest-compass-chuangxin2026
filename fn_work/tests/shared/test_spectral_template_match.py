"""spectral_template_match 对抗测试：距离序/softmax 值域与和一/平手取排序最小类
（确定性）/labels 显式锚域/形状先拒（模板空、非 dict、维度不一致、非数值）/
ndarray 与 list 同果/距离按维度归一防 softmax 饱和（C1）。责任规约见
fn_docs/responsibility.md 共享函数节。"""
from __future__ import annotations

import math

import numpy as np
import pytest

from src.shared.spectral_template_match import spectral_template_match


def test_distance_ordering():
    """① 距离序正确：待测向量近 A 远 B → label=A 且 confidence>0.5。"""
    spectra = {"A": [0.0, 0.0], "B": [4.0, 0.0]}
    label, conf = spectral_template_match([0.2, 0.1], spectra)
    assert label == "A"
    assert conf > 0.5
    # 换到 B 侧对称成立。
    label_b, conf_b = spectral_template_match([3.9, -0.1], spectra)
    assert label_b == "B"
    assert conf_b > 0.5


def test_softmax_value_range_and_sum_one():
    """② softmax 值域与和一：两类等距 → conf=0.5（各占一半即和一，归一除子
    同值不破坏等距）；三类距离 (0,1,1) → conf=精确 softmax 归一值（logits=
    -distance/sqrt(维度) 的 RMS 归一口径——C1 防饱和改造后数值更新）；conf
    始终 ∈ (0,1]。"""
    label, conf = spectral_template_match(
        [1.0, 0.0], {"A": [0.0, 0.0], "B": [2.0, 0.0]}
    )
    assert (label, conf) == ("A", 0.5)  # 等距平手 → 排序最小类 + 各 0.5

    label3, conf3 = spectral_template_match(
        [0.0, 0.0], {"A": [0.0, 0.0], "B": [1.0, 0.0], "C": [-1.0, 0.0]}
    )
    # RMS 归一口径（2 维）：logits=-d/sqrt(2) → exp(0)/(exp(0)+2·exp(-1/√2))
    expected = 1.0 / (1.0 + 2.0 * math.exp(-1.0 / math.sqrt(2.0)))
    assert label3 == "A"
    assert math.isclose(conf3, expected, rel_tol=1e-12)
    for conf_case in (conf, conf3):
        assert 0.0 < conf_case <= 1.0


def test_tie_break_deterministic():
    """③ 平手确定性：等距平手 → 排序最小类（与 labels 给出顺序无关）；重复调用同结果。"""
    spectra = {"B": [2.0, 0.0], "A": [0.0, 0.0]}  # dict 序故意 B 在前
    results = {spectral_template_match([1.0, 0.0], spectra) for _ in range(5)}
    assert results == {("A", 0.5)}
    # 显式 labels 乱序给出，平手仍取排序最小类。
    label, _ = spectral_template_match([1.0, 0.0], spectra, labels=["B", "A"])
    assert label == "A"


def test_labels_anchor():
    """④ labels 显式锚定：结果限 labels 域（域外最近类被排除）；锚域与模板键
    无交集 → ValueError（形状先拒，不静默兜底）。"""
    spectra = {"A": [0.0, 0.0], "B": [1.0, 0.0], "C": [0.1, 0.0]}
    label, conf = spectral_template_match([0.2, 0.0], spectra, labels=["A", "B"])
    assert label == "A"  # 全域最近是 C(0.1)，锚域外被排除 → 域内最近 A(0.2)
    assert 0.0 < conf <= 1.0
    with pytest.raises(ValueError, match="无交集"):
        spectral_template_match([0.2, 0.0], spectra, labels=["X"])


def test_empty_or_non_dict_templates():
    """⑤ 模板空 dict / 非 dict → ValueError。"""
    with pytest.raises(ValueError, match="不能为空"):
        spectral_template_match([1.0, 2.0], {})
    with pytest.raises(ValueError, match="dict"):
        spectral_template_match([1.0, 2.0], [("A", [0.0, 0.0])])


def test_dimension_mismatch():
    """⑥ 维度不一致 → ValueError：features≠模板，及模板相互不一致。"""
    with pytest.raises(ValueError, match="维度不一致"):
        spectral_template_match([1.0, 2.0, 3.0], {"A": [0.0, 0.0]})
    with pytest.raises(ValueError, match="维度不一致"):
        spectral_template_match(
            [1.0, 2.0], {"A": [0.0, 0.0], "B": [1.0, 2.0, 3.0]}
        )


def test_non_numeric_elements():
    """⑦ 非数值元素 → ValueError：features 与模板两侧皆拒（bool 不作数值）。"""
    with pytest.raises(ValueError, match="非数值"):
        spectral_template_match([1.0, "x"], {"A": [0.0, 0.0]})
    with pytest.raises(ValueError, match="非数值"):
        spectral_template_match([1.0, 2.0], {"A": [0.0, None]})
    with pytest.raises(ValueError, match="非数值"):
        spectral_template_match([True, 2.0], {"A": [0.0, 0.0]})


def test_ndarray_list_tuple_same_result():
    """⑧ ndarray/list/tuple 输入同结果（features 与模板两侧均同构）。"""
    list_result = spectral_template_match([0.3, 0.1], {"A": [0.0, 0.0], "B": [2.0, 0.0]})
    arr_result = spectral_template_match(
        np.array([0.3, 0.1]), {"A": np.zeros(2), "B": np.array([2.0, 0.0])}
    )
    tuple_result = spectral_template_match(
        (0.3, 0.1), {"A": (0.0, 0.0), "B": (2.0, 0.0)}
    )
    assert list_result == arr_result == tuple_result


def test_near_distances_not_saturated_after_dim_normalization():
    """⑨ 距离按维度归一防 softmax 饱和（C1）：两类近距（距离 10 与 12，16 维）→
    logits=-distance/sqrt(16)（每维 RMS 口径）→ conf=1/(1+exp(-0.5))≈0.622，
    介于 (0.5,0.95)——置信度不再恒 1.0；argmin 序不变（近者 A 胜出）。"""
    features = np.zeros(16)
    near = np.concatenate(([10.0], np.zeros(15)))  # 距离 10
    far = np.concatenate(([0.0, 12.0], np.zeros(14)))  # 距离 12
    label, conf = spectral_template_match(features, {"A": near, "B": far})
    assert label == "A"  # 归一除子同值 → 最近类判定序不变
    assert 0.5 < conf < 0.95  # 近距两类不再饱和恒 1.0
    expected = 1.0 / (1.0 + math.exp(-(12.0 - 10.0) / math.sqrt(16.0)))
    assert math.isclose(conf, expected, rel_tol=1e-12)  # RMS 归一精确值
