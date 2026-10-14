"""open_sim_backend 对抗测试：验收 slug=backend_sim——环回取块/停发射残余/增益夹紧与热更新/域校验/注册集成。

走查环 F2/F3 新真值（2026-10-14）：read_samples 非发射登记态不再恒空——静默态
合成低功率底噪块（meta 'synthetic': 'noise_floor'，每实例预算 _IDLE_NOISE_BUDGET
块，预算尽回落 []）；_drain 以底噪块为"真实流尽"哨兵截断（不再等空读）。
"""
import importlib

import pytest

from src.manage_backend_registry.lookup_backend import lookup_backend
from src.manage_backend_registry.register_backend import REGISTRY

# 被测模块延迟到 run 阶段才 import：其 import 期向全局 REGISTRY 自注册 'sim'，
# 若在 collection 期导入，会让字母序在前、假定注册表起始无 'sim' 的
# manage_backend_registry 形式用例（无 override 登记/拒绝后不在表断言）误红。
@pytest.fixture(scope="module", autouse=True)
def _load_backend_module():
    mod = importlib.import_module("src.open_sim_backend.open_sim_backend")
    globals()["SIM_MODULE"] = mod
    globals()["SimBackend"] = mod.SimBackend
    globals()["open_sim_backend"] = mod.open_sim_backend
    return mod


def _is_synthetic(meta: dict) -> bool:
    """静默态底噪块判定（meta 'synthetic' 标注——新真值的流尽哨兵）。"""
    return meta.get("synthetic") == "noise_floor"


def _drain(backend):
    """弹尽真实环回流：反复 read_samples 至出现底噪块（真实流尽哨兵——静默态
    预算内恒可产底噪块，不能以空读为尽），返回哨兵前的全部 (rx_block, meta)。"""
    drained = []
    while True:
        got = backend.read_samples()
        if not got or all(_is_synthetic(meta) for _, meta in got):
            break
        drained.extend(
            (block, meta) for block, meta in got if not _is_synthetic(meta)
        )
    return drained


def test_backend_sim_start_tx_read_samples_loopback_retrieves_transformed_blocks():
    # 用例1: start_tx → read_samples 逐块取回环回变换块（增益 0dB=恒等，幅度/时间戳/溯源全保真）
    be = open_sim_backend({"freq_hz": 2.4e9, "sample_rate": 1e6, "tx_gain_db": 0.0})
    be.start_tx([[1 + 0j] * 16, [2 + 0j] * 16, [3 + 0j] * 16], effects={})
    drained = _drain(be)
    assert [abs(b[0]) for b, _ in drained] == [1.0, 2.0, 3.0]
    assert [m["rx_ts"] for _, m in drained] == [0, 1, 2]
    assert [m["src_index"] for _, m in drained] == [0, 1, 2]
    assert all(m["n_samples"] == 16 for _, m in drained)


def test_backend_sim_stop_tx_residual_then_noise_floor():
    # 用例2: stop_tx 后 read_samples 先弹残余（stop 不清缓冲）再转静默底噪块；stop 幂等
    be = open_sim_backend({})
    be.start_tx([[1 + 0j] * 8 for _ in range(10)])
    first = be.read_samples()
    assert first
    be.stop_tx()
    be.stop_tx()  # 重复停不抛
    residual = _drain(be)
    assert residual  # 残余非空：已变换入缓冲的块不因 stop 丢失
    assert 1 + len(residual) <= 10
    assert all(abs(b[0]) == 1.0 for b, _ in first + residual)
    # 走查环新真值：残余尽后静默读产底噪块（synthetic 标注，非空非抛）
    nxt = be.read_samples()
    assert nxt and all(_is_synthetic(meta) for _, meta in nxt)


def test_backend_sim_set_tx_gain_clamps_0_90():
    # 用例3: set_tx_gain 越界夹紧 [0, 90]，域内原样生效；非实数拒收
    be = open_sim_backend({"tx_gain_db": 50})
    assert be.tx_gain_db == 50.0
    assert be.set_tx_gain(120) == 90.0
    assert be.tx_gain_db == 90.0
    assert be.set_tx_gain(-7) == 0.0
    assert be.set_tx_gain(37.5) == 37.5
    with pytest.raises(ValueError):
        be.set_tx_gain("high")


def test_backend_sim_hot_gain_update_scales_subsequent_blocks():
    # 用例4: 发射中热更新增益：旧增益块在前、新增益块在后单调切换（即时生效于后续变换块）
    be = open_sim_backend({"tx_gain_db": 0})
    be.start_tx([[1 + 0j] * 8 for _ in range(8)])
    first_block, _ = be.read_samples()[0]
    assert abs(first_block[0]) == 1.0  # 更新前变换的块：1.0
    be.set_tx_gain(20)  # +20dB → ×10
    drained = _drain(be)
    assert len(drained) == 7  # 共 8 块：1 + 7
    amps = [abs(b[0]) for b, _ in drained]
    assert amps[-1] == 10.0  # 尾块必然新增益
    jump = amps.index(10.0)
    assert all(a == 1.0 for a in amps[:jump])
    assert all(a == 10.0 for a in amps[jump:])


