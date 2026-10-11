"""make_spectrogram 对抗单测：谱峰/帧数公式/边界拒参/输入规整/拼接可加性/Parseval——slug=spectrogram。"""
from __future__ import annotations

import numpy as np
import pytest

from src.make_spectrogram.make_spectrogram import make_spectrogram


def _tone(n: int, bin_idx: int, nfft: int) -> np.ndarray:
    """bin 对齐的复单音（每个整窗内相干，谱峰应精确落在 bin_idx）。"""
    return np.exp(2j * np.pi * bin_idx * np.arange(n) / nfft)


def _noise(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(n) + 1j * rng.standard_normal(n)


def test_spectrogram_tone_peak_bin_and_concentration():
    x = _tone(896, 32, 256)  # 896=256+5*128：恰 6 个完整帧、无补零尾帧
    out = make_spectrogram(x, 256, 128, to_db=False, normalize=False)
    spec = out["spec"]
    assert spec.shape == (129, 6)
    peaks = spec.argmax(axis=0)
    assert np.all(np.abs(peaks - 32) <= 1)  # 谱峰在预期 bin（±1 容忍）
    total = spec.sum(axis=0)
    near = spec[29:36, :].sum(axis=0)  # 峰附近 ±3 bin
    assert np.all(near / total >= 0.95)  # 能量集中于主瓣
    out_db = make_spectrogram(x)  # 默认 dB 口径峰位不变
    assert np.all(np.abs(out_db["spec"].argmax(axis=0) - 32) <= 1)


def test_spectrogram_shape_frames_formula():
    x = _noise(1000, 7)
    out = make_spectrogram(x, 256, 128)
    # (1000-256)/128+1 → 6 完整帧 + 1 补零尾帧 = frames=7
    assert out["frames"] == 7
    assert out["spec"].shape == (129, 7)
    assert out["freq_bins"] == 129
    assert out["skipped"] == 0
    assert out["spec"].dtype == np.float32


def test_spectrogram_empty_and_short_input():
    cases = [
        [],
        (),
        np.array([], dtype=np.complex128),
        np.zeros(100, dtype=np.complex128),  # 段长 < 窗长（100 < 256）
    ]
    for x in cases:
        out = make_spectrogram(x)
        assert out["spec"].shape == (0, 0)
        assert out["spec"].dtype == np.float32
        assert out["frames"] == 0
        assert out["skipped"] == 1
        assert out["freq_bins"] == 129


def test_spectrogram_linear_power_nonnegative():
    x = _noise(896, 11)
    out = make_spectrogram(x, 256, 128, to_db=False, normalize=False)
    assert float(out["spec"].min()) >= 0.0  # 功率谱非负
    out_n = make_spectrogram(x, 256, 128, to_db=False, normalize=True)
    assert abs(float(out_n["spec"].max()) - 1.0) < 1e-6  # 线性口径归一→峰值 1


def test_spectrogram_normalized_peak_zero_dbfs():
    x = _noise(512, 13)
    out = make_spectrogram(x)  # to_db=True + normalize=True → dBFS
    assert abs(float(out["spec"].max())) < 1e-4  # 参考最大值归一：峰值 0 dB
    assert float(out["spec"].min()) < -1.0  # 动态范围确实被 dB 压缩展开


def test_spectrogram_param_validation():
    x = np.zeros(64, dtype=np.complex128)
    ok_low = make_spectrogram(x, 8, 4)  # nfft 下边界 8 合法
    assert ok_low["freq_bins"] == 5
    ok_high = make_spectrogram(np.zeros(100, dtype=np.complex128), 2 ** 16)  # 上边界 2**16 合法（段短→跳过）
    assert ok_high["spec"].shape == (0, 0)
    assert ok_high["skipped"] == 1
    with pytest.raises(ValueError):
        make_spectrogram(x, 7, 3)  # nfft < 8
    with pytest.raises(ValueError):
        make_spectrogram(x, 2 ** 16 + 1)  # nfft > 2**16
    with pytest.raises(ValueError):
        make_spectrogram(x, 256, 0)  # hop < 1
    with pytest.raises(ValueError):
        make_spectrogram(x, 256, 256)  # hop == nfft
    with pytest.raises(ValueError):
        make_spectrogram(x, 256, 300)  # hop > nfft


def test_spectrogram_list_ndarray_equivalent():
    arr = _noise(896, 17)
    a = make_spectrogram(list(arr), 128, 64)
    b = make_spectrogram(arr, 128, 64)
    assert a["frames"] == b["frames"]
    assert a["freq_bins"] == b["freq_bins"]
    np.testing.assert_allclose(a["spec"], b["spec"], rtol=1e-6, atol=1e-6)


def test_spectrogram_float_tuple_coercion():
    base = _noise(16, 19)
    pairs = [(float(v.real), float(v.imag)) for v in base]  # (I,Q) 浮点二元组
    a = make_spectrogram(pairs, 8, 4)
    b = make_spectrogram(base, 8, 4)
    np.testing.assert_allclose(a["spec"], b["spec"], rtol=1e-6, atol=1e-6)
    reals = [float(v) for v in base.real]  # 纯实数按 +0j 规整
    c = make_spectrogram(reals, 8, 4)
    d = make_spectrogram(np.asarray(reals, dtype=np.complex128), 8, 4)
    np.testing.assert_allclose(c["spec"], d["spec"], rtol=1e-6, atol=1e-6)
    e = make_spectrogram(np.stack([base.real, base.imag], axis=1), 8, 4)  # (N,2) ndarray 按 I/Q
    np.testing.assert_allclose(e["spec"], b["spec"], rtol=1e-6, atol=1e-6)


def test_spectrogram_concat_frame_additivity():
    a = _noise(1000, 21)
    b = _noise(1000, 22)
    fa = make_spectrogram(a)["frames"]
    fb = make_spectrogram(b)["frames"]
    fab = make_spectrogram(np.concatenate([a, b]))["frames"]
    assert abs(fab - (fa + fb)) <= 1  # 两段拼接帧数相加，共享边界差 1 可容忍


def test_spectrogram_parseval_energy_conservation():
    nfft, hop, n = 256, 128, 896  # 6 个完整帧、无补零
    x = _noise(n, 29)
    out = make_spectrogram(x, nfft, hop, to_db=False, normalize=False)
    k = np.arange(nfft)
    win = 0.5 - 0.5 * np.cos(2 * np.pi * k / nfft)  # 测试内独立实现 hann
    e_time = 0.0
    for start in range(0, n - nfft + 1, hop):
        seg = x[start : start + nfft] * win
        e_time += float(np.sum(np.abs(seg) ** 2))
    e_spec = float(np.sum(out["spec"].astype(np.float64)))
    ratio = e_spec / (nfft * e_time)  # 单边 rfft Parseval：ratio ∈ [0.5, 1]
    assert 0.45 <= ratio <= 1.05  # 时域与谱总能量同数量级


def test_spectrogram_default_hop_and_params_echo():
    x = np.zeros(1000, dtype=np.complex128)
    out = make_spectrogram(x)
    assert out["params"] == {"nfft": 256, "hop": 128, "window": "hann"}  # hop 缺省 nfft//2
    assert np.isfinite(out["spec"]).all()  # 全零信号 dB 归一后仍有限
    finer = make_spectrogram(x, 256, 64)
    assert finer["params"]["hop"] == 64
    assert finer["frames"] > out["frames"]  # 更小 hop → 更多帧


def test_spectrogram_preview_png_optional(tmp_path):
    x = _tone(896, 32, 256)
    out = make_spectrogram(x, preview_png=str(tmp_path / "spec.png"))
    if out.get("preview") is not None:  # matplotlib 在场才校验落盘，测试不强依赖
        assert tmp_path.joinpath("spec.png").exists()
    out_empty = make_spectrogram([], preview_png=str(tmp_path / "empty.png"))  # 空谱图渲染失败也不抛
    assert out_empty["spec"].shape == (0, 0)
