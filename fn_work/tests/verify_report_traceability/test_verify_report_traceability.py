"""verify_report_traceability 对抗测试（R46 顶层，slug=report_traceability）：
全可溯 passed、虚构数字（手改 99.9 dBm）检出、脚注引用行 contextual 白名单（仅
'>' 行——判据/阈值/目标字样行不再豁免，正文数字一律回查）、数字词界回查（'5.0'
不命中 '15.03'/'0.2' 不命中 '0.25'）、等值候选（整数形态/科学计数双形——无舍入
变体，0.25≠0.2）、空报告 0 数字 passed、报告不存在/为目录拒绝、run_dir 不存在/
为文件拒绝、输出键集合恰为五键、traced+contextual+mismatch 混合计数、无数据文件
全差异、build_report 生成报告全回路 passed（含聚合中位数——引用块口径行覆盖）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.build_report.build_report import build_report
from src.verify_report_traceability.verify_report_traceability import (
    verify_report_traceability,
)

KPI_HEADER = "timestamp_ms,link,source,per,judge_per,rssi_dbm,retries,per_note"
MONITOR_HEADER = "timestamp_ms,freq_mhz,power_db,confidence"


def _write_run_files(
    run_dir: Path,
    *,
    kpi: bool = True,
    events: bool = True,
    monitor: bool = True,
) -> None:
    if kpi:
        (run_dir / "kpi.csv").write_text(
            KPI_HEADER + "\n150,downlink,sim,0.08,0.10,-62.5,0,\n", encoding="utf-8"
        )
    if events:
        (run_dir / "events.jsonl").write_text(
            '{"type": "power_step", "ts_ms": 100, "step": 0, "target_db": -10.0}\n',
            encoding="utf-8",
        )
    if monitor:
        (run_dir / "monitor.csv").write_text(
            MONITOR_HEADER + "\n1000,2412.5,-62.5,0.90\n", encoding="utf-8"
        )


def _write_report(run_dir: Path, text: str) -> str:
    path = run_dir / "report.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _write_full_run(run_dir: Path) -> None:
    """完整三路数据夹具（与 build_report 测试同形：数字均为 float 文本形态）。"""
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


def test_report_traceability_all_traced_passed(tmp_path):
    """① 全可溯：报告数字在数据文件原文同值存在→passed、无差异。"""
    _write_run_files(tmp_path)
    report = _write_report(
        tmp_path, "事件电平 -10.0 dBm（events.jsonl 回查）\n监测频点 2412.5 MHz（monitor.csv 回查）\n"
    )
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_numbers"] == 2
    assert result["n_traced"] == 2
    assert result["n_contextual"] == 0
    assert result["mismatches"] == []
    assert result["passed"] is True


def test_report_traceability_fabricated_number_detected(tmp_path):
    """② 虚构数字：手改 99.9 dBm（数据文件无此值）→检出差异条目。"""
    _write_run_files(tmp_path)
    report = _write_report(tmp_path, "实测功率 99.9 dBm\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["passed"] is False
    assert result["mismatches"] == [
        {
            "value": 99.9,
            "unit": "dBm",
            "line_no": 1,
            "context": "实测功率 99.9 dBm",
        }
    ]


def test_report_traceability_footnote_line_contextual(tmp_path):
    """③ 脚注区（'>' 开头行）数字→contextual，不算差异。"""
    _write_run_files(tmp_path)
    report = _write_report(tmp_path, "> 时钟基准 = 10 MHz（外部参考）\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_contextual"] == 1
    assert result["n_traced"] == 0
    assert result["mismatches"] == []
    assert result["passed"] is True


@pytest.mark.parametrize(
    "line",
    [
        "判据：门限电平 -20.0 dB（平台常量）",
        "阈值：限值 40 dB",
        "目标：目标电平 5 dB 步进",
    ],
)
def test_report_traceability_criterion_keyword_lines_must_trace(tmp_path, line):
    """④ 判据/阈值/目标字样行不再整行豁免（B18 高#2）：正文测量行数字一律
    回查——数据文件无同值 → mismatch（白名单仅 '>' 脚注/引用行）。"""
    _write_run_files(tmp_path)
    report = _write_report(tmp_path, line + "\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_contextual"] == 0
    assert len(result["mismatches"]) == 1
    assert result["mismatches"][0]["unit"] in ("dB",)
    assert result["passed"] is False


def test_report_traceability_criterion_keyword_traced_when_in_data(tmp_path):
    """④b 判据字样行的数字若真实可溯回数据文件 → traced（不因字样豁免也不误杀）。"""
    _write_run_files(tmp_path)
    report = _write_report(tmp_path, "判据：门限电平 -10.0 dB（events.jsonl 回查）\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_traced"] == 1
    assert result["mismatches"] == []
    assert result["passed"] is True


def test_report_traceability_body_target_fabricated_number_detected(tmp_path):
    """④c 正文含「目标」虚构数字（77.7 不在数据文件）→ mismatch（关键词旁路封死）。"""
    _write_run_files(tmp_path)
    report = _write_report(tmp_path, "目标：目标电平 77.7 dB（手改虚构）\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["passed"] is False
    assert result["mismatches"][0]["value"] == 77.7
    assert result["n_contextual"] == 0


def test_report_traceability_word_boundary_blocks_substring_hit(tmp_path):
    """⑤ 数字词界回查（B18 高#1）：数据仅 15.03 时报告 5.0 dB 不算可溯——
    '5.0' 是 '15.03' 的子串但前后有数字，命中被 (?<![\\d.])/(?![\\d.]) 拦下。"""
    (tmp_path / "monitor.csv").write_text(
        MONITOR_HEADER + "\n1000,15.03,-62.5,0.90\n", encoding="utf-8"
    )
    report = _write_report(tmp_path, "电平 5.0 dB\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["passed"] is False
    assert result["mismatches"] == [
        {
            "value": 5.0,
            "unit": "dB",
            "line_no": 1,
            "context": "电平 5.0 dB",
        }
    ]


def test_report_traceability_full_number_still_traced_at_word_boundary(tmp_path):
    """⑤b 数据 15.03、报告 15.03 → 仍 traced（词界只拦子串，不拦全值命中）。"""
    (tmp_path / "monitor.csv").write_text(
        MONITOR_HEADER + "\n1000,15.03,-62.5,0.90\n", encoding="utf-8"
    )
    report = _write_report(tmp_path, "电平 15.03 dB\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_traced"] == 1
    assert result["passed"] is True


def test_report_traceability_round_variant_not_matched(tmp_path):
    """⑥ 舍入候选已去除（B18 中#5）：数据 0.25、报告 0.2 → mismatch（0.2 是
    0.25 的舍入形态而非等值形态——不再因 .1f 变体误判可溯）。"""
    (tmp_path / "events.jsonl").write_text(
        '{"type": "power_step", "ts_ms": 100, "step": 0, "target_db": 0.25}\n',
        encoding="utf-8",
    )
    report = _write_report(tmp_path, "电平 0.2 dB\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["passed"] is False
    assert result["mismatches"][0]["value"] == 0.2


def test_report_traceability_exact_and_integer_forms_traced(tmp_path):
    """⑥b 等值形态仍互认：str(0.3)↔0.3 与整数形态 2412.0↔'2412' 可溯。"""
    (tmp_path / "events.jsonl").write_text(
        '{"type": "power_step", "ts_ms": 100, "step": 0, "target_db": 0.3}\n',
        encoding="utf-8",
    )
    (tmp_path / "monitor.csv").write_text(
        MONITOR_HEADER + "\n1000,2412,-62.5,0.90\n", encoding="utf-8"
    )
    report = _write_report(tmp_path, "电平 0.3 dB；频点 2412 MHz\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_traced"] == 2
    assert result["passed"] is True


def test_report_traceability_trailing_zero_form_not_matched(tmp_path):
    """⑥c 尾零形态不再自动互认（无舍入候选的代价，如实收紧）：数据 0.300、
    报告 0.3 → mismatch（'0.3' 后随 '0' 被词界拦下；数据应写等值原文 0.3）。"""
    (tmp_path / "events.jsonl").write_text(
        '{"type": "power_step", "ts_ms": 100, "step": 0, "target_db": 0.300}\n',
        encoding="utf-8",
    )
    report = _write_report(tmp_path, "电平 0.3 dB\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["passed"] is False
    assert result["mismatches"][0]["value"] == 0.3


@pytest.mark.parametrize(
    "data_text",
    [
        '{"type": "carrier", "freq_hz": 2.4e9}\n',
        '{"type": "carrier", "freq_hz": 2.4E+09}\n',
        '{"type": "carrier", "freq_hz": 2.4e+09}\n',
    ],
)
def test_report_traceability_scientific_forms_traced(tmp_path, data_text):
    """⑦ 科学计数双形互认（B18 中#6）：数据 2.4e9/2.4E+09/2.4e+09，报告
    2.4e9 Hz → 候选集科学计数变体命中可溯。"""
    (tmp_path / "events.jsonl").write_text(data_text, encoding="utf-8")
    report = _write_report(tmp_path, "载波 2.4e9 Hz\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_traced"] == 1
    assert result["passed"] is True


def test_report_traceability_scientific_report_uppercase_traced(tmp_path):
    """⑦b 报告写 2.4E9、数据写 2400000000（整数形态）→ 候选整数形态命中可溯。"""
    (tmp_path / "events.jsonl").write_text(
        '{"type": "carrier", "freq_hz": 2400000000}\n', encoding="utf-8"
    )
    report = _write_report(tmp_path, "载波 2.4E9 Hz\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_traced"] == 1
    assert result["passed"] is True


def test_report_traceability_empty_report_zero_numbers_passed(tmp_path):
    """⑦ 空报告：0 数字、无差异、passed（空集口径）。"""
    _write_run_files(tmp_path)
    report = _write_report(tmp_path, "")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_numbers"] == 0
    assert result["n_traced"] == 0
    assert result["n_contextual"] == 0
    assert result["mismatches"] == []
    assert result["passed"] is True


def test_report_traceability_missing_report_rejected(tmp_path):
    """⑧ 报告不存在 → ValueError。"""
    _write_run_files(tmp_path)
    with pytest.raises(ValueError, match="报告"):
        verify_report_traceability(str(tmp_path / "nope.md"), str(tmp_path))


def test_report_traceability_report_path_is_directory_rejected(tmp_path):
    """⑨ 报告路径是目录 → ValueError。"""
    (tmp_path / "adir").mkdir()
    with pytest.raises(ValueError, match="报告"):
        verify_report_traceability(str(tmp_path / "adir"), str(tmp_path))


def test_report_traceability_missing_run_dir_rejected(tmp_path):
    """⑩ 运行目录不存在 → ValueError。"""
    report = _write_report(tmp_path, "电平 -10.0 dBm\n")
    with pytest.raises(ValueError, match="运行目录"):
        verify_report_traceability(report, str(tmp_path / "gone"))


def test_report_traceability_run_dir_is_file_rejected(tmp_path):
    """⑪ 运行目录路径是文件 → ValueError。"""
    report = _write_report(tmp_path, "电平 -10.0 dBm\n")
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    with pytest.raises(ValueError, match="运行目录"):
        verify_report_traceability(report, str(blocker))


def test_report_traceability_result_key_set_exact(tmp_path):
    """⑫ 输出键集合恰为五键（n_numbers/n_traced/n_contextual/mismatches/passed）。"""
    _write_run_files(tmp_path)
    report = _write_report(tmp_path, "电平 -10.0 dBm\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert set(result) == {
        "n_numbers",
        "n_traced",
        "n_contextual",
        "mismatches",
        "passed",
    }
    assert isinstance(result["passed"], bool)


def test_report_traceability_mixed_counts(tmp_path):
    """⑬ 混合：可溯+口径行+虚构三数字并立→计数三分账、passed False。"""
    _write_run_files(tmp_path)
    report = _write_report(
        tmp_path,
        "电平 -10.0 dB\n> 脚注参考 10 MHz\n功率 88.8 dBm\n",
    )
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_numbers"] == 3
    assert result["n_traced"] == 1
    assert result["n_contextual"] == 1
    assert len(result["mismatches"]) == 1
    assert result["mismatches"][0]["value"] == 88.8
    assert result["passed"] is False


def test_report_traceability_no_data_files_all_mismatch(tmp_path):
    """⑭ run_dir 无任何数据文件：报告数字全部列差异（可回查面如实缩小）。"""
    report = _write_report(tmp_path, "电平 1.5 dB\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_numbers"] == 1
    assert result["n_traced"] == 0
    assert result["mismatches"][0]["value"] == 1.5
    assert result["passed"] is False


def test_report_traceability_generated_report_full_loop(tmp_path):
    """⑮ 全回路：build_report 生成的完整报告→溯源校验 passed（数字纪律闭环）。
    失效对比表+结论已整段引用块化（B18 中#7）→ 频点段数字 traced、对比段
    数字 contextual（口径行），无正文不可溯数字。"""
    _write_full_run(tmp_path)
    report = build_report(str(tmp_path), _full_result())
    result = verify_report_traceability(report, str(tmp_path))

    assert result["passed"] is True
    assert result["mismatches"] == []
    assert result["n_traced"] >= 2  # 频点段 2412.5/5760.0 MHz 可溯
    assert result["n_contextual"] >= 5  # 引用块口径行（对比表+结论+EMC 级常量）


def _write_aggregate_run(run_dir: Path) -> None:
    """聚合夹具：每样式 2 条失效条目——中位数为均值聚合（-6.0/-4.0），
    不以原文形态出现在任何数据文件（专测聚合值自噬修复，B18 中#7）。"""
    (run_dir / "kpi.csv").write_text(
        KPI_HEADER + "\n150,downlink,sim,0.08,0.10,-62.5,0,\n", encoding="utf-8"
    )
    events = [
        {"type": "power_step", "ts_ms": 100, "step": 0, "target_db": -10.0},
        {
            "type": "failure_level", "ts_ms": 320, "step": 1, "style": "tone",
            "failure_level_db": -5.0, "freq_mhz": 2412.5,
        },
        {
            "type": "failure_level", "ts_ms": 340, "step": 1, "style": "tone",
            "failure_level_db": -7.0, "freq_mhz": 2412.5,
        },
        {
            "type": "failure_level", "ts_ms": 360, "step": 0, "style": "pulse",
            "failure_level_db": -3.0, "freq_mhz": 5760.0,
        },
        {
            "type": "failure_level", "ts_ms": 380, "step": 0, "style": "pulse",
            "failure_level_db": -5.0, "freq_mhz": 5760.0,
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


def _aggregate_result() -> dict:
    failure_levels = [
        {
            "step": 1, "ts_ms": 320, "style": "tone",
            "failure_level_db": -5.0, "freq_mhz": 2412.5,
        },
        {
            "step": 1, "ts_ms": 340, "style": "tone",
            "failure_level_db": -7.0, "freq_mhz": 2412.5,
        },
        {
            "step": 0, "ts_ms": 360, "style": "pulse",
            "failure_level_db": -3.0, "freq_mhz": 5760.0,
        },
        {
            "step": 0, "ts_ms": 380, "style": "pulse",
            "failure_level_db": -5.0, "freq_mhz": 5760.0,
        },
    ]
    return {
        "run_id": "RUN-08",
        "backend": "sim",
        "clock_ref": "monotonic",
        "failure_levels": failure_levels,
    }


def test_report_traceability_full_loop_with_aggregate_medians_passed(tmp_path):
    """⑯ 聚合中位数全回路（B18 中#7 回归）：两样式各 2 条 → 中位数 -6.0/-4.0
    为聚合值、不以原文出现在数据文件；build_report 把对比表+结论整段以 '> '
    引用块嵌入（口径行白名单覆盖）→ 全回路 verify passed，无自噬差异。"""
    _write_aggregate_run(tmp_path)
    report = build_report(str(tmp_path), _aggregate_result())
    report_text = Path(report).read_text(encoding="utf-8")
    result = verify_report_traceability(report, str(tmp_path))

    # 报告确含聚合中位数（非数据原文值）且在引用块行上
    assert "> | tone | -6.0 dB | 2 | -7.0 dB | -5.0 dB |" in report_text
    assert "> | pulse | -4.0 dB | 2 | -5.0 dB | -3.0 dB |" in report_text
    assert "> 结论：" in report_text
    for blob_name in ("kpi.csv", "events.jsonl", "monitor.csv"):
        assert "-6.0" not in (tmp_path / blob_name).read_text(encoding="utf-8")

    assert result["passed"] is True
    assert result["mismatches"] == []
    assert result["n_contextual"] >= 2  # 聚合中位数计入口径行而非差异
