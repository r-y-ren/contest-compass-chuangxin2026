"""open_sim_emi_receiver 对抗测试：验收 slug=sim_emi_receiver——频段边界/底噪公式/三检波关系/QP 重频曲线/RBW 缺省与参数化/模拟标记/能力与注册集成/no_tx/工厂校验/单音峰定位。"""
import importlib
import math

import pytest

from src.manage_backend_registry.register_backend import REGISTRY, BackendError
from src.manage_backend_registry.lookup_backend import lookup_backend

# 被测模块延迟到 run 阶段才 import：其 import 期向全局 REGISTRY 自注册 'sim_emi_receiver'，
# 若在 collection 期导入，会让字母序在前、对注册表内容做精确断言的
# manage_backend_registry 用例（相近名提示列表/空表文案）误红。
@pytest.fixture(scope="module", autouse=True)
def _load_backend_module():
    mod = importlib.import_module("src.open_sim_emi_receiver.open_sim_emi_receiver")
    globals()["SimEmiReceiver"] = mod.SimEmiReceiver
    globals()["open_sim_emi_receiver"] = mod.open_sim_emi_receiver
    return mod


def _tone(n: int, bin_index: int, amplitude: float = 1.0) -> list[complex]:
    """bin 恰对齐的单位复单音（n 采样、频率 bin_index·fs/n）。"""
    return [
        amplitude * complex(
            math.cos(2.0 * math.pi * bin_index * k / n),
            math.sin(2.0 * math.pi * bin_index * k / n),
        )
        for k in range(n)
    ]


def _argmax(values: list[float]) -> int:
    return max(range(len(values)), key=values.__getitem__)


def test_sim_emi_receiver_band_boundary_exact_pass_outside_reject():
    # 用例1: 频段边界恰过（1e3 与 3e9 闭区间合法），域外/非有限/bool 拒收
    assert open_sim_emi_receiver({"freq_hz": 1e3}).freq_hz == 1e3
    assert open_sim_emi_receiver({"freq_hz": 3e9}).freq_hz == 3e9
    for bad in (999.0, 0.0, -1e3, 3.0000001e9, 1e12, float("inf"), float("nan"), True, "10MHz"):
        with pytest.raises(ValueError):
            open_sim_emi_receiver({"freq_hz": bad})


def test_sim_emi_receiver_none_input_noise_floor_formula():
    # 用例2: measure(None) 底噪口径 = −150 + 10·log10(rbw)；缺省频段（10MHz→9kHz RBW）
    rx = open_sim_emi_receiver()  # params 缺省 None 亦可
    reading = rx.measure(None)
    assert reading["power_dbm"] == pytest.approx(-150.0 + 10.0 * math.log10(9e3))
    assert reading["freq_mhz"] == pytest.approx(10.0)
    assert reading["rbw_hz"] == 9e3
    assert reading["noise_floor_dbm_hz"] == -150.0
    assert reading["detector"] == "peak"
    assert rx.read_samples() == reading  # rx 契约适配等价 measure(None)


def test_sim_emi_receiver_detector_ordering_peak_ge_qp_ge_average():
    # 用例3: 脉冲 IQ（仅 1/4 帧含单音）：peak ≥ quasi_peak ≥ average（单音 bin 上逐口径核验）
    rx = open_sim_emi_receiver({"freq_hz": 10e6, "sample_rate": 64e3, "rep_hz": 1e3})
    iq = _tone(64, 8) + [0j] * 192  # 4 帧×64 样本，仅首帧含单音（幅度 1.0 → 0 dBm）
    rx.set_detector("peak")
    peak = rx.measure(iq)["power_dbm"]
    rx.set_detector("quasi_peak")
    qp = rx.measure(iq)["power_dbm"]
    rx.set_detector("average")
    avg = rx.measure(iq)["power_dbm"]
    i = _argmax(peak)
    assert i == 8
    assert peak[i] == pytest.approx(0.0, abs=1e-6)  # 幅度口径：单音幅度 1.0 → 0 dBm
    # QP 简化曲线：rep=1kHz → 衰减 5·log10(1+1000/1000)=5·log10(2)≈1.505 dB
    assert qp[i] == pytest.approx(peak[i] - 5.0 * math.log10(2.0), abs=1e-6)
    # average：4 帧仅 1 帧有信号 → 线性均值 1/4 → −10·log10(4)≈−6.02 dB
    assert avg[i] == pytest.approx(peak[i] - 10.0 * math.log10(4.0), abs=1e-6)
    assert peak[i] >= qp[i] >= avg[i]


