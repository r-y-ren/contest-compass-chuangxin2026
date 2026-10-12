"""组粒度 K 折划分纯函数（组数不足降级标注）——重写规约与签名意图详见 fn_docs/responsibility.md。

防段级泄漏核心：同一批次键（group key）的全部样本索引永远落在同一折，
train/test 按键集合互斥切分，杜绝段级（批次级）信息跨折泄漏。
"""
from __future__ import annotations


def make_group_splits(group_keys: list, k: int = 5) -> dict:
    """组粒度 K 折划分纯函数（组数不足降级标注）。

    把唯一键集合贪心均衡地分到 K 折：键按（样本数降序，键字典序）依次放入
    当前样本最少的折（折平手取折序最小），确定性、无随机种子参与。

    输入:
        group_keys: list[str|None] —— 每样本的批次键；None 归入 '_none' 桶。
        k: int —— 目标折数，须为 >=2 的 int。

    输出:
        dict:
            'folds': K 个 {'train_keys': [...], 'test_keys': [...],
                           'train_idx': [...], 'test_idx': [...]}
                     —— 每折 test 为该折键的全部样本索引（升序），train 为其余；
                        键列表按字典序，索引列表升序。
            'effective_k': int —— 实际折数（键数<k 时降级为键数）。
            'degraded': bool —— 是否发生降级。
            'key_counts': {键: 样本数} —— 规范化后（None→'_none'）的键计数。

    错误:
        ValueError —— group_keys 非 list / 为空 / k 非 int 或 <2（含 bool）/
                      键非 str|None。
    """
    if not isinstance(group_keys, list):
        raise ValueError(f"group_keys 必须为 list，实际: {type(group_keys).__name__}")
    if not group_keys:
        raise ValueError("group_keys 不能为空列表")
    if isinstance(k, bool) or not isinstance(k, int) or k < 2:
        raise ValueError(f"k 必须为 >=2 的 int，实际: {k!r}")
    for i, key in enumerate(group_keys):
        if key is not None and not isinstance(key, str):
            raise ValueError(f"group_keys[{i}] 必须为 str|None，实际: {key!r}")

    # 规范化键并计数、收集索引（保出现顺序 → test_idx 自然升序的基础）。
    key_counts: dict[str, int] = {}
    key_indices: dict[str, list[int]] = {}
    for idx, key in enumerate(group_keys):
        norm = "_none" if key is None else key
        key_counts[norm] = key_counts.get(norm, 0) + 1
        key_indices.setdefault(norm, []).append(idx)

    n_keys = len(key_counts)
    degraded = n_keys < k
    effective_k = n_keys if degraded else k

    # 贪心均衡：键按（样本数降序，键字典序）依次放入当前样本最少的折。
    fold_keys: list[list[str]] = [[] for _ in range(effective_k)]
    fold_loads = [0] * effective_k
    for key in sorted(key_counts, key=lambda kk: (-key_counts[kk], kk)):
        target = min(range(effective_k), key=lambda f: (fold_loads[f], f))
        fold_keys[target].append(key)
        fold_loads[target] += key_counts[key]

    all_indices = set(range(len(group_keys)))
    folds: list[dict] = []
    for assigned in fold_keys:
        test_set = set(assigned)
        test_idx = sorted(i for key in assigned for i in key_indices[key])
        train_idx = sorted(all_indices - set(test_idx))
        folds.append(
            {
                "train_keys": sorted(kk for kk in key_counts if kk not in test_set),
                "test_keys": sorted(assigned),
                "train_idx": train_idx,
                "test_idx": test_idx,
            }
        )

    return {
        "folds": folds,
        "effective_k": effective_k,
        "degraded": degraded,
        "key_counts": dict(key_counts),
    }
