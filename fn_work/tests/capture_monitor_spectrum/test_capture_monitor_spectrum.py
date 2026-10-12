"""capture_monitor_spectrum 行为用例：验收 slug=monitor_capture（FFT 谱 bin+分段限带+自漏扣除+流异常透传）。"""
import math

import numpy as np
import pytest

from src.calibrate_leakage.calibrate_leakage import CalibrationWarn, calibrate_leakage
from src.capture_monitor_spectrum.capture_monitor_spectrum import (
    MonitorError,
    capture_monitor_spectrum,
)
from src.manage_backend_registry.register_backend import BackendError

DEV_BW = 56.0  # 与 enforce_bandwidth_limit 缺省设备实时带宽一致
BAND_SINGLE = (2400.0, 2408.0)  # 8 MHz <= 56 → 单段，中心 2404.0


def _tone_samples(offset_mhz=7.0, n=64, fs_mhz=DEV_BW):
    """单音复基带样本：offset_mhz 取 fs/nfft 的整数倍（7.0 = 8 bin × 0.875）时正好落在 bin 中心。"""
    phase = 2.0 * np.pi * offset_mhz * np.arange(n) / fs_mhz
    return np.exp(1j * phase).tolist()


def _block(samples, ts=0, overflow=False):
    return {"samples": samples, "ts": ts, "overflow": overflow}


def test_monitor_capture_tone_bin_peak_freq():
    """单音块→峰 bin 频点=段中心+音调频偏（nfft=64，频偏 7.0 MHz 恰为 bin 中心）。"""
    params = {"target_band": BAND_SINGLE, "nfft": 64}
    blocks = list(capture_monitor_spectrum(None, [_block(_tone_samples(7.0))], params))
    assert len(blocks) == 1
    bins = blocks[0]["bins"]
    assert len(bins) == 64
    peak = max(bins, key=lambda row: row["power_db"])
    assert peak["freq_mhz"] == pytest.approx(2404.0 + 7.0, abs=1e-6)
    others = [row["power_db"] for row in bins if row is not peak]
    assert peak["power_db"] > max(others) + 10.0  # 单音能量集中，显著高于旁瓣


def test_monitor_capture_segment_plan_two_segments_limited():
    """2.4G 整段 83.5MHz>56MHz→两段计划透传首块（limited=True），产出块按段轮转。"""
    params = {"target_band": (2400.0, 2483.5)}
    stream = [_block(_tone_samples()) for _ in range(3)]
    blocks = list(capture_monitor_spectrum(None, stream, params))
    plan = blocks[0]["plan"]
    assert plan["limited"] is True
    assert "span_exceeds_device_bw" in plan["note"]
    assert len(plan["segments"]) == 2
    assert [b["segment"] for b in blocks] == [0, 1, 0]
    assert blocks[0]["center_mhz"] == pytest.approx(2428.0)
    assert blocks[1]["center_mhz"] == pytest.approx(2469.75)
    assert "plan" not in blocks[1]  # 计划只附首块


def test_monitor_capture_ts_passthrough():
    """流块 ts 透传为 timestamp_ms。"""
    params = {"target_band": BAND_SINGLE, "nfft": 64}
    stream = [_block(_tone_samples(), ts=101), _block(_tone_samples(), ts=202)]
    blocks = list(capture_monitor_spectrum(None, stream, params))
    assert [b["timestamp_ms"] for b in blocks] == [101, 202]


def test_monitor_capture_ts_missing_falls_back_to_block_index():
    """ts 键缺失→产出块序号兜底（0,1,…，跳过块不占号）。"""
    params = {"target_band": BAND_SINGLE, "nfft": 64}
    stream = [{"samples": _tone_samples()}, {"samples": _tone_samples()}]
    blocks = list(capture_monitor_spectrum(None, stream, params))
    assert [b["timestamp_ms"] for b in blocks] == [0, 1]


def test_monitor_capture_overflow_passthrough():
    """流块 overflow 标志透传到块 meta；缺省 False。"""
    params = {"target_band": BAND_SINGLE, "nfft": 64}
    stream = [_block(_tone_samples(), overflow=True), _block(_tone_samples())]
    blocks = list(capture_monitor_spectrum(None, stream, params))
    assert blocks[0]["overflow"] is True
    assert blocks[1]["overflow"] is False


