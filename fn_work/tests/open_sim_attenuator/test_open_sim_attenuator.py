"""open_sim_attenuator 对抗用例：程控衰减器仿真后端（slug=sim_attenuator，B15/R43）。

覆盖口径：域边界恰过/越域拒（附域文案）；0.25dB half-up 量化；pass_through 真衰减
数学（dB→10^(−att/20) 线性幅度因子，−6dB/75dB 两点+0dB 恒等）；切换记录含标称
nominal_switch_ns=500 与实测非负 switch_delay_ns；幂等重设；capabilities 规格；
REGISTRY 自注册 lookup；工厂初值参数化；鸭子兼容 set_channel_attenuation。
"""
from __future__ import annotations

import pytest

from src.manage_backend_registry.lookup_backend import lookup_backend
from src.manage_backend_registry.register_backend import REGISTRY
from src.open_sim_attenuator.open_sim_attenuator import (
    SimAttenuator,
    open_sim_attenuator,
)


def test_sim_attenuator_range_boundaries_0_and_75_exact_pass():
    dev = SimAttenuator()
    assert dev.set_attenuation(0)["applied_db"] == 0.0
    assert dev.get_attenuation() == 0.0
    assert dev.set_attenuation(75)["applied_db"] == 75.0
    assert dev.get_attenuation() == 75.0


@pytest.mark.parametrize("bad", [76.0, -1.0])
def test_sim_attenuator_out_of_range_76_and_minus1_rejected_with_domain(bad):
    dev = SimAttenuator()
    with pytest.raises(ValueError) as excinfo:
        dev.set_attenuation(bad)
    msg = str(excinfo.value)
    assert "75" in msg and "0" in msg  # 拒绝须附域 [0, 75]
    assert dev.get_attenuation() == 0.0  # 原子拒绝：档位原样保留


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "30"])
def test_sim_attenuator_non_finite_or_non_real_rejected(bad):
    dev = SimAttenuator()
    with pytest.raises(ValueError):
        dev.set_attenuation(bad)


def test_sim_attenuator_quantization_half_up_to_025_grid():
    dev = SimAttenuator()
    # 文档口径 half-up：30.1/0.25=120.4 → 120 步 → 30.0（<0.5 步舍下）
    rec = dev.set_attenuation(30.1)
    assert rec["applied_db"] == 30.0
    assert dev.get_attenuation() == 30.0
    # 30.15/0.25=120.6 → 121 步 → 30.25（>0.5 步入上）
    assert dev.set_attenuation(30.15)["applied_db"] == 30.25
    # 恰半界 30.125 → half-up 上取 30.25
    assert dev.set_attenuation(30.125)["applied_db"] == 30.25
    # 网格值恒为 0.25 整数倍（浮点精确）
    for applied in (0.0, 12.25, 30.0, 74.75, 75.0):
        assert dev.set_attenuation(applied)["applied_db"] * 4 == int(dev.get_attenuation() * 4)


def test_sim_attenuator_pass_through_minus_6db_true_db_math():
    dev = open_sim_attenuator({"attenuation_db": 6.0})
    factor = 10.0 ** (-6.0 / 20.0)  # 真衰减数学：dB→线性幅度因子
    iq = [1.0 + 0.0j, 0.7071 + 0.7071j, -2.5 + 1.25j]
    out = dev.pass_through(iq)
    assert len(out) == len(iq)
    for src, got in zip(iq, out):
        assert abs(got.real - src.real * factor) <= 1e-9
        assert abs(got.imag - src.imag * factor) <= 1e-9


def test_sim_attenuator_pass_through_75db_scales_by_10_pow_minus_375():
    dev = SimAttenuator()
    dev.set_attenuation(75.0)
    factor = 10.0 ** (-75.0 / 20.0)  # = 10^-3.75
    assert factor == pytest.approx(10.0 ** (-3.75), rel=0.0)
    iq = [1.0 + 0.0j, 4.0 - 3.0j]
    for src, got in zip(iq, dev.pass_through(iq)):
        assert abs(got - src * factor) <= abs(src * factor) * 1e-12


