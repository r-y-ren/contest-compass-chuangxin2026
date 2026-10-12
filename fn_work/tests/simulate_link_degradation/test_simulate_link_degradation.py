"""simulate_link_degradation 对抗测试：sim KPI 发生器（JSR 推导/悬崖 PER/流式口径）。"""
from __future__ import annotations

import pytest

from src.simulate_link_degradation.apply_cliff_model import apply_cliff_model
from src.simulate_link_degradation.simulate_link_degradation import simulate_link_degradation


def _ev(**fields) -> dict:
    """构造注入事件（默认 power_step + ts，字段可覆盖）。"""
    return {"type": "power_step", "ts": 1.0, **fields}


def _collect(events, **kwargs) -> list[dict]:
    return list(simulate_link_degradation(events, **kwargs))


def test_dut_sim_two_events_per_rises_monotonically():
    # 低/高电平两事件（信号 −20dBm）：JSR=−10 → 悬崖左远端 ≈ base；JSR=+30 → ≈ 1
    events = [
        _ev(target_db=-30.0, ts=1.0),
        _ev(target_db=10.0, ts=2.0),
    ]
    samples = _collect(events, ctx={"signal_power_db": -20.0})
    assert len(samples) == 2 * 3  # 默认 samples_per_event=3
    assert all(s["link"] == "sim" and s["source"] == "sim" for s in samples)
    low = [s["per_model"] for s in samples if s["event_ts"] == 1.0]
    high = [s["per_model"] for s in samples if s["event_ts"] == 2.0]
    assert max(low) < min(high)  # 样本流 PER 单调升（低批全段低于高批）
    assert all(p == pytest.approx(0.01, abs=1e-4) for p in low)
    assert all(0.95 < p < 1.0 for p in high)


def test_dut_sim_per_raw_matches_per_model_within_quantization():
    events = [_ev(jsr_db=jsr) for jsr in (-40.0, -12.0, 10.0, 11.5, 14.0, 25.0, 60.0)]
    for s in _collect(events):
        assert s["sent"] == 10
        assert s["err"] == round(s["per_model"] * 10)  # 构造口径
        assert s["per_raw"] == s["err"] / s["sent"]
        assert abs(s["per_raw"] - s["per_model"]) <= 0.05 + 1e-9  # 半量化步长内一致
        assert 0.0 <= s["per_model"] < 1.0
        assert s["per_model"] == apply_cliff_model({"jsr_db": s["jsr_db"]}, None)["per"]


def test_dut_sim_jsr_derivation_priority_three_tiers():
    ctx = {"signal_power_db": -20.0}
    cases = [
        ({"jsr_db": 5.0}, 5.0),  # 直给：不减信号电平
        ({"achieved_db": 30.0}, 50.0),  # achieved − signal
        ({"target_db": 40.0}, 60.0),  # 无 achieved → target − signal
        ({"jsr_db": 5.0, "achieved_db": 30.0, "target_db": 40.0}, 5.0),  # jsr_db 最优先
        ({"achieved_db": 30.0, "target_db": 40.0}, 50.0),  # achieved > target
    ]
    for fields, want_jsr in cases:
        sample = _collect([_ev(**fields)], ctx=ctx)[0]
        assert sample["jsr_db"] == pytest.approx(want_jsr)


def test_dut_sim_missing_signal_power_absolute_level_note():
    event = _ev(achieved_db=-15.0)
    for ctx in (None, {}):
        sample = _collect([event], ctx=ctx)[0]
        assert sample["jsr_note"] == "absolute_level_assumed"
        assert sample["jsr_db"] == pytest.approx(-15.0)  # 按绝对电平口径
    with_signal = _collect([event], ctx={"signal_power_db": -20.0})[0]
    assert "jsr_note" not in with_signal
    assert with_signal["jsr_db"] == pytest.approx(5.0)


