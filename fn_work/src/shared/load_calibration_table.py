"""标定表加载与结构校验（缺表按语义占位或抛出）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import json
import math
import os
from types import MappingProxyType

__all__ = ["CalibrationError", "load_calibration_table"]

_DEFAULT_CALIBRATION_DIR = "fn_work/calibrations"
_VALID_TABLE_NAMES = ("gain", "link_loss", "antenna")
_PLACEHOLDER_NOTE = "【待实测】标定表缺失，entries 为空占位"


class CalibrationError(Exception):
    """标定表加载/校验失败：文件损坏、表名未知、缺表且 placeholder=False、目录不存在。"""


def _reject_constant(token: str) -> None:
    """JSON 解析遇到 NaN/Infinity/-Infinity 字面量即视为文件损坏。"""
    raise CalibrationError(f"非法 JSON 常量 {token}（NaN/inf 视为损坏）")


def _no_duplicate_pairs(pairs: list) -> dict:
    """逐层拒绝 JSON 对象重复键（json 默认会静默保留最后一个键）。"""
    seen: set = set()
    for key, _ in pairs:
        if key in seen:
            raise CalibrationError(f"JSON 对象存在重复键 {key!r}")
        seen.add(key)
    return dict(pairs)


def _checked_number(value: object, where: str) -> int | float:
    """数值必须为有限的非 bool 数值，否则视为损坏。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalibrationError(f"{where} 期望数值，实际 {type(value).__name__}（bool 不作数值）")
    if not math.isfinite(value):
        raise CalibrationError(f"{where} 数值非有限（NaN/inf 视为损坏）")
    return value


def _checked_freq_mhz(key: str, where: str) -> float:
    """频点表键必须可解析为有限数值（MHz），解析后统一为 float 键。"""
    try:
        freq = float(key)
    except (TypeError, ValueError):
        raise CalibrationError(f"{where} 频点键 {key!r} 不是数值（MHz）") from None
    if not math.isfinite(freq):
        raise CalibrationError(f"{where} 频点键 {key!r} 非有限（NaN/inf）")
    return freq


def _validate_entries(table_name: str, raw: dict) -> dict:
    """按表名约定校验结构并规范化 entries。

    'gain'：键=档位标识（非空字符串），值={"power_dbm": float}；
    'link_loss'/'antenna'：键=频点 MHz（数值字符串，规范化为 float），值=dB 数值。
    """
    entries: dict = {}
    if table_name == "gain":
        for key, value in raw.items():
            if not isinstance(key, str) or not key:
                raise CalibrationError(f"gain 档位键必须为非空字符串，实际 {key!r}")
            where = f"gain[{key!r}]"
            if not isinstance(value, dict):
                raise CalibrationError(f"{where} 期望 {{'power_dbm': float}}，实际 {type(value).__name__}")
            if "power_dbm" not in value:
                raise CalibrationError(f"{where} 缺少 power_dbm 字段")
            entries[key] = {"power_dbm": _checked_number(value["power_dbm"], f"{where}.power_dbm")}
    else:  # link_loss / antenna：频点 MHz → dB
        for key, value in raw.items():
            where = f"{table_name}[{key!r}]"
            freq = _checked_freq_mhz(key, where)
            if freq in entries:
                raise CalibrationError(f"{where} 频点 {freq} MHz 重复")
            entries[freq] = _checked_number(value, where)
    return entries


def _freeze(value):
    """递归转只读（dict→MappingProxyType，list→tuple），保证返回视图的表数据不可被改写。"""
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def load_calibration_table(table_name: str, config: dict, *, placeholder: bool = False) -> dict:
    """标定表加载与结构校验（缺表按语义占位或抛出）。

    返回只读视图 {name, source, entries, placeholder, meta}，其中 entries 与 meta 深度只读。
    缺表时：placeholder=True → 返回【待实测】占位视图（entries 为空，禁止预写数字）；
    placeholder=False → CalibrationError。文件损坏（非法 JSON、结构不符、NaN/inf、bool 数值、
    重复键）、表名未知、标定目录不存在 → 一律 CalibrationError（含原因）。
    """
    if not isinstance(table_name, str) or table_name not in _VALID_TABLE_NAMES:
        raise CalibrationError(f"未知标定表名 {table_name!r}（合法: {'|'.join(_VALID_TABLE_NAMES)}）")
    if not isinstance(config, dict):
        raise CalibrationError(f"config 必须为 dict，实际 {type(config).__name__}")

    calibration_dir = str(config.get("calibration_dir", _DEFAULT_CALIBRATION_DIR))
    path = os.path.join(calibration_dir, f"{table_name}.json")

    if not os.path.isdir(calibration_dir):
        raise CalibrationError(f"标定目录不存在: {calibration_dir}（表 {table_name}）")

    if not os.path.isfile(path):
        if placeholder:
            return {
                "name": table_name,
                "source": None,
                "entries": MappingProxyType({}),
                "placeholder": True,
                "meta": _freeze(
                    {
                        "kind": table_name,
                        "entry_count": 0,
                        "expected_path": path,
                        "note": _PLACEHOLDER_NOTE,
                    }
                ),
            }
        raise CalibrationError(f"标定表缺失: {path}（placeholder=False）")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(
                fh,
                object_pairs_hook=_no_duplicate_pairs,
                parse_constant=_reject_constant,
            )
    except json.JSONDecodeError as exc:
        raise CalibrationError(f"标定表损坏（非法 JSON）: {path}: {exc}") from exc
    except OSError as exc:
        raise CalibrationError(f"标定表不可读: {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise CalibrationError(f"标定表结构不符: 顶层应为 JSON 对象，实际 {type(raw).__name__}（{path}）")

    try:
        entries = _validate_entries(table_name, raw)
    except CalibrationError as exc:
        raise CalibrationError(f"标定表损坏: {path}: {exc}") from exc

    return {
        "name": table_name,
        "source": path,
        "entries": _freeze(entries),
        "placeholder": False,
        "meta": _freeze({"kind": table_name, "entry_count": len(entries)}),
    }
