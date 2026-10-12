"""公式(4) SNR 估计（bin 归属划分）——B10 叶子（上游 compute_spectrum_stats）。

口径与约定（重写规约落地细节，背景见 fn_docs/responsibility.md R17）：
- dB→线性：p = 10**(db/10)，−inf dB → 线性 0（零功率口径；dB 极负致线性下溢
  同样得 0，计入退化判定）；
- 功率分量取线性域总和：P_noise 用总和口径（噪声 bin 线性功率总和，非
  均值×bin 数），P_signal/P_interference 同；
- 带归属：闭区间 [lo, hi] 判定，优先级 信号带 > 干扰带 > 噪声（其余 bin）；
- 防泄漏 guard：信号带/干扰带各自的带内候选 bin 按频率排序后掐头去尾各
  edge_guard_bins 个；被 guard 排除的边界 bin 不计入任何功率和（测量 guard
  band 惯例——边界泄漏区不污染信号/噪声/干扰任一估计），计入跳过桶；
- 可用性：信号带零 bin（guard 排空/频谱无覆盖/无数据）→ available=False
  不抛；全谱零功率 → available=False 且 degenerate=True；分母为零（纯信号、
  噪声/干扰零功率）→ snr_db=+inf（数学口径），available=True；
- 坏数据：power_db 为 NaN 或 +inf、freq_mhz 非有限实数、bin 非 dict/缺键/
  值非实数 → 该 bin 跳过（n_invalid_bins 计数），不参与任何归属与功率和；
- 计数不变式：n_signal+n_noise+n_interference+n_skipped == len(power_bins)，
  其中 n_skipped = n_guard + n_invalid。
"""
from __future__ import annotations

import math
from numbers import Integral, Real

__all__ = ["estimate_snr"]

_DEFAULT_EDGE_GUARD_BINS = 2


def _band(value, name: str) -> tuple[float, float]:
    """校验 (lo, hi) 频带：二元组、lo/hi 有限实数（拒 bool）、lo < hi。"""
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f"split_params[{name!r}] 必须为 (lo, hi) 二元组: {value!r}")
    bounds = []
    for tag, raw in zip(("lo", "hi"), value):
        if isinstance(raw, bool) or not isinstance(raw, Real):
            raise ValueError(f"split_params[{name!r}].{tag} 必须为有限实数: {raw!r}")
        num = float(raw)
        if not math.isfinite(num):
            raise ValueError(f"split_params[{name!r}].{tag} 必须为有限实数（拒 NaN/inf）: {raw!r}")
        bounds.append(num)
    lo, hi = bounds
    if lo >= hi:
        raise ValueError(f"split_params[{name!r}] 须 lo < hi（闭区间非空）: ({lo}, {hi})")
    return lo, hi


def _guard(value) -> int:
    """校验 edge_guard_bins：非负 int（拒 bool/浮点/负数）。"""
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) < 0:
        raise ValueError(f"split_params['edge_guard_bins'] 必须为非负 int: {value!r}")
    return int(value)


def _parse_bin(entry) -> tuple[float | None, float | None]:
    """单 bin 解析 → (freq, 线性功率)；坏样本返回 (None, None)（计跳过）。

    坏样本口径：非 dict、缺 'freq_mhz'/'power_db'、值非实数（拒 bool）、
    频率非有限、power_db 为 NaN 或 +inf。−inf dB 合法（线性 0，零功率）。
    """
    if not isinstance(entry, dict):
        return None, None
    freq_raw = entry.get("freq_mhz")
    power_raw = entry.get("power_db")
    for raw in (freq_raw, power_raw):
        if raw is None or isinstance(raw, bool) or not isinstance(raw, Real):
            return None, None
    freq = float(freq_raw)
    power_db = float(power_raw)
    if not math.isfinite(freq):
        return None, None
    if math.isnan(power_db) or power_db == math.inf:
        return None, None
    return freq, 10.0 ** (power_db / 10.0)  # −inf dB → 0.0


def _split_guard(candidates: list, guard: int) -> tuple[list, list]:
    """带内候选（已按频率升序）掐头去尾各 guard 个 → (保留, guard 排除)。

    候选数 ≤ 2·guard 时全部落入 guard 区（保留为空），不重复计数。
    """
    if guard <= 0 or not candidates:
        return list(candidates), []
    lo = guard
    hi = max(guard, len(candidates) - guard)
    return candidates[lo:hi], candidates[:lo] + candidates[hi:]


