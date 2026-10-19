"""场景保存服务端守卫（R103）——重写规约与签名意图详见 fn_docs/responsibility.md 域二十六。"""
from __future__ import annotations

__all__ = ["guard_scenario_update"]


def guard_scenario_update(old_text, new_text, allow_drop=False):
    """比较新旧场景：丢频段/丢表单不表达键→拒绝；allow_drop=True 放行。

    输入: 旧文本+新文本+allow_drop / 输出: {'ok','dropped_bands','dropped_keys'} / 错误: 解析失败→ValueError 携带原因。
    """
    raise NotImplementedError("unimplemented:fn:guard_scenario_update")
