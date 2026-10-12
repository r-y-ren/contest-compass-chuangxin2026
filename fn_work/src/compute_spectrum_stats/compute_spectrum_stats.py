"""频谱监测窗口统计行（SNR/JSR 反演/平坦度/底噪口径）——B10 顶层（R17）。

调用方：record_run_streams（随采随算）；build_report（图谱数据）。
重写规约与签名意图详见 fn_docs/responsibility.md R17，落地口径：

- reference 在位（window['reference'] 为 dict，缺省回落第二参数）→ mode='full'：
  estimate_snr（guard 默认 2，reference['edge_guard_bins'] 可透传）出 SNR 口径
  字段整块合入行；JSR 反演 = P_interference/P_signal 线性→dB（即
  p_interference_db − p_signal_db），附 'jsr_db'；
- JSR 交叉口径：reference 含 'signal_power_db'（已知信号功率，有限实数）时
  jsr = p_interference_db − signal_power_db（'jsr_source'='signal_power'，
  同谱下与反演口径一致）；否则 'jsr_source'='inverted'；
- flatness_band 在位 → check_flatness（判据默认 4 dB，
  reference['flatness_limit_db'] 可透传），结果键幂等加前缀 flatness_ 合入
  （'flatness_db' 已带前缀保持原名，'pass'→'flatness_pass' 等）；
- 自漏扣除：window 含 'leakage_table_path' 时按频点扣除（corrected = measured_db
  + coupling_db，calibrate_leakage 的读表/插值语义；每次调用表只读一次），
  扣除后谱进统计；表缺失/无效 → 读数原样保留且 'leak_corrected'=False（不抛）；
- 底噪口径：无 reference（缺省/None）→ mode='power_only'，只出
  {'p_total_db': 全谱线和, 'peak_db'/'peak_at_mhz', 'noise_floor_db': 全谱
  20 分位（近似底噪）, 'available': bool, 'mode', 'note':
  '无参考参数——仅功率统计'}；
- 一切不抛：子函数 available=False / ValueError（参考带形状错等）→ 对应块
  以不可用标记透传；仅 window 形状错（非 dict / 缺 'bins' / bins 非 list）
  抛 ValueError。统计行含 'timestamp_ms' 透传与 'invalid_bins'（坏 bin 计数，
  口径同 estimate_snr：非 dict/缺键/非实数/频率非有限/power NaN 或 +inf）。
"""
from __future__ import annotations

import math
import os
from numbers import Real

from .estimate_snr import estimate_snr
from .check_flatness import check_flatness
import src.calibrate_leakage.calibrate_leakage as _leakage_impl

__all__ = ["compute_spectrum_stats"]

# 无参考时的底噪近似分位（全谱 20 分位 ≈ 底噪，避开信号/干扰峰抬高估计）。
_NOISE_FLOOR_PERCENTILE = 0.2
_NO_REFERENCE_NOTE = "无参考参数——仅功率统计"
_DEFAULT_FLATNESS_LIMIT_DB = 4.0


def _parse_bin(entry) -> tuple[float | None, float | None]:
    """单 bin 解析 → (freq_mhz, power_db)；坏样本 (None, None)。

    与 estimate_snr 同口径：非 dict / 缺 'freq_mhz'/'power_db' / 非实数（拒
    bool）/ 频率非有限 / power_db 为 NaN 或 +inf → 坏样本；−inf dB 合法（零功率）。
    """
    if not isinstance(entry, dict):
        return None, None
    freq_raw = entry.get("freq_mhz")
    power_raw = entry.get("power_db")
    for raw in (freq_raw, power_raw):
        if raw is None or isinstance(raw, bool) or not isinstance(raw, Real):
            return None, None
    freq, power_db = float(freq_raw), float(power_raw)
    if not math.isfinite(freq) or math.isnan(power_db) or power_db == math.inf:
        return None, None
    return freq, power_db