def test_monitor_capture_leakage_table_corrects_power(tmp_path):
    """ctx 含 leakage_table_path（5 点平坦表 -10dB）→逐 bin corrected=原功率-10 且标注 True。"""
    points = [{"freq_mhz": f, "coupling_db": -10.0} for f in (2400.0, 2425.0, 2450.0, 2475.0, 2500.0)]
    table_path = tmp_path / "leak5.json"
    calibrate_leakage(session_data={"points": points, "out_path": str(table_path)})
    rng = np.random.default_rng(7)
    samples = (rng.standard_normal(64) + 1j * rng.standard_normal(64)).tolist()
    params = {"target_band": BAND_SINGLE, "nfft": 64}
    raw = list(capture_monitor_spectrum(None, [_block(samples)], params))[0]
    corrected = list(
        capture_monitor_spectrum({"leakage_table_path": str(table_path)}, [_block(samples)], params)
    )[0]
    assert raw["leak_corrected"] is False
    assert corrected["leak_corrected"] is True
    for raw_row, cor_row in zip(raw["bins"], corrected["bins"]):
        assert cor_row["freq_mhz"] == pytest.approx(raw_row["freq_mhz"])
        assert cor_row["power_db"] == pytest.approx(raw_row["power_db"] - 10.0, abs=1e-9)


def test_monitor_capture_leakage_table_missing_marks_false_no_raise(tmp_path):
    """表文件缺失→不抛异常、不扣不改（与无表基线完全一致），标注 False。"""
    params = {
        "target_band": BAND_SINGLE,
        "nfft": 64,
        "leakage_table_path": str(tmp_path / "absent.json"),
    }
    blocks = list(capture_monitor_spectrum(None, [_block(_tone_samples())], params))
    assert blocks[0]["leak_corrected"] is False
    baseline = list(
        capture_monitor_spectrum(None, [_block(_tone_samples())], {"target_band": BAND_SINGLE, "nfft": 64})
    )[0]
    assert blocks[0]["bins"] == baseline["bins"]


def test_monitor_capture_leakage_table_empty_no_deduct_no_raise(tmp_path):
    """空标定表（标定会话 points=[] 真实产出 "table": []）→不抛不扣：
    leak_corrected=False、bins 与无表基线一致，块 meta 附 leak_note='empty_table'。"""
    table_path = tmp_path / "leak_empty.json"
    with pytest.raises(CalibrationWarn):  # 0 点 < 3：表已写出（insufficient）并抛警告
        calibrate_leakage(session_data={"points": [], "out_path": str(table_path)})
    params = {
        "target_band": BAND_SINGLE,
        "nfft": 64,
        "leakage_table_path": str(table_path),
    }
    blocks = list(capture_monitor_spectrum(None, [_block(_tone_samples())], params))
    assert blocks[0]["leak_corrected"] is False
    assert blocks[0]["leak_note"] == "empty_table"
    baseline = list(
        capture_monitor_spectrum(None, [_block(_tone_samples())], {"target_band": BAND_SINGLE, "nfft": 64})
    )[0]
    assert blocks[0]["bins"] == baseline["bins"]
    assert "leak_note" not in baseline  # 有表可扣/无表时不出现空表标注


def test_monitor_capture_nan_block_skipped_and_counted():
    """IQ 含 NaN 的块跳过不产出，计数透传到下一产出块 invalid_blocks_so_far。"""
    params = {"target_band": BAND_SINGLE, "nfft": 64}
    bad = [complex(np.nan, 0.5)] * 64
    stream = [_block(_tone_samples()), _block(bad), _block(_tone_samples())]
    blocks = list(capture_monitor_spectrum(None, stream, params))
    assert len(blocks) == 2
    assert blocks[0]["invalid_blocks_so_far"] == 0
    assert blocks[1]["invalid_blocks_so_far"] == 1


