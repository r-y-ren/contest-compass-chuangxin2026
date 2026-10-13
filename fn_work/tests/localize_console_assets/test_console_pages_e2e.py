"""console_pages_e2e：playwright+chromium 断网端到端（用例名统一
test_console_pages_e2e_ 前缀——`pytest -k console_pages_e2e` 整体发现本族）。

R56 验收口径「七页经 /pages 托管、断网可加载」的浏览器侧证据：
- uvicorn 线程内起真服务（随机端口，serve_console dry_run 装配的 app——即缺省
  七页产出的真实装配路径），结束关服务；
- chromium context.route 把非 127.0.0.1 的 http(s) 请求全部 abort（模拟断网），
  同时记录被 abort 的外网请求（应为空——页面根本不该尝试外网）；
- 逐页 GET /pages/<slug>：200+load 事件到达+导航条在位+无 console error 级
  JS 报错+window.Vue 在位（本地 vendor 真实装载，断网全可用的硬证据）；
- 总时长预算 <30s：chromium 单次launch+uvicorn 单实例，七页各一次导航。

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

#: 七页 slug（与导航产出序一致）。
SEVEN_SLUGS = ["overview", "index", "reports", "data", "ai", "instruments", "ledger"]

#: 六页（除 index）应有的 mounts 占位 id（index 为 render_console_pages 真实区块）。
SPEC_MOUNTS = {
    "overview": ["backend", "clock", "ledger", "recent-runs"],
    "reports": ["run-list", "report-view", "comparison"],
    "data": ["dataset-grid", "filters"],
    "ai": ["train-panel", "eval-panel", "infer-panel"],
    "instruments": ["instrument-panels", "visa-status"],
    "ledger": ["audit-report", "ledger-detail"],
}


def _free_port() -> int:
    """取一个当前空闲的本地端口（bind(0) 后立即释放，随机端口化解占用冲突）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def console_server(tmp_path_factory):
    """真服务（线程内 uvicorn.Server+config，随机端口）：serve_console dry_run
    装配的 app——static_pages 未传即走缺省七页产出（被测的真实装配路径）。"""
    tmp_path = tmp_path_factory.mktemp("console_pages_e2e")
    sdir = tmp_path / "scenarios"
    sdir.mkdir()
    rroot = tmp_path / "reports"
    rroot.mkdir()
    result = serve_console(
        {
            "scenario_dir": str(sdir),
            "report_root": str(rroot),
            "port": 18123,  # dry_run 不真占用，仅形状合法
            "host": "127.0.0.1",
            "dry_run": True,
            "runner": lambda scenario: {"echo": scenario},  # e2e 不触发真跑
            "stop_flag": {"flag": False},
        }
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(result["app"], host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True, name="console-e2e-server")
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not server.started:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        pytest.fail("uvicorn 未能在 10s 内启动（e2e 前置失败）")
    yield {"base": f"http://127.0.0.1:{port}", "port": port}
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
def offline_page(browser):
    """断网浏览器页：非 127.0.0.1 的请求全部 abort（模拟断网），并记录被 abort
    的外网请求（供断言「根本没尝试外网」）；返回 (page, aborted)。"""
    context = browser.new_context()
    aborted: list = []

    def _block_external(route):
        url = route.request.url
        if url.startswith("http://127.0.0.1"):
            route.continue_()
        else:
            aborted.append(url)
            route.abort()

    context.route("**/*", _block_external)
    page = context.new_page()
    yield page, aborted
    context.close()


@needs_e2e
@pytest.mark.parametrize("slug", SEVEN_SLUGS)
def test_console_pages_e2e_offline_load(slug, console_server, offline_page):
    """① 断网逐页加载：GET /pages/<slug> 200+load 到达+导航条在位+无 console
    error 级 JS 报错+window.Vue 在位（本地 vendor 真实装载）+全程零外网请求
    尝试；六页 mounts 占位逐 id 在位，index 为真实运行页区块。"""
    page, aborted = offline_page
    errors: list = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    resp = page.goto(
        f"{console_server['base']}/pages/{slug}", wait_until="load", timeout=10_000
    )
    assert resp is not None and resp.status == 200
    assert page.locator("#console-nav").count() == 1  # 导航条存在
    assert page.evaluate("() => typeof window.Vue !== 'undefined'") is True
    assert errors == []  # 无 console error 级 JS 报错
    assert aborted == []  # 断网下零外网请求尝试（页面本就不该有外链）
    if slug in SPEC_MOUNTS:
        for mid in SPEC_MOUNTS[slug]:
            assert page.locator(f"#{mid}").count() == 1, (slug, mid)
    else:  # index：render_console_pages 真实运行页区块（经 CDN→vendor 切换）
        assert page.locator("#scenario-grid").count() == 1
        assert page.locator("#status-panel").count() == 1
        assert "unpkg.com" not in page.content()


@needs_e2e
def test_console_pages_e2e_offline_navigation_hops(console_server, offline_page):
    """② 断网页间跳转：导航条链接真实可达——从总览页点击「台账」链接加载台账页
    （200+当前页高亮切换到 ledger）。"""
    page, aborted = offline_page
    resp = page.goto(
        f"{console_server['base']}/pages/overview", wait_until="load", timeout=10_000
    )
    assert resp is not None and resp.status == 200
    page.click('a.nav-link[href="/pages/ledger"]')
    page.wait_for_url(f"{console_server['base']}/pages/ledger", timeout=10_000)
    page.wait_for_load_state("load")
    assert page.locator("#page-identity").get_attribute("data-page") == "ledger"
    assert page.evaluate("() => typeof window.Vue !== 'undefined'") is True
    assert aborted == []