def estimate_snr(power_bins: list, split_params: dict) -> dict:
    """公式(4) SNR 计算：SNR_dB = 10·log10(P_signal/(P_noise+P_interference))。

    输入:
        power_bins: [{'freq_mhz': float, 'power_db': float}] 功率谱 bin（dB 口径）；
        split_params: {
            'signal_band': (lo, hi)           信号所在带（闭区间，MHz）；
            'interference_band': (lo, hi)|None 干扰带，None=无干扰（缺省同 None）；
            'edge_guard_bins': int = 2        带边界排除 bin 数（防泄漏）。
        }
    归属/口径:
        信号带内 bin（guard 截取后）归信号；干扰带内先剔除信号归属再 guard 截取
        （重叠 bin 归信号）；其余为噪声。各 P_* 为对应 bin 的线性功率总和
        （dB→10**(db/10)），SNR 取 10·log10(P_signal/(P_noise+P_interference))。
    输出:
        {'snr_db': float|None,                     分母零→+inf；不可用→None
         'p_signal_db'/'p_noise_db'/'p_interference_db': float|None（零功率→None）,
         'n_signal_bins'/'n_noise_bins'/'n_interference_bins': int,
         'n_skipped_bins'/'n_guard_bins'/'n_invalid_bins': int（skipped=guard+invalid）,
         'available': bool, 'degenerate': bool, 'reason': str|None}
        计数不变式：n_signal+n_noise+n_interference+n_skipped == len(power_bins)。
    错误:
        ValueError：power_bins 非 list；split_params 非 dict；signal_band 缺失/
        非二元组/lo>=hi/边界非有限实数；interference_band 非 None 且形状错；
        edge_guard_bins 非非负 int（拒 bool/浮点）。
    不可用（不抛）:
        信号带零 bin → available=False（reason='signal_band_empty'）；
        全谱零功率（全 −inf dB 或线性全 0）→ available=False、degenerate=True
        （reason='degenerate_spectrum'）；信号带有 bin 但零功率（谱非全零）→
        available=False（reason='zero_signal_power'）；坏 bin 一律跳过计数。
    """
    if not isinstance(power_bins, list):
        raise ValueError(f"power_bins 必须为 list[dict]: {type(power_bins).__name__}")
    if not isinstance(split_params, dict):
        raise ValueError(f"split_params 必须为 dict: {type(split_params).__name__}")
    if "signal_band" not in split_params:
        raise ValueError("split_params 缺 'signal_band'（(lo, hi) 信号带）")
    sig_lo, sig_hi = _band(split_params["signal_band"], "signal_band")
    interference_band = split_params.get("interference_band")
    if interference_band is None:
        int_lo = int_hi = None
    else:
        int_lo, int_hi = _band(interference_band, "interference_band")
    guard = _guard(split_params.get("edge_guard_bins", _DEFAULT_EDGE_GUARD_BINS))

    valid = []  # (原始下标, freq_mhz, 线性功率) —— 坏 bin 已跳过
    n_invalid = 0
    for index, entry in enumerate(power_bins):
        freq, linear = _parse_bin(entry)
        if freq is None:
            n_invalid += 1
        else:
            valid.append((index, freq, linear))

    sig_cand = sorted((v for v in valid if sig_lo <= v[1] <= sig_hi), key=lambda v: v[1])
    sig_members, sig_guarded = _split_guard(sig_cand, guard)

    if int_lo is None:
        int_members, int_guarded = [], []
    else:
        sig_claimed = {v[0] for v in sig_members}
        int_cand = sorted(
            (v for v in valid if int_lo <= v[1] <= int_hi and v[0] not in sig_claimed),
            key=lambda v: v[1],
        )
        int_members, int_guarded = _split_guard(int_cand, guard)

    claimed = {v[0] for v in sig_members} | {v[0] for v in int_members}
    guarded = {v[0] for v in sig_guarded} | {v[0] for v in int_guarded}
    # guard 排除的边界 bin 不计入任何功率和（防泄漏），只进跳过桶
    noise_members = [v for v in valid if v[0] not in claimed and v[0] not in guarded]

    p_signal = math.fsum(v[2] for v in sig_members)
    p_interference = math.fsum(v[2] for v in int_members)
    p_noise = math.fsum(v[2] for v in noise_members)
    total_power = math.fsum(v[2] for v in valid)  # 含 guard 排除 bin（谱整体退化判定）

    n_guard = len(sig_guarded) + len(int_guarded)
    degenerate = bool(valid) and total_power <= 0.0
    n_signal = len(sig_members)

    if degenerate:
        available, snr_db, reason = False, None, "degenerate_spectrum"
    elif n_signal == 0:
        available, snr_db, reason = False, None, "signal_band_empty"
    elif p_signal <= 0.0:
        available, snr_db, reason = False, None, "zero_signal_power"
    else:
        available, reason = True, None
        denominator = p_noise + p_interference
        snr_db = (
            math.inf
            if denominator <= 0.0
            else 10.0 * math.log10(p_signal / denominator)
        )

    def _db(power: float) -> float | None:
        return 10.0 * math.log10(power) if power > 0.0 else None

    return {
        "snr_db": snr_db,
        "p_signal_db": _db(p_signal),
        "p_noise_db": _db(p_noise),
        "p_interference_db": _db(p_interference),
        "n_signal_bins": n_signal,
        "n_noise_bins": len(noise_members),
        "n_interference_bins": len(int_members),
        "n_skipped_bins": n_invalid + n_guard,
        "n_guard_bins": n_guard,
        "n_invalid_bins": n_invalid,
        "available": available,
        "degenerate": degenerate,
        "reason": reason,
    }
