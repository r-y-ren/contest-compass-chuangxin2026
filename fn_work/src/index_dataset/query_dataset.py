"""数据集索引条件检索（样式/频段/日期/后端/失效/批次分组键）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

__all__ = ["QueryError", "query_dataset"]

_SUPPORTED_FIELDS = ("style", "freq_range", "date_range", "backend", "failed", "batch_key")
_SUPPORTED_SET = frozenset(_SUPPORTED_FIELDS)
_NONE_GROUP = "_none"


class QueryError(ValueError):
    """检索非法：未知条件字段（附支持字段清单）/索引或条件形状错。"""


def _is_number(value) -> bool:
    """数值口径：int/float 且非 bool（避免 True==1 误命中频段边界）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _effective_batch_key(entry: dict) -> str:
    """条目生效批次键：仅 str 算分组键，缺失/None/非 str 一律归 '_none'。"""
    key = entry.get("batch_key")
    return key if isinstance(key, str) else _NONE_GROUP


def _sort_key(entry: dict) -> tuple:
    """date 升序、run_id 字典序；缺失/非 str 记 ''（排最前）保证全序比较不抛错。"""
    date = entry.get("date")
    run_id = entry.get("run_id")
    return (date if isinstance(date, str) else "", run_id if isinstance(run_id, str) else "")


def _pair(value, field: str, check, kind: str) -> tuple:
    """区间条件形状校验：必须为 (x, y) 二元 list/tuple 且两端点通过 check。"""
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or not check(value[0])
        or not check(value[1])
    ):
        raise QueryError(f"{field} 条件必须为 ({kind}, {kind}) 二元组，得到 {value!r}")
    return value[0], value[1]


def _compile_checks(conditions) -> list:
    """条件编译为谓词列表（多条件 AND）；未知字段/条件值形状错→QueryError。"""
    if conditions is None:
        conditions = {}
    if not isinstance(conditions, dict):
        raise QueryError(f"conditions 必须为 dict，得到 {type(conditions).__name__}")
    unknown = [key for key in conditions if key not in _SUPPORTED_SET]
    if unknown:
        raise QueryError(f"未知条件字段 {unknown!r}；支持字段清单: {list(_SUPPORTED_FIELDS)}")

    checks = []

    if "style" in conditions:
        style = conditions["style"]
        if isinstance(style, str):
            wanted_styles = {style}
        elif isinstance(style, (list, tuple, set)) and all(isinstance(s, str) for s in style):
            wanted_styles = set(style)  # 列表多值 OR 语义（空列表不命中任何条目）
        else:
            raise QueryError(f"style 条件必须为 str 或 str 列表，得到 {style!r}")
        checks.append(lambda entry: entry.get("style") in wanted_styles)

    if "freq_range" in conditions:
        lo, hi = _pair(conditions["freq_range"], "freq_range", _is_number, "数值")
        checks.append(
            lambda entry: _is_number(entry.get("freq_mhz"))
            and lo <= entry["freq_mhz"] <= hi  # 闭区间；缺频点/None/非数值不命中（不抛错）
        )

    if "date_range" in conditions:
        lo, hi = _pair(
            conditions["date_range"], "date_range", lambda v: isinstance(v, str), "日期字符串"
        )
        checks.append(
            lambda entry: isinstance(entry.get("date"), str)
            and lo <= entry["date"] <= hi  # 闭区间，字符串字典序比较
        )

    if "backend" in conditions:
        backend = conditions["backend"]
        if not isinstance(backend, str):
            raise QueryError(f"backend 条件必须为 str，得到 {backend!r}")
        checks.append(lambda entry: entry.get("backend") == backend)

    if "failed" in conditions:
        failed = conditions["failed"]
        if not isinstance(failed, bool):
            raise QueryError(f"failed 条件必须为 bool，得到 {failed!r}")
        checks.append(lambda entry: bool(entry.get("failed")) is failed)  # 缺 failed 记 False

    if "batch_key" in conditions:
        batch_key = conditions["batch_key"]
        if not isinstance(batch_key, str):
            raise QueryError(f"batch_key 条件必须为 str，得到 {batch_key!r}")
        checks.append(lambda entry: _effective_batch_key(entry) == batch_key)

    return checks


def query_dataset(index: list, conditions: dict | None = None) -> dict:
    """按条件检索数据集索引（纯函数：不修改 index/conditions）。

    索引条目：{'run_id','path','style','freq_mhz','date','backend','jsr_db','failed': bool}，
    可选 'batch_key'（分组键；缺失/None/非 str 归 '_none'，可用条件 batch_key='_none' 检索该桶）。

    conditions 多条件 AND，支持字段：
    - style: str 或 list[str]（列表内 OR）；条目缺 style 不命中；
    - freq_range: (lo, hi) 数值闭区间；条目 freq_mhz 缺失/None/非数值（含 bool）不命中；
    - date_range: (lo, hi) 日期字符串闭区间（字典序比较）；条目 date 非 str 不命中；
    - backend: str 精确相等；
    - failed: bool（条目缺失 failed 记 False）；
    - batch_key: str 与生效批次键相等。

    返回：{'entries': [匹配条目...], 'batch_groups': {batch_key: [条目...]},
    'total': 索引条目总数, 'matched': 匹配数}；entries 与各组内顺序均为
    date 升序 + run_id 字典序稳定排序（缺失/非 str 的 date/run_id 记 ''）。

    错误（只抛 QueryError，不抛其他）：index 非 list、条目非 dict、
    未知条件字段（消息附支持字段清单）、条件值形状错（含 conditions 非 dict）。
    """
    if not isinstance(index, list):
        raise QueryError(f"index 必须为 list[dict]，得到 {type(index).__name__}")
    for position, entry in enumerate(index):
        if not isinstance(entry, dict):
            raise QueryError(f"索引条目 #{position} 必须为 dict，得到 {type(entry).__name__}")

    checks = _compile_checks(conditions)
    matched = [entry for entry in index if all(check(entry) for check in checks)]
    matched.sort(key=_sort_key)  # sorted 稳定；matched 为新列表，index 原序不动

    batch_groups: dict = {}
    for entry in matched:
        batch_groups.setdefault(_effective_batch_key(entry), []).append(entry)

    return {
        "entries": matched,
        "batch_groups": batch_groups,
        "total": len(index),
        "matched": len(matched),
    }
