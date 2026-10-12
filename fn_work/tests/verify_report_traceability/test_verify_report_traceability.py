"""verify_report_traceability 对抗测试（R46 顶层，slug=report_traceability）：
全可溯 passed、虚构数字（手改 99.9 dBm）检出、脚注引用行/判据·阈值·目标行
contextual 白名单、float 等价（数据 0.300 报告 0.3 / 定点 .2f 变体）、空报告
0 数字 passed、报告不存在/为目录拒绝、run_dir 不存在/为文件拒绝、输出键集合
恰为五键、traced+contextual+mismatch 混合计数、无数据文件全差异、build_report
生成报告全回路 passed。"""
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
def test_report_traceability_criterion_keyword_lines_contextual(tmp_path, line):
    """④ 判据/阈值/目标行数字→contextual（平台常量非本 run 数据）。"""
    _write_run_files(tmp_path)
    report = _write_report(tmp_path, line + "\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_contextual"] == 1
    assert result["mismatches"] == []
    assert result["passed"] is True


def test_report_traceability_float_equivalence_trailing_zeros(tmp_path):
    """⑤ float 等价：数据原文 0.300，报告写 0.3 → 候选串 .3f 命中可溯。"""
    (tmp_path / "events.jsonl").write_text(
        '{"type": "power_step", "ts_ms": 100, "step": 0, "target_db": 0.300}\n',
        encoding="utf-8",
    )
    report = _write_report(tmp_path, "电平 0.3 dB\n")
    result = verify_report_traceability(report, str(tmp_path))

    assert result["n_traced"] == 1
    assert result["passed"] is True


def test_report_traceability_round_variant_traced(tmp_path):
    """⑥ 定点变体：数据 2412.50，报告 2412.5 → 候选串 .2f 命中可溯。"""
    (tmp_path / "monitor.csv").write_text(
        MONITOR_HEADER + "\n1000,2412.50,-62.5,0.90\n", encoding="utf-8"
    )
    report = _write_report(tmp_path, "监测频点 2412.5 MHz\n")
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
    """⑮ 全回路：build_report 生成的完整报告→溯源校验 passed（数字纪律闭环）。"""
    _write_full_run(tmp_path)
    report = build_report(str(tmp_path), _full_result())
    result = verify_report_traceability(report, str(tmp_path))

    assert result["passed"] is True
    assert result["mismatches"] == []
    assert result["n_traced"] >= 5  # 对比表+结论+频点段数字均可溯
