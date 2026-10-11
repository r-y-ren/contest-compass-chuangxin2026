"""标定表加载与结构校验（缺表按语义占位或抛出）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def load_calibration_table(table_name: str, config: dict, *, placeholder: bool = False) -> dict:
    """标定表加载与结构校验（缺表按语义占位或抛出）。"""
    raise NotImplementedError("unimplemented:fn:load_calibration_table")
