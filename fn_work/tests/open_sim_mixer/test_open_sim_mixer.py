"""open_sim_mixer 对抗测试：验收 slug=sim_mixer13g——公式(2) 13G 恰合链、镜像抑制 60 缺省、
beyond_model 域标注、LO 相噪 −100 透传、shift_iq 频谱搬移（含环绕）、chain_demo 键集+13G、
capabilities、注册集成、工厂 LO 参数化、no_tx 鸭子、IQ 域错（NaN）拒绝。"""
import importlib

import numpy as np
import pytest

from src.manage_backend_registry.lookup_backend import lookup_backend
from src.manage_backend_registry.register_backend import REGISTRY, BackendError


# 被测模块延迟到 run 阶段才 import：其 import 期向全局 REGISTRY 自注册 'sim_mixer_13g'，
# 若在 collection 期导入，会让先跑的 manage_backend_registry 形式用例（假定注册表
# 起始状态）误红（与 open_sim_siggen/open_sim_backend 测试同款隔离口径）。
@pytest.fixture(scope="module", autouse=True)
def _load_mixer_module():
    mod = importlib.import_module("src.open_sim_mixer.open_sim_mixer")
    globals()["SIM_MODULE"] = mod
    globals()["SimMixer13G"] = mod.SimMixer13G
    globals()["open_sim_mixer"] = mod.open_sim_mixer
    return mod


def _default_mixer():
    return open_sim_mixer({})


def test_sim_mixer13g_upconvert_formula2_if150m_lo12_85g_hits_13g_exactly():
    # 用例1: 公式(2) 链——IF 150MHz + LO 12.85GHz（缺省自持）→ RF 恰 13.0GHz；
    # 叶子 7 键全透传 + 本层 2 个标注键（in_model / simulated）
    mx = _default_mixer()
    result = mx.upconvert(150e6, -10.0)
    assert result["rf_freq_hz"] == 13e9  # 恰 13GHz（整数和，浮点精确）
    assert result["rf_power_dbm"] == pytest.approx(-7.0)  # 叶子简化口径：IF+3dB
    assert result["image_freq_hz"] == pytest.approx(12.7e9)  # f_LO−f_IF
    assert result["phase_noise_note"] == -100.0
    assert result["rf_domain_note"] == "in_model"
    assert result["simulated"] is True
    assert {"rf_freq_hz", "rf_power_dbm", "image_freq_hz", "image_power_dbm",
            "image_rejection_db", "phase_noise_note", "spurious"} <= set(result)


def test_sim_mixer13g_default_image_rejection_60_db_residual():
    # 用例2: 镜像抑制 60dB 缺省——image_power_dbm = IF−60，rejection 键归一透传，
    # 二次本振杂散按叶子口径落 2·f_LO±f_IF 各压 IF−60
    result = _default_mixer().upconvert(150e6, -10.0)
    assert result["image_rejection_db"] == 60.0
    assert result["image_power_dbm"] == pytest.approx(-70.0)  # -10 - 60
    assert [s["freq_hz"] for s in result["spurious"]] == [25.55e9, 25.85e9]
    assert all(s["power_dbm"] == pytest.approx(-70.0) for s in result["spurious"])


def test_sim_mixer13g_rf_beyond_20ghz_annotated_not_rejected():
    # 用例3: RF 超 20GHz 仿真域——不拒收，标注 'beyond_model'；恰在 20GHz 端点仍 in_model
    beyond = open_sim_mixer({"lo_freq_hz": 19e9}).upconvert(2e9, 0.0)
    assert beyond["rf_freq_hz"] == pytest.approx(21e9)
    assert beyond["rf_domain_note"] == "beyond_model"
    edge = open_sim_mixer({"lo_freq_hz": 18.5e9}).upconvert(1.5e9, 0.0)
    assert edge["rf_freq_hz"] == 20e9  # 端点含入
    assert edge["rf_domain_note"] == "in_model"


def test_sim_mixer13g_phase_noise_minus100_dbc_hz_passthrough():
    # 用例4: LO 相噪 −100 dBc/Hz（R40 C8 指标）口径透传——upconvert 叶子键、实例属性、
    # chain_demo 顶键三路同值，且为 float 本体
    mx = _default_mixer()
    assert mx.phase_noise_dbc_hz == -100.0
    assert isinstance(mx.upconvert(150e6, -10.0)["phase_noise_note"], float)
    assert mx.upconvert(150e6, -10.0)["phase_noise_note"] == -100.0
    assert mx.chain_demo()["phase_noise_dbc_hz"] == -100.0


