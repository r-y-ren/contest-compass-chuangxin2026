"""stream_realtime_console 桥测试（无浏览器）：三路帧转换+尾随生命周期+降频+
离线落盘+延迟统计落点，及 serve_console 缺省 runner 挂桥的集成回归。

覆盖口径（R58 L0；帧协议=render_triple_stream_charts 顶部注释约定）：
- 三路转换：kpi.csv 行→kpi 帧 metrics 数值列、monitor.csv 行→spectrum 帧
  （按块时间戳聚合/时间窗聚合）、events.jsonl 行→event 帧 label 摘要（坏行跳过）；
- 尾随生命周期：新运行目录发现（基线外首个）、result.json 出现静默收尾、
  stop 信号即停、目录未出现 discovery_timeout 安静退出、'w' 重写截断自愈；
- 降频（R49 口径）：两连断+广播失败→degraded 置位+间隔升档+后续帧盖标注；
- hub 失联：push 抛出→帧批离线落盘 realtime_offline.jsonl 不中断运行；
- 延迟统计：measure_refresh_latency 口径（行可见→广播发送戳 P50/P95）入
  run_ctx['result']['realtime']（操控台侧缺省 runner 并入运行结果 'realtime' 键）；
- 装配助手 build_realtime_charts 经手叶子（wired：grep render_triple_stream_charts
  调用点在父模块）；serve_console 缺省装配注入三路图区+共享 hub 容器贯通。
"""
import json
import os
import threading
import time

import pytest

from src.stream_realtime_console.render_triple_stream_charts import (
    render_triple_stream_charts,
)
from src.stream_realtime_console.stream_realtime_console import (
    OFFLINE_FILENAME,
    build_realtime_charts,
    stream_realtime_console,
)

try:  # 集成用例同源依赖 fastapi+httpx——缺失即整族 skip
    from fastapi.testclient import TestClient

    _HAS_TESTCLIENT = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_TESTCLIENT = False

needs_fastapi = pytest.mark.skipif(
    not _HAS_TESTCLIENT, reason="环境缺 fastapi/httpx——TestClient 不可用"
)


class FakeSocket:
    """同步 fake WS：send_json 收帧并可选用回执戳流（hub['acks']）写回执。"""

    def __init__(self, hub=None, fail=False, ack_delay_ms=0.0):
        self.frames = []
        self._hub = hub
        self._fail = fail
        self._ack_delay_ms = ack_delay_ms

    def send_json(self, frame):
        if self._fail:
            raise RuntimeError("fake socket down")
        self.frames.append(frame)
        if self._hub is not None and isinstance(frame, dict):
            acked = frame.get("sent_ms")
            if acked is not None:
                self._hub["acks"].append(
                    {"sent_ms": acked, "acked_ms": acked + self._ack_delay_ms}
                )
        return None


def _make_run(root: str, name: str = "20261013-230000") -> str:
    """预建一个含三路空文件（表头态）的运行目录（create_run_workspace 口径）。"""
    run_dir = os.path.join(root, name)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "kpi.csv"), "w", encoding="utf-8") as fh:
        fh.write(
            "timestamp_ms,link,source,per,judge_per,rssi_dbm,retries,per_note\n"
        )
    with open(os.path.join(run_dir, "monitor.csv"), "w", encoding="utf-8") as fh:
        fh.write("timestamp_ms,freq_mhz,power_db,confidence\n")
    open(os.path.join(run_dir, "events.jsonl"), "w", encoding="utf-8").close()
    return run_dir


def _append(path: str, text: str) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()


def _bridge_ctx(root: str, **over) -> dict:
    """最小桥上下文（快轮询/短静默——测试总时长可控）。"""
    ctx = {
        "report_root": root,
        "baseline_runs": set(),
        "result": {},
        "stop": {"flag": False},
        "poll_interval_s": 0.02,
        "quiesce_s": 0.15,
    }
    ctx.update(over)
    return ctx


# ---- 三路帧真实到达（fake hub 全链：发现→尾随→push→帧形状） ----


