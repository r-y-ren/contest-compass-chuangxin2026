"""make_group_splits 对抗测试：组粒度 K 折划分（防段级泄漏）。"""
import pytest

from src.grouped_cv_evaluate.make_group_splits import make_group_splits


def _owner_fold(res: dict, key: str) -> int:
    """断言 key 恰归属一个 test 折并返回其下标。"""
    owners = [fi for fi, fold in enumerate(res["folds"]) if key in fold["test_keys"]]
    assert len(owners) == 1, f"键 {key!r} 应恰属于一个折，实际: {owners}"
    return owners[0]


def test_same_key_samples_never_split_across_folds():
    """防泄漏断言性质：同一键的全部索引永远同折，绝不跨折。"""
    keys = ["b1"] * 3 + ["b2"] * 5 + ["b3"] * 2 + ["b4"] * 4 + ["b5"] * 6 + ["b6"] * 1
    res = make_group_splits(keys, k=3)
    for key in sorted(set(keys)):
        fi = _owner_fold(res, key)
        expected = {i for i, kk in enumerate(keys) if kk == key}
        # 全部在该折 test 内，且不出现在任何其他折的 test/train... 即不出现在其他折 test
        assert expected <= set(res["folds"][fi]["test_idx"])
        for other, fold in enumerate(res["folds"]):
            if other != fi:
                assert not (expected & set(fold["test_idx"]))


def test_full_coverage_each_sample_in_exactly_one_test():
    """K 折 test 全覆盖：每样本恰好出现在一个 test_idx。"""
    keys = ["a", "b", "a", "c", "b", "a", "d", "e"]
    res = make_group_splits(keys, k=4)
    seen = [i for fold in res["folds"] for i in fold["test_idx"]]
    assert sorted(seen) == list(range(len(keys)))
    assert len(seen) == len(set(seen))


def test_train_test_disjoint_and_union_is_all():
    """每折 train/test 不交且并集=全索引。"""
    keys = ["g1", "g2", "g3", "g1", "g2", "g4"]
    res = make_group_splits(keys, k=2)
    n = len(keys)
    for fold in res["folds"]:
        assert not (set(fold["train_idx"]) & set(fold["test_idx"]))
        assert sorted(fold["train_idx"] + fold["test_idx"]) == list(range(n))
        assert not (set(fold["train_keys"]) & set(fold["test_keys"]))
        assert sorted(fold["train_keys"] + fold["test_keys"]) == sorted(set(keys))


def test_degrade_when_fewer_keys_than_k():
    """3 唯一键 k=5 → 降级 effective_k=3、degraded=True、共 3 折。"""
    keys = ["a", "b", "c", "a", "c"]
    res = make_group_splits(keys, k=5)
    assert res["effective_k"] == 3
    assert res["degraded"] is True
    assert len(res["folds"]) == 3
    # 每键独占一折
    for fi, fold in enumerate(res["folds"]):
        assert len(fold["test_keys"]) == 1


def test_no_degrade_when_keys_ge_k():
    """键数>=k 不降级。"""
    keys = ["k1", "k2", "k3", "k4", "k5", "k6"]
    res = make_group_splits(keys, k=3)
    assert res["effective_k"] == 3
    assert res["degraded"] is False
    assert len(res["folds"]) == 3


def test_greedy_balance_big_key_first():
    """均衡性：两键 100/1 样本 k=2 → 大键独占一折的 test。"""
    keys = ["A"] * 100 + ["B"]
    res = make_group_splits(keys, k=2)
    fa = _owner_fold(res, "A")
    fb = _owner_fold(res, "B")
    assert res["folds"][fa]["test_keys"] == ["A"]
    assert res["folds"][fa]["test_idx"] == list(range(100))
    assert res["folds"][fb]["test_keys"] == ["B"]
    assert res["folds"][fb]["test_idx"] == [100]


def test_greedy_balance_equalizes_fold_loads():
    """贪心均衡：计数 10,9,8,3,2,1 k=3 → 三折各 11 样本。"""
    keys = ["a"] * 10 + ["b"] * 9 + ["c"] * 8 + ["d"] * 3 + ["e"] * 2 + ["f"] * 1
    res = make_group_splits(keys, k=3)
    assert [len(f["test_idx"]) for f in res["folds"]] == [11, 11, 11]


def test_none_key_bucketed_as_none_literal():
    """None 键统一归 '_none' 桶，索引全部同折。"""
    keys = ["a", None, "a", None, "b", None]
    res = make_group_splits(keys, k=2)
    assert res["key_counts"]["_none"] == 3
    fn = _owner_fold(res, "_none")
    assert res["folds"][fn]["test_idx"] == [1, 3, 5]
    assert None not in res["key_counts"]


def test_count_tie_broken_lexicographically():
    """键计数平手按字典序：'b'/'a' 同计数 k=2 → 'a' 进折 0。"""
    res = make_group_splits(["b", "a"], k=2)
    assert res["folds"][0]["test_keys"] == ["a"]
    assert res["folds"][1]["test_keys"] == ["b"]


def test_key_counts_reported():
    res = make_group_splits(["x", "y", "x", "z", "x", "y"], k=2)
    assert res["key_counts"] == {"x": 3, "y": 2, "z": 1}


def test_indices_sorted_ascending():
    """索引保序：所有 test_idx / train_idx 升序。"""
    keys = ["m", "z", "a", "m", "z", "a", "m", "q"]
    res = make_group_splits(keys, k=2)
    for fold in res["folds"]:
        assert fold["test_idx"] == sorted(fold["test_idx"])
        assert fold["train_idx"] == sorted(fold["train_idx"])


def test_empty_or_non_list_rejected():
    with pytest.raises(ValueError):
        make_group_splits([], k=3)
    with pytest.raises(ValueError):
        make_group_splits(("a", "b"), k=2)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_k", [1, 0, -2, True, False, 2.5, "3"])
def test_invalid_k_rejected(bad_k):
    with pytest.raises(ValueError):
        make_group_splits(["a", "b", "c"], k=bad_k)


def test_non_str_non_none_key_rejected():
    with pytest.raises(ValueError):
        make_group_splits(["a", 42, "b"], k=2)
    with pytest.raises(ValueError):
        make_group_splits(["a", 3.5], k=2)
