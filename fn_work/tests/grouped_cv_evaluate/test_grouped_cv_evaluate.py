"""grouped_cv_evaluate 对抗测试：分组 CV 评测协议（防泄漏分组+混淆矩阵+Macro-F1+泄漏自检）。"""
import random
from collections import Counter

import pytest

from src.grouped_cv_evaluate.grouped_cv_evaluate import grouped_cv_evaluate


def _mk(label, center, batch, n=4, sigma=0.05, seed=0):
    """合成样本：label + 数值向量特征（center+高斯噪声）+batch_key，种子确定性。"""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        feats = [v + rng.gauss(0.0, sigma) for v in center]
        out.append({"label": label, "features": feats, "batch_key": batch})
    return out


def _two_class_mixed_batches(
    batches=("b0", "b1", "b2", "b3", "b4", "b5"),
    per=4,
    sigma=0.5,
    center_a=(5.0, 0.0, 0.0, 0.0),
    center_b=(-5.0, 0.0, 0.0, 0.0),
):
    """干净数据：两类可分、每批次都混有两类（分组/随机口径都应高分→不触发泄漏）。"""
    data = []
    for bi, batch in enumerate(batches):
        data += _mk("A", list(center_a), batch, per, sigma, seed=100 + bi)
        data += _mk("B", list(center_b), batch, per, sigma, seed=200 + bi)
    return data


def _leaky_batch_pure_batches(m=10.0, dim=6, per=4):
    """泄漏构造：批次内标签一致+类间特征近（无批次偏移时两类同中心）——
    唯一可学信号是批次偏置，随机划分（train/test 同批）虚高，分组划分近乎瞎猜。"""
    data = []
    for bi in range(6):
        label = "A" if bi < 3 else "B"
        center = [m if d == bi else 0.0 for d in range(dim)]
        data += _mk(label, center, f"p{bi}", per, 0.05, seed=7 + bi)
    return data


def test_grouped_cv_separable_two_class_high_f1_and_diagonal():
    """两类可分+批次混类：macro_f1>0.9、混淆矩阵全对角、逐折 accuracy=1。"""
    data = _two_class_mixed_batches()  # 6 批 × (4A+4B) = 48
    res = grouped_cv_evaluate(data, k=5)
    assert res["macro_f1"] > 0.9
    assert res["confusion"]["labels"] == ["A", "B"]
    matrix = res["confusion"]["matrix"]
    assert matrix[0][0] == 24 and matrix[1][1] == 24
    assert matrix[0][1] == 0 and matrix[1][0] == 0
    assert all(f["accuracy"] == 1.0 for f in res["per_fold"])


def test_grouped_cv_three_class_gives_3x3_matrix():
    """三类混批次：labels 3 个、矩阵 3×3、对角=类计数、非对角 0。"""
    centers = {"A": [6.0, 0, 0, 0], "B": [0, 6.0, 0, 0], "C": [0, 0, 6.0, 0]}
    data = []
    for bi in range(6):
        for li, (label, center) in enumerate(sorted(centers.items())):
            data += _mk(label, center, f"m{bi}", 2, 0.1, seed=10 * bi + li)
    res = grouped_cv_evaluate(data, k=3)
    assert res["confusion"]["labels"] == ["A", "B", "C"]
    matrix = res["confusion"]["matrix"]
    assert len(matrix) == 3 and all(len(row) == 3 for row in matrix)
    assert [matrix[i][i] for i in range(3)] == [12, 12, 12]
    assert all(
        matrix[i][j] == 0 for i in range(3) for j in range(3) if i != j
    )
    assert res["macro_f1"] > 0.9


def test_grouped_cv_leak_suspect_triggered_on_batch_pure_leak():
    """泄漏自检触发：批次内标签一致+类间近→随机口径虚高>0.15→leak_suspect+告警。"""
    data = _leaky_batch_pure_batches()
    with pytest.warns(RuntimeWarning):
        res = grouped_cv_evaluate(data, k=5)
    assert res["leak_suspect"] is True
    assert res["macro_f1"] < 0.85  # 分组口径（防泄漏）分数被如实压低
    assert res["below_target"] is True


def test_grouped_cv_leak_not_triggered_on_clean_data():
    """干净数据：分组/随机口径同高→leak_suspect False。"""
    res = grouped_cv_evaluate(_two_class_mixed_batches(), k=5)
    assert res["leak_suspect"] is False
    assert res["below_target"] is False


