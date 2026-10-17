"""按名登记后端工厂（含契约形式检查）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

from typing import Any, Callable

# 全局后端注册表（模块级 dict，本模块持有）：名 -> {'factory': Callable, 'meta': dict}。
# 各后端模块 import 时自注册写入；lookup_backend / manage_backend_registry 从此处读取。
REGISTRY: dict[str, dict[str, Any]] = {}

# 统一接口契约：能力名 -> 该能力声明为真时实例须具备的方法名。
CONTRACT_METHODS: dict[str, list[str]] = {
    "tx": ["start_tx", "stop_tx", "set_tx_gain"],
    "rx": ["read_samples"],
}

# 契约词汇表可选扩充名（R96）：get_tx_gain 为 B210 形态鸭子特征名——允许出现在
# method_names 在册（B210Backend 五名交检），不列入能力必备（契约检查是子集关系，
# SimBackend 四名不在册不受扰）。
_OPTIONAL_METHOD_NAMES: frozenset[str] = frozenset({"get_tx_gain"})

# 契约方法名全集：method_names 须为其子集（未约定名如 'hack' 一律拒绝）。
_ALLOWED_METHOD_NAMES: frozenset[str] = frozenset(
    name for names in CONTRACT_METHODS.values() for name in names
) | _OPTIONAL_METHOD_NAMES

# 保留路由名（小写口径）：lookup_backend 永不把它解析到注册表（交 autodetect_backend
# 决策），注册侧一并直接拒绝——杜绝登记一个永远查不到的"幽灵后端"。
_RESERVED_NAME = "auto"


class BackendError(Exception):
    """后端注册错误：名称非法 / 工厂不可调用 / meta 缺 caps / 契约形式检查不过 / 重名未授权。"""


def _check_name(name: object) -> str:
    """名称形式校验：须为非空 str（空白名视同空名）。"""
    if not isinstance(name, str):
        raise BackendError(
            f"名称非法: 须为非空 str，得到 {type(name).__name__}: {name!r}"
        )
    if not name.strip():
        raise BackendError(f"名称非法: 不允许空/空白名，得到 {name!r}")
    return name


def _check_factory(factory: object) -> None:
    """工厂形式校验：须可调用（类/函数等均可）。"""
    if not callable(factory):
        raise BackendError(
            f"工厂不可调用: {type(factory).__name__}: {factory!r}"
        )


def _check_meta(meta: object) -> dict:
    """能力元数据形式校验：meta 须为 dict 且必含 caps（caps 须为 dict）。"""
    if not isinstance(meta, dict):
        raise BackendError(
            f"meta 须为 dict（必含能力声明 caps），得到 {type(meta).__name__}: {meta!r}"
        )
    if "caps" not in meta:
        raise BackendError(
            "meta 缺必填键 'caps'（能力声明: tx/rx/freq_range_mhz）"
        )
    caps = meta["caps"]
    if not isinstance(caps, dict):
        raise BackendError(
            f"caps 须为 dict（能力声明: tx/rx/freq_range_mhz），得到 {type(caps).__name__}: {caps!r}"
        )
    return caps


def _check_contract(method_names: object, caps: dict) -> None:
    """契约形式检查（只查方法名，不实例化工厂、不触碰实例属性）。

    1) method_names 须为 list[str]（或 tuple），且每个名字都在约定方法集内——
       未约定名（如 'hack'）说明工厂对象不走统一接口，拒绝；
    2) caps 声明为真的能力，其约定方法须逐一出现在 method_names 中——
       声明了能力却缺对应方法名，拒绝。
    """
    if not isinstance(method_names, (list, tuple)):
        raise BackendError(
            "method_names 须为 list[str] | None（None 跳过契约检查，"
            f"延迟到首次实例化），得到 {type(method_names).__name__}: {method_names!r}"
        )
    declared = set(method_names)
    for method in method_names:
        if not isinstance(method, str) or method not in _ALLOWED_METHOD_NAMES:
            raise BackendError(
                f"契约违例: method_names 含未约定方法名 {method!r}"
                f"（约定全集: {sorted(_ALLOWED_METHOD_NAMES)}）"
            )
    for cap, required in CONTRACT_METHODS.items():
        if caps.get(cap):
            missing = [name for name in required if name not in declared]
            if missing:
                raise BackendError(
                    f"契约违例: caps 声明 {cap} 为真但 method_names 缺方法 {missing}"
                    f"（{cap} 须具备: {required}）"
                )


def register_backend(
    name: str,
    factory: Callable,
    meta: dict,
    *,
    override: bool = False,
    method_names: list[str] | None = None,
) -> dict:
    """按名登记后端工厂（含契约形式检查）。

    输入: name 后端名；factory 工厂（调用返回实现统一接口的实例）；meta 能力元数据
    （必含 caps: {'tx': bool, 'rx': bool, 'freq_range_mhz': (lo, hi)}）；override
    显式授权覆盖重名；method_names 实例方法名清单（None 缺省跳过契约检查，检查
    延迟到首次实例化）。
    输出: {'registered': True, 'replaced': bool}（replaced=True 仅出现在 override 覆盖，
    含大小写变体覆盖——旧规范名键一并让位，不产生双键）。
    错误: BackendError——名称非法（空/非 str/保留名 'auto'，大小写不敏感，override
    也不放行）/工厂不可调用/meta 缺 caps/契约形式检查不过（未约定方法名、声明能力
    缺方法）/重名且未显式 override（重名按大小写不敏感口径：'SIM' 与 'sim' 冲突）。
    所有校验先于注册表写入：失败路径不产生任何登记（无半写状态）。
    """
    name = _check_name(name)
    _check_factory(factory)
    caps = _check_meta(meta)
    if method_names is not None:
        _check_contract(method_names, caps)
    lowered = name.lower()
    if lowered == _RESERVED_NAME:
        raise BackendError(
            f"名称非法: {name!r} 为保留名（'auto' 交 autodetect_backend 决策路由），"
            "不允许注册（override 亦不放行）"
        )
    existing = next((key for key in REGISTRY if key.lower() == lowered), None)
    replaced = existing is not None
    if replaced and not override:
        raise BackendError(
            f"重名: 后端 {name!r} 与已注册 {existing!r} 冲突（大小写不敏感口径），"
            f"覆盖须显式 override=True（已注册: {sorted(REGISTRY)}）"
        )
    if existing is not None:
        del REGISTRY[existing]  # 大小写变体覆盖：旧键让位，避免同名异键双查歧义
    REGISTRY[name] = {"factory": factory, "meta": meta}
    return {"registered": True, "replaced": replaced}
