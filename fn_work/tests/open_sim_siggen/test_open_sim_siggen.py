"""open_sim_siggen 对抗测试：验收 slug=sim_1433d——频率/功率域、0.5dB 量化、1ppm 回读、输出状态、capabilities、注册集成、发射登记/统计、增益映射、命令映射复用。"""
import importlib

import pytest

from src.create_visa_driver.create_visa_driver import MODELS
from src.manage_backend_registry.lookup_backend import lookup_backend
from src.manage_backend_registry.register_backend import REGISTRY

# 被测模块延迟到 run 阶段才 import：其 import 期向全局 REGISTRY 自注册 'sim_siggen_1433d'，
# 若在 collection 期导入，会让先跑的 manage_backend_registry 形式用例（假定注册表
# 起始状态）误红（与 open_sim_backend 测试同款隔离口径）。
@pytest.fixture(scope="module", autouse=True)
def _load_siggen_module():
    mod = importlib.import_module("src.open_sim_siggen.open_sim_siggen")
    globals()["SIM_MODULE"] = mod
    globals()["SimSiggen1433D"] = mod.SimSiggen1433D
    globals()["open_sim_siggen"] = mod.open_sim_siggen
    return mod


def test_sim_1433d_freq_domain_boundaries_pass_exactly():
    # 用例1: 频率域两端恰过（1e6 与 20e9 含端点），设定点精确记录、返回生效值
    sg = open_sim_siggen({"freq_hz": 1e6})
    assert sg.set_freq(1e6) == 1e6
    assert sg.freq_hz == 1e6
    assert sg.set_freq(20e9) == 20e9
    assert sg.freq_hz == 20e9


def test_sim_1433d_freq_out_of_domain_rejected_with_domain_in_message():
    # 用例2: 越频率域拒收 ValueError 且消息附域；bool/非有限值亦拒（不抛 TypeError）
    sg = open_sim_siggen({})
    for bad in (999999.0, 2.1e10, -1.0):
        with pytest.raises(ValueError, match="频率域"):
            sg.set_freq(bad)
    with pytest.raises(ValueError, match=r"\[1e6, 20e9\]"):
        sg.set_freq(999999.0)
    with pytest.raises(ValueError):
        sg.set_freq(True)
    with pytest.raises(ValueError):
        sg.set_freq(float("nan"))


def test_sim_1433d_power_domain_bounds_and_out_of_range():
    # 用例3: 功率域两端恰过（-140/+10 含端点）；越域按原始请求拒（10.2 虽可量化落 10.0 仍拒）
    sg = open_sim_siggen({})
    assert sg.set_power(-140.0) == -140.0
    assert sg.set_power(10.0) == 10.0
    for bad in (-140.5, 10.2, 99.0):
        with pytest.raises(ValueError, match="功率域"):
            sg.set_power(bad)
    with pytest.raises(ValueError, match=r"\[-140, \+10\]"):
        sg.set_power(11.0)


def test_sim_1433d_power_half_db_quantization_semantics():
    # 用例4: 0.5dB 量化口径——-7.3 → -7.5（就近）、-7.0 恰格点不变、+2.25 半格向 +∞ 进 +2.5；
    # get_power 返回量化生效值 + 量化标注（requested/resolution/是否被舍入）
    sg = open_sim_siggen({"power_dbm": -7.0})
    assert sg.get_power() == {
        "power_dbm": -7.0,
        "requested_dbm": -7.0,
        "resolution_db": 0.5,
        "quantized": False,
    }
    assert sg.set_power(-7.3) == -7.5
    p = sg.get_power()
    assert p["power_dbm"] == -7.5
    assert p["requested_dbm"] == -7.3
    assert p["resolution_db"] == 0.5
    assert p["quantized"] is True
    assert sg.set_power(2.25) == 2.5


