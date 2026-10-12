"""compute_spectrum_stats 行为用例：B10 顶层（R17 统计行，对抗用例）。

合成谱两套（均 41 bin、0.5 MHz 步进）：
- 低频谱 0–20 MHz：信号带 (4,8) 九候选 guard=2 掐两头各 2 后剩 5 bin
  （5.0–7.0）全 −40 dB，干扰带 (13,17) 有效区 14.0–16.0 共 5 bin 全 −70 dB，
  噪声底 −100 dB 共 23 bin（guard 排除 4+4=8 边界 bin 不进任何功率和）；
- WiFi 段谱 2400–2420 MHz：同构（+2400 偏移），用于泄漏表扣除方向用例。

数值断言用测试内独立重算的参考实现 ref_split（闭区间归属+带内升序掐头去尾
guard+线性总和口径，不复用被测代码路径），对照 ±1e-6 dB；另加手算字面值锚点。
"""
import math

import pytest

from src.compute_spectrum_stats.compute_spectrum_stats import compute_spectrum_stats
from src.calibrate_leakage.calibrate_leakage import CalibrationWarn, calibrate_leakage

FREQS_MHZ = [i * 0.5 for i in range(41)]  # 0.0 .. 20.0，步进 0.5
NOISE_FLOOR_DB = -100.0
SIGNAL_DB = -40.0
INTERFERENCE_DB = -70.0
SIGNAL_BAND = (4.0, 8.0)
INTERFERENCE_BAND = (13.0, 17.0)
REFERENCE = {
    "signal_band": SIGNAL_BAND,
    "interference_band": INTERFERENCE_BAND,
}


def make_spectrum(offset: float = 0.0) -> list:
    """合成谱：信号带 + 噪声底 + 干扰带（见模块 docstring 的划分账目）。"""
    bins = []
    for freq in FREQS_MHZ:
        freq = freq + offset
        if SIGNAL_BAND[0] + offset <= freq <= SIGNAL_BAND[1] + offset:
            power = SIGNAL_DB
        elif INTERFERENCE_BAND[0] + offset <= freq <= INTERFERENCE_BAND[1] + offset:
            power = INTERFERENCE_DB
        else:
            power = NOISE_FLOOR_DB
        bins.append({"freq_mhz": freq, "power_db": power})
    return bins


def ref_split(bins, signal_band, interference_band=None, guard=2):
    """独立参考实现：闭区间归属、信号优先于干扰、带内升序掐头去尾 guard、线性总和。

    返回 (p_signal, p_noise, p_interference) 线性功率；guard 排除的边界 bin
    不计入任何功率和（与被测口径一致）。不复用 estimate_snr 代码路径。
    """

    def band_all(lo, hi):
        return [b for b in bins if lo <= b["freq_mhz"] <= hi]

    def trim(candidates):
        ordered = sorted(candidates, key=lambda b: b["freq_mhz"])
        hi_index = max(guard, len(ordered) - guard)
        return ordered[guard:hi_index], ordered[:guard] + ordered[hi_index:]

    sig, sig_guarded = trim(band_all(*signal_band))
    sig_freqs = {b["freq_mhz"] for b in sig}
    if interference_band is not None:
        int_candidates = [b for b in band_all(*interference_band) if b["freq_mhz"] not in sig_freqs]
        inter, int_guarded = trim(int_candidates)
    else:
        inter, int_guarded = [], []
    excluded = {b["freq_mhz"] for b in sig_guarded + int_guarded}
    claimed = sig_freqs | {b["freq_mhz"] for b in inter}
    noise = [b for b in bins if b["freq_mhz"] not in claimed and b["freq_mhz"] not in excluded]

    def lin(db):
        return 10.0 ** (db / 10.0)

    return (
        sum(lin(b["power_db"]) for b in sig),
        sum(lin(b["power_db"]) for b in noise),
        sum(lin(b["power_db"]) for b in inter),
    )


def db(power_linear: float) -> float:
    return 10.0 * math.log10(power_linear)


# ---------------------------------------------------------------- full 模式


