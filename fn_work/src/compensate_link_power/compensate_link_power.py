"""公式(6) 全链路补偿（无表频点标不可信）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import bisect
import math
from collections.abc import Mapping

from src.shared.load_calibration_table import CalibrationError, load_calibration_table

__all__ = ["compensate_link_power"]

# 可信度取值：ok=双表区间内；extrapolated=表外最近端点；no_table=表缺失/占位/损坏；invalid=测量值非法
_OK = "ok"
_EXTRAPOLATED = "extrapolated"
_NO_TABLE = "no_table"
_INVALID = "invalid"

# 表名 → 输出字段名（公式(6) 的两个补偿项 L_link 与 C_ant）
_TABLE_FIELDS = (("link_loss", "l_link"), ("antenna", "c_ant"))


def _is_valid_number(value: object) -> bool:
    """有限非 bool 数值（频点/测量值/表值的统一合法性口径）。"""
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _make_ladder(entries: object) -> tuple[list[float], list[float]] | None:
    """entries（频点 MHz→dB）规范化为升序 (freqs, values) 平行列表；无可信条目 → None（视同缺表）。

    显式传入的 entries 未经文件加载校验，此处逐条剔除非法键值（bool/NaN/inf/非数值，数值字符串键宽容解析）。
    """
    pairs: dict[float, float] = {}
    if isinstance(entries, Mapping):  # 兼容文件加载返回的 MappingProxyType 只读视图
        for key, value in entries.items():
            if isinstance(key, str):
                try:
                    key = float(key)
                except ValueError:
                    continue
            if not _is_valid_number(key) or not _is_valid_number(value):
                continue
            pairs.setdefault(float(key), float(value))
    if not pairs:
        return None
    freqs = sorted(pairs)
    return freqs, [pairs[freq] for freq in freqs]


def _interp(ladder: tuple[list[float], list[float]], freq: float) -> tuple[float, str]:
    """阶梯上取 freq 的 dB：区间内（含端点精确命中）线性插值；区间外取最近端点。返回 (dB, ok|extrapolated)。"""
    freqs, values = ladder
    i = bisect.bisect_left(freqs, freq)
    if i < len(freqs) and freqs[i] == freq:
        return values[i], _OK
    if i <= 0:  # 低于最低频点 → 最近端点=低端
        return values[0], _EXTRAPOLATED
    if i >= len(freqs):  # 高于最高频点 → 最近端点=高端
        return values[-1], _EXTRAPOLATED
    f_lo, f_hi = freqs[i - 1], freqs[i]
    if f_hi == f_lo:  # 规范化后理论上不会相等，防御性兜底
        return values[i - 1], _OK
    frac = (freq - f_lo) / (f_hi - f_lo)
    return values[i - 1] + (values[i] - values[i - 1]) * frac, _OK


def _resolve_ladders(config: dict, tables: dict | None) -> dict:
    """每张表解析为插值阶梯：显式 tables 逐键优先，其余走 load_calibration_table(placeholder=True)。

    缺表→【待实测】占位视图、表损坏/目录不存在→CalibrationError、entries 全非法 → 一律 None（视同缺表，不抛出）。
    """
    explicit = tables if isinstance(tables, dict) else {}
    ladders: dict = {}
    for name, _field in _TABLE_FIELDS:
        if name in explicit:
            ladders[name] = _make_ladder(explicit[name])
            continue
        try:
            view = load_calibration_table(name, config, placeholder=True)
        except CalibrationError:
            view = None
        if isinstance(view, dict) and not view.get("placeholder"):
            ladders[name] = _make_ladder(view.get("entries"))
        else:
            ladders[name] = None
    return ladders


def _compensate_point(item: object, ladders: dict) -> dict:
    """单点补偿：非法点标 invalid；公式(6) P_actual=P_measured+L_link+C_ant（缺失项不计入）。"""
    freq = p_measured = None
    if isinstance(item, (tuple, list)) and len(item) == 2:
        freq, p_measured = item
    freq_ok = _is_valid_number(freq)
    p_ok = _is_valid_number(p_measured)
    point = {
        "freq_mhz": float(freq) if freq_ok else None,
        "p_measured": float(p_measured) if p_ok else None,
        "l_link": None,
        "c_ant": None,
        "p_actual": None,
        "confidence": _INVALID,
    }
    if not freq_ok or not p_ok:
        return point

    statuses: list[str] = []
    for name, field in _TABLE_FIELDS:
        ladder = ladders.get(name)
        if ladder is None:
            statuses.append(_NO_TABLE)
            continue
        value, status = _interp(ladder, point["freq_mhz"])
        point[field] = value
        statuses.append(status)

    # 可信度阶梯：缺表压过外推，外推压过 ok（表越缺越不可信）
    if _NO_TABLE in statuses:
        point["confidence"] = _NO_TABLE
    elif _EXTRAPOLATED in statuses:
        point["confidence"] = _EXTRAPOLATED
    else:
        point["confidence"] = _OK

    # 公式(6)：未知项（None）不计入，p_actual=测量值+已知补偿项
    p_actual = point["p_measured"]
    if point["l_link"] is not None:
        p_actual += point["l_link"]
    if point["c_ant"] is not None:
        p_actual += point["c_ant"]
    point["p_actual"] = p_actual
    return point


def compensate_link_power(measurements: list, config: dict, tables: dict | None = None) -> list:
    """公式(6) 全链路补偿（无表频点标不可信）——逐点代数和，任何输入不抛出。

    输入: measurements=[(freq_mhz, p_measured_dbm), ...]；
    config={'calibration_dir': ...}（文件加载口径，缺 calibration_dir 回退默认目录）；
    tables={'link_loss': {freq_mhz: dB}, 'antenna': {freq_mhz: dB}} 可显式传表跳过文件加载（逐键优先于文件）。

    输出: 逐点 [{'freq_mhz','p_measured','l_link','c_ant','p_actual','confidence'}]，其中：
    - 'ok'：双表均在覆盖区间内（线性插值，端点精确命中同 ok）；
    - 'extrapolated'：任一在表频点区间外 → 该表取最近端点值；
    - 'no_table'：任一表缺失/【待实测】占位/损坏（CalibrationError）→ 该表贡献记 None，
      p_actual=测量值+已知项（未知项不计）；
    - 'invalid'：频点或测量值非法（NaN/inf/bool/非二元组）→ p_actual=None，不抛出。
    空序列 → []。
    """
    try:
        items = list(measurements)
    except TypeError:
        return []
    ladders = _resolve_ladders(config, tables)
    return [_compensate_point(item, ladders) for item in items]
