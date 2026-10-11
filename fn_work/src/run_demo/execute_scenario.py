"""单场景执行阶段编排（按场景类型分派各功能块）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def execute_scenario(ctx: dict, scenario: dict) -> dict:
    """单场景执行阶段编排（按场景类型分派各功能块）。"""
    raise NotImplementedError("unimplemented:fn:execute_scenario")
