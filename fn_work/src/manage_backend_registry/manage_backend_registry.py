"""后端注册表总入口：登记/获取，接口契约与能力元数据——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def manage_backend_registry(action: str, name: str, factory=None, meta: dict | None = None, *, override: bool = False) -> object:
    """后端注册表总入口：登记/获取，接口契约与能力元数据。"""
    raise NotImplementedError("unimplemented:fn:manage_backend_registry")
