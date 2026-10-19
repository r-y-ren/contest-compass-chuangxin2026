"""失效电平聚合重算（R105）——重写规约与签名意图详见 fn_docs/responsibility.md 共享函数节。"""
from __future__ import annotations

__all__ = ["recompute_failure_aggregates"]


def recompute_failure_aggregates(entries):
    """按 style 重算失效电平 median/min/max/n_runs（与 compare_failure_boundaries 同源）。

    输入: failure_level 事件条目（style/failure_level_db）/ 输出: {style:{median_db,min_db,max_db,n_runs}}
    错误: 缺 style 或非有限值→ValueError。
    """
    raise NotImplementedError("unimplemented:fn:recompute_failure_aggregates")
