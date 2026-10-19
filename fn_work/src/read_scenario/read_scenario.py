"""读取单个场景原文（R103）——重写规约与签名意图详见 fn_docs/responsibility.md 域二十六。"""
from __future__ import annotations

__all__ = ["read_scenario"]


def read_scenario(scenario_dir, name):
    """读取场景原始 YAML 文本（.yaml/.yml 与列表口径一致）。

    输入: 场景目录+场景名 / 输出: {'name','content'} / 错误: 不存在→FileNotFoundError；读取失败原样透传。
    """
    raise NotImplementedError("unimplemented:fn:read_scenario")
