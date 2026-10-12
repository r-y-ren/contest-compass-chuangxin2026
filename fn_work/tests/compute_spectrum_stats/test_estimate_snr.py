"""estimate_snr 行为用例：B10 叶子（公式(4)，对抗用例，fn-implement 阶段填充）。

合成谱：0–20 MHz、0.5 MHz 步进共 41 bin，噪声底 −100 dB；信号带 (4,8) 峰区
5.0–7.0（guard=2 掐掉带内两头各 2 bin 后恰剩这 5 个），干扰带 (13,17) 有效区
14.0–16.0（15.0 处 −20 dB 干扰峰），guard 排除 4+4=8 个边界 bin，其余 23 bin
为噪声。数值断言用测试内独立重算的参考实现（ref_estimate，闭区间归属+带内排序
掐头去尾+线性总和口径，不复用被测代码路径）对照 ±0.1 dB，另加手算字面值锚点。
"""
import math

import pytest

from src.compute_spectrum_stats.estimate_snr import estimate_snr

FREQS_MHZ = [i * 0.5 for i in range(41)]  # 0.0 .. 20.0，步进 0.5
NOISE_FLOOR_DB = -100.0
SIGNAL_BAND = (4.0, 8.0)
INTERFERENCE_BAND = (13.0, 17.0)
SIGNAL_PEAK_DB = {5.0: -21.0, 5.5: -19.0, 6.0: -18.0, 6.5: -19.0, 7.0: -21.0}
INTERFERENCE_DB = {14.0: -30.0, 14.5: -30.0, 15.0: -20.0, 15.5: -30.0, 16.0: -30.0}
SPLIT = {"signal_band": SIGNAL_BAND, "interference_band": INTERFERENCE_BAND}  # guard 缺省=2

VALID_BINS = [{"freq_mhz": 1.0, "power_db": -10.0}]


def make_spectrum():
    """合成谱：信号峰带 + 噪声底 + 干扰带（见模块 docstring 的划分账目）。"""
    bins = [{"freq_mhz": f, "power_db": NOISE_FLOOR_DB} for f in FREQS_MHZ]
    for b in bins:
        if b["freq_mhz"] in SIGNAL_PEAK_DB:
            b["power_db"] = SIGNAL_PEAK_DB[b["freq_mhz"]]
        elif b["freq_mhz"] in INTERFERENCE_DB:
            b["power_db"] = INTERFERENCE_DB[b["freq_mhz"]]
    return bins


def ref_estimate(bins, signal_band, interference_band, guard):
    """独立参考实现：NaN bin 剔除、闭区间归属、带内升序掐头去尾 guard、线性总和。

    guard 排除的边界 bin 同样不计入噪声（与被测口径一致：guard 区不进任何功率和）。
    返回线性功率与 SNR dB、三类计数。
    """
    valid = [
        (b["freq_mhz"], 10.0 ** (b["power_db"] / 10.0))
        for b in bins
        if not math.isnan(b["power_db"])
    ]

    def split(band, exclude=()):
        if band is None:
            return [], []
        lo, hi = band
        in_band = sorted(v for v in valid if lo <= v[0] <= hi and v[0] not in exclude)
        if guard and len(in_band) > 2 * guard:
            return in_band[guard:-guard], in_band[:guard] + in_band[-guard:]
        if guard:
            return [], list(in_band)
        return list(in_band), []

    sig, sig_g = split(signal_band)
    itf, itf_g = split(interference_band, exclude={f for f, _ in sig})
    excluded = (
        {f for f, _ in sig} | {f for f, _ in itf} | {f for f, _ in sig_g} | {f for f, _ in itf_g}
    )
    noise = [v for v in valid if v[0] not in excluded]
    p_signal = sum(p for _, p in sig)
    p_interference = sum(p for _, p in itf)
    p_noise = sum(p for _, p in noise)
    denominator = p_noise + p_interference
    return {
        "snr_db": math.inf if denominator == 0.0 else 10.0 * math.log10(p_signal / denominator),
        "p_signal": p_signal,
        "p_noise": p_noise,
        "p_interference": p_interference,
        "n_signal": len(sig),
        "n_interference": len(itf),
        "n_noise": len(noise),
    }