def test_spectrum_stats_full_mode_snr_matches_independent_calc():
    """full 模式：SNR/各功率分量对照独立重算（反演谱 = 无泄漏原谱）。"""
    bins = make_spectrum()
    row = compute_spectrum_stats({"bins": bins, "timestamp_ms": 10.0, "reference": REFERENCE})
    p_sig, p_noise, p_int = ref_split(bins, SIGNAL_BAND, INTERFERENCE_BAND)

    assert row["mode"] == "full"
    assert row["available"] is True
    assert row["leak_corrected"] is False
    assert row["invalid_bins"] == 0
    assert row["n_signal_bins"] == 5
    assert row["n_interference_bins"] == 5
    assert row["snr_db"] == pytest.approx(db(p_sig / (p_noise + p_int)), abs=1e-6)
    assert row["p_signal_db"] == pytest.approx(db(p_sig), abs=1e-6)
    assert row["p_noise_db"] == pytest.approx(db(p_noise), abs=1e-6)
    assert row["p_interference_db"] == pytest.approx(db(p_int), abs=1e-6)
    # 手算锚点：5×10⁻⁴ / (2.3×10⁻⁹ + 5×10⁻⁷) ≈ 30.0 dB
    assert row["snr_db"] == pytest.approx(30.0, abs=0.1)


def test_spectrum_stats_jsr_inverted_from_band_powers():
    """JSR 反演口径：P_interference/P_signal 线性→dB = p_int_db − p_sig_db。"""
    bins = make_spectrum()
    row = compute_spectrum_stats({"bins": bins, "reference": dict(REFERENCE)})
    p_sig, _, p_int = ref_split(bins, SIGNAL_BAND, INTERFERENCE_BAND)

    assert row["jsr_db"] == pytest.approx(db(p_int / p_sig), abs=1e-6)
    assert row["jsr_source"] == "inverted"
    # 手算锚点：5×10⁻⁷ / 5×10⁻⁴ → −30 dB
    assert row["jsr_db"] == pytest.approx(-30.0, abs=0.1)


def test_spectrum_stats_jsr_signal_power_cross_check_matches_inversion():
    """JSR 交叉口径：已知 signal_power_db=实测 P_signal → 与反演口径一致（同谱）。"""
    bins = make_spectrum()
    p_sig, _, p_int = ref_split(bins, SIGNAL_BAND, INTERFERENCE_BAND)
    inverted = compute_spectrum_stats({"bins": bins, "reference": dict(REFERENCE)})
    cross = compute_spectrum_stats(
        {
            "bins": bins,
            "reference": {**REFERENCE, "signal_power_db": db(p_sig)},
        }
    )

    assert cross["jsr_db"] == pytest.approx(inverted["jsr_db"], abs=1e-9)
    assert cross["jsr_source"] == "signal_power"
    # 已知功率偏 10 dB → JSR 同向偏 −10 dB（交叉口径生效，非透传反演值）
    shifted = compute_spectrum_stats(
        {"bins": bins, "reference": {**REFERENCE, "signal_power_db": db(p_sig) + 10.0}}
    )
    assert shifted["jsr_db"] == pytest.approx(db(p_int / p_sig) - 10.0, abs=1e-6)


def test_spectrum_stats_flatness_band_embedded_pass_and_violation():
    """flatness_band 嵌入 → flatness_ 前缀块（flatness_pass/flatness_db/越限）。"""
    flat_bins = make_spectrum()
    flat_row = compute_spectrum_stats(
        {"bins": flat_bins, "reference": {**REFERENCE, "flatness_band": (1.0, 3.0)}}
    )
    assert flat_row["flatness_available"] is True
    assert flat_row["flatness_db"] == pytest.approx(0.0)
    assert flat_row["flatness_pass"] is True
    assert flat_row["flatness_violation"] is False
    assert flat_row["flatness_n_bins"] == 5

    tilt_bins = make_spectrum()
    for bin_item in tilt_bins:  # 带内 6 dB 斜坡 > 4 dB 判据 → 越限
        if 1.0 <= bin_item["freq_mhz"] <= 3.0:
            bin_item["power_db"] = -106.0 + (bin_item["freq_mhz"] - 1.0) * 3.0
    tilt_row = compute_spectrum_stats(
        {"bins": tilt_bins, "reference": {**REFERENCE, "flatness_band": (1.0, 3.0)}}
    )
    assert tilt_row["flatness_db"] == pytest.approx(6.0)
    assert tilt_row["flatness_pass"] is False
    assert tilt_row["flatness_violation"] is True
    assert tilt_row["flatness_max_at_mhz"] == pytest.approx(3.0)
    assert tilt_row["flatness_min_at_mhz"] == pytest.approx(1.0)

    absent = compute_spectrum_stats({"bins": make_spectrum(), "reference": dict(REFERENCE)})
    assert absent["flatness_available"] is False
    assert absent["flatness_reason"] == "no_flatness_band"
    assert absent["flatness_db"] is None


