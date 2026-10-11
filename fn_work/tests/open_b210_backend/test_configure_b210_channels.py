"""configure_b210_channels 对抗单测（slug=backend_b210 的双通道参数下发/回读校验叶子）。"""
import pytest

from src.manage_backend_registry.register_backend import BackendError
from src.open_b210_backend.configure_b210_channels import configure_b210_channels

# FakeDevice 可挂载的方法全集（tx/rx 五参数 setter+getter，外加时钟两 setter）。
_ALL_METHODS = tuple(
    f"{verb}_{prefix}_{suffix}"
    for verb in ("set", "get")
    for prefix in ("tx", "rx")
    for suffix in ("freq", "gain", "rate", "bandwidth", "antenna")
) + ("set_clock_source", "set_time_source")


class FakeDevice:
    """鸭子设备句柄：setter 记录调用并存值；getter 回读存值（可加偏移/直接覆盖/返回 NaN），
    亦可按名整方法缺失（模拟句柄不带该能力）。"""

    def __init__(
        self,
        *,
        readback_offsets=None,
        readback_overrides=None,
        nan_getters=(),
        missing=(),
    ):
        self.set_calls = {}  # setter 名 -> 最后一次下发的值
        self._store = {}  # getter 名 -> 存值
        self._offsets = readback_offsets or {}
        self._overrides = readback_overrides or {}
        self._nan = set(nan_getters)
        absent = set(missing)
        for name in _ALL_METHODS:
            if name in absent:
                continue
            if name.startswith("set_"):
                setattr(self, name, self._make_setter(name))
            else:
                setattr(self, name, self._make_getter(name))

    def _make_setter(self, name):
        def setter(value, _name=name):
            self.set_calls[_name] = value
            self._store["get_" + _name[4:]] = value

        return setter

    def _make_getter(self, name):
        def getter(_name=name):
            if _name in self._nan:
                return float("nan")
            if _name in self._overrides:
                return self._overrides[_name]
            value = self._store.get(_name)
            offset = self._offsets.get(_name, 0)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return value + offset
            return value

        return getter


def _full_params():
    return {
        "ch1_tx": {
            "freq_hz": 2_450_000_000.0,
            "gain_db": 30.0,
            "sample_rate": 1_000_000.0,
            "bandwidth_hz": 20_000_000.0,
            "antenna": "TX/RX",
        },
        "ch2_rx": {
            "freq_hz": 2_450_000_000.0,
            "gain_db": 25.0,
            "sample_rate": 1_000_000.0,
            "bandwidth_hz": 20_000_000.0,
            "antenna": "RX2",
        },
        "clock_ref": "internal",
    }


def test_full_params_apply_and_readback_match():
    dev = FakeDevice()
    params = _full_params()
    result = configure_b210_channels(dev, params)
    assert result["applied"] == {"ch1_tx": params["ch1_tx"], "ch2_rx": params["ch2_rx"]}
    assert result["skipped"] == []
    assert result["clock_ref"] == "internal"
    assert dev.set_calls["set_tx_freq"] == params["ch1_tx"]["freq_hz"]
    assert dev.set_calls["set_tx_gain"] == 30.0
    assert dev.set_calls["set_tx_rate"] == 1_000_000.0
    assert dev.set_calls["set_tx_bandwidth"] == 20_000_000.0
    assert dev.set_calls["set_tx_antenna"] == "TX/RX"
    assert dev.set_calls["set_rx_antenna"] == "RX2"
    assert dev.set_calls["set_clock_source"] == "internal"
    assert dev.set_calls["set_time_source"] == "internal"


def test_freq_readback_off_by_2hz_rejected_with_both_values():
    dev = FakeDevice(readback_offsets={"get_tx_freq": 2.0})
    params = _full_params()
    with pytest.raises(BackendError) as excinfo:
        configure_b210_channels(dev, params)
    msg = str(excinfo.value)
    assert "ch1_tx.freq_hz" in msg
    assert repr(params["ch1_tx"]["freq_hz"]) in msg  # 下发值
    assert repr(params["ch1_tx"]["freq_hz"] + 2.0) in msg  # 回读值


def test_gain_readback_off_by_0p6db_rejected():
    dev = FakeDevice(readback_offsets={"get_rx_gain": 0.6})
    with pytest.raises(BackendError) as excinfo:
        configure_b210_channels(dev, _full_params())
    assert "ch2_rx.gain_db" in str(excinfo.value)


