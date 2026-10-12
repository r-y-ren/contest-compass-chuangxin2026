"""map_distance_to_loss 对抗用例：距离序列→损耗→档位计划（seed 序列口径/不可达不抛/透传）。"""
import math
import random

import pytest

from src.map_distance_to_loss.map_distance_to_loss import map_distance_to_loss


def _model(**overrides):
    base = {"d0_m": 1.0, "l0_db": 10.0, "n": 2.0}
    base.update(overrides)
    return base


def _det(d_m, d0_m, l0_db, n):
    return l0_db + 10.0 * n * math.log10(d_m / d0_m)


# ---- 无阴影：10x/100x 公式精确 + 组合正确（对应衰减档） ----


def test_pathloss_map_three_distances_no_shadow_exact_loss_and_combos():
    result = map_distance_to_loss([1.0, 10.0, 100.0], _model())
    # log10(1/10/100 倍 d0)=0/1/2 精确 → 损耗恰为 10/30/50 dB
    assert [p["loss_db"] for p in result["points"]] == [10.0, 30.0, 50.0]
    assert [p["d_m"] for p in result["points"]] == [1.0, 10.0, 100.0]  # 输入序保留
    assert all(p["x_sigma_db"] == 0.0 for p in result["points"])  # 无阴影→抽样值恰 0
    assert all(p["reachable"] for p in result["points"])
    assert result["unreachable_count"] == 0
    c10, c30, c50 = (p["combo"] for p in result["points"])
    assert (c10["coarse"], c10["coarse_db"], c10["fine_step_db"], c10["achieved_db"]) == (
        "bypass", 0.0, 10.0, 10.0,
    )
    assert (c30["coarse"], c30["coarse_db"], c30["fine_step_db"], c30["achieved_db"]) == (
        "in", 30.0, 0.0, 30.0,
    )
    assert (c50["coarse"], c50["coarse_db"], c50["fine_step_db"], c50["achieved_db"]) == (
        "in", 30.0, 20.0, 50.0,  # 默认域顶 50 恰可达
    )


def test_pathloss_map_result_shape_top_level_and_point_keys():
    result = map_distance_to_loss([2.0], _model(x_sigma=1.0, base_seed=3))
    assert set(result.keys()) == {"points", "model", "unreachable_count"}
    assert set(result["points"][0].keys()) == {"d_m", "loss_db", "x_sigma_db", "combo", "reachable"}


# ---- 阴影 seed 序列口径：可复现 / 逐点递增 ----


def test_pathloss_map_shadow_fixed_base_seed_two_passes_identical():
    params = _model(l0_db=30.0, x_sigma=4.0, base_seed=2024)
    distances = [2.0, 5.0, 7.5, 12.0]
    first = map_distance_to_loss(distances, params)
    second = map_distance_to_loss(distances, params)
    assert first == second  # 全序列逐点一致（含 combo 与 hint 字符串）


def test_pathloss_map_different_base_seed_changes_sequence():
    run_2024 = map_distance_to_loss([2.0, 5.0], _model(x_sigma=4.0, base_seed=2024))
    run_2025 = map_distance_to_loss([2.0, 5.0], _model(x_sigma=4.0, base_seed=2025))
    assert [p["loss_db"] for p in run_2024["points"]] != [p["loss_db"] for p in run_2025["points"]]


def test_pathloss_map_base_seed_increment_per_point():
    # seed 序列口径：逐点 seed=base_seed+i → i=0,1,2 抽样不同且可精确重放
    sigma, base_seed, d = 6.0, 100, 3.0
    result = map_distance_to_loss([d, d, d], _model(l0_db=20.0, x_sigma=sigma, base_seed=base_seed))
    draws = [random.Random(base_seed + i).normalvariate(0.0, sigma) for i in range(3)]
    deterministic = _det(d, 1.0, 20.0, 2.0)
    for i, point in enumerate(result["points"]):
        assert point["loss_db"] == pytest.approx(deterministic + draws[i])
        assert point["x_sigma_db"] == pytest.approx(draws[i])
    assert len({round(x, 9) for x in (p["x_sigma_db"] for p in result["points"])}) == 3  # 各点抽样不同
    # 与逐点显式 seed 的 compute_pathloss 完全等价
    replay = [
        math.isclose(
            point["loss_db"],
            deterministic + random.Random(base_seed + i).normalvariate(0.0, sigma),
            rel_tol=1e-12,
        )
        for i, point in enumerate(result["points"])
    ]
    assert all(replay)