def test_dut_sim_event_exhaustion_ends_naturally():
    pulled: list[dict] = []

    def source():
        for e in (_ev(jsr_db=-10.0, ts=1.0), _ev(jsr_db=20.0, ts=2.0)):
            pulled.append(e)
            yield e

    stream = simulate_link_degradation(source())
    assert iter(stream) is stream  # 输出为生成器/迭代器
    assert pulled == []  # 惰性：构造不拉取事件
    samples = list(stream)
    assert len(samples) == 2 * 3
    assert list(stream) == []  # 耗尽后再取为空（自然结束，不抛错）


def test_dut_sim_seq_and_timestamp_strictly_increasing():
    events = [_ev(jsr_db=0.0, ts=5.0), _ev(jsr_db=10.0, ts=6.0), _ev(jsr_db=20.0, ts=7.0)]
    samples = _collect(events)
    assert [s["seq"] for s in samples] == list(range(9))  # 全局递增且连续
    ts = [s["timestamp_ms"] for s in samples]
    assert all(b > a for a, b in zip(ts, ts[1:]))  # 严格单调递增
    assert ts[0] == 0.0


def test_dut_sim_samples_per_event_two_exact_batch_size():
    events = [_ev(jsr_db=0.0, ts=1.0), _ev(jsr_db=5.0, ts=2.0), _ev(jsr_db=9.0, ts=3.0)]
    samples = _collect(events, samples_per_event=2)
    assert len(samples) == 6
    per_event: dict[float, int] = {}
    for s in samples:
        per_event[s["event_ts"]] = per_event.get(s["event_ts"], 0) + 1
    assert per_event == {1.0: 2, 2.0: 2, 3.0: 2}  # 每事件恰 2 样本


def test_dut_sim_model_params_passthrough_threshold_shifts_per():
    event = _ev(jsr_db=0.0)
    shifted = {"base_per": 0.01, "threshold_db": -10.0, "softness_db": 2.0}
    default_sample = _collect([event], model_params=None)[0]
    shifted_sample = _collect([event], model_params=shifted)[0]
    # 透传：per_model 与 apply_cliff_model(同参数) 完全一致
    assert default_sample["per_model"] == apply_cliff_model({"jsr_db": 0.0}, None)["per"]
    assert shifted_sample["per_model"] == apply_cliff_model({"jsr_db": 0.0}, shifted)["per"]
    # threshold 10 → −10：同一 JSR=0 的 PER 抬升
    assert shifted_sample["per_model"] > default_sample["per_model"]
    assert shifted_sample["per_model"] > 0.9


def test_dut_sim_events_non_iterable_rejected():
    for bad in (42, None, 3.5, object()):
        with pytest.raises(ValueError):
            simulate_link_degradation(bad)


def test_dut_sim_samples_per_event_invalid_rejected():
    for bad in (0, -3, 2.5, "3", True):
        with pytest.raises(ValueError):
            simulate_link_degradation([], samples_per_event=bad)


def test_dut_sim_empty_events_yields_empty_generator():
    assert _collect([]) == []
    assert _collect(iter([])) == []
    stream = simulate_link_degradation([])
    assert list(stream) == []  # 空流 → 空生成器
    assert list(stream) == []


def test_dut_sim_out_of_domain_jsr_clamped_and_annotated():
    sample = _collect([_ev(jsr_db=150.0)])[0]
    assert sample["jsr_db"] == 150.0  # 记录推导原值
    assert sample["jsr_clamped"] is True  # 模型域外夹紧标注
    assert sample["per_model"] == apply_cliff_model({"jsr_db": 100.0}, None)["per"]
    inside = _collect([_ev(jsr_db=10.0)])[0]
    assert inside["jsr_clamped"] is False


def test_dut_sim_malformed_event_or_ctx_rejected():
    with pytest.raises(ValueError):
        _collect(["not-a-dict"])  # 事件非 dict
    with pytest.raises(ValueError):
        _collect([{"type": "power_step", "ts": 1.0}])  # 缺电平字段
    with pytest.raises(ValueError):
        _collect([_ev(jsr_db=float("nan"))])  # 电平非有限数值
    with pytest.raises(ValueError):
        simulate_link_degradation([], ctx={"signal_power_db": "high"})  # ctx 电平非法
