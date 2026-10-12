"""create_console_app 对抗测试：五路由合约（scenarios/run 202/runs/stop/ledger）、
非法 body 400 字段指错、deps 缺键/类型拒、缺 fastapi→AppError pip 提示、WS 握手。

环境缺 fastapi（或 httpx）时 TestClient 族用例自动 skip——AppError 缺库路径用
sys.modules 注入 None 独立覆盖（不依赖环境是否装了 fastapi）。
"""
from __future__ import annotations

import sys
import threading
import time

import pytest

from src.serve_console.create_console_app import AppError, create_console_app

try:  # TestClient 同源依赖 fastapi+httpx——任一缺失即整族 skip
    from fastapi.testclient import TestClient

    _HAS_TESTCLIENT = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_TESTCLIENT = False

needs_fastapi = pytest.mark.skipif(
    not _HAS_TESTCLIENT, reason="环境缺 fastapi/httpx——TestClient 不可用"
)


def _base_deps(tmp_path, runner=None):
    """合法五键 deps（tmp 目录就位），runner 缺省为回显假件。"""
    sdir = tmp_path / "scenarios"
    sdir.mkdir(exist_ok=True)
    rroot = tmp_path / "reports"
    rroot.mkdir(exist_ok=True)
    return {
        "runner": runner if runner is not None else (lambda scenario: {"echo": scenario}),
        "stop_flag": {"flag": False},
        "scenario_dir": str(sdir),
        "report_root": str(rroot),
        "static_pages": None,
    }