def test_monitor_capture_empty_block_skipped():
    """空样本块/缺 samples 键的块跳过不产出、不计无效。"""
    params = {"target_band": BAND_SINGLE, "nfft": 64}
    stream = [
        _block(_tone_samples()),
        _block([]),
        {"ts": 9},  # 缺 samples 键
        _block(_tone_samples()),
    ]
    blocks = list(capture_monitor_spectrum(None, stream, params))
    assert len(blocks) == 2
    assert all(b["invalid_blocks_so_far"] == 0 for b in blocks)


def test_monitor_capture_max_bins_truncates():
    """max_bins=8 截断每块 bins 数（保低频端、升序频轴不变）。"""
    params = {"target_band": BAND_SINGLE, "nfft": 32, "max_bins": 8}
    blocks = list(capture_monitor_spectrum(None, [_block(_tone_samples(n=32))], params))
    bins = blocks[0]["bins"]
    assert len(bins) == 8
    freqs = [row["freq_mhz"] for row in bins]
    assert freqs == sorted(freqs)
    assert freqs[0] == pytest.approx(2404.0 - DEV_BW / 2.0)  # 截断保留频轴最低端


def test_monitor_capture_monitor_error_passthrough():
    """目标频段超设备能力域→enforce_bandwidth_limit 的 MonitorError 调用时透传。"""
    with pytest.raises(MonitorError):
        capture_monitor_spectrum(None, [], {"target_band": (10.0, 20.0)})


def test_monitor_capture_value_error_bad_band():
    """target_band 形状非法（lo>=hi）→调用时 ValueError 透传。"""
    with pytest.raises(ValueError):
        capture_monitor_spectrum(None, [], {"target_band": (2400.0, 2400.0)})


def test_monitor_capture_backend_error_passthrough():
    """流迭代抛 BackendError→生成器消费时原样透传（不吞不改型）。"""
    def breaking_stream():
        raise BackendError("CH2 失联")
        yield  # pragma: no cover

    gen = capture_monitor_spectrum(None, breaking_stream(), {"target_band": BAND_SINGLE})
    with pytest.raises(BackendError):
        list(gen)


def test_monitor_capture_non_dict_chunk_raises_monitor_error():
    """流块非 dict（流协议破坏=流中断）→迭代时 MonitorError（走停发射路径）。"""
    gen = capture_monitor_spectrum(None, ["not-a-dict"], {"target_band": BAND_SINGLE})
    with pytest.raises(MonitorError):
        list(gen)


def test_monitor_capture_meta_key_set():
    """产出块 meta 键集稳定：首块=基础键+plan，后续块=基础键。"""
    base = {
        "timestamp_ms",
        "segment",
        "center_mhz",
        "bins",
        "overflow",
        "leak_corrected",
        "invalid_blocks_so_far",
    }
    params = {"target_band": BAND_SINGLE, "nfft": 64}
    stream = [_block(_tone_samples()), _block(_tone_samples())]
    blocks = list(capture_monitor_spectrum(None, stream, params))
    assert set(blocks[0]) == base | {"plan"}
    assert set(blocks[1]) == base
    assert isinstance(blocks[0]["segment"], int)


def test_monitor_capture_noise_power_finite():
    """纯噪声块→每 bin power_db 为有限 float，频轴覆盖段中心±设备带宽/2。"""
    rng = np.random.default_rng(11)
    samples = (rng.standard_normal(128) + 1j * rng.standard_normal(128)).tolist()
    params = {"target_band": BAND_SINGLE, "nfft": 128}
    blocks = list(capture_monitor_spectrum(None, [_block(samples)], params))
    bins = blocks[0]["bins"]
    assert len(bins) == 128
    assert all(isinstance(r["power_db"], float) and math.isfinite(r["power_db"]) for r in bins)
    assert bins[0]["freq_mhz"] == pytest.approx(2404.0 - DEV_BW / 2.0)
    assert bins[-1]["freq_mhz"] == pytest.approx(2404.0 + DEV_BW / 2.0 - DEV_BW / 128.0)


# ----------------------------- B10 对抗审查回归（末段频轴/泄漏表单次读入）


