"""loopback_sim_stream 对抗测试：恒等环回、延迟占位因果性、增益/泄漏/噪声效应、
越域夹紧标注、空块/空迭代器、非复数样本计数标注、非法 effects 类型 ValueError。"""
from __future__ import annotations

import math

import pytest

from src.open_sim_backend.loopback_sim_stream import loopback_sim_stream


def _collect(stream):
    """物化整条 RX 流为 [(block 副本, meta 副本)]，便于整体比较。"""
    return [(list(block), dict(meta)) for block, meta in stream]


def test_identity_loopback_effects_empty():
    """① 恒等环回：effects={} 逐块等值透传，meta 仅含基础字段，rx_ts 从 0 单调。"""
    blocks = [[1 + 2j, 3 - 1j], [0.5 + 0.5j]]
    stream = loopback_sim_stream(blocks, {})
    assert hasattr(stream, "__next__")  # 返回迭代器（生成器），逐块拉取
    out = _collect(stream)
    assert [b for b, _ in out] == blocks
    assert [m["rx_ts"] for _, m in out] == [0, 1]
    assert [m["src_index"] for _, m in out] == [0, 1]
    assert [m["n_samples"] for _, m in out] == [2, 1]
    for _, meta in out:
        assert "clamped" not in meta
        assert "placeholder" not in meta
        assert "invalid_samples" not in meta


def test_delay_two_blocks_placeholder_causal():
    """② 延迟 2 块：首两块为空占位（src_index=None）且 rx_ts 0..4 连续，真实块随后逐块等值。"""
    blocks = [[1 + 1j], [2 + 2j], [3 + 3j]]
    out = _collect(loopback_sim_stream(blocks, {"delay_blocks": 2}))
    assert len(out) == 5
    first, second, *rest = out
    assert first[0] == [] and second[0] == []
    assert first[1]["placeholder"] is True and second[1]["placeholder"] is True
    assert first[1]["src_index"] is None and second[1]["src_index"] is None
    assert first[1]["n_samples"] == 0 and second[1]["n_samples"] == 0
    assert [m["rx_ts"] for _, m in out] == [0, 1, 2, 3, 4]  # 序号连续无跳变
    assert [b for b, _ in rest] == blocks
    assert [m["src_index"] for _, m in rest] == [0, 1, 2]
    for _, meta in rest:
        assert "placeholder" not in meta


def test_gain_minus_6db_halves_amplitude():
    """③ gain_db=-6：幅度按 10**(-6/20)≈0.501 缩放（近似减半），相位不变。"""
    blocks = [[2 + 0j, 3j, 1 + 1j]]
    (rx, _), = _collect(loopback_sim_stream(blocks, {"gain_db": -6}))
    factor = 10.0 ** (-6.0 / 20.0)
    for got, src in zip(rx, blocks[0]):
        assert got == pytest.approx(src * factor)
        assert abs(got) == pytest.approx(0.5 * abs(src), rel=0.005)  # “减半”


def test_noise_seeded_reproducible():
    """④ 噪声种子固定：同 seed 两轮输出逐位一致；换 seed 不同；噪声确实改变了样本。"""
    blocks = [[1 + 0j] * 8, [0.5 - 0.5j] * 8]
    run_a = _collect(loopback_sim_stream(blocks, {"noise_dbm": 0.0}, seed=7))
    run_b = _collect(loopback_sim_stream(blocks, {"noise_dbm": 0.0}, seed=7))
    assert run_a == run_b  # 含 meta 的逐位一致
    run_c = _collect(loopback_sim_stream(blocks, {"noise_dbm": 0.0}, seed=8))
    assert run_c != run_a
    clean = _collect(loopback_sim_stream(blocks, {}))
    assert [b for b, _ in run_a] != [b for b, _ in clean]  # 噪声真实叠加（非恒等）