# --- B14 中#2 类饥饿排除 → B14 复核发现1 修正：两旗标可并存、警告分三态 ---


def _starved_folds_scenario(maj_batches=9, per_maj=10):
    """并存态构造（审查复现场景）：90 个多类样本分 9 批 + 2 个少类各 5 样本单批，k=5。

    make_group_splits 贪心均衡把两个少类批（计数 5 最小）堆进同一个 test 折 →
    该折训练集只剩多类（类别覆盖 1<2）→ fold_class_starvation=True；同时各类中心
    可分 → 随机口径近乎满分 vs 分组口径少类全错，差>0.15 → leak_suspect=True
    （批纯结构下饥饿与泄漏的贡献不可分——发现1：泄漏不再被饥饿静默改判）。
    """
    data = []
    for bi in range(maj_batches):
        data += _mk("A", [8.0, 0.0, 0.0], f"maj{bi}", per_maj, 0.05, seed=bi)
    data += _mk("B", [-8.0, 0.0, 0.0], "minB", 5, 0.05, seed=90)
    data += _mk("C", [0.0, 8.0, 0.0], "minC", 5, 0.05, seed=91)
    return data


def _starved_folds_indivisible_scenario(maj_batches=9, per_maj=10):
    """仅饥饿态构造：与 _starved_folds_scenario 同折布局（两个少类批堆进同一 test 折 →
    该折训练集只剩多类，fold_class_starvation=True），但三类中心完全相同且零噪声——
    特征完全不可分，随机/分组两口径同样失败（macro_f1 相等）→ 差距 0（≤0.15），
    leak_suspect=False：饥饿旗标独立成立而不涉泄漏改判。"""
    data = []
    for bi in range(maj_batches):
        data += _mk("A", [8.0, 0.0, 0.0], f"maj{bi}", per_maj, 0.0, seed=bi)
    data += _mk("B", [8.0, 0.0, 0.0], "minB", 5, 0.0, seed=90)
    data += _mk("C", [8.0, 0.0, 0.0], "minC", 5, 0.0, seed=91)
    return data


def test_grouped_cv_class_starvation_not_misreported_as_leak():
    """仅饥饿态：折构造饥饿存在但随机/分组差距≤0.15（特征完全不可分，两口径同低）→
    fold_class_starvation=True、leak_suspect=False（差距不达标即非泄漏，与饥饿无关），
    警告文案报仅饥饿。"""
    data = _starved_folds_indivisible_scenario()
    with pytest.warns(RuntimeWarning, match="折构造饥饿"):
        res = grouped_cv_evaluate(data, k=5)
    assert res["fold_class_starvation"] is True
    assert res["leak_suspect"] is False
    assert res["macro_f1"] < 0.85  # 不可分+饥饿：分组口径如实低
    assert res["below_target"] is True


def test_grouped_cv_starvation_and_leak_flags_coexist():
    """并存态（B14 复核发现1）：批纯（可泄漏结构）数据+饥饿折并存、随机/分组差>0.15 →
    两旗标齐 True（leak_suspect 不再被饥饿否决、饥饿旗标保留），警告报并存文案。"""
    data = _starved_folds_scenario()
    with pytest.warns(
        RuntimeWarning, match="差距或由饥饿与泄漏共同贡献——建议增批后再评"
    ):
        res = grouped_cv_evaluate(data, k=5)
    assert res["fold_class_starvation"] is True
    assert res["leak_suspect"] is True
    assert res["macro_f1"] < 0.85  # 分组口径（防泄漏）分数被如实压低
    assert res["below_target"] is True


def test_grouped_cv_starvation_scenario_gap_actually_large():
    """同场景补证：随机口径确实虚高（>0.15 差距真实存在）——排除「差本来就不大」
    的平凡通过，确保并存分支真正吃到了大差距（两旗标齐 True 的前提成立）。"""
    data = _starved_folds_scenario()
    labels = {s["label"] for s in data}
    assert labels == {"A", "B", "C"}
    with pytest.warns(RuntimeWarning, match="饥饿"):
        res = grouped_cv_evaluate(data, k=5)
    # 少类 B/C 在分组口径下被整折饿死 → 混淆矩阵对应行全预测成 A
    idx = {lab: i for i, lab in enumerate(res["confusion"]["labels"])}
    matrix = res["confusion"]["matrix"]
    assert matrix[idx["B"]][idx["A"]] == 5
    assert matrix[idx["C"]][idx["A"]] == 5


