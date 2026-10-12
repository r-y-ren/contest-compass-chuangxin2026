"""open_sim_analyzer 对抗单测（slug=sim_rsa513a 的 RSA513A 频谱仪模拟后端顶层）。"""
import math

import numpy as np
import pytest

from src.manage_backend_registry.register_backend import REGISTRY, BackendError
from src.open_sim_analyzer.open_sim_analyzer import SimRsa513a, open_sim_analyzer

_NFFT = 1024


def _tone_iq(db: float, fnorm: float, n: int = _NFFT) -> list[complex]:
    """确定性单音 IQ：幅度 10^(db/20)（满刻度 1.0 ≡ 0 dBm），数字频率 fnorm 周/样本。"""
    amp = 10.0 ** (db / 20.0)
    t = np.arange(n)
    return (amp * np.exp(2j * np.pi * fnorm * t)).tolist()


def _peak_index(power_db: list[float]) -> int:
    return max(range(len(power_db)), key=lambda i: power_db[i])


def test_sim_rsa513a_factory_defaults_and_params():
    # 工厂初值：None/空 dict 同缺省；显式参数全部生效；非法 params/键逐项拒
    inst = open_sim_analyzer(None)
    assert isinstance(inst, SimRsa513a)
    assert (inst.center_hz, inst.span_hz, inst.rbw_hz, inst.trace_mode) == (
        1e9, 10e6, 10e3, "clearwrite",
    )
    assert (inst.center_hz, inst.span_hz, inst.rbw_hz, inst.trace_mode) == (
        open_sim_analyzer({}).center_hz,
        open_sim_analyzer({}).span_hz,
        open_sim_analyzer({}).rbw_hz,
        open_sim_analyzer({}).trace_mode,
    )
    tuned = open_sim_analyzer(
        {"center_hz": 12e9, "span_hz": 110e6, "rbw_hz": 1e5, "trace": "maxhold"}
    )
    assert (tuned.center_hz, tuned.span_hz, tuned.rbw_hz, tuned.trace_mode) == (
        12e9, 110e6, 1e5, "maxhold",
    )
    for bad in (
        {"center_hz": 0.5e6},
        {"span_hz": 100.0},
        {"rbw_hz": 0.0},
        {"trace": "average"},
        {"center_hz": True},
        {"span_hz": float("nan")},
        42,
        "cfg",
    ):
        with pytest.raises(ValueError):
            open_sim_analyzer(bad)


def test_sim_rsa513a_center_span_rbw_domain_bounds_and_atomic_reject():
    ana = open_sim_analyzer()
    # 边界恰收（闭域）
    assert ana.set_center(1e6) == 1e6
    assert ana.set_center(13.6e9) == 13.6e9
    assert ana.set_span(1e3) == 1e3
    assert ana.set_span(110e6) == 110e6
    assert ana.set_rbw(1.0) == 1.0
    assert ana.set_rbw(1e6) == 1e6
    # 越域/非实数/bool/非有限一律 ValueError
    for bad in (999_999.0, 13.6e9 + 1.0, 0.0, -1e9, float("nan"), float("inf"), True, "1e9"):
        with pytest.raises(ValueError):
            ana.set_center(bad)
    for bad in (999.0, 110.000001e6, float("inf"), False):
        with pytest.raises(ValueError):
            ana.set_span(bad)
    for bad in (0.0, 1e6 + 1.0, float("nan"), True):
        with pytest.raises(ValueError):
            ana.set_rbw(bad)
    # 拒绝不改状态（原子性）：仍是最后一次成功值
    assert (ana.center_hz, ana.span_hz, ana.rbw_hz) == (13.6e9, 110e6, 1e6)