def test_synthetic_spectrum_snr_matches_independent_reference():
    # 数值对照：SNR/各分量 dB 对独立参考 ±0.1 dB；手算锚点 ≈6.091 dB
    # （p_sig=2·10^-2.1+2·10^-1.9+10^-1.8≈0.056914，分母≈0.014+23·10^-10）
    bins = make_spectrum()
    got = estimate_snr(bins, SPLIT)
    ref = ref_estimate(bins, SIGNAL_BAND, INTERFERENCE_BAND, 2)
    assert got["available"] is True
    assert got["degenerate"] is False
    assert got["reason"] is None
    assert got["snr_db"] == pytest.approx(ref["snr_db"], abs=0.1)
    assert got["snr_db"] == pytest.approx(6.091, abs=0.1)
    assert got["p_signal_db"] == pytest.approx(10.0 * math.log10(ref["p_signal"]), abs=1e-6)
    assert got["p_noise_db"] == pytest.approx(10.0 * math.log10(ref["p_noise"]), abs=1e-6)
    assert got["p_interference_db"] == pytest.approx(
        10.0 * math.log10(ref["p_interference"]), abs=1e-6
    )
    # 划分账目：信号 5 + 干扰 5 + 噪声 23 + guard 8 = 41
    assert (got["n_signal_bins"], got["n_interference_bins"], got["n_noise_bins"]) == (5, 5, 23)
    assert got["n_guard_bins"] == 8
    assert got["n_invalid_bins"] == 0
    assert got["n_skipped_bins"] == 8


def test_no_interference_band_denominator_is_noise_only():
    # 干扰带 None：分母只含噪声——SNR ≡ p_signal_db − p_noise_db（dB 减法恒等）
    bins = make_spectrum()
    got = estimate_snr(bins, {"signal_band": SIGNAL_BAND, "interference_band": None})
    ref = ref_estimate(bins, SIGNAL_BAND, None, 2)
    assert got["n_interference_bins"] == 0
    assert got["p_interference_db"] is None
    assert got["snr_db"] == pytest.approx(ref["snr_db"], abs=0.1)
    assert got["n_noise_bins"] == ref["n_noise"]
    assert got["snr_db"] == pytest.approx(got["p_signal_db"] - got["p_noise_db"], abs=1e-9)

    # 干扰峰抹平后（无干扰物理场景）：分母只剩噪声底 → 高 SNR，同样对参考
    clean = make_spectrum()
    for b in clean:
        if b["freq_mhz"] in INTERFERENCE_DB:
            b["power_db"] = NOISE_FLOOR_DB
    got_clean = estimate_snr(clean, {"signal_band": SIGNAL_BAND, "interference_band": None})
    ref_clean = ref_estimate(clean, SIGNAL_BAND, None, 2)
    assert got_clean["snr_db"] == pytest.approx(ref_clean["snr_db"], abs=0.1)
    assert got_clean["snr_db"] > 70.0  # 10·log10(0.056914/(32·10^-10)) ≈ 72.5 dB


def test_strong_interference_lowers_snr():
    # 干扰带整体 +20 dB（分母约 ×100）→ SNR 降约 20 dB，且对参考 ±0.1 dB
    base = make_spectrum()
    boosted = make_spectrum()
    for b in boosted:
        if b["freq_mhz"] in INTERFERENCE_DB:
            b["power_db"] += 20.0
    got_base = estimate_snr(base, SPLIT)
    got_boost = estimate_snr(boosted, SPLIT)
    ref_boost = ref_estimate(boosted, SIGNAL_BAND, INTERFERENCE_BAND, 2)
    assert got_boost["snr_db"] == pytest.approx(ref_boost["snr_db"], abs=0.1)
    assert got_boost["snr_db"] < got_base["snr_db"]
    assert got_base["snr_db"] - got_boost["snr_db"] > 15.0


def test_guard_excludes_boundary_leakage_peak():
    # 信号带 (3,7) guard=2 → 唯一成员 bin 5.0；bin 3.0 是带边界泄漏区。
    # 边界放 +10 dB 高峰：guard=2 时该 bin 被排除——结果与无峰完全一致；
    # guard=0 时该峰混入信号 → p_signal_db 抬高 ≥15 dB（反证排除生效）。
    def spec(boundary_db):
        bins = [{"freq_mhz": float(f), "power_db": NOISE_FLOOR_DB} for f in range(11)]
        bins[3]["power_db"] = boundary_db
        bins[5]["power_db"] = -10.0  # 信号峰
        return bins

    quiet = estimate_snr(spec(NOISE_FLOOR_DB), {"signal_band": (3.0, 7.0)})
    leaky = estimate_snr(spec(10.0), {"signal_band": (3.0, 7.0)})
    unguarded = estimate_snr(spec(10.0), {"signal_band": (3.0, 7.0), "edge_guard_bins": 0})

    assert leaky["n_signal_bins"] == 1  # 高峰 bin 不在信号计数里
    assert leaky["n_guard_bins"] == 4  # bin 3/4/6/7 为 guard 排除
    assert leaky["n_skipped_bins"] == 4
    assert leaky["p_signal_db"] == pytest.approx(-10.0, abs=1e-9)
    assert leaky["snr_db"] == pytest.approx(quiet["snr_db"], abs=1e-12)  # 高峰无影响
    assert leaky["p_signal_db"] == pytest.approx(quiet["p_signal_db"], abs=1e-12)

    assert unguarded["n_signal_bins"] == 5  # 无 guard 时边界峰计入信号
    assert unguarded["p_signal_db"] > leaky["p_signal_db"] + 15.0
    assert unguarded["snr_db"] > leaky["snr_db"]