def test_sim_1433d_freq_readback_fixed_1ppm_deviation():
    # 用例5: 回读 1ppm 口径——固定偏差 1.000001×设定（非随机，两次回读一致），设定点不受染
    sg = open_sim_siggen({"freq_hz": 2.4e9})
    rb = sg.get_freq()
    assert rb == pytest.approx(2.4e9 * 1.000001)
    assert rb / 2.4e9 - 1.0 == pytest.approx(1e-6, abs=1e-12)
    assert sg.get_freq() == rb  # 固定偏差：逐次回读一致
    assert sg.freq_hz == 2.4e9  # 设定点保持无偏差原值
    sg.set_freq(20e9)
    assert sg.get_freq() == pytest.approx(20e9 * 1.000001)


def test_sim_1433d_output_on_off_state():
    # 用例6: 输出开关状态——出厂关，output_on/output_off 翻转并返回最新态，重复调用幂等
    sg = open_sim_siggen({})
    assert sg.output is False
    assert sg.output_on() is True
    assert sg.output is True
    assert sg.output_on() is True  # 幂等
    assert sg.output is True
    assert sg.output_off() is False
    assert sg.output is False
    assert sg.output_off() is False  # 幂等
    assert sg.output is False


def test_sim_1433d_capabilities_key_set():
    # 用例7: capabilities 键集恰为规约七键（不多不少），simulated=True，数值口径与域一致
    caps = open_sim_siggen({}).capabilities()
    assert set(caps) == {
        "model",
        "freq_range_hz",
        "power_range_dbm",
        "power_resolution_db",
        "freq_accuracy_ppm",
        "phase_noise_dbc_hz_10k",
        "simulated",
    }
    assert caps["model"] == "1433D-sim"
    assert caps["freq_range_hz"] == (1e6, 20e9)
    assert caps["power_range_dbm"] == (-140, 10)
    assert caps["power_resolution_db"] == 0.5
    assert caps["freq_accuracy_ppm"] == 1.0
    assert caps["phase_noise_dbc_hz_10k"] == -100.0  # 10kHz 偏移典型值仿真声明
    assert caps["simulated"] is True


def test_sim_1433d_registry_lookup_and_instantiation():
    # 用例8: 注册集成——lookup_backend('sim_siggen_1433d') 取回本模块工厂与 caps，
    # 实例化得 SimSiggen1433D（统一接口方法齐备可调用）
    assert any(key.lower() == "sim_siggen_1433d" for key in REGISTRY)
    factory, meta = lookup_backend("sim_siggen_1433d")
    assert factory is SIM_MODULE.open_sim_siggen
    assert meta["caps"] == {"tx": True, "rx": False, "freq_range_mhz": (1, 20000)}
    inst = factory({"freq_hz": 1e9, "power_dbm": 0.0})
    assert isinstance(inst, SimSiggen1433D)
    for name in ("start_tx", "stop_tx", "set_tx_gain", "read_samples"):
        assert callable(getattr(inst, name))


def test_sim_1433d_start_tx_records_iq_and_stats_without_transmitting():
    # 用例9: start_tx 登记 IQ+当前参数并返回统计（不真发——无任何样本可读）
    sg = open_sim_siggen({"freq_hz": 2.4e9, "power_dbm": -7.3})
    sg.output_on()
    stats = sg.start_tx([[1 + 0j, 2 + 0j], [3 + 0j]], effects={"delay_blocks": 1})
    assert stats["simulated"] is True
    assert stats["blocks"] == 2
    assert stats["samples"] == 3
    assert stats["freq_hz"] == 2.4e9
    assert stats["power_dbm"] == -7.5  # 发射电平=登记时刻的量化生效功率
    assert stats["output"] is True
    assert stats["effects"] == {"delay_blocks": 1}
    assert sg.tx_active is True
    assert sg.tx_iq_blocks == [[1 + 0j, 2 + 0j], [3 + 0j]]  # IQ 已记录（含块结构）
    assert sg.tx_params == {"freq_hz": 2.4e9, "power_dbm": -7.5, "output": True}
    assert sg.read_samples() == []  # 不真发：无任何可读产物


