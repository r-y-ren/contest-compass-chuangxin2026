"""数据集索引：登记/检索入口（损坏自动重建）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def index_dataset(action: str, record: dict | None = None, query: dict | None = None) -> object:
    """数据集索引：登记/检索入口（损坏自动重建）。"""
    raise NotImplementedError("unimplemented:fn:index_dataset")
