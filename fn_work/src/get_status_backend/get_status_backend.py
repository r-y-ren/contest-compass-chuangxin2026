"""后端状态端点（R104）——重写规约与签名意图详见 fn_docs/responsibility.md 域二十六。"""
from __future__ import annotations

__all__ = ["get_status_backend"]


def get_status_backend():
    """只读探测后端在位状态（不打开/占用设备）。

    输出: {'available','kind','note'} / 错误: 探测失败→available=False 含原因（不抛）。
    """
    raise NotImplementedError("unimplemented:fn:get_status_backend")
