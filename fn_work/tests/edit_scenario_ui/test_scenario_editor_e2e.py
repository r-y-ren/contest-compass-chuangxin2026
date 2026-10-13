"""scenario_editor_e2e：playwright+chromium 端到端（用例名统一
test_scenario_editor_e2e_ 前缀——`pytest -k scenario_editor_e2e` 整体发现本族）。

R57 验收口径「编辑器区块注入 index 运行页、三操作接线既有 CRUD、校验错误
逐条上屏、成功后卡片刷新」的浏览器侧证据（构造方式同
tests/localize_console_assets/test_console_pages_e2e.py：线程内 uvicorn
随机端口+chromium 单实例，serve_console dry_run 装配——即缺省七页产出的
真实装配路径，编辑器区块经 serve_console 注入被真实检验）：

- 打开 /pages/index → #scenario-editor 区块在位+预置场景进目标下拉；
- 表单模式故意缺安全声明提交 → 400 错误清单逐条上屏（shielded_box/dut_scope
  各自成条）；
- 补全声明后提交 → 201 → #editor-cards 出现新卡+服务端落盘在册；
- 编辑（目标下拉 PUT 覆写）→ 200 → 描述注释行落盘；
- YAML 模式粘贴非法 YAML → 400 错误上屏；
- 删除目标 → 卡片消失+服务端文件移除。

总时长预算 <30s：chromium 单次 launch+uvicorn 单实例+单页单测按序驱动。
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

#: 装配期预置场景（合法全口径：schema+红线均过）——编辑/删除的目标对象。
_SEED_YAML = """\
# desc: 预置定频音
style: tone
fs: 1.0e6
power_dbm: -20
duration_s: 1
backend: sim
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
    装配的 app——static_pages 未传即走缺省七页产出+R57 编辑器区块注入的真实
    装配路径；scenario_dir 预置 seed_tone 场景（装配期卡片内嵌来源）。"""
    tmp_path = tmp_path_factory.mktemp("scenario_editor_e2e")
    sdir = tmp_path / "scenarios"
    sdir.mkdir()
    (sdir / "seed_tone.yaml").write_text(_SEED_YAML, encoding="utf-8")
    rroot = tmp_path / "reports"
    rroot.mkdir()
    result = serve_console(
        {
            "scenario_dir": str(sdir),
            "report_root": str(rroot),
            "port": 18124,  # dry_run 不真占用，仅形状合法
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
    thread = threading.Thread(target=server.run, daemon=True, name="scenario-editor-e2e")
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not server.started:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        pytest.fail("uvicorn 未能在 10s 内启动（e2e 前置失败）")
    yield {"base": f"http://127.0.0.1:{port}", "sdir": sdir}
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
def editor_page(browser):
    """普通浏览器页（编辑器与同源 API 交互，无外网依赖）+console error 收集。

    「Failed to load resource … 4xx」是浏览器对预期 400 响应的网络层日志
    （负路径用例有意触发，fetch 已正常处理），不计入 JS 错误。"""
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


def _api_card_names(page, base: str) -> list:
    """GET /api/scenarios 的场景名清单（服务端在册口径，浏览器上下文内请求）。"""
    resp = page.request.get(f"{base}/api/scenarios")
    assert resp.status == 200
    return [card["name"] for card in resp.json()["cards"]]


@needs_e2e
def test_scenario_editor_e2e_full_flow(console_server, editor_page):
    """R57 端到端主链路：区块在位→缺声明 400 逐条上屏→补全 201 新卡出现→
    PUT 编辑落盘→非法 YAML 400 上屏→DELETE 卡片消失（全程无 console error）。"""
    page, errors = editor_page
    base = console_server["base"]
    sdir = console_server["sdir"]

    # ---- ① 打开 /pages/index：编辑器区块在位+预置场景进目标下拉 ----
    resp = page.goto(f"{base}/pages/index", wait_until="load", timeout=10_000)
    assert resp is not None and resp.status == 200
    assert page.locator("#scenario-editor").count() == 1
    assert page.locator("#editor-panel-form").is_visible()
    assert page.locator("#editor-target option", has_text="seed_tone").count() == 1

    # ---- ② 表单模式故意缺安全声明（shielded_box/dut_scope 均不勾）提交 ----
    page.fill("#editor-name", "e2e_created")
    page.fill("#editor-f-fs", "1000000")
    page.click("#editor-btn-form-save")
    page.wait_for_selector("#editor-errors li", timeout=5_000)
    items = page.locator("#editor-errors li").all_text_contents()
    assert len(items) >= 2  # 逐条上屏：两条声明缺省各成一条（400 错误清单）
    assert any("shielded_box" in item for item in items)
    assert any("dut_scope" in item for item in items)
    assert "e2e_created" not in _api_card_names(page, base)  # 未落盘（400 拒绝）

    # ---- ③ 补全声明后提交 → 201 → 卡片区出现新卡+服务端落盘在册 ----
    page.check("#editor-f-shield")
    page.check("#editor-f-dut")
    page.click("#editor-btn-form-save")
    page.wait_for_selector("#editor-status.ok", timeout=5_000)
    assert "e2e_created" in page.locator("#editor-status").text_content()
    page.locator("#editor-cards .sce-card", has_text="e2e_created").wait_for(
        timeout=5_000
    )  # 成功后场景卡片刷新（区块卡片视图出现新卡）
    assert "e2e_created" in _api_card_names(page, base)
    assert (sdir / "e2e_created.yaml").is_file()

    # ---- ④ 编辑：目标下拉选中 e2e_created → 改描述 → PUT 覆写落盘 ----
    page.select_option("#editor-target", "e2e_created")
    page.fill("#editor-f-desc", "edited-by-e2e")
    page.click("#editor-btn-form-save")
    page.wait_for_selector("#editor-status.ok", timeout=5_000)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if "edited-by-e2e" in (sdir / "e2e_created.yaml").read_text(encoding="utf-8"):
            break
        time.sleep(0.05)
    assert "edited-by-e2e" in (sdir / "e2e_created.yaml").read_text(encoding="utf-8")

    # ---- ⑤ YAML 模式粘贴非法 YAML → 400 错误上屏（不吞错） ----
    page.select_option("#editor-target", "")
    page.fill("#editor-name", "e2e_bad_yaml")
    page.click("#editor-btn-mode-yaml")
    assert page.locator("#editor-panel-yaml").is_visible()
    page.fill("#editor-yaml", "style: [unclosed\nfs: 1e6\n")
    page.click("#editor-btn-yaml-save")
    page.wait_for_selector("#editor-errors li", timeout=5_000)
    yaml_items = page.locator("#editor-errors li").all_text_contents()
    assert any("YAML" in item for item in yaml_items)
    assert "e2e_bad_yaml" not in _api_card_names(page, base)  # 非法内容未落盘

    # ---- ⑥ 删除目标场景 → 卡片消失+服务端文件移除 ----
    page.select_option("#editor-target", "e2e_created")
    page.click("#editor-btn-delete")
    page.wait_for_selector("#editor-status.ok", timeout=5_000)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and page.locator(
        "#editor-cards .sce-card", has_text="e2e_created"
    ).count():
        time.sleep(0.05)
    assert page.locator("#editor-cards .sce-card", has_text="e2e_created").count() == 0
    assert "e2e_created" not in _api_card_names(page, base)
    assert not (sdir / "e2e_created.yaml").exists()

    assert errors == []  # 全程无 console error 级 JS 报错