def test_backend_sim_read_samples_idle_yields_noise_floor_blocks():
    # 用例5（走查环 F2 新真值）: 空闲（未发射/已弹尽）read_samples 产低功率底噪块
    # （meta 'synthetic': 'noise_floor'、src_index=None、n_samples=256、幅度低功率
    # 域），每实例预算尽后回落 []（源耗尽语义），不抛
    be = open_sim_backend({})
    first = be.read_samples()
    assert first  # 未发射即有底噪块
    block, meta = first[0]
    assert _is_synthetic(meta)
    assert meta["src_index"] is None and meta["n_samples"] == len(block) == 256
    import math

    assert all(math.isfinite(abs(s)) and abs(s) < 1e-6 for s in block)  # 低功率底噪域
    be.start_tx([[1 + 0j] * 4])
    drained = _drain(be)  # 发射流真实块（非 synthetic）
    assert drained and all(not _is_synthetic(m) for _, m in drained)
    # 预算尽：连续读掉剩余底噪块后回落 []（有界产块——监测路空读熔断可收尾）
    while be.read_samples():
        pass
    assert be.read_samples() == []


def test_backend_sim_capabilities_structure():
    # 用例6: capabilities 结构（tx/rx/频率域/当前配置回显），且每次返回副本可安全篡改
    be = open_sim_backend({"freq_hz": 100e6, "sample_rate": 2e6})
    caps = be.capabilities()
    assert caps["tx"] is True and caps["rx"] is True
    assert caps["freq_range_mhz"] == (70, 6000)
    assert caps["sample_rate_hz"] == 2e6
    assert caps["freq_hz"] == 100e6
    caps["tx"] = False
    assert be.capabilities()["tx"] is True  # 副本：篡改不回写


def test_backend_sim_registered_in_registry_lookup_and_instantiate():
    # 用例7（集成）: REGISTRY 中 'sim' 可 lookup 到、meta caps 契约完整、工厂可实例化且四方法齐备
    assert "sim" in REGISTRY
    factory, meta = lookup_backend("sim")
    assert callable(factory)
    assert meta["caps"] == {"tx": True, "rx": True, "freq_range_mhz": (70, 6000)}
    inst = factory({"freq_hz": 900e6})
    assert isinstance(inst, SimBackend)
    for name in ("start_tx", "stop_tx", "set_tx_gain", "read_samples", "capabilities"):
        assert callable(getattr(inst, name))


def test_backend_sim_freq_out_of_domain_value_error():
    # 用例8: freq 域外（负值 / 低于 70MHz / 高于 6GHz）→ ValueError
    for bad in (-1.0, 10e6, 7e9):
        with pytest.raises(ValueError):
            open_sim_backend({"freq_hz": bad})


def test_backend_sim_effects_passthrough_minus_6db():
    # 用例9: effects 透传：gain_db=-6 → 环回块幅度 ×10**(-6/20)
    be = open_sim_backend({"tx_gain_db": 0})
    be.start_tx([[1 + 0j] * 32], effects={"gain_db": -6})
    block, meta = be.read_samples()[0]
    assert meta["n_samples"] == 32
    assert all(abs(s) == pytest.approx(10 ** (-6 / 20), rel=1e-9) for s in block)


def test_backend_sim_import_idempotent_reload():
    # 用例10: 二次 import（reload 重执行模块体+自注册）不炸，注册表仍可用可实例化
    reloaded = importlib.reload(SIM_MODULE)
    assert callable(reloaded.open_sim_backend)
    factory, _ = lookup_backend("sim")
    assert factory({"freq_hz": 100e6}).capabilities()["tx"] is True
    importlib.reload(SIM_MODULE)  # 连续第二次仍幂等
    assert "sim" in REGISTRY


def test_backend_sim_sample_rate_non_positive_rejected():
    # 用例11: sample_rate ≤ 0（0 与负值）→ ValueError
    for bad in (0, -5e5):
        with pytest.raises(ValueError):
            open_sim_backend({"sample_rate": bad})


def test_backend_sim_invalid_params_value_error():
    # 用例12: params 形状/类型域外 → ValueError（非 dict、数值键非实数/布尔、带宽非正）
    for bad_params in (
        "sim",
        {"freq_hz": None},
        {"sample_rate": True},
        {"tx_gain_db": "high"},
        {"tx_bandwidth_hz": 0},
    ):
        with pytest.raises(ValueError):
            open_sim_backend(bad_params)


