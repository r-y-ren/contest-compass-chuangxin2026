"""report_view_e2e：真服务+真跑一次最小 sim 运行的报告页端到端（R60 决定性
防回归——用例名统一 test_report_view_e2e_ 前缀，`pytest -k report_view`
整体发现本族）。

验收链（报告站内可读）：
- 真运行：serve_console dry_run **缺省 runner**（真跑 sim 场景，抄
  test_emergency_stop_e2e 的真运行模式）→POST /api/run 薄载荷→轮询至 done
  →report_root 下真实 run 目录（report.md+plots 三 PNG+数据文件+result.json
  附 traceability）；
- 三端点 API 证据（urllib 打真 uvicorn 端口）：GET /api/runs/{run}/report→
  200 HTML（plots 端点引用+溯源徽标）、/plots/{name}→200 PNG（三张）、
  /files/kpi.csv→200 原始字节；
- 浏览器证据（playwright+chromium）：GET /pages/reports?run=<运行目录名>→
  报告查看区 JS fetch 渲染——#report-html 在位、三 <img> 全部加载
  （naturalWidth>0）、#traceability-badge 徽标可见且 data-passed 与
  result.json 的 traceability.passed 一致、files 下载链接真实 200。

环境缺 playwright/uvicorn/fastapi 时整族 skip。
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

try:  # playwright 浏览器侧证据——缺失即整族 skip
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_PLAYWRIGHT = False

needs_e2e = pytest.mark.skipif(
    not (_HAS_PLAYWRIGHT and _HAS_SERVER),
    reason="环境缺 playwright/uvicorn/fastapi——e2e 不可用",
)

#: 最小 sim 场景（gb42590 快路径：dwell 0/judge 2/baseline 10——秒级完成；
#: sim 事件缺省 jsr=-20 恒不触发判据 → completed，与 serve_console e2e 同源）。
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

#: 三元曲线三 PNG 名（build_report 恒产出——三图可见断言用）。
_PNG_NAMES = (
    "curve_a_per_vs_level.png",
    "curve_b_throughput_vs_per.png",
    "curve_c_event_timeline.png",
)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


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


def _get_json(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_bytes(base: str, path: str) -> "tuple[int, str, bytes]":
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return resp.status, resp.headers.get("Content-Type", ""), resp.read()


@pytest.fixture(scope="module")
def console_server(tmp_path_factory):
    """真服务（线程内 uvicorn.Server+config，随机端口）：serve_console dry_run
    **缺省 runner** 装配（不注入 runner——POST /api/run 即真跑 sim）；scenario_dir
    预置 gb_fast 场景。返回 {'base': http://…}。"""
    tmp_path = tmp_path_factory.mktemp("report_view_e2e")
    sdir = tmp_path / "scenarios"
    sdir.mkdir()
    (sdir / "gb_fast.yaml").write_text(_GB_FAST_YAML, encoding="utf-8")
    rroot = tmp_path / "reports"
    rroot.mkdir()
    result = serve_console(
        {
            "scenario_dir": str(sdir),
            "report_root": str(rroot),
            "port": 18127,  # dry_run 不真占用，仅形状合法
            "host": "127.0.0.1",
            "dry_run": True,
            "stop_flag": {"flag": False},
        }
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(result["app"], host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True, name="report-view-e2e")
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
def real_run(console_server):
    """真跑一次最小 sim 运行至终态，返回 (run_name, result)——run_name 即
    report_root 下运行目录名（R60 三端点的 run_id 口径）。"""
    base = console_server["base"]
    run_uuid = _post(base, "/api/run", {"scenario": {"name": "gb_fast"}})["run_id"]
    entry = None
    deadline = time.monotonic() + 90  # sim 快路径秒级，90s 足够宽
    while time.monotonic() < deadline:
        entry = _get_json(base, f"/api/runs/{run_uuid}")
        if entry["status"] != "running":
            break
        time.sleep(0.2)
    assert entry is not None and entry["status"] == "done"
    result = entry["result"]
    assert result["status"] == "completed"  # 真跑完成（非校验失败回执）
    run_name = result["run_dir"].rstrip("/").split("/")[-1]
    return run_name, result


@needs_e2e
def test_report_view_e2e_real_run_report_page(console_server, real_run):
    """R60 主链路端到端：真 sim 运行→三端点 API 证据（report HTML/三 PNG/文件
    下载 200）→浏览器打开报告页 ?run=<id>——HTML 渲染在位+三图可见+溯源徽标
    与 result.json 一致+文件下载链接 200。"""
    base = console_server["base"]
    run_name, result = real_run

    # ---- ① report 端点：200 HTML+plots 端点引用+溯源徽标 ----
    status, ctype, body = _get_bytes(base, f"/api/runs/{run_name}/report")
    assert status == 200 and ctype.startswith("text/html")
    html = body.decode("utf-8")
    for png in _PNG_NAMES:
        assert f'src="/api/runs/{run_name}/plots/{png}"' in html
    assert 'src="plots/' not in html  # 相对引用零残留（全部改写为端点引用）
    assert 'id="traceability-badge"' in html
    assert "https://" not in html and "http://" not in html  # 零外链

    # ---- ② plots 端点：三 PNG 全部 200+PNG 魔数 ----
    for png in _PNG_NAMES:
        p_status, p_ctype, p_bytes = _get_bytes(base, f"/api/runs/{run_name}/plots/{png}")
        assert p_status == 200 and p_ctype == "image/png"
        assert p_bytes.startswith(_PNG_MAGIC) and len(p_bytes) > 1000  # 真图非占位

    # ---- ③ files 端点：原始数据文件下载 200（字节与终态 result 对齐） ----
    f_status, f_ctype, f_bytes = _get_bytes(base, f"/api/runs/{run_name}/files/kpi.csv")
    assert f_status == 200 and f_ctype.startswith("text/csv")
    assert f_bytes.startswith(b"timestamp_ms")
    rj_status, _, rj_bytes = _get_bytes(base, f"/api/runs/{run_name}/files/result.json")
    assert rj_status == 200
    result_json = json.loads(rj_bytes.decode("utf-8"))
    trace_passed = (
        result_json.get("traceability", {}).get("passed") is True
    )

    # ---- ④ 浏览器证据：报告页 ?run=<id> 渲染在位+三图可见+徽标+下载链接 ----
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.goto(f"{base}/pages/reports?run={run_name}", timeout=15000)
            # 报告查看区 JS fetch 渲染完成标志：#report-html 注入挂载点
            page.wait_for_selector("#report-view #report-html", timeout=10000)
            assert page.locator("#report-view-area").count() == 1  # 区块注入在位

            # 溯源徽标：可见且 data-passed 与 result.json 一致（服务端注入回显）
            badge = page.locator(f"#report-view #report-html #traceability-badge")
            assert badge.count() == 1
            assert badge.is_visible()
            assert badge.get_attribute("data-passed") == (
                "true" if trace_passed else "false"
            )

            # 三图可见：三个 <img> 均真实加载（naturalWidth>0——端点引用真出图）
            imgs = page.locator("#report-view #report-html img")
            assert imgs.count() == len(_PNG_NAMES)
            loaded = page.evaluate(
                "Array.from(document.querySelectorAll("
                "'#report-view #report-html img'))"
                ".every(function (i) { return i.complete && i.naturalWidth > 0; })"
            )
            assert loaded, "三元曲线图未全部加载（端点引用断链）"

            # files 下载链接：白名单清单在位且首个链接真实 200
            links = page.locator("#report-view #files-list a")
            assert links.count() >= 5
            first_href = links.first.get_attribute("href")
            assert first_href.startswith(f"/api/runs/{run_name}/files/")  # 端点接线
            dl = page.request.get(base + first_href)  # request.get 须绝对 URL
            assert dl.status == 200 and len(dl.body()) > 0

            # plots 图列表：与三图对位
            assert page.locator("#report-view #plot-list a").count() == len(_PNG_NAMES)
        finally:
            browser.close()