def test_sim_1433d_stop_tx_idempotent_keeps_record():
    # 用例10: stop_tx 撤销发射登记态（幂等不抛），IQ 记录与参数快照留存供核查
    sg = open_sim_siggen({})
    sg.start_tx([1 + 0j, 2 + 0j])  # 扁平 IQ 序列：登记为单块
    assert sg.tx_active is True
    assert sg.stop_tx() is None
    assert sg.tx_active is False
    sg.stop_tx()  # 幂等
    assert sg.tx_active is False
    assert sg.tx_iq_blocks == [[1 + 0j, 2 + 0j]]  # 记录留存
    assert sg.tx_params["power_dbm"] == 0.0


def test_sim_1433d_set_tx_gain_maps_to_set_power():
    # 用例11: set_tx_gain 即 set_power 的电平面映射——量化返回/回读标注/SCPI 留档全同路径
    sg = open_sim_siggen({})
    assert sg.set_tx_gain(-7.3) == -7.5
    p = sg.get_power()
    assert p["power_dbm"] == -7.5
    assert p["requested_dbm"] == -7.3
    assert p["quantized"] is True
    assert sg.last_scpi == "POW -7.5 dBm"
    with pytest.raises(ValueError, match="功率域"):
        sg.set_tx_gain(99.0)


def test_sim_1433d_read_samples_always_empty_no_rx():
    # 用例12: 信号源无 RX——发射前后/停发射后 read_samples 恒 []（带块数参数亦然）
    sg = open_sim_siggen({})
    assert sg.read_samples() == []
    sg.start_tx([[1 + 0j] * 8, [2 + 0j] * 8])
    assert sg.read_samples() == []
    assert sg.read_samples(4) == []
    sg.stop_tx()
    assert sg.read_samples() == []


def test_sim_1433d_factory_initial_values_and_domain_errors():
    # 用例13: 工厂初值参数化（freq/power 初值同走量化与回读口径）+ 域错/类型错 ValueError
    sg = open_sim_siggen({"freq_hz": 5e9, "power_dbm": -7.3})
    assert isinstance(sg, SimSiggen1433D)
    assert sg.freq_hz == 5e9
    assert sg.get_power()["power_dbm"] == -7.5  # 初值同样走 0.5dB 量化
    assert sg.get_freq() == pytest.approx(5e9 * 1.000001)
    assert sg.output is False  # 出厂默认输出关
    d = open_sim_siggen(None)  # None → 全缺省
    assert d.freq_hz == 1e9
    assert d.get_power()["power_dbm"] == 0.0
    with pytest.raises(ValueError, match="频率域"):
        open_sim_siggen({"freq_hz": 1e5})
    with pytest.raises(ValueError, match="功率域"):
        open_sim_siggen({"power_dbm": 10.5})
    with pytest.raises(ValueError):
        open_sim_siggen(["not", "a", "dict"])


def test_sim_1433d_models_1433d_mapping_reused_readonly():
    # 用例14: SCPI 命令映射复用 create_visa_driver.MODELS['1433d']（只读引用）——
    # 同一表对象、命令键齐备、last_scpi 按模板展开、全程不回写全局表
    assert "1433d" in MODELS
    assert SIM_MODULE.MODELS is MODELS  # 只读引用同一张表（非拷贝）
    snapshot = dict(MODELS["1433d"])
    assert set(snapshot) >= {"set_freq", "set_power", "output_on", "output_off"}
    sg = open_sim_siggen({})
    sg.set_freq(1e9)
    assert sg.last_scpi == "FREQ 1000.0 MHz"
    sg.set_power(-7.5)
    assert sg.last_scpi == "POW -7.5 dBm"
    sg.output_on()
    assert sg.last_scpi == "OUTP ON"
    sg.output_off()
    assert sg.last_scpi == "OUTP OFF"
    assert MODELS["1433d"] == snapshot  # 只读：全程未改全局表
    assert sg.scpi_commands == snapshot  # 实例持等值拷贝