def test_sim_attenuator_zero_db_pass_through_is_identity():
    dev = open_sim_attenuator()  # 默认初值 0 dB
    iq = [1.5 + 2.0j, -3.0 + 0.5j, 0.0 + 0.0j, 2.0 + 0.0j]
    assert dev.pass_through(iq) == iq  # 10^0=1.0 精确恒等


def test_sim_attenuator_switch_record_contains_nominal_500_and_measured_delay():
    dev = SimAttenuator()
    rec = dev.set_attenuation(10.0)
    assert rec["switched"] is True
    assert rec["nominal_switch_ns"] == 500  # 器件规格标称口径声明
    assert isinstance(rec["switch_delay_ns"], float)
    assert rec["switch_delay_ns"] >= 0.0  # 实测 perf_counter_ns 差仅记录
    assert rec["applied_db"] == 10.0 and rec["previous_db"] == 0.0
    assert dev.switch_log[-1]["nominal_switch_ns"] == 500


def test_sim_attenuator_two_switches_measured_delays_nonnegative():
    dev = SimAttenuator()
    first = dev.set_attenuation(5.0)
    second = dev.set_attenuation(7.25)
    assert first["switch_delay_ns"] >= 0.0 and second["switch_delay_ns"] >= 0.0
    assert second["previous_db"] == 5.0
    assert len(dev.switch_log) == 2


def test_sim_attenuator_repeated_set_idempotent():
    dev = SimAttenuator()
    dev.set_attenuation(20.0)
    again = dev.set_attenuation(20.0)
    assert again["applied_db"] == 20.0
    assert again["switched"] is False  # 幂等重设不构成档位变化
    assert dev.get_attenuation() == 20.0
    assert len(dev.switch_log) == 1  # 仅真实变化进切换日志


def test_sim_attenuator_get_attenuation_returns_quantized_grid_value():
    dev = SimAttenuator()
    dev.set_attenuation(12.3)  # 12.3/0.25=49.2 → 49 步 → 12.25
    assert dev.get_attenuation() == 12.25


def test_sim_attenuator_capabilities_declares_spec():
    caps = SimAttenuator().capabilities()
    assert caps["attenuation_range_db"] == (0, 75)
    assert caps["step_db"] == 0.25
    assert caps["nominal_switch_ns"] == 500
    assert caps["simulated"] is True
    # 返回新 dict：篡改不回写
    caps["step_db"] = 99.0
    assert SimAttenuator().capabilities()["step_db"] == 0.25


def test_sim_attenuator_self_registered_and_lookup_returns_factory():
    factory, meta = lookup_backend("sim_attenuator")
    assert factory is open_sim_attenuator
    assert meta["caps"]["attenuation_range_db"] == (0, 75)
    assert "sim_attenuator" in REGISTRY


def test_sim_attenuator_factory_initial_value_30_and_default_0():
    dev = open_sim_attenuator({"attenuation_db": 30})
    assert isinstance(dev, SimAttenuator)
    assert dev.get_attenuation() == 30.0
    assert open_sim_attenuator(None).get_attenuation() == 0.0
    assert open_sim_attenuator().get_attenuation() == 0.0
    # 初值亦过量化口径：30.1 → 30.0
    assert open_sim_attenuator({"attenuation_db": 30.1}).get_attenuation() == 30.0


def test_sim_attenuator_factory_rejects_bad_params():
    with pytest.raises(ValueError):
        open_sim_attenuator({"attenuation_db": 76.0})
    with pytest.raises(ValueError):
        open_sim_attenuator({"attenuation_db": -1.0})
    with pytest.raises(ValueError):
        open_sim_attenuator("not-a-dict")


def test_sim_attenuator_duck_compatible_with_set_channel_attenuation():
    # 鸭子口径：set_channel_attenuation 优先探测 callable set_attenuation（承载粗+细全量实达值）
    dev = open_sim_attenuator()
    assert callable(getattr(dev, "set_attenuation", None))
    dev.set_attenuation(30.0)  # 粗档 30dB 两态可由本插件承载
    assert dev.get_attenuation() == 30.0
