"""record_run_streams 对抗用例：B12 顶层（三路采集编排，验收 slug=align_streams）。

全 mock/lines/sim 注入 + 一例真 SimBackend 端到端（无真实硬件）：监测路假后端
read_samples 遵真实契约（list[块 dict]，耗尽恒 []——与 SimBackend/B210Backend
同构），另以真 open_sim_backend（start_tx 喂两块再采集）锚死后端契约防再漂移；
DUT 路以 sim 事件流或 esp32 lines 行流注入，run_dir 用 pytest tmp_path。

口径锚点：
- kpi.csv 表头精确（timestamp_ms,link,source,per,judge_per,rssi_dbm,retries,
  per_note），行数 = sim 事件数 × samples_per_event（DUT/监测 1:1 交错不影响
  DUT 总产出——单路耗尽后继续 drain 另一路）；
- monitor.csv bin 行四列（timestamp_ms,freq_mhz,power_db,confidence），统计行
  另存 monitor_stats.jsonl（逐行可 json.loads）；
- 对齐：kpi/monitor 样本钟由注入 ts 控制——sim 仿真钟 0/100/…ms，监测块 ts
  60/160/…ms，事件 ts_ms 50/150/…ms → kpi 时延恒 50ms、监测时延恒 10ms，
  ≥5 对 → P50 有限且精确可断言；
- 安全铁律：LinkError（esp32 lines 坏帧超阈）/ BackendError（监测路断流）→
  backend.stop_tx 先于异常透传被调用（drive 内停 + 编排层幂等不重复实停）；
- 协作停惰性：停检在每路拉取之间——两块后置 flag 则 read_samples 恰调 2 次。
"""
import json
import math
import os
import time

import pytest

from src.drive_esp32_link.drive_esp32_link import LinkError
from src.manage_backend_registry.register_backend import BackendError
from src.open_sim_backend.open_sim_backend import open_sim_backend
from src.record_run_streams.record_run_streams import record_run_streams

KPI_HEADER_LINE = "timestamp_ms,link,source,per,judge_per,rssi_dbm,retries,per_note"
MONITOR_HEADER_LINE = "timestamp_ms,freq_mhz,power_db,confidence"
RESULT_KEYS = {
    "kpi_rows",
    "monitor_blocks",
    "stats_rows",
    "alignment",
    "recording",
    "streams_note",
}
ALIGNMENT_KEYS = {
    "pairs",
    "kpi_delay_p50_ms",
    "kpi_delay_p95_ms",
    "monitor_delay_p50_ms",
    "monitor_delay_p95_ms",
    "kpi_delay_note",
    "monitor_delay_note",
    "n_events",
    "n_paired_kpi",
    "n_paired_monitor",
    "unpaired_events",
}
MONITOR_PARAMS = {"target_band": (2400.0, 2440.0), "nfft": 64, "max_bins": 4}


class FakeMonitorBackend:
    """监测路假后端：一次性块列表 + read_samples 调用计数 + 停发射日志。

    read_samples 遵真实后端契约（SimBackend/B210Backend 同构）：返回 list[块 dict]
    （无数据恒 []）——与 sim/B210 的轮询式块弹出口径一致，防 mock 契约漂移。
    """

    def __init__(self, blocks=None, on_read=None):
        self._blocks = list(blocks or [])
        self._on_read = on_read
        self.log = []
        self.read_calls = 0

    def read_samples(self, max_blocks: int = 1):
        self.read_calls += 1
        self.log.append("read")
        if self._on_read is not None:
            self._on_read(self)
        if self._blocks:
            return [self._blocks.pop(0)]
        return []

    def stop_tx(self):
        self.log.append("stop_tx")
        return {"status": "stopped"}

    def set_tx_gain(self, gain):
        self.log.append(f"set_tx_gain:{gain}")
        return {"status": "stopped"}


