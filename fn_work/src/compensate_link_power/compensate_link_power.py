"""公式(6) 全链路补偿（无表频点标不可信）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def compensate_link_power(measurements: list, tables: dict | None = None) -> list:
    """公式(6) 全链路补偿（无表频点标不可信）。"""
    raise NotImplementedError("unimplemented:fn:compensate_link_power")
