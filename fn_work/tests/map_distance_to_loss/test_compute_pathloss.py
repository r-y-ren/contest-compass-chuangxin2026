"""compute_pathloss 对抗用例：公式(3) 单点对数距离路径损耗（X_σ 抽样可复现、参数域拒绝）。"""
import math
import random

import pytest

from src.map_distance_to_loss.compute_pathloss import compute_pathloss


def _det(d_m, d0_m, l0_db, n):
    return l0_db + 10.0 * n * math.log10(d_m / d0_m)


def test_d_equals_d0_returns_l0_exactly():
    # log10(1)=0 → 阴影关闭时精确返回 L0
    assert compute_pathloss(5.0, 5.0, 60.0, 2.0) == 60.0


def test_d_equals_d0_with_sigma_returns_l0_plus_sampled_x():
    x = random.Random(7).normalvariate(0.0, 5.0)
    assert compute_pathloss(5.0, 5.0, 60.0, 2.0, 5.0, 7) == pytest.approx(60.0 + x)


def test_one_decade_n2_adds_exactly_20db():
    assert compute_pathloss(10.0, 1.0, 60.0, 2.0) == 80.0


def test_two_decades_n3_5_adds_exactly_70db():
    assert compute_pathloss(100.0, 1.0, 40.0, 3.5) == 110.0


def test_int_inputs_accepted():
    assert compute_pathloss(10, 1, 60, 2) == 80.0


def test_x_sigma_none_is_pure_deterministic():
    d, d0, l0, n = 3.0, 1.0, 55.5, 2.3
    first = compute_pathloss(d, d0, l0, n)
    assert first == compute_pathloss(d, d0, l0, n)
    assert first == pytest.approx(_det(d, d0, l0, n))


def test_x_sigma_zero_matches_disabled_seed_irrelevant():
    kwargs = {"d_m": 7.0, "d0_m": 1.0, "l0_db": 48.0, "n": 3.0}
    off = compute_pathloss(**kwargs)
    assert compute_pathloss(**kwargs, x_sigma=0.0) == off
    assert compute_pathloss(**kwargs, x_sigma=0.0, seed=99) == off


def test_sigma_seed_reproducible_pointwise():
    args = (4.0, 1.0, 50.0, 2.0)
    r1 = compute_pathloss(*args, 5.0, 42)
    r2 = compute_pathloss(*args, 5.0, 42)
    assert r1 == r2
    x = random.Random(42).normalvariate(0.0, 5.0)
    assert r1 == pytest.approx(_det(*args) + x)
    assert r1 != pytest.approx(_det(*args))  # 阴影项确实生效且非零


def test_per_call_seed_reset_same_first_draw_across_distances():
    # per-call Random(seed) 重置：同 seed 的抽样与 d 无关（首点一致）
    x = random.Random(123).normalvariate(0.0, 5.0)
    r_a = compute_pathloss(2.0, 1.0, 30.0, 2.0, 5.0, 123)
    r_b = compute_pathloss(20.0, 1.0, 30.0, 2.0, 5.0, 123)
    assert r_a == pytest.approx(_det(2.0, 1.0, 30.0, 2.0) + x)
    assert r_b == pytest.approx(_det(20.0, 1.0, 30.0, 2.0) + x)


def test_sequence_replay_two_passes_identical_and_order_independent():
    dists = [1.0, 1.5, 2.0, 5.0, 10.0]
    seq1 = [compute_pathloss(d, 1.0, 45.0, 2.5, 3.0, 2024) for d in dists]
    seq2 = [compute_pathloss(d, 1.0, 45.0, 2.5, 3.0, 2024) for d in dists]
    assert seq1 == seq2
    seq3 = [compute_pathloss(d, 1.0, 45.0, 2.5, 3.0, 2024) for d in reversed(dists)]
    assert seq1[0] == seq3[-1]  # 单点结果不依赖序列位置/顺序


def test_negative_sigma_rejected():
    with pytest.raises(ValueError):
        compute_pathloss(10.0, 1.0, 60.0, 2.0, -0.1, 1)


@pytest.mark.parametrize(
    "d_m,d0_m",
    [(0.0, 1.0), (-5.0, 1.0), (0.5, 1.0), (0.999999, 1.0), (1.0, 0.0), (1.0, -1.0)],
)
def test_distance_domain_violations_rejected(d_m, d0_m):
    with pytest.raises(ValueError):
        compute_pathloss(d_m, d0_m, 60.0, 2.0)


@pytest.mark.parametrize("n", [0.0, -2.0])
def test_nonpositive_n_rejected(n):
    with pytest.raises(ValueError):
        compute_pathloss(10.0, 1.0, 60.0, n)


@pytest.mark.parametrize(
    "bad", [float("nan"), float("inf"), -float("inf"), True, False, "10", 10**400]
)
@pytest.mark.parametrize("arg", ["d_m", "d0_m", "l0_db", "n"])
def test_invalid_numeric_arguments_rejected(arg, bad):
    kwargs = {"d_m": 10.0, "d0_m": 1.0, "l0_db": 60.0, "n": 2.0}
    kwargs[arg] = bad
    with pytest.raises(ValueError):
        compute_pathloss(**kwargs)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "5"])
def test_invalid_x_sigma_rejected(bad):
    with pytest.raises(ValueError):
        compute_pathloss(10.0, 1.0, 60.0, 2.0, bad, 1)


@pytest.mark.parametrize("bad_seed", [True, 1.5, "7", [1]])
def test_invalid_seed_rejected(bad_seed):
    with pytest.raises(ValueError):
        compute_pathloss(10.0, 1.0, 60.0, 2.0, 5.0, bad_seed)


def test_invalid_seed_rejected_even_without_shadowing():
    # bool 拒绝口径对所有参数无条件生效（含阴影关闭时）
    with pytest.raises(ValueError):
        compute_pathloss(10.0, 1.0, 60.0, 2.0, None, True)


def test_seed_none_with_sigma_returns_finite_float():
    result = compute_pathloss(10.0, 1.0, 60.0, 2.0, 5.0, None)
    assert isinstance(result, float)
    assert math.isfinite(result)


def test_returns_finite_float_for_large_representable_d():
    result = compute_pathloss(1e30, 1.0, 60.0, 2.0)
    assert isinstance(result, float)
    assert math.isfinite(result)
    assert result == pytest.approx(60.0 + 10 * 2 * 30.0)


def test_oversized_d_int_rejected_no_inf():
    # 10**400 转 float 即溢出——按"极大 d 不产生 inf"口径拒绝
    with pytest.raises(ValueError):
        compute_pathloss(10**400, 1.0, 60.0, 2.0)


def test_overflow_ratio_rejected_as_non_finite():
    with pytest.raises(ValueError):
        compute_pathloss(1e308, 1e-308, 60.0, 2.0)
