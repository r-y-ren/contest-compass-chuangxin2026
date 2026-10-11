"""calibrate_leakage 行为用例：验收 slug=leak_calibration（标定写表 + 查表扣除 + 未扣除标注）。"""
import json

import pytest

from src.calibrate_leakage.calibrate_leakage import CalibrationWarn, calibrate_leakage


def _calibrate_ok(tmp_path, points, name="leak_table.json"):
    """辅助：用合法测点完成一次标定，返回表路径与返回值。"""
    table_path = tmp_path / name
    result = calibrate_leakage(session_data={"points": points, "out_path": str(table_path)})
    assert result["mode"] == "calibrate"
    assert result["table_path"] == str(table_path)
    assert result["points"] == len(points)
    assert table_path.is_file()
    return table_path, result


def test_leak_calibration_roundtrip_five_points(tmp_path):
    """标定 5 点 -> 表落盘 -> 扣除请求读回同一张表并命中测点。"""
    points = [
        {"freq_mhz": 100.0, "coupling_db": -30.5},
        {"freq_mhz": 200.0, "coupling_db": -28.0},
        {"freq_mhz": 300.0, "coupling_db": -25.5},
        {"freq_mhz": 400.0, "coupling_db": -23.0},
        {"freq_mhz": 500.0, "coupling_db": -20.5},
    ]
    table_path, result = _calibrate_ok(tmp_path, points)
    assert result["points"] == 5
    payload = json.loads(table_path.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["points"] == 5
    assert sorted(payload["table"], key=lambda p: p["freq_mhz"]) == [
        {"freq_mhz": p["freq_mhz"], "coupling_db": p["coupling_db"]} for p in points
    ]
    # 往返：读表扣除，命中 300 MHz 测点
    out = calibrate_leakage(
        request={"table_path": str(table_path), "measured_db": -42.25, "freq_mhz": 300.0}
    )
    assert out["mode"] == "subtract"
    assert out["coupling_db"] == pytest.approx(-25.5)
    assert out["corrected_db"] == pytest.approx(-42.25 + -25.5)
    assert out["extrapolated"] is False


def test_leak_calibration_insufficient_points_warns_but_writes_table(tmp_path):
    """<3 点抛 CalibrationWarn，但表仍写出且标注 insufficient。"""
    table_path = tmp_path / "thin_table.json"
    points = [
        {"freq_mhz": 100.0, "coupling_db": -30.0},
        {"freq_mhz": 200.0, "coupling_db": -28.0},
    ]
    with pytest.raises(CalibrationWarn):
        calibrate_leakage(session_data={"points": points, "out_path": str(table_path)})
    assert table_path.is_file()
    payload = json.loads(table_path.read_text(encoding="utf-8"))
    assert payload["status"] == "insufficient"
    assert payload["points"] == 2


def test_leak_calibration_nan_coupling_rejected(tmp_path):
    """NaN 耦合值非法 -> ValueError，且不写表。"""
    table_path = tmp_path / "bad_nan.json"
    with pytest.raises(ValueError, match="有限"):
        calibrate_leakage(
            session_data={
                "points": [
                    {"freq_mhz": 100.0, "coupling_db": -30.0},
                    {"freq_mhz": 200.0, "coupling_db": float("nan")},
                ],
                "out_path": str(table_path),
            }
        )
    assert not table_path.exists()


def test_leak_calibration_bool_coupling_rejected(tmp_path):
    """bool 耦合值（bool 是 int 子类，须显式拒绝）-> ValueError。"""
    with pytest.raises(ValueError, match="数值"):
        calibrate_leakage(
            session_data={
                "points": [
                    {"freq_mhz": 100.0, "coupling_db": True},
                    {"freq_mhz": 200.0, "coupling_db": -28.0},
                    {"freq_mhz": 300.0, "coupling_db": -25.0},
                ],
                "out_path": str(tmp_path / "bad_bool.json"),
            }
        )


def test_leak_calibration_interpolation_midpoint_exact(tmp_path):
    """插值中点：10MHz=-20dB 与 20MHz=-10dB 的中点 15MHz 恰为 -15dB。"""
    table_path, _ = _calibrate_ok(
        tmp_path,
        [
            {"freq_mhz": 10.0, "coupling_db": -20.0},
            {"freq_mhz": 20.0, "coupling_db": -10.0},
            {"freq_mhz": 30.0, "coupling_db": -5.0},
        ],
        name="mid_table.json",
    )
    out = calibrate_leakage(
        request={"table_path": str(table_path), "measured_db": -5.0, "freq_mhz": 15.0}
    )
    assert out["coupling_db"] == -15.0
    assert out["corrected_db"] == -20.0
    assert out["extrapolated"] is False


def test_leak_calibration_extrapolates_with_nearest_endpoint(tmp_path):
    """表外频点（低于下界/高于上界）extrapolated=True 且取最近端点耦合值。"""
    table_path, _ = _calibrate_ok(
        tmp_path,
        [
            {"freq_mhz": 100.0, "coupling_db": -30.0},
            {"freq_mhz": 200.0, "coupling_db": -20.0},
            {"freq_mhz": 300.0, "coupling_db": -10.0},
        ],
        name="extrap_table.json",
    )
    low = calibrate_leakage(
        request={"table_path": str(table_path), "measured_db": -7.0, "freq_mhz": 40.0}
    )
    assert low["extrapolated"] is True
    assert low["coupling_db"] == -30.0
    assert low["corrected_db"] == pytest.approx(-37.0)
    high = calibrate_leakage(
        request={"table_path": str(table_path), "measured_db": -7.0, "freq_mhz": 900.0}
    )
    assert high["extrapolated"] is True
    assert high["coupling_db"] == -10.0
    assert high["corrected_db"] == pytest.approx(-17.0)


def test_leak_calibration_missing_table_returns_none_noted(tmp_path):
    """表缺失：不抛异常，返回 corrected_db=None 并附未扣除标注。"""
    missing = tmp_path / "no_such_table.json"
    out = calibrate_leakage(
        request={"table_path": str(missing), "measured_db": -33.0, "freq_mhz": 150.0}
    )
    assert out["mode"] == "subtract"
    assert out["corrected_db"] is None
    assert out["note"] == "未扣除（无标定表）"
    assert "coupling_db" not in out


def test_leak_calibration_no_arguments_valueerror():
    """两模式都为 None -> ValueError。"""
    with pytest.raises(ValueError, match="session_data"):
        calibrate_leakage()


def test_leak_calibration_duplicate_freq_rejected(tmp_path):
    """频点重复 -> ValueError。"""
    with pytest.raises(ValueError, match="重复"):
        calibrate_leakage(
            session_data={
                "points": [
                    {"freq_mhz": 100.0, "coupling_db": -30.0},
                    {"freq_mhz": 100.0, "coupling_db": -29.0},
                    {"freq_mhz": 200.0, "coupling_db": -20.0},
                ],
                "out_path": str(tmp_path / "dup.json"),
            }
        )


def test_leak_calibration_nonpositive_freq_rejected(tmp_path):
    """频点 <=0 -> ValueError。"""
    with pytest.raises(ValueError, match="大于 0"):
        calibrate_leakage(
            session_data={
                "points": [
                    {"freq_mhz": 0.0, "coupling_db": -30.0},
                    {"freq_mhz": 100.0, "coupling_db": -25.0},
                    {"freq_mhz": 200.0, "coupling_db": -20.0},
                ],
                "out_path": str(tmp_path / "zero_freq.json"),
            }
        )


# ---------------------------------------------------------------------------
# B2 对抗审查缺陷回归（高#4/#7）
# ---------------------------------------------------------------------------

_VALID_THREE_POINTS = [
    {"freq_mhz": 100.0, "coupling_db": -30.0},
    {"freq_mhz": 200.0, "coupling_db": -20.0},
    {"freq_mhz": 300.0, "coupling_db": -10.0},
]


def test_defect_b2_huge_int_coupling_valueerror(tmp_path):
    """高#4：10**400 耦合值 → ValueError（保持声明通道，文案注明超大数值），不抛 OverflowError、不落表。"""
    table_path = tmp_path / "huge.json"
    with pytest.raises(ValueError, match="超大") as excinfo:
        calibrate_leakage(
            session_data={
                "points": [
                    {"freq_mhz": 100.0, "coupling_db": -30.0},
                    {"freq_mhz": 200.0, "coupling_db": 10**400},
                    {"freq_mhz": 300.0, "coupling_db": -20.0},
                ],
                "out_path": str(table_path),
            }
        )
    assert "有限" in str(excinfo.value)  # 与既有有限数值文案口径一致
    assert not table_path.exists()


def test_defect_b2_huge_int_freq_and_measured_valueerror(tmp_path):
    """高#4 同族：10**400 频点（会话模式）与 10**400 measured_db（扣除请求）→ ValueError，不抛 OverflowError。"""
    with pytest.raises(ValueError):
        calibrate_leakage(
            session_data={
                "points": [
                    {"freq_mhz": 10**400, "coupling_db": -30.0},
                    {"freq_mhz": 200.0, "coupling_db": -20.0},
                    {"freq_mhz": 300.0, "coupling_db": -10.0},
                ],
                "out_path": str(tmp_path / "huge_freq.json"),
            }
        )
    with pytest.raises(ValueError):
        calibrate_leakage(
            request={
                "table_path": str(tmp_path / "no_such.json"),
                "measured_db": 10**400,
                "freq_mhz": 150.0,
            }
        )


def test_defect_b2_session_out_path_directory_valueerror(tmp_path):
    """高#7：会话模式 out_path 指向已存在目录 → ValueError（文案含路径），而非裸 IsADirectoryError。"""
    out_dir = tmp_path / "adir"
    out_dir.mkdir()
    with pytest.raises(ValueError) as excinfo:
        calibrate_leakage(
            session_data={"points": _VALID_THREE_POINTS, "out_path": str(out_dir)}
        )
    assert str(out_dir) in str(excinfo.value)
