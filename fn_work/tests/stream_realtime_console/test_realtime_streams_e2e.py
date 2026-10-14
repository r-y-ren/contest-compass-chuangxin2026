"""realtime_streams_e2e：playwright+chromium 端到端（用例名统一
test_realtime_streams_e2e_ 前缀——`pytest -k realtime_streams_e2e` 整体发现本族）。

R58 验收口径「运行期三路帧经 /ws 真实到达浏览器三图」的端到端证据（构造方式同
tests/edit_scenario_ui/test_scenario_editor_e2e.py：线程内 uvicorn 随机端口+
chromium 单实例，serve_console dry_run **缺省 runner** 装配——不注入 runner，
POST /api/run 即真跑 sim 场景，实时流桥随行推帧）：

- 打开 /pages/index → #triple-stream-charts 三图区块+三 canvas 在位（装配注入）；
- POST /api/run 薄载荷 → 真 sim 运行：KPI 帧/事件帧/频谱帧真实到达浏览器
  （window.__TSCHARTS_STATS__ 每类帧计数 >0——叶子内建的最小 window 计数器，
  R58 接线申报）；运行终态 result 携 'realtime' 延迟统计（操控台侧结果 JSON）。
  频谱路真帧（走查环 F2 新真值，2026-10-14）：SimBackend 静默态产底噪块后
  sim 管线 monitor.csv 不再恒空——旧「频谱路为空属既有口径」的回声通道
  用例保留（R58 三图渲染叶子消费的独立证据），运行主链路的 spectrum 计数
  直接断言 >0；
- 全程无 console error 级 JS 报错。

总时长预算 <30s：chromium 单次 launch+uvicorn 单实例+单 sim 快路径运行。
环境缺 playwright/uvicorn/fastapi 时整族 skip。
"""
import socket
import threading
import time

import pytest

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_PLAYWRIGHT = False

try:  # uvicorn+fastapi 同源依赖——任一缺失即整族 skip
    import uvicorn

    from src.serve_console.serve_console import serve_console

    _HAS_SERVER = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_SERVER = False

needs_e2e = pytest.mark.skipif(
    not (_HAS_PLAYWRIGHT and _HAS_SERVER),
    reason="环境缺 playwright/uvicorn/fastapi——e2e 不可用",
)

#: 真跑 sim 场景文件（gb42590 快路径：与 tests/serve_console 既有端到端同形状）。
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


