"""清单条目行定位（结构感知，返回现状）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def locate_ledger_row(entry_id: str, ledger_path: str) -> dict:
    """清单条目行定位（结构感知，返回现状）。"""
    raise NotImplementedError("unimplemented:fn:locate_ledger_row")