def test_sim_emi_receiver_qp_lower_rep_more_attenuation():
    # 用例4: QP 简化曲线低重频衰减多：rep=10Hz 比 rep=1kHz 多衰减 5·(log10(101)−log10(2))≈8.52 dB
    common = {"freq_hz": 10e6, "sample_rate": 64e3, "detector": "quasi_peak"}
    rx_low = open_sim_emi_receiver({**common, "rep_hz": 10.0})
    rx_high = open_sim_emi_receiver({**common, "rep_hz": 1e3})
    iq = _tone(64, 8) * 4  # 连续单音（各帧等幅）
    low = rx_low.measure(iq)["power_dbm"]
    high = rx_high.measure(iq)["power_dbm"]
    i = _argmax(high)
    assert i == 8
    assert low[i] < high[i]
    assert high[i] - low[i] == pytest.approx(
        5.0 * (math.log10(101.0) - math.log10(2.0)), abs=1e-6
    )
    assert low[i] == pytest.approx(-5.0 * math.log10(101.0), abs=1e-6)


def test_sim_emi_receiver_default_rbw_band_auto():
    # 用例5: RBW 频段缺省自动：<30MHz→9kHz、恰 30MHz 及以上→120kHz；显式给值优先
    assert open_sim_emi_receiver({"freq_hz": 1e3}).measure(None)["rbw_hz"] == 9e3
    assert open_sim_emi_receiver({"freq_hz": 29.999999e6}).measure(None)["rbw_hz"] == 9e3
    assert open_sim_emi_receiver({"freq_hz": 30e6}).measure(None)["rbw_hz"] == 120e3
    assert open_sim_emi_receiver({"freq_hz": 3e9}).measure(None)["rbw_hz"] == 120e3
    assert open_sim_emi_receiver({"freq_hz": 5e6, "rbw_hz": 200.0}).measure(None)["rbw_hz"] == 200.0


def test_sim_emi_receiver_set_rbw_parameterized():
    # 用例6: set_rbw 生效并联动底噪读数；None 恢复频段缺省；非正/非实数/bool 拒收
    rx = open_sim_emi_receiver({"freq_hz": 10e6})
    assert rx.set_rbw(3e3) == 3e3
    assert rx.measure(None)["power_dbm"] == pytest.approx(-150.0 + 10.0 * math.log10(3e3))
    assert rx.set_rbw(None) == 9e3  # 恢复 <30MHz 频段缺省
    assert rx.set_rbw(120e3) == 120e3
    for bad in (0.0, -9e3, float("inf"), "9k", True):
        with pytest.raises(ValueError):
            rx.set_rbw(bad)


def test_sim_emi_receiver_readings_carry_simulated_marker_and_cispr_note():
    # 用例7: 两种读数路径（None 底噪 / IQ 频域）均恒带 simulated=True 与 cispr_note，键集恰为规约七键
    rx = open_sim_emi_receiver({"freq_hz": 10e6, "sample_rate": 64e3})
    expected_keys = {
        "freq_mhz", "power_dbm", "detector", "rbw_hz",
        "noise_floor_dbm_hz", "simulated", "cispr_note",
    }
    floor_reading = rx.measure(None)
    assert set(floor_reading) == expected_keys
    assert floor_reading["simulated"] is True
    assert floor_reading["cispr_note"] == "模拟读数——非 CISPR 16-1-1 测量接收机"
    rx.set_detector("quasi_peak")
    iq_reading = rx.measure(_tone(64, 8) * 4)
    assert set(iq_reading) == expected_keys
    assert iq_reading["simulated"] is True
    assert iq_reading["cispr_note"] == "模拟读数——非 CISPR 16-1-1 测量接收机"
    assert isinstance(iq_reading["freq_mhz"], list) and isinstance(iq_reading["power_dbm"], list)
    assert len(iq_reading["freq_mhz"]) == len(iq_reading["power_dbm"]) == 64


def test_sim_emi_receiver_capabilities_structure():
    # 用例8: capabilities 结构（频段/检波器全集/底噪/仿真标记），且每次返回副本可安全篡改
    rx = open_sim_emi_receiver()
    caps = rx.capabilities()
    assert caps == {
        "freq_range_hz": (1e3, 3e9),
        "detectors": ["peak", "quasi_peak", "average"],
        "noise_floor_dbm_hz": -150.0,
        "simulated": True,
    }
    caps["simulated"] = False
    caps["detectors"].append("rms")
    fresh = rx.capabilities()
    assert fresh["simulated"] is True  # 副本：篡改不回写
    assert fresh["detectors"] == ["peak", "quasi_peak", "average"]