def test_spectrum_stats_reference_second_param_fallback():
    """签名兼容：window 未携带 'reference' 键时回落第二参数。"""
    row = compute_spectrum_stats({"bins": make_spectrum()}, reference=dict(REFERENCE))
    assert row["mode"] == "full"
    assert row["available"] is True
    assert row["snr_db"] == pytest.approx(30.0, abs=0.1)


# ------------------------------------------------------------ power_only 模式


def test_spectrum_stats_no_reference_power_only_with_note():
    """无 reference → power_only：全谱线和/20 分位底噪/note 标注，不出 SNR 字段。"""
    bins = make_spectrum()
    row = compute_spectrum_stats({"bins": bins, "timestamp_ms": 5.0})

    assert row["mode"] == "power_only"
    assert row["available"] is True
    assert row["note"] == "无参考参数——仅功率统计"
    assert "snr_db" not in row and "jsr_db" not in row
    total_linear = sum(10.0 ** (b["power_db"] / 10.0) for b in bins)
    assert row["p_total_db"] == pytest.approx(db(total_linear), abs=1e-6)
    # 20 分位：41 个有限功率排序后 rank=0.2×40=8 落在噪声底平台 → −100 dB
    assert row["noise_floor_db"] == pytest.approx(NOISE_FLOOR_DB)
    assert row["peak_db"] == pytest.approx(SIGNAL_DB)
    assert row["peak_at_mhz"] == pytest.approx(SIGNAL_BAND[0])  # 并列取首个


def test_spectrum_stats_power_only_peak_location():
    """power_only 峰值定位：peak_db/peak_at_mhz 指向最大功率 bin（并列取首）。"""
    bins = [
        {"freq_mhz": 2400.0, "power_db": -50.0},
        {"freq_mhz": 2402.0, "power_db": -30.0},
        {"freq_mhz": 2404.0, "power_db": -55.0},
        {"freq_mhz": 2406.0, "power_db": -30.0},
    ]
    row = compute_spectrum_stats({"bins": bins})
    assert row["peak_db"] == pytest.approx(-30.0)
    assert row["peak_at_mhz"] == pytest.approx(2402.0)
    assert row["available"] is True


# ------------------------------------------------------------- 自漏扣除口径


@pytest.fixture()
def leakage_table(tmp_path):
    """泄漏标定表：2400 MHz 处 −20 dB 耦合线性抬升至 2420 MHz 处 0 dB。"""
    table_path = tmp_path / "leakage_table.json"
    calibrate_leakage(
        session_data={
            "points": [
                {"freq_mhz": 2400.0, "coupling_db": -20.0},
                {"freq_mhz": 2410.0, "coupling_db": -10.0},
                {"freq_mhz": 2420.0, "coupling_db": 0.0},
            ],
            "out_path": str(table_path),
        }
    )
    assert table_path.exists()
    return str(table_path)


@pytest.fixture()
def wifi_window():
    """WiFi 段窗口：信号带 (2416,2420)（耦合近 0），干扰带 (2404,2408) 与噪声
    偏低频段（耦合 −20…−11 dB）——扣漏后噪声/干扰降幅远大于信号。"""
    bins = []
    for freq in FREQS_MHZ:
        freq = 2400.0 + freq
        if 2416.0 <= freq <= 2420.0:
            power = SIGNAL_DB
        elif 2404.0 <= freq <= 2408.0:
            power = INTERFERENCE_DB
        else:
            power = NOISE_FLOOR_DB
        bins.append({"freq_mhz": freq, "power_db": power})
    return {
        "bins": bins,
        "timestamp_ms": 99.0,
        "reference": {
            "signal_band": (2416.0, 2420.0),
            "interference_band": (2404.0, 2408.0),
        },
    }


