"""时钟状态端点（R104）——重写规约与签名意图详见 fn_docs/responsibility.md 域二十六。"""
from __future__ import annotations

__all__ = ["get_status_clock"]


def get_status_clock():
    """返回时钟参考状态与来源（最近运行/实时）；无值→unavailable。

    输出: {'clock_ref','source','available','note'} / 错误: 解析失败→unavailable 含原因（不抛）。
    """
    raise NotImplementedError("unimplemented:fn:get_status_clock")