def test_bridge_follows_run_and_pushes_three_streams(tmp_path):
    """① 新运行目录被尾随：kpi/monitor/events 三路增量各转帧经 push 到达
    订阅 socket，帧形状合叶子协议（type/ts_ms/metrics|powers_db|label+sent_ms）。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    run_dir = _make_run(root)
    hub = {"sockets": set(), "acks": []}
    sock = FakeSocket(hub)
    hub["sockets"].add(sock)
    ctx = _bridge_ctx(root)

    def _writer():
        time.sleep(0.03)
        _append(
            os.path.join(run_dir, "kpi.csv"),
            "100.0,sim,sim,0.01,0.0,,1,\n200.0,sim,sim,0.02,0.0,,2,\n",
        )
        _append(
            os.path.join(run_dir, "monitor.csv"),
            "1000.0,2410.0,-90.5,ok\n1000.0,2411.0,-91.5,ok\n"
            "2000.0,2410.0,-80.25,ok\n2000.0,2411.0,-81.75,ok\n",
        )
        _append(
            os.path.join(run_dir, "events.jsonl"),
            json.dumps({"type": "power_step", "step": 3, "ts": 111})
            + "\n"
            + json.dumps({"type": "baseline", "passed": True, "ts": 112})
            + "\n",
        )
        time.sleep(0.08)
        open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8").write("{}")

    writer = threading.Thread(target=_writer)
    writer.start()
    stats = stream_realtime_console(ctx, hub)
    writer.join()
    assert stats["followed_run"] == "20261013-230000"
    assert stats["stopped_reason"] == "result_json"
    assert stats["frames"] == {"kpi": 2, "spectrum": 2, "event": 2}
    assert stats["n_pushed"] == 6 and stats["n_offline"] == 0
    kpi = [f for f in sock.frames if f.get("type") == "kpi"]
    assert len(kpi) == 2
    assert kpi[0]["ts_ms"] == 100.0
    assert kpi[0]["metrics"]["per"] == 0.01 and kpi[0]["metrics"]["retries"] == 1.0
    assert "rssi_dbm" not in kpi[0]["metrics"]  # 空值列省略
    spec = [f for f in sock.frames if f.get("type") == "spectrum"]
    assert [f["powers_db"] for f in spec] == [[-90.5, -91.5], [-80.25, -81.75]]
    events = [f for f in sock.frames if f.get("type") == "event"]
    assert [e["label"] for e in events] == ["power_step step=3", "baseline passed=通过"]
    assert all("sent_ms" in f for f in sock.frames)  # push 统一盖发送戳


def test_latency_stats_land_in_result_container(tmp_path):
    """② 延迟统计（行可见→广播发送戳，measure_refresh_latency 口径）入
    run_ctx['result']['realtime']，样本足够时 P50/P95 非 None。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    run_dir = _make_run(root)
    hub = {"sockets": set()}
    hub["sockets"].add(FakeSocket())
    ctx = _bridge_ctx(root)
    rows = "".join(
        f"{100.0 * i},sim,sim,0.0,{i % 3},,{i},\n" for i in range(6)
    )
    _append(os.path.join(run_dir, "kpi.csv"), rows)
    open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8").write("{}")
    stats = stream_realtime_console(ctx, hub)
    latency = stats["latency"]
    assert latency["status"] == "ok" and latency["n_measured"] == 6
    assert latency["p50_ms"] is not None and latency["p95_ms"] is not None
    assert latency["threshold_ms"] == 500
    # B24 I3 方向铆：配对方向为 行可见戳(sent_ms)→广播发送戳(acked_ms)——
    # 广播必晚于行可见（同源墙钟），延迟恒 ≥0 且无 clock_skew 样本；交换
    # sent/acked 配对的变异会令全样本变负（被钳 0+计入 skew）——n_clock_skew
    # 断言即杀。分位单调（P50≤P95）同铆统计语义。
    assert latency["n_clock_skew"] == 0
    assert latency["p50_ms"] >= 0 and latency["p50_ms"] <= latency["p95_ms"]
    assert ctx["result"]["realtime"] is stats  # 落点容器同对象


