"""按名（含别名）取工厂与能力元数据——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

from typing import Callable

# 权威注册表与域错误均来自同包 register_backend（单一事实源）：
# REGISTRY 为同一 dict 对象直接读、不拷贝——写入侧的增删改即时可见。
from .register_backend import REGISTRY, BackendError

__all__ = ["BackendError", "lookup_backend"]

# 'auto' 为保留路由名：永不查注册表，交 autodetect_backend 探测决策
_AUTO = "auto"
_AUTO_NOTE = "需经 autodetect_backend 决策"

# 别名 → 注册表规范名（键值均以小写为准；大小写归一与键匹配在查找侧统一处理）。
# 当前三别名均为恒等映射，表即后续非恒等别名（如设备型号缩写）的唯一扩展点。
_ALIASES = {
    "b210": "b210",
    "sim": "sim",
    "replay": "replay",
}


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein 编辑距离（两行 DP；对已归一为小写的串计算）。"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def lookup_backend(name: str) -> tuple[Callable | None, dict]:
    """按名（含别名）取后端工厂与能力元数据。

    读取 register_backend.REGISTRY（同一 dict 直接读，不拷贝），值形状
    {'factory': Callable, 'meta': dict} 由 register_backend 登记时保证。

    解析顺序:
      1) 名形式校验：须为非空 str（空白名视同空名）→ 否则 BackendError；
      2) 保留名 'auto'（大小写不敏感）：返回
         (None, {'alias': 'auto', 'note': '需经 autodetect_backend 决策'})，
         不报错、不查注册表（即使有人登记了 'auto'，保留名仍优先）；
      3) 别名归一：b210→b210 / sim→sim / replay→replay；
      4) 注册表键大小写不敏感匹配，命中返回登记时的 (factory, meta) 本体
         （身份不变，不做任何拷贝/快照）；
      5) 未命中 → BackendError：注册表为空走单独文案；非空则附按与未知名的
         编辑距离升序（距离同则按名字母序）排列的相近名提示（如 'simx'→sim）。
    """
    if not isinstance(name, str):
        raise BackendError(
            f"名称非法: 须为非空 str，得到 {type(name).__name__}: {name!r}"
        )
    if not name.strip():
        raise BackendError(f"名称非法: 不允许空/空白名，得到 {name!r}")

    lowered = name.lower()

    # 保留名短路：'auto' 不解析到任何具体后端，交 autodetect_backend 决策
    if lowered == _AUTO:
        return None, {"alias": _AUTO, "note": _AUTO_NOTE}

    canonical = _ALIASES.get(lowered, lowered)
    for registered, entry in REGISTRY.items():
        if registered.lower() == canonical:
            return entry["factory"], entry["meta"]

    if not REGISTRY:
        raise BackendError(
            f"未知后端名 {name!r}；注册表为空（尚无后端登记，无相近名可提示）"
        )
    hints = sorted(
        REGISTRY,
        key=lambda key: (_edit_distance(lowered, key.lower()), key.lower()),
    )
    raise BackendError(
        f"未知后端名 {name!r}；相近建议（按编辑距离升序）: {', '.join(hints)}"
    )