def test_signal_band_emptied_by_guard_reports_unavailable():
    # 信号带 (4,6) 内仅 bin 4/5/6，guard=2 全部落入 guard 区 → 信号带空：
    # available=False、snr None、不抛、非退化（谱内有功率）
    bins = [{"freq_mhz": float(f), "power_db": -50.0} for f in range(11)]
    got = estimate_snr(bins, {"signal_band": (4.0, 6.0)})
    assert got["available"] is False
    assert got["snr_db"] is None
    assert got["degenerate"] is False
    assert got["reason"] == "signal_band_empty"
    assert got["n_signal_bins"] == 0
    assert got["n_guard_bins"] == 3
    assert got["n_skipped_bins"] == 3
    assert got["p_signal_db"] is None


def test_empty_bin_list_unavailable():
    got = estimate_snr([], SPLIT)
    assert got["available"] is False
    assert got["snr_db"] is None
    assert got["degenerate"] is False
    assert got["reason"] == "signal_band_empty"
    assert got["n_signal_bins"] == 0
    assert got["n_skipped_bins"] == 0


def test_all_zero_spectrum_degenerate():
    # 全 −inf dB（线性全 0）→ available=False 且 degenerate=True
    bins = [{"freq_mhz": float(f), "power_db": float("-inf")} for f in range(7)]
    got = estimate_snr(bins, {"signal_band": (2.0, 5.0), "edge_guard_bins": 0})
    assert got["available"] is False
    assert got["degenerate"] is True
    assert got["snr_db"] is None
    assert got["reason"] == "degenerate_spectrum"
    assert got["n_signal_bins"] == 4  # 有归属 bin，但功率全零 → 退化而非空带
    assert got["p_signal_db"] is None

    # dB 极负致线性下溢为 0 → 同样退化
    underflow = [{"freq_mhz": float(f), "power_db": -1.0e6} for f in range(7)]
    got_u = estimate_snr(underflow, {"signal_band": (2.0, 5.0), "edge_guard_bins": 0})
    assert got_u["available"] is False
    assert got_u["degenerate"] is True


def test_nan_power_bin_skipped_and_counted():
    # 追加一个 NaN bin（乱序插入）：跳过计数、不参与功率，结果与干净谱一致
    clean = make_spectrum()
    dirty = make_spectrum()
    dirty.append({"freq_mhz": 0.25, "power_db": float("nan")})
    got = estimate_snr(dirty, SPLIT)
    ref = ref_estimate(dirty, SIGNAL_BAND, INTERFERENCE_BAND, 2)
    assert got["n_invalid_bins"] == 1
    assert got["n_guard_bins"] == 8
    assert got["n_skipped_bins"] == 9
    assert got["snr_db"] == pytest.approx(ref["snr_db"], abs=0.1)
    got_clean = estimate_snr(clean, SPLIT)
    assert got["snr_db"] == pytest.approx(got_clean["snr_db"], abs=1e-12)
    assert got["p_signal_db"] == pytest.approx(got_clean["p_signal_db"], abs=1e-12)
    assert got["p_noise_db"] == pytest.approx(got_clean["p_noise_db"], abs=1e-12)


