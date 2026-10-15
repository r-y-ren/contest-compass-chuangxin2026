"""render_emc_flow_section 三叶子渲染测试（R89）：传导/辐射/扫频分节断言——
正常形状全要素（标题/表行/引言/simulated 行逐字）、缺项分支（readings/points/
spectrum 空）、注记/warnings/disclaimer/spurious/超限截断注记、消毒分支（换行
折叠与 '|' 转义不破表）。分发器与映射层归 R89 快速通道改造点，另测覆盖。"""
from __future__ import annotations

from src.render_emc_flow_section.render_emc_flow_section import (
    _RADIATION_MAX_ROWS,
    _emc_conduction_md,
    _emc_radiation_md,
    _emc_sweep_md,
)

INTRO = "> 本段读数全部由模拟后端产生（simulated 读数），非 CISPR 16-1-1 测量接收机实测值。"
TAIL = "> simulated = True（本段全部读数带模拟标记）"


# ---------------------------------------------------------------- 传导 ----


def test_conduction_full_shape_verbatim() -> None:
    """正常形状全要素：标题/引言/表行（含 margin None）/检波器/passed/四注记/
    warnings/disclaimer/simulated 行——与期望全文逐字相等（行为等价迁移口径）。"""
    emc = {
        "readings": [
            {
                "freq_hz": 150000.0,
                "power_dbm": -42.5,
                "power_dbuv": 64.5,
                "margin_db": 15.5,
            },
            {"freq_hz": 500000.0, "power_dbm": -48.0, "power_dbuv": 59.0},
        ],
        "detector": "QP",
        "passed": True,
        "compliance_note": "合规注记",
        "limit_note": "限值注记",
        "reading_note": "读数注记",
        "conversion_note": "换算注记",
        "warnings": ["警告一"],
        "disclaimer": "> EMC 摸底段口径：示例",
        "simulated": True,
    }
    expected = "\n".join(
        [
            "## EMC 传导摸底（模拟）",
            "",
            INTRO,
            "> 频点 (Hz) | 读数 (dBm) | 换算 (dBµV) | 裕量 (dB)",
            "> 150000.0 Hz | -42.5 dBm | 64.5 dBµV | 15.5 dB",
            "> 500000.0 Hz | -48.0 dBm | 59.0 dBµV | 未判定（未提供限值线）",
            "> 检波器：QP",
            "> passed：合规（演示口径，非认证）",
            "> 合规注记",
            "> 限值注记",
            "> 读数注记",
            "> 换算注记",
            "> 警告一",
            "> EMC 摸底段口径：示例",
            TAIL,
        ]
    )
    assert _emc_conduction_md(emc) == expected


def test_conduction_empty_readings_missing_branch() -> None:
    """缺项分支：readings 空（[]与非 list 同口径）→缺项行，不出现表头。"""
    text = _emc_conduction_md({"readings": [], "passed": None})
    assert "> 缺项：无读数（readings 为空）——不虚构。" in text
    assert "频点 (Hz)" not in text
    assert "> passed：未判定（未提供限值线）" in text
    assert TAIL in text
    text_no_key = _emc_conduction_md({})
    assert "> 缺项：无读数（readings 为空）——不虚构。" in text_no_key


def test_conduction_passed_verdicts_and_multiline_detector() -> None:
    """passed False→不合规；检波器多行逐行引用；非 dict 读数行跳过不虚构。"""
    emc = {
        "readings": [
            {"freq_hz": 1.0e6, "power_dbm": -30.0, "power_dbuv": 77.0, "margin_db": -2.0},
            "非 dict 读数",
        ],
        "detector": "QP\nAVG",
        "passed": False,
    }
    text = _emc_conduction_md(emc)
    assert "> 1000000.0 Hz | -30.0 dBm | 77.0 dBµV | -2.0 dB" in text
    assert "> 检波器：QP" in text
    assert "> AVG" in text
    assert "> passed：不合规（演示口径，非认证）" in text
    assert "非 dict 读数" not in text