def test_sim_rsa513a_builtin_tone_peak_at_center_minus_30dbm():
    ana = open_sim_analyzer({"center_hz": 2.45e9, "span_hz": 10e6})
    out = ana.measure()  # iq=None → 内置自校准测试音
    assert set(out) == {"freqs", "power_db", "uncertainty_db", "trace_mode", "simulated"}
    assert out["simulated"] is True
    assert out["uncertainty_db"] == 1.5
    assert out["trace_mode"] == "clearwrite"
    freqs, power = out["freqs"], out["power_db"]
    assert len(freqs) == len(power) == _NFFT
    assert freqs == sorted(freqs)  # 升频轴
    assert freqs[0] == pytest.approx(2.45e9 - 5e6)
    assert freqs[-1] == pytest.approx(2.45e9 + 5e6 - 10e6 / _NFFT)  # 半开区间
    peak = _peak_index(power)
    assert freqs[peak] == 2.45e9  # DC bin 映射恰为 center（精确值）
    assert abs(power[peak] - (-30.0)) <= 1.5  # 单音 -30dBm ± 不确定度
    others = power[:peak] + power[peak + 1:]
    assert max(others) < power[peak] - 40  # 邻道隔离：其余 bin 全在底噪
    assert all(-121.5 <= p <= -118.5 for p in others)  # 底噪 -120 叠 ±1.5 偏差


def test_sim_rsa513a_iq_single_tone_peak_localization():
    ana = open_sim_analyzer({"center_hz": 1e9, "span_hz": 8e6})
    # fnorm=+0.25 周/样本 → fftshift 后 bin 768 → 频率 center + 0.25·span
    out = ana.measure(iq=_tone_iq(-6.0, 0.25))
    peak = _peak_index(out["power_db"])
    assert peak == 768
    assert out["freqs"][peak] == pytest.approx(1e9 + 0.25 * 8e6)
    assert abs(out["power_db"][peak] - 20 * math.log10(0.5)) <= 1.5  # -6.02dBm±1.5
    # 超长输入截断前 1024 样本：与恰 1024 输入逐位同谱（同种子确定性）
    assert ana.measure(iq=_tone_iq(-6.0, 0.25, n=2048))["power_db"] == out["power_db"]
    # 短输入零填：峰位不变（幅度按占空比减半量级，不严格断言幅度）
    short = ana.measure(iq=_tone_iq(-6.0, 0.25, n=512))["power_db"]
    assert _peak_index(short) == 768
    # 非 IQ 输入：字符串/标量/二维/含非数值元素一律 ValueError
    for bad in ("not iq at all", 3.0, [[1, 2], [3, 4]], ["a", "b"]):
        with pytest.raises(ValueError):
            ana.measure(iq=bad)


def test_sim_rsa513a_uncertainty_deviation_deterministic():
    a1 = open_sim_analyzer({"center_hz": 3.5e9, "span_hz": 20e6})
    a2 = open_sim_analyzer({"center_hz": 3.5e9, "span_hz": 20e6})
    r1, r2 = a1.measure(), a1.measure()
    assert r1["power_db"] == r2["power_db"]  # 同实例两次逐位一致
    assert r1["freqs"] == r2["freqs"]
    assert a2.measure()["power_db"] == r1["power_db"]  # 跨实例同参数亦逐位一致
    # 种子随 center+span 变化：换 span 后偏差重抽，谱逐位不同
    a1.set_span(30e6)
    assert a1.measure()["power_db"] != r1["power_db"]
    a1.set_center(3.6e9)
    assert a1.measure()["power_db"] != r1["power_db"]


def test_sim_rsa513a_dpx_frame_composite_eight_frames():
    ana = open_sim_analyzer({"center_hz": 6e9, "span_hz": 5e6})
    base = ana.measure()["power_db"]  # salt=0 帧（clearwrite 当前谱）
    frame = ana.dpx_frame()
    assert set(frame) == {"density", "frames", "note"}
    assert frame["frames"] == 8
    assert frame["note"] == "dpx_sim"
    density = frame["density"]
    assert len(density) == _NFFT  # 2D 密度：每 bin 一行 [min, max]
    assert all(len(row) == 2 and row[0] <= row[1] for row in density)
    for (lo, hi), b in zip(density, base):
        assert lo <= b <= hi  # base 本身即 8 帧之一（salt=0）
        assert b - 3.0 - 1e-9 <= lo and hi <= b + 3.0 + 1e-9  # 两帧偏差至多差 2×1.5dB
    # DPX 不受迹线模式影响，也不改 maxhold 状态
    ana.trace("maxhold")
    assert ana.dpx_frame()["frames"] == 8
    held = ana.measure()["power_db"]
    assert held == base  # maxhold 首帧=当前谱（DPX 未污染保持谱）