def test_sim_mixer13g_shift_iq_single_tone_upshift_with_wraparound():
    # 用例5: shift_iq 频谱整体上移——单音 0.1fs 搬移 0.25fs → FFT 峰落 0.35fs；
    # 搬移 0.95fs（缺省 fs=10MHz 路径）→ (0.1+0.95)%1 = 0.05fs 环绕；幅度不变
    fs = 1e6
    n = np.arange(1000)
    tone = np.exp(2j * np.pi * 0.1 * n)  # 单音恰在 bin 100 = 0.1·fs
    mx = _default_mixer()
    out = mx.shift_iq(tone, 0.25e6, fs_hz=fs)
    assert out["fs_hz"] == fs and out["if_freq_hz"] == 0.25e6
    assert out["n_samples"] == 1000 and out["simulated"] is True
    assert int(np.argmax(np.abs(np.fft.fft(out["iq"])))) == 350  # 0.35·fs
    assert np.abs(out["iq"]).max() == pytest.approx(1.0)  # 单位幅度不变
    wrapped = mx.shift_iq(tone, 9.5e6)  # 缺省 fs=10MHz → 搬移 0.95·fs
    assert wrapped["fs_hz"] == 10e6
    assert int(np.argmax(np.abs(np.fft.fft(wrapped["iq"])))) == 50  # 环绕至 0.05·fs


def test_sim_mixer13g_chain_demo_keyset_and_13g_assertions():
    # 用例6: chain_demo 键集恰 4 键；缺省 LO 下 RF 恰 13GHz；三步链
    # （if_setup→lo_mix→rf_summary）各步键齐备，镜像频率 12.7GHz
    demo = _default_mixer().chain_demo()
    assert set(demo) == {"steps", "rf_freq_hz", "image_freq_hz", "phase_noise_dbc_hz"}
    assert demo["rf_freq_hz"] == 13e9  # 13GHz 全链一步演示
    assert demo["image_freq_hz"] == pytest.approx(12.7e9)
    assert demo["phase_noise_dbc_hz"] == -100.0
    steps = demo["steps"]
    assert [s["step"] for s in steps] == ["if_setup", "lo_mix", "rf_summary"]
    assert steps[0]["if_freq_hz"] == 150e6 and steps[0]["if_power_dbm"] == -10.0
    assert steps[1]["lo_freq_hz"] == 12.85e9 and steps[1]["lo_power_dbm"] == 7.0
    assert steps[1]["phase_noise_dbc_hz"] == -100.0 and steps[1]["image_rejection_db"] == 60.0
    assert steps[2]["rf_freq_hz"] == 13e9 and steps[2]["rf_domain_note"] == "in_model"


def test_sim_mixer13g_capabilities_exact_keyset_and_values():
    # 用例7: capabilities 键集恰 5 键——口径常量逐一断言；每次新 dict（篡改不回写）
    caps = _default_mixer().capabilities()
    assert set(caps) == {
        "rf_max_hz",
        "lo_default_hz",
        "phase_noise_dbc_hz",
        "image_rejection_db_default",
        "simulated",
    }
    assert caps["rf_max_hz"] == 20e9
    assert caps["lo_default_hz"] == 12.85e9
    assert caps["phase_noise_dbc_hz"] == -100.0
    assert caps["image_rejection_db_default"] == 60.0
    assert caps["simulated"] is True
    again = _default_mixer().capabilities()
    assert again == caps and again is not caps


def test_sim_mixer13g_registry_lookup_and_meta():
    # 用例8: 注册集成——lookup_backend('sim_mixer_13g') 取回本模块工厂与组件级 caps
    # （tx/rx 均假），实例化得 SimMixer13G 且核心方法可调用
    assert any(key.lower() == "sim_mixer_13g" for key in REGISTRY)
    factory, meta = lookup_backend("sim_mixer_13g")
    assert factory is SIM_MODULE.open_sim_mixer
    assert meta["caps"] == {"tx": False, "rx": False, "freq_range_mhz": (1, 20000)}
    inst = factory({})
    assert isinstance(inst, SimMixer13G)
    for name in ("upconvert", "shift_iq", "chain_demo", "capabilities", "stop_tx"):
        assert callable(getattr(inst, name))


def test_sim_mixer13g_factory_lo_parameterization():
    # 用例9: 工厂 LO 参数化——lo_freq/lo_power/rejection 三键生效进 upconvert 链；
    # None → 全缺省（12.85G/+7/60）
    mx = open_sim_mixer({"lo_freq_hz": 10e9, "lo_power_dbm": 5.0, "rejection_db": 30.0})
    assert (mx.lo_freq_hz, mx.lo_power_dbm, mx.rejection_db) == (10e9, 5.0, 30.0)
    result = mx.upconvert(150e6, -10.0)
    assert result["rf_freq_hz"] == pytest.approx(10.15e9)
    assert result["image_rejection_db"] == 30.0
    assert result["image_power_dbm"] == pytest.approx(-40.0)  # -10 - 30
    default = open_sim_mixer(None)
    assert (default.lo_freq_hz, default.lo_power_dbm, default.rejection_db) == (
        12.85e9, 7.0, 60.0,
    )


