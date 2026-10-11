"""lookup_backend 对抗单测——别名/保留名/大小写/相近提示/空表/名非法/身份直读。"""
from __future__ import annotations

import pytest

from src.manage_backend_registry.lookup_backend import BackendError, lookup_backend
from src.manage_backend_registry.register_backend import REGISTRY, register_backend

_AUTO_META = {"alias": "auto", "note": "需经 autodetect_backend 决策"}


def _factory(tag: str):
    def factory(cfg=None):
        return {"backend": tag, "cfg": cfg}

    factory.__name__ = f"factory_{tag}"
    return factory


def _entry(tag: str) -> dict:
    """与 register_backend 契约一致的登记项 {'factory', 'meta'}（meta 必含 caps）。"""
    return {
        "factory": _factory(tag),
        "meta": {"caps": {"tx": True, "rx": True, "freq_range_mhz": (2400.0, 2483.5)}},
    }


@pytest.fixture
def _isolate():
    """用例间隔离共享注册表：就地清空，用毕按快照原样还原（同一 dict 对象）。"""
    saved = dict(REGISTRY)
    REGISTRY.clear()
    yield REGISTRY
    REGISTRY.clear()
    REGISTRY.update(saved)


@pytest.fixture
def trio(_isolate):
    """注入标准三后端 b210/sim/replay（配合 _isolate 隔离与还原）。"""
    entries = {name: _entry(name) for name in ("b210", "sim", "replay")}
    REGISTRY.update(entries)
    return entries


def test_exact_registered_name_resolves_identity(trio):
    """① 已注册名精确取：三规范名各取回登记时的 factory/meta 本体，二元组形状。"""
    for name in ("b210", "sim", "replay"):
        result = lookup_backend(name)
        assert isinstance(result, tuple) and len(result) == 2
        factory, meta = result
        assert factory is trio[name]["factory"]
        assert meta is trio[name]["meta"]


def test_auto_returns_special_without_error(trio):
    """② 保留名 'auto'：返回 (None, 提示 meta)，不报错。"""
    factory, meta = lookup_backend("auto")
    assert factory is None
    assert meta == _AUTO_META


@pytest.mark.parametrize(
    "query, canonical",
    [
        ("SIM", "sim"),
        ("Sim", "sim"),
        ("sIm", "sim"),
        ("B210", "b210"),
        ("RePlay", "replay"),
    ],
    ids=["SIM", "Sim", "sIm", "B210", "RePlay"],
)
def test_case_insensitive_lookup(trio, query, canonical):
    """③ 大小写不敏感：任意大小写变体取回对应规范名的登记本体。"""
    factory, meta = lookup_backend(query)
    assert factory is trio[canonical]["factory"]
    assert meta is trio[canonical]["meta"]


def test_unknown_name_hints_sorted_by_edit_distance(trio):
    """④ 未知名 'simx'：BackendError 且相近名按编辑距离升序（sim=1 < b210=4 < replay=6）。"""
    with pytest.raises(BackendError) as exc_info:
        lookup_backend("simx")
    msg = str(exc_info.value)
    assert "'simx'" in msg
    assert "相近建议" in msg
    assert "sim, b210, replay" in msg


def test_empty_registry_dedicated_message(_isolate):
    """⑤ 空注册表：单独文案点明注册表为空，不进入相近名提示分支。"""
    with pytest.raises(BackendError) as exc_info:
        lookup_backend("sim")
    msg = str(exc_info.value)
    assert "'sim'" in msg
    assert "注册表为空" in msg
    assert "相近建议" not in msg


@pytest.mark.parametrize(
    "bad",
    [None, "", "   ", 42, 3.5, b"sim", ["sim"], True, object()],
    ids=["None", "empty", "blank", "int", "float", "bytes", "list", "bool", "object"],
)
def test_invalid_name_rejected(trio, bad):
    """⑥ 名 None/空/空白/非 str（含 bool/bytes）→ BackendError（名称非法）。"""
    with pytest.raises(BackendError) as exc_info:
        lookup_backend(bad)
    assert "名称非法" in str(exc_info.value)


def test_meta_identity_via_register_backend(_isolate):
    """⑦ 身份断言（端到端）：register_backend 登记的 meta/factory 即取回本体，不拷贝。"""
    factory = _factory("sim")
    meta = {"caps": {"tx": True, "rx": True, "freq_range_mhz": (2400.0, 2483.5)}}
    ack = register_backend("sim", factory, meta)
    assert ack == {"registered": True, "replaced": False}
    got_factory, got_meta = lookup_backend("sim")
    assert got_factory is factory
    assert got_meta is meta
    assert lookup_backend("sim")[1] is meta  # 重复查询仍为同一对象，无中途快照


@pytest.mark.parametrize(
    "query", ["AUTO", "Auto", "aUtO", "auto"], ids=["AUTO", "Auto", "aUtO", "auto"]
)
def test_auto_case_variants_special_return(trio, query):
    """⑧ 'auto' 大小写变体：全部特殊返回，不查表、不报错。"""
    factory, meta = lookup_backend(query)
    assert factory is None
    assert meta == _AUTO_META


def test_auto_reserved_beats_registered_entry(_isolate):
    """⑨ 对抗：即使有人把 'auto' 登记进表，保留名仍优先返回特殊值而非该登记。"""
    entry = _entry("auto")
    REGISTRY["auto"] = entry
    factory, meta = lookup_backend("auto")
    assert factory is None
    assert meta == _AUTO_META
    assert factory is not entry["factory"]


def test_auto_special_even_when_registry_empty(_isolate):
    """⑩ 对抗：空注册表时 'auto' 依旧特殊返回（保留名不依赖表内容）。"""
    factory, meta = lookup_backend("auto")
    assert factory is None
    assert meta == _AUTO_META


def test_registry_read_live_not_snapshot(trio):
    """⑪ 直读不快照：登记项删/改即时反映（REGISTRY 同一对象直接读）。"""
    assert lookup_backend("replay")[0] is trio["replay"]["factory"]
    del REGISTRY["replay"]
    with pytest.raises(BackendError):
        lookup_backend("replay")
    replacement = _entry("replay")
    REGISTRY["replay"] = replacement
    assert lookup_backend("replay")[0] is replacement["factory"]


def test_unknown_message_preserves_original_case(trio):
    """⑫ 未知名报错携带原始大小写（'SIMX' 原样入文案），提示仍按小写距离排序。"""
    with pytest.raises(BackendError) as exc_info:
        lookup_backend("SIMX")
    msg = str(exc_info.value)
    assert "'SIMX'" in msg
    assert "sim, b210, replay" in msg


def test_whitespace_padded_name_not_silently_trimmed(trio):
    """⑬ 对抗：' sim' 不做静默去空格——按未知名报错，且 'sim'（距离1）排提示首位。"""
    with pytest.raises(BackendError) as exc_info:
        lookup_backend(" sim")
    msg = str(exc_info.value)
    assert "未知后端名" in msg
    assert "sim, b210, replay" in msg
