"""manage_backend_registry 对抗单测——分派/透传/身份直读/清单/缺省拒绝/override 链路。"""
from __future__ import annotations

import pytest

from src.manage_backend_registry.lookup_backend import BackendError
from src.manage_backend_registry.manage_backend_registry import manage_backend_registry
from src.manage_backend_registry.register_backend import REGISTRY


def _factory(tag: str):
    def factory(cfg=None):
        return {"backend": tag, "cfg": cfg}

    factory.__name__ = f"factory_{tag}"
    return factory


def _meta(tag: str) -> dict:
    """与 register_backend 契约一致的 meta（必含 caps）。"""
    return {"caps": {"tx": True, "rx": True, "freq_range_mhz": (2400.0, 2483.5)}, "tag": tag}


@pytest.fixture
def _isolate():
    """用例间隔离共享注册表：就地清空，用毕按快照原样还原（同一 dict 对象）。"""
    saved = dict(REGISTRY)
    REGISTRY.clear()
    yield REGISTRY
    REGISTRY.clear()
    REGISTRY.update(saved)


def test_slot_registry_register_adds_name_to_available(_isolate):
    out = manage_backend_registry("register", "sim", _factory("sim"), _meta("sim"))
    assert out["registered"] is True
    assert out["replaced"] is False
    assert "sim" in out["available"]


def test_slot_registry_lookup_returns_factory_and_meta_identity(_isolate):
    factory, meta = _factory("b210"), _meta("b210")
    manage_backend_registry("register", "b210", factory, meta)
    out = manage_backend_registry("lookup", "b210")
    assert out["factory"] is factory
    assert out["meta"] is meta


def test_slot_registry_list_returns_full_metas(_isolate):
    m_b210, m_sim = _meta("b210"), _meta("sim")
    manage_backend_registry("register", "b210", _factory("b210"), m_b210)
    manage_backend_registry("register", "sim", _factory("sim"), m_sim)
    out = manage_backend_registry("list")
    assert out["available"] == ["b210", "sim"]
    assert out["metas"] == {"b210": m_b210, "sim": m_sim}


def test_slot_registry_invalid_action_lists_legal_actions(_isolate):
    for bad in ("destroy", ""):
        with pytest.raises(BackendError, match="register.*lookup.*list"):
            manage_backend_registry(bad, "sim")


def test_slot_registry_non_str_action_rejected(_isolate):
    for bad in (None, 7, ["register"], b"register"):
        with pytest.raises(BackendError, match="合法取值"):
            manage_backend_registry(bad)


def test_slot_registry_register_missing_name_rejected(_isolate):
    with pytest.raises(BackendError, match="name"):
        manage_backend_registry("register", factory=_factory("x"), meta=_meta("x"))


def test_slot_registry_lookup_missing_name_rejected(_isolate):
    with pytest.raises(BackendError, match="name"):
        manage_backend_registry("lookup")


def test_slot_registry_lookup_unknown_name_hint_passthrough(_isolate):
    manage_backend_registry("register", "sim", _factory("sim"), _meta("sim"))
    with pytest.raises(BackendError, match="simx.*sim"):
        manage_backend_registry("lookup", "simx")


def test_slot_registry_override_chain_replaces_factory(_isolate):
    old, new = _factory("old"), _factory("new")
    manage_backend_registry("register", "sim", old, _meta("old"))
    with pytest.raises(BackendError, match="override"):
        manage_backend_registry("register", "sim", new, _meta("new"))
    out = manage_backend_registry("register", "sim", new, _meta("new"), override=True)
    assert out["replaced"] is True
    assert "sim" in out["available"]
    assert manage_backend_registry("lookup", "sim")["factory"] is new


def test_slot_registry_list_empty_registry(_isolate):
    assert manage_backend_registry("list") == {"available": [], "metas": {}}


def test_slot_registry_lookup_reserved_auto_returns_none_factory(_isolate):
    out = manage_backend_registry("lookup", "auto")
    assert out["factory"] is None
    assert out["meta"]["alias"] == "auto"