def test_conduction_sanitization_newline_and_pipe() -> None:
    """消毒分支：单元格 '|' 转义、换行折叠 ' / '——表结构不被注入破坏。"""
    emc = {
        "readings": [
            {"freq_hz": "150\n000", "power_dbm": "x|y", "power_dbuv": 64.5}
        ],
        "reading_note": "注记\n第二行",
    }
    text = _emc_conduction_md(emc)
    assert "> 150 / 000 Hz | x\\|y dBm | 64.5 dBµV | 未判定（未提供限值线）" in text
    assert "> 注记\n第二行" not in text  # 换行不逃出：逐行引用而非原文内嵌
    assert "> 注记" in text and "> 第二行" in text


# ---------------------------------------------------------------- 辐射 ----


def test_radiation_full_shape_verbatim() -> None:
    """正常形状全要素：谱图表（上限内不截断）/洁净度三指标+criterion/补偿区
    （布尔+note+不确定度+置信度逐键）/warnings/disclaimer——与期望全文逐字相等。"""
    emc = {
        "spectrum": {"freqs": [1.0e6, 2.0e6, 3.0e6], "power_db": [-56.2, -70.1, -64.4]},
        "compensated": True,
        "cleanliness": {
            "in_band_peaks": 2,
            "out_of_band_ratio_db": -23.4,
            "peak_threshold_db": -62.2,
            "criterion": "简单阈值判据（演示口径）：示例判据文字",
        },
        "compensation_note": "补偿表有贡献（示例）",
        "uncertainty_db": 0.5,
        "compensation_confidence": {"ok": 2, "extrapolated": 1, "no_table": 0},
        "warnings": ["辐射警告"],
        "disclaimer": "> EMC 摸底段口径：示例",
        "simulated": True,
    }
    expected = "\n".join(
        [
            "## EMC 辐射摸底（模拟）",
            "",
            INTRO,
            "> 频点 (Hz) | 功率 (dB)",
            "> 1000000.0 Hz | -56.2 dB",
            "> 2000000.0 Hz | -70.1 dB",
            "> 3000000.0 Hz | -64.4 dB",
            "> 带内峰簇数（in_band_peaks）：2",
            "> 带外杂散比（out_of_band_ratio_db）：-23.4 dB",
            "> 峰判定阈值（peak_threshold_db）：-62.2 dB",
            "> 简单阈值判据（演示口径）：示例判据文字",
            "> 补偿：已补偿（compensated=True）",
            "> 补偿表有贡献（示例）",
            "> 谱不确定度（uncertainty_db）：0.5 dB",
            "> 补偿置信度（ok）：2",
            "> 补偿置信度（extrapolated）：1",
            "> 补偿置信度（no_table）：0",
            "> 辐射警告",
            "> EMC 摸底段口径：示例",
            TAIL,
        ]
    )
    assert _emc_radiation_md(emc) == expected


def test_radiation_truncation_note() -> None:
    """超限截断注记：bin 数超 _RADIATION_MAX_ROWS → 列前 N 行+全谱去向注明，
    超出 bin 不出现（不静默全列，也不虚构）。"""
    total = _RADIATION_MAX_ROWS + 4
    emc = {
        "spectrum": {
            "freqs": [1.0e6 * (i + 1) for i in range(total)],
            "power_db": [-60.0 - i for i in range(total)],
        },
        "compensated": False,
    }
    text = _emc_radiation_md(emc)
    assert (
        f"> 谱 bin 共 {total} 行，此处列前 {_RADIATION_MAX_ROWS} 行"
        "——全谱见 result.json（不静默截断）" in text
    )
    row_lines = [line for line in text.splitlines() if line.startswith("> ") and " Hz | " in line]
    assert len(row_lines) == _RADIATION_MAX_ROWS
    assert f"> {1.0e6 * _RADIATION_MAX_ROWS:.1f} Hz" in row_lines[-1]
    for i in range(_RADIATION_MAX_ROWS, total):
        assert f"{1.0e6 * (i + 1):.1f} Hz" not in text


