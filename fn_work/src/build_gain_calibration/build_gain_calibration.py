"""发射端增益标定表构建与存储（含【待实测】占位）——重写规约与签名意图详见 fn_docs/responsibility.md。

表文件采用 load_calibration_table 可读的规范格式：顶层即 entries
{"<str(gain_step)>": {"power_dbm": float}, ...}——loader 对每个顶层键按 gain
条目校验，写入 name/meta 等信封键会使表不可读，故表名/占位语义由 loader 的
返回视图承载（name/meta/placeholder 字段在视图层，而非表文件内）。
"""
from __future__ import annotations

import json
import math
import os

from .check_monotonicity import check_monotonicity

__all__ = ["CalibrationError", "build_gain_calibration"]

_DEFAULT_OUT_PATH = "fn_work/calibrations/gain.json"
_MIN_POINTS = 2


class CalibrationError(Exception):
    """增益标定构建失败：样本不足/形状非法/非法数值（NaN/inf/bool）/非单调（拒用）。"""


def _extract_out_path(measurements: list) -> str:
    """从测点字典里取 'out_path' 键（可携带在任一测点上）；缺省默认表路径。"""
    for item in measurements:
        if isinstance(item, dict):
            candidate = item.get("out_path")
            if isinstance(candidate, (str, os.PathLike)) and str(candidate).strip():
                return str(candidate)
    return _DEFAULT_OUT_PATH


def _serialize_points(measurements: list) -> list[tuple]:
    """测点字典列表 → (gain_step, power_dbm) 元组列表；结构非法即抛（形状文案）。"""
    points: list[tuple] = []
    for index, item in enumerate(measurements):
        if not isinstance(item, dict):
            raise CalibrationError(
                f"增益标定样本形状非法：第 {index} 个测点应为 dict"
                f"（gain_step/power_dbm），实际为 {item!r}"
            )
        if "gain_step" not in item or "power_dbm" not in item:
            raise CalibrationError(
                f"增益标定样本形状非法：第 {index} 个测点缺少 "
                f"gain_step/power_dbm 字段，实际键为 {sorted(map(str, item))}"
            )
        points.append((item["gain_step"], item["power_dbm"]))
    return points


def _violation_summary(violation: dict) -> str:
    """把 check_monotonicity 的单条违例渲染为可读摘要。"""
    return (
        f"第 {violation['index']} 点档 {violation['gain_step']!r} 功率 "
        f"{violation['power_dbm']!r} dBm 低于前点 {violation['prev_power_dbm']!r} dBm"
        f"（降 {violation['drop_db']:g} dB）"
    )


def _step_number(key: str) -> float | None:
    """档位键字符串的数值归一：可解析为有限数值则返回其值，否则 None（纯标签档）。

    超出 float 表示范围的超大数值字符串（如 400 位整数）float() 解析为 inf，归 None 按标签档处理。
    """
    try:
        number = float(key)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _write_table(out_path: str, entries: dict) -> None:
    """写出表 JSON（目录自动创建）；序列化确定性保证同输入幂等重建。

    out_path 指向已存在目录（IsADirectoryError）→ CalibrationError（文案含路径）。
    """
    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(entries, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except IsADirectoryError as exc:
        raise CalibrationError(
            f"增益标定表输出路径不可写（已存在目录）: {out_path}"
        ) from exc


def build_gain_calibration(measurements: list | None = None) -> dict:
    """发射端增益标定表构建与存储（含【待实测】占位）。

    输入 measurements 为真实标定测量序列 [{'gain_step': …, 'power_dbm': float}, …]：
    序列化为 (档位, 功率) 点后经 check_monotonicity 校验（容差 0，严格非降），
    违例非空或形状错（含 NaN/inf/bool/超出 float 范围的超大数值功率）→
    CalibrationError 拒用（文案含违例摘要；形状错单独文案）；样本 <2 点 →
    CalibrationError（样本不足）。档位序列化去重含数值等价检测——'20'、'20.0'
    与 20 视为同档，重复即 CalibrationError（文案注明两档位表示）。任一测点
    字典可额外携带 'out_path' 键指定表输出路径（缺省 'fn_work/calibrations/
    gain.json'，目录自动创建；out_path 指向已存在目录 → CalibrationError）。

    measurements 为 None → 生成【待实测】占位表（entries={}，placeholder=True，
    无任何预写数字，写默认路径——占位请求不携带测点，故无 out_path 来源）。

    返回 {'table_path': str, 'points': int, 'placeholder': bool, 'monotonic': True}；
    占位路径不抛异常。
    """
    if measurements is None:
        _write_table(_DEFAULT_OUT_PATH, {})
        return {
            "table_path": _DEFAULT_OUT_PATH,
            "points": 0,
            "placeholder": True,
            "monotonic": True,
        }

    if not isinstance(measurements, (list, tuple)):
        raise CalibrationError(
            f"增益标定样本形状非法：measurements 应为测点 dict 列表或 None，"
            f"实际为 {type(measurements).__name__}"
        )

    out_path = _extract_out_path(measurements)

    if len(measurements) < _MIN_POINTS:
        raise CalibrationError(
            f"样本不足：增益标定至少需要 {_MIN_POINTS} 个测点，实际为 {len(measurements)}"
        )

    points = _serialize_points(measurements)

    violations = check_monotonicity(points)
    if violations:
        if violations[0].get("error") == "shape":
            raise CalibrationError(
                f"增益标定样本形状非法：{violations[0]['detail']}"
            )
        summary = "；".join(_violation_summary(v) for v in violations)
        raise CalibrationError(
            f"增益标定非单调，拒用（{len(violations)} 处违例）：{summary}"
        )

    entries: dict = {}
    numeric_seen: dict[float, str] = {}
    for index, (step, power) in enumerate(points):
        key = str(step)
        if not key:
            raise CalibrationError(
                f"增益标定样本形状非法：第 {index} 个测点档位字符串化为空字符串"
            )
        if key in entries:
            raise CalibrationError(
                f"增益标定样本形状非法：档位重复 {key!r}"
                f"（第 {index} 个测点与此前测点 str(gain_step) 冲突）"
            )
        number = _step_number(key)
        if number is not None and number in numeric_seen:
            raise CalibrationError(
                f"增益标定样本形状非法：档位数值等价重复 {numeric_seen[number]!r} 与 {key!r}"
                f"（数值同为 {number:g}，第 {index} 个测点；防同档双写与最近邻匹配摆动）"
            )
        try:
            entries[key] = {"power_dbm": float(power)}
        except OverflowError:
            raise CalibrationError(
                f"增益标定样本非法值：第 {index} 个测点功率 {power!r} 超出可表示范围"
            ) from None
        if number is not None:
            numeric_seen[number] = key

    _write_table(out_path, entries)
    return {
        "table_path": out_path,
        "points": len(entries),
        "placeholder": False,
        "monotonic": True,
    }
