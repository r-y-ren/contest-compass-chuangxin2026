"""条件检索（样式/频段/日期/后端，含批次分组键）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def query_dataset(query: dict) -> list:
    """条件检索（样式/频段/日期/后端，含批次分组键）。"""
    raise NotImplementedError("unimplemented:fn:query_dataset")