def test_gain_readback_off_exactly_0p5db_passes_boundary():
    dev = FakeDevice(readback_offsets={"get_tx_gain": 0.5})  # 恰在容差边界内（"超容差"才拒）
    result = configure_b210_channels(dev, _full_params())
    assert result["applied"]["ch1_tx"]["gain_db"] == pytest.approx(30.5)


def test_bandwidth_readback_off_2pct_rejected():
    dev = FakeDevice(readback_offsets={"get_tx_bandwidth": 0.02 * 20_000_000.0})
    with pytest.raises(BackendError) as excinfo:
        configure_b210_channels(dev, _full_params())
    assert "ch1_tx.bandwidth_hz" in str(excinfo.value)


def test_bandwidth_readback_off_exactly_1pct_passes_boundary():
    dev = FakeDevice(readback_offsets={"get_tx_bandwidth": 200_000.0})  # 20e6 的 1%
    result = configure_b210_channels(dev, _full_params())
    assert result["applied"]["ch1_tx"]["bandwidth_hz"] == pytest.approx(20_200_000.0)


def test_missing_antenna_methods_recorded_skipped():
    dev = FakeDevice(missing=("set_tx_antenna", "get_tx_antenna"))
    params = _full_params()
    result = configure_b210_channels(dev, params)
    assert "ch1_tx.antenna:set_tx_antenna" in result["skipped"]
    assert "antenna" not in result["applied"]["ch1_tx"]
    assert result["applied"]["ch1_tx"]["freq_hz"] == params["ch1_tx"]["freq_hz"]
    assert "set_tx_antenna" not in dev.set_calls
    assert result["applied"]["ch2_rx"]["antenna"] == "RX2"  # rx 侧不受影响


def test_missing_ch2_only_ch1_applied():
    dev = FakeDevice()
    params = _full_params()
    del params["ch2_rx"]
    result = configure_b210_channels(dev, params)
    assert "ch2_rx" in result["skipped"]
    assert set(result["applied"]) == {"ch1_tx"}
    assert not any(name.startswith("set_rx_") for name in dev.set_calls)
    assert result["clock_ref"] == "internal"


@pytest.mark.parametrize("bad_freq", [69_999_999.0, 6_000_000_001.0])
def test_freq_out_of_range_valueerror_without_device_calls(bad_freq):
    dev = FakeDevice()
    params = _full_params()
    params["ch1_tx"]["freq_hz"] = bad_freq
    with pytest.raises(ValueError, match="freq_hz"):
        configure_b210_channels(dev, params)
    assert dev.set_calls == {}  # 域校验先行：失败路径零设备副作用


def test_negative_rate_valueerror():
    dev = FakeDevice()
    params = _full_params()
    params["ch2_rx"]["sample_rate"] = -1_000_000.0
    with pytest.raises(ValueError, match="sample_rate"):
        configure_b210_channels(dev, params)
    assert dev.set_calls == {}


def test_gain_90_valueerror():
    dev = FakeDevice()
    params = _full_params()
    params["ch1_tx"]["gain_db"] = 90.0
    with pytest.raises(ValueError, match="gain_db"):
        configure_b210_channels(dev, params)
    assert dev.set_calls == {}


def test_illegal_antenna_valueerror():
    dev = FakeDevice()
    params = _full_params()
    params["ch1_tx"]["antenna"] = "tx/rx"  # 白名单大小写敏感
    with pytest.raises(ValueError, match="antenna"):
        configure_b210_channels(dev, params)
    assert dev.set_calls == {}


def test_clock_ref_gpsdo_passed_through():
    dev = FakeDevice()
    params = _full_params()
    params["clock_ref"] = "gpsdo"
    result = configure_b210_channels(dev, params)
    assert dev.set_calls["set_clock_source"] == "gpsdo"
    assert dev.set_calls["set_time_source"] == "gpsdo"
    assert result["clock_ref"] == "gpsdo"


def test_clock_ref_illegal_valueerror():
    dev = FakeDevice()
    params = _full_params()
    params["clock_ref"] = "magma"
    with pytest.raises(ValueError, match="clock_ref"):
        configure_b210_channels(dev, params)
    assert dev.set_calls == {}


@pytest.mark.parametrize("bad_params", [None, [], "ch1_tx", 42])
def test_params_not_dict_valueerror(bad_params):
    with pytest.raises(ValueError, match="params"):
        configure_b210_channels(FakeDevice(), bad_params)