def test_sim_mixer13g_factory_domain_errors_raise_valueerror():
    # 用例10: 工厂参数域错——params 非 dict、lo_freq ≤0/NaN/bool、lo_power NaN、
    # rejection 负值一律 ValueError（校验先于构造，无半初始化对象）
    with pytest.raises(ValueError):
        open_sim_mixer(["not", "a", "dict"])
    for bad_params in (
        {"lo_freq_hz": 0.0},
        {"lo_freq_hz": -12.85e9},
        {"lo_freq_hz": float("nan")},
        {"lo_freq_hz": True},
        {"lo_power_dbm": float("nan")},
        {"rejection_db": -5.0},
        {"rejection_db": float("inf")},
    ):
        with pytest.raises(ValueError):
            open_sim_mixer(bad_params)


def test_sim_mixer13g_no_tx_duck_compatibility():
    # 用例11: no_tx 鸭子——stop_tx/set_tx_gain 返回 {'status': 'no_tx'} 不抛并记录
    # 事件（stop_transmit_safely 可安全串）；start_tx 调用即 BackendError 绝不静默
    mx = _default_mixer()
    assert mx.stop_tx() == {"status": "no_tx"}
    assert mx.set_tx_gain(0) == {"status": "no_tx"}
    assert len(mx.events) == 2
    with pytest.raises(BackendError):
        mx.start_tx([1 + 0j])


def test_sim_mixer13g_shift_iq_domain_errors_nan_rejected():
    # 用例12: IQ 域错拒收——含 NaN/±inf 样本、2 维、空序列、非数值序列 ValueError；
    # if_freq_hz/fs_hz ≤0 或 bool 亦拒（不抛 TypeError）
    mx = _default_mixer()
    with pytest.raises(ValueError, match="NaN"):
        mx.shift_iq([1 + 0j, float("nan")], 1e3)
    with pytest.raises(ValueError):
        mx.shift_iq([1 + 0j, complex(float("inf"), 0)], 1e3)
    with pytest.raises(ValueError, match="一维"):
        mx.shift_iq([[1 + 0j, 2 + 0j], [3 + 0j, 4 + 0j]], 1e3)
    with pytest.raises(ValueError):
        mx.shift_iq([], 1e3)
    with pytest.raises(ValueError):
        mx.shift_iq(["a", "b"], 1e3)
    with pytest.raises(ValueError):
        mx.shift_iq([1 + 0j, 2 + 0j], 0.0)
    with pytest.raises(ValueError):
        mx.shift_iq([1 + 0j, 2 + 0j], 1e3, fs_hz=0.0)
    with pytest.raises(ValueError):
        mx.shift_iq([1 + 0j, 2 + 0j], True)


def test_sim_mixer13g_upconvert_if_domain_errors_propagate_from_leaf():
    # 用例13: upconvert 的 IF 参数域错由叶子单源抛出（≤0 频率/NaN 功率/bool），
    # 本层不做前置复检、原样透传 ValueError
    mx = _default_mixer()
    with pytest.raises(ValueError, match="正频率"):
        mx.upconvert(0.0, -10.0)
    with pytest.raises(ValueError):
        mx.upconvert(-150e6, -10.0)
    with pytest.raises(ValueError):
        mx.upconvert(150e6, float("nan"))
    with pytest.raises(ValueError):
        mx.upconvert(True, -10.0)


def test_sim_mixer13g_import_reload_registration_idempotent():
    # 用例14: 重复 import/reload 自注册幂等（override=True 不炸），注册表不产生双键，
    # reload 后登记项即新工厂、可正常实例化
    importlib.reload(SIM_MODULE)
    globals()["SimMixer13G"] = SIM_MODULE.SimMixer13G
    globals()["open_sim_mixer"] = SIM_MODULE.open_sim_mixer
    keys = [key for key in REGISTRY if key.lower() == "sim_mixer_13g"]
    assert len(keys) == 1
    factory, meta = lookup_backend("sim_mixer_13g")
    assert factory is SIM_MODULE.open_sim_mixer
    assert meta["caps"]["tx"] is False and meta["caps"]["rx"] is False
    inst = factory({})
    assert isinstance(inst, SimMixer13G)
    assert inst.upconvert(150e6, -10.0)["rf_freq_hz"] == 13e9
