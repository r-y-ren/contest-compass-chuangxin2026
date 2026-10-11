"""plan_attenuator_combo 对抗单测（B8 叶子）：择档规则 / 标定回退 / 残差 / 域顶 / 校验。"""
import pytest

from src.set_channel_attenuation.plan_attenuator_combo import plan_attenuator_combo


def test_target_35_coarse_in_plus_fine_5():
    assert plan_attenuator_combo(35.0) == {
        "coarse": "in",
        "coarse_db": 30.0,
        "fine_step_db": 5.0,
        "fine_actual_db": 5.0,
        "achieved_db": 35.0,
        "residual_db": 0.0,
        "fine_from": "nominal",
    }


def test_target_10_bypass_plus_fine_10():
    result = plan_attenuator_combo(10.0)
    assert result["coarse"] == "bypass"
    assert result["coarse_db"] == 0.0
    assert result["fine_step_db"] == 10.0
    assert result["achieved_db"] == 10.0
    assert result["residual_db"] == 0.0


def test_target_exactly_30_uses_in_fine_zero_not_bypass_saturation():
    # in+0 残差 0 vs bypass 顶格 20 残差 +10 → 残差最小者优先（文档化规则）
    result = plan_attenuator_combo(30.0)
    assert result["coarse"] == "in"
    assert result["fine_step_db"] == 0.0
    assert result["achieved_db"] == 30.0
    assert result["residual_db"] == 0.0


def test_domain_full_at_45_and_46_beyond_returns_none():
    domain = {
        "coarse_db": 30.0,
        "fine_steps_db": [float(i) for i in range(16)],  # 0..15 → 域顶 45
        "fine_granularity_db": 1.0,
    }
    full = plan_attenuator_combo(45.0, domain)
    assert full["coarse"] == "in"
    assert full["fine_step_db"] == 15.0
    assert full["achieved_db"] == 45.0
    assert full["residual_db"] == 0.0
    assert plan_attenuator_combo(46.0, domain) is None


def test_default_domain_upper_bound_is_50():
    edge = plan_attenuator_combo(50.0)
    assert edge["coarse"] == "in"
    assert edge["fine_step_db"] == 20.0
    assert edge["achieved_db"] == 50.0
    assert edge["residual_db"] == 0.0
    assert plan_attenuator_combo(50.000001) is None
    assert plan_attenuator_combo(1e9) is None
    assert plan_attenuator_combo(float("inf")) is None


def test_cal_table_selects_step_by_actual_value():
    cal = {5.0: 5.3, 4.0: 4.2}
    result = plan_attenuator_combo(35.0, cal_table=cal)
    # 剩余 5：档 5 实际 5.3（偏差 0.3）胜档 4 实际 4.2（偏差 0.8）→ 按实际值选档
    assert result["fine_step_db"] == 5.0
    assert result["fine_actual_db"] == pytest.approx(5.3)
    assert result["fine_from"] == "calibrated"
    assert result["achieved_db"] == pytest.approx(35.3)
    assert result["residual_db"] == pytest.approx(-0.3)


def test_cal_table_missing_key_falls_back_to_nominal_with_flag():
    result = plan_attenuator_combo(35.0, cal_table={4.0: 4.2})  # 档 5 缺键
    assert result["fine_step_db"] == 5.0
    assert result["fine_actual_db"] == 5.0
    assert result["fine_from"] == "nominal"
    assert result["achieved_db"] == 35.0
    assert result["residual_db"] == 0.0


def test_nonmonotonic_cal_not_checked_and_bounds_max_actual():
    cal = {18.0: 19.0, 20.0: 18.0}  # 单调性不检查（B2 单调工具属另函数）
    result = plan_attenuator_combo(48.5, cal_table=cal)
    # 档 18（实际 19）与档 20（实际 18）残差同为 0.5 → 列表序靠前（18）胜
    assert result["coarse"] == "in"
    assert result["fine_step_db"] == 18.0
    assert result["fine_actual_db"] == 19.0
    assert result["achieved_db"] == 49.0
    assert result["residual_db"] == -0.5
    # 域顶按实际最大细档 19.0（档 19 标称）=49，49.5 不可达（尽管标称可达 50）
    assert plan_attenuator_combo(49.5, cal_table=cal) is None