def test_nan_readback_rejected_as_backend_error():
    # NaN 与任何容差比较恒为 False：若未先判 isfinite，nan 会静默通过比较混入 applied。
    dev = FakeDevice(nan_getters=("get_tx_rate",))
    with pytest.raises(BackendError) as excinfo:
        configure_b210_channels(dev, _full_params())
    msg = str(excinfo.value)
    assert "ch1_tx.sample_rate" in msg
    assert "nan" in msg


def test_antenna_readback_mismatch_rejected_with_both_values():
    dev = FakeDevice(readback_overrides={"get_tx_antenna": "RX2"})
    with pytest.raises(BackendError) as excinfo:
        configure_b210_channels(dev, _full_params())
    msg = str(excinfo.value)
    assert "ch1_tx.antenna" in msg
    assert "TX/RX" in msg and "RX2" in msg


def test_missing_clock_methods_skipped_and_clock_ref_none():
    dev = FakeDevice(missing=("set_clock_source", "set_time_source"))
    params = _full_params()
    result = configure_b210_channels(dev, params)
    assert "clock_ref:set_clock_source" in result["skipped"]
    assert "clock_ref:set_time_source" in result["skipped"]
    assert result["clock_ref"] is None
    # 通道下发不受时钟方法缺失影响
    assert result["applied"]["ch1_tx"]["freq_hz"] == params["ch1_tx"]["freq_hz"]


def test_partial_channel_params_record_missing_keys_skipped():
    dev = FakeDevice()
    params = {"ch1_tx": {"freq_hz": 100_000_000.0}}  # 其余子键缺 -> 各自 skipped
    result = configure_b210_channels(dev, params)
    assert result["skipped"] == [
        "ch1_tx.gain_db",
        "ch1_tx.sample_rate",
        "ch1_tx.bandwidth_hz",
        "ch1_tx.antenna",
        "ch2_rx",
    ]
    assert result["applied"] == {"ch1_tx": {"freq_hz": 100_000_000.0}}
    assert result["clock_ref"] is None
    assert dev.set_calls == {"set_tx_freq": 100_000_000.0}


# ---- B5 对抗审查缺陷回归（中#1 setter 异常契约 / 中#3 域校验对齐真机 /
# ---- 低#6 未知键记 skipped / 低#7 skipped 语义拆分 unverified）----


def test_defect_b5_1_setter_exception_wrapped_backend_error_with_cause():
    """中#1：setter 抛 UHD 异常 → BackendError（含原文与方法名），__cause__ 保留。"""
    dev = FakeDevice()

    def boom(value):
        raise RuntimeError("UHD RuntimeError: assert failed: 0.0 < freq")

    dev.set_tx_freq = boom
    with pytest.raises(BackendError) as excinfo:
        configure_b210_channels(dev, _full_params())
    msg = str(excinfo.value)
    assert "ch1_tx.freq_hz" in msg
    assert "set_tx_freq" in msg
    assert "UHD RuntimeError" in msg  # UHD 原文并入消息
    assert isinstance(excinfo.value.__cause__, RuntimeError)  # 原因链保留


def test_defect_b5_1_getter_exception_wrapped_backend_error():
    """中#1：getter 抛异常同样入 BackendError 契约（非裸穿 AttributeError/RuntimeError）。"""
    dev = FakeDevice()

    def boom():
        raise RuntimeError("UHD io fault on get_tx_gain")

    dev.get_tx_gain = boom
    with pytest.raises(BackendError) as excinfo:
        configure_b210_channels(dev, _full_params())
    msg = str(excinfo.value)
    assert "ch1_tx.gain_db" in msg
    assert "get_tx_gain" in msg
    assert "UHD io fault" in msg
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_defect_b5_3_tx_antenna_whitelist_only_tx_rx():
    """中#3：tx 天线白名单 {'TX/RX'}——'RX2'/'RX1'/'TX' 一律域校验期即拒（零设备副作用）。"""
    for bad in ("RX2", "RX1", "TX"):
        dev = FakeDevice()
        params = _full_params()
        params["ch1_tx"]["antenna"] = bad
        with pytest.raises(ValueError, match="antenna"):
            configure_b210_channels(dev, params)
        assert dev.set_calls == {}


