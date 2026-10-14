"""report_center_e2e：真服务+真跑两次最小 sim 运行的报告中心端到端（R61/R62
决定性防回归——用例名统一 test_report_center_e2e_ 前缀，`pytest -k
report_center_e2e` 整体发现本族）。

验收链（报告中心升级+跨轮对比视图）：
- 真运行×2：serve_console dry_run **缺省 runner**（真跑 sim 场景）→POST /api/run
  薄载荷×2（tone/bandlimited_noise 两场景，GB 阶梯中段档判据触发→各登记一条
  失效电平，dwell 0 秒级完成）→轮询至 done；
- 报告中心列表（R61）：GET /api/runs/summaries→200 两行（新建在前；行含时间/
  场景/样式/后端/状态/失效电平/报告相对路径/退出码）；
- 浏览器 /pages/reports→#run-list 元数据表格两行（时间/场景/样式/后端/状态/
  失效电平列）+「查看报告」链接→/pages/reports?run=<运行目录名>；
- 钻取（R60 共页协作）：链接进入报告页→#report-html 渲染在位（报告 200 可见）；
- 跨轮对比（R62）：POST /api/runs/compare→对比表+最薄弱样式结论；浏览器勾选
  run-list 两行→comparison 区出对比表+结论。

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

#: tone 场景（gb42590 快路径，dwell 0/judge 2/baseline 10——阶梯档位驱动 JSR 爬升：
#: signal −20 → −15dBm 档 jsr=+5 判据触发 → 失效电平登记 P_crit=−15dBm）。
_TONE_YAML = """\
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
signal_power_db: -20.0
link_power_db: -20.0
record: false
sim_events:
  - {type: power_step, achieved_db: -25.0, ts: 0.0}
  - {type: power_step, achieved_db: -20.0, ts: 1.0}
  - {type: power_step, achieved_db: -15.0, ts: 2.0}
bands:
  - [2400.0, 2483.5]
shielded_box: true
dut_scope: self_built
"""

#: bandlimited_noise 场景（同构但 signal/link −25：同 jsr=+5 判据在 −20dBm 档触发
#: → 失效电平 −20dBm≠tone 的 −15dBm——跨样式对比表无平手，最薄弱=noise）。
_NOISE_YAML = """\
style: bandlimited_noise
bandwidth_hz: 20000.0
fs: 1.0e6
freq_hz: 2.4e9
power_dbm: -10
duration_s: 0.005
backend: sim
scenario_type: gb42590
judge_min_samples: 2
dwell_s: 0.0
baseline_samples: 10
signal_power_db: -25.0
link_power_db: -25.0
record: false
sim_events:
  - {type: power_step, achieved_db: -30.0, ts: 0.0}
  - {type: power_step, achieved_db: -25.0, ts: 1.0}
  - {type: power_step, achieved_db: -20.0, ts: 2.0}
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


