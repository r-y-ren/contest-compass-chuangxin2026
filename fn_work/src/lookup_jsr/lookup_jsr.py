"""增益档→估计注入功率→JSR 换算（缺表拒绝）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math

from src.shared.load_calibration_table import CalibrationError, load_calibration_table

__all__ = ["lookup_jsr"]

_PLACEHOLDER_NOTE = "标定表为【待实测】占位，JSR 场景不可用"
_MISSING_TABLE_NOTE = "先运行 build_gain_calibration 生成标定表"


def _freq_mhz(freq_hz) -> float | None:
    """频率仅作记录口径（Hz→MHz）：非法/非有限/超出 float 可表示范围（超大 int）
    一律记 None，不参与 gain 表查询，绝不抛出。"""
    if isinstance(freq_hz, bool) or not isinstance(freq_hz, (int, float)):
        return None
    try:
        value = float(freq_hz) / 1e6
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def _is_valid_signal(value) -> bool:
    """链路信号功率必须为有限非 bool 数值（含可转 float），否则 JSR 减法无意义。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _parse_step(value) -> float | None:
    """档位归一为数值：bool 与不可解析对象（None/容器/未知档名/超出 float 范围）不算数值档。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except OverflowError:
            return None
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _nearest_key(entries, step_number: float):
    """在 entries 键中找数值最近邻档；平手取数值更小档保证确定性。无可解析键返回 None。"""
    best_rank = None
    best_key = None
    for key in entries:
        key_number = _parse_step(key)
        if key_number is None:
            continue
        rank = (abs(key_number - step_number), key_number)
        if best_rank is None or rank < best_rank:
            best_rank, best_key = rank, key
    return best_key


def lookup_jsr(gain_step, freq_hz: float, signal_power_dbm: float, config: dict) -> dict:
    """由（增益档, 频率, 链路信号功率）查 gain 标定表估计注入功率并换算 JSR。

    一切异常转 status 返回，不抛出：
    - invalid_signal：signal_power_dbm 为 NaN/inf/bool/非数值（先于查表校验）；
    - missing_table：load_calibration_table 抛 CalibrationError（目录缺失/文件损坏等）；
    - unavailable：占位表（placeholder=True，缺文件按占位语义返回）或 entries 为空；
    - invalid_gain_step：档位既不精确命中也无法数值最近邻（None/容器/bool/未知档名）；
    - ok：{gain_step, freq_mhz, injected_power_dbm, signal_power_dbm, jsr_db, nearest,
           matched_gain_step}，档位不在表内时取数值最近邻档并附 extrapolated_note；
      jsr_db = injected_power_dbm − signal_power_dbm（信号强于干扰时为负 dB）。
    频率仅供记录（freq_mhz），不参与 gain 表查询。
    """
    base = {"gain_step": gain_step, "freq_mhz": _freq_mhz(freq_hz)}

    if not _is_valid_signal(signal_power_dbm):
        return {
            **base,
            "status": "invalid_signal",
            "signal_power_dbm": signal_power_dbm,
            "note": "链路信号功率非法（NaN/inf/bool/非数值），JSR 换算拒绝",
        }

    try:
        table = load_calibration_table("gain", config, placeholder=True)
    except CalibrationError as exc:
        return {
            **base,
            "status": "missing_table",
            "signal_power_dbm": float(signal_power_dbm),
            "note": f"标定表缺失/不可用（{exc}）：{_MISSING_TABLE_NOTE}",
        }

    entries = table.get("entries") or {}
    if table.get("placeholder"):
        return {
            **base,
            "status": "unavailable",
            "signal_power_dbm": float(signal_power_dbm),
            "note": _PLACEHOLDER_NOTE,
        }
    if not entries:
        return {
            **base,
            "status": "unavailable",
            "signal_power_dbm": float(signal_power_dbm),
            "note": "标定表条目为空（未实测写入），JSR 场景不可用",
        }

    signal = float(signal_power_dbm)

    if isinstance(gain_step, str) and gain_step in entries:
        matched, nearest = gain_step, False
    else:
        step_number = _parse_step(gain_step)
        if step_number is None:
            return {
                **base,
                "status": "invalid_gain_step",
                "signal_power_dbm": signal,
                "note": f"增益档 {gain_step!r} 不在标定表内且无法按数值最近邻匹配（bool/None/容器/未知档名）",
            }
        matched = _nearest_key(entries, step_number)
        if matched is None:
            return {
                **base,
                "status": "invalid_gain_step",
                "signal_power_dbm": signal,
                "note": "标定表内不存在可解析为数值的档位键，无法最近邻匹配",
            }
        nearest = abs(_parse_step(matched) - step_number) > 0.0

    try:
        injected = float(entries[matched]["power_dbm"])
    except Exception as exc:  # 兜底：规约要求一切异常转 status
        return {
            **base,
            "status": "error",
            "signal_power_dbm": signal,
            "matched_gain_step": matched,
            "note": f"lookup_jsr 内部错误: {exc}",
        }

    result = {
        **base,
        "status": "ok",
        "signal_power_dbm": signal,
        "injected_power_dbm": injected,
        "jsr_db": injected - signal,
        "matched_gain_step": matched,
        "nearest": nearest,
    }
    if nearest:
        result["extrapolated_note"] = (
            f"增益档 {gain_step!r} 不在标定表内，按数值最近邻档 {matched!r} 估计（外推标注）"
        )
    return result