def test_lo_leak_adds_fixed_dc():
    """⑤ lo_leak_db：每块加固定 DC 分量（本块 RMS×10**(db/20)），实轴单音、块内逐样本等值。"""
    blocks = [[1 + 0j] * 8, [2 + 0j] * 4, [1 + 0j, 3 + 0j]]
    out = _collect(loopback_sim_stream(blocks, {"lo_leak_db": -20.0}))
    (b0, _), (b1, _), (b2, _) = out
    assert b0 == pytest.approx([1.1 + 0j] * 8)  # rms=1 → DC=0.1
    assert b1 == pytest.approx([2.2 + 0j] * 4)  # rms=2 → DC=0.2
    dc2 = math.sqrt((1.0 + 9.0) / 2.0) * 0.1  # 混幅块按块 RMS=sqrt(5) 取参考
    assert b2 == pytest.approx([1.0 + dc2 + 0j, 3.0 + dc2 + 0j])
    assert all(s.imag == 0 for s in b0 + b1)  # DC 泄漏落在实轴


def test_negative_delay_clamped_to_zero():
    """⑥ 负延迟：夹紧为 0（无占位块、块数不增），每块 meta['clamped'] 记录 from/to。"""
    blocks = [[1j], [2j]]
    out = _collect(loopback_sim_stream(blocks, {"delay_blocks": -3}))
    assert len(out) == 2
    assert [b for b, _ in out] == blocks
    assert [m["rx_ts"] for _, m in out] == [0, 1]
    assert all(
        m["clamped"] == {"delay_blocks": {"from": -3, "to": 0}} for _, m in out
    )
    assert all("placeholder" not in m for _, m in out)


def test_gain_100db_clamped_to_40db():
    """⑦ gain_db=100：夹紧 40dB（×100 幅度），clamped 记录 from=100.0 to=40.0。"""
    blocks = [[0.001 + 0.002j, 0.1j]]
    (rx, meta), = _collect(loopback_sim_stream(blocks, {"gain_db": 100.0}))
    assert meta["clamped"] == {"gain_db": {"from": 100.0, "to": 40.0}}
    assert rx == pytest.approx([c * 100.0 for c in blocks[0]])  # 40dB=×100，非 ×10^5


def test_empty_blocks_and_empty_iterator():
    """⑧ 空块透传空块（噪声/泄漏开启时仍无样本可作用）、空迭代器零产出；延迟与空流共存只吐占位块。"""
    effects = {"gain_db": 0.0, "noise_dbm": 0.0, "lo_leak_db": -10.0}
    out = _collect(loopback_sim_stream([[], [1 + 1j], []], effects))
    assert [len(b) for b, _ in out] == [0, 1, 0]
    assert out[0][0] == [] and out[2][0] == []  # 空块保持空（未被噪声/泄漏填充）
    assert [m["n_samples"] for _, m in out] == [0, 1, 0]
    assert [m["src_index"] for _, m in out] == [0, 1, 2]
    assert _collect(loopback_sim_stream(iter([]), {})) == []  # 空迭代器：零产出不报错
    only_ph = _collect(loopback_sim_stream(iter([]), {"delay_blocks": 1}))
    assert len(only_ph) == 1
    assert only_ph[0][0] == []
    assert only_ph[0][1]["placeholder"] is True


def test_non_complex_samples_zeroed_and_counted():
    """⑨ 非复数元素：按 0+0j 处理且该块 meta 计数标注（不传染后续块）。"""
    blocks = [[1 + 0j, "abc", None, 2 + 0j, {"bad": 1}], [5 + 5j]]
    out = _collect(loopback_sim_stream(blocks, {"lo_leak_db": -20.0}))
    (rx0, m0), (rx1, m1) = out
    # 块 RMS 参考=清零后全块（|1|²+|2|² 共 5 样本 → rms=1 → DC=0.1）
    assert rx0 == pytest.approx([1.1 + 0j, 0.1 + 0j, 0.1 + 0j, 2.1 + 0j, 0.1 + 0j])
    assert m0["invalid_samples"] == 3
    assert "invalid_samples" not in m1  # 计数按块、不累计
    assert rx1 == pytest.approx([(5.0 + math.sqrt(50.0) * 0.1) + 5j])  # 全有效块正常