def test_defect_b5_3_rx_antenna_whitelist_tx_rx_or_rx2_rejects_rx1():
    """中#3：rx 天线白名单 {'TX/RX','RX2'}——'RX1' 已移除（非真机端口名）。"""
    result = configure_b210_channels(FakeDevice(), _full_params())  # 默认 rx 用 RX2：合法
    assert result["applied"]["ch2_rx"]["antenna"] == "RX2"
    dev = FakeDevice()
    params = _full_params()
    params["ch2_rx"]["antenna"] = "RX1"
    with pytest.raises(ValueError, match="antenna"):
        configure_b210_channels(dev, params)
    assert dev.set_calls == {}
    # 'TX/RX' 同时在收发白名单（双工共用端口）
    params["ch2_rx"]["antenna"] = "TX/RX"
    assert configure_b210_channels(dev, params)["applied"]["ch2_rx"]["antenna"] == "TX/RX"


def test_defect_b5_3_rx_gain_cap_76_tx_gain_cap_89_75():
    """中#3：增益上界按通道分设——rx 0–76 / tx 0–89.75（80dB 对 rx 拒、对 tx 域内）。"""
    dev = FakeDevice()
    params = _full_params()
    params["ch2_rx"]["gain_db"] = 76.0  # 恰 rx 上界：合法
    result = configure_b210_channels(dev, params)
    assert result["applied"]["ch2_rx"]["gain_db"] == pytest.approx(76.0)

    dev2 = FakeDevice()
    params2 = _full_params()
    params2["ch2_rx"]["gain_db"] = 80.0  # rx 上界 76 外（虽在旧统一域 89.75 内）→ ValueError
    with pytest.raises(ValueError, match="gain_db"):
        configure_b210_channels(dev2, params2)
    assert dev2.set_calls == {}

    dev3 = FakeDevice()
    params3 = _full_params()
    params3["ch1_tx"]["gain_db"] = 89.75  # tx 上界 89.75：合法
    result3 = configure_b210_channels(dev3, params3)
    assert result3["applied"]["ch1_tx"]["gain_db"] == pytest.approx(89.75)


def test_defect_b5_6_unknown_subkey_and_top_level_key_recorded_skipped():
    """低#6：通道 cfg 未知子键与顶层未知键各记 skipped（':unknown_key' 后缀），不炸不阻断。"""
    dev = FakeDevice()
    params = {
        "ch1_tx": {"freq_hz": 100_000_000.0, "freq_mhz": 2450.0},
        "ch2_rx": {"agc": True},
        "agc_mode": "fast",
    }
    result = configure_b210_channels(dev, params)
    assert "ch1_tx.freq_mhz:unknown_key" in result["skipped"]
    assert "ch2_rx.agc:unknown_key" in result["skipped"]
    assert "agc_mode:unknown_key" in result["skipped"]
    # 已知键照常下发：未知键不阻断既有参数
    assert dev.set_calls["set_tx_freq"] == 100_000_000.0
    assert result["applied"]["ch1_tx"]["freq_hz"] == 100_000_000.0
    # 未知键不进 applied / unverified
    assert "freq_mhz" not in result["applied"]["ch1_tx"]
    assert result["unverified"] == []


def test_defect_b5_7_getter_missing_unverified_with_applied_dispatched_value():
    """低#7：setter 在 getter 缺 → 已下发未确认记 unverified（非 skipped），applied 记下发值。"""
    dev = FakeDevice(missing=("get_tx_freq",))
    params = _full_params()
    result = configure_b210_channels(dev, params)
    assert "ch1_tx.freq_hz:get_tx_freq" in result["unverified"]
    assert "ch1_tx.freq_hz:get_tx_freq" not in result["skipped"]  # 语义拆分：不再混入 skipped
    assert dev.set_calls["set_tx_freq"] == params["ch1_tx"]["freq_hz"]  # 确已下发
    assert result["applied"]["ch1_tx"]["freq_hz"] == params["ch1_tx"]["freq_hz"]  # 记下发值
    # 其余参数正常回读确认：不进 unverified
    assert "ch1_tx.gain_db" not in [s.split(":")[0] for s in result["unverified"]]
    # 对照：setter 缺（未下发）仍走 skipped
    dev2 = FakeDevice(missing=("set_tx_freq",))
    result2 = configure_b210_channels(dev2, params)
    assert "ch1_tx.freq_hz:set_tx_freq" in result2["skipped"]
    assert "freq_hz" not in result2["applied"]["ch1_tx"]
