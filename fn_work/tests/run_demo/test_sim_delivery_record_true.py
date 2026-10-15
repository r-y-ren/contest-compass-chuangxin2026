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

R88 交窗测试族（2026-10-15 追加，tap_tx_window_blocks 装配接线验收）：
⑤ 交窗判据——events.jsonl 首 power_step ts→ladder_stop ts（ts_ms 域）窗内
   monitor.csv 有行，且窗内行承载发射环回内容（功率显著高于底噪口径，非
   synthetic:noise_floor 量级）+ SigMF 首个数据块为发射环回块（块均功率
   dB > -80，底噪 -110dBm 级）；
⑥ 样式可分性——同场景仅改 style（tone vs bandlimited_noise）两轮实跑，各自
   SigMF data 全量 FFT 峰值集中度（峰均比）tone 显著高于 bandlimited_noise
   （相差 >6dB）——录音承载样式调制而非均质底噪；
⑦ 急停/停发射先行不破——本文件无急停用例，由 tests/run_demo 全目录回归
   证明（B24 C1 急停族+tap dwell 分片停检共用 EmergencyStopRequested 路径）。

用例名统一 ``test_sim_delivery_`` 前缀（`pytest -k sim_delivery` 发现）。
"""
import csv
import json
import math
import os

import numpy as np
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


# ---------- R88 交窗测试族（tap_tx_window_blocks 装配接线验收，2026-10-15 追加） ----------

#: 样式可分对照场景：仅改 style（bandlimited_noise 须显式给 bandwidth_hz——
#: load_scenario 带限类样式校验；20kHz=配方缺省带，铺带与单音集中两极对照）。
_SCENARIO_NOISE = {**_SCENARIO, "style": "bandlimited_noise", "bandwidth_hz": 20e3}

#: tone 配方缺省合成点数（switch_style 配方表 tone defaults n_samples=4096）——
#: start_tx([iq]) 单块发射，录音首个环回块长度即此。
_TONE_N_SAMPLES = 4096

#: 底噪判据阈（dB）：SimBackend 静默态底噪 -110dBm（样本均功率 ≈ -140dB 采样
#: 域），块均功率 > -80 即非纯底噪（R88 交窗判据口径）。
_NOT_NOISE_FLOOR_DB = -80.0

#: 窗内外功率分离阈（dB）：发射环回内容对底噪口径的最低可辨间隔。
_WINDOW_POWER_GAP_DB = 20.0

#: 样式可分阈（dB）：tone 对 bandlimited_noise 的 FFT 峰均比差下限。
_STYLE_SEPARABILITY_DB = 6.0


@pytest.fixture(scope="module")
def noise_delivered_run(tmp_path_factory):
    """bandlimited_noise 对照运行（样式可分性判据素材，模块级复用——同
    delivered_run 执行管线，仅 style 不同）。"""
    root = tmp_path_factory.mktemp("sim_delivery_noise")
    result = run_scenario(dict(_SCENARIO_NOISE), out_root=str(root))
    assert result["status"] == "completed" and result["exit_code"] == 0
    return str(root), result["run_dir"]


def _events_of(run_dir):
    """events.jsonl 逐行读回（append_event 严格 JSON，行可信）。"""
    with open(os.path.join(run_dir, "events.jsonl"), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _tx_window_bounds_ts_ms(run_dir):
    """发射窗界（ts_ms 域）：events.jsonl 首个 power_step ts → ladder_stop ts。

    事件 ts 为 append_event 权威盖戳（int 毫秒单调钟）；tap 块 ts 为拉取时刻
    float 毫秒（同域）——窗界即「发射起点→停发射完成」的监测覆盖窗。
    """
    events = _events_of(run_dir)
    steps = [e["ts"] for e in events if e.get("type") == "power_step"]
    stops = [e["ts"] for e in events if e.get("type") == "ladder_stop"]
    assert steps and stops, "power_step/ladder_stop 事件缺失（场景执行异常）"
    return steps[0], stops[0]


def _monitor_rows_of(run_dir):
    with open(os.path.join(run_dir, "monitor.csv"), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _recording_samples(run_dir):
    """SigMF data → complex64 全量样本（cf32_le 小端直读，与 meta datatype 同口径）。"""
    rec_dir = os.path.join(run_dir, "recordings")
    metas = sorted(n for n in os.listdir(rec_dir) if n.endswith(".sigmf-meta"))
    assert metas, "recordings/ 无 .sigmf-meta（录制未落盘）"
    data_path = os.path.join(rec_dir, metas[0][: -len(".sigmf-meta")] + ".sigmf-data")
    samples = np.fromfile(data_path, dtype=np.complex64)
    assert samples.size > 0
    return samples


def _spectral_peak_to_mean_db(samples):
    """全录音 FFT 峰值集中度：10·log10(max|X|² / mean|X|²)（dB）。

    单音能量相干集中于一个 bin（峰均比高）；带限噪声能量铺满带宽内诸 bin
    （峰均比低）——两轮差值即样式可分判据。
    """
    spectrum = np.abs(np.fft.fft(samples)) ** 2
    return 10.0 * math.log10(float(spectrum.max()) / float(spectrum.mean()))


def test_sim_delivery_tx_window_rows_within_power_step_to_ladder_stop(delivered_run):
    """⑤a 交窗判据：monitor.csv 存在 ts 落 [首 power_step ts, ladder_stop ts]
    窗内的行——tap 装配后 dwell 分片拉取的监测块以**拉取时刻**盖戳（发射窗
    内），采集阶段前置消费写入 monitor.csv（旧口径「监测行全部落在发射窗外」
    作废——录音窗自此覆盖发射窗）。"""
    _, run_dir = delivered_run
    lo, hi = _tx_window_bounds_ts_ms(run_dir)
    rows = _monitor_rows_of(run_dir)
    in_window = [
        row for row in rows if lo <= float(row["timestamp_ms"]) <= hi
    ]
    assert in_window, (
        f"monitor.csv 无 ts 落发射窗内的行（窗=[{lo}, {hi}]，"
        f"{len(rows)} 行全体窗外——tap 装配/前置消费未生效）"
    )


def test_sim_delivery_tx_window_rows_carry_tx_loopback_not_noise_floor(delivered_run):
    """⑤b 交窗判据：窗内行/录音首块承载**发射环回内容**（非 synthetic:noise_floor
    量级）——① monitor.csv 窗内行 power_db 最大值 > -80（底噪 -110dBm 口径下
    非纯底噪）；② SigMF 录音首个数据块（前置消费序=发射窗块先行）块均功率
    dB > -80；③ 环回块 vs 底噪 20dB 分离：首块均功率 > 其后全部样本（窗内
    dwell 期底噪块集，-110dBm 级）均功率 + 20dB——若窗内全为底噪块则不可能
    拉开 20dB（归谬旁证）。注：本场景 dwell 期耗尽底噪块预算、采集期窗外无
    行，spec「窗外行对比」形式以录音内「环回块 vs 底噪块集」等效承载。"""
    _, run_dir = delivered_run
    lo, hi = _tx_window_bounds_ts_ms(run_dir)
    rows = _monitor_rows_of(run_dir)
    in_max = max(
        float(row["power_db"])
        for row in rows
        if lo <= float(row["timestamp_ms"]) <= hi
    )
    assert in_max > _NOT_NOISE_FLOOR_DB  # 窗内有非底噪量级内容（发射环回在窗）
    samples = _recording_samples(run_dir)
    first_block = samples[:_TONE_N_SAMPLES]  # 首块=发射窗环回块（tone 4096 点）
    assert first_block.size == _TONE_N_SAMPLES  # 录音不短于一个发射块
    rest = samples[_TONE_N_SAMPLES:]
    first_power_db = 10.0 * math.log10(float(np.mean(np.abs(first_block) ** 2)))
    rest_power_db = 10.0 * math.log10(float(np.mean(np.abs(rest) ** 2)))
    assert first_power_db > _NOT_NOISE_FLOOR_DB  # 首块非纯底噪=环回内容在录
    assert first_power_db > rest_power_db + _WINDOW_POWER_GAP_DB  # 环回 vs 底噪分离


def test_sim_delivery_style_separability_tone_vs_bandlimited_noise(
    delivered_run, noise_delivered_run
):
    """⑥ 样式可分性：同场景仅改 style 两轮实跑，SigMF data 全量 FFT 峰值集中度
    tone 显著高于 bandlimited_noise（差 >6dB）——发射窗内录音承载样式调制
    （单音相干集中 vs 带限噪声铺带），非均质底噪（两轮底噪块同源同量级，差值
    只能来自环回块样式差异）。"""
    tone_papr = _spectral_peak_to_mean_db(_recording_samples(delivered_run[1]))
    noise_papr = _spectral_peak_to_mean_db(_recording_samples(noise_delivered_run[1]))
    assert tone_papr - noise_papr > _STYLE_SEPARABILITY_DB, (
        f"tone 峰均比 {tone_papr:.1f}dB 未显著高于 bandlimited_noise "
        f"{noise_papr:.1f}dB（差 {tone_papr - noise_papr:.1f}dB ≤ 6dB）"
    )