def test_sim_emi_receiver_registered_in_registry_lookup_and_instantiate():
    # 用例9（集成）: REGISTRY 登记 'sim_emi_receiver'，lookup 取回工厂与 caps 契约，工厂可实例化且接口齐备
    assert "sim_emi_receiver" in REGISTRY
    factory, meta = lookup_backend("sim_emi_receiver")
    assert callable(factory)
    assert meta["caps"] == {"tx": False, "rx": True, "freq_range_mhz": (1, 3000)}
    inst = factory({"freq_hz": 100e6, "detector": "average"})
    assert isinstance(inst, SimEmiReceiver)
    assert inst.measure(None)["rbw_hz"] == 120e3  # 100MHz → 频段缺省 120kHz
    for name in (
        "measure", "set_detector", "set_rbw", "read_samples",
        "start_tx", "stop_tx", "set_tx_gain", "capabilities",
    ):
        assert callable(getattr(inst, name))
    assert isinstance(factory(None), SimEmiReceiver)  # 工厂 params=None 缺省口径亦可


def test_sim_emi_receiver_no_tx_semantics():
    # 用例10: no_tx 语义——start_tx 明确报错（BackendError）；stop_tx/set_tx_gain 返回 no_tx 并记事件
    rx = open_sim_emi_receiver()
    with pytest.raises(BackendError, match="无发射能力"):
        rx.start_tx([[1 + 0j] * 16])
    assert rx.stop_tx() == {"status": "no_tx"}
    assert rx.set_tx_gain(30) == {"status": "no_tx"}
    assert len(rx.events) == 2
    assert all("无发射能力" in e for e in rx.events)


def test_sim_emi_receiver_set_detector_invalid_rejected():
    # 用例11: 检波器非法拒收（未知名/大小写变体/非 str/不可哈希对象均 ValueError），三合法名往返生效
    rx = open_sim_emi_receiver()
    for bad in ("rms", "PEAK", "Quasi_Peak", "", None, 3, ["peak"]):
        with pytest.raises(ValueError):
            rx.set_detector(bad)
    for ok in ("peak", "quasi_peak", "average"):
        assert rx.set_detector(ok) == ok
        assert rx.measure(None)["detector"] == ok


def test_sim_emi_receiver_factory_initial_values_and_validation():
    # 用例12: 工厂初值（freq=10e6/detector=peak/rbw=9k/rep=100/fs=1e6）、显式覆盖生效、非法参数拒收
    rx = open_sim_emi_receiver()
    assert rx.freq_hz == 10e6
    assert rx.capabilities()["simulated"] is True
    assert rx.measure(None)["detector"] == "peak" and rx.measure(None)["rbw_hz"] == 9e3
    assert rx.rep_hz == 100.0 and rx.sample_rate == 1e6
    rx2 = open_sim_emi_receiver(
        {"freq_hz": 2.45e9, "detector": "quasi_peak", "rbw_hz": 120e3,
         "rep_hz": 500.0, "sample_rate": 4e6}
    )
    assert (rx2.freq_hz, rx2.rep_hz, rx2.sample_rate) == (2.45e9, 500.0, 4e6)
    assert rx2.measure(None)["detector"] == "quasi_peak"
    assert rx2.measure(None)["rbw_hz"] == 120e3
    for bad_params in (
        "fast", 42, [()],  # params 非 dict|None
        {"detector": "max_hold"}, {"rbw_hz": 0.0}, {"rbw_hz": -9e3}, {"rbw_hz": True},
        {"rep_hz": 0.0}, {"sample_rate": -1.0}, {"rep_hz": float("nan")},
    ):
        with pytest.raises(ValueError):
            open_sim_emi_receiver(bad_params)


def test_sim_emi_receiver_single_tone_peak_located():
    # 用例13: 给 IQ 单音峰定位——argmax bin 恰落单音频点（中心+bin·fs/N），幅值口径 0.5→−6.02 dBm
    fs = 256e3
    rx = open_sim_emi_receiver({"freq_hz": 100e6, "sample_rate": fs, "detector": "peak"})
    iq = _tone(64, 8, amplitude=0.5) * 4  # 4 帧×64 样本，单音在 bin 8 → 偏移 +fs/8=32kHz
    reading = rx.measure(iq)
    power = reading["power_dbm"]
    i = _argmax(power)
    assert i == 8
    assert reading["freq_mhz"][i] == pytest.approx((100e6 + 32e3) / 1e6)
    assert reading["freq_mhz"][0] == pytest.approx(100.0)  # DC bin 映射到中心频率
    assert power[i] == pytest.approx(10.0 * math.log10(0.5 ** 2), abs=1e-6)  # ≈ −6.02 dBm
    # 非 4 帧整除的尾样本与过短序列口径：余数样本不计入（259=4×64+3 → 仍 64 bin），<4 样本拒绝
    assert len(rx.measure(_tone(64, 8) * 4 + [0j] * 3)["power_dbm"]) == 64
    with pytest.raises(ValueError):
        rx.measure([1 + 0j, 2 + 0j])
    with pytest.raises(ValueError):
        rx.measure("not-iq")
    with pytest.raises(ValueError):
        rx.measure([1 + 0j, "x", 3 + 0j, 4 + 0j])
