"""build_curve_frames 对抗单测（B13 叶子）：窗口聚合/帧B口径/时间线合并/形状校验。

覆盖（≥11）：两事件夹三 KPI 行的窗均独立复算、无判据样本窗→None、帧B y=1−x、
失效档对位、帧C 三类合并时间序、全空数据不抛、缺 judge_per 行不进均值、
乱序 KPI 时间排序开窗、元素非 dict 拒（含键+索引）、data 形状错拒、
n_windows/n_kpi_rows 计数、帧A x 为 target 序非索引、首事件前行不进窗、
非 power_step 事件不开窗但入帧C。
"""
from __future__ import annotations

import pytest

from src.plot_triple_curves.build_curve_frames import build_curve_frames


def _kpi(ts, per=None, **extra):
    row = {"ts_ms": ts}
    if per is not None:
        row["judge_per"] = per
    row.update(extra)
    return row


def _ev(ts, target, step=None, type_="power_step"):
    ev = {"type": type_, "ts_ms": ts, "target_db": target}
    if step is not None:
        ev["step"] = step
    return ev


def _two_events_three_rows():
    """两 power_step 事件夹三行 KPI（窗0 两行、窗1 一行）的标准夹具。"""
    return {
        "kpi": [_kpi(150, 0.08), _kpi(250, 0.12), _kpi(350, 0.30)],
        "events": [_ev(100, -10.0, step=0), _ev(300, -5.0, step=1)],
        "failure_levels": [],
    }


def test_frame_a_two_windows_mean_independent_recompute():
    data = _two_events_three_rows()
    out = build_curve_frames(data)

    # 独立复算（不复用被测代码路径）：窗0=事件@100 后、事件@300 前的行均值
    w0 = [r["judge_per"] for r in data["kpi"] if 100 <= r["ts_ms"] < 300]
    w1 = [r["judge_per"] for r in data["kpi"] if r["ts_ms"] >= 300]
    expected0 = sum(w0) / len(w0)
    expected1 = sum(w1) / len(w1)

    assert out["frame_a"]["x"] == [-10.0, -5.0]
    assert out["frame_a"]["y"][0] == pytest.approx(expected0)
    assert out["frame_a"]["y"][1] == pytest.approx(expected1)
    assert out["frame_a"]["y"] == pytest.approx([0.10, 0.30])
    assert out["frame_a"]["window_sizes"] == [2, 1]


def test_window_without_judge_samples_yields_none_breakpoint():
    data = {
        "kpi": [_kpi(150, 0.1), _kpi(250, None), _kpi(350)],  # 窗1 两行均无判据
        "events": [_ev(100, -10.0), _ev(300, -5.0), _ev(500, 0.0)],  # 窗2 无任何行
        "failure_levels": [],
    }
    out = build_curve_frames(data)
    assert out["frame_a"]["y"] == [pytest.approx(0.1), None, None]
    assert out["frame_a"]["window_sizes"] == [1, 0, 0]
    # None 窗自帧B剔除 → 帧B 仅剩窗0
    assert out["frame_b"]["x"] == [pytest.approx(0.1)]
    assert out["frame_b"]["y"] == [pytest.approx(0.9)]


def test_frame_b_y_is_one_minus_x():
    data = {
        "kpi": [_kpi(150, 0.02), _kpi(250, 0.06), _kpi(350, 0.5)],
        "events": [_ev(100, -10.0), _ev(300, -5.0)],
        "failure_levels": [],
    }
    out = build_curve_frames(data)
    bx, by = out["frame_b"]["x"], out["frame_b"]["y"]
    assert len(bx) == len(by) == 2
    for x_val, y_val in zip(bx, by):
        assert y_val == pytest.approx(1.0 - x_val)
    assert by == pytest.approx([1.0 - 0.04, 0.5])


def test_failure_x_alignment_with_window_positions():
    data = {
        "kpi": [_kpi(150, 0.1)],
        "events": [_ev(100, -10.0, step=0), _ev(300, -5.0, step=1), _ev(500, 0.0, step=2)],
        "failure_levels": [
            {"step": 1, "ts_ms": 320, "failure_level_db": -5.0},
            {"step": 2, "ts_ms": 520},
            {"step": 9, "ts_ms": 530},  # 越界档号：跳过不抛
        ],
    }
    out = build_curve_frames(data)
    # step 对位窗口 x：档1→-5.0、档2→0.0
    assert out["frame_a"]["failure_x"] == [-5.0, 0.0]

    # 事件缺 step 字段时按窗口序号兜底
    data2 = {
        "kpi": [],
        "events": [_ev(100, -10.0), _ev(300, -5.0), _ev(500, 0.0)],
        "failure_levels": [{"step": 0, "ts_ms": 320}],
    }
    out2 = build_curve_frames(data2)
    assert out2["frame_a"]["failure_x"] == [-10.0]


def test_frame_c_merges_three_kinds_in_time_order():
    data = {
        "kpi": [_kpi(400, 0.3), _kpi(120, 0.1)],  # 乱序输入
        "events": [_ev(300, -5.0), _ev(100, -10.0)],
        "failure_levels": [{"step": 1, "ts_ms": 200}],
    }
    out = build_curve_frames(data)
    frame_c = out["frame_c"]
    t, kind, labels = frame_c["t"], frame_c["kind"], frame_c["labels"]
    assert len(t) == len(kind) == len(labels) == 5
    assert t == sorted(t) == [100, 120, 200, 300, 400]
    assert kind == [0, 1, 2, 0, 1]  # 事件/KPI/失效/事件/KPI 按时间排定
    assert set(kind) == {0, 1, 2}
    assert all(isinstance(label, str) for label in labels)
    # 失效点标签含档号
    assert labels[2] == "失效@档1"


