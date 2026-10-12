"""plan_frequency_sweep 对抗测试：线性/对数点表、CISPR 频段便捷、域校验拒绝。"""
from __future__ import annotations

import math

import pytest

from src.run_emc_sweep.plan_frequency_sweep import plan_frequency_sweep

NAN = float('nan')


# ---------------------------------------------------------------------------
# 线性刻度
# ---------------------------------------------------------------------------

def test_linear_9k_to_90k_step_9k_yields_exactly_10_uniform_points():
    result = plan_frequency_sweep(9e3, 90e3, step_hz=9e3)
    points = result['points_hz']
    assert points == [9e3, 18e3, 27e3, 36e3, 45e3, 54e3, 63e3, 72e3, 81e3, 90e3]
    assert result['n_points'] == 10 == len(points)
    assert result['scale'] == 'linear'
    # 逐点均匀：相邻差恒为 9 kHz
    diffs = [b - a for a, b in zip(points, points[1:])]
    assert all(math.isclose(d, 9e3, rel_tol=0, abs_tol=1e-9) for d in diffs)
    assert result['warnings'] == []


def test_linear_step_ge_span_degrades_to_single_point_with_warning():
    # step == 跨度
    result = plan_frequency_sweep(1e6, 2e6, step_hz=1e6)
    assert result['points_hz'] == [1e6]
    assert result['n_points'] == 1
    assert 'single_point' in result['warnings']
    # step > 跨度
    result2 = plan_frequency_sweep(1e6, 1.5e6, step_hz=5e6)
    assert result2['points_hz'] == [1e6]
    assert result2['n_points'] == 1
    assert 'single_point' in result2['warnings']


def test_linear_non_divisible_span_clamps_last_point_to_stop():
    result = plan_frequency_sweep(10e3, 20e3, step_hz=3e3)
    points = result['points_hz']
    # n = ceil(10/3)+1 = 5：10,13,16,19 kHz 后末点对齐 20 kHz
    assert result['n_points'] == 5 == len(points)
    assert points[0] == pytest.approx(10e3)
    assert points[-1] == pytest.approx(20e3)
    assert all(p < 20e3 for p in points[:-1])


def test_linear_point_count_matches_formula_recomputed_independently():
    cases = [
        (9e3, 90e3, 9e3),
        (10e3, 20e3, 3e3),
        (1e6, 10e6, 1e6),          # 缺省步长量级
        (150e3, 30e6, 141e3),
    ]
    for start, stop, step in cases:
        result = plan_frequency_sweep(start, stop, step_hz=step)
        expected_n = math.ceil((stop - start) / step) + 1
        assert result['n_points'] == expected_n, (start, stop, step)
        assert len(result['points_hz']) == expected_n == result['n_points']
        assert result['points_hz'][0] == pytest.approx(start)
        assert result['points_hz'][-1] == pytest.approx(stop)


# ---------------------------------------------------------------------------
# 对数刻度
# ---------------------------------------------------------------------------

def test_log_1m_to_4m_per_step_ratio_2_yields_three_points():
    # r=1 → 每步频率比 1+r=2：1M → 2M → 4M
    result = plan_frequency_sweep(1e6, 4e6, step_hz=1.0, scale='log')
    points = result['points_hz']
    assert result['n_points'] == 3 == len(points)
    assert points[0] == pytest.approx(1e6)
    assert points[1] == pytest.approx(2e6)
    assert points[2] == pytest.approx(4e6)
    assert result['scale'] == 'log'


def test_log_step_semantics_is_relative_ratio_not_hertz():
    # step_hz=0.02 → 每步频率比 1.02（+2%），非 0.02 Hz 绝对步长
    result = plan_frequency_sweep(1e6, 2e6, step_hz=0.02, scale='log')
    points = result['points_hz']
    expected_n = math.ceil(math.log(2e6 / 1e6) / math.log(1.02)) + 1
    assert result['n_points'] == expected_n == len(points)
    # 除末点（对齐 stop）外，相邻点比值恒为 1.02
    for prev, cur in zip(points[:-2], points[1:-1]):
        assert cur / prev == pytest.approx(1.02, rel=1e-12)
    assert points[-1] == pytest.approx(2e6)
    assert all(p < 2e6 for p in points[:-1])
    # 若 step_hz 被误读为 Hz，点数会截然不同——断言语义确为相对比
    misread = plan_frequency_sweep(1e6, 2e6, step_hz=0.5, scale='log')
    assert misread['n_points'] == math.ceil(math.log(2.0) / math.log(1.5)) + 1