def _wait_status(app, run_id, want, timeout=3.0):
    """轮询后台运行表至目标状态（线程调度时差容忍）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if app.state.runs.get(run_id, {}).get("status") == want:
            return True
        time.sleep(0.01)
    return False


# ---- deps 契约（不依赖 fastapi，工厂校验先于延迟 import） ----


@pytest.mark.parametrize(
    "missing",
    ["runner", "stop_flag", "scenario_dir", "report_root", "static_pages"],
)
def test_deps_missing_key_rejected(tmp_path, missing):
    """① 五必需键逐一缺失→AppError，消息点名缺失键。"""
    deps = _base_deps(tmp_path)
    del deps[missing]
    with pytest.raises(AppError) as ei:
        create_console_app(deps)
    assert missing in str(ei.value)


def test_deps_not_dict_rejected():
    """② deps 非 dict（None/str）→AppError 指错 deps。"""
    with pytest.raises(AppError) as ei:
        create_console_app(None)
    assert "deps" in str(ei.value)


def test_deps_runner_not_callable_rejected(tmp_path):
    """③ runner 不可调用→AppError 指错 runner。"""
    deps = _base_deps(tmp_path)
    deps["runner"] = "not-callable"
    with pytest.raises(AppError) as ei:
        create_console_app(deps)
    assert ei.value.field == "runner"


def test_deps_stop_flag_not_dict_rejected(tmp_path):
    """④ stop_flag 非共享 dict→AppError 指错 stop_flag。"""
    deps = _base_deps(tmp_path)
    deps["stop_flag"] = ["flag"]
    with pytest.raises(AppError) as ei:
        create_console_app(deps)
    assert ei.value.field == "stop_flag"


def test_apperror_is_valueerror():
    """⑤ AppError 为 ValueError 子类（规约口径）。"""
    assert issubclass(AppError, ValueError)


def test_fastapi_missing_raises_apperror_with_pip_hint(tmp_path, monkeypatch):
    """⑥ fastapi 缺库（sys.modules 注入 None 模拟）→AppError 且消息含 pip 提示。"""
    monkeypatch.setitem(sys.modules, "fastapi", None)
    with pytest.raises(AppError) as ei:
        create_console_app(_base_deps(tmp_path))
    assert "pip" in str(ei.value)


# ---- 路由合约（TestClient 族：缺 fastapi/httpx 自动 skip） ----


@needs_fastapi
def test_app_created_with_hub_and_runs_state(tmp_path):
    """⑦ 合法 deps→app 就位，state 携 hub dict（sockets/history/broadcast）与运行表。"""
    app = create_console_app(_base_deps(tmp_path))
    hub = app.state.hub
    assert isinstance(hub, dict)
    assert set(hub) >= {"sockets", "history", "broadcast"}
    assert callable(hub["broadcast"])
    assert app.state.runs == {}


@needs_fastapi
def test_get_scenarios_lists_cards(tmp_path):
    """⑧ GET /api/scenarios：目录内 yaml→卡片数据（name/style/risk/backend_hint）。"""
    sdir = tmp_path / "scenarios"
    sdir.mkdir()  # 先建目录再落 yaml（_base_deps 的 mkdir 在其后才执行）
    (sdir / "tone_demo.yaml").write_text(
        "# desc: 定频音干扰演示\nstyle: tone\nbackend: sim\npower_dbm: -10\n",
        encoding="utf-8",
    )
    (sdir / "noise_mid.yaml").write_text(
        "# desc: 带限噪声\nstyle: noise\npower_dbm: -5\n", encoding="utf-8"
    )
    app = create_console_app(_base_deps(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/api/scenarios")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    cards = {c["name"]: c for c in body["cards"]}
    assert cards["tone_demo"]["style_tags"] == ["tone"]
    assert cards["tone_demo"]["desc"] == "定频音干扰演示"
    assert cards["noise_mid"]["risk"] == "mid"  # -5dBm 高于 -10 分档线


@needs_fastapi
def test_get_scenarios_missing_dir_400_with_field(tmp_path):
    """⑨ scenario_dir 不存在→400 且 detail.field 指错 scenario_dir。"""
    deps = _base_deps(tmp_path)
    deps["scenario_dir"] = str(tmp_path / "nope")
    app = create_console_app(deps)
    with TestClient(app) as client:
        resp = client.get("/api/scenarios")
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "scenario_dir"


@needs_fastapi
def test_post_run_returns_202_and_runs_in_background(tmp_path):
    """⑩ POST /api/run 合约：202+run_id，runner 后台线程执行且共享 stop_flag 可达。"""
    started = threading.Event()

    def runner(scenario):
        started.set()
        return {"echo": scenario, "flag_seen": deps["stop_flag"]["flag"]}

    deps = _base_deps(tmp_path, runner=runner)
    app = create_console_app(deps)
    scenario = {"style": "tone", "fs": 2.0e6}
    with TestClient(app) as client:
        resp = client.post("/api/run", json={"scenario": scenario})
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    assert isinstance(run_id, str) and run_id
    assert started.wait(3)
    assert _wait_status(app, run_id, "done")
    assert app.state.runs[run_id]["result"]["echo"] == scenario


@needs_fastapi
def test_post_run_missing_scenario_400(tmp_path):
    """⑪ body 缺 scenario→400 field='scenario'。"""
    app = create_console_app(_base_deps(tmp_path))
    with TestClient(app) as client:
        resp = client.post("/api/run", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "scenario"


@needs_fastapi
def test_post_run_scenario_not_dict_400(tmp_path):
    """⑫ scenario 非 dict→400 field='scenario'。"""
    app = create_console_app(_base_deps(tmp_path))
    with TestClient(app) as client:
        resp = client.post("/api/run", json={"scenario": 42})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "scenario"


@needs_fastapi
def test_post_run_body_not_json_400(tmp_path):
    """⑬ body 非 JSON 对象（文本/数组）→400 field='body'。"""
    app = create_console_app(_base_deps(tmp_path))
    with TestClient(app) as client:
        resp_text = client.post(
            "/api/run", content="oops", headers={"Content-Type": "application/json"}
        )
        resp_arr = client.post("/api/run", json=[1, 2])
    assert resp_text.status_code == 400
    assert resp_text.json()["detail"]["field"] == "body"
    assert resp_arr.status_code == 400
    assert resp_arr.json()["detail"]["field"] == "body"


@needs_fastapi
def test_post_stop_sets_shared_flag(tmp_path):
    """⑭ POST /api/stop→{'stopped': True} 且共享 stop_flag['flag'] 置位。"""
    deps = _base_deps(tmp_path)
    app = create_console_app(deps)
    with TestClient(app) as client:
        resp = client.post("/api/stop")
    assert resp.status_code == 200
    assert resp.json() == {"stopped": True}
    assert deps["stop_flag"]["flag"] is True


@needs_fastapi
def test_get_runs_lists_report_dirs_newest_first(tmp_path):
    """⑮ GET /api/runs：report_root 子目录列表（倒序），散文件不计。"""
    root = tmp_path / "reports"
    root.mkdir()  # 先建根目录再落子目录/散文件（_base_deps 的 mkdir 在其后才执行）
    (root / "run-a").mkdir()
    (root / "run-b").mkdir()
    (root / " stray.txt").write_text("x", encoding="utf-8")
    app = create_console_app(_base_deps(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/api/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"runs": ["run-b", "run-a"], "count": 2}


@needs_fastapi
def test_get_runs_missing_root_400_with_field(tmp_path):
    """⑯ report_root 不存在→400 field='report_root'。"""
    deps = _base_deps(tmp_path)
    deps["report_root"] = str(tmp_path / "absent")
    app = create_console_app(deps)
    with TestClient(app) as client:
        resp = client.get("/api/runs")
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "report_root"


@needs_fastapi
def test_get_ledger_counts_done_total(tmp_path):
    """⑰ GET /api/ledger：✅/wired 行计 done，条目行计 total（▶ 变体同口径）。"""
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        "# 台账\n"
        "| 编号 | 功能 | 状态 |\n"
        "| --- | --- | --- |\n"
        "| A1 | 甲 | ✅ 10-01 fn(x) |\n"
        "| A2 | 乙 |  |\n"
        "| ▶ C2 | 丙 | wired 演示 |\n"
        "非表格普通行\n",
        encoding="utf-8",
    )
    deps = _base_deps(tmp_path)
    deps["ledger_path"] = str(ledger)
    app = create_console_app(deps)
    with TestClient(app) as client:
        resp = client.get("/api/ledger")
    body = resp.json()
    assert body["done"] == 2 and body["total"] == 3 and body["available"] is True


@needs_fastapi
def test_get_ledger_missing_file_returns_zeros(tmp_path):
    """⑱ 清单文件缺失→200 零值+available False（查询不炸）。"""
    deps = _base_deps(tmp_path)
    deps["ledger_path"] = str(tmp_path / "absent.md")
    app = create_console_app(deps)
    with TestClient(app) as client:
        resp = client.get("/api/ledger")
    assert resp.status_code == 200
    assert resp.json() == {
        "done": 0,
        "total": 0,
        "available": False,
        "path": str(tmp_path / "absent.md"),
    }


@needs_fastapi
def test_run_failure_recorded_not_crash_service(tmp_path):
    """⑲ runner 抛异常→运行表记 failed 含原因，服务与后续请求不受影响。"""
    def bad_runner(scenario):
        raise RuntimeError("boom-in-runner")

    app = create_console_app(_base_deps(tmp_path, runner=bad_runner))
    with TestClient(app) as client:
        resp = client.post("/api/run", json={"scenario": {"style": "tone"}})
        run_id = resp.json()["run_id"]
        assert _wait_status(app, run_id, "failed")
        assert "RuntimeError" in app.state.runs[run_id]["error"]
        assert client.get("/api/runs").status_code == 200  # 服务仍活


@needs_fastapi
def test_static_pages_served_and_404(tmp_path):
    """⑳ static_pages 资产：str→HTML、dict→JSON、缺名→404。"""
    deps = _base_deps(tmp_path)
    deps["static_pages"] = {"index.html": "<html>console</html>", "meta.json": {"v": 1}}
    app = create_console_app(deps)
    with TestClient(app) as client:
        html = client.get("/pages/index.html")
        meta = client.get("/pages/meta.json")
        miss = client.get("/pages/nope.html")
    assert html.status_code == 200 and "console" in html.text
    assert "text/html" in html.headers["content-type"]
    assert meta.status_code == 200 and meta.json() == {"v": 1}
    assert miss.status_code == 404


@needs_fastapi
def test_ws_handshake_echo_broadcast_and_hub_lifecycle(tmp_path):
    """㉑ WS /ws：握手回 connected 帧，入册 hub，消息广播回环，断开剔除。"""
    app = create_console_app(_base_deps(tmp_path))
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "connected"
            assert app.state.hub["sockets"]  # 在线入册
            ws.send_text('{"kind": "kpi", "v": 1}')
            echoed = ws.receive_json()
            assert echoed == {"kind": "kpi", "v": 1}
        deadline = time.monotonic() + 3  # 断开剔除（服务器侧异步收尾）
        while app.state.hub["sockets"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not app.state.hub["sockets"]
        assert app.state.hub["history"][-1] == {"kind": "kpi", "v": 1}
