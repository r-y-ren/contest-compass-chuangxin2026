"""失效判据纯函数（默认 PER≥10%，EN 300 328 口径）——重写规约与签名意图详见 fn_docs/responsibility.md。

判据语义（样本不足不判失效——保守继续测试）：
- ``per >= threshold`` → failed=True，basis='per_threshold'（≥ 口径，恰等判失效）；
- ``available`` False / ``per`` None / ``n_total`` 0 → failed=False，basis='insufficient_samples'；
- ``per < threshold`` → failed=False，basis='per_threshold'。
"""
from __future__ import annotations

import math


def check_failure(per_result: dict, threshold: float = 0.10) -> dict:
    """失效判据评估：窗口 PER 聚合对阈值比较，返回 失效/未失效+依据。

    Args:
        per_result: compute_per 口径的窗口聚合 ``{'per', 'n_error', 'n_total',
            'window', 'available', 'samples_note'}``，或直接最小形状
            ``{'per': float|None, 'n_total': int, 'available': bool}``；
            仅 ``per`` 键必填（缺 ``n_total`` 视 0、缺 ``available`` 视 True）。
        threshold: 失效阈值，域 (0, 1]，默认 0.10（EN 300 328 口径）。

    Returns:
        dict: ``{'failed': bool, 'basis': 'per_threshold'|'insufficient_samples',
        'per': float|None, 'threshold': float, 'n_total': int, 'detail': str}``；
        ``detail`` 文案含 per/threshold/n_total 数值。

    Raises:
        ValueError: threshold 为 bool/非数值/NaN/域外 (0,1]；per_result 非 dict
            或缺 ``per`` 键；per 为 bool/非数值/NaN/数值时域外 [0,1]。
    """
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError(
            f"threshold must be a number in (0, 1], got {type(threshold).__name__}: {threshold!r}"
        )
    if math.isnan(threshold) or not (0 < threshold <= 1):
        raise ValueError(f"threshold must be in (0, 1], got {threshold!r}")

    if not isinstance(per_result, dict):
        raise ValueError(
            f"per_result must be dict, got {type(per_result).__name__}: {per_result!r}"
        )
    if "per" not in per_result:
        raise ValueError(f"per_result must contain 'per' key, got keys: {sorted(per_result)}")

    per = per_result["per"]
    if per is not None:
        if isinstance(per, bool) or not isinstance(per, (int, float)):
            raise ValueError(f"per must be float|None in [0, 1], got {type(per).__name__}: {per!r}")
        if math.isnan(per) or not (0 <= per <= 1):
            raise ValueError(f"per must be in [0, 1] when numeric, got {per!r}")

    n_total = per_result.get("n_total", 0)
    available = per_result.get("available", True)

    if (not available) or (per is None) or (n_total == 0):
        return {
            "failed": False,
            "basis": "insufficient_samples",
            "per": per,
            "threshold": float(threshold),
            "n_total": n_total,
            "detail": (
                f"insufficient_samples: available={available}, per={per!r}, "
                f"n_total={n_total}——样本不足不判失效，保守继续测试"
            ),
        }

    failed = per >= threshold
    return {
        "failed": failed,
        "basis": "per_threshold",
        "per": per,
        "threshold": float(threshold),
        "n_total": n_total,
        "detail": (
            f"per={per:.4g} {'>=' if failed else '<'} threshold={threshold:.4g} "
            f"(n_total={n_total}) -> {'失效' if failed else '未失效'}（EN 300 328 口径）"
        ),
    }