def _free_port() -> int:
    """取一个当前空闲的本地端口（bind(0) 后立即释放，随机端口化解占用冲突）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def console_server(tmp_path_factory):
    """真服务（线程内 uvicorn.Server+config，随机端口）：serve_console dry_run
    **缺省 runner** 装配（不注入 runner——POST /api/run 走 _make_default_runner
    真跑+R58 实时流桥挂 hub 的完整改造路径）；scenario_dir 预置 gb_fast 场景。"""
    tmp_path = tmp_path_factory.mktemp("realtime_streams_e2e")
    sdir = tmp_path / "scenarios"
    sdir.mkdir()
    (sdir / "gb_fast.yaml").write_text(_GB_FAST_YAML, encoding="utf-8")
    rroot = tmp_path / "reports"
    rroot.mkdir()
    result = serve_console(
        {
            "scenario_dir": str(sdir),
            "report_root": str(rroot),
            "port": 18125,  # dry_run 不真占用，仅形状合法
            "host": "127.0.0.1",
            "dry_run": True,
            "stop_flag": {"flag": False},
        }
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(result["app"], host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True, name="realtime-streams-e2e")
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not server.started:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        pytest.fail("uvicorn 未能在 10s 内启动（e2e 前置失败）")
    yield {"base": f"http://127.0.0.1:{port}"}
    server.should_exit = True  # 结束关服务
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    """chromium 单实例（模块级复用，控制总时长）。"""
    with sync_playwright() as p:
        instance = p.chromium.launch(args=["--no-sandbox"])
        yield instance
        instance.close()


@pytest.fixture
def charts_page(browser):
    """普通浏览器页（index 运行页：编辑器/三图区块+同源 /ws，无外网依赖）
    +console error 收集（预期 4xx 网络日志不计入）。"""
    context = browser.new_context()
    page = context.new_page()
    errors: list = []

    def _on_console(msg):
        if msg.type == "error" and not msg.text.startswith("Failed to load resource"):
            errors.append(msg.text)

    page.on("console", _on_console)
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    yield page, errors
    context.close()


def _stats(page, key: str) -> int:
    """window.__TSCHARTS_STATS__ 每类帧计数读取（叶子内建 e2e 断言钩子）。"""
    return page.evaluate("window.__TSCHARTS_STATS__ ? window.__TSCHARTS_STATS__.%s : -1" % key)


@needs_e2e
def test_realtime_streams_e2e_run_frames_reach_charts(console_server, charts_page):
    """R58 端到端主链路：三图区块在位→真 sim 运行→KPI/事件帧真实到达浏览器
    （计数>0）→运行终态 result 携 'realtime' 延迟统计（操控台侧结果 JSON）。"""
    page, errors = charts_page
    base = console_server["base"]

    # ---- ① 打开 /pages/index：三图区块+三 canvas 在位（装配注入被真实检验） ----
    resp = page.goto(f"{base}/pages/index", wait_until="load", timeout=10_000)
    assert resp is not None and resp.status == 200
    assert page.locator("#triple-stream-charts").count() == 1
    for cid in ("chart-kpi", "chart-spectrum", "chart-events"):
        assert page.locator(f"#{cid}").count() == 1

    # ---- ② POST /api/run 薄载荷（缺省 runner 真跑 sim+实时流桥随行） ----
    run_id = page.evaluate(
        """async (base) => {
            const resp = await fetch(base + '/api/run', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({scenario: {name: 'gb_fast'}}),
            });
            return (await resp.json()).run_id;
        }""",
        base,
    )
    assert run_id

    # ---- ③ KPI 帧/事件帧/频谱帧真实到达（kpi.csv/events.jsonl/monitor.csv 实有
    # 行→帧→/ws→叶子——走查环 F2 后 monitor.csv 有底噪块行，频谱路真帧直达） ----
    page.wait_for_function("window.__TSCHARTS_STATS__.kpi > 0", timeout=30_000)
    page.wait_for_function("window.__TSCHARTS_STATS__.events > 0", timeout=10_000)
    page.wait_for_function("window.__TSCHARTS_STATS__.spectrum > 0", timeout=30_000)
    assert _stats(page, "kpi") > 0
    assert _stats(page, "events") > 0
    assert _stats(page, "spectrum") > 0

    # ---- ④ 运行终态：result 携 'realtime' 延迟统计（app.state.runs 条目落点） ----
    entry = page.evaluate(
        """async ([base, runId]) => {
            const deadline = Date.now() + 45000;
            while (Date.now() < deadline) {
                const entry = await (await fetch(base + '/api/runs/' + runId)).json();
                if (entry.status !== 'running') { return entry; }
                await new Promise(r => setTimeout(r, 200));
            }
            return null;
        }""",
        [base, run_id],
    )
    assert entry is not None and entry["status"] == "done"
    res = entry["result"]
    assert res["status"] == "completed" and res["exit_code"] == 0
    realtime = res["realtime"]
    assert realtime["frames"]["kpi"] > 0 and realtime["frames"]["event"] > 0
    assert realtime["latency"]["n_measured"] > 0  # 行可见→广播发送戳样本入档
    # B24 I3 方向铆（e2e）：行可见戳先于广播发送戳（同源墙钟）——无负延迟
    # 样本；交换 sent/acked 配对的变异令全样本入 skew，此处即杀。
    assert realtime["latency"]["n_clock_skew"] == 0
    assert realtime["followed_run"]  # 真实尾随到本运行目录
    assert errors == []  # 全程无 console error 级 JS 报错


@needs_e2e
def test_realtime_streams_e2e_spectrum_path_via_ws_echo(console_server, charts_page):
    """R58 频谱路 /ws 回声通道（独立证据保留）：走查环 F2 修复后 sim 运行的
    monitor.csv 已有真实底噪块行（主链路用例直接断言 spectrum>0）；本用例经
    /ws 客户端回声通道（收到消息即广播全体）从页面发真频谱帧：真实 hub/WS/
    叶子频谱消费全链（计数>0），未知帧跳过计数器照常工作（connected 帧即
    未知帧族）。"""
    page, errors = charts_page
    base = console_server["base"]

    resp = page.goto(f"{base}/pages/index", wait_until="load", timeout=10_000)
    assert resp is not None and resp.status == 200
    page.wait_for_function(
        "window.__TSCHARTS_STATS__ !== undefined", timeout=10_000
    )  # 图区 JS 已引导

    sent = page.evaluate(
        """async () => {
            return await new Promise((resolve) => {
                const sock = new WebSocket((location.protocol === 'https:' ? 'wss:' : 'ws:')
                    + '//' + location.host + '/ws');
                sock.onopen = () => {
                    sock.send(JSON.stringify({type: 'spectrum', ts_ms: Date.now(),
                        powers_db: [-85.5, -78.25, -66.0, -52.75]}));
                    resolve(true);
                };
                sock.onerror = () => resolve(false);
            });
        }"""
    )
    assert sent is True

    # 频谱帧经 hub 回声广播到达本页图区（真实 WS 链路，非 mock）
    page.wait_for_function("window.__TSCHARTS_STATS__.spectrum > 0", timeout=10_000)
    assert _stats(page, "spectrum") > 0
    # 未知帧跳过计数在位（握手 connected 帧属未知帧族→skipped ≥1）
    assert _stats(page, "skipped") >= 1
    assert page.locator("#tscharts-skipped").count() == 1
    assert errors == []
