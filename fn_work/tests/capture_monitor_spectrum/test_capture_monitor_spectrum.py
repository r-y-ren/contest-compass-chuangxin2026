"""capture_monitor_spectrum 行为用例：验收 slug=monitor_capture（FFT 谱 bin+分段限带+自漏扣除+流异常透传）。"""
import math

import numpy as np
import pytest

from src.calibrate_leakage.calibrate_leakage import calibrate_leakage
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