def test_empty_data_gives_empty_frames_no_raise():
    out = build_curve_frames({"kpi": [], "events": [], "failure_levels": []})
    assert out["frame_a"] == {"x": [], "y": [], "failure_x": [], "window_sizes": []}
    assert out["frame_b"] == {"x": [], "y": []}
    assert out["frame_c"] == {"t": [], "kind": [], "labels": []}
    assert out["n_windows"] == 0
    assert out["n_kpi_rows"] == 0


def test_kpi_missing_judge_per_excluded_from_window_mean():
    data = {
        "kpi": [_kpi(150, 0.06), _kpi(200), _kpi(250, 0.14)],  # 中间行缺 judge_per
        "events": [_ev(100, -10.0), _ev(300, -5.0)],
        "failure_levels": [],
    }
    out = build_curve_frames(data)
    assert out["frame_a"]["y"][0] == pytest.approx((0.06 + 0.14) / 2)
    assert out["frame_a"]["window_sizes"] == [2, 0]  # 缺判据行不计入窗样本
    # 该行仍入帧C与计数（缺判据只影响均值）
    assert out["frame_c"]["kind"].count(1) == 3
    assert out["n_kpi_rows"] == 3


def test_out_of_order_kpi_rows_sorted_before_windowing():
    data = _two_events_three_rows()
    data["kpi"] = list(reversed(data["kpi"]))  # 乱序：350/250/150
    out = build_curve_frames(data)
    assert out["frame_a"]["y"] == pytest.approx([0.10, 0.30])
    assert out["frame_a"]["window_sizes"] == [2, 1]
    assert out["frame_c"]["t"] == [100, 150, 250, 300, 350]


@pytest.mark.parametrize("key", ["kpi", "events", "failure_levels"])
def test_non_dict_element_rejected_with_key_and_index(key):
    data = {"kpi": [_kpi(100, 0.1)], "events": [_ev(50, -10.0)], "failure_levels": []}
    data[key] = [dict(data[key][0]) if data[key] else {"step": 0}, 42]  # [1] 非法
    with pytest.raises(ValueError, match=rf"data\['{key}'\]\[1\]"):
        build_curve_frames(data)


@pytest.mark.parametrize(
    "bad",
    [
        [],  # 非 dict
        None,
        "kpi",
        {"kpi": {}, "events": [], "failure_levels": []},  # 键非 list
        {"kpi": [], "events": None, "failure_levels": []},
        {"kpi": [], "events": [], "failure_levels": "x"},
        {"kpi": []},  # 缺键
        {"events": [], "failure_levels": []},
        {"kpi": [], "failure_levels": []},
    ],
)
def test_data_shape_rejected(bad):
    with pytest.raises(ValueError):
        build_curve_frames(bad)


def test_n_windows_and_n_kpi_rows_counts():
    data = {
        "kpi": [_kpi(50, 0.01), _kpi(150, 0.08), _kpi(250), _kpi(350, 0.30)],
        "events": [
            _ev(100, -10.0),
            _ev(300, -5.0),
            {"type": "tx_stop", "ts_ms": 400},  # 非 power_step 不开窗
        ],
        "failure_levels": [{"step": 0, "ts_ms": 310}],
    }
    out = build_curve_frames(data)
    assert out["n_windows"] == 2  # 仅两个 power_step
    assert out["n_kpi_rows"] == 4  # 全部 kpi 行（含缺判据/首事件前）
    assert len(out["frame_a"]["x"]) == len(out["frame_a"]["y"]) == 2
    assert out["frame_a"]["window_sizes"] == [1, 1]  # 150 与 350 各成窗判据


def test_frame_a_x_is_target_sequence_not_indices():
    targets = [-12.5, -7, 0]
    data = {
        "kpi": [],
        "events": [_ev(100 + 100 * i, t) for i, t in enumerate(targets)],
        "failure_levels": [],
    }
    out = build_curve_frames(data)
    assert out["frame_a"]["x"] == targets
    assert out["frame_a"]["x"] != [0, 1, 2]  # 值序而非索引序
    assert all(v != i for i, v in enumerate(out["frame_a"]["x"]))


def test_rows_before_first_event_not_in_any_window():
    data = {
        "kpi": [_kpi(50, 0.99), _kpi(150, 0.1)],  # ts=50 在首事件之前
        "events": [_ev(100, -10.0), _ev(300, -5.0)],
        "failure_levels": [],
    }
    out = build_curve_frames(data)
    assert out["frame_a"]["y"] == [pytest.approx(0.1), None]
    assert out["frame_a"]["window_sizes"] == [1, 0]
    assert out["n_kpi_rows"] == 2  # 计数不丢
    assert 50 in out["frame_c"]["t"]  # 时间线仍在


def test_non_power_step_event_no_window_but_in_frame_c():
    data = {
        "kpi": [_kpi(150, 0.1)],
        "events": [_ev(100, -10.0), {"type": "tx_stop", "ts_ms": 120}],
        "failure_levels": [],
    }
    out = build_curve_frames(data)
    assert out["n_windows"] == 1
    assert out["frame_a"]["x"] == [-10.0]
    assert out["frame_a"]["y"] == [pytest.approx(0.1)]
    kinds = out["frame_c"]["kind"]
    assert kinds == [0, 0, 1]  # tx_stop 仍为事件点入帧C
    assert "tx_stop" in out["frame_c"]["labels"][1]