def test_on_result_callback_receives_stats(tmp_path):
    """③ 'on_result' 回调落点并行生效（stats 原对象收旨）。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    run_dir = _make_run(root)
    seen = []
    ctx = _bridge_ctx(root, on_result=seen.append)
    _append(os.path.join(run_dir, "events.jsonl"), '{"type": "x", "ts": 1}\n')
    open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8").write("{}")
    stats = stream_realtime_console(ctx, {"sockets": set()})
    assert seen == [stats]


def test_spectrum_window_aggregation_merges_nearby_blocks(tmp_path):
    """④ spectrum_window_ms>0：同窗相邻块行并入一帧（floor(ts/窗) 分组口径）。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    run_dir = _make_run(root)
    hub = {"sockets": set()}
    hub["sockets"].add(FakeSocket())
    ctx = _bridge_ctx(root, spectrum_window_ms=1500.0)
    _append(
        os.path.join(run_dir, "monitor.csv"),
        "1000.0,2410.0,-90.0,ok\n1400.0,2411.0,-91.0,ok\n"
        "3100.0,2410.0,-80.0,ok\n3200.0,2411.0,-81.0,ok\n",
    )
    open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8").write("{}")
    stats = stream_realtime_console(ctx, hub)
    assert stats["frames"]["spectrum"] == 2  # {1000,1400} 同窗、{3100,3200} 同窗
    frames = [
        f
        for sock in hub["sockets"]
        for f in sock.frames
        if f.get("type") == "spectrum"
    ]
    assert [f["powers_db"] for f in frames] == [[-90.0, -91.0], [-80.0, -81.0]]


def test_event_bad_lines_skipped_and_label_falls_back_to_type(tmp_path):
    """⑤ 坏 JSON 行跳过不中断；无可辨别字段的事件 label 回退 type。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    run_dir = _make_run(root)
    hub = {"sockets": set()}
    hub["sockets"].add(FakeSocket())
    ctx = _bridge_ctx(root)
    _append(
        os.path.join(run_dir, "events.jsonl"),
        "{broken json\n"
        + json.dumps({"type": "streams_stopped"}) + "\n"
        + json.dumps({"no_type_key": 1, "ts": 5}) + "\n",
    )
    open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8").write("{}")
    stats = stream_realtime_console(ctx, hub)
    assert stats["frames"]["event"] == 2  # 坏行丢弃，两行合法
    labels = [f["label"] for sock in hub["sockets"] for f in sock.frames]
    assert "streams_stopped" in labels and "event" in labels  # 缺 type/无字段回退


# ---- 尾随生命周期 ----


def test_stop_flag_exits_promptly_without_result_json(tmp_path):
    """⑥ 无 result.json：stop 信号即停（stopped_reason='stop_flag'），已见行
    仍完成最终冲刷（不丢尾帧）。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    run_dir = _make_run(root)
    hub = {"sockets": set()}
    hub["sockets"].add(FakeSocket())
    ctx = _bridge_ctx(root, discovery_timeout_s=30.0)

    def _stopper():
        time.sleep(0.05)
        _append(os.path.join(run_dir, "events.jsonl"), '{"type": "e1", "ts": 1}\n')
        time.sleep(0.06)
        ctx["stop"]["flag"] = True

    stopper = threading.Thread(target=_stopper)
    stopper.start()
    stats = stream_realtime_console(ctx, hub)
    stopper.join()
    assert stats["stopped_reason"] == "stop_flag"
    assert stats["frames"]["event"] == 1  # 停前最终冲刷到位


