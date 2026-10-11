"""场景装载总入口：读 YAML→schema 校验→红线校验→规范化，产出场景对象——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def load_scenario(path: str) -> dict:
    """场景装载总入口：读 YAML→schema 校验→红线校验→规范化，产出场景对象。"""
    raise NotImplementedError("unimplemented:fn:load_scenario")
