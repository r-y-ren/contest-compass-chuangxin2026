"""自漏耦合系数标定与监测读数扣除（未扣除标注）——重写规约与签名意图详见 fn_docs/responsibility.md。

双模式：
- 标定会话（session_data 非 None）：校验逐频点 CH1→CH2 耦合测点并写出泄漏标定表 JSON；
- 扣除请求（request 非 None）：按频点线性插值取耦合系数并回加到监测读数上；
  无标定表时不抛异常，返回 corrected_db=None 并附 note 标注（无标定继续 + 标注）。
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

_TABLE_KIND = "leakage_coupling_table"
_MIN_POINTS = 3
_NO_TABLE_NOTE = "未扣除（无标定表）"
# 会话数据中耦合测点列表的候选键名（按优先级）
_DATA_KEYS = ("points", "coupling_data", "data", "samples", "measurements")


class CalibrationWarn(Warning):
    """标定样本不足（<3 点）等不阻断后续流程的警告性异常（表仍会写出）。"""


def _require_finite_number(value: Any, label: str) -> float:
    """校验 value 为有限数值（拒绝 bool/字符串/NaN/Inf），返回 float。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} 必须为数值，实际类型为 {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} 必须为有限数值，实际为 {number}")
    return number


def _validate_points(raw_points: Any) -> list[dict]:
    """校验耦合测点列表：有限非 bool 数值、频点>0、频点不重复；返回按频点升序的表。"""
    if not isinstance(raw_points, (list, tuple)):
        raise ValueError("耦合测点数据必须是 [{'freq_mhz': float, 'coupling_db': float}] 列表")
    table: list[dict] = []
    seen_freqs: set[float] = set()
    for idx, item in enumerate(raw_points):
        if not isinstance(item, dict):
            raise ValueError(f"第 {idx} 个测点必须为 dict，实际类型为 {type(item).__name__}")
        if "freq_mhz" not in item or "coupling_db" not in item:
            raise ValueError(f"第 {idx} 个测点缺少 freq_mhz/coupling_db 字段")
        freq = _require_finite_number(item["freq_mhz"], f"第 {idx} 个测点 freq_mhz")
        coupling = _require_finite_number(item["coupling_db"], f"第 {idx} 个测点 coupling_db")
        if freq <= 0:
            raise ValueError(f"第 {idx} 个测点 freq_mhz 必须大于 0，实际为 {freq}")
        if freq in seen_freqs:
            raise ValueError(f"频点重复：{freq} MHz")
        seen_freqs.add(freq)
        table.append({"freq_mhz": freq, "coupling_db": coupling})
    table.sort(key=lambda point: point["freq_mhz"])
    return table