@pytest.fixture(scope="module")
def console_server(tmp_path_factory):
    """真服务（线程内 uvicorn.Server+config，随机端口）：serve_console dry_run
    **缺省 runner** 装配（不注入 runner——POST /api/run 即真跑 sim）；scenario_dir
    预置 tone/bandlimited_noise 两个判据触发场景。返回 {'base': http://…}。"""
    tmp_path = tmp_path_factory.mktemp("report_center_e2e")
    sdir = tmp_path / "scenarios"
    sdir.mkdir()
    (sdir / "tone_fail.yaml").write_text(_TONE_YAML, encoding="utf-8")
    (sdir / "noise_fail.yaml").write_text(_NOISE_YAML, encoding="utf-8")
    rroot = tmp_path / "reports"
    rroot.mkdir()
    result = serve_console(
        {
            "scenario_dir": str(sdir),
            "report_root": str(rroot),
            "port": 18128,  # dry_run 不真占用，仅形状合法
            "host": "127.0.0.1",
            "dry_run": True,
            "stop_flag": {"flag": False},
        }
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(result["app"], host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True, name="report-center-e2e")
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


def _run_one(base: str, scenario_name: str) -> "tuple[str, dict]":
    """真跑一次场景至终态，返回 (run 目录名, result)——run 目录名即报告中心 run_id。"""
    run_uuid = _post(base, "/api/run", {"scenario": {"name": scenario_name}})["run_id"]
    entry = None
    deadline = time.monotonic() + 90  # sim 快路径秒级，90s 足够宽
    while time.monotonic() < deadline:
        entry = _get_json(base, f"/api/runs/{run_uuid}")
        if entry["status"] != "running":
            break
        time.sleep(0.2)
    assert entry is not None and entry["status"] == "done"  # runner 线程收尾
    result = entry["result"]
    assert result["status"] == "failed"  # 判据真触发（失效电平登记的运行态）
    assert result["failure_levels"] >= 1
    return result["run_dir"].rstrip("/").split("/")[-1], result


@pytest.fixture(scope="module")
def real_runs(console_server):
    """顺序真跑两次（tone 先、noise 后——started_at 严格递增，列表序可断言），
    返回 [(run_name, result), …]。"""
    base = console_server["base"]
    tone = _run_one(base, "tone_fail")
    noise = _run_one(base, "noise_fail")
    return [tone, noise]


@needs_e2e
def test_report_center_e2e_summaries_api(console_server, real_runs):
    """R61 API 证据：GET /api/runs/summaries→200 两行（新建在前：noise 在首行），
    行含时间/场景/样式/后端/状态/失效电平/报告相对路径/退出码，不虚构。"""
    base = console_server["base"]
    (tone_name, tone_result), (noise_name, _) = real_runs
    payload = _get_json(base, "/api/runs/summaries")
    assert payload["count"] == 2
    rows = payload["summaries"]
    assert [row["run_id"] for row in rows] == [noise_name, tone_name]  # 新建在前

    noise_row, tone_row = rows
    # noise 行（首行=最新）：两行都判据触发 → status failed/exit 1/失效电平在案
    for row, style in ((noise_row, "bandlimited_noise"), (tone_row, "tone")):
        assert row["style"] == style
        assert row["scenario_name"] == "gb42590"
        assert row["backend"] == "SimBackend"
        assert row["status"] == "failed"
        assert row["exit_code"] == 1
        assert isinstance(row["started_at"], float)
        assert row["report_relpath"] == "report.md"  # 报告在位（钻取依据）
        levels = row["failure_levels"]
        assert len(levels) == 1 and isinstance(levels[0]["failure_level_db"], float)
    # 失效电平真实取值（判据触发档）：tone −15dBm / noise −20dBm
    assert tone_row["failure_levels"][0]["failure_level_db"] == -15.0
    assert noise_row["failure_levels"][0]["failure_level_db"] == -20.0


@needs_e2e
def test_report_center_e2e_compare_api(console_server, real_runs):
    """R62 API 证据：POST /api/runs/compare 两轮→对比表升序两行（noise −20 最薄弱）
    +薄弱环节结论（R26 口径透传）。"""
    base = console_server["base"]
    (tone_name, _), (noise_name, _) = real_runs
    view = _post(base, "/api/runs/compare", {"run_ids": [tone_name, noise_name]})
    assert view["run_ids"] == [tone_name, noise_name]
    assert view["degraded"] is False
    assert [row["style"] for row in view["comparison"]] == [
        "bandlimited_noise",
        "tone",
    ]
    assert view["comparison"][0]["median_level_db"] == -20.0
    assert view["weakest_style"] == "bandlimited_noise"
    assert "最薄弱样式为 bandlimited_noise" in view["conclusion"]
    assert view["entries"][0]["run_id"] == tone_name  # 条目携来源运行
    assert view["runs_without_failure"] == [] and view["missing_runs"] == []


@needs_e2e
def test_report_center_e2e_browser_list_drilldown_and_comparison(
    console_server, real_runs
):
    """浏览器证据：/pages/reports→run-list 元数据表格两行（R61）→「查看报告」
    钻取报告页渲染可见（R60 共页）→返回勾选两行→comparison 对比表+结论（R62）。"""
    base = console_server["base"]
    (tone_name, _), (noise_name, _) = real_runs
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page()
            # ---- ① 报告中心列表：元数据表格两行+查看报告链接 ----
            page.goto(f"{base}/pages/reports", timeout=15000)
            page.wait_for_selector("#run-list #run-summary-table", timeout=10000)
            rows = page.locator("#run-list #run-summary-table tbody tr")
            assert rows.count() == 2  # 真跑两次→两行（不虚构不剔除）
            first_run = rows.nth(0).get_attribute("data-run")
            assert first_run == noise_name  # 新建在前
            assert rows.nth(1).get_attribute("data-run") == tone_name
            # 行含选/时间/场景/样式/后端/状态/失效电平/操作 8 列（样式列 idx=3）
            assert rows.nth(0).locator("td").count() == 8
            assert rows.nth(0).locator("td[data-status='failed']").count() == 1
            styles = [rows.nth(i).locator("td").nth(3).inner_text() for i in range(2)]
            assert styles == ["bandlimited_noise", "tone"]

            # ---- ② 钻取：查看报告链接→报告页渲染可见（200 报告上屏） ----
            links = page.locator("#run-list a.view-report-link")
            assert links.count() == 2
            assert noise_name in links.first.get_attribute("href")
            page.wait_for_selector(
                "#run-list a.view-report-link >> text=查看报告"
            ).click()
            page.wait_for_selector("#report-view #report-html", timeout=10000)
            assert page.locator("#report-view #report-html").is_visible()
            assert page.locator("#report-view #report-html img").count() >= 1

            # ---- ③ 跨轮对比：回列表页勾选两行→对比表+结论 ----
            page.goto(f"{base}/pages/reports", timeout=15000)
            page.wait_for_selector("#run-list #run-summary-table", timeout=10000)
            boxes = page.locator("#run-list input.run-select")
            assert boxes.count() == 2
            boxes.nth(0).check()
            boxes.nth(1).check()
            page.click("#cmp-run")
            page.wait_for_selector("#comparison #comparison-table", timeout=10000)
            comp_rows = page.locator("#comparison #comparison-table tbody tr")
            assert comp_rows.count() == 2  # 两样式对比表
            first_style = comp_rows.nth(0).locator("td").nth(0).inner_text()
            assert first_style == "bandlimited_noise"  # 升序：最薄弱在首行
            conclusion = page.locator("#comparison #comparison-conclusion")
            assert conclusion.is_visible()
            assert "最薄弱样式为 bandlimited_noise" in conclusion.inner_text()
        finally:
            browser.close()
