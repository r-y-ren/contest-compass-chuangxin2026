"""SigMF 录制真值 facts 组装（R106）——重写规约与签名意图详见 fn_docs/responsibility.md 共享函数节。"""
from __future__ import annotations

__all__ = ["build_recording_facts"]


def build_recording_facts(scenario, selection, clock_ref, events, window=None):
    """组装录制 facts：fs/实际 backend/clock_ref/功率档/window；缺可选给 status。

    输入: 场景+选择结果+时钟+事件序列+录制窗口 / 输出: facts dict / 错误: 必填缺失→ValueError。
    """
    raise NotImplementedError("unimplemented:fn:build_recording_facts")
