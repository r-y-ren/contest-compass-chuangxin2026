"""PER 台阶→SITL 丢包/时延注入（不在位跳过不阻塞）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def bridge_to_sitl(result: dict, sitl_config: dict) -> dict:
    """PER 台阶→SITL 丢包/时延注入（不在位跳过不阻塞）。"""
    raise NotImplementedError("unimplemented:fn:bridge_to_sitl")
