"""后端注册表总入口：登记/获取/清点，按 action 分派——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

from typing import Any, Callable

# 子函数与权威注册表均来自同包（REGISTRY/BackendError 单一事实源在 register_backend）。
from .lookup_backend import lookup_backend
from .register_backend import REGISTRY, BackendError, register_backend

__all__ = ["BackendError", "manage_backend_registry"]

# 合法 action 清单：错误信息中完整列出，便于调用方自纠。
_ACTIONS: tuple[str, ...] = ("register", "lookup", "list")


def manage_backend_registry(
    action: str,
    name: str | None = None,
    factory: Callable | None = None,
    meta: dict | None = None,
    *,
    override: bool = False,
    method_names: list[str] | None = None,
) -> dict[str, Any]:
    """后端注册表总入口：按 action 分派 register/lookup/list。

    输入: action 取 'register' | 'lookup' | 'list'；name 后端名（register/lookup
    必填，缺省 None → BackendError）；factory/meta/override/method_names 仅
    register 使用，原样透传 register_backend（含契约形式检查）。
    输出: register → {'registered': True, 'replaced': bool, 'available': [名清单]}
    （available 为注册成功后的注册表名快照）；lookup → {'factory': 工厂,
    'meta': 元数据}（保留名 'auto' 时 factory 为 None，交 autodetect_backend）；
    list → {'available': [名清单], 'metas': {名: meta}}。
    错误: action 非 str 或非法（附合法清单）→ BackendError；register/lookup 缺
    name → BackendError；其余（名称非法/工厂不可调用/meta 缺 caps/契约违例/
    重名未 override/未知名相近提示）由子函数透传，失败路径不留半写状态。
    """
    if not isinstance(action, str):
        raise BackendError(
            f"action 须为 str，合法取值: {list(_ACTIONS)}；"
            f"得到 {type(action).__name__}: {action!r}"
        )
    if action == "register":
        if name is None:
            raise BackendError("register 需要后端名 name（得到缺省 None）")
        result = dict(
            register_backend(
                name, factory, meta, override=override, method_names=method_names
            )
        )
        result["available"] = sorted(REGISTRY)
        return result
    if action == "lookup":
        if name is None:
            raise BackendError("lookup 需要后端名 name（得到缺省 None）")
        found_factory, found_meta = lookup_backend(name)
        return {"factory": found_factory, "meta": found_meta}
    if action == "list":
        return {
            "available": sorted(REGISTRY),
            "metas": {key: REGISTRY[key]["meta"] for key in sorted(REGISTRY)},
        }
    raise BackendError(f"非法 action {action!r}；合法取值: {list(_ACTIONS)}")
