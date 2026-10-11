"""compensate_link_power 对抗测试：插值/外推/缺表/占位与损坏/非法值/空序列/显式表/不对称覆盖/可信度压级。"""
from __future__ import annotations

import json

import pytest

from src.compensate_link_power.compensate_link_power import compensate_link_power


def _cfg_with_dir(tmp_path, name="calibrations"):
    """建立临时标定目录，返回 (config, dir)。"""
    cal = tmp_path / name
    cal.mkdir()
    return {"calibration_dir": str(cal)}, cal


def _write_table(cal_dir, name, payload):
    (cal_dir / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_link_compensation_both_tables_interpolate_and_formula(tmp_path):
    """① 双表齐全：区间中点线性插值+公式(6) P_actual=P_measured+L_link+C_ant；端点精确命中同 ok。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "link_loss", {"2400": 1.0, "5800": 3.0})
    _write_table(cal, "antenna", {"2400": 2.0, "5800": 6.0})
    out = compensate_link_power([(4100, -40.0), (2400, -50.0)], cfg)
    assert len(out) == 2
    mid = out[0]
    assert mid["freq_mhz"] == 4100.0
    assert mid["p_measured"] == -40.0
    assert mid["l_link"] == pytest.approx(2.0)  # (4100-2400)/3400 中点 → 1.0+0.5*2.0
    assert mid["c_ant"] == pytest.approx(4.0)  # 2.0+0.5*4.0
    assert mid["p_actual"] == pytest.approx(-34.0)  # 公式(6)：-40+2+4
    assert mid["confidence"] == "ok"
    hit = out[1]
    assert hit["l_link"] == pytest.approx(1.0)  # 端点精确命中
    assert hit["c_ant"] == pytest.approx(2.0)
    assert hit["p_actual"] == pytest.approx(-47.0)
    assert hit["confidence"] == "ok"


def test_link_compensation_out_of_range_uses_nearest_endpoint(tmp_path):
    """② 频点在表覆盖区间外：取最近端点值并标 extrapolated，公式仍逐点成立。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "link_loss", {"2400": 1.0, "5800": 3.0})
    _write_table(cal, "antenna", {"2400": 2.0, "5800": 6.0})
    out = compensate_link_power([(1000, -30.0), (6000, -30.0)], cfg)
    low = out[0]
    assert low["l_link"] == pytest.approx(1.0)  # 低于低端 → 取 2400 处值
    assert low["c_ant"] == pytest.approx(2.0)
    assert low["confidence"] == "extrapolated"
    high = out[1]
    assert high["l_link"] == pytest.approx(3.0)  # 高于高端 → 取 5800 处值
    assert high["c_ant"] == pytest.approx(6.0)
    assert high["p_actual"] == pytest.approx(-21.0)
    assert high["confidence"] == "extrapolated"


