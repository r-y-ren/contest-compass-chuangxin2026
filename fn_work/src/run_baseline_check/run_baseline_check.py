"""无干扰对照段：基线异常即中止防误报——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def run_baseline_check(ctx: dict, threshold: dict | None = None) -> dict:
    """无干扰对照段：基线异常即中止防误报。"""
    raise NotImplementedError("unimplemented:fn:run_baseline_check")