def test_db_roundtrip_single_bin_identity():
    # dB→线性→求和→dB 往返：单 bin 分量 dB 恒等于原 bin dB；
    # 两等值噪声 bin 求和 → −100+10·log10(2)；SNR 满足 dB 减法恒等
    bins = [
        {"freq_mhz": 1.0, "power_db": -13.37},
        {"freq_mhz": 2.0, "power_db": -100.0},
        {"freq_mhz": 3.0, "power_db": -100.0},
    ]
    split = {"signal_band": (0.9, 1.1), "interference_band": None, "edge_guard_bins": 0}
    got = estimate_snr(bins, split)
    assert got["n_signal_bins"] == 1
    assert got["p_signal_db"] == pytest.approx(-13.37, abs=1e-9)  # 单 bin 恒等
    assert got["p_noise_db"] == pytest.approx(-100.0 + 10.0 * math.log10(2.0), abs=1e-9)
    assert got["snr_db"] == pytest.approx(got["p_signal_db"] - got["p_noise_db"], abs=1e-9)

    # 噪声也只剩单 bin：p_noise_db 严格回到该 bin 的 dB
    got_single_noise = estimate_snr(bins[:2], split)
    assert got_single_noise["p_noise_db"] == pytest.approx(-100.0, abs=1e-9)
    assert got_single_noise["snr_db"] == pytest.approx(-13.37 - (-100.0), abs=1e-9)


def test_zero_noise_denominator_infinite_snr():
    # 噪声 bin 全 −inf dB（线性 0）→ 分母为零：snr_db=+inf，仍 available
    bins = [
        {"freq_mhz": 1.0, "power_db": -10.0},
        {"freq_mhz": 2.0, "power_db": float("-inf")},
        {"freq_mhz": 3.0, "power_db": float("-inf")},
    ]
    got = estimate_snr(bins, {"signal_band": (0.9, 1.1), "edge_guard_bins": 0})
    assert got["available"] is True
    assert got["degenerate"] is False
    assert got["snr_db"] == math.inf
    assert got["p_noise_db"] is None
    assert got["p_interference_db"] is None


@pytest.mark.parametrize(
    "split_params",
    [
        pytest.param({}, id="missing-signal-band"),
        pytest.param({"signal_band": None}, id="signal-band-none"),
        pytest.param({"signal_band": (5.0,)}, id="signal-band-1tuple"),
        pytest.param({"signal_band": (1.0, 2.0, 3.0)}, id="signal-band-3tuple"),
        pytest.param({"signal_band": 4.5}, id="signal-band-float"),
        pytest.param({"signal_band": "12"}, id="signal-band-str"),
        pytest.param({"signal_band": (2.0, 1.0)}, id="signal-band-lo-gt-hi"),
        pytest.param({"signal_band": (1.0, 1.0)}, id="signal-band-lo-eq-hi"),
        pytest.param({"signal_band": (float("nan"), 5.0)}, id="signal-band-nan-lo"),
        pytest.param({"signal_band": (1.0, float("inf"))}, id="signal-band-inf-hi"),
        pytest.param({"signal_band": (1.0, 2.0), "interference_band": (9.0,)}, id="itf-1tuple"),
        pytest.param({"signal_band": (1.0, 2.0), "interference_band": (3.0, 2.0)}, id="itf-lo-gt-hi"),
        pytest.param({"signal_band": (1.0, 2.0), "edge_guard_bins": -1}, id="guard-negative"),
        pytest.param({"signal_band": (1.0, 2.0), "edge_guard_bins": 1.5}, id="guard-float"),
        pytest.param({"signal_band": (1.0, 2.0), "edge_guard_bins": True}, id="guard-bool"),
    ],
)
def test_invalid_split_params_rejected(split_params):
    with pytest.raises(ValueError):
        estimate_snr(VALID_BINS, split_params)


@pytest.mark.parametrize(
    "bad_bins",
    [
        pytest.param(({"freq_mhz": 1.0, "power_db": -10.0},), id="tuple"),
        pytest.param({"freq_mhz": 1.0}, id="dict"),
        pytest.param(None, id="none"),
        pytest.param("bins", id="str"),
        pytest.param(42, id="int"),
    ],
)
def test_power_bins_not_list_rejected(bad_bins):
    with pytest.raises(ValueError, match="power_bins"):
        estimate_snr(bad_bins, {"signal_band": (1.0, 2.0)})


def test_counter_fields_partition_total_bins():
    # 计数不变式：三分计数 + 跳过 == 总 bin 数；跳过 = guard + 坏 bin
    bins = make_spectrum()
    bins.append({"freq_mhz": 0.25, "power_db": float("nan")})
    for split in (SPLIT, {"signal_band": SIGNAL_BAND, "interference_band": None}):
        got = estimate_snr(bins, split)
        assert (
            got["n_signal_bins"]
            + got["n_noise_bins"]
            + got["n_interference_bins"]
            + got["n_skipped_bins"]
            == len(bins)
        )
        assert got["n_skipped_bins"] == got["n_guard_bins"] + got["n_invalid_bins"]