def _write_table(out_path: str, table: list[dict], sufficient: bool) -> None:
    """把标定表写为 JSON；样本不足时以 status=insufficient 标注。"""
    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    payload = {
        "kind": _TABLE_KIND,
        "status": "ok" if sufficient else "insufficient",
        "points": len(table),
        "freq_unit": "MHz",
        "coupling_unit": "dB",
        "table": table,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def _calibrate_session(session_data: Any) -> dict:
    """模式一：校验耦合测点并写出泄漏标定表。"""
    if not isinstance(session_data, dict):
        raise ValueError(f"session_data 必须为 dict，实际类型为 {type(session_data).__name__}")
    out_path = session_data.get("out_path")
    if not isinstance(out_path, (str, os.PathLike)) or not str(out_path).strip():
        raise ValueError("session_data['out_path'] 必须为非空路径")
    raw_points = None
    for key in _DATA_KEYS:
        if session_data.get(key) is not None:
            raw_points = session_data[key]
            break
    if raw_points is None:
        raise ValueError(f"session_data 缺少耦合测点数据（候选键：{'/'.join(_DATA_KEYS)}）")
    table = _validate_points(raw_points)
    sufficient = len(table) >= _MIN_POINTS
    _write_table(str(out_path), table, sufficient)
    if not sufficient:
        raise CalibrationWarn(
            f"标定测点不足（{len(table)} < {_MIN_POINTS}），标定表已写出并标注 insufficient：{out_path}"
        )
    return {"mode": "calibrate", "table_path": str(out_path), "points": len(table)}


def _lookup_coupling(table: list[dict], freq: float) -> tuple[float, bool]:
    """按频点线性插值取耦合系数；表外频点取最近端点值并置 extrapolated=True。"""
    freqs = [point["freq_mhz"] for point in table]
    couplings = [point["coupling_db"] for point in table]
    if freq < freqs[0]:
        return couplings[0], True
    if freq > freqs[-1]:
        return couplings[-1], True
    for i in range(len(freqs) - 1):
        f0, f1 = freqs[i], freqs[i + 1]
        if f0 <= freq <= f1:
            c0, c1 = couplings[i], couplings[i + 1]
            if f1 == f0:
                return c0, False
            fraction = (freq - f0) / (f1 - f0)
            return c0 + (c1 - c0) * fraction, False
    return couplings[-1], False


def _load_table(table_path: str) -> list[dict]:
    """读取并轻校验标定表 JSON，返回按频点升序的测点列表；不可用则抛 ValueError。"""
    with open(table_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict) or not isinstance(payload.get("table"), (list, tuple)):
        raise ValueError("标定表 JSON 结构无效（缺少 table 列表）")
    return _validate_points(payload["table"])


def _subtract_request(request: Any) -> dict:
    """模式二：查表插值扣除自漏耦合；无标定表则不扣除并标注。"""
    if not isinstance(request, dict):
        raise ValueError(f"request 必须为 dict，实际类型为 {type(request).__name__}")
    measured_db = _require_finite_number(request.get("measured_db"), "request.measured_db")
    freq_mhz = _require_finite_number(request.get("freq_mhz"), "request.freq_mhz")
    if freq_mhz <= 0:
        raise ValueError(f"request.freq_mhz 必须大于 0，实际为 {freq_mhz}")
    table_path = request.get("table_path")
    if not isinstance(table_path, (str, os.PathLike)) or not str(table_path).strip():
        return {"mode": "subtract", "corrected_db": None, "note": _NO_TABLE_NOTE}
    if not os.path.isfile(str(table_path)):
        return {"mode": "subtract", "corrected_db": None, "note": _NO_TABLE_NOTE}
    try:
        table = _load_table(str(table_path))
    except (OSError, ValueError, TypeError, KeyError):
        return {"mode": "subtract", "corrected_db": None, "note": "未扣除（标定表无效）"}
    if not table:
        return {"mode": "subtract", "corrected_db": None, "note": "未扣除（标定表为空）"}
    coupling_db, extrapolated = _lookup_coupling(table, freq_mhz)
    return {
        "mode": "subtract",
        "coupling_db": coupling_db,
        "corrected_db": measured_db + coupling_db,
        "extrapolated": extrapolated,
    }


def calibrate_leakage(session_data=None, request=None) -> dict:
    """自漏耦合系数标定与监测读数扣除（未扣除标注）。

    模式一（标定会话）：session_data = {'points': [{'freq_mhz': float, 'coupling_db': float}, ...],
    'out_path': <JSON 表输出路径>}。校验（有限非 bool 数值、频点>0、频点不重复）通过后写出
    泄漏标定表，返回 {'mode': 'calibrate', 'table_path': …, 'points': N}；测点不足 3 个时表仍
    写出（标注 insufficient）并抛 CalibrationWarn；数据非法抛 ValueError。

    模式二（扣除请求）：request = {'table_path': …, 'measured_db': …, 'freq_mhz': …}。按频点
    线性插值取耦合系数，返回 {'mode': 'subtract', 'coupling_db': …, 'corrected_db': measured_db
    + coupling_db, 'extrapolated': bool}（频点在表外取最近端点值并置 extrapolated=True）；
    标定表缺失时不抛异常，返回 {'mode': 'subtract', 'corrected_db': None, 'note': '未扣除（无标定表）'}。

    两模式都为 None 时抛 ValueError；两者同时提供时以标定会话（session_data）优先。
    """
    if session_data is None and request is None:
        raise ValueError("必须提供 session_data（标定会话）或 request（扣除请求）之一")
    if session_data is not None:
        return _calibrate_session(session_data)
    return _subtract_request(request)
