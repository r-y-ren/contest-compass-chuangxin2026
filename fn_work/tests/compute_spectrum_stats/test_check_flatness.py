"""check_flatness 对抗单测：验收 slug=spectrum_stats（B10 叶子，≤4dB 带内平坦度判据）。"""
import math

import pytest

from src.compute_spectrum_stats.check_flatness import check_flatness

OK_KEYS = {"flatness_db", "limit_db", "pass", "n_bins", "max_at_mhz", "min_at_mhz", "violation"}
UNAVAILABLE_KEYS = {"available", "n_bins", "reason", "flatness_db"}


def _bins(freqs, powers):
    return [
        {"freq_mhz": f, "power_db": p} for f, p in zip(freqs, powers)
    ]


def test_flat_spectrum_passes_with_default_limit():
    # ±0.5dB 纹波：max−min = 1.0dB < 4dB 默认判据（EN 300 328 B.7 口径）。
    bins = _bins(
        [2400.0, 2401.0, 2402.0, 2403.0, 2404.0, 2405.0],
        [-20.0, -20.5, -19.5, -20.2, -19.8, -20.1],
    )
    result = check_flatness(bins, (2400.0, 2405.0))
    assert set(result) == OK_KEYS
    assert result["pass"] is True
    assert result["violation"] is False
    assert result["flatness_db"] == pytest.approx(1.0)
    assert result["limit_db"] == pytest.approx(4.0)  # 默认判据 4.0
    assert result["n_bins"] == 6


def test_tilted_spectrum_6db_fails():
    bins = _bins([2400.0, 2401.0, 2402.0, 2403.0], [-20.0, -18.0, -17.0, -14.0])
    result = check_flatness(bins, (2400.0, 2403.0))
    assert result["pass"] is False
    assert result["violation"] is True
    assert result["flatness_db"] == pytest.approx(6.0)


def test_exactly_at_limit_passes():
    # 恰 4.0dB：<= 口径，等值通过，violation 为 False。
    bins = _bins([2400.0, 2402.0, 2404.0], [-10.0, -8.0, -6.0])
    result = check_flatness(bins, (2400.0, 2404.0))
    assert result["flatness_db"] == pytest.approx(4.0)
    assert result["pass"] is True
    assert result["violation"] is False


def test_three_bins_exactly_passing():
    # 3 bin 是下限样本量：恰 3 个带内 bin 且平坦度贴判据仍可判（pass）。
    bins = _bins([2400.0, 2401.0, 2402.0], [-20.0, -17.5, -16.0])
    result = check_flatness(bins, (2400.0, 2402.0))
    assert result["n_bins"] == 3
    assert result["flatness_db"] == pytest.approx(4.0)
    assert result["pass"] is True


def test_two_bins_insufficient_not_raising():
    bins = _bins([2400.0, 2401.0], [-20.0, -19.0])
    result = check_flatness(bins, (2400.0, 2401.0))
    assert set(result) == UNAVAILABLE_KEYS
    assert result["available"] is False
    assert result["n_bins"] == 2
    assert result["reason"] == "insufficient_bins"
    assert result["flatness_db"] is None


def test_zero_in_band_bins_insufficient():
    # 带外全排除后带内 0 bin：不可用而非异常。
    bins = _bins([2300.0, 2305.0, 2310.0], [-20.0, -19.0, -18.0])
    result = check_flatness(bins, (2400.0, 2480.0))
    assert result["available"] is False
    assert result["n_bins"] == 0
    assert result["reason"] == "insufficient_bins"
    assert result["flatness_db"] is None


def test_nan_and_inf_bins_skipped():
    # NaN/inf 功率 bin 不计入 n_bins，也不污染 max/min（否则 -inf/+50 会翻转结论）。
    bins = _bins(
        [2400.0, 2401.0, 2402.0, 2403.0, 2404.0],
        [-20.0, float("nan"), -19.0, float("inf"), -17.0],
    )
    result = check_flatness(bins, (2400.0, 2404.0))
    assert result["n_bins"] == 3
    assert result["flatness_db"] == pytest.approx(3.0)
    assert result["max_at_mhz"] == pytest.approx(2404.0)
    assert result["min_at_mhz"] == pytest.approx(2400.0)
    assert result["pass"] is True