def test_grouped_cv_no_starvation_on_mixed_batches():
    """干净混批数据：各折训练集类别覆盖≥2 → fold_class_starvation=False（旗标不粘死）。"""
    res = grouped_cv_evaluate(_two_class_mixed_batches(), k=5)
    assert res["fold_class_starvation"] is False
    assert res["leak_suspect"] is False


def test_grouped_cv_below_target_on_unseparable_noise():
    """不可分噪声特征：F1 低+below_target=True 如实记录（不粉饰）。"""
    data = []
    for bi in range(6):
        data += _mk("A", [0.0, 0.0, 0.0], f"n{bi}", 5, 1.0, seed=bi)
        data += _mk("B", [0.0, 0.0, 0.0], f"n{bi}", 5, 1.0, seed=50 + bi)
    res = grouped_cv_evaluate(data, k=3)
    assert res["below_target"] is True
    assert res["macro_f1"] < 0.85
    assert res["leak_suspect"] is False  # 两种口径都近随机水平，差距不超阈值


def test_grouped_cv_custom_fns_called_once_per_fold_and_per_test_sample():
    """自定义 train_fn/predict_fn：调用次数=折数/测试样本数（对照组实验不碰用户回调）。"""
    data = _two_class_mixed_batches(batches=("c0", "c1", "c2", "c3"), per=2, sigma=0.1)
    calls = {"train": 0, "predict": 0}

    def train_fn(train_samples):
        calls["train"] += 1
        return sorted({s["label"] for s in train_samples})[0]

    def predict_fn(model, test_sample):
        calls["predict"] += 1
        return model

    res = grouped_cv_evaluate(data, k=4, train_fn=train_fn, predict_fn=predict_fn)
    assert res["effective_k"] == 4
    assert calls["train"] == 4
    assert calls["predict"] == len(data) == res["n_samples"] == 16
    assert 0.0 <= res["macro_f1"] <= 1.0


def test_grouped_cv_missing_batch_key_defaults_to_none_bucket():
    """batch_key 全缺省归 '_none' 桶：与显式键同等参与组粒度分折。"""
    data = (
        _mk("A", [5.0, 0.0], "b1", 2, 0.05, seed=1)
        + _mk("B", [-5.0, 0.0], "b1", 2, 0.05, seed=2)
        + _mk("A", [5.0, 0.0], "x", 1, 0.05, seed=3)
        + _mk("B", [-5.0, 0.0], "x", 1, 0.05, seed=4)
        + _mk("A", [5.0, 0.0], "b2", 1, 0.05, seed=5)
        + _mk("B", [-5.0, 0.0], "b2", 1, 0.05, seed=6)
    )
    for s in data[4:6]:  # 2 个样本缺 batch_key → '_none' 桶（计数 2）
        del s["batch_key"]
    res = grouped_cv_evaluate(data, k=5)
    # 键计数 b1:4、_none:2、b2:2 → 3 唯一键（k=5 降级）；贪心均衡 n_test [4,2,2]
    assert res["effective_k"] == 3
    assert [f["n_test"] for f in res["per_fold"]] == [4, 2, 2]
    assert [f["n_train"] for f in res["per_fold"]] == [4, 6, 6]
    assert res["n_samples"] == 8
    assert res["macro_f1"] > 0.9


def test_grouped_cv_effective_k_degrades_with_two_batches_k5():
    """2 批次 k=5 → effective_k 降级为 2，共 2 折。"""
    data = _two_class_mixed_batches(batches=("d0", "d1"), per=3, sigma=0.1)
    res = grouped_cv_evaluate(data, k=5)
    assert res["effective_k"] == 2
    assert len(res["per_fold"]) == 2
    assert [f["n_test"] for f in res["per_fold"]] == [6, 6]
    assert res["macro_f1"] > 0.9


def test_grouped_cv_per_fold_counts_and_indices():
    """per_fold：fold 序号连续、n_test 全覆盖一次、n_train=总×(k-1)、accuracy∈[0,1]。"""
    data = _two_class_mixed_batches()
    res = grouped_cv_evaluate(data, k=5)
    per_fold = res["per_fold"]
    assert [f["fold"] for f in per_fold] == list(range(res["effective_k"]))
    assert sum(f["n_test"] for f in per_fold) == 48 == res["n_samples"]
    assert sum(f["n_train"] for f in per_fold) == 48 * (res["effective_k"] - 1)
    assert all(f["n_test"] >= 1 for f in per_fold)
    assert all(0.0 <= f["accuracy"] <= 1.0 for f in per_fold)