def test_log_point_count_matches_formula_recomputed_independently():
    cases = [
        (1e6, 4e6, 1.0),           # 1,2,4 MHz
        (1e6, 2e6, 0.02),
        (150e3, 30e6, 1.0),
        (9e3, 150e3, 2.0),
    ]
    for start, stop, r in cases:
        result = plan_frequency_sweep(start, stop, step_hz=r, scale='log')
        expected_n = math.ceil(math.log(stop / start) / math.log(1 + r)) + 1
        assert result['n_points'] == expected_n, (start, stop, r)
        assert len(result['points_hz']) == expected_n == result['n_points']
        assert result['points_hz'][0] == pytest.approx(start)
        assert result['points_hz'][-1] == pytest.approx(stop)


# ---------------------------------------------------------------------------
# CISPR 频段便捷参数
# ---------------------------------------------------------------------------

def test_cispr_a_band_uses_9k_to_150k():
    result = plan_frequency_sweep(0, 0, step_hz=9e3, band='cispr_a')
    points = result['points_hz']
    assert points[0] == 9e3
    assert points[-1] == 150e3
    assert result['n_points'] == math.ceil((150e3 - 9e3) / 9e3) + 1 == 17
    assert result['band'] == 'cispr_a'


def test_cispr_b_band_uses_150k_to_30m():
    result = plan_frequency_sweep(0, 0, step_hz=1.0, scale='log', band='cispr_b')
    points = result['points_hz']
    assert points[0] == 150e3
    assert points[-1] == 30e6
    assert result['n_points'] == math.ceil(math.log(200) / math.log(2)) + 1 == 9
    assert result['band'] == 'cispr_b'


def test_band_overrides_user_start_stop():
    # 用户显式给的合法 start/stop 在给 band 时被忽略
    ignored = plan_frequency_sweep(1e9, 2e9, step_hz=9e3, band='cispr_a')
    direct = plan_frequency_sweep(9e3, 150e3, step_hz=9e3)
    assert ignored['points_hz'] == direct['points_hz']
    assert ignored['points_hz'][0] == 9e3
    assert ignored['points_hz'][-1] == 150e3
    assert all(p <= 150e3 for p in ignored['points_hz'])  # 1e9/2e9 未混入


# ---------------------------------------------------------------------------
# 域校验拒绝
# ---------------------------------------------------------------------------

def test_start_equal_or_above_stop_rejected():
    with pytest.raises(ValueError):
        plan_frequency_sweep(90e3, 90e3, step_hz=9e3)
    with pytest.raises(ValueError):
        plan_frequency_sweep(90e3, 9e3, step_hz=9e3)   # 起止颠倒
    with pytest.raises(ValueError):
        plan_frequency_sweep(1e6, 1e6, step_hz=0.5, scale='log')  # 对数同样拒


@pytest.mark.parametrize('bad_start', [0.0, -1e3, -1e-9])
def test_start_le_zero_rejected_on_both_scales(bad_start):
    with pytest.raises(ValueError):
        plan_frequency_sweep(bad_start, 90e3, step_hz=9e3)
    with pytest.raises(ValueError):
        # 对数刻度 start>0 同样由域校验保证
        plan_frequency_sweep(bad_start, 90e3, step_hz=0.02, scale='log')


def test_invalid_scale_rejected_with_legal_values_listed():
    with pytest.raises(ValueError, match=r"linear.*log"):
        plan_frequency_sweep(9e3, 90e3, step_hz=9e3, scale='sqrt')


def test_invalid_band_rejected_with_both_legal_values_listed():
    with pytest.raises(ValueError, match=r"cispr_a.*cispr_b"):
        plan_frequency_sweep(9e3, 90e3, step_hz=9e3, band='cispr_c')


def _call_with(arg_name, value):
    """以完整 kwargs 调用（避免与位置参数撞名的 TypeError 干扰断言）。"""
    kwargs = {'start_hz': 9e3, 'stop_hz': 90e3, 'step_hz': 9e3, arg_name: value}
    return plan_frequency_sweep(**kwargs)


@pytest.mark.parametrize('arg_name,bad_value', [
    ('start_hz', NAN),
    ('stop_hz', NAN),
    ('step_hz', NAN),
    ('start_hz', True),       # bool 是 int 子类，必须显式拒绝
    ('stop_hz', False),
    ('step_hz', True),
    ('start_hz', float('inf')),
])
def test_nan_bool_and_nonfinite_rejected(arg_name, bad_value):
    with pytest.raises(ValueError):
        _call_with(arg_name, bad_value)


@pytest.mark.parametrize('arg_name,bad_value', [
    ('start_hz', '9000'),
    ('stop_hz', None),
    ('step_hz', [9e3]),
])
def test_non_numeric_types_rejected(arg_name, bad_value):
    with pytest.raises(ValueError):
        _call_with(arg_name, bad_value)


def test_step_le_zero_rejected_on_both_scales():
    with pytest.raises(ValueError):
        plan_frequency_sweep(9e3, 90e3, step_hz=0)
    with pytest.raises(ValueError):
        plan_frequency_sweep(9e3, 90e3, step_hz=-9e3)
    with pytest.raises(ValueError):
        # 对数刻度 r<=0 → 每步比 1+r<=1 无意义
        plan_frequency_sweep(1e6, 4e6, step_hz=0.0, scale='log')