def test_discovery_timeout_quiet_exit_when_no_run_dir(tmp_path):
    """⑦ 新运行目录未出现（如校验失败不建目录）→discovery_timeout 安静退出，
    统计落点照写（followed None/frames 全零）。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    ctx = _bridge_ctx(root, discovery_timeout_s=0.06)
    stats = stream_realtime_console(ctx, {"sockets": set()})
    assert stats["followed_run"] is None and stats["run_dir"] is None
    assert stats["stopped_reason"] == "discovery_timeout"
    assert stats["frames"] == {"kpi": 0, "spectrum": 0, "event": 0}
    assert stats["latency"]["n_measured"] == 0  # 空样本：insufficient 口径
    assert ctx["result"]["realtime"] is stats


def test_baseline_runs_excludes_existing_dirs(tmp_path):
    """⑧ 发现基线外首个新目录被尾随（基线内既有目录不跟随）。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    _make_run(root, "20261013-220000")  # 既有目录（基线内）
    new_dir = _make_run(root, "20261013-230000")
    open(os.path.join(new_dir, "result.json"), "w", encoding="utf-8").write("{}")
    ctx = _bridge_ctx(root, baseline_runs={"20261013-220000"})
    stats = stream_realtime_console(ctx, {"sockets": set()})
    assert stats["followed_run"] == "20261013-230000"


def test_kpi_csv_rewrite_truncation_self_heals(tmp_path):
    """⑨ kpi.csv 以 'w' 重写（record_run_streams 分段重开口径）→锚点检测归零
    重读：重写后比旧文件**更长**（更难的漏判向）与更短两态，新行都不漏读；
    缓冲块边界截断的半行等补齐后再消费。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    run_dir = _make_run(root)
    hub = {"sockets": set()}
    hub["sockets"].add(FakeSocket())
    ctx = _bridge_ctx(root)

    def _writer():
        _append(os.path.join(run_dir, "kpi.csv"), "100.0,sim,sim,0.1,0,0,1,\n")
        time.sleep(0.06)
        # 半行（模拟 8KB 缓冲块边界截断）——补齐前不应被消费
        with open(os.path.join(run_dir, "kpi.csv"), "a", encoding="utf-8") as fh:
            fh.write("200.0,sim,sim,0.2,0,0,")
            fh.flush()
        time.sleep(0.06)
        _append(os.path.join(run_dir, "kpi.csv"), "2,\n")  # 补齐成完整行
        time.sleep(0.06)
        # 'w' 重写：内容比旧文件更长（长度判据漏判向，锚点检测须命中）
        with open(os.path.join(run_dir, "kpi.csv"), "w", encoding="utf-8") as fh:
            fh.write(
                "timestamp_ms,link,source,per,judge_per,rssi_dbm,retries,per_note\n"
            )
            for i in range(6):
                fh.write(f"{50.0 * i},sim,sim,0.05,{i % 2},,{i},\n")
            fh.flush()
        time.sleep(0.06)
        open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8").write("{}")

    writer = threading.Thread(target=_writer)
    writer.start()
    stats = stream_realtime_console(ctx, hub)
    writer.join()
    ts_seen = [
        f["ts_ms"]
        for sock in hub["sockets"]
        for f in sock.frames
        if f.get("type") == "kpi"
    ]
    # 补齐行 200.0 与重写后的 0/50/…/250 全部到达（半行补齐+两向重写自愈）
    assert 200.0 in ts_seen
    for i in range(6):
        assert 50.0 * i in ts_seen
    assert stats["frames"]["kpi"] >= 7


# ---- 无订阅者 / 降频（R49 口径） / hub 失联 ----


def test_no_subscriber_frames_counted_no_error(tmp_path):
    """⑩ 无订阅者：帧照常消费计数（n_pushed），不报错不落离线。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    run_dir = _make_run(root)
    ctx = _bridge_ctx(root)
    _append(os.path.join(run_dir, "kpi.csv"), "1.0,sim,sim,0.1,0,0,1,\n")
    open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8").write("{}")
    stats = stream_realtime_console(ctx, {"sockets": set()})
    assert stats["frames"]["kpi"] == 1
    assert stats["n_pushed"] == 1 and stats["n_offline"] == 0


