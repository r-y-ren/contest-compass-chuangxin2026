"""公式(3) 单点对数距离路径损耗：L(d)=L(d0)+10·n·log10(d/d0)+X_σ（重写规约与签名意图详见 fn_docs/responsibility.md）。"""
from __future__ import annotations

import math
import random
from numbers import Real

__all__ = ["compute_pathloss"]


def _finite_float(name: str, value: object) -> float:
    """数值参数校验：拒 bool、非实数、NaN/±inf、超 float 域（如 10**400），返回 float。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} 必须为实数（bool/非数值一律拒绝）：{value!r}")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        # 例：int 10**400 转 float 溢出——按"极大 d 不产生 inf"口径直接拒绝
        raise ValueError(f"{name} 超出 float 可表示域：{value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} 必须为有限数（拒 NaN/±inf）：{value!r}")
    return number


def compute_pathloss(
    d_m: float,
    d0_m: float,
    l0_db: float,
    n: float,
    x_sigma: float | None = None,
    seed: int | None = None,
) -> float:
    """公式(3) 单点对数距离路径损耗（纯函数）。

    L(d) = L(d0) + 10·n·log10(d/d0) + X_σ，其中 X_σ ~ N(0, σ²) 单次抽样（dB）。

    阴影抽样口径（per-call 重置，文档注明）：每次调用独立构造 ``random.Random(seed)``
    并抽取一个 X_σ——单点抽样只依赖 ``(seed, x_sigma)``，与调用序列/顺序无关。因此：
    同一 (d 序列, seed) 两次计算逐点一致；不同 d 序列同 seed 的首点抽样一致。
    ``x_sigma`` 为 None 或 0 时无阴影项（确定性输出）；``seed=None`` 且 σ>0 时由
    系统熵播种（可运行但不可复现）。

    :param d_m: 目标距离（米），>0 且 ≥ d0_m
    :param d0_m: 参考距离（米），>0
    :param l0_db: 参考距离处标称损耗 L(d0)（dB）
    :param n: 路径损耗指数，>0
    :param x_sigma: 阴影衰落标准差 σ（dB）；None/0=关闭，负值拒绝
    :param seed: 阴影抽样种子（int 或 None；bool 拒绝）
    :return: 路径损耗（dB），保证有限 float
    :raises ValueError: d_m≤0 或 d_m<d0_m；d0_m≤0；n≤0；x_sigma<0；任何数值参数
        为 bool/非实数/NaN/±inf（含超 float 域如 10**400）；seed 非 int/None。
    """
    d = _finite_float("d_m", d_m)
    d0 = _finite_float("d0_m", d0_m)
    l0 = _finite_float("l0_db", l0_db)
    exponent = _finite_float("n", n)

    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError(f"seed 必须为 int 或 None（bool 拒绝）：{seed!r}")

    if d0 <= 0.0:
        raise ValueError(f"d0_m 必须为正参考距离：d0_m={d0!r}")
    if d <= 0.0:
        raise ValueError(f"d_m 必须为正距离：d_m={d!r}")
    if d < d0:
        raise ValueError(f"d_m 不得小于参考距离 d0_m：d_m={d!r} < d0_m={d0!r}")
    if exponent <= 0.0:
        raise ValueError(f"n 必须为正路径损耗指数：n={exponent!r}")

    deterministic = l0 + 10.0 * exponent * math.log10(d / d0)
    if not math.isfinite(deterministic):
        raise ValueError(f"路径损耗中间值非有限（d/d0 比值溢出或超域）：d_m={d!r}, d0_m={d0!r}, n={exponent!r}")

    if x_sigma is None:
        return deterministic

    sigma = _finite_float("x_sigma", x_sigma)
    if sigma < 0.0:
        raise ValueError(f"x_sigma 不得为负（None/0 关闭阴影项）：x_sigma={sigma!r}")
    if sigma == 0.0:
        return deterministic

    rng = random.Random(seed)  # per-call 重置：单点抽样仅依赖 (seed, x_sigma)
    shadow = rng.normalvariate(0.0, sigma)
    result = deterministic + shadow
    if not math.isfinite(result):
        raise ValueError(f"路径损耗结果非有限：{deterministic!r} + {shadow!r}")
    return result
