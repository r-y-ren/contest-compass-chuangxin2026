"""normalize_monitor_block 对抗测试（共享，R88 上提）：dict 直通同对象/二元组归一盖戳
（ts 主机单调毫秒域、rx_ts→block_index 附注、overflow 透传、meta 缺键降级）/未知形状
原样透传同一对象。"""
from __future__ import annotations

import time

from src.shared.normalize_monitor_block import normalize_monitor_block


def test_dict_block_passthrough_same_object():
    """① dict 块（B210 契约）直通：返回同一对象引用，不复制不改键。"""
    block = {"samples": [1 + 2j, 3 + 4j], "ts": 1234.5, "overflow": False}
    result = normalize_monitor_block(block)
    assert result is block


def test_empty_dict_passthrough():
    """①b 空 dict 也是 dict 形状：同样直通（不做键级校验，拒形状归 capture 侧）。"""
    block: dict = {}
    assert normalize_monitor_block(block) is block


def test_sim_tuple_normalized_to_block_dict():
    """② sim 契约二元组归一：(samples, {'rx_ts': 7, 'overflow': True}) → 块 dict
    四键齐全：samples 同引用、ts 为主机单调毫秒（落在调用前后窗内）、
    block_index==7（rx_ts 块号降级附注）、overflow is True。"""
    samples = [0.5 + 0.5j, -1 + 0j]
    ts_before = time.monotonic() * 1000.0
    result = normalize_monitor_block((samples, {"rx_ts": 7, "overflow": True}))
    ts_after = time.monotonic() * 1000.0
    assert set(result.keys()) == {"samples", "ts", "block_index", "overflow"}
    assert result["samples"] is samples
    assert isinstance(result["ts"], float)
    assert ts_before <= result["ts"] <= ts_after  # 盖戳语义=调用时刻
    assert result["block_index"] == 7
    assert result["overflow"] is True


def test_sim_tuple_meta_missing_keys_defaults():
    """②b meta 无 rx_ts/overflow 键：block_index 降级 None、overflow 缺省 False。"""
    samples = [1 + 1j]
    result = normalize_monitor_block((samples, {}))
    assert result["samples"] is samples
    assert result["block_index"] is None
    assert result["overflow"] is False
    assert isinstance(result["ts"], float)


def test_tuple_consecutive_stamps_strictly_increasing():
    """②c 逐块连盖戳严格递增：浮点毫秒域同毫秒内两块不并列（B12 中#1 注记口径）。"""
    first = normalize_monitor_block(([1], {"rx_ts": 1}))
    second = normalize_monitor_block(([2], {"rx_ts": 2}))
    assert second["ts"] > first["ts"]
    assert second["block_index"] == 2


def test_unknown_shapes_passthrough_same_object():
    """③ 未知形状（字符串/单元素 tuple/三元组/第二元素非 dict 的二元组）原样透传
    同一对象——形状拒归 capture 块形状校验，此处不抛不裹。"""
    blob = "not-a-block"
    assert normalize_monitor_block(blob) is blob
    one = ([1],)
    assert normalize_monitor_block(one) is one
    three = ([1], {"rx_ts": 1}, "extra")
    assert normalize_monitor_block(three) is three
    pair_nondict = ([1], [1])
    assert normalize_monitor_block(pair_nondict) is pair_nondict


def test_list_shape_passthrough():
    """③b list 形状（非 tuple 分支）：原样透传同一对象，不做元素级归一。"""
    blob = [{"samples": [1], "ts": 9.0}]
    assert normalize_monitor_block(blob) is blob