def test_sim_rsa513a_trace_mode_maxhold_vs_clearwrite():
    ana = open_sim_analyzer({"center_hz": 1e9, "span_hz": 10e6, "trace": "maxhold"})
    bin_i = 768
    low = ana.measure(iq=_tone_iq(-40.0, 0.25))
    assert abs(low["power_db"][bin_i] + 40.0) <= 1.5
    high = ana.measure(iq=_tone_iq(-20.0, 0.25))
    assert abs(high["power_db"][bin_i] + 20.0) <= 1.5
    again = ana.measure(iq=_tone_iq(-40.0, 0.25))  # 输入回落，保持谱仍钉在峰值
    assert again["power_db"][bin_i] == high["power_db"][bin_i]
    assert again["trace_mode"] == "maxhold"
    # 切回 clearwrite：当前谱即显（回落输入直接可见 -40）
    assert ana.trace("clearwrite") == "clearwrite"
    fresh = ana.measure(iq=_tone_iq(-40.0, 0.25))
    assert fresh["trace_mode"] == "clearwrite"
    assert abs(fresh["power_db"][bin_i] + 40.0) <= 1.5
    # 改轴（set_center/set_span）清保持谱：maxhold 从新轴当前谱重新累积
    ana.trace("maxhold")
    ana.measure(iq=_tone_iq(-20.0, 0.25))
    ana.set_center(1.05e9)
    reset = ana.measure(iq=_tone_iq(-50.0, 0.25))
    assert abs(reset["power_db"][bin_i] + 50.0) <= 1.5  # 不再钉住旧轴 -20 峰


def test_sim_rsa513a_trace_mode_invalid_rejected():
    ana = open_sim_analyzer()
    for bad in ("average", "minhold", "", None, 1):
        with pytest.raises(ValueError):
            ana.trace(bad)
    assert ana.trace_mode == "clearwrite"  # 拒绝不改模式
    assert ana.trace("maxhold") == "maxhold"


def test_sim_rsa513a_capabilities_key_set():
    caps = open_sim_analyzer().capabilities()
    assert set(caps) == {
        "model", "max_freq_hz", "span_range_hz", "rbw_range_hz", "vbw_hz",
        "uncertainty_db", "simulated",
    }
    assert caps["model"] == "RSA513A-sim"
    assert caps["max_freq_hz"] == 13.6e9
    assert caps["span_range_hz"] == (1e3, 110e6)
    assert caps["rbw_range_hz"] == (1, 1e6)
    assert caps["vbw_hz"] == 10e3  # VBW 参数面回显（缺省 10kHz，span 10e6 域内）
    assert caps["uncertainty_db"] == 1.5
    assert caps["simulated"] is True
    caps["model"] = "tampered"  # 返回副本：篡改不回写
    assert open_sim_analyzer().capabilities()["model"] == "RSA513A-sim"


def test_sim_rsa513a_registry_integration():
    from src.manage_backend_registry.lookup_backend import lookup_backend

    assert "sim_rsa513a" in REGISTRY  # import 期自注册（override 幂等）
    factory, meta = lookup_backend("sim_rsa513a")
    assert callable(factory)
    assert meta["kind"] == "sim_rsa513a"
    assert meta["caps"] == {"tx": False, "rx": True, "freq_range_mhz": (1, 13600)}
    inst = factory({"center_hz": 2.4e9, "span_hz": 40e6})
    assert isinstance(inst, SimRsa513a)
    assert inst.read_samples() == []
    assert len(inst.measure()["power_db"]) == _NFFT


def test_sim_rsa513a_no_tx_semantics():
    ana = open_sim_analyzer()
    assert ana.stop_tx() == {"status": "no_tx"}
    assert ana.set_tx_gain(30.0) == {"status": "no_tx"}
    assert ana.set_tx_gain() == {"status": "no_tx"}
    assert ana.events == ["sim_rsa513a 无发射能力"] * 3  # 调用留痕（不抛）
    with pytest.raises(BackendError, match="sim_rsa513a 后端无发射能力"):
        ana.start_tx(samples=[1.0 + 1.0j], center_freq=2.4e9)  # 发射请求绝不静默假装成功


