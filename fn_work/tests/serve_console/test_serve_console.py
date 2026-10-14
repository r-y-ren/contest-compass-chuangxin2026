"""serve_console 对抗测试：dry_run 装配+TestClient 路由可达/uvicorn 拉起 mock+
缺库 ConsoleError pip 提示/端口占用拒（dry_run 不检）/config 形状错 ValueError。

用例名统一 test_console_api_ 前缀——`pytest -k console_api` 可整体发现本文件
用例（B19 三轴中#4 slug 可发现性修订）。

测试不真起服务：真拉起路径以 sys.modules 注入假 uvicorn（MagicMock 断言调用，
不真跑）；缺库路径以 sys.modules 注入 None（无论环境是否装有 uvicorn 均可复现）。
"""
import socket
import sys
import time
import types
from unittest.mock import MagicMock

import pytest

from src.localize_console_assets.mount_console_extensions import VENDOR_VUE_PATH
from src.serve_console.serve_console import ConsoleError, serve_console

try:  # TestClient 同源依赖 fastapi+httpx——任一缺失即整族 skip
    from fastapi.testclient import TestClient

    _HAS_TESTCLIENT = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_TESTCLIENT = False

needs_fastapi = pytest.mark.skipif(
    not _HAS_TESTCLIENT, reason="环境缺 fastapi/httpx——TestClient 不可用"
)


def _base_config(tmp_path):
    """合法最小 config（tmp 目录就位，显式端口避开缺省 8000 撞环境）。"""
    sdir = tmp_path / "scenarios"
    sdir.mkdir(exist_ok=True)
    rroot = tmp_path / "reports"
    rroot.mkdir(exist_ok=True)
    return {
        "scenario_dir": str(sdir),
        "report_root": str(rroot),
        "port": 8123,
        "host": "127.0.0.1",
        "stop_flag": {"flag": False},
    }