def _apply_leakage_correction(bins: list, table_path: str) -> tuple[list, bool]:
    """逐频点自漏扣除 → (扣除后 bins, leak_corrected)；标定表每次调用只读一次。

    仅对可扣除的 bin（dict、频率有限且 >0、power_db 有限实数）尝试扣除：
    corrected = measured_db + coupling(freq)（calibrate_leakage 扣除请求的读表/
    插值语义，表单次读入后逐频点插值复用）；表缺失/无效（读表失败）→ 读数
    原样保留。leak_corrected = 至少一个可扣 bin 且全部扣除成功（标定表按
    路径整体生效/失效，逐 bin 不偏科）。输入 bins 不被原地改动。
    """
    if os.path.isfile(table_path):
        try:
            coupling_table = _leakage_impl._load_table(table_path)
        except (OSError, ValueError, TypeError, KeyError):
            coupling_table = None
    else:
        coupling_table = None
    corrected_bins: list = []
    n_attempted = 0
    n_corrected = 0
    for entry in bins:
        freq, power_db = _parse_bin(entry)
        if freq is None or freq <= 0.0 or not math.isfinite(power_db):
            # −inf dB（零功率）扣除前后线性功率同为 0，无需扣除
            corrected_bins.append(entry)
            continue
        n_attempted += 1
        corrected: float | None = None
        if coupling_table is not None:
            candidate = power_db + _leakage_impl._lookup_coupling(coupling_table, freq)[0]
            if math.isfinite(candidate):
                corrected = candidate
        if corrected is None:
            corrected_bins.append(entry)
        else:
            n_corrected += 1
            corrected_bins.append({"freq_mhz": freq, "power_db": corrected})
    return corrected_bins, n_attempted > 0 and n_corrected == n_attempted


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """线性插值分位（numpy 'linear' 口径）：rank = fraction·(n−1)，端点间内插。"""
    n = len(sorted_values)
    position = fraction * (n - 1)
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return sorted_values[lo]
    weight = position - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * weight


def _power_only_metrics(bins: list) -> dict:
    """无参考底噪口径：全谱线和 / 峰值定位 / 20 分位近似底噪。

    峰值与分位取功率有限（非 ±inf/NaN）的 bin；−inf dB bin 计入谱（线性 0）
    但不进峰值/分位；无任何可用 bin → available=False（metrics 全 None）。
    """
    total_linear = 0.0
    finite_powers: list[float] = []
    peak_db: float | None = None
    peak_at_mhz: float | None = None
    n_invalid = 0
    n_valid = 0
    for entry in bins:
        freq, power_db = _parse_bin(entry)
        if freq is None:
            n_invalid += 1
            continue
        n_valid += 1
        if math.isfinite(power_db):
            finite_powers.append(power_db)
            if peak_db is None or power_db > peak_db:
                peak_db, peak_at_mhz = power_db, freq
        if power_db != -math.inf:
            total_linear += 10.0 ** (power_db / 10.0)
    available = bool(finite_powers)
    if not n_valid:
        reason = "empty_window"
    elif not available:
        reason = "degenerate_spectrum"
    else:
        reason = None
    finite_powers.sort()
    return {
        "p_total_db": 10.0 * math.log10(total_linear) if total_linear > 0.0 else None,
        "peak_db": peak_db,
        "peak_at_mhz": peak_at_mhz,
        "noise_floor_db": _percentile(finite_powers, _NOISE_FLOOR_PERCENTILE) if available else None,
        "available": available,
        "reason": reason,
    }


def _snr_unavailable(reason: str, n_invalid: int) -> dict:
    """estimate_snr 不可调用（参考带形状错等）时的整块兜底（available=False 透传）。"""
    return {
        "snr_db": None,
        "p_signal_db": None,
        "p_noise_db": None,
        "p_interference_db": None,
        "n_signal_bins": 0,
        "n_noise_bins": 0,
        "n_interference_bins": 0,
        "n_skipped_bins": n_invalid,
        "n_guard_bins": 0,
        "n_invalid_bins": n_invalid,
        "available": False,
        "degenerate": False,
        "reason": reason,
    }


def _flatness_unavailable(reason: str) -> dict:
    """check_flatness 不可调用（flatness_band 缺失/形状错）时的兜底块。"""
    return {
        "flatness_db": None,
        "available": False,
        "n_bins": 0,
        "reason": reason,
    }


def _flatness_prefixed(flatness_result: dict) -> dict:
    """check_flatness 结果键幂等加前缀 flatness_（'flatness_db' 保持原名）。

    check_flatness 成功分支不携带 'available' 键，此处统一补 available=True，
    保证统计行上 flatness_available 恒在。
    """
    normalized = dict(flatness_result)
    normalized.setdefault("available", True)
    return {
        (key if key.startswith("flatness_") else f"flatness_{key}"): value
        for key, value in normalized.items()
    }