def test_spectrum_stats_leakage_correction_raises_snr(leakage_table, wifi_window):
    """泄漏表扣除方向：扣漏后底噪降 → SNR 升（统计用扣除后谱）。"""
    corrected = compute_spectrum_stats({**wifi_window, "leakage_table_path": leakage_table})
    raw = compute_spectrum_stats(dict(wifi_window))

    assert corrected["leak_corrected"] is True
    assert raw["leak_corrected"] is False
    assert corrected["p_noise_db"] < raw["p_noise_db"]
    assert corrected["snr_db"] > raw["snr_db"]
    # 输入窗口 bins 不被原地改动
    assert all(b["power_db"] == NOISE_FLOOR_DB or b["power_db"] in (SIGNAL_DB, INTERFERENCE_DB) for b in wifi_window["bins"])


def test_spectrum_stats_missing_leakage_table_not_corrected(tmp_path, wifi_window):
    """表缺失：读数原样保留（leak_corrected=False），结果与无表调用一致。"""
    missing = compute_spectrum_stats(
        {**wifi_window, "leakage_table_path": str(tmp_path / "absent.json")}
    )
    raw = compute_spectrum_stats(dict(wifi_window))

    assert missing["leak_corrected"] is False
    assert missing == raw


def test_spectrum_stats_empty_leakage_table_not_corrected(tmp_path, wifi_window):
    """空标定表（标定会话 points=[] 真实产出 "table": []）：不抛不扣
    （leak_corrected=False），统计与无表调用一致，行附 leak_note='empty_table'。"""
    table_path = tmp_path / "empty_table.json"
    with pytest.raises(CalibrationWarn):  # 0 点 < 3：表已写出（insufficient）并抛警告
        calibrate_leakage(session_data={"points": [], "out_path": str(table_path)})

    empty = compute_spectrum_stats({**wifi_window, "leakage_table_path": str(table_path)})
    raw = compute_spectrum_stats(dict(wifi_window))

    assert empty["leak_corrected"] is False
    assert empty["leak_note"] == "empty_table"
    assert "leak_note" not in raw  # 有表可扣/无表时不出现空表标注
    # 除 leak_note 标注外，统计结果与无表调用完全一致（读数原样保留）
    assert {k: v for k, v in empty.items() if k != "leak_note"} == raw


# ------------------------------------------------------------- 退化与形状错


def test_spectrum_stats_empty_bins_unavailable_both_modes():
    """空 bins：无 reference → power_only 空 metrics available False；
    有 reference → full 模式 signal_band_empty 不可用。"""
    power_only = compute_spectrum_stats({"bins": [], "timestamp_ms": 7})
    assert power_only["mode"] == "power_only"
    assert power_only["available"] is False
    assert power_only["p_total_db"] is None
    assert power_only["peak_db"] is None
    assert power_only["noise_floor_db"] is None
    assert power_only["note"] == "无参考参数——仅功率统计"
    assert power_only["invalid_bins"] == 0

    full = compute_spectrum_stats({"bins": [], "reference": dict(REFERENCE)})
    assert full["mode"] == "full"
    assert full["available"] is False
    assert full["reason"] == "signal_band_empty"
    assert full["jsr_db"] is None
    assert full["invalid_bins"] == 0


@pytest.mark.parametrize(
    "bad_window",
    [
        ["not", "a", "dict"],
        "window-as-string",
        {"timestamp_ms": 1.0},  # 缺 'bins'
        {"bins": {"freq_mhz": 4.0}},  # bins 非 list
    ],
)
def test_spectrum_stats_malformed_window_rejected(bad_window):
    """window 形状错（非 dict/缺 bins/bins 非 list）→ ValueError。"""
    with pytest.raises(ValueError):
        compute_spectrum_stats(bad_window)