def test_radiation_missing_spectrum_and_cleanliness() -> None:
    """缺项分支：spectrum 缺/空与 cleanliness 缺→缺项行；未补偿布尔+note 如实。"""
    emc = {
        "compensated": False,
        "compensation_note": "表为空——未补偿（示例）",
    }
    expected = "\n".join(
        [
            "## EMC 辐射摸底（模拟）",
            "",
            INTRO,
            "> 缺项：无谱数据（spectrum 缺失或为空）——不虚构。",
            "> 缺项：无洁净度结论（cleanliness 缺失或形状异常）——不虚构。",
            "> 补偿：未补偿（compensated=False）",
            "> 表为空——未补偿（示例）",
            TAIL,
        ]
    )
    assert _emc_radiation_md(emc) == expected
    empty_spectrum_text = _emc_radiation_md({"spectrum": {"freqs": [], "power_db": []}})
    assert "> 缺项：无谱数据（spectrum 缺失或为空）——不虚构。" in empty_spectrum_text


def test_radiation_sanitization_and_missing_metric() -> None:
    """消毒分支：频点含 '|' 转义、指标值含换行折叠；指标缺值→未记录（不虚构）。"""
    emc = {
        "spectrum": {"freqs": ["2.4\nG", "5.8|G"], "power_db": [-55.0, -66.0]},
        "cleanliness": {"in_band_peaks": "3|4\n5", "criterion": "判据\n第二段"},
    }
    text = _emc_radiation_md(emc)
    assert "> 2.4 / G Hz | -55.0 dB" in text
    assert "> 5.8\\|G Hz | -66.0 dB" in text
    assert "> 带内峰簇数（in_band_peaks）：3\\|4 / 5" in text
    assert "> 带外杂散比（out_of_band_ratio_db）：未记录" in text
    assert "> 判据" in text and "> 第二段" in text


# ---------------------------------------------------------------- 扫频 ----


def test_sweep_full_shape_verbatim() -> None:
    """正常形状全要素：点表（spurious 有则标注值、无则 '-'）/n_points 总数行/
    warnings/disclaimer——与期望全文逐字相等。"""
    emc = {
        "points": [
            {"freq_hz": 1.0e6, "power_dbm": -95.5},
            {"freq_hz": 2.0e6, "power_dbm": -98.0, "spurious": True},
            {"freq_hz": 3.0e6, "power_dbm": -101.2},
        ],
        "n_points": 3,
        "warnings": ["扫频警告"],
        "disclaimer": "> EMC 摸底段口径：示例",
        "simulated": True,
    }
    expected = "\n".join(
        [
            "## EMC 步进扫频（模拟）",
            "",
            INTRO,
            "> 频点 (Hz) | 读数 (dBm) | spurious",
            "> 1000000.0 Hz | -95.5 dBm | -",
            "> 2000000.0 Hz | -98.0 dBm | True",
            "> 3000000.0 Hz | -101.2 dBm | -",
            "> 扫频点总数（n_points）：3",
            "> 扫频警告",
            "> EMC 摸底段口径：示例",
            TAIL,
        ]
    )
    assert _emc_sweep_md(emc) == expected


def test_sweep_empty_points_missing_branch() -> None:
    """缺项分支：points 空（[]与非 list 同口径）→缺项行，不出表头与总数行。"""
    text = _emc_sweep_md({"points": [], "n_points": 0})
    assert "> 缺项：无扫频点（points 为空）——不虚构。" in text
    assert "频点 (Hz)" not in text
    assert "n_points" not in text
    assert TAIL in text
    text_no_key = _emc_sweep_md({})
    assert "> 缺项：无扫频点（points 为空）——不虚构。" in text_no_key


def test_sweep_sanitization_and_missing_n_points() -> None:
    """消毒分支：读数含 '|' 转义、频点含换行折叠；n_points 缺→未记录（不虚构）。"""
    emc = {
        "points": [
            {"freq_hz": "1.5\ne6", "power_dbm": "a|b", "spurious": True},
        ],
    }
    text = _emc_sweep_md(emc)
    assert "> 1.5 / e6 Hz | a\\|b dBm | True" in text
    assert "> 扫频点总数（n_points）：未记录" in text
