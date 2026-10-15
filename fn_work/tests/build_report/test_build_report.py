"""build_report 对抗测试（R45 顶层，slug=report_builder）：完整数据各节+脚注口径、
返回路径、缺数据文件缺项标注、无失效数据跳段、无模型未识别、PNG 齐备复用不重绘
（mock 不调用）、EMC 段引用行嵌入、数字全部可回查数据文件（虚构检测）、频点
图谱位直传/缺省占位、模型在位识别、全空目录缺项、result/路径形状错拒绝、
上下文字段缺→未记录、失效对比段整段引用块（聚合值口径行）、注入字段消毒
（换行折叠/竖线转义）、emc 非 dict 不附 simulated_parts；
EMC 三流程分节（R89，经 render_emc_flow_section 分发）：flow 标签
conduction/radiation/sweep 各节标题与表体、sweep 标签优先于 readings 形状
（映射层 flow 标签依赖下一任务 _report_payload 改造补齐）；simulated_parts
防御回退随 emc.flow 出三流程段名（I-2——脚注与正文标题一致）。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import src.build_report.build_report as build_report_module
from src.build_report.build_report import build_report
from src.shared.make_disclaimer_block import make_disclaimer_block

KPI_HEADER = "timestamp_ms,link,source,per,judge_per,rssi_dbm,retries,per_note"
MONITOR_HEADER = "timestamp_ms,freq_mhz,power_db,confidence"
PNG_NAMES = (
    "curve_a_per_vs_level.png",
    "curve_b_throughput_vs_per.png",
    "curve_c_event_timeline.png",
)


def _write_full_run(run_dir: Path) -> None:
    """完整三路数据夹具：两窗 KPI + 两档事件 + 两失效条目 + 两频点监测。"""
    (run_dir / "kpi.csv").write_text(
        KPI_HEADER + "\n150,downlink,sim,0.08,0.10,-62.5,0,\n350,downlink,sim,0.29,0.30,-63.0,1,\n",
        encoding="utf-8",
    )
    events = [
        {"type": "power_step", "ts_ms": 100, "step": 0, "target_db": -10.0},
        {"type": "power_step", "ts_ms": 300, "step": 1, "target_db": -5.0},
        {
            "type": "failure_level",
            "ts_ms": 320,
            "step": 1,
            "style": "tone",
            "failure_level_db": -5.0,
            "freq_mhz": 2412.5,
        },
        {
            "type": "failure_level",
            "ts_ms": 340,
            "step": 0,
            "style": "pulse",
            "failure_level_db": -3.0,
            "freq_mhz": 5760.0,
        },
    ]
    (run_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
        encoding="utf-8",
    )
    (run_dir / "monitor.csv").write_text(
        MONITOR_HEADER + "\n1000,2412.5,-62.5,0.90\n1100,5760.0,-58.0,0.85\n",
        encoding="utf-8",
    )


def _full_result() -> dict:
    return {
        "run_id": "RUN-07",
        "backend": "sim",
        "clock_ref": "monotonic",
        "failure_levels": [
            {
                "step": 1,
                "ts_ms": 320,
                "style": "tone",
                "failure_level_db": -5.0,
                "freq_mhz": 2412.5,
            },
            {
                "step": 0,
                "ts_ms": 340,
                "style": "pulse",
                "failure_level_db": -3.0,
                "freq_mhz": 5760.0,
            },
        ],
    }


def _emc_result() -> dict:
    return {
        "readings": [
            {
                "freq_hz": 150000.0,
                "power_dbm": -57.0,
                "power_dbuv": 50.0,
                "margin_db": 10.0,
                "rbw_hz": 9000.0,
            },
            {
                "freq_hz": 500000.0,
                "power_dbm": -60.0,
                "power_dbuv": 47.0,
                "margin_db": 13.0,
                "rbw_hz": 9000.0,
            },
        ],
        "detector": "peak",
        "passed": True,
        "simulated": True,
        "disclaimer": make_disclaimer_block("emc"),
        "conversion_note": (
            "功率换算口径：dBµV = dBm + 107（50Ω：0 dBm = 1 mW ≈ 223.6 mV = 107 dBµV）"
        ),
        "compliance_note": "passed 口径：全部频点裕量非负——演示口径，非认证符合性判定",
    }


def test_report_builder_full_data_sections_and_footnote(tmp_path):
    """① 完整数据：report.md 存在，各节标题齐备，脚注含 GB 42590+PER 声明。"""
    _write_full_run(tmp_path)
    path = build_report(str(tmp_path), _full_result())
    text = Path(path).read_text(encoding="utf-8")

    assert Path(path).is_file()
    for heading in (
        "# Run Report",
        "## 运行概要",
        "## 三元曲线",
        "## 失效电平对比",
        "## 样式识别",
        "## 频点图谱位",
        "## 缺项汇总",
        "## 口径声明（脚注）",
    ):
        assert heading in text, f"缺节标题: {heading}"
    assert "## EMC 传导摸底（模拟）" not in text  # 无 emc 键不嵌段
    assert "GB 42590" in text  # 脚注全局口径块
    assert "PER（分组差错率）" in text  # per_basis=True → BER→PER 声明句
    for name in PNG_NAMES:
        assert (tmp_path / "plots" / name).is_file()  # 三 PNG 落盘
    assert "sim" in text and "monotonic" in text and "RUN-07" in text


def test_report_builder_returns_report_path(tmp_path):
    """② 返回路径恰为 run_dir/report.md（os.path.join 口径）。"""
    _write_full_run(tmp_path)
    path = build_report(str(tmp_path), _full_result())
    assert path == os.path.join(str(tmp_path), "report.md")
    assert Path(path).is_file()


def test_report_builder_missing_kpi_marked_missing(tmp_path):
    """③ 缺 kpi.csv：概要行缺项+缺项汇总列出，不虚构 KPI 行。"""
    (tmp_path / "events.jsonl").write_text(
        '{"type": "power_step", "ts_ms": 100, "step": 0, "target_db": -10.0}\n',
        encoding="utf-8",
    )
    (tmp_path / "monitor.csv").write_text(
        MONITOR_HEADER + "\n1000,2412.5,-62.5,0.90\n", encoding="utf-8"
    )
    path = build_report(str(tmp_path), {"failure_levels": []})
    text = Path(path).read_text(encoding="utf-8")

    assert "| kpi.csv | 缺项（文件不存在） |" in text
    assert "kpi.csv（数据文件不存在" in text  # 缺项汇总清单


def test_report_builder_empty_failure_levels_skips_section(tmp_path):
    """④ failure_levels 空→跳段标「无失效数据」，不出现对比表。"""
    _write_full_run(tmp_path)
    result = _full_result()
    result["failure_levels"] = []
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    assert "无失效数据" in text
    assert "失效电平中位数" not in text  # 无对比表/结论数字


def test_report_builder_no_model_unrecognized_note(tmp_path):
    """⑤ models/style_classifier.json 不存在→段标「未识别（无模型）」。"""
    _write_full_run(tmp_path)
    text = Path(build_report(str(tmp_path), _full_result())).read_text(encoding="utf-8")

    assert "未识别（无模型）" in text
    assert "识别样式：" not in text


def test_report_builder_reuses_existing_pngs_without_replot(tmp_path, monkeypatch):
    """⑥ plots/ 三 PNG 已存在→复用不重绘（mock plot 断言不调用）。"""
    _write_full_run(tmp_path)
    plots = tmp_path / "plots"
    plots.mkdir()
    for name in PNG_NAMES:
        (plots / name).write_bytes(b"\x89PNG\r\n\x1a\n")

    calls: list = []

    def _boom(*args, **kwargs):
        calls.append(1)
        raise AssertionError("三 PNG 已齐备——不应重绘")

    monkeypatch.setattr(build_report_module, "plot_triple_curves", _boom)

    path = build_report(str(tmp_path), _full_result())
    text = Path(path).read_text(encoding="utf-8")

    assert calls == []
    assert "复用" in text
    for name in PNG_NAMES:
        assert f"plots/{name}" in text


def test_report_builder_embeds_emc_section_quoted(tmp_path):
    """⑦ result 含 'emc' 键→EMC 段嵌入：读数引用行+模拟口径+脚注 emc 级声明。"""
    _write_full_run(tmp_path)
    result = _full_result()
    result["emc"] = _emc_result()
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    assert "## EMC 传导摸底（模拟）" in text
    assert "> 150000.0 Hz | -57.0 dBm | 50.0 dBµV | 10.0 dB" in text
    assert "> passed：合规（演示口径，非认证）" in text
    assert "CISPR 16-1-1" in text  # simulated_parts→脚注 emc 级声明块


def test_report_builder_all_numbers_traceable_to_data_files(tmp_path):
    """⑧ 数字纪律：报告电平/频点数字在数据文件原文可查，无虚构数字。"""
    _write_full_run(tmp_path)
    text = Path(build_report(str(tmp_path), _full_result())).read_text(encoding="utf-8")
    events_text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    monitor_text = (tmp_path / "monitor.csv").read_text(encoding="utf-8")

    assert "-5.0 dB" in text and "-5.0" in events_text
    assert "-3.0 dB" in text and "-3.0" in events_text
    assert "2412.5 MHz" in text and "2412.5" in monitor_text
    assert "5760.0 MHz" in text and "5760.0" in monitor_text
    assert "99.9" not in text  # 虚构检测：不得出现数据文件外的电平数字


def test_report_builder_only_kpi_marks_other_files_missing(tmp_path):
    """⑨ 仅 kpi.csv：events/monitor 缺项汇总列出，频点段标 monitor 缺。"""
    (tmp_path / "kpi.csv").write_text(
        KPI_HEADER + "\n150,downlink,sim,0.08,0.10,-62.5,0,\n", encoding="utf-8"
    )
    text = Path(build_report(str(tmp_path), {"failure_levels": []})).read_text(
        encoding="utf-8"
    )

    assert "events.jsonl（数据文件不存在" in text
    assert "monitor.csv（数据文件不存在" in text
    assert "缺项：monitor.csv 不存在——无频点统计。" in text


def test_report_builder_freq_plots_passthrough_satisfied(tmp_path):
    """⑩ result['freq_plots'] 直传：5 位全在→实有 5/需 5+满足，不计缺。"""
    _write_full_run(tmp_path)
    keys = ["ch2412", "ch2437", "ch2462", "ch2484", "band58_monitor"]
    result = _full_result()
    result["freq_plots"] = {"freq_mhz": keys, "images": {k: True for k in keys}}
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    assert "图谱位：实有 5/需 5" in text
    assert "满足 ≥5 频点图谱位要求" in text
    assert "result['freq_plots'] 直传" in text
    assert "频点图谱位（缺" not in text  # 满足不计缺项


def test_report_builder_default_freq_placeholder_deficit(tmp_path):
    """⑪ 未给 freq_plots→缺省占位口径+monitor 实测频点如实计缺。"""
    _write_full_run(tmp_path)
    text = Path(build_report(str(tmp_path), _full_result())).read_text(encoding="utf-8")

    assert "一期频点按 2.4G/5.8G 实有频点如实标注" in text
    assert "实有频点（monitor.csv 读回，2 个）：2412.5 MHz、5760.0 MHz" in text
    assert "缺 5 个频点图" in text  # 未登记图谱→如实计缺
    assert "频点图谱位（缺 5 个频点图" in text  # 进缺项汇总


def test_report_builder_with_model_recognizes_tone(tmp_path):
    """⑫ 模型在位+cnn_dummy→识别段出标签/置信度/模型版本。"""
    _write_full_run(tmp_path)
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "style_classifier.json").write_text(
        json.dumps({"kind": "cnn_dummy"}), encoding="utf-8"
    )
    result = _full_result()
    result["iq_source"] = [1 + 0j] * 512  # 恒包络单音段
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    assert "识别样式：tone" in text
    assert "cnn_dummy-dummy" in text
    assert "未识别（无模型）" not in text


def test_report_builder_no_data_at_all_marks_missing(tmp_path):
    """⑬ 全空 run_dir：报告仍产出，三数据文件/曲线/频点位如实标缺项。"""
    text = Path(build_report(str(tmp_path), {})).read_text(encoding="utf-8")

    assert (tmp_path / "report.md").is_file()
    for name in ("kpi.csv", "events.jsonl", "monitor.csv"):
        assert f"{name}（数据文件不存在" in text
    assert "三元曲线（绘图失败" in text  # 三路全空→CurvesError 被段内缺项吸收
    assert "缺 5 个频点图" in text
    assert "未识别（无模型）" in text


def test_report_builder_non_dict_result_rejected(tmp_path):
    """⑭ result 非 dict → ValueError。"""
    for bad in (None, ["not-a-dict"], "run"):
        with pytest.raises(ValueError, match="result"):
            build_report(str(tmp_path), bad)


def test_report_builder_bad_run_dir_type_rejected(tmp_path):
    """⑮ run_dir 非 str/PathLike → ValueError。"""
    with pytest.raises(ValueError, match="run_dir"):
        build_report(123, {})


def test_report_builder_unrecorded_context_fields(tmp_path):
    """⑯ result 缺 backend/clock_ref/run_id→概要与脚注补「未记录」（不虚构）。"""
    _write_full_run(tmp_path)
    text = Path(build_report(str(tmp_path), {"failure_levels": []})).read_text(
        encoding="utf-8"
    )

    assert text.count("未记录") >= 3  # 概要三行+脚注三行
    assert "> 报告上下文：后端 = 未记录" in text
    assert "> 报告上下文：时钟基准 = 未记录" in text


def test_report_builder_failure_table_styles_and_weakest(tmp_path):
    """⑰ 失效对比表：两样式行数值可查+结论定位最薄弱样式/频点。"""
    _write_full_run(tmp_path)
    text = Path(build_report(str(tmp_path), _full_result())).read_text(encoding="utf-8")

    assert "| tone | -5.0 dB | 1 | -5.0 dB | -5.0 dB |" in text
    assert "| pulse | -3.0 dB | 1 | -3.0 dB | -3.0 dB |" in text
    assert "最薄弱样式为 tone" in text
    assert "最薄弱频点为 2412.5 MHz" in text


def test_report_builder_failure_section_quoted_as_caliber_block(tmp_path):
    """⑰b 失效对比段整段引用块（B18 中#7）：表行与结论行均 '> ' 前缀——
    中位数等聚合值呈现在口径行（R46 白名单覆盖），不再以正文测量行形态
    出现（防聚合值自噬）。"""
    _write_full_run(tmp_path)
    text = Path(build_report(str(tmp_path), _full_result())).read_text(encoding="utf-8")

    assert "> | 样式 | 失效电平中位数 (dB) | 有效条目数（按条目计） | 最小 (dB) | 最大 (dB) |" in text
    assert "> | tone | -5.0 dB | 1 | -5.0 dB | -5.0 dB |" in text
    assert "> 结论：跨样式对比（按失效电平中位数升序）" in text
    bare = [ln for ln in text.splitlines() if ln.startswith("| tone ") or ln.startswith("结论：")]
    assert bare == []  # 无未引用的裸表行/裸结论行


def test_report_builder_injected_context_fields_sanitized(tmp_path):
    """⑱ 注入消毒（B18 中#8/#9）：backend/run_id 含 '\\n' 或 '|' → 概要表
    单元格折叠 ' / ' + 转义 '\\|'（表格结构不破），脚注引用块逐行 '> '。"""
    _write_full_run(tmp_path)
    result = _full_result()
    result["backend"] = "sim\nreplay"
    result["run_id"] = "RUN|07\nX"
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    # 概要表：单元格消毒后仍是完整表格行（无注入换行/裸竖线分列）
    assert "| 后端 | sim / replay |" in text
    assert "| 运行标识 | RUN\\|07 / X |" in text
    assert "\nreplay |" not in text
    assert "sim\nreplay" not in text
    # 标题同样消毒（换行不注入新行）
    assert "# Run Report（RUN\\|07 / X）" in text
    # 脚注引用块：多行值逐行 '> '，无裸行逃逸
    assert "> 报告上下文：后端 = sim" in text.split("\n")
    assert "> replay" in text.split("\n")
    assert "> 报告上下文：运行标识 = RUN\\|07" in text.split("\n")
    assert "> X" in text.split("\n")
    footnote_zone = text.split("## 口径声明（脚注）")[1]
    body_lines = [
        ln for ln in footnote_zone.split("\n") if ln.strip() and not ln.startswith("#")
    ]
    assert all(ln.startswith(">") for ln in body_lines), "脚注区出现非引用行"


def test_report_builder_emc_non_dict_no_simulated_parts(tmp_path):
    """⑲ emc 形状防御（B18 低#15）：result['emc'] 非 dict → EMC 缺项段仍在
    （R89 起标题不含具体流程——形状不可知），但不据此附 simulated_parts
    （脚注无 emc 级声明/CISPR 16-1-1 句）。"""
    _write_full_run(tmp_path)
    result = _full_result()
    result["emc"] = "not-a-dict"
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    assert "## EMC 摸底（模拟）" in text
    assert "形状异常（非 dict）" in text
    assert "emc（result['emc'] 非 dict——EMC 段缺项）" in text  # 进缺项汇总
    assert "CISPR 16-1-1" not in text  # 无模拟段 → 不拼 emc 级声明块


def test_report_builder_emc_text_injection_does_not_break_quote_table(tmp_path):
    """⑲b EMC 文本注入消毒（B18 中#8/#9）：detector/读数含换行竖线 → 折叠
    ' / '+转义，EMC 引用表/引用行结构不被破坏。"""
    _write_full_run(tmp_path)
    result = _full_result()
    result["emc"] = {
        "readings": [
            {
                "freq_hz": "150000.0\nINJ",
                "power_dbm": "-57.0|x",
                "power_dbuv": 50.0,
                "margin_db": 10.0,
            }
        ],
        "detector": "peak\navg",
        "passed": True,
        "simulated": True,
    }
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    assert "> 150000.0 / INJ Hz | -57.0\\|x dBm | 50.0 dBµV | 10.0 dB" in text
    assert "> 检波器：peak" in text.split("\n")
    assert "> avg" in text.split("\n")  # 多行值逐行补 '> '（保持引用块）
    emc_zone = text.split("## EMC 传导摸底（模拟）")[1].split("\n\n")[0]
    quoted = [ln for ln in emc_zone.split("\n") if ln.strip()]
    assert all(ln.startswith(">") for ln in quoted), "EMC 段出现非引用行"


# --------------------------------------------- EMC 三流程分节（R89 分发器） ----


def test_report_builder_emc_flow_conduction_section(tmp_path):
    """⑳ flow='conduction'+readings 形状→「EMC 传导摸底（模拟）」标题与裕量表行
    （分发器经 build_report 入口整链嵌入——标签显式命定传导子渲染器）。"""
    _write_full_run(tmp_path)
    result = _full_result()
    result["emc"] = {"flow": "conduction", **_emc_result()}
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    assert "## EMC 传导摸底（模拟）" in text
    assert "> 频点 (Hz) | 读数 (dBm) | 换算 (dBµV) | 裕量 (dB)" in text
    assert "> 150000.0 Hz | -57.0 dBm | 50.0 dBµV | 10.0 dB" in text
    assert "## EMC 辐射摸底（模拟）" not in text
    assert "## EMC 步进扫频（模拟）" not in text
    assert "CISPR 16-1-1" in text  # dict 形状 → simulated_parts → emc 级声明


def test_report_builder_emc_flow_radiation_section(tmp_path):
    """㉑ flow='radiation'+spectrum/cleanliness 形状→「EMC 辐射摸底（模拟）」+
    谱图表行+洁净度三指标+补偿区（脚注 emc 级声明同附）。"""
    _write_full_run(tmp_path)
    result = _full_result()
    result["emc"] = {
        "flow": "radiation",
        "spectrum": {"freqs": [1.0e6, 2.0e6], "power_db": [-56.2, -70.1]},
        "cleanliness": {
            "in_band_peaks": 2,
            "out_of_band_ratio_db": -23.4,
            "peak_threshold_db": -62.2,
            "criterion": "简单阈值判据（演示口径）：示例判据文字",
        },
        "compensated": True,
        "compensation_note": "补偿表有贡献（示例）",
        "uncertainty_db": 0.5,
        "simulated": True,
    }
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    assert "## EMC 辐射摸底（模拟）" in text
    assert "> 频点 (Hz) | 功率 (dB)" in text
    assert "> 1000000.0 Hz | -56.2 dB" in text
    assert "> 带内峰簇数（in_band_peaks）：2" in text
    assert "> 带外杂散比（out_of_band_ratio_db）：-23.4 dB" in text
    assert "> 补偿：已补偿（compensated=True）" in text
    assert "## EMC 传导摸底（模拟）" not in text
    assert "CISPR 16-1-1" in text


def test_report_builder_emc_flow_sweep_label_section(tmp_path):
    """㉒ flow='sweep'+points（并带映射层 readings←points 适配键）→「EMC 步进
    扫频（模拟）」+扫频点表+n_points；标签优先于 readings 形状回推。

    依赖序申明：现有 run_demo._report_payload 对 sweep 结果只附 readings←points
    适配、不带 flow 标签——分发器形状回推会误判 conduction（已知口径缝）。本测
    以带 flow='sweep' 标签的 payload 验证标签优先；映射层补 flow 标签归下一任务
    _report_payload 改造。"""
    _write_full_run(tmp_path)
    result = _full_result()
    points = [
        {"freq_hz": 1.0e6, "power_dbm": -95.5},
        {"freq_hz": 2.0e6, "power_dbm": -98.0, "spurious": True},
    ]
    result["emc"] = {
        "flow": "sweep",
        "points": points,
        "readings": points,  # 现有映射形状（readings←points 适配）并立在场
        "n_points": 2,
        "simulated": True,
    }
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    assert "## EMC 步进扫频（模拟）" in text
    assert "> 频点 (Hz) | 读数 (dBm) | spurious" in text
    assert "> 1000000.0 Hz | -95.5 dBm | -" in text
    assert "> 2000000.0 Hz | -98.0 dBm | True" in text
    assert "> 扫频点总数（n_points）：2" in text
    # 标签优先：虽带 readings 形状，不落传导表头/裕量列（修正扫频误挂传导的瑕疵）
    assert "## EMC 传导摸底（模拟）" not in text
    assert "换算 (dBµV)" not in text


def test_report_builder_emc_flow_missing_section_title_generic(tmp_path):
    """㉓ result['emc'] 非 dict（list 形）→缺项段标题「EMC 摸底（模拟）」不含
    具体流程（形状不可知）+不附 simulated_parts（回归 B18 低#15 口径）。"""
    _write_full_run(tmp_path)
    result = _full_result()
    result["emc"] = ["not", "a", "dict"]
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    assert "## EMC 摸底（模拟）" in text
    assert "> 缺项：result['emc'] 形状异常（非 dict）——不虚构读数。" in text
    assert "## EMC 传导摸底（模拟）" not in text
    assert "emc（result['emc'] 非 dict——EMC 段缺项）" in text  # 进缺项汇总
    assert "CISPR 16-1-1" not in text  # 不据此附 simulated_parts/emc 级声明


def test_report_builder_simulated_parts_fallback_follows_flow(tmp_path):
    """㉔ I-2 回归：payload 无 simulated_parts+emc flow='radiation' → 脚注
    防御回退随流程出「EMC 辐射摸底段」（与正文标题一致），不误称「传导摸底段」
    （旧回退恒传导段名——radiation/sweep 场景脚注与标题自相矛盾）。"""
    _write_full_run(tmp_path)
    result = _full_result()
    result["emc"] = {
        "flow": "radiation",
        "spectrum": {"freqs": [1.0e6, 2.0e6], "power_db": [-56.2, -70.1]},
        "compensated": True,
        "simulated": True,
    }
    text = Path(build_report(str(tmp_path), result)).read_text(encoding="utf-8")

    assert "## EMC 辐射摸底（模拟）" in text  # 正文标题=辐射
    assert "报告涉及模拟段：EMC 辐射摸底段" in text  # 脚注回退随 flow
    assert "传导摸底段" not in text  # 不误称传导（旧回退缺陷）
    assert "CISPR 16-1-1" in text  # dict 形状 → emc 级声明照附