def test_sim_1433d_import_registration_idempotent():
    # 用例15: 重复 import/reload 自注册幂等（override=True 不炸），注册表不产生双键
    importlib.reload(SIM_MODULE)
    # reload 重建模块级类/函数对象——测试命名空间同步到新对象再断言
    globals()["SimSiggen1433D"] = SIM_MODULE.SimSiggen1433D
    globals()["open_sim_siggen"] = SIM_MODULE.open_sim_siggen
    keys = [key for key in REGISTRY if key.lower() == "sim_siggen_1433d"]
    assert len(keys) == 1
    factory, meta = lookup_backend("sim_siggen_1433d")
    assert factory is SIM_MODULE.open_sim_siggen  # reload 后登记项即新工厂
    assert meta["caps"]["rx"] is False
    assert isinstance(factory({"freq_hz": 1e6}), SimSiggen1433D)  # 新工厂可正常实例化


def test_sim_1433d_phase_noise_static_declaration_set_and_get():
    # 用例16（B15三轴中②）: 相噪静态口径——capabilities 声明 -100 dBc/Hz @10kHz 偏移典型值，
    # set_phase_noise(≤0)/get_phase_noise 参数化；>0/bool/非有限拒收；不做 IQ 相噪注入
    sg = open_sim_siggen({})
    assert sg.get_phase_noise() == -100.0
    assert sg.set_phase_noise(-110.0) == -110.0
    assert sg.get_phase_noise() == -110.0
    assert sg.capabilities()["phase_noise_dbc_hz_10k"] == -110.0  # 回显当前声明值
    assert sg.set_phase_noise(0.0) == 0.0  # ≤0 域：恰 0 边界收
    for bad in (0.5, 10.0, float("nan"), float("inf"), True, "-100"):
        with pytest.raises(ValueError):
            sg.set_phase_noise(bad)
    assert sg.get_phase_noise() == 0.0  # 拒绝不改状态
    # 静态口径：相噪设置不注入 IQ——start_tx 登记样本原样
    stats = sg.start_tx([1 + 0j, 2 + 0j])
    assert stats["samples"] == 2
    assert sg.tx_iq_blocks == [[1 + 0j, 2 + 0j]]


def test_sim_1433d_start_tx_rejects_non_numeric_iq_with_block_sample_position():
    # 用例17（B15低#5）: IQ 逐样本校验——标量 iq/str/块内与扁平序列内非数值样本一律
    # ValueError（消息含块/样本位置），拒绝不留半截登记态
    sg = open_sim_siggen({})
    for scalar in (3, 3.5):  # 不可迭代标量整体拒（不再漏 TypeError）
        with pytest.raises(ValueError):
            sg.start_tx(scalar)
    with pytest.raises(ValueError, match="块 0 样本 0"):  # str 逐字符成块后在样本面拒
        sg.start_tx("abc")
    with pytest.raises(ValueError, match="块 0 样本 1"):  # 块内样本位次入消息
        sg.start_tx([[1 + 0j, "x"]])
    with pytest.raises(ValueError, match="块 1 样本 0"):  # 混合扁平序列逐元素成块后在样本面拒
        sg.start_tx([1 + 0j, "x"])
    with pytest.raises(ValueError, match="块 1 样本 0"):
        sg.start_tx([[1 + 0j, 2 + 0j], [True]])
    with pytest.raises(ValueError, match="块 1 样本 2"):
        sg.start_tx([[1 + 0j], [1 + 0j, 2 + 0j, None]])
    assert sg.tx_active is False  # 校验先于登记：状态原样
    assert sg.tx_iq_blocks == []