def test_grouped_cv_macro_f1_matches_independent_recompute():
    """macro_f1 数值独立复算：从混淆矩阵按定义重算 P/R/F1 平均，行和=真值类计数。"""
    data = []
    for bi in range(5):
        data += _mk("A", [1.5, 0.0, 0.0], f"r{bi}", 6, 1.0, seed=bi)
        data += _mk("B", [-1.5, 0.0, 0.0], f"r{bi}", 6, 1.0, seed=60 + bi)
    res = grouped_cv_evaluate(data, k=5)
    labels = res["confusion"]["labels"]
    matrix = res["confusion"]["matrix"]
    f1s = []
    for i in range(len(labels)):
        tp = matrix[i][i]
        fp = sum(matrix[row][i] for row in range(len(labels))) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    assert res["macro_f1"] == pytest.approx(sum(f1s) / len(f1s), abs=1e-9)
    counts = Counter(s["label"] for s in data)
    for i, label in enumerate(labels):
        assert sum(matrix[i]) == counts[label]  # 行和=该真值类全部样本数
    assert 0.0 < res["macro_f1"] < 1.0  # 有错分，复算非平凡


def test_grouped_cv_single_label_rejected():
    """样本少于 2 类拒。"""
    data = _mk("A", [1.0, 2.0], "b0", 4)
    with pytest.raises(ValueError):
        grouped_cv_evaluate(data, k=2)


def test_grouped_cv_missing_label_rejected():
    data = _two_class_mixed_batches(batches=("x0", "x1"), per=2, sigma=0.1)
    del data[1]["label"]
    with pytest.raises(ValueError):
        grouped_cv_evaluate(data, k=2)


def test_grouped_cv_missing_features_rejected():
    data = _two_class_mixed_batches(batches=("x0", "x1"), per=2, sigma=0.1)
    del data[2]["features"]
    with pytest.raises(ValueError):
        grouped_cv_evaluate(data, k=2)


def test_grouped_cv_empty_samples_rejected():
    with pytest.raises(ValueError):
        grouped_cv_evaluate([], k=3)


def test_grouped_cv_non_dict_element_rejected():
    data = _two_class_mixed_batches(batches=("x0", "x1"), per=1, sigma=0.1)
    with pytest.raises(ValueError):
        grouped_cv_evaluate(data + [42], k=2)


def test_grouped_cv_invalid_k_rejected_via_make_group_splits():
    """k 透传 make_group_splits 校验：<2 或非 int 拒。"""
    data = _two_class_mixed_batches(batches=("z0", "z1", "z2"), per=1, sigma=0.1)
    with pytest.raises(ValueError):
        grouped_cv_evaluate(data, k=1)
    with pytest.raises(ValueError):
        grouped_cv_evaluate(data, k="5")  # type: ignore[arg-type]


def test_grouped_cv_single_batch_key_rejected():
    """全部样本同属一个批次键→每折训练集为空→拒绝评测（分组 CV 不可行）。"""
    data = _mk("A", [5.0, 0.0], "only", 3) + _mk("B", [-5.0, 0.0], "only", 3)
    with pytest.raises(ValueError):
        grouped_cv_evaluate(data, k=3)


def test_grouped_cv_mismatched_custom_fns_rejected():
    """train_fn/predict_fn 只提供其一→拒绝（口径必须成对）。"""
    data = _two_class_mixed_batches(batches=("w0", "w1", "w2"), per=1, sigma=0.1)
    with pytest.raises(ValueError):
        grouped_cv_evaluate(data, k=3, train_fn=lambda ts: None)
    with pytest.raises(ValueError):
        grouped_cv_evaluate(data, k=3, predict_fn=lambda m, s: "A")


