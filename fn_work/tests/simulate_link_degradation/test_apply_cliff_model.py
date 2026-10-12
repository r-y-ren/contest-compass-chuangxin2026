"""apply_cliff_model 对抗测试：sigmoid 悬崖单点退化（中点/远端/单调/软度/夹紧/参数域）。"""
from __future__ import annotations

import math

import pytest

from src.simulate_link_degradation.apply_cliff_model import apply_cliff_model

DEFAULTS = {"base_per": 0.01, "threshold_db": 10.0, "softness_db": 2.0}


def _per(jsr: float, **overrides) -> float:
    params = {**DEFAULTS, **overrides}
    return apply_cliff_model({"jsr_db": jsr}, params)["per"]


def test_threshold_midpoint():
    # JSR=threshold → S(0)=0.5 → PER = base + (1−base)/2
    out = apply_cliff_model({"jsr_db": 10.0}, DEFAULTS)
    assert out["per"] == pytest.approx(0.01 + 0.99 * 0.5)


def test_none_params_use_defaults():
    out = apply_cliff_model({"jsr_db": 10.0}, None)
    assert out["per"] == pytest.approx(0.505)
    out_partial = apply_cliff_model({"jsr_db": 10.0}, {"softness_db": 2.0})  # 仅给部分键
    assert out_partial["per"] == pytest.approx(0.505)


def test_far_below_approaches_base():
    per = _per(10.0 - 30.0)  # JSR=−20，悬崖左远端
    assert per == pytest.approx(0.01, abs=1e-4)
    assert per >= 0.01  # sigmoid 非负，PER 不低于基线


def test_far_above_approaches_one_minus_epsilon():
    per = _per(10.0 + 30.0)  # JSR=+40，悬崖右远端
    assert 0.999 < per < 1.0  # ≈1−ε 且严格小于 1
    assert per == pytest.approx(1.0 - 0.99 * math.exp(-15.0), rel=1e-6)


def test_monotonic_nondecreasing():
    pers = [_per(jsr) for jsr in range(-50, 51, 10)]
    assert all(b >= a for a, b in zip(pers, pers[1:]))  # 多点非降
    assert pers[-1] > pers[0]  # 整体确有上升


def test_softness_controls_steepness():
    steep = _per(11.0, softness_db=0.1) - _per(9.0, softness_db=0.1)
    gentle = _per(11.0, softness_db=20.0) - _per(9.0, softness_db=20.0)
    assert steep > 0.9  # 小 softness：悬崖陡（±1dB 内近乎全摆幅）
    assert gentle < 0.1  # 大 softness：平缓
    assert steep > gentle


def test_zero_base_far_below_is_zero():
    per = _per(-20.0, base_per=0.0)
    assert 0.0 <= per < 1e-5


def test_out_of_domain_clamped():
    out_hi = apply_cliff_model({"jsr_db": 150.0}, DEFAULTS)
    assert out_hi["clamped"] is True
    assert out_hi["jsr_db"] == 100.0  # 输出记录夹紧后有效值
    assert out_hi["per"] == _per(100.0)

    out_lo = apply_cliff_model({"jsr_db": -150.0}, DEFAULTS)
    assert out_lo["clamped"] is True
    assert out_lo["jsr_db"] == -100.0
    assert out_lo["per"] == _per(-100.0)
    assert out_lo["per"] == pytest.approx(0.01, abs=1e-12)  # 夹紧到左边界仍是基线


def test_domain_boundary_not_clamped():
    for jsr in (-100.0, -55.5, 0.0, 37.5, 100.0):
        out = apply_cliff_model({"jsr_db": jsr}, DEFAULTS)
        assert out["clamped"] is False
        assert out["jsr_db"] == jsr


@pytest.mark.parametrize(
    "overrides",
    [
        {"base_per": float("nan")},
        {"threshold_db": float("nan")},
        {"softness_db": float("nan")},
        {"softness_db": 0.0},
        {"softness_db": -2.0},
        {"base_per": 1.5},
        {"base_per": 1.0},
        {"base_per": -0.1},
        {"base_per": float("inf")},
        {"softness_db": "2.0"},
        {"threshold_db": None},
    ],
)
def test_invalid_model_params_rejected(overrides):
    with pytest.raises(ValueError):
        apply_cliff_model({"jsr_db": 10.0}, {**DEFAULTS, **overrides})


def test_missing_or_invalid_jsr_rejected():
    with pytest.raises(ValueError):
        apply_cliff_model({"style": "aggressive"}, DEFAULTS)  # 缺 jsr_db
    with pytest.raises(ValueError):
        apply_cliff_model({"jsr_db": float("nan")}, DEFAULTS)
    with pytest.raises(ValueError):
        apply_cliff_model({"jsr_db": float("inf")}, DEFAULTS)
    with pytest.raises(ValueError):
        apply_cliff_model({"jsr_db": "high"}, DEFAULTS)
    with pytest.raises(ValueError):
        apply_cliff_model(["not", "a", "dict"], DEFAULTS)


def test_per_always_in_unit_range_50_point_sweep():
    softness_choices = [0.05, 0.5, 2.0, 5.0, 20.0]
    checked = 0
    for i in range(50):
        jsr = -160.0 + i * (320.0 / 49.0)  # 覆盖域外两侧（−150…+150 区间扫过）
        out = apply_cliff_model(
            {"jsr_db": jsr},
            {
                "base_per": (i % 10) * 0.11,  # 0 … 0.99
                "threshold_db": -20.0 + (i % 7) * 10.0,
                "softness_db": softness_choices[i % 5],
            },
        )
        assert 0.0 <= out["per"] < 1.0  # 恒成立，含 sigmoid 舍入到 1 的极端点
        assert out["clamped"] == (jsr < -100.0 or jsr > 100.0)
        checked += 1
    assert checked == 50


def test_pure_function_no_mutation_and_style_passthrough():
    state = {"jsr_db": 15.0, "style": "soft"}
    params = {"base_per": 0.02, "threshold_db": 8.0, "softness_db": 1.5}
    state_snapshot, params_snapshot = dict(state), dict(params)

    out1 = apply_cliff_model(state, params)
    out2 = apply_cliff_model(state, params)

    assert out1 == out2  # 纯函数：同输入同输出
    assert state == state_snapshot and params == params_snapshot  # 不改输入
    assert out1["style"] == "soft"  # style 仅记录透传，不参与模型