def test_link_compensation_missing_link_loss_marks_no_table(tmp_path):
    """③ 缺 link_loss 表（仅 antenna 在档）：l_link=None、confidence='no_table'，p_actual 只计已知项。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "antenna", {"2400": 2.0, "5800": 6.0})
    out = compensate_link_power([(2400, -40.0)], cfg)
    assert out[0]["l_link"] is None
    assert out[0]["c_ant"] == pytest.approx(2.0)
    assert out[0]["confidence"] == "no_table"
    assert out[0]["p_actual"] == pytest.approx(-38.0)  # 未知项不计


def test_link_compensation_placeholder_and_corrupt_tables_no_table(tmp_path):
    """④ 占位表（空目录全缺 →【待实测】）与损坏表（非法 JSON/结构不符）均同 no_table，不抛出。"""
    # 空目录：双表均走【待实测】占位视图
    cfg_empty, _ = _cfg_with_dir(tmp_path)
    out = compensate_link_power([(2400, -40.0)], cfg_empty)
    assert out[0]["l_link"] is None
    assert out[0]["c_ant"] is None
    assert out[0]["confidence"] == "no_table"
    assert out[0]["p_actual"] == pytest.approx(-40.0)
    # 损坏表：截断 JSON + 值非数值 → CalibrationError 路径，同样标 no_table
    cfg_bad, cal_bad = _cfg_with_dir(tmp_path, name="cal_corrupt")
    (cal_bad / "link_loss.json").write_text('{"2400": ', encoding="utf-8")
    (cal_bad / "antenna.json").write_text('{"2400": "x"}', encoding="utf-8")
    out_bad = compensate_link_power([(2400, -40.0)], cfg_bad)
    assert out_bad[0]["confidence"] == "no_table"
    assert out_bad[0]["l_link"] is None
    assert out_bad[0]["c_ant"] is None
    assert out_bad[0]["p_actual"] == pytest.approx(-40.0)


def test_link_compensation_nan_or_inf_measurement_invalid(tmp_path):
    """⑤ NaN/inf 测量值：该点 confidence='invalid'、p_actual=None，不抛出且不污染邻点。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "link_loss", {"2400": 1.0})
    _write_table(cal, "antenna", {"2400": 2.0})
    out = compensate_link_power(
        [(2400, float("nan")), (2400, float("inf")), (2400, -40.0)], cfg
    )
    assert out[0]["confidence"] == "invalid"
    assert out[0]["p_actual"] is None
    assert out[0]["p_measured"] is None
    assert out[1]["confidence"] == "invalid"
    assert out[1]["p_actual"] is None
    assert out[2]["confidence"] == "ok"
    assert out[2]["p_actual"] == pytest.approx(-37.0)


def test_link_compensation_bool_or_malformed_points_invalid(tmp_path):
    """⑥ bool 频点/bool 测量值/NaN 频点/非二元组：一律 invalid、p_actual=None，不抛出。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "link_loss", {"2400": 1.0})
    _write_table(cal, "antenna", {"2400": 2.0})
    out = compensate_link_power(
        [(True, -40.0), (float("nan"), -40.0), (2400, True), "junk", [2400]], cfg
    )
    for point in out:
        assert point["confidence"] == "invalid"
        assert point["p_actual"] is None
    assert out[0]["freq_mhz"] is None  # bool 不作频点数值
    assert out[2]["freq_mhz"] == 2400.0  # 频点合法仅功率非法 → 频点保留
    assert out[2]["p_measured"] is None
    assert out[3]["freq_mhz"] is None and out[3]["p_measured"] is None


def test_link_compensation_empty_sequence_returns_empty(tmp_path):
    """⑦ 空测量序列 → []（不触发表加载口径以外的副作用）。"""
    cfg, _ = _cfg_with_dir(tmp_path)
    assert compensate_link_power([], cfg) == []


def test_link_compensation_explicit_tables_match_file_loading(tmp_path):
    """⑧ 显式 tables 参数与文件加载（tables=None+config）结果完全一致（含插值与外推点）。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "link_loss", {"2400": 1.0, "3600": 2.0, "5800": 3.0})
    _write_table(cal, "antenna", {"2400": 2.0, "5800": 6.0})
    measurements = [(2400, -40.0), (3000, -41.5), (9000, -20.0)]
    via_files = compensate_link_power(measurements, cfg)
    via_tables = compensate_link_power(
        measurements,
        cfg,
        tables={
            "link_loss": {2400.0: 1.0, 3600.0: 2.0, 5800.0: 3.0},
            "antenna": {2400.0: 2.0, 5800.0: 6.0},
        },
    )
    assert via_tables == via_files
    assert [p["confidence"] for p in via_files] == ["ok", "ok", "extrapolated"]
    assert via_files[1]["l_link"] == pytest.approx(1.5)  # 3000 恰为 2400→3600 中点