def test_sim_rsa513a_read_samples_always_empty():
    ana = open_sim_analyzer()
    assert ana.read_samples() == []
    assert ana.read_samples(4) == []
    assert ana.read_samples(max_blocks=8) == []  # 纯分析仪无 IQ 流：任意调用恒 []


def test_sim_rsa513a_measure_is_pure_of_rbw_and_repeatable():
    # RBW 是参数面状态（不改谱值）：域内改 RBW 后同 IQ 谱逐位不变
    ana = open_sim_analyzer({"center_hz": 5e9, "span_hz": 20e6})
    iq = _tone_iq(-12.0, -0.125)
    first = ana.measure(iq=iq)
    ana.set_rbw(1e5)
    assert ana.measure(iq=iq)["power_db"] == first["power_db"]
    peak = _peak_index(first["power_db"])
    assert peak == 512 - 128  # fnorm=-0.125 → fftshift 后 bin 384
    assert first["freqs"][peak] == pytest.approx(5e9 - 0.125 * 20e6)


def test_sim_rsa513a_rejects_non_finite_iq_and_maxhold_stays_clean():
    # B15对抗中#1: 含 NaN/±inf 样本的 IQ 拒收（家族口径 ValueError，首位置入消息）；
    # 校验先于谱计算 → maxhold 保持谱不被污染，后续干净帧照常累积/覆写
    ana = open_sim_analyzer({"trace": "maxhold"})
    for bad in (
        [float("nan") + 0j, 1 + 0j],
        [1 + 0j, complex(float("inf"), 0.0), 2 + 0j],
        [complex(0.0, float("-inf"))],
    ):
        with pytest.raises(ValueError, match="非有限"):
            ana.measure(iq=bad)
    # 拒绝后无保持谱（首帧尚未成功）：干净低帧成为保持谱起点
    low = ana.measure(iq=_tone_iq(-40.0, 0.25))["power_db"]
    # 再次以 NaN 输入拒收：保持谱保持干净低帧原值（不抛前先算的污染不存在）
    with pytest.raises(ValueError, match="非有限"):
        ana.measure(iq=[1 + 0j, complex(float("nan"), 0.0)])
    assert ana.measure(iq=_tone_iq(-40.0, 0.25))["power_db"] == low  # 幂等不变
    # 干净高帧可正常覆写（钉住峰值）——maxhold 通道完好
    high = ana.measure(iq=_tone_iq(-20.0, 0.25))["power_db"]
    bin_i = 768
    assert abs(high[bin_i] + 20.0) <= 1.5
    assert high[bin_i] > low[bin_i]


def test_sim_rsa513a_vbw_parameter_face_domain_echo_and_no_spectral_effect():
    # B15三轴低③: VBW 纯参数面——域 1–span/10（按调用时刻 span 判域）、capabilities
    # 'vbw_hz' 回显、不改谱计算、不清 maxhold 保持谱；拒绝原子（不改状态）
    ana = open_sim_analyzer()  # span 10e6 → 域 [1, 1e6]
    iq = _tone_iq(-12.0, 0.25)
    ana.set_vbw(1e6)  # 域顶恰过（span/10）
    base = ana.measure(iq=iq)["power_db"]
    assert ana.set_vbw(1.0) == 1.0  # 域底恰过
    assert ana.measure(iq=iq)["power_db"] == base  # 纯参数面：谱逐位不变
    for bad in (0.0, 0.5, 1e6 + 1.0, float("nan"), float("inf"), True, "1e3"):
        with pytest.raises(ValueError, match="vbw_hz"):
            ana.set_vbw(bad)
    assert ana.capabilities()["vbw_hz"] == 1.0  # 回显当前生效值（拒绝后原值保持）
    # maxhold 保持谱不被 set_vbw 清除
    ana.trace("maxhold")
    held = ana.measure(iq=iq)["power_db"]
    ana.set_vbw(2e3)
    assert ana.measure(iq=iq)["power_db"] == held
    # 小 span 构造：缺省 vbw=min(10k, span/10) 保域内；域顶随 span 收窄
    small = open_sim_analyzer({"span_hz": 1e3})
    assert small.capabilities()["vbw_hz"] == 100.0  # min(10e3, 1e2)
    assert small.set_vbw(100.0) == 100.0  # 新域顶恰过
    with pytest.raises(ValueError, match="vbw_hz"):
        small.set_vbw(100.1)