def test_degraded_latch_interval_growth_and_frame_annotation(tmp_path):
    """⑪ R49 口径降频：两断连（≥2 下限）→degraded 置位+推送间隔升档+
    degrade_note 标注；后续帧盖 'degraded': True，健康订阅者可见。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    run_dir = _make_run(root)
    hub = {"sockets": set(), "acks": []}
    healthy = FakeSocket()
    hub["sockets"].add(FakeSocket(fail=True))
    hub["sockets"].add(FakeSocket(fail=True))
    hub["sockets"].add(healthy)
    ctx = _bridge_ctx(root, degrade_max_interval_s=0.5)

    def _writer():
        _append(os.path.join(run_dir, "events.jsonl"), '{"type": "wave1"}\n')
        time.sleep(0.12)  # 隔开两个推送周期（降频判定先行）
        _append(os.path.join(run_dir, "events.jsonl"), '{"type": "wave2"}\n')
        time.sleep(0.1)
        open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8").write("{}")

    writer = threading.Thread(target=_writer)
    writer.start()
    stats = stream_realtime_console(ctx, hub)
    writer.join()
    assert stats["degraded"] is True
    assert stats["degrade_note"] and "R49" in stats["degrade_note"]
    assert stats["poll_interval_s"] > ctx["poll_interval_s"]  # 间隔升档
    assert hub.get("degraded") is True
    wave2 = [f for f in healthy.frames if f.get("label") == "wave2"]
    assert wave2 and all(f.get("degraded") is True for f in wave2)


def test_hub_failure_offline_fallback_writes_jsonl(tmp_path):
    """⑫ hub 失联（push 抛出）：帧批降级离线落盘 realtime_offline.jsonl，
    运行不中断（安静收尾），n_offline 计数。"""
    root = str(tmp_path / "reports")
    os.makedirs(root)
    run_dir = _make_run(root)
    ctx = _bridge_ctx(root)
    _append(os.path.join(run_dir, "kpi.csv"), "1.0,sim,sim,0.1,0,0,1,\n")
    open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8").write("{}")
    stats = stream_realtime_console(ctx, 42)  # 非 dict hub：push 路径必炸
    assert stats["stopped_reason"] == "result_json"  # 运行照常收尾
    assert stats["n_offline"] == 1
    offline_path = os.path.join(root, OFFLINE_FILENAME)
    assert os.path.isfile(offline_path)
    record = json.loads(open(offline_path, encoding="utf-8").read().splitlines()[0])
    assert record["frames"][0]["type"] == "kpi"
    assert isinstance(record["detected_ms"], float)


# ---- 形状校验 + 装配助手（叶子 wired 于父模块） ----


@pytest.mark.parametrize("bad_ctx", [None, "ctx", 42, [], {"report_root": ""}])
def test_bad_run_ctx_valueerror(bad_ctx):
    """⑬ run_ctx 非 dict/缺 report_root（非空 str）→ValueError 显式拒。"""
    with pytest.raises(ValueError, match="run_ctx|report_root"):
        stream_realtime_console(bad_ctx, {"sockets": set()})


def test_build_realtime_charts_delegates_to_leaf():
    """⑭ 装配助手经手叶子（R58 wired：render_triple_stream_charts 调用点在父
    模块）：产物同源、三 canvas 在位、非法 config ValueError 原样透传。"""
    block = build_realtime_charts()
    assert block == render_triple_stream_charts()
    assert 'id="chart-kpi"' in block and 'id="chart-spectrum"' in block
    assert 'id="chart-events"' in block
    assert "__TSCHARTS_STATS__" in block  # e2e 断言钩子（申报的最小计数器）
    with pytest.raises(ValueError, match="config"):
        build_realtime_charts({"unknown_key": 1})


# ---- 集成：serve_console 缺省 runner 挂桥（真实 sim 运行，无浏览器） ----


#: 集成场景文件（gb42590 快路径 sim——与 tests/serve_console 既有 e2e 同形状）。
_GB_FAST_YAML = """\
style: tone
fs: 1.0e6
freq_hz: 2.4e9
power_dbm: -10
duration_s: 0.005
backend: sim
scenario_type: gb42590
judge_min_samples: 2
dwell_s: 0.0
baseline_samples: 10
record: false
bands:
  - [2400.0, 2483.5]