def test_residual_min_beats_coarse_heuristic_at_16_5():
    half_db = {
        "coarse_db": 30.0,
        "fine_steps_db": [i * 0.5 for i in range(41)],  # 0..20 步进 0.5
        "fine_granularity_db": 0.5,
    }
    result = plan_attenuator_combo(16.5, domain=half_db)
    # bypass+16.5 残差 0 胜 in+0 残差 -13.5：经验法则"≥15dB 用粗档"被残差最优先修正
    assert result["coarse"] == "bypass"
    assert result["coarse_db"] == 0.0
    assert result["fine_step_db"] == 16.5
    assert result["achieved_db"] == 16.5
    assert result["residual_db"] == 0.0
    # 默认 1dB 步进域：16/17 平手 → 列表序靠前（16）胜，仍 bypass
    default_result = plan_attenuator_combo(16.5)
    assert default_result["coarse"] == "bypass"
    assert default_result["fine_step_db"] == 16.0
    assert default_result["residual_db"] == pytest.approx(0.5)


def test_tie_between_coarse_states_prefers_in():
    # 25：bypass+20 残差 +5 与 in+0 残差 -5 平手 → 平手选粗档接入（文档化规则）
    result = plan_attenuator_combo(25.0)
    assert result["coarse"] == "in"
    assert result["fine_step_db"] == 0.0
    assert result["achieved_db"] == 30.0
    assert result["residual_db"] == -5.0


@pytest.mark.parametrize("bad", [float("nan"), -0.1, -30.0, True, False, "35", None])
def test_invalid_target_raises_value_error(bad):
    with pytest.raises(ValueError):
        plan_attenuator_combo(bad)


def test_domain_missing_coarse_db_uses_default():
    result = plan_attenuator_combo(35.0, domain={"fine_steps_db": [float(i) for i in range(21)]})
    assert result["coarse"] == "in"
    assert result["coarse_db"] == 30.0
    assert result["fine_step_db"] == 5.0
    assert plan_attenuator_combo(35.0, domain={})["fine_step_db"] == 5.0
    assert plan_attenuator_combo(35.0)["fine_step_db"] == 5.0  # domain 缺省→全默认


def test_empty_fine_steps_coarse_only_two_state():
    domain = {"coarse_db": 30.0, "fine_steps_db": []}
    low = plan_attenuator_combo(10.0, domain)
    assert low["coarse"] == "bypass"
    assert low["coarse_db"] == 0.0
    assert low["fine_step_db"] == 0.0
    assert low["fine_actual_db"] == 0.0
    assert low["fine_from"] == "nominal"
    assert low["achieved_db"] == 0.0
    assert low["residual_db"] == 10.0
    high = plan_attenuator_combo(20.0, domain)  # |−10| < |+20| → 接入
    assert high["coarse"] == "in"
    assert high["achieved_db"] == 30.0
    assert high["residual_db"] == -10.0
    assert plan_attenuator_combo(30.0, domain)["residual_db"] == 0.0
    assert plan_attenuator_combo(30.5, domain) is None  # 域顶 30


@pytest.mark.parametrize(
    "domain",
    [
        "nope",
        [1.0, 2.0],
        {"coarse_db": "x"},
        {"coarse_db": 0.0},
        {"coarse_db": True},
        {"coarse_db": float("nan")},
        {"coarse_db": None},
        {"fine_steps_db": "0..20"},
        {"fine_steps_db": 5.0},
        {"fine_steps_db": [1.0, "x"]},
        {"fine_steps_db": [1.0, float("nan")]},
        {"fine_steps_db": [-1.0]},
        {"fine_steps_db": [True]},
        {"fine_granularity_db": 0.0},
        {"fine_granularity_db": "1.0"},
    ],
)
def test_domain_shape_errors_raise_value_error(domain):
    with pytest.raises(ValueError):
        plan_attenuator_combo(35.0, domain=domain)


@pytest.mark.parametrize("cal", ["nope", [5.0], {5.0: "x"}, {5.0: float("nan")}, {5.0: True}])
def test_cal_table_shape_errors_raise_value_error(cal):
    with pytest.raises(ValueError):
        plan_attenuator_combo(35.0, cal_table=cal)
