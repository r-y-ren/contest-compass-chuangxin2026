"""≥5 频点图谱位组装（不足如实标注）——重写规约与签名意图详见 fn_docs/responsibility.md。

plots 形状：{'freq_mhz': [多频点谱图路径键], 'images': {路径键: 存在性 bool 或路径}}。
按 freq_mhz 顺序逐键判存（bool 表项直接采信，str/PathLike 表项落盘 os.path.exists
实测），产出图谱位计数（slots）/要求数（required=5）/可用图谱键列表（images）/
缺额注记（deficit_note，<5 时如实列缺哪些频点）/满足标志（satisfied=slots≥5）。
plots 空/全缺→slots 0+注记；plots 非 dict、freq_mhz 非 list[str]、images 非 dict
或表项类型异类→ValueError。
"""
from __future__ import annotations

import os

__all__ = ["assemble_frequency_plots"]

#: 报告要求的频点图谱位数（R45：2.4G 各信道+5.8G 监测段，≥5 位，不足如实标注）。
REQUIRED_SLOTS = 5


def _entry_available(key: str, entry: object) -> bool:
    """images 表项判存：bool 直接采信；str/os.PathLike 路径落盘实测；其余形状错。"""
    if isinstance(entry, bool):
        return entry
    if isinstance(entry, (str, os.PathLike)):
        return os.path.exists(os.fspath(entry))
    raise ValueError(
        f"images[{key!r}] 必须为存在性 bool 或路径，"
        f"实际 {type(entry).__name__}: {entry!r}"
    )


def assemble_frequency_plots(plots: dict) -> dict:
    """≥5 频点图谱位组装（不足如实标注）。

    返回 {'slots': 实际可用频点图数, 'required': 5, 'images': [可用路径键列表
    （按 freq_mhz 顺序）], 'deficit_note': 缺 N 个频点图注记（<5 时如实列出缺失
    频点；满足时为空串）, 'satisfied': slots>=5}。freq_mhz 中未在 images 登记、
    登记为 False 或路径不存在者均计入缺失。plots 非 dict、freq_mhz 非 list 或
    元素非 str、images 非 dict、images 表项非 bool/路径 → ValueError。
    """
    if not isinstance(plots, dict):
        raise ValueError(
            f"plots 必须为 dict，实际 {type(plots).__name__}: {plots!r}"
        )

    freq_mhz = plots.get("freq_mhz", [])
    if not isinstance(freq_mhz, list):
        raise ValueError(
            f"plots['freq_mhz'] 必须为 list[str]，实际 {type(freq_mhz).__name__}: {freq_mhz!r}"
        )
    for idx, key in enumerate(freq_mhz):
        if not isinstance(key, str):
            raise ValueError(
                f"plots['freq_mhz'][{idx}] 必须为 str（路径键），"
                f"实际 {type(key).__name__}: {key!r}"
            )

    images = plots.get("images", {})
    if not isinstance(images, dict):
        raise ValueError(
            f"plots['images'] 必须为 dict，实际 {type(images).__name__}: {images!r}"
        )

    available: list[str] = []
    missing: list[str] = []
    for key in freq_mhz:
        entry = images.get(key)
        if entry is not None and _entry_available(key, entry):
            available.append(key)
        else:
            missing.append(key)

    slots = len(available)
    deficit = REQUIRED_SLOTS - slots
    if deficit <= 0:
        deficit_note = ""
    elif missing:
        deficit_note = (
            f"缺 {deficit} 个频点图（实有 {slots}/需 {REQUIRED_SLOTS}；"
            f"缺失频点：{'、'.join(missing)}）"
        )
    elif freq_mhz:
        deficit_note = (
            f"缺 {deficit} 个频点图（实有 {slots}/需 {REQUIRED_SLOTS}；"
            f"已登记 {len(freq_mhz)} 个频点均可用，登记数不足）"
        )
    else:
        deficit_note = (
            f"缺 {deficit} 个频点图（实有 {slots}/需 {REQUIRED_SLOTS}；未登记任何频点键）"
        )

    return {
        "slots": slots,
        "required": REQUIRED_SLOTS,
        "images": available,
        "deficit_note": deficit_note,
        "satisfied": slots >= REQUIRED_SLOTS,
    }