def test_pathloss_map_base_seed_none_entropic_not_reproducible():
    params = _model(x_sigma=5.0)  # 无 base_seed → 全 None（熵播种）
    first = map_distance_to_loss([2.0, 3.0, 4.0], params)
    second = map_distance_to_loss([2.0, 3.0, 4.0], params)
    assert all(math.isfinite(p["loss_db"]) for p in first["points"])
    assert [p["loss_db"] for p in first["points"]] != [p["loss_db"] for p in second["points"]]


def test_pathloss_map_shadow_may_break_monotonicity_reported_honestly():
    # 单调演变断言不强制：X_σ 可打破损耗随距离单调——搜索一个打破单调的 base_seed 并如实断言
    params_base = {"d0_m": 1.0, "l0_db": 30.0, "n": 1.0, "x_sigma": 10.0}
    distances = [1.0, 1.5]
    breaking_seed = None
    for seed in range(500):
        x0 = random.Random(seed).normalvariate(0.0, 10.0)
        x1 = random.Random(seed + 1).normalvariate(0.0, 10.0)
        if _det(1.0, 1.0, 30.0, 1.0) + x0 > _det(1.5, 1.0, 30.0, 1.0) + x1:
            breaking_seed = seed
            break
    assert breaking_seed is not None
    result = map_distance_to_loss(distances, dict(params_base, base_seed=breaking_seed))
    losses = [p["loss_db"] for p in result["points"]]
    assert losses[0] > losses[1]  # 距离更远损耗更低（X_σ 打破单调，未静默整形）
    assert [p["d_m"] for p in result["points"]] == distances  # 不排序、保持输入序


# ---- 不可达：reachable=False + 提示 + 计数（不抛，整计划继续） ----


def test_pathloss_map_unreachable_point_marked_false_with_hint_and_continues():
    result = map_distance_to_loss([1.0, 100.0], _model(l0_db=40.0))  # 损耗 40 / 80
    assert len(result["points"]) == 2  # 不可达不抛出，整计划继续
    ok, bad = result["points"]
    assert ok["reachable"] is True and ok["combo"] is not None  # 40 → in+10 残差 0
    assert (ok["combo"]["coarse"], ok["combo"]["fine_step_db"]) == ("in", 10.0)
    assert bad["reachable"] is False
    assert bad["combo"] is None
    assert isinstance(bad["hint"], str) and "50.000" in bad["hint"]  # 默认域顶 30+20
    assert result["unreachable_count"] == 1
    assert "hint" not in ok  # 可达点不附提示


def test_pathloss_map_unreachable_count_consistent_with_points():
    # 损耗 45/49.5/54/58.5/63 → 后三点超默认域顶 50
    result = map_distance_to_loss([1.0, 2.0, 4.0, 8.0, 16.0], _model(l0_db=45.0, n=1.5))
    flags = [p["reachable"] for p in result["points"]]
    assert flags == [True, True, False, False, False]
    assert result["unreachable_count"] == sum(1 for f in flags if not f) == 3


# ---- 入参拒绝：distances 空 / 含非法；base_seed 非法 ----


def test_pathloss_map_empty_distances_rejected():
    with pytest.raises(ValueError):
        map_distance_to_loss([], _model())


@pytest.mark.parametrize(
    "bad",
    [0.0, -2.5, float("nan"), float("inf"), -float("inf"), True, False, "5", None, 10**400],
)
def test_pathloss_map_invalid_distance_elements_rejected(bad):
    with pytest.raises(ValueError):
        map_distance_to_loss([1.0, bad, 10.0], _model())


@pytest.mark.parametrize("bad_distances", ["1.0", 5, None, {"d": 1.0}])
def test_pathloss_map_non_sequence_distances_rejected(bad_distances):
    with pytest.raises(ValueError):
        map_distance_to_loss(bad_distances, _model())