shielded_box: true
dut_scope: self_built
"""


def _serve(tmp_path, **cfg_over):
    from src.serve_console.serve_console import serve_console

    sdir = tmp_path / "scenarios"
    sdir.mkdir(exist_ok=True)
    rroot = tmp_path / "reports"
    rroot.mkdir(exist_ok=True)
    (sdir / "gb_fast.yaml").write_text(_GB_FAST_YAML, encoding="utf-8")
    cfg = {
        "scenario_dir": str(sdir),
        "report_root": str(rroot),
        "port": 18126,
        "host": "127.0.0.1",
        "dry_run": True,
    }
    cfg.update(cfg_over)
    return serve_console(cfg), rroot


@needs_fastapi
def test_console_default_runner_real_run_attaches_realtime(tmp_path):
    """⑮ 集成主链路：缺省 runner 真跑 sim 运行（薄载荷 name）→运行期间三路
    帧桥随行（/api/runs/{id} 终态 result 携 'realtime'：kpi/event 帧>0+
    latency 统计+followed_run 真实目录名）。"""
    result, rroot = _serve(tmp_path)
    with TestClient(result["app"]) as client:
        resp = client.post("/api/run", json={"scenario": {"name": "gb_fast"}})
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]
        entry = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            entry = client.get(f"/api/runs/{run_id}").json()
            if entry["status"] != "running":
                break
            time.sleep(0.2)
    assert entry["status"] == "done"
    res = entry["result"]
    assert res["status"] == "completed" and res["exit_code"] == 0
    realtime = res["realtime"]  # 延迟统计入运行结果（操控台侧落点）
    assert realtime["followed_run"] == os.path.basename(res["run_dir"])
    assert realtime["frames"]["kpi"] > 0  # sim 真跑 kpi.csv 实有行
    assert realtime["frames"]["event"] > 0  # events.jsonl 实有事件
    assert realtime["latency"]["n_measured"] > 0
    assert realtime["stopped_reason"] in {"stop_flag", "result_json"}
    assert os.path.isdir(os.path.join(str(rroot), realtime["followed_run"]))


@needs_fastapi
def test_console_default_assembly_injects_charts_section(tmp_path):
    """⑯ 缺省装配：index 运行页注入三路图区区块（id+三 canvas+帧计数钩子）；
    其余六页与显式 static_pages 直通不注入。"""
    result, _ = _serve(tmp_path)
    with TestClient(result["app"]) as client:
        page = client.get("/pages/index").text
        skeleton = client.get("/pages/overview").text
    assert 'id="triple-stream-charts"' in page
    assert 'id="chart-kpi"' in page and 'id="chart-spectrum"' in page
    assert 'id="chart-events"' in page
    assert "__TSCHARTS_STATS__" in page
    assert 'id="triple-stream-charts"' not in skeleton

    result2, _ = _serve(
        tmp_path, static_pages={"index.html": "<html><body>x</body></html>"}
    )
    with TestClient(result2["app"]) as client2:
        page2 = client2.get("/pages/index").text
    assert "triple-stream-charts" not in page2  # 显式直通不注入


@needs_fastapi
def test_console_hub_container_shared_into_app(tmp_path):
    """⑰ hub 流通：serve_console 预建共享容器→create_console_app 原对象优先
    （app.state.hub 与 deps['hub'] 同一对象，缺省 runner 桥与路由共用）。"""
    result, _ = _serve(tmp_path)
    hub = result["app"].state.deps["hub"]
    assert result["app"].state.hub is hub
    assert {"sockets", "history", "broadcast"} <= set(hub)  # 工厂填齐三件套


@needs_fastapi
def test_console_explicit_runner_result_has_no_realtime(tmp_path):
    """⑱ 显式 runner 直通不挂桥：result 无 'realtime' 键（桥仅缺省 runner 路径）。"""
    result, _ = _serve(tmp_path, runner=lambda scenario: {"echo": True})
    with TestClient(result["app"]) as client:
        resp = client.post("/api/run", json={"scenario": {"style": "tone"}})
        run_id = resp.json()["run_id"]
        deadline = time.monotonic() + 5
        entry = None
        while time.monotonic() < deadline:
            entry = client.get(f"/api/runs/{run_id}").json()
            if entry["status"] != "running":
                break
            time.sleep(0.05)
    assert entry["status"] == "done"
    assert "realtime" not in entry["result"]
