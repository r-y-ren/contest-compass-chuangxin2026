"""PER 纯计算（窗口参数化+样本量标记）——重写规约与签名意图详见 fn_docs/responsibility.md。

窗口语义（由调用方传入的序列化计数口径，本函数只收计数不收序列、只算比值，
窗口聚合归调用方；``window`` 字典透传仅用于记录口径）：
- ``None`` → 缺省累计 ``{'type': 'cumulative'}``；
- ``{'type': 'interval', 'last_n': k}`` → 最近 k 个样本的区间口径。
"""
from __future__ import annotations

_LOW_SAMPLES_THRESHOLD = 30


def compute_per(n_error: int, n_total: int, window: dict | None = None) -> dict:
    """PER 纯计算：``per = n_error / n_total``，附样本量置信标记。

    Args:
        n_error: 错误样本计数（非负 int，且 <= n_total）。
        n_total: 总样本计数（非负 int；0 表示无样本）。
        window: 计数口径字典，透传记录；None 视为累计口径。

    Returns:
        dict: ``{'per', 'n_error', 'n_total', 'window', 'available',
        'samples_note'}``；n_total==0 时 available=False、per=None、
        note='no_samples'；n_total<30 时 note='low_samples(<30)'（available
        仍 True，作为 EN 300 328 判据的样本量警告）；样本充足时 note=''。

    Raises:
        ValueError: n_error/n_total 为 bool、非 int（含 NaN）、负数，
            或 n_error > n_total。
    """
    for name, value in (("n_error", n_error), ("n_total", n_total)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be int, got {type(value).__name__}: {value!r}")
        if value < 0:
            raise ValueError(f"{name} must be non-negative, got {value}")
    if n_error > n_total:
        raise ValueError(f"n_error ({n_error}) must not exceed n_total ({n_total})")

    resolved_window = window if window is not None else {"type": "cumulative"}

    if n_total == 0:
        return {
            "per": None,
            "n_error": n_error,
            "n_total": n_total,
            "window": resolved_window,
            "available": False,
            "samples_note": "no_samples",
        }
    return {
        "per": n_error / n_total,
        "n_error": n_error,
        "n_total": n_total,
        "window": resolved_window,
        "available": True,
        "samples_note": "low_samples(<30)" if n_total < _LOW_SAMPLES_THRESHOLD else "",
    }