@pytest.mark.parametrize("bad_effects", [None, [], "gain_db=-6", 3.5, ("delay_blocks", 1)])
def test_invalid_effects_type_raises_valueerror(bad_effects):
    """⑩ 非法 effects 类型：非 dict 一律 ValueError，且调用点即抛（无需消费流）。"""
    with pytest.raises(ValueError):
        loopback_sim_stream([[1 + 1j]], bad_effects)


@pytest.mark.parametrize(
    "bad_effects",
    [
        {"delay_blocks": "2"},  # 字符串非整数
        {"delay_blocks": 1.5},  # 浮点非整数
        {"delay_blocks": True},  # 布尔拒收
        {"gain_db": "high"},
        {"gain_db": False},
        {"noise_dbm": float("nan")},
        {"lo_leak_db": float("inf")},
    ],
)
def test_invalid_effects_numeric_key_raises_valueerror(bad_effects):
    """⑪ 数值键类型非法（字符串/布尔/非有限数）：ValueError。"""
    with pytest.raises(ValueError):
        loopback_sim_stream([[1 + 1j]], bad_effects)


def test_clamped_annotation_present_on_every_block():
    """⑫ 夹紧+数据块并存：clamped 在占位块与真实块上都带（中途接入消费者可审计）。"""
    out = _collect(
        loopback_sim_stream([[1j]], {"delay_blocks": 1, "gain_db": 50.0})
    )
    assert len(out) == 2
    expected_clamp = {
        "gain_db": {"from": 50.0, "to": 40.0},
    }
    assert out[0][1]["clamped"] == expected_clamp  # 占位块带标注
    assert out[1][1]["clamped"] == expected_clamp  # 真实块带标注
    assert out[1][0] == pytest.approx([100j])  # 夹紧后 ×100
    assert [m["rx_ts"] for _, m in out] == [0, 1]


def test_noise_and_leak_overflow_clamped_not_raised():
    """⑬ 对抗：noise_dbm=4000 / lo_leak_db=10000 会让预推导 10**x 溢出——按上界夹紧
    （noise→30dBm、leak→60dB）并标注 clamped，不抛 OverflowError，样本保持有限。"""
    blocks = [[1 + 0j, 1 + 0j]]
    out = _collect(loopback_sim_stream(blocks, {"noise_dbm": 4000.0, "lo_leak_db": 10000.0}))
    (rx, meta), = out
    assert meta["clamped"]["noise_dbm"] == {"from": 4000.0, "to": 30.0}
    assert meta["clamped"]["lo_leak_db"] == {"from": 10000.0, "to": 60.0}
    # 夹紧后：噪声 sigma=sqrt(1/2)（30dBm=1W、I/Q 各半），泄漏 DC=RMS×10**(60/20)=1000
    assert all(math.isfinite(s.real) and math.isfinite(s.imag) for s in rx)
    for s in rx:
        assert s.real == pytest.approx(1000.0, abs=10.0)  # DC 主导，噪声 ±~7σ 内
        assert abs(s.imag) < 10.0  # 虚轴只剩 ±sqrt(1/2) 量级噪声


def test_noise_leak_at_bounds_not_clamped():
    """⑭ 恰在边界（noise=30dBm、leak=60dB）不夹紧：clamped 不含对应键。"""
    out = _collect(loopback_sim_stream([[1 + 0j]], {"noise_dbm": 30.0, "lo_leak_db": 60.0}))
    (rx, meta), = out
    assert "clamped" not in meta
    assert math.isfinite(rx[0].real) and math.isfinite(rx[0].imag)