def compute_spectrum_stats(window: dict, reference: dict | None = None) -> dict:
    """对监测数据窗口出统计行：SNR（公式(4)）/JSR 反演/平坦度/底噪口径。

    输入:
        window: {'bins': [{'freq_mhz': float, 'power_db': float}, ...],
                 'timestamp_ms': 透传盖戳,
                 'reference': {'signal_band': (lo, hi),
                               'interference_band': (lo, hi)|None,
                               'flatness_band': (lo, hi)|None,
                               'edge_guard_bins': int（缺省 2）,
                               'flatness_limit_db': float（缺省 4.0）,
                               'signal_power_db': float|None（已知信号功率）}|None,
                 'leakage_table_path': 自漏标定表 JSON 路径（可选）}
        reference: window 未携带 'reference' 键时的兜底参考参数（同上形状）。
    输出:
        基础行 {'timestamp_ms', 'mode': 'full'|'power_only',
        'leak_corrected': bool, 'invalid_bins': int}；
        full 模式追加 **estimate_snr 结果（snr_db/p_*_db/n_*_bins/available/
        degenerate/reason 等）、**flatness_ 前缀平坦度块、'jsr_db'（反演或
        signal_power 交叉口径）与 'jsr_source'；
        power_only 模式只追加 {'p_total_db', 'peak_db', 'peak_at_mhz',
        'noise_floor_db', 'available', 'reason', 'note': 无参考标注}。
    错误:
        window 非 dict / 缺 'bins' / bins 非 list → ValueError；
        其余（子函数不可用、坏 bin、表缺失）一律不抛，以 available=False /
        leak_corrected=False / invalid_bins 计数透传。
    """
    if not isinstance(window, dict):
        raise ValueError(f"window 必须为 dict: {type(window).__name__}")
    if "bins" not in window:
        raise ValueError("window 缺 'bins'（监测功率谱 bin 列表）")
    bins = window["bins"]
    if not isinstance(bins, list):
        raise ValueError(f"window['bins'] 必须为 list[dict]: {type(bins).__name__}")

    reference = window.get("reference", reference)  # window 内优先，缺省回落第二参数
    timestamp_ms = window.get("timestamp_ms")

    table_path = window.get("leakage_table_path")
    if table_path is not None and str(table_path).strip():
        spec_bins, leak_corrected = _apply_leakage_correction(bins, str(table_path))
    else:
        spec_bins, leak_corrected = bins, False

    row: dict = {
        "timestamp_ms": timestamp_ms,
        "leak_corrected": leak_corrected,
        "invalid_bins": sum(1 for entry in spec_bins if _parse_bin(entry)[0] is None),
    }

    if not isinstance(reference, dict):
        # ③ 底噪口径：无参考 → 仅功率统计并标注
        metrics = _power_only_metrics(spec_bins)
        row["mode"] = "power_only"
        row.update(metrics)
        row["note"] = _NO_REFERENCE_NOTE
        return row

    row["mode"] = "full"

    # ① SNR 口径字段（guard 默认 2，透传 reference['edge_guard_bins']）
    split_params: dict = {}
    if "signal_band" in reference:
        split_params["signal_band"] = reference["signal_band"]
    if reference.get("interference_band") is not None:
        split_params["interference_band"] = reference["interference_band"]
    if "edge_guard_bins" in reference:
        split_params["edge_guard_bins"] = reference["edge_guard_bins"]
    try:
        snr_result = estimate_snr(spec_bins, split_params)
    except ValueError as exc:
        snr_result = _snr_unavailable(f"invalid_reference: {exc}", row["invalid_bins"])
    row.update(snr_result)

    # 平坦度块（flatness_band 在位才核验）；band 与判据值谁非法以 reason 前缀区分
    # （invalid_flatness_band / invalid_flatness_limit）——判据非法时换默认判据重试
    # 可算即归因于判据，仍抛则归因于带形状。
    flatness_band = reference.get("flatness_band")
    if flatness_band is None:
        flatness_result = _flatness_unavailable("no_flatness_band")
    else:
        limit_db = reference.get("flatness_limit_db")
        effective_limit = _DEFAULT_FLATNESS_LIMIT_DB if limit_db is None else limit_db
        try:
            flatness_result = check_flatness(spec_bins, flatness_band, effective_limit)
        except ValueError as exc:
            if limit_db is not None:
                try:
                    check_flatness(spec_bins, flatness_band, _DEFAULT_FLATNESS_LIMIT_DB)
                except ValueError:
                    flatness_result = _flatness_unavailable(f"invalid_flatness_band: {exc}")
                else:
                    flatness_result = _flatness_unavailable(f"invalid_flatness_limit: {exc}")
            else:
                flatness_result = _flatness_unavailable(f"invalid_flatness_band: {exc}")
    row.update(_flatness_prefixed(flatness_result))

    # ①/④ JSR：反演口径 P_interference/P_signal → dB；已知 signal_power_db
    # 时用交叉口径 jsr = p_interference_db − signal_power_db（同谱下两口径一致）
    p_interference_db = snr_result.get("p_interference_db")
    jsr_db: float | None = None
    jsr_source: str | None = None
    if p_interference_db is not None:
        known = reference.get("signal_power_db")
        if (
            known is not None
            and not isinstance(known, bool)
            and isinstance(known, Real)
            and math.isfinite(float(known))
        ):
            jsr_db = p_interference_db - float(known)
            jsr_source = "signal_power"
        else:
            p_signal_db = snr_result.get("p_signal_db")
            if p_signal_db is not None:
                jsr_db = p_interference_db - p_signal_db
            else:
                jsr_db = math.inf  # 信号带零功率 vs 干扰在位 → +inf（数学口径）
            jsr_source = "inverted"
    row["jsr_db"] = jsr_db
    row["jsr_source"] = jsr_source
    return row
