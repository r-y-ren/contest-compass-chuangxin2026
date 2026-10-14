"""sim 交付态数据面硬判据测试族（走查环 F2/F3/F4 修复验收，2026-10-14）：
真跑一个 record:true 最小 sim 场景（run_scenario 无头入口——与操控台缺省
runner 同一执行管线），断言四条硬判据：

① monitor.csv 数据行 > 0（SimBackend 静默态底噪块——采集窗在发射窗外也有
   数据；旧口径「sim monitor.csv 恒空」作废，见 batches/requirements 申报行）；
② SigMF 录音 data 文件字节数 > 0 且 meta core:num_samples > 0（旧口径 0 字节
   空录音作废——AI 训练/回放数据面在 sim 交付态可达）；
③ report.md 三元曲线段无「缺帧」标注且 curves_data.json 开窗各档有判据样本
   （kpi 行主机单调钟盖戳+gb 判据窗样本重追加——旧口径图A/图B 空帧作废）；
④ demo_sitl_bridge 对该运行输出非空映射（PER-功率台阶可提取——SITL 门在
   sim 交付态可达）。

用例名统一 ``test_sim_delivery_`` 前缀（`pytest -k sim_delivery` 发现）。
"""
import csv
import json
import os

import pytest

from src.demo_sitl_bridge.demo_sitl_bridge import demo_sitl_bridge
from src.run_demo.run_demo import run_scenario

#: record:true 最小 sim 场景（gb42590 快路径+dwell 100ms——功率档事件 int 毫秒
#: 戳可分辨，判据窗样本逐档归位）。
_SCENARIO = {
    "style": "tone",
    "fs": 1.0e6,
    "freq_hz": 2.4e9,
    "power_dbm": -10.0,
    "duration_s": 0.005,
    "backend": "sim",
    "judge_per_threshold": 0.10,
    "scenario_type": "gb42590",
    "judge_min_samples": 2,
    "dwell_s": 0.1,
    "baseline_samples": 10,
    "record": True,
    "bands": [[2400.0, 2483.5]],
    "shielded_box": True,
    "dut_scope": "self_built",
}


@pytest.fixture(scope="module")
def delivered_run(tmp_path_factory):
    """真跑一次 record:true 场景（模块级复用——sim 秒级快路径），返回
    (report_root, run_dir)。"""
    root = tmp_path_factory.mktemp("sim_delivery")
    result = run_scenario(dict(_SCENARIO), out_root=str(root))
    assert result["status"] == "completed" and result["exit_code"] == 0
    return str(root), result["run_dir"]


def test_sim_delivery_monitor_csv_has_data_rows(delivered_run):
    """① 监测路：monitor.csv 数据行 > 0（表头外有 bin 行——静默态底噪块兑现
    「发射窗外采集窗也有数据」，旧恒空口径作废）。"""
    _, run_dir = delivered_run
    with open(os.path.join(run_dir, "monitor.csv"), newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0][:1] == ["timestamp_ms"]  # 表头在位
    assert len(rows) - 1 > 0  # 数据行 > 0（硬判据①）
    assert all(len(row) == 4 and row[3] == "ok" for row in rows[1:100])  # bin 行四列口径


def test_sim_delivery_sigmf_recording_nonempty(delivered_run):
    """② 录制路：SigMF data 字节数 > 0 且 core:num_samples > 0（流式 tee 收到
    非空 IQ 块——旧 0 字节空录音口径作废，AI 训练/回放数据面可达）。"""
    _, run_dir = delivered_run
    rec_dir = os.path.join(run_dir, "recordings")
    metas = sorted(n for n in os.listdir(rec_dir) if n.endswith(".sigmf-meta"))
    assert metas, "recordings/ 无 .sigmf-meta（录制未落盘）"
    meta_path = os.path.join(rec_dir, metas[0])
    data_path = meta_path[: -len(".sigmf-meta")] + ".sigmf-data"
    assert os.path.getsize(data_path) > 0  # 硬判据②a：data 非零字节
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    assert meta["global"]["core:num_samples"] > 0  # 硬判据②b：样本数 > 0


def test_sim_delivery_report_curves_windows_have_samples(delivered_run):
    """③ 报告曲线：report.md 三元曲线段无「缺帧」标注 + curves_data.json 各
    power_step 窗均有判据样本（window_sizes 全 > 0）且 missing==[]——开窗有
    样本（旧「图A/图B 空帧：no_judged_windows」口径作废）。"""
    _, run_dir = delivered_run
    with open(os.path.join(run_dir, "report.md"), encoding="utf-8") as fh:
        report = fh.read()
    assert "缺帧" not in report  # 硬判据③a：无缺帧标注
    with open(os.path.join(run_dir, "plots", "curves_data.json"), encoding="utf-8") as fh:
        curves = json.load(fh)
    frame_a = curves["frames"]["frame_a"]
    assert frame_a["x"], "无 power_step 窗（场景执行异常）"
    assert all(size > 0 for size in frame_a["window_sizes"])  # 硬判据③b：各窗有样本
    assert curves["plot"]["missing"] == []
    assert curves["plot"]["partial"] is False  # 三帧齐备可绘（≥2 可绘点）


def test_sim_delivery_sitl_bridge_nonempty_mapping(delivered_run):
    """④ SITL 桥：demo_sitl_bridge 对该运行输出非空映射（PER-功率台阶表可
    提取+丢包/时延注入表非空——旧「sim 下无运行可过门」口径作废）。"""
    root, run_dir = delivered_run
    view = demo_sitl_bridge(os.path.basename(run_dir.rstrip(os.sep)), root)
    assert view["ok"] is True
    assert view["n_steps"] > 0  # 硬判据④a：台阶表非空
    assert view["injections"]  # 硬判据④b：注入参数映射非空


def test_sim_delivery_kpi_rows_host_monotonic_clock(delivered_run):
    """配套判据：kpi.csv 行 ts 为主机单调毫秒域（>1e6，非旧仿真钟 0/100/…）
    ——与 power_step 事件钟同域（开窗/对齐可相交的根因修复）。行序=写入序
    （采集段行在前、gb 判据窗重追补行在后，判据行 ts 早于采集行属预期——
    build_curve_frames 内部按 ts 排序开窗，不依赖文件行序）。"""
    _, run_dir = delivered_run
    with open(os.path.join(run_dir, "kpi.csv"), newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "kpi.csv 无数据行"
    ts_values = [float(row["timestamp_ms"]) for row in rows]
    assert all(ts > 1e6 for ts in ts_values)  # 主机单调域（运行时长毫秒级巨值）
    assert sorted(ts_values)  # 全体可排序（数值在位）且两段共存（判据+采集）
    assert min(ts_values) < max(ts_values)