def test_max_min_frequency_location_and_ties():
    # 带外高峰（2399 MHz 处 0dB）不得参与；最大功率并列取首个出现频点。
    bins = [
        {"freq_mhz": 2399.0, "power_db": 0.0},  # 带外：闭区间也不含
        {"freq_mhz": 2400.0, "power_db": -30.0},
        {"freq_mhz": 2402.0, "power_db": -10.0},
        {"freq_mhz": 2405.0, "power_db": -25.0},
        {"freq_mhz": 2408.0, "power_db": -10.0},  # 与 2402 并列最大 → 取 2402
    ]
    result = check_flatness(bins, (2400.0, 2410.0))
    assert result["n_bins"] == 4
    assert result["flatness_db"] == pytest.approx(20.0)
    assert result["max_at_mhz"] == pytest.approx(2402.0)
    assert result["min_at_mhz"] == pytest.approx(2400.0)
    assert result["violation"] is True


def test_band_edges_closed_interval():
    # 闭区间：恰在 lo/hi 边界上的 bin 计入，且参与 max/min。
    bins = _bins([2400.0, 2402.0, 2404.0], [-12.0, -16.0, -9.0])
    result = check_flatness(bins, (2400.0, 2404.0))
    assert result["n_bins"] == 3
    assert result["flatness_db"] == pytest.approx(7.0)
    assert result["max_at_mhz"] == pytest.approx(2404.0)
    assert result["min_at_mhz"] == pytest.approx(2402.0)


@pytest.mark.parametrize(
    "bad_band",
    [
        (2400.0,),  # 一元
        (2400.0, 2480.0, 2500.0),  # 三元
        "2400-2480",  # 字符串区间
        2400,  # 裸数值
        (2400.0, "2480.0"),  # 元素非数值
        (float("nan"), 2480.0),  # NaN 元素
        (2400.0, float("inf")),  # 非有限元素
        None,
    ],
)
def test_bad_band_shape_rejected(bad_band):
    bins = _bins([2400.0, 2401.0, 2402.0], [-20.0, -19.0, -18.0])
    with pytest.raises(ValueError):
        check_flatness(bins, bad_band)


@pytest.mark.parametrize("bad_limit", [float("nan"), -4.0, -0.1, "4", True, None])
def test_bad_limit_rejected(bad_limit):
    bins = _bins([2400.0, 2401.0, 2402.0], [-20.0, -19.0, -18.0])
    with pytest.raises(ValueError):
        check_flatness(bins, (2400.0, 2402.0), limit_db=bad_limit)


def test_power_bins_container_shape_rejected():
    with pytest.raises(ValueError):
        check_flatness("not-a-bin-list", (2400.0, 2480.0))


def test_reversed_band_treated_as_empty_not_error():
    # lo>hi：空带 → 不可用返回，不抛（区别于形状错）。
    bins = _bins([2400.0, 2401.0, 2402.0], [-20.0, -19.0, -18.0])
    result = check_flatness(bins, (2480.0, 2400.0))
    assert result["available"] is False
    assert result["n_bins"] == 0


def test_malformed_bins_skipped_not_fatal():
    # 缺字段/非 dict bin：跳过而非抛错；剩余 3 个可用 bin 仍出结论。
    bins = [
        {"freq_mhz": 2400.0},  # 缺 power_db
        {"power_db": -18.0},  # 缺 freq_mhz
        "garbage",
        {"freq_mhz": 2401.0, "power_db": -20.0},
        {"freq_mhz": 2402.0, "power_db": -19.0},
        {"freq_mhz": 2403.0, "power_db": -18.5},
    ]
    result = check_flatness(bins, (2400.0, 2403.0))
    assert result["n_bins"] == 3
    assert result["flatness_db"] == pytest.approx(1.5)
    assert result["max_at_mhz"] == pytest.approx(2403.0)
    assert result["min_at_mhz"] == pytest.approx(2401.0)
    assert result["pass"] is True