def test_spectrum_stats_nan_bins_counted_invalid():
    """NaN/非 dict bin 计入 invalid_bins，不进功率和（full 与 power_only 一致）。"""
    bins = make_spectrum() + [
        {"freq_mhz": 21.0, "power_db": float("nan")},
        "garbage-bin",
    ]
    full = compute_spectrum_stats({"bins": bins, "reference": dict(REFERENCE)})
    assert full["invalid_bins"] == 2
    assert full["n_invalid_bins"] == 2
    assert full["available"] is True  # 有效 bin 仍出统计
    clean = compute_spectrum_stats({"bins": make_spectrum(), "reference": dict(REFERENCE)})
    assert full["snr_db"] == pytest.approx(clean["snr_db"], abs=1e-9)

    power_only = compute_spectrum_stats({"bins": bins})
    assert power_only["invalid_bins"] == 2
    assert power_only["available"] is True


def test_spectrum_stats_timestamp_passthrough():
    """timestamp_ms 原样透传；缺省为 None。"""
    row = compute_spectrum_stats(
        {"bins": make_spectrum(), "timestamp_ms": 987.5, "reference": dict(REFERENCE)}
    )
    assert row["timestamp_ms"] == 987.5
    absent = compute_spectrum_stats({"bins": make_spectrum()})
    assert absent["timestamp_ms"] is None


# --------------------------- B10 对抗审查回归（None 透传/表缓存/reason 前缀）


def test_spectrum_stats_contained_interference_band_passes_none_jsr_through():
    """高#1 下游回归：干扰带 (2400,2419) 完全含信号带 (2402,2417) → 干扰桶被
    剔/掐尽：p_interference_db=None、jsr_db/jsr_source=None 口径透传，
    snr_db=+inf（噪声/干扰分母为零）。"""
    bins = [{"freq_mhz": float(f), "power_db": -20.0} for f in range(2400, 2420)]
    row = compute_spectrum_stats(
        {
            "bins": bins,
            "timestamp_ms": 1.0,
            "reference": {
                "signal_band": (2402.0, 2417.0),
                "interference_band": (2400.0, 2419.0),
            },
        }
    )
    assert row["mode"] == "full"
    assert row["available"] is True
    assert row["n_interference_bins"] == 0
    assert row["p_interference_db"] is None
    assert row["jsr_db"] is None
    assert row["jsr_source"] is None
    assert row["snr_db"] == math.inf


def test_spectrum_stats_leakage_table_read_once_per_call(monkeypatch, leakage_table, wifi_window):
    """低#5 回归：单次统计调用（window 内 41 个可扣 bin）泄漏表只读一次（旧
    口径逐 bin 重读 41 次）；缓存以调用为界，跨调用各自再读。"""
    import src.calibrate_leakage.calibrate_leakage as leakage_mod

    reads = {"count": 0}
    real_load = leakage_mod._load_table

    def counting_load(path):
        reads["count"] += 1
        return real_load(path)

    monkeypatch.setattr(leakage_mod, "_load_table", counting_load)
    window = {**wifi_window, "leakage_table_path": leakage_table}
    first = compute_spectrum_stats(dict(window))
    assert reads["count"] == 1
    assert first["leak_corrected"] is True
    compute_spectrum_stats(dict(window))
    assert reads["count"] == 2  # 不跨调用缓存


def test_spectrum_stats_invalid_flatness_limit_uses_limit_reason_prefix():
    """低#6 回归：flatness_band 合法而 flatness_limit_db 非法（负数）→ reason
    前缀 invalid_flatness_limit；band 形状非法仍用 invalid_flatness_band 前缀；
    平坦度兜底不影响 SNR 块。"""
    limit_bad = compute_spectrum_stats(
        {
            "bins": make_spectrum(),
            "reference": {
                **REFERENCE,
                "flatness_band": (1.0, 3.0),
                "flatness_limit_db": -1.0,
            },
        }
    )
    assert limit_bad["flatness_available"] is False
    assert limit_bad["flatness_db"] is None
    assert limit_bad["flatness_reason"].startswith("invalid_flatness_limit")
    assert limit_bad["available"] is True  # SNR 口径不受平坦度兜底影响

    band_bad = compute_spectrum_stats(
        {
            "bins": make_spectrum(),
            "reference": {**REFERENCE, "flatness_band": (1.0, 2.0, 3.0)},
        }
    )
    assert band_bad["flatness_reason"].startswith("invalid_flatness_band")