@pytest.mark.parametrize("bad_seed", [True, 1.5, "7", [1]])
def test_pathloss_map_invalid_base_seed_rejected(bad_seed):
    with pytest.raises(ValueError):
        map_distance_to_loss([1.0, 2.0], _model(x_sigma=2.0, base_seed=bad_seed))


# ---- compute_pathloss 域错透传 ----


def test_pathloss_map_below_d0_point_passthrough_valueerror():
    with pytest.raises(ValueError, match="d0_m"):
        map_distance_to_loss([10.0, 5.0], _model(d0_m=10.0))  # d=5 < d0=10


@pytest.mark.parametrize(
    "overrides",
    [{"n": 0.0}, {"n": -1.0}, {"d0_m": 0.0}, {"d0_m": -5.0}, {"l0_db": float("nan")}, {"n": True}],
)
def test_pathloss_map_invalid_model_params_passthrough(overrides):
    with pytest.raises(ValueError):
        map_distance_to_loss([2.0], _model(**overrides))


def test_pathloss_map_negative_sigma_rejected_via_passthrough():
    with pytest.raises(ValueError):
        map_distance_to_loss([2.0], _model(x_sigma=-0.5, base_seed=1))


# ---- domain / cal_table 经 model_params 透传组合 ----


def test_pathloss_map_domain_passthrough_shapes_combo_and_ceiling():
    domain = {"coarse_db": 20.0, "fine_steps_db": [0.0, 5.0, 10.0], "fine_granularity_db": 5.0}
    # 损耗 10/30：自定义域 bypass+10；in(20)+10=30 残差 0（默认域下 30 会选 in(30)+0）
    result = map_distance_to_loss([1.0, 10.0], _model(domain=domain))
    c10, c30 = (p["combo"] for p in result["points"])
    assert (c10["coarse"], c10["coarse_db"], c10["fine_step_db"]) == ("bypass", 0.0, 10.0)
    assert (c30["coarse"], c30["coarse_db"], c30["fine_step_db"], c30["achieved_db"]) == (
        "in", 20.0, 10.0, 30.0,
    )
    # 损耗 45：自定义域顶 20+10=30 → 不可达（默认域 50 下可达 in+15）
    custom = map_distance_to_loss([10.0], _model(l0_db=25.0, domain=domain))["points"][0]
    assert custom["reachable"] is False and custom["combo"] is None
    assert "30.000" in custom["hint"]  # 提示按自定义域顶 30 给出
    default = map_distance_to_loss([10.0], _model(l0_db=25.0))["points"][0]
    assert default["reachable"] is True
    assert (default["combo"]["coarse"], default["combo"]["fine_step_db"]) == ("in", 15.0)


def test_pathloss_map_cal_table_passthrough_marks_calibrated():
    # 损耗 45：档 15 标定实际 15.4 → achieved 45.4、残差 -0.4、fine_from=calibrated
    result = map_distance_to_loss([10.0], _model(l0_db=25.0, cal_table={15.0: 15.4}))
    combo = result["points"][0]["combo"]
    assert combo["fine_from"] == "calibrated"
    assert combo["fine_actual_db"] == pytest.approx(15.4)
    assert combo["achieved_db"] == pytest.approx(45.4)
    assert combo["residual_db"] == pytest.approx(-0.4)


# ---- model 元数据回显 ----


def test_pathloss_map_model_metadata_echoed():
    params = {"d0_m": 1.0, "l0_db": 33.5, "n": 2.5, "x_sigma": 3.0, "base_seed": 9}
    result = map_distance_to_loss([1.0], params)
    assert result["model"] == {
        "d0_m": 1.0,
        "l0_db": 33.5,
        "n": 2.5,
        "x_sigma": 3.0,
        "base_seed": 9,
    }  # 恰五键回显（domain/cal_table 不进 model）
    x = random.Random(9).normalvariate(0.0, 3.0)
    assert result["points"][0]["loss_db"] == pytest.approx(33.5 + x)


def test_pathloss_map_model_defaults_echoed_as_none():
    result = map_distance_to_loss([1.0], _model())
    assert result["model"] == {"d0_m": 1.0, "l0_db": 10.0, "n": 2.0, "x_sigma": None, "base_seed": None}
