"""emergency_stop_e2e：真 uvicorn+缺省 runner+真 sim 的急停真停端到端（B24 C1
决定性防回归——用例名统一 test_emergency_stop_e2e_ 前缀，`pytest -k
emergency_stop` 整体发现本族）。

被杀缺陷（C1 急停生产接线空转）：修复前 /api/stop 仅置共享 stop_flag，而缺省
runner 的 run_scenario 不收停容器、管线无任何检查点、停止路由也拿不到后端句柄
（run_ctx 空→no_backend）——三处皆空转：运行照常跑完全程、页面宣称「发射已停」。

本 e2e 以真服务（线程内 uvicorn.Server 随机端口，serve_console dry_run **缺省
runner** 装配——不注入 runner，POST /api/run 即真跑 sim 场景）证三要素：
- 响应含真停结果：/api/stop 的 emergency_stop.transmit.status='stopped'（真后端
  句柄经 stop_flag['backend'] 通道贯通——非 no_backend）；
- 运行提前终止：result.status='stopped'（exit 1 未完成口径）、阶梯未走完
  （power_step 事件数 < 计划档数）、wall time 明显短于自然时长（dwell 1.2×6 档
  ≥7.2s 纯驻留，实测终止 <6s）；
- 急停后 KPI 帧不再增长：运行终止后 hub 广播历史的 kpi 帧计数冻结（window
  计数冻结口径——桥随停旗退出，kpi.csv 不再增长）。

环境缺 uvicorn/fastapi 时整族 skip（不需要 playwright——帧计数经进程内共享
hub['history'] 观测，与服务端 /ws 同源）。
"""
import json
import socket
import threading
import time
import urllib.request

import pytest

try:  # uvicorn+fastapi 同源依赖——任一缺失即整族 skip
    import uvicorn

    from src.serve_console.serve_console import serve_console

    _HAS_SERVER = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_SERVER = False

needs_e2e = pytest.mark.skipif(
    not _HAS_SERVER, reason="环境缺 uvicorn/fastapi——e2e 不可用"
)

#: 真跑 sim 场景（gb42590：dwell 1.2×GB 缺省 6 档 → 自然时长 ≥7.2s 纯驻留；
#: sim 事件缺省 10 条 jsr=-20 恒不触发判据——不走完全程即被急停截停）。
_GB_SLOW_YAML = """\
style: tone
fs: 1.0e6
freq_hz: 2.4e9
power_dbm: -10
duration_s: 0.005
backend: sim
scenario_type: gb42590
judge_min_samples: 2
dwell_s: 1.2
baseline_samples: 10
record: false
bands:
  - [2400.0, 2483.5]
shielded_box: true
dut_scope: self_built
"""

#: GB 缺省阶梯档数（link−5 起、5dB 步、0dBm 红线内——计划档数，用于「未走完」断言）。
_GB_LADDER_STEPS = 6

#: 自然时长下界（6 档 × 1.2s 纯 dwell，不含基线/收尾）与急停后实测上界预算。
_NATURAL_SECONDS = _GB_LADDER_STEPS * 1.2
_STOPPED_SECONDS_BUDGET = 6.0


