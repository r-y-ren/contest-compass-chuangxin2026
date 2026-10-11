"""register_backend 单元测试——工厂登记/重名覆盖/契约形式检查/入参形式校验。"""
import pytest

from src.manage_backend_registry.register_backend import (
    REGISTRY,
    BackendError,
    register_backend,
)

# tx+rx 双能力后端的约定方法全集
TX_RX_METHODS = ["start_tx", "stop_tx", "set_tx_gain", "read_samples"]


def _full_meta() -> dict:
    """tx+rx 双能力元数据（含必填 caps）。"""
    return {
        "caps": {
            "tx": True,
            "rx": True,
            "freq_range_mhz": (2400.0, 2483.5),
        }
    }


def _factory():
    return object()


@pytest.fixture(autouse=True)
def _isolate():
    """用例间隔离全局注册表：进入前清空、结束后按快照还原（同一 dict 对象）。

    只"事后还原"不够——其他后端模块（open_sim_backend/open_replay_backend）import 期
    会向 REGISTRY 自注册，若本文件用例在组合运行（如 pytest tests/manage_backend_registry
    tests/open_sim_backend）时假定注册表起始为空（无 override 登记 / 拒绝后不在表断言），
    会被预置的 'sim'/'replay' 干扰；进入前清空保证任意子集、任意顺序下都稳定。
    """
    saved = dict(REGISTRY)
    REGISTRY.clear()
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


def test_register_normal_entry_queryable():
    # 用例1: 正常登记+注册表可查
    result = register_backend("sim", _factory, _full_meta(), method_names=list(TX_RX_METHODS))
    assert result == {"registered": True, "replaced": False}
    entry = REGISTRY["sim"]
    assert entry["factory"] is _factory
    assert entry["meta"]["caps"]["tx"] is True
    assert entry["meta"]["caps"]["rx"] is True
    assert entry["meta"]["caps"]["freq_range_mhz"] == (2400.0, 2483.5)


def test_duplicate_name_rejected_without_override():
    # 用例2: 重名默认拒绝，且原登记不被破坏
    register_backend("b210", _factory, _full_meta(), method_names=list(TX_RX_METHODS))
    replacement = lambda: None  # noqa: E731
    with pytest.raises(BackendError):
        register_backend("b210", replacement, _full_meta(), method_names=list(TX_RX_METHODS))
    assert REGISTRY["b210"]["factory"] is _factory


def test_override_replaces_existing():
    # 用例3: 显式 override=True 覆盖，replaced=True 且指向新工厂
    register_backend("replay", _factory, _full_meta(), method_names=list(TX_RX_METHODS))
    replacement = lambda: None  # noqa: E731
    result = register_backend(
        "replay", replacement, _full_meta(), override=True, method_names=list(TX_RX_METHODS)
    )
    assert result == {"registered": True, "replaced": True}
    assert REGISTRY["replay"]["factory"] is replacement


@pytest.mark.parametrize("bad_name", ["", "   ", None, 123, True])
def test_invalid_name_rejected(bad_name):
    # 用例4: 名称空/空白/非 str（None/int/bool）一律拒，注册表无半写
    before = dict(REGISTRY)
    with pytest.raises(BackendError):
        register_backend(bad_name, _factory, _full_meta())
    assert REGISTRY == before


def test_factory_not_callable_rejected():
    # 用例5: factory 非 callable 拒
    before = dict(REGISTRY)
    with pytest.raises(BackendError):
        register_backend("sim", 42, _full_meta())
    assert REGISTRY == before


def test_unknown_method_name_rejected():
    # 用例6: method_names 含未约定方法名（'hack'）拒，不登记
    with pytest.raises(BackendError):
        register_backend("sim", _factory, _full_meta(), method_names=["start_tx", "hack"])
    assert "sim" not in REGISTRY


def test_method_names_none_skips_contract_check():
    # 用例7: method_names 缺省（None）跳过契约形式检查（延迟到首次实例化）
    result = register_backend("sim", _factory, _full_meta())
    assert result == {"registered": True, "replaced": False}
    assert REGISTRY["sim"]["factory"] is _factory


def test_meta_missing_caps_rejected():
    # 用例8: meta 缺 caps 键拒（caps 必填），meta 非 dict 同拒
    before = dict(REGISTRY)
    for bad_meta in ({}, {"freq_range_mhz": (2400.0, 2483.5)}, ["caps"]):
        with pytest.raises(BackendError):
            register_backend("sim", _factory, bad_meta)
    assert REGISTRY == before


def test_declared_cap_missing_methods_rejected():
    # 用例9: caps 声明 tx=True 但 method_names 缺 stop_tx/set_tx_gain 拒
    meta = {"caps": {"tx": True, "rx": False, "freq_range_mhz": (2400.0, 2483.5)}}
    with pytest.raises(BackendError):
        register_backend("sim", _factory, meta, method_names=["start_tx"])
    assert "sim" not in REGISTRY


def test_rx_only_backend_registers_with_rx_methods():
    # 用例10: 仅 rx 能力时，只需 read_samples 即满足契约
    meta = {"caps": {"tx": False, "rx": True, "freq_range_mhz": (2400.0, 2483.5)}}
    result = register_backend("monitor", _factory, meta, method_names=["read_samples"])
    assert result == {"registered": True, "replaced": False}
    assert REGISTRY["monitor"]["meta"] is meta


def test_method_names_not_a_list_rejected():
    # 用例11: method_names 传裸字符串等非列表拒（防逐字符误当方法名）
    before = dict(REGISTRY)
    with pytest.raises(BackendError):
        register_backend("sim", _factory, _full_meta(), method_names="start_tx")
    assert REGISTRY == before


def test_case_insensitive_duplicate_rejected_without_override():
    # 用例12: 重名检查大小写不敏感：'SIM' 与已注册 'sim' 冲突，无 override 即拒、无半写
    register_backend("sim", _factory, _full_meta(), method_names=list(TX_RX_METHODS))
    with pytest.raises(BackendError):
        register_backend("SIM", _factory, _full_meta(), method_names=list(TX_RX_METHODS))
    assert "SIM" not in REGISTRY
    assert REGISTRY["sim"]["factory"] is _factory  # 原登记不被破坏


def test_case_variant_override_replaces_old_key():
    # 用例13: override 授权下大小写变体覆盖：旧键让位（无双键歧义），replaced=True
    register_backend("sim", _factory, _full_meta(), method_names=list(TX_RX_METHODS))
    result = register_backend(
        "Sim", _factory, _full_meta(), override=True, method_names=list(TX_RX_METHODS)
    )
    assert result == {"registered": True, "replaced": True}
    assert list(REGISTRY) == ["Sim"]


@pytest.mark.parametrize("reserved", ["auto", "AUTO", "Auto"], ids=["auto", "AUTO", "Auto"])
def test_auto_reserved_name_rejected(reserved):
    # 用例14: 保留名 'auto'（含大小写变体）注册直接拒（保留给 autodetect_backend 决策路由），
    # override=True 也不放行
    before = dict(REGISTRY)
    with pytest.raises(BackendError):
        register_backend(
            reserved, _factory, _full_meta(), override=True, method_names=list(TX_RX_METHODS)
        )
    assert REGISTRY == before  # 拒绝路径无半写