def test_backend_sim_caps_param_extends_freq_domain():
    # 用例13: caps['freq_range_mhz'] 扩域：默认域外频率放行、capabilities 反映扩域、非法形状拒收
    with pytest.raises(ValueError):
        open_sim_backend({"freq_hz": 30e6})  # 默认域内不含 30MHz
    be = open_sim_backend({"freq_hz": 30e6, "caps": {"freq_range_mhz": (1, 10000)}})
    assert be.freq_hz == 30e6
    assert be.capabilities()["freq_range_mhz"] == (1, 10000)
    assert open_sim_backend({"freq_hz": 7e9, "caps": {"freq_range_mhz": (1, 10000)}}).freq_hz == 7e9
    with pytest.raises(ValueError):
        open_sim_backend({"caps": {"freq_range_mhz": (10, 5)}})  # hi ≤ lo
    with pytest.raises(ValueError):
        open_sim_backend({"caps": "wide"})  # caps 非 dict


def test_backend_sim_delay_placeholders_causal_timestamps():
    # 用例14: effects delay_blocks 占位块先行吐出且 rx_ts 连续因果，随后真实块溯源 src_index
    be = open_sim_backend({})
    be.start_tx([[1 + 0j] * 4, [2 + 0j] * 4], effects={"delay_blocks": 2})
    drained = _drain(be)
    assert len(drained) == 4
    assert [m["rx_ts"] for _, m in drained] == [0, 1, 2, 3]
    assert [m.get("placeholder") for _, m in drained] == [True, True, None, None]
    assert [m["src_index"] for _, m in drained] == [None, None, 0, 1]
    assert abs(drained[2][0][0]) == 1.0 and abs(drained[3][0][0]) == 2.0


def test_backend_sim_start_tx_replaces_active_stream():
    # 用例15: 发射中未 stop 直接 start_tx：隐式停旧流并清残余，后续只读得新流
    be = open_sim_backend({"tx_gain_db": 0})
    be.start_tx([[9 + 0j] * 8])  # 流 A
    be.start_tx([[1 + 0j] * 8], effects={})  # 换流 B：不抛
    drained = _drain(be)
    assert len(drained) == 1
    assert all(abs(b[0]) == 1.0 for b, _ in drained)  # 只见流 B，无 A 残余


def test_backend_sim_start_tx_invalid_effects_value_error():
    # 用例16: effects 非 dict → loopback_sim_stream 急切校验在 start_tx 即抛 ValueError，实例保持非发射态
    be = open_sim_backend({})
    with pytest.raises(ValueError):
        be.start_tx([[1 + 0j] * 4], effects="gain_db=-6")
    # 静默态照常产底噪块（原子拒绝：坏 effects 不留半途状态）
    nxt = be.read_samples()
    assert nxt and all(_is_synthetic(meta) for _, meta in nxt)


def test_backend_sim_start_tx_bad_effects_atomic_rejection():
    # 用例17: 发射中 start_tx 非法 effects → 原子拒绝：校验先于 stop_tx/清缓冲，
    # 旧流残余保留、streaming 不变，旧源照常续读
    be = open_sim_backend({"tx_gain_db": 0})
    be.start_tx([[5 + 0j] * 4 for _ in range(10)])
    first = be.read_samples()  # 泵入 4 块、弹出 1 块 → 缓冲余 3 块旧流残余
    assert first and abs(first[0][0][0]) == 5.0
    with pytest.raises(ValueError):
        be.start_tx([[1 + 0j] * 4], effects={"noise_dbm": "loud"})  # 非法 effects
    assert be.streaming is True  # 旧发射登记态不受坏 effects 影响
    residual = _drain(be)
    assert len(residual) == 9  # 3 块残余 + 旧源剩余 6 块（共 10，已弹 1）
    assert all(abs(b[0]) == 5.0 for b, _ in residual)  # 全是旧流，无半途换流
    # 真实流尽后转静默底噪块（synthetic 标注可辨，不再混入旧流幅度）
    nxt = be.read_samples()
    assert nxt and all(_is_synthetic(meta) for _, meta in nxt)


def test_backend_sim_source_exception_clears_streaming_immediately():
    # 用例18: 源生成器第 3 块抛异常：异常上抛且 streaming 即时转 False（不虚报），
    # 已变换入缓冲的 2 块残余仍可续读
    def flaky_source():
        yield [1 + 0j] * 4
        yield [2 + 0j] * 4
        raise RuntimeError("source boom")

    be = open_sim_backend({})
    be.start_tx(flaky_source(), effects={})
    with pytest.raises(RuntimeError, match="source boom"):
        be.read_samples()  # 泵送（target=4）途中源异常冒出
    assert be.streaming is False  # 即时撤销（而非等下一次 read 才自愈）
    residual = _drain(be)
    assert [abs(b[0]) for b, _ in residual] == [1.0, 2.0]  # 已入缓冲残余照常可读
    # 异常撤销后静默态转底噪块（synthetic 标注，不虚报发射流）
    nxt = be.read_samples()
    assert nxt and all(_is_synthetic(meta) for _, meta in nxt)