class FailingBackend:
    """第 2 次 read_samples 起 BackendError（监测路断流注入，真实 list 契约）。"""

    def __init__(self, blocks):
        self._blocks = list(blocks)
        self.log = []
        self.read_calls = 0

    def read_samples(self, max_blocks: int = 1):
        self.read_calls += 1
        if self.read_calls == 1 and self._blocks:
            return [self._blocks.pop(0)]
        raise BackendError("rx stream lost")

    def stop_tx(self):
        self.log.append("stop_tx")
        return {"status": "stopped"}

    def set_tx_gain(self, gain):
        self.log.append("set_tx_gain")
        return {"status": "stopped"}


class StopAfterFrames:
    """esp32 lines 行流：出 n 帧后置协作停 flag 并耗尽（StopIteration）。"""

    def __init__(self, n_frames, stop):
        self._n_frames = n_frames
        self._i = 0
        self._stop = stop

    def __iter__(self):
        return self

    def __next__(self):
        if self._i >= self._n_frames:
            self._stop["flag"] = True  # DUT 拉取内协作停：此后不得再读监测块
            raise StopIteration
        self._i += 1
        return f"ESP,{self._i},{self._i * 10},{self._i - 1},0,-55"


def iq_block(ts, n=8, seed=0):
    """监测原始 IQ 块：n 个复样本 + 块时间戳 ts（ms）。"""
    return {
        "samples": [complex(seed + 0.1 * i, -0.05 * i) for i in range(n)],
        "ts": float(ts),
    }


def sim_events(n, jsr=6.0):
    """sim 注入事件流（jsr_db 直给口径）。"""
    return [{"type": "power_step", "jsr_db": jsr, "ts": i} for i in range(n)]


def jam_events(n, first=50, step=100):
    """对齐共享事件（ts_ms 口径，compute_alignment_error 消费形状）。"""
    return [{"ts_ms": first + step * i, "type": "power_step"} for i in range(n)]


def endless_esp_frames():
    i = 0
    while True:
        i += 1
        yield f"ESP,{i},{i * 10},{i - 1},0,-55"


def make_ctx(
    run_dir,
    backend,
    dut=None,
    monitor_params=None,
    sim_events_src=None,
    jam=None,
    record=False,
    stop=None,
    reference=None,
    events_sink=None,
    facts=None,
):
    ctx = {
        "run_dir": str(run_dir),
        "backend": backend,
        "scenario": {"style": "noise", "freq_mhz": 2420.0, "signal_power_db": -20.0},
        "dut": dut if dut is not None else {"source": "sim"},
        "monitor": monitor_params if monitor_params is not None else dict(MONITOR_PARAMS),
        "record": record,
    }
    if sim_events_src is not None:
        ctx["sim_events"] = sim_events_src
    if jam is not None:
        ctx["jam_events"] = jam
    if stop is not None:
        ctx["stop"] = stop
    if reference is not None:
        ctx["reference"] = reference
    if events_sink is not None:
        ctx["events_sink"] = events_sink
    if facts is not None:
        ctx["facts"] = facts
    return ctx