def _free_port() -> int:
    """取一个当前空闲的本地端口（bind(0) 后立即释放，探测窗口内可用）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


# ---- dry_run：装配不出网 ----


@needs_fastapi
def test_console_api_dry_run_returns_app_not_launched(tmp_path):
    """① dry_run=True→{'app', 'launched': False, 'port', 'host'}，不起服务。"""
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    result = serve_console(cfg)
    assert result["launched"] is False
    assert result["port"] == 8123
    assert result["host"] == "127.0.0.1"
    assert hasattr(result["app"], "state")  # create_console_app 产物（ASGI app）


@needs_fastapi
def test_console_api_dry_run_app_serves_scenarios_route(tmp_path):
    """② dry_run 返回的 app 可直接 TestClient 打 create 路由（/api/scenarios）。"""
    sdir = tmp_path / "scenarios"
    sdir.mkdir()  # 先落 yaml 再让 _base_config 的 mkdir 就位
    (sdir / "tone_demo.yaml").write_text(
        "# desc: 定频音演示\nstyle: tone\npower_dbm: -20\n", encoding="utf-8"
    )
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    result = serve_console(cfg)
    with TestClient(result["app"]) as client:
        resp = client.get("/api/scenarios")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["cards"][0]["name"] == "tone_demo"


@needs_fastapi
def test_console_api_default_port_when_omitted(tmp_path):
    """③ config 缺 port/host→缺省 8000/127.0.0.1 原样回显。"""
    cfg = _base_config(tmp_path)
    del cfg["port"]
    del cfg["host"]
    result = serve_console({**cfg, "dry_run": True})
    assert result["port"] == 8000
    assert result["host"] == "127.0.0.1"


@needs_fastapi
def test_console_api_default_runner_placeholder(tmp_path):
    """④ 未注入 runner→deps 里为真实运行器（可调用，缺省构造）——网页「开始」
    真跑测试（阻断①(b)）：不完整载荷 {'style':'tone'}（缺 fs）不再 noop 回执，
    而是真实校验失败回执 exit_code=2（run_scenario 真实返回值）。"""
    cfg = _base_config(tmp_path)
    assert "runner" not in cfg
    result = serve_console({**cfg, "dry_run": True})
    runner = result["app"].state.deps["runner"]
    assert callable(runner)
    receipt = runner({"style": "tone"})
    assert receipt["status"] == "validation_failed"  # 真实校验（缺 fs → exit 2 口径）
    assert receipt["exit_code"] == 2
    assert "fs" in receipt["error"]


@needs_fastapi
def test_console_api_shared_stop_flag_wired_by_identity(tmp_path):
    """⑤ config['stop_flag'] 原对象直通 app.state.deps（/api/stop 与急停共享）。"""
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    result = serve_console(cfg)
    assert result["app"].state.deps["stop_flag"] is cfg["stop_flag"]


# ---- 真拉起：mock uvicorn，不真跑 ----


@needs_fastapi
def test_console_api_readme_way3_out_of_box(tmp_path, monkeypatch):
    """README 方式三开箱即用回归（阻断A）：缺省命令原样可跑——

    不预建 scenarios/ 目录、不传 static_pages、dry_run=True+TestClient：
    ① scenario_dir 缺失→自动建空目录（相对 cwd）；② static_pages 未传→七页
    产出注入（R56 改造：localize_console_assets 缺省骨架+render_console_pages
    运行页经 CDN→vendor 切换——全站零 CDN，断网全可用；旧断言 unpkg CDN 注入
    随本改造同步废止）；③ /pages/index 无后缀回退 index.html → 200 含本地
    vendor script；/api/scenarios 200 空卡（不再 400）。
    """
    import os

    monkeypatch.chdir(tmp_path)  # README 'cd fn_work' 等价：相对 cwd 的 scenarios/
    result = serve_console(
        {"scenario_dir": "scenarios", "report_root": "runs", "port": 18123, "dry_run": True}
    )
    assert result["launched"] is False
    assert os.path.isdir(tmp_path / "scenarios")  # ① 缺失目录自动建
    # ② 七页产出注入（键带 .html 后缀；B23-F3：vendor 不落盘 scenarios/——
    # /assets/vendor 路由恒服务仓内文件，死副本无人消费）
    assert set(result["app"].state.deps["static_pages"]) == {
        f"{slug}.html"
        for slug in (
            "overview", "index", "reports", "data", "ai", "instruments", "ledger",
        )
    }
    assert not (tmp_path / "scenarios" / "vendor").exists()
    with TestClient(result["app"]) as client:
        page = client.get("/pages/index")  # ③ 无后缀名 → index.html 回退
        overview = client.get("/pages/overview")  # 骨架页同经 /pages 托管
        cards = client.get("/api/scenarios")
        miss = client.get("/api/runs")  # report_root 未建：仍按原口径 400（不在本修范围）
    assert page.status_code == 200
    assert "vue.global.prod.js" in page.text  # 本地 vendor script 注入
    assert "unpkg.com" not in page.text  # 零 CDN（R56 断网全可用）
    assert overview.status_code == 200 and 'id="console-nav"' in overview.text
    assert cards.status_code == 200  # 空目录不再 400
    assert cards.json() == {"cards": [], "count": 0}
    assert miss.status_code == 400


@needs_fastapi
def test_console_api_default_assembly_no_vendor_copy_in_scenario_dir(tmp_path):
    """B23-F3 回归：tmp scenario_dir 缺省装配→不向 scenario_dir 落 vendor 死副本
    （157KB 白写无人消费——路由恒服务仓内文件）；vendor 路由仍 200 且逐字节
    对拍仓内源文件（断网全可用不受影响）。"""
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    result = serve_console(cfg)
    assert not (tmp_path / "scenarios" / "vendor").exists()  # 零 vendor 落盘
    with TestClient(result["app"]) as client:
        resp = client.get("/assets/vendor/vue.global.prod.js")
    assert resp.status_code == 200  # 路由照常服务仓内文件
    assert resp.content == VENDOR_VUE_PATH.read_bytes()


@needs_fastapi
def test_console_api_explicit_static_pages_not_overridden(tmp_path):
    """显式 static_pages 原样直通（不触发自动渲染注入）。"""
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    cfg["static_pages"] = {"custom.html": "<html>custom</html>"}
    result = serve_console(cfg)
    assert result["app"].state.deps["static_pages"] == {"custom.html": "<html>custom</html>"}


@needs_fastapi
def test_console_api_default_index_injects_scenario_editor(tmp_path):
    """R57 wired 回归：缺省装配的 index 运行页注入场景编辑器区块（serve_console
    运行页区块挂载点）——区块根 id+CRUD 接线+装配期场景卡片内嵌均在位；
    显式 static_pages 直通则不注入（区块注入仅缺省七页产出路径）。"""
    sdir = tmp_path / "scenarios"
    sdir.mkdir()
    (sdir / "tone_seed.yaml").write_text(
        "style: tone\nfs: 1.0e6\npower_dbm: -20\nbands:\n  - [2400.0, 2483.5]\n"
        "shielded_box: true\ndut_scope: self_built\n",
        encoding="utf-8",
    )
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    result = serve_console(cfg)
    with TestClient(result["app"]) as client:
        page = client.get("/pages/index").text
        skeleton = client.get("/pages/overview").text  # 其余六页不受注入影响
    assert 'id="scenario-editor"' in page
    assert "method: 'PUT'" in page and "method: 'DELETE'" in page  # CRUD 接线在位
    assert '<option value="tone_seed">' in page  # 装配期卡片进目标下拉
    assert 'id="scenario-editor"' not in skeleton

    cfg2 = _base_config(tmp_path)
    cfg2["dry_run"] = True
    cfg2["static_pages"] = {"index.html": "<html><body>x</body></html>"}
    result2 = serve_console(cfg2)
    with TestClient(result2["app"]) as client2:
        page2 = client2.get("/pages/index").text
    assert "scenario-editor" not in page2  # 显式直通：不注入


@needs_fastapi
def test_console_api_default_reports_page_injects_report_view_area(tmp_path):
    """R60 wired 回归：缺省装配的 reports 页注入报告查看区（serve_console 报告
    阅读视图挂载点——?run=<id> 驱动 fetch /api/runs/{id}/report 渲染+plots 图
    列表+files 下载链接+溯源徽标）；区块根 id+fetch 接线在位且零外链；其余骨架
    页不受注入影响；显式 static_pages 直通则不注入（同 R57 口径）。"""
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    result = serve_console(cfg)
    with TestClient(result["app"]) as client:
        page = client.get("/pages/reports").text
        overview = client.get("/pages/overview").text
    assert 'id="report-view-area"' in page
    assert "'/api/runs/' + encodeURIComponent(runId)" in page  # fetch 接线在位
    assert "'/report'" in page and "'/files/' + fname" in page  # 三端点消费
    assert "traceability-badge" in page  # 溯源徽标透显接线
    assert "http://" not in page and "https://" not in page  # 零外链
    assert 'id="report-view-area"' not in overview  # 其余骨架页不受影响

    cfg2 = _base_config(tmp_path)
    cfg2["dry_run"] = True
    cfg2["static_pages"] = {"reports.html": "<html><body>x</body></html>"}
    result2 = serve_console(cfg2)
    with TestClient(result2["app"]) as client2:
        page2 = client2.get("/pages/reports").text
    assert "report-view-area" not in page2  # 显式直通：不注入


@needs_fastapi
def test_console_api_default_ai_page_injects_train_eval_infer_areas(tmp_path):
    """R65/R66/R67 wired 回归：缺省装配的 ai 页注入训练/评估/推理三页区
    （train-panel/eval-panel/infer-panel 挂载点——三区块根 id+/api/ai/* 端点
    接线在位且零外链）；其余骨架页不受注入影响；显式 static_pages 直通则
    不注入（同 R57/R60 口径）。"""
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    result = serve_console(cfg)
    with TestClient(result["app"]) as client:
        page = client.get("/pages/ai").text
        overview = client.get("/pages/overview").text
    assert 'id="train-panel-area"' in page  # R65 训练面板
    assert 'id="eval-panel-area"' in page  # R66 评估面板
    assert 'id="infer-panel-area"' in page  # R67 推理面板
    assert "'/api/ai/train'" in page and "'/api/ai/models'" in page  # R65 端点接线
    assert "'/api/ai/evaluate'" in page  # R66 端点接线
    assert "'/api/ai/infer'" in page  # R67 端点接线
    assert "http://" not in page and "https://" not in page  # 零外链
    assert "train-panel-area" not in overview  # 其余骨架页不受影响

    cfg2 = _base_config(tmp_path)
    cfg2["dry_run"] = True
    cfg2["static_pages"] = {"ai.html": "<html><body>x</body></html>"}
    result2 = serve_console(cfg2)
    with TestClient(result2["app"]) as client2:
        page2 = client2.get("/pages/ai").text
    assert "train-panel-area" not in page2  # 显式直通：不注入


@needs_fastapi
def test_console_api_default_pages_inject_calibration_and_ledger_audit_areas(tmp_path):
    """R70/R71 wired 回归：缺省装配的 instruments 页注入标定看板区（instrument
    挂载点附近——calibration-status 区块：三件只读看板+合成演示一键走，GET
    /api/calibration 接线在位且零外链）、ledger 页注入台账审计页区
    （ledger-audit 区块——audit-report/ledger-detail 挂载点，GET /api/ledger/audit
    只读接线在位）；其余骨架页不受注入影响；显式 static_pages 直通则不注入
    （同 R57/R60 口径）。"""
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    result = serve_console(cfg)
    with TestClient(result["app"]) as client:
        instruments = client.get("/pages/instruments").text
        ledger = client.get("/pages/ledger").text
        overview = client.get("/pages/overview").text
    # R70 标定页区（instruments 页）
    assert 'id="calibration-status-area"' in instruments
    assert "'/api/calibration'" in instruments  # 看板 fetch 接线在位
    assert "'/api/calibration?demo=1'" in instruments  # 合成演示触发接线
    assert "合成数据演示" in instruments and "只读" in instruments
    # R71 台账审计页区（ledger 页）
    assert 'id="ledger-audit-area"' in ledger
    assert "'/api/ledger/audit'" in ledger  # 只读审计 fetch 接线在位
    assert "audit-report" in ledger and "ledger-detail" in ledger  # 两挂载点消费
    assert "无写清单入口" in ledger or "只读" in ledger
    # 零外链+其余骨架页不受影响
    for page in (instruments, ledger):
        assert "http://" not in page and "https://" not in page
    assert "calibration-status-area" not in overview
    assert "ledger-audit-area" not in overview

    cfg2 = _base_config(tmp_path)
    cfg2["dry_run"] = True
    cfg2["static_pages"] = {
        "instruments.html": "<html><body>x</body></html>",
        "ledger.html": "<html><body>y</body></html>",
    }
    result2 = serve_console(cfg2)
    with TestClient(result2["app"]) as client2:
        page2 = client2.get("/pages/instruments").text
        page3 = client2.get("/pages/ledger").text
    assert "calibration-status-area" not in page2  # 显式直通：不注入
    assert "ledger-audit-area" not in page3


@needs_fastapi
def test_console_api_default_instruments_page_injects_demo_three_areas(tmp_path):
    """R72/R73/R74 wired 回归：缺省装配的 instruments 页注入二期演示三页区
    （sitl-bridge SITL 桥 dry_run 映射预览区+rl-policy sim 冒烟区+rff-pipeline
    管道 smoke 区——三区块根 id+/api/demo/sitl|rl|rff 端点接线在位且零外链）；
    其余骨架页不受注入影响；显式 static_pages 直通则不注入（同 R57/R60 口径）。"""
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    result = serve_console(cfg)
    with TestClient(result["app"]) as client:
        instruments = client.get("/pages/instruments").text
        overview = client.get("/pages/overview").text
        ledger = client.get("/pages/ledger").text
    # R72 SITL 桥演示页区（instruments 页）
    assert 'id="sitl-bridge-area"' in instruments
    assert "'/api/demo/sitl'" in instruments  # dry_run 映射预览 fetch 接线
    assert "映射预览" in instruments and "run_id" in instruments
    # R73 RL 策略演示页区（instruments 页）
    assert 'id="rl-policy-area"' in instruments
    assert "'/api/demo/rl'" in instruments  # sim 冒烟 fetch 接线
    assert "reward_history" in instruments and "fallback" in instruments.lower()
    # R74 RFF 管道演示页区（instruments 页）
    assert 'id="rff-pipeline-area"' in instruments
    assert "'/api/demo/rff'" in instruments  # smoke fetch 接线
    assert "阶段进度" in instruments and "产物清单" in instruments
    # 零外链+其余骨架页不受影响
    assert "http://" not in instruments and "https://" not in instruments
    for page in (overview, ledger):
        assert "sitl-bridge-area" not in page
        assert "rl-policy-area" not in page
        assert "rff-pipeline-area" not in page

    cfg2 = _base_config(tmp_path)
    cfg2["dry_run"] = True
    cfg2["static_pages"] = {"instruments.html": "<html><body>x</body></html>"}
    result2 = serve_console(cfg2)
    with TestClient(result2["app"]) as client2:
        page2 = client2.get("/pages/instruments").text
    assert "sitl-bridge-area" not in page2  # 显式直通：不注入
    assert "rl-policy-area" not in page2
    assert "rff-pipeline-area" not in page2


@needs_fastapi
def test_console_api_scenario_dir_uncreatable_console_error(tmp_path):
    """scenario_dir 不可创建（父为文件）→ConsoleError 指明路径（不静默 400 路由）。"""
    blocker = tmp_path / "afile"
    blocker.write_text("not a dir", encoding="utf-8")
    with pytest.raises(ConsoleError) as ei:
        serve_console(
            {
                "scenario_dir": str(blocker / "scenarios"),
                "report_root": str(tmp_path / "runs"),
                "port": 8123,
                "dry_run": True,
            }
        )
    assert "scenario_dir" in str(ei.value)


@pytest.mark.skipif(not _HAS_TESTCLIENT, reason="环境缺 fastapi/httpx——TestClient 不可用")
def test_console_api_real_launch_invokes_uvicorn_run(tmp_path, monkeypatch):
    """⑥ 真拉起：假 uvicorn.run 被调一次（app+host+port），返回 launched True。"""
    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = MagicMock()
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    cfg = _base_config(tmp_path)
    cfg["port"] = _free_port()
    result = serve_console(cfg)
    assert result["launched"] is True
    assert result["port"] == cfg["port"]
    fake_uvicorn.run.assert_called_once()
    args, kwargs = fake_uvicorn.run.call_args
    assert args[0] is not None  # 位置参数即 ASGI app
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == cfg["port"]


@pytest.mark.skipif(not _HAS_TESTCLIENT, reason="环境缺 fastapi/httpx——TestClient 不可用")
def test_console_api_missing_uvicorn_console_error_pip_hint(tmp_path, monkeypatch):
    """⑦ uvicorn 缺库（sys.modules 注入 None）→ConsoleError 且消息含 pip 提示。"""
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    cfg = _base_config(tmp_path)
    cfg["port"] = _free_port()
    with pytest.raises(ConsoleError) as ei:
        serve_console(cfg)
    assert "pip" in str(ei.value)


# ---- 端口占用 ----


@pytest.mark.skipif(not _HAS_TESTCLIENT, reason="环境缺 fastapi/httpx——TestClient 不可用")
def test_console_api_port_in_use_raises_console_error(tmp_path):
    """⑧ 端口被占→ConsoleError（消息含端口号）；检查先于 uvicorn import。"""
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    cfg = _base_config(tmp_path)
    cfg["port"] = blocker.getsockname()[1]
    try:
        with pytest.raises(ConsoleError) as ei:
            serve_console(cfg)
        assert str(cfg["port"]) in str(ei.value)
    finally:
        blocker.close()


@needs_fastapi
def test_console_api_dry_run_skips_port_check(tmp_path):
    """⑨ 端口被占但 dry_run=True→不检端口，正常返回装配结果。"""
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    cfg = _base_config(tmp_path)
    cfg["port"] = blocker.getsockname()[1]
    cfg["dry_run"] = True
    try:
        result = serve_console(cfg)
        assert result["launched"] is False
        assert result["port"] == cfg["port"]
    finally:
        blocker.close()


# ---- config 形状 ----


@pytest.mark.parametrize("bad", [None, "8000", 8000, [("port", 1)], set()])
def test_console_api_config_not_dict_valueerror(bad):
    """⑩ config 非 dict→ValueError。"""
    with pytest.raises(ValueError, match="config"):
        serve_console(bad)


def _drop_scenario_dir(cfg):
    del cfg["scenario_dir"]


def _bad_scenario_dir(cfg):
    cfg["scenario_dir"] = 123


def _bad_report_root(cfg):
    cfg["report_root"] = ""


def _port_str(cfg):
    cfg["port"] = "8123"


def _port_bool(cfg):
    cfg["port"] = True


def _port_zero(cfg):
    cfg["port"] = 0


def _port_overflow(cfg):
    cfg["port"] = 70000


def _dry_run_str(cfg):
    cfg["dry_run"] = "yes"


def _runner_not_callable(cfg):
    cfg["runner"] = "not-callable"


def _stop_flag_list(cfg):
    cfg["stop_flag"] = ["flag"]


def _static_pages_list(cfg):
    cfg["static_pages"] = [("index.html", "x")]


@pytest.mark.parametrize(
    "mutate",
    [
        _drop_scenario_dir,
        _bad_scenario_dir,
        _bad_report_root,
        _port_str,
        _port_bool,
        _port_zero,
        _port_overflow,
        _dry_run_str,
        _runner_not_callable,
        _stop_flag_list,
        _static_pages_list,
    ],
)
def test_console_api_bad_config_fields_valueerror(tmp_path, mutate):
    """⑪ 各键形状错（缺路径/类型不符/端口越界/runner 不可调用…）→ValueError 指错键。"""
    cfg = _base_config(tmp_path)
    mutate(cfg)
    with pytest.raises(ValueError):
        serve_console(cfg)


# ---- stop 复位（B19 对抗中#2：新 run 不吃旧停机信号） ----


@needs_fastapi
def test_console_api_new_run_resets_stale_stop_flag(tmp_path):
    """⑫ /api/stop 置旗后新 POST /api/run→启动即复位共享停旗（flag=False），
    下一轮运行不再吃到上一轮的停机信号（runner 启动时刻快照为证）。"""
    seen: dict = {}

    def runner(scenario):
        seen["flag_at_start"] = cfg["stop_flag"]["flag"]
        return {"ok": True}

    cfg = _base_config(tmp_path)
    cfg["runner"] = runner
    cfg["dry_run"] = True
    result = serve_console(cfg)
    with TestClient(result["app"]) as client:
        stop_resp = client.post("/api/stop")  # 上一轮遗留停机信号
        assert stop_resp.json()["stopped"] is True  # R59 后另携 'emergency_stop' 键
        assert cfg["stop_flag"]["flag"] is True
        run_resp = client.post("/api/run", json={"scenario": {"style": "tone"}})
    assert run_resp.status_code == 202
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and "flag_at_start" not in seen:
        time.sleep(0.01)  # 等 runner 启动快照（线程调度时差容忍）
    assert seen["flag_at_start"] is False  # 新 run 启动时旗标已复位


# ---- 网页「开始」真跑测试（阻断①：缺省 runner=真实运行器） ----


#: 端到端场景文件（gb42590 快路径：dwell 0/judge 2/baseline 10，sim 事件缺省
#: jsr=-20 不触发判据 → completed）——与 run_demo 场景文件路线同形状。
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


@needs_fastapi
def test_console_api_start_button_real_run_end_to_end(tmp_path):
    """阻断① 端到端回归：网页「开始」真跑测试——

    TestClient 起服（dry_run）→ scenario_dir 放场景文件 → POST /api/run 薄载荷
    {name, power_dbm} → 轮询 /api/runs/{id} 至 done → result 为真实运行结果
    （status completed/exit_code 0），report_root 下 run 目录+report.md 真实生成
    （文件存在断言）。修复前缺省 runner 为 noop 占位——「开始」从不跑测试。
    """
    from pathlib import Path

    cfg = _base_config(tmp_path)
    (tmp_path / "scenarios" / "gb_fast.yaml").write_text(_GB_FAST_YAML, encoding="utf-8")
    cfg["dry_run"] = True
    result = serve_console(cfg)
    with TestClient(result["app"]) as client:
        resp = client.post(
            "/api/run", json={"scenario": {"name": "gb_fast", "power_dbm": -20}}
        )
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]
        entry = None
        deadline = time.monotonic() + 60  # sim 快路径秒级，60s 足够宽
        while time.monotonic() < deadline:
            got = client.get(f"/api/runs/{run_id}")
            assert got.status_code == 200
            entry = got.json()
            if entry["status"] != "running":
                break
            time.sleep(0.2)
        assert entry is not None and entry["status"] == "done"  # runner 真实返回
    res = entry["result"]  # /api/runs/{id} 的 result 即真实运行结果
    assert res["status"] == "completed"
    assert res["exit_code"] == 0
    report = Path(res["report_path"])
    assert report.name == "report.md" and report.is_file()  # 报告真实生成
    run_dir = Path(res["run_dir"])
    assert run_dir.is_dir()
    assert str(run_dir).startswith(str(tmp_path / "reports"))  # report_root 落位


@needs_fastapi
def test_console_api_explicit_runner_not_overridden(tmp_path):
    """阻断① 补充：config['runner'] 显式注入→原对象直通（真实运行器不越权覆盖）。"""
    cfg = _base_config(tmp_path)
    cfg["runner"] = lambda scenario: {"echo": scenario}
    cfg["dry_run"] = True
    result = serve_console(cfg)
    assert result["app"].state.deps["runner"] is cfg["runner"]  # 同一对象身份


# ---- B24 C1：缺省 runner 急停接线（stop 容器贯通 + run_ctx 注册） ----


@needs_fastapi
def test_console_api_default_runner_threads_shared_stop_into_run_scenario(
    tmp_path, monkeypatch
):
    """B24 C1 接线回归：缺省 runner 把共享停容器（config['stop_flag'] 原对象）
    经 run_scenario(stop=…) 贯通管线协作停——猴补 run_scenario 捕获 kwargs 证
    同一性；run_ctx 注册进 deps 并直通 app.state.run_ctx（含 backend 通道）。"""
    import src.serve_console.serve_console as svs

    seen: dict = {}

    def fake_run_scenario(scenario, **kwargs):
        seen["stop"] = kwargs.get("stop")
        return {"status": "completed", "exit_code": 0, "run_dir": None,
                "report_path": None, "failure_levels": 0, "summary": "stub"}

    monkeypatch.setattr(svs, "run_scenario", fake_run_scenario)
    cfg = _base_config(tmp_path)  # 先建目录再落场景文件
    cfg["dry_run"] = True
    (tmp_path / "scenarios" / "gb_stub.yaml").write_text(_GB_FAST_YAML, encoding="utf-8")
    result = serve_console(cfg)
    with TestClient(result["app"]) as client:
        resp = client.post("/api/run", json={"scenario": {"name": "gb_stub"}})
        assert resp.status_code == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "stop" not in seen:
            time.sleep(0.02)
    assert seen["stop"] is cfg["stop_flag"]  # 共享停容器原对象贯通（/api/stop 同一 dict）
    # run_ctx 注册：deps 与 app.state.run_ctx 同一对象（backend 通道容器）
    assert result["app"].state.deps["run_ctx"] is result["app"].state.run_ctx