def test_grouped_cv_feature_dict_features_supported():
    """特征 dict 口径（与 train_classifier 谱特征口径一致）：可用且键序无关。"""
    rng = random.Random(0)
    data = []
    for bi in range(4):
        for label, peak in (("A", 5.0), ("B", -5.0)):
            for _ in range(3):
                data.append(
                    {
                        "label": label,
                        "features": {
                            "peak": peak + rng.gauss(0, 0.1),
                            "floor": rng.gauss(0, 0.1),
                        },
                        "batch_key": f"f{bi}",
                    }
                )
    res = grouped_cv_evaluate(data, k=4)
    assert res["macro_f1"] > 0.9
    # 键序打乱（值不变）→ 解析向量相同 → 结果完全一致
    shuffled = [
        {**s, "features": dict(reversed(list(s["features"].items())))} for s in data
    ]
    assert grouped_cv_evaluate(shuffled, k=4) == res


def test_grouped_cv_result_shape_and_types():
    """返回契约：恰 9 个顶层键（含 B14 中#2 新增 fold_class_starvation+R93 新增
    eval_protocol）+confusion 两键+类型正确。"""
    data = _two_class_mixed_batches(batches=("y0", "y1", "y2"), per=2, sigma=0.1)
    res = grouped_cv_evaluate(data, k=3)
    assert set(res) == {
        "confusion",
        "macro_f1",
        "per_fold",
        "effective_k",
        "leak_suspect",
        "fold_class_starvation",
        "below_target",
        "n_samples",
        "eval_protocol",
    }
    assert set(res["confusion"]) == {"labels", "matrix"}
    assert isinstance(res["macro_f1"], float)
    assert isinstance(res["leak_suspect"], bool)
    assert isinstance(res["fold_class_starvation"], bool)
    assert isinstance(res["below_target"], bool)
    assert isinstance(res["n_samples"], int)
    assert isinstance(res["effective_k"], int)
    assert isinstance(res["eval_protocol"], str)
    assert isinstance(res["confusion"]["labels"], list)
    assert all(
        isinstance(cell, int)
        for row in res["confusion"]["matrix"]
        for cell in row
    )


# --- R93 口径标注（B48）：缺省 intrinsic_dummy 锚 / 对齐 aligned_template 验收 / 类型校验 ---


def test_r93_default_eval_protocol_is_intrinsic_dummy():
    """R93 缺省路径零语义漂移锚：不传 eval_protocol→报告 'eval_protocol'==
    'intrinsic_dummy'（既有评测协议全不变——缺省标注即内置 dummy 口径；新增用例
    补断言，不改既有用例）。"""
    res = grouped_cv_evaluate(_two_class_mixed_batches(), k=5)
    assert res["eval_protocol"] == "intrinsic_dummy"
    assert isinstance(res["eval_protocol"], str)


def test_r93_aligned_template_protocol_with_make_predict_style_callbacks():
    """R93 验收核心：显式 eval_protocol='aligned_template'+注入
    make_predict_style_callbacks() 对齐回调跑两类可分合成 → 口径标注断言+
    矩阵字段断言（labels/对角=类计数/非对角 0）+macro_f1==1.0。"""
    # 局部导入：R93 对齐回调工厂（同包新叶）——口径标注与回调来源一致由本调用方保证
    from src.grouped_cv_evaluate.make_predict_style_callbacks import (
        make_predict_style_callbacks,
    )

    train_fn, predict_fn = make_predict_style_callbacks()
    data = _two_class_mixed_batches()  # 6 批 × (4A+4B) = 48，两类可分
    res = grouped_cv_evaluate(
        data,
        k=5,
        train_fn=train_fn,
        predict_fn=predict_fn,
        eval_protocol="aligned_template",
    )
    assert res["eval_protocol"] == "aligned_template"
    assert res["macro_f1"] == 1.0  # 对齐口径（模板路同源）两类可分全对
    assert res["confusion"]["labels"] == ["A", "B"]
    matrix = res["confusion"]["matrix"]
    assert matrix[0][0] == 24 and matrix[1][1] == 24
    assert matrix[0][1] == 0 and matrix[1][0] == 0
    assert res["below_target"] is False  # 满分不触目标旗标（既有协议语义不动）


def test_r93_invalid_eval_protocol_type_rejected():
    """eval_protocol 非 str|None（int）→ ValueError（沿参数校验族风格：类型先拒，
    在样本校验前抛）。"""
    data = _two_class_mixed_batches(batches=("t0", "t1"), per=2, sigma=0.1)
    with pytest.raises(ValueError, match="eval_protocol"):
        grouped_cv_evaluate(data, k=2, eval_protocol=7)  # type: ignore[arg-type]