def read_lines(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read().splitlines()


# ---------------------------------------------------------------------------
# ① sim 事件流：kpi.csv 行数 = 事件 × samples_per_event；对齐 P50 有限精确
# ---------------------------------------------------------------------------
def test_align_streams_sim_events_kpi_rows_and_alignment_p50_finite(tmp_path):
    backend = FakeMonitorBackend([iq_block(60 + 100 * i, seed=i) for i in range(9)])
    ctx = make_ctx(
        tmp_path,
        backend,
        sim_events_src=sim_events(6),
        jam=jam_events(6),
        dut={"source": "sim", "samples_per_event": 3},
    )
    result = record_run_streams(ctx)

    # kpi.csv：1 表头 + 6 事件 × 3 样本 = 19 行；link/source 均为 sim
    kpi_lines = read_lines(os.path.join(str(tmp_path), "kpi.csv"))
    assert len(kpi_lines) == 1 + 6 * 3
    assert result["kpi_rows"] == 6 * 3
    body = kpi_lines[1].split(",")
    assert body[1] == "sim" and body[2] == "sim"
    float(body[3])  # per 数值在位

    assert result["monitor_blocks"] == 9
    assert result["stats_rows"] == 9

    # 对齐：事件 ts 50..550，kpi 样本钟 0/100/…，监测块钟 60/160/…
    # → kpi 时延恒 50ms、监测时延恒 10ms；6 对 ≥5 → P50 有限
    alignment = result["alignment"]
    assert alignment["n_events"] == 6
    assert alignment["n_paired_kpi"] == 6
    assert alignment["n_paired_monitor"] == 6
    assert alignment["unpaired_events"] == []
    assert alignment["kpi_delay_p50_ms"] == pytest.approx(50.0)
    assert alignment["kpi_delay_p95_ms"] == pytest.approx(50.0)
    assert alignment["monitor_delay_p50_ms"] == pytest.approx(10.0)
    assert alignment["monitor_delay_p95_ms"] == pytest.approx(10.0)
    assert alignment["kpi_delay_note"] is None
    assert alignment["monitor_delay_note"] is None


# ---------------------------------------------------------------------------
# ② 监测 mock 流（read_samples 出 2 块）：monitor_blocks=2 + 统计行 + bin 四列
# ---------------------------------------------------------------------------
def test_align_streams_monitor_mock_two_blocks_stats_and_bin_columns(tmp_path):
    backend = FakeMonitorBackend([iq_block(60), iq_block(160, seed=1)])
    ctx = make_ctx(
        tmp_path,
        backend,
        sim_events_src=sim_events(2),
        dut={"source": "sim", "samples_per_event": 2},
    )
    result = record_run_streams(ctx)

    assert set(result) == RESULT_KEYS
    assert result["monitor_blocks"] == 2
    assert result["kpi_rows"] == 4

    # monitor.csv：表头 + 2 块 × max_bins=4 行，每行恰 4 列，confidence 缺省 ok
    import csv as _csv

    with open(os.path.join(str(tmp_path), "monitor.csv"), newline="", encoding="utf-8") as fh:
        rows = list(_csv.reader(fh))
    assert rows[0] == MONITOR_HEADER_LINE.split(",")
    assert len(rows) == 1 + 2 * 4
    for row in rows[1:]:
        assert len(row) == 4
        assert row[3] == "ok"
        float(row[1]) and float(row[2])  # 频点/功率数值在位

    # 统计行另存 monitor_stats.jsonl（不混 bin 行）：2 行可逐行解析
    stats_lines = read_lines(os.path.join(str(tmp_path), "monitor_stats.jsonl"))
    assert len(stats_lines) == 2
    parsed = [json.loads(line) for line in stats_lines]
    assert [row["timestamp_ms"] for row in parsed] == [60.0, 160.0]
    assert all(row["mode"] == "power_only" for row in parsed)  # 无参考 → 底噪口径


# ---------------------------------------------------------------------------
# ③ record=True：recordings/ 下 SigMF 对（num_samples>0）且监测照出（tee 双消费）
# ---------------------------------------------------------------------------
def test_align_streams_record_true_tees_raw_iq_to_sigmf_pair(tmp_path):
    backend = FakeMonitorBackend([iq_block(60), iq_block(160, seed=1)])
    facts = {
        "style": "noise",
        "backend": "simu",
        "freq_hz": 2.42e9,
        "sample_rate": 1e6,
        "run_id": "rec-test",
    }
    ctx = make_ctx(
        tmp_path,
        backend,
        sim_events_src=sim_events(2),
        dut={"source": "sim", "samples_per_event": 2},
        record=True,
        facts=facts,
    )
    result = record_run_streams(ctx)

    # tee 双消费：原始 IQ 进录制（2 块 × 8 样本）且谱/统计照常产出
    recording = result["recording"]
    assert recording is not None
    assert recording["num_samples"] == 2 * 8
    assert recording["bytes_written"] == recording["num_samples"] * 8
    assert result["monitor_blocks"] == 2
    assert result["stats_rows"] == 2

    recordings_dir = os.path.join(str(tmp_path), "recordings")
    names = sorted(os.listdir(recordings_dir))
    assert names == ["rec-test.sigmf-data", "rec-test.sigmf-meta"]
    assert os.path.getsize(recording["data_path"]) == recording["num_samples"] * 8
    with open(recording["meta_path"], encoding="utf-8") as fh:
        meta = json.load(fh)
    assert meta["global"]["core:num_samples"] == recording["num_samples"]
    assert meta["global"]["core:datatype"] == "cf32_le"

    # 监测路未被录制分叉抢占（同流分叉双消费）
    assert len(read_lines(os.path.join(str(tmp_path), "monitor.csv"))) == 1 + 2 * 4


# ---------------------------------------------------------------------------
# ④ record=False：无录制
# ---------------------------------------------------------------------------
def test_align_streams_record_false_writes_no_recording(tmp_path):
    backend = FakeMonitorBackend([iq_block(60)])
    ctx = make_ctx(
        tmp_path, backend, sim_events_src=sim_events(1), dut={"source": "sim"}
    )
    result = record_run_streams(ctx)

    assert result["recording"] is None
    assert not os.path.exists(os.path.join(str(tmp_path), "recordings"))
    assert result["monitor_blocks"] == 1


# ---------------------------------------------------------------------------
# ⑤ stop 协作：三路收尾，返回含 note；记帐事件落 events.jsonl 并镜像 sink
# ---------------------------------------------------------------------------
def test_align_streams_cooperative_stop_drains_and_notes(tmp_path):
    stop = {"flag": False}

    def on_read(backend):
        if backend.read_calls == 2:
            stop["flag"] = True  # 第 2 块读出后协作停：不得再读第 3 块

    backend = FakeMonitorBackend(
        [iq_block(60), iq_block(160, seed=1), iq_block(260, seed=2)], on_read=on_read
    )
    sink = []
    ctx = make_ctx(
        tmp_path,
        backend,
        dut={"source": "esp32", "serial_config": {"source": "lines", "lines": endless_esp_frames()}},
        stop=stop,
        events_sink=sink,
    )
    result = record_run_streams(ctx)

    assert "cooperative_stop" in result["streams_note"]
    assert backend.read_calls == 2
    assert result["kpi_rows"] == 2  # DUT 路 1:1 交错各拉 2 次
    assert result["monitor_blocks"] == 2

    # 记帐事件：events.jsonl 一行 streams_stopped，并镜像 events_sink
    events_lines = read_lines(os.path.join(str(tmp_path), "events.jsonl"))
    assert len(events_lines) == 1
    entry = json.loads(events_lines[0])
    assert entry["type"] == "streams_stopped"
    assert entry["reason"] == "cooperative_stop"
    assert len(sink) == 1 and sink[0]["type"] == "streams_stopped"


# ---------------------------------------------------------------------------
# ⑥ DUT sim 耗尽：'dut_source_exhausted' 注继续，监测路完整收完
# ---------------------------------------------------------------------------
def test_align_streams_dut_sim_exhausted_notes_and_continues(tmp_path):
    backend = FakeMonitorBackend([iq_block(60), iq_block(160, seed=1)])
    ctx = make_ctx(
        tmp_path,
        backend,
        sim_events_src=sim_events(2),
        dut={"source": "sim", "samples_per_event": 2},
    )
    result = record_run_streams(ctx)

    assert "dut_source_exhausted" in result["streams_note"]
    assert result["kpi_rows"] == 2 * 2
    assert result["monitor_blocks"] == 2  # 耗尽后监测路继续收完
    assert result["stats_rows"] == 2


# ---------------------------------------------------------------------------
# ⑦ DUT LinkError（lines 注入坏帧超阈）：先停发射（stop_tx 先于异常）再透传
# ---------------------------------------------------------------------------
def test_align_streams_dut_link_error_stops_tx_before_raise(tmp_path):
    backend = FakeMonitorBackend([iq_block(60)])
    ctx = make_ctx(
        tmp_path,
        backend,
        dut={
            "source": "esp32",
            "serial_config": {"source": "lines", "lines": ["GARBAGE"] * 5},
        },
    )
    with pytest.raises(LinkError):
        record_run_streams(ctx)

    # drive_esp32_link 抛 LinkError 前已实停（异常能传出即停发射已完成）；
    # 编排层同 token 幂等补停 → stop_tx 恰一次；监测路尚未开读
    assert backend.log.count("stop_tx") == 1
    assert "read" not in backend.log
    assert backend.read_calls == 0


# ---------------------------------------------------------------------------
# ⑧ 监测路 BackendError：先停发射再透传（编排层停——sim 路无 drive 内停）
# ---------------------------------------------------------------------------
def test_align_streams_monitor_backend_error_stops_tx_and_reraises(tmp_path):
    backend = FailingBackend([iq_block(60)])
    ctx = make_ctx(
        tmp_path,
        backend,
        sim_events_src=sim_events(4),
        dut={"source": "sim", "samples_per_event": 2},
    )
    with pytest.raises(BackendError):
        record_run_streams(ctx)

    assert backend.log.count("stop_tx") == 1  # 编排层异常路径实停
    # 首块已被处理落盘（异常前已得数据不回滚）
    assert len(read_lines(os.path.join(str(tmp_path), "monitor.csv"))) == 1 + 4


# ---------------------------------------------------------------------------
# ⑨ max_kpi_rows 截断：恰 10000 行，不抛
# ---------------------------------------------------------------------------
def test_align_streams_max_kpi_rows_caps_exactly_without_raise(tmp_path):
    backend = FakeMonitorBackend([iq_block(60)])
    ctx = make_ctx(
        tmp_path,
        backend,
        sim_events_src=sim_events(4000),  # 4000 × 3 = 12000 > 10000
        dut={"source": "sim", "samples_per_event": 3},
    )
    result = record_run_streams(ctx, max_kpi_rows=10000)

    assert result["kpi_rows"] == 10000
    assert "kpi_rows_capped" in result["streams_note"]
    kpi_lines = read_lines(os.path.join(str(tmp_path), "kpi.csv"))
    assert len(kpi_lines) == 1 + 10000


# ---------------------------------------------------------------------------
# ⑩ ctx 形状错拒：ValueError（启动前直抛，不停发射）
# ---------------------------------------------------------------------------
def test_align_streams_ctx_shape_errors_rejected_without_stop(tmp_path):
    backend = FakeMonitorBackend([])
    good = make_ctx(
        tmp_path, backend, sim_events_src=sim_events(1), dut={"source": "sim"}
    )

    with pytest.raises(ValueError):
        record_run_streams("not-a-dict")

    missing_run_dir = dict(good)
    del missing_run_dir["run_dir"]
    with pytest.raises(ValueError, match="run_dir"):
        record_run_streams(missing_run_dir)

    missing_dut = dict(good)
    del missing_dut["dut"]
    with pytest.raises(ValueError, match="dut"):
        record_run_streams(missing_dut)

    bad_source = dict(good)
    bad_source["dut"] = {"source": "zigbee"}
    with pytest.raises(ValueError, match="source"):
        record_run_streams(bad_source)

    no_events = dict(good)
    del no_events["sim_events"]
    with pytest.raises(ValueError, match="sim_events"):
        record_run_streams(no_events)

    no_serial = dict(good)
    no_serial["dut"] = {"source": "esp32"}
    with pytest.raises(ValueError, match="serial_config"):
        record_run_streams(no_serial)

    bad_monitor = dict(good)
    bad_monitor["monitor"] = {}  # 缺 target_band → capture 计划校验 ValueError
    with pytest.raises(ValueError, match="target_band"):
        record_run_streams(bad_monitor)

    with pytest.raises(ValueError, match="max_kpi_rows"):
        record_run_streams(dict(good), max_kpi_rows=0)

    # 形状错在启动前拒绝：不经停发射路径
    assert backend.log == []


# ---------------------------------------------------------------------------
# ⑪ alignment 键集与 None 口径（事件不足 → p50 None + insufficient_pairs）
# ---------------------------------------------------------------------------
def test_align_streams_alignment_keys_and_none_insufficient_calendar(tmp_path):
    backend = FakeMonitorBackend([iq_block(60)])
    ctx = make_ctx(
        tmp_path, backend, sim_events_src=sim_events(1), dut={"source": "sim"}
    )
    result = record_run_streams(ctx)

    alignment = result["alignment"]
    assert set(alignment) == ALIGNMENT_KEYS
    # 无 jam_events/events_sink/events.jsonl → 对齐事件空：分位全 None + 标记
    assert alignment["n_events"] == 0
    assert alignment["pairs"] == []
    assert alignment["unpaired_events"] == []
    for key in (
        "kpi_delay_p50_ms",
        "kpi_delay_p95_ms",
        "monitor_delay_p50_ms",
        "monitor_delay_p95_ms",
    ):
        assert alignment[key] is None
    assert alignment["kpi_delay_note"] == "insufficient_pairs"
    assert alignment["monitor_delay_note"] == "insufficient_pairs"


# ---------------------------------------------------------------------------
# ⑫ kpi.csv 表头精确
# ---------------------------------------------------------------------------
def test_align_streams_kpi_csv_header_exact(tmp_path):
    backend = FakeMonitorBackend([iq_block(60)])
    ctx = make_ctx(
        tmp_path, backend, sim_events_src=sim_events(1), dut={"source": "sim"}
    )
    record_run_streams(ctx)

    first_line = read_lines(os.path.join(str(tmp_path), "kpi.csv"))[0]
    assert first_line == KPI_HEADER_LINE


# ---------------------------------------------------------------------------
# ⑬ stats jsonl 逐行可解析；reference 在位 → full 模式
# ---------------------------------------------------------------------------
def test_align_streams_monitor_stats_jsonl_parseable_modes(tmp_path):
    power_only_dir = tmp_path / "po"
    power_only_dir.mkdir()
    backend = FakeMonitorBackend([iq_block(60), iq_block(160, seed=1)])
    ctx = make_ctx(
        power_only_dir,
        backend,
        sim_events_src=sim_events(2),
        dut={"source": "sim", "samples_per_event": 2},
    )
    record_run_streams(ctx)
    rows = [json.loads(line) for line in read_lines(str(power_only_dir / "monitor_stats.jsonl"))]
    assert len(rows) == 2
    assert all(set(row) >= {"timestamp_ms", "mode", "leak_corrected", "invalid_bins"} for row in rows)
    assert all(row["mode"] == "power_only" for row in rows)
    assert all(row["noise_floor_db"] is not None for row in rows)

    full_dir = tmp_path / "full"
    full_dir.mkdir()
    reference = {
        "signal_band": (2400.0, 2410.0),
        "interference_band": (2430.0, 2440.0),
        "flatness_band": (2405.0, 2415.0),
    }
    full_params = {"target_band": (2400.0, 2440.0), "nfft": 64}
    backend2 = FakeMonitorBackend([iq_block(60)])
    ctx2 = make_ctx(
        full_dir,
        backend2,
        sim_events_src=sim_events(1),
        dut={"source": "sim"},
        monitor_params=full_params,
        reference=reference,
    )
    record_run_streams(ctx2)
    rows2 = [json.loads(line) for line in read_lines(str(full_dir / "monitor_stats.jsonl"))]
    assert len(rows2) == 1
    assert rows2[0]["mode"] == "full"
    assert "snr_db" in rows2[0]


# ---------------------------------------------------------------------------
# ⑭ 两块后 stop → 不读第三块（停检在拉取之间的惰性）
# ---------------------------------------------------------------------------
def test_align_streams_stop_after_two_blocks_is_lazy_no_third_read(tmp_path):
    stop = {"flag": False}
    backend = FakeMonitorBackend(
        [iq_block(60), iq_block(160, seed=1), iq_block(260, seed=2)]
    )
    ctx = make_ctx(
        tmp_path,
        backend,
        dut={
            "source": "esp32",
            "serial_config": {
                "source": "lines",
                "lines": StopAfterFrames(2, stop),  # 第 3 次 DUT 拉取置 flag
            },
        },
        stop=stop,
    )
    result = record_run_streams(ctx)

    assert backend.read_calls == 2  # 第 3 块存在但未被读取（惰性）
    assert result["monitor_blocks"] == 2
    assert result["kpi_rows"] == 2
    assert "cooperative_stop" in result["streams_note"]
    assert "dut_source_exhausted" in result["streams_note"]


# ---------------------------------------------------------------------------
# ⑮ 真 SimBackend 端到端（防后端契约再漂移）：start_tx 喂两块 → 拆包归一采集
# ---------------------------------------------------------------------------
def test_align_streams_real_sim_backend_end_to_end_two_blocks(tmp_path):
    # 真 sim 后端 read_samples 契约：返回 [(samples, meta), ...]（无数据 []）——
    # 编排层须逐块拆包并把 (samples, meta) 元组归一为块 dict，不得整单透传。
    backend = open_sim_backend({"freq_hz": 2.44e9, "sample_rate": 1e6})
    tone = [
        complex(math.cos(2 * math.pi * i / 16), math.sin(2 * math.pi * i / 16))
        for i in range(64)
    ]
    backend.start_tx([tone, list(tone)])  # 喂两块再采集

    events = sim_events(2)
    # 对齐事件用主机单调毫秒域盖戳（B12 中#1：sim 元组块归一 ts 已统一主机域，
    # jam_events 取值口径 ts_ms 优先——事件与监测块同域方可配对）。
    host_jam = [
        {"type": "power_step", "ts_ms": time.monotonic() * 1000.0} for _ in range(2)
    ]
    ctx = make_ctx(
        tmp_path,
        backend,
        sim_events_src=events,
        jam=host_jam,
        dut={"source": "sim", "samples_per_event": 1},
    )
    result = record_run_streams(ctx)

    # 两块全收：谱块/统计行各 2，bin 行 = 表头 + 2 块 × max_bins=4
    assert result["monitor_blocks"] == 2
    assert result["stats_rows"] == 2
    assert result["kpi_rows"] == 2
    assert len(read_lines(os.path.join(str(tmp_path), "monitor.csv"))) == 1 + 2 * 4
    # 源耗尽（空读超阈）自然收尾不抛，注在位
    assert "monitor_source_exhausted" in result["streams_note"]
    # 归一块 ts 为主机单调毫秒盖戳（rx_ts 块号非毫秒域，不再充当时间戳）：
    # 统计行时间戳非负且逐块严格递增（同域毫断言，替代旧 [0,1] 块号错误锚）。
    stats_rows = [
        json.loads(line)
        for line in read_lines(os.path.join(str(tmp_path), "monitor_stats.jsonl"))
    ]
    ts_values = [row["timestamp_ms"] for row in stats_rows]
    assert len(ts_values) == 2
    assert ts_values[0] >= 0 and ts_values[1] > ts_values[0]
    # 对齐腿：主机域事件与主机域监测块可配对（延迟非负有限），不再因单位错位
    # 流尽 unpaired；kpi 腿仍 sim 仿真钟域（配不上属预期，单路未配不进
    # unpaired_events——两路皆流先止才算）。
    alignment = result["alignment"]
    assert alignment["n_events"] == 2
    assert alignment["n_paired_monitor"] == 2
    assert alignment["unpaired_events"] == []
    for pair in alignment["pairs"]:
        assert pair["monitor_delay_ms"] is not None
        assert pair["monitor_delay_ms"] >= 0
        assert math.isfinite(pair["monitor_delay_ms"])