def test_monitor_capture_narrow_last_segment_freq_axis_stays_in_band():
    """低#4 回归：(5900,6000)=100MHz>56MHz → 两段；收窄末段（span=44）bin 频轴
    按段实际 span 等比缩放：∈[5956,6000] 不越目标带顶（旧口径恒 56MHz 频轴，
    末段频轴越顶到 6005.125）；满宽段频轴保持设备带宽口径。"""
    params = {"target_band": (5900.0, 6000.0), "nfft": 64}
    stream = [_block(_tone_samples()), _block(_tone_samples())]
    blocks = list(capture_monitor_spectrum(None, stream, params))
    assert [b["segment"] for b in blocks] == [0, 1]
    full_bins, narrow_bins = blocks[0]["bins"], blocks[1]["bins"]
    # 满宽段：频轴=段中心±设备带宽/2（5900 起、步进 56/64），口径不变
    assert full_bins[0]["freq_mhz"] == pytest.approx(5900.0)
    assert full_bins[-1]["freq_mhz"] == pytest.approx(5956.0 - DEV_BW / 64.0)
    # 收窄末段：频轴=段中心±span/2（步进 span/nfft），max ≤ 目标带顶 6000
    assert narrow_bins[0]["freq_mhz"] == pytest.approx(5956.0)
    assert narrow_bins[-1]["freq_mhz"] == pytest.approx(6000.0 - 44.0 / 64.0)
    assert max(r["freq_mhz"] for r in narrow_bins) <= 6000.0 + 1e-9
    assert min(r["freq_mhz"] for r in narrow_bins) >= 5956.0 - 1e-9
    narrow_freqs = [r["freq_mhz"] for r in narrow_bins]
    assert narrow_freqs == sorted(narrow_freqs)


def test_monitor_capture_leakage_table_read_once_per_call(monkeypatch, tmp_path):
    """低#5 回归：同一采集调用（生成器生命周期）泄漏表只读一次——两块同段频轴
    去重后 _load_table 计数=1（旧口径逐块逐频点重读 2×64 次）；且各块按本块
    功率扣除（corrected=本块原始读数−10 dB，非共享首块同频点的结果）。"""
    import src.calibrate_leakage.calibrate_leakage as leakage_mod

    points = [{"freq_mhz": f, "coupling_db": -10.0} for f in (2376.0, 2404.0, 2432.0)]
    table_path = tmp_path / "leak_flat.json"
    calibrate_leakage(session_data={"points": points, "out_path": str(table_path)})

    reads = {"count": 0}
    real_load = leakage_mod._load_table

    def counting_load(path):
        reads["count"] += 1
        return real_load(path)

    monkeypatch.setattr(leakage_mod, "_load_table", counting_load)

    rng_a, rng_b = np.random.default_rng(3), np.random.default_rng(5)
    samples_a = (rng_a.standard_normal(64) + 1j * rng_a.standard_normal(64)).tolist()
    samples_b = (rng_b.standard_normal(64) + 1j * rng_b.standard_normal(64)).tolist()
    params = {"target_band": BAND_SINGLE, "nfft": 64, "leakage_table_path": str(table_path)}
    corrected_blocks = list(
        capture_monitor_spectrum(None, [_block(samples_a), _block(samples_b)], params)
    )
    assert len(corrected_blocks) == 2
    assert all(b["leak_corrected"] is True for b in corrected_blocks)
    assert reads["count"] == 1  # 表只被读一次

    # 扣除语义逐块独立：corrected = 本块原始读数 − 10 dB（平坦耦合表）
    raw_blocks = list(
        capture_monitor_spectrum(
            None,
            [_block(samples_a), _block(samples_b)],
            {"target_band": BAND_SINGLE, "nfft": 64},
        )
    )
    for raw, corrected in zip(raw_blocks, corrected_blocks):
        for raw_row, cor_row in zip(raw["bins"], corrected["bins"]):
            assert cor_row["freq_mhz"] == pytest.approx(raw_row["freq_mhz"])
            assert cor_row["power_db"] == pytest.approx(raw_row["power_db"] - 10.0, abs=1e-9)
