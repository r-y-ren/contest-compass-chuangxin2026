"""check_band_whitelist 单元测试——频段白名单纯校验（2.4G/5.8G 法定频段，闭区间）。"""
from src.guard_compliance.check_band_whitelist import BAND_WHITELIST, check_band_whitelist

EXPECTED_WHITELIST = [(2400.0, 2483.5), (5725.0, 5829.0)]


def test_full_2g4_band_passes():
    result = check_band_whitelist({"bands": [(2400.0, 2483.5)]})
    assert result["status"] == "pass"
    assert result["violations"] == []
    assert result["whitelist"] == EXPECTED_WHITELIST
    assert list(BAND_WHITELIST) == EXPECTED_WHITELIST


def test_full_5g8_band_passes():
    result = check_band_whitelist({"bands": [(5725.0, 5829.0)]})
    assert result["status"] == "pass"
    assert result["violations"] == []


def test_below_2g4_lower_bound_violates():
    result = check_band_whitelist({"bands": [(2355.0, 2450.0)]})
    assert result["status"] == "violation"
    assert len(result["violations"]) == 1
    assert result["violations"][0]["band"] == (2355.0, 2450.0)
    assert "白名单" in result["violations"][0]["reason"]


def test_below_5g8_lower_bound_violates():
    result = check_band_whitelist({"bands": [(5700.0, 5800.0)]})
    assert result["status"] == "violation"
    assert len(result["violations"]) == 1
    assert result["violations"][0]["band"] == (5700.0, 5800.0)


def test_band_entirely_outside_whitelist_violates():
    result = check_band_whitelist({"bands": [(900.0, 928.0)]})
    assert result["status"] == "violation"
    assert len(result["violations"]) == 1
    assert result["violations"][0]["band"] == (900.0, 928.0)


def test_mixed_bands_only_bad_one_listed():
    result = check_band_whitelist(
        {"bands": [(2400.0, 2450.0), (900.0, 928.0)]}
    )
    assert result["status"] == "violation"
    assert len(result["violations"]) == 1
    assert result["violations"][0]["band"] == (900.0, 928.0)


def test_whitelist_boundary_values_exactly_pass():
    # 白名单边界值本身合法（闭区间）：起点恰为 2400.0、终点恰为 2483.5 的频段均通过
    result = check_band_whitelist({"bands": [(2400.0, 2450.0), (2450.0, 2483.5)]})
    assert result["status"] == "pass"
    assert result["violations"] == []


def test_empty_bands_is_shape_violation():
    result = check_band_whitelist({"bands": []})
    assert result["status"] == "violation"
    assert len(result["violations"]) == 1
    assert "形状错误" in result["violations"][0]["reason"]
    assert "空" in result["violations"][0]["reason"]


def test_reversed_band_is_shape_violation():
    result = check_band_whitelist({"bands": [(2483.5, 2400.0)]})
    assert result["status"] == "violation"
    assert len(result["violations"]) == 1
    assert result["violations"][0]["band"] == (2483.5, 2400.0)
    assert "逆序" in result["violations"][0]["reason"]