def test_link_compensation_asymmetric_coverage_mixed_confidence(tmp_path):
    """⑨ 双表频点不对称：一张覆盖另一张不覆盖 → 同批输出混合 ok/extrapolated。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "link_loss", {"2400": 1.0, "5800": 3.0})
    _write_table(cal, "antenna", {"5150": 5.0, "5850": 7.0})  # antenna 不覆盖 2.4G
    out = compensate_link_power([(5500, -40.0), (2450, -40.0)], cfg)
    covered = out[0]
    assert covered["confidence"] == "ok"  # 双表均在区间内
    assert covered["c_ant"] == pytest.approx(6.0)  # 5150→5850 中点
    assert covered["l_link"] == pytest.approx(1.0 + 3100.0 / 3400.0 * 2.0)
    uncovered = out[1]
    assert uncovered["confidence"] == "extrapolated"  # antenna 区间外 → 取低端端点
    assert uncovered["c_ant"] == pytest.approx(5.0)
    assert uncovered["l_link"] == pytest.approx(1.0 + 50.0 / 3400.0 * 2.0)
    assert uncovered["p_actual"] == pytest.approx(-40.0 + uncovered["l_link"] + 5.0)
    assert {p["confidence"] for p in out} == {"ok", "extrapolated"}


def test_link_compensation_no_table_precedence_over_extrapolated(tmp_path):
    """⑩ 缺表与外推并存：no_table 压过 extrapolated，已知（外推）项仍计入 p_actual。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "antenna", {"5150": 5.0, "5850": 7.0})  # link_loss 缺 + antenna 不覆盖 2450
    out = compensate_link_power([(2450, -40.0)], cfg)
    assert out[0]["confidence"] == "no_table"
    assert out[0]["l_link"] is None
    assert out[0]["c_ant"] == pytest.approx(5.0)
    assert out[0]["p_actual"] == pytest.approx(-35.0)


def test_link_compensation_single_point_table_exact_ok_else_extrapolated(tmp_path):
    """⑪ 单点表：频点精确命中 ok；其余频点一律取该点值并标 extrapolated。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "link_loss", {"2400": 1.5})
    _write_table(cal, "antenna", {"2400": 2.5})
    out = compensate_link_power([(2400, -40.0), (2450, -40.0)], cfg)
    assert out[0]["confidence"] == "ok"
    assert out[0]["p_actual"] == pytest.approx(-36.0)
    assert out[1]["confidence"] == "extrapolated"
    assert out[1]["l_link"] == pytest.approx(1.5)
    assert out[1]["c_ant"] == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# B2 对抗审查缺陷回归（高#3/#5）
# ---------------------------------------------------------------------------

def test_defect_b2_huge_int_freq_or_measurement_invalid(tmp_path):
    """高#3：10**400 超大 int 频点/测量值 → confidence='invalid'（p_actual=None），不抛 OverflowError。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    _write_table(cal, "link_loss", {"2400": 1.0})
    _write_table(cal, "antenna", {"2400": 2.0})
    out = compensate_link_power(
        [(10**400, -40.0), (2400, 10**400), (2400, -40.0)], cfg
    )
    assert out[0]["confidence"] == "invalid"
    assert out[0]["freq_mhz"] is None
    assert out[0]["p_actual"] is None
    assert out[1]["confidence"] == "invalid"
    assert out[1]["p_measured"] is None
    assert out[1]["p_actual"] is None
    assert out[2]["confidence"] == "ok"  # 非法点不污染邻点
    assert out[2]["p_actual"] == pytest.approx(-37.0)


def test_defect_b2_deeply_nested_tables_no_table(tmp_path):
    """高#5 下游：50000 层深嵌套标定表 → CalibrationError 转该表缺表（no_table），不抛。"""
    cfg, cal = _cfg_with_dir(tmp_path)
    deep = "[" * 50000 + "]" * 50000
    (cal / "link_loss.json").write_text(deep, encoding="utf-8")
    (cal / "antenna.json").write_text(deep, encoding="utf-8")
    out = compensate_link_power([(2400, -40.0)], cfg)
    assert out[0]["confidence"] == "no_table"
    assert out[0]["l_link"] is None
    assert out[0]["c_ant"] is None
    assert out[0]["p_actual"] == pytest.approx(-40.0)