# ---------------------------------------------------------------------------
# B16高#1：点数上限 max_points（公式点数超限秒拒不建表）
# ---------------------------------------------------------------------------

def test_linear_formula_points_over_limit_rejected_with_count_and_hint():
    # 1kHz–21kHz 步 2Hz → 公式点数恰 10001 > 10000：消息附点数、上限与提示
    with pytest.raises(ValueError, match=r"计划点数 10001 超出上限 max_points=10000") as excinfo:
        plan_frequency_sweep(1e3, 21e3, step_hz=2.0)
    message = str(excinfo.value)
    assert "step_hz" in message          # 提示：增大步长
    assert "max_points" in message       # 提示：或提高上限


def test_log_formula_points_over_limit_rejected():
    # cispr_a 对数步 r=1e-4 → 公式点数 >10000：同样秒拒
    expected_n = math.ceil(math.log(150e3 / 9e3) / math.log(1.0 + 1e-4)) + 1
    assert expected_n > 10000            # 前置自检：本用例确为超限场景
    with pytest.raises(ValueError, match=f"计划点数 {expected_n} 超出上限"):
        plan_frequency_sweep(9e3, 150e3, step_hz=1e-4, scale='log')


def test_tiny_step_1e9_rejected_instantly_without_building_table():
    # 1e-9 级步长：公式点数 ~1e15——先拒后建表（若先建表本用例将拖垮内存/时耗）
    with pytest.raises(ValueError, match=r"超出上限 max_points=10000"):
        plan_frequency_sweep(1e6, 2e6, step_hz=1e-9)


def test_exactly_10000_points_passes_on_both_scales():
    # 线性：跨度 9999Hz 步 1Hz → 恰 10000 点（边界含——==上限通过）
    linear = plan_frequency_sweep(1e3, 10999.0, step_hz=1.0)
    assert linear['n_points'] == 10000 == len(linear['points_hz'])
    assert linear['points_hz'][0] == pytest.approx(1e3)
    assert linear['points_hz'][-1] == pytest.approx(10999.0)
    # 对数：步比构造使公式比值 = 9998.5 → ceil+1 恰 10000 点
    r = 2.0 ** (1.0 / 9998.5) - 1.0
    log_result = plan_frequency_sweep(1e6, 2e6, step_hz=r, scale='log')
    assert log_result['n_points'] == 10000 == len(log_result['points_hz'])
    assert log_result['points_hz'][0] == pytest.approx(1e6)
    assert log_result['points_hz'][-1] == pytest.approx(2e6)


def test_max_points_custom_limit_boundary():
    # 自定义上限：n=10 ≤ max_points=10 恰过；同计划对 max_points=9 超限拒
    plan_kwargs = {'start_hz': 9e3, 'stop_hz': 90e3, 'step_hz': 9e3}
    ok = plan_frequency_sweep(**plan_kwargs, max_points=10)
    assert ok['n_points'] == 10
    with pytest.raises(ValueError, match=r"超出上限 max_points=9"):
        plan_frequency_sweep(**plan_kwargs, max_points=9)


@pytest.mark.parametrize('bad_max_points', [True, 0, -1, 10.5, '100', None])
def test_max_points_invalid_values_rejected(bad_max_points):
    with pytest.raises(ValueError, match="max_points"):
        plan_frequency_sweep(9e3, 90e3, step_hz=9e3, max_points=bad_max_points)


# ---------------------------------------------------------------------------
# B16低#4：band 给定时短路 start/stop 校验（频段值即生效——None start 可达）
# ---------------------------------------------------------------------------

def test_band_short_circuits_start_stop_validation_none_reachable():
    result = plan_frequency_sweep(None, None, step_hz=9e3, band='cispr_a')
    assert result['points_hz'][0] == 9e3
    assert result['points_hz'][-1] == 150e3
    assert result['n_points'] == 17
    assert result['band'] == 'cispr_a'
    # band 值即生效：用户 start/stop 为 NaN/负数等垃圾值也被忽略（不触发其校验）
    weird = plan_frequency_sweep(NAN, -1, step_hz=1.0, scale='log', band='cispr_b')
    assert weird['points_hz'][0] == 150e3
    assert weird['points_hz'][-1] == 30e6
    assert weird['n_points'] == 9


def test_none_start_without_band_still_rejected():
    # 无 band 时 start/stop 缺省 None 仍拒（None 只在 band 语境下合法）
    with pytest.raises(ValueError, match="start_hz"):
        plan_frequency_sweep(None, 90e3, step_hz=9e3)
    with pytest.raises(ValueError, match="stop_hz"):
        plan_frequency_sweep(9e3, None, step_hz=9e3)