def _free_port() -> int:
    """取一个当前空闲的本地端口（bind(0) 后立即释放，随机端口化解占用冲突）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _post(base: str, path: str, payload: "dict | None" = None) -> dict:
    """真 HTTP POST（urllib——打真 uvicorn 端口，非 TestClient）。"""
    data = json.dumps(payload if payload is not None else {}).encode("utf-8")
    with urllib.request.urlopen(
        urllib.request.Request(
            base + path,
            method="POST",
            data=data,
            headers={"Content-Type": "application/json"},
        ),
        timeout=10,
    ) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


@pytest.fixture(scope="module")
def console_server(tmp_path_factory):
    """真服务（线程内 uvicorn.Server+config，随机端口）：serve_console dry_run
    **缺省 runner** 装配（C1 改造路径全真：共享停容器贯通 run_scenario(stop=…)、
    后端句柄写回、run_ctx 注册 deps）；scenario_dir 预置 gb_slow 场景。

    返回 {'base': http://…, 'app': app}（app 供进程内读共享 hub['history']
    观测帧计数——与 /ws 广播同源）。"""
    tmp_path = tmp_path_factory.mktemp("emergency_stop_e2e")
    sdir = tmp_path / "scenarios"
    sdir.mkdir()
    (sdir / "gb_slow.yaml").write_text(_GB_SLOW_YAML, encoding="utf-8")
    rroot = tmp_path / "reports"
    rroot.mkdir()
    result = serve_console(
        {
            "scenario_dir": str(sdir),
            "report_root": str(rroot),
            "port": 18126,  # dry_run 不真占用，仅形状合法
            "host": "127.0.0.1",
            "dry_run": True,
            "stop_flag": {"flag": False},
        }
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(result["app"], host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True, name="emergency-stop-e2e")
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not server.started:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        pytest.fail("uvicorn 未能在 10s 内启动（e2e 前置失败）")
    yield {"base": f"http://127.0.0.1:{port}", "app": result["app"]}
    server.should_exit = True  # 结束关服务
    thread.join(timeout=5)


def _kpi_frames_in_history(app) -> int:
    """hub 广播历史中的 kpi 帧计数（与 /ws 推送同源——window 计数冻结口径）。"""
    return sum(
        1 for f in list(app.state.hub["history"]) if isinstance(f, dict) and f.get("type") == "kpi"
    )


def _events_of(run_dir: str) -> list:
    with open(run_dir + "/events.jsonl", encoding="utf-8") as fh:
        return [json.loads(x) for x in fh.read().splitlines() if x.strip()]


@needs_e2e
def test_emergency_stop_e2e_real_stop_terminates_run_early(console_server):
    """C1 决定性主链路：真 sim 运行中 POST /api/stop→响应含真停结果（真后端被
    实停，非 no_backend）→运行提前终止（status=stopped/阶梯未走完/wall time 明显
    短于自然时长）→/api/runs/{id} 终态→急停后 KPI 帧计数冻结。"""
    base, app = console_server["base"], console_server["app"]

    # ---- ① 发起真运行（薄载荷→缺省 runner 真跑 sim，dwell 1.2×6 档） ----
    started = time.monotonic()
    run_id = _post(base, "/api/run", {"scenario": {"name": "gb_slow"}})["run_id"]
    assert run_id

    # ---- ② 运行确认在途：hub 广播历史出现 kpi 帧（基线采集落盘→桥推帧） ----
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and _kpi_frames_in_history(app) == 0:
        time.sleep(0.05)
    assert _kpi_frames_in_history(app) > 0, "15s 内未见 kpi 帧——运行未真正在途"

    # ---- ③ 运行中急停：响应含真停结果（backend 通道贯通→真后端实停） ----
    body = _post(base, "/api/stop")
    assert body["stopped"] is True  # 编排旗置位（既有键）
    hard = body["emergency_stop"]
    assert hard["status"] == "stopped"
    assert hard["transmit"]["status"] == "stopped"  # 真停直证（非 no_backend 空转）
    assert hard["source"] == "console"

    # ---- ④ 运行提前终止：/api/runs/{id} 至终态，result.status='stopped' ----
    entry = None
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        entry = _get(base, f"/api/runs/{run_id}")
        if entry["status"] != "running":
            break
        time.sleep(0.1)
    assert entry is not None and entry["status"] == "done"  # runner 正常返回（stopped 非 crashed）
    res = entry["result"]
    assert res["status"] == "stopped"  # 提前终止归一（非 completed/failed）
    assert res["exit_code"] == 1  # 未完成口径（中断语义）
    elapsed = time.monotonic() - started
    assert elapsed < _STOPPED_SECONDS_BUDGET, (
        f"wall time {elapsed:.2f}s 未明显短于自然时长（≥{_NATURAL_SECONDS:.1f}s）"
        "——急停未真终止编排（C1 回归）"
    )

    # ---- ⑤ 阶梯未走完+急停事件留痕（events.jsonl 实证档间中止） ----
    events = _events_of(res["run_dir"])
    types = [e.get("type") for e in events]
    assert "emergency_stop" in types  # 急停原因入事件流
    n_steps = types.count("power_step")
    assert 1 <= n_steps < _GB_LADDER_STEPS  # 进入阶梯但未走完（提前终止实证）

    # ---- ⑥ 急停后 KPI 帧不再增长（window 计数冻结：桥退出，kpi.csv 定格） ----
    frozen = _kpi_frames_in_history(app)
    assert res["realtime"]["frames"]["kpi"] > 0  # 运行期帧确曾流动
    time.sleep(1.0)
    assert _kpi_frames_in_history(app) == frozen, "急停后 kpi 帧仍在增长——帧流未冻结"
