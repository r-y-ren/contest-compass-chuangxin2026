"""create_console_app 对抗测试：路由合约（scenarios 列表+CRUD/run 202+stop 复位/
runs 列表+单查/stop/ledger）、非法 body 400 字段指错、deps 缺键/类型拒、缺
fastapi→AppError pip 提示、WS 握手。

环境缺 fastapi（或 httpx）时 TestClient 族用例自动 skip——AppError 缺库路径用
sys.modules 注入 None 独立覆盖（不依赖环境是否装了 fastapi）。
"""
from __future__ import annotations

import sys
import threading
import time

import pytest

from src.load_scenario.load_scenario import load_scenario
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
    """⑭ POST /api/stop→'stopped': True 且共享 stop_flag['flag'] 置位；R59
    快速通道后响应另携 'emergency_stop' 硬停结果键（向后兼容——既有键保留）。"""
    deps = _base_deps(tmp_path)
    app = create_console_app(deps)
    with TestClient(app) as client:
        resp = client.post("/api/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stopped"] is True  # 既有键保留（向后兼容）
    assert body["emergency_stop"]["status"] == "stopped"  # 新增硬停结果键
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
def test_static_pages_name_fallback_to_html_suffix(tmp_path):
    """⑳b /pages/{name} 无后缀回退 name+'.html'（阻断A③）：/pages/index → index.html。

    render_console_pages 产物键恒带 .html 后缀——回退后 README 方式三的
    /pages/index 直达；带后缀名不二次回退（index.html.html 仍 404）。
    """
    deps = _base_deps(tmp_path)
    deps["static_pages"] = {"index.html": "<html>console</html>"}
    app = create_console_app(deps)
    with TestClient(app) as client:
        direct = client.get("/pages/index.html")
        via_fallback = client.get("/pages/index")
        double = client.get("/pages/index.html.html")
    assert direct.status_code == 200
    assert via_fallback.status_code == 200
    assert via_fallback.text == direct.text  # 回退命中同一资产
    assert double.status_code == 404  # 已带后缀名不再追加回退


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


# ---- 场景 CRUD（B19 三轴中#1：写侧三端点+写前 load_scenario 全口径校验） ----

#: 完整合法场景文本（与 load_scenario 测试同源样本：字段+信封键均过红线）。
_VALID_SCENARIO_YAML = (
    "style: TONE\n"
    "fs: 2000000\n"
    "freq_hz: 2440000000\n"
    "power_dbm: -10\n"
    "duration_s: 2.5\n"
    "repeats: 2\n"
    "backend: SIM\n"
    "bands:\n"
    "  - [2400, 2483.5]\n"
    "shielded_box: true\n"
    "dut_scope: self_built\n"
)

#: 红线违例文本：power_dbm 5dBm 超上限（guard [power] 条款拒）。
_REDLINE_SCENARIO_YAML = _VALID_SCENARIO_YAML.replace("power_dbm: -10", "power_dbm: 5")


@needs_fastapi
def test_post_scenario_saves_valid_yaml(tmp_path):
    """㉒ POST /api/scenarios 合法保存：name+content→scenario_dir/<name>.yaml，
    内容可经 load_scenario 装载（红线已过），列表端点即可见。"""
    app = create_console_app(_base_deps(tmp_path))
    with TestClient(app) as client:
        resp = client.post(
            "/api/scenarios",
            json={"name": "demo_save", "content": _VALID_SCENARIO_YAML},
        )
        assert resp.status_code == 201
        assert resp.json()["saved"] is True
        listing = client.get("/api/scenarios")
    target = tmp_path / "scenarios" / "demo_save.yaml"
    assert target.is_file()
    assert load_scenario(str(target))["style"] == "tone"  # 落盘件可装载
    assert listing.json()["count"] == 1
    assert listing.json()["cards"][0]["name"] == "demo_save"


@needs_fastapi
def test_post_scenario_redline_rejected_400_no_write(tmp_path):
    """㉓ 红线拒：power 5dBm 超 guard 上限→400 field='content' 附红线原因，
    scenario_dir 绝不落盘。"""
    app = create_console_app(_base_deps(tmp_path))
    with TestClient(app) as client:
        resp = client.post(
            "/api/scenarios",
            json={"name": "evil_power", "content": _REDLINE_SCENARIO_YAML},
        )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["field"] == "content"
    assert "红线" in detail["error"]  # guard 条款原因透传
    assert not (tmp_path / "scenarios" / "evil_power.yaml").exists()  # 不落盘


@pytest.mark.parametrize(
    "bad_name",
    ["../evil", "a/b", "a\\b", "..", "", "   ", "demo.yaml", "demo.txt"],
)
@needs_fastapi
def test_post_scenario_bad_name_rejected_400(tmp_path, bad_name):
    """㉔ name 非法（路径穿越/空/非纯 stem 名）→400 field='name'，目录内外均无落盘。"""
    app = create_console_app(_base_deps(tmp_path))
    with TestClient(app) as client:
        resp = client.post(
            "/api/scenarios",
            json={"name": bad_name, "content": _VALID_SCENARIO_YAML},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "name"
    assert list((tmp_path / "scenarios").iterdir()) == []  # 目录内零写入
    assert list(tmp_path.glob("*.yaml")) == []  # 穿越名不得逃出 scenario_dir


@needs_fastapi
def test_put_scenario_overwrites_with_same_validation(tmp_path):
    """㉕ PUT /api/scenarios/{name} 覆写：合法内容覆写成功；红线内容 400 且旧件原样。"""
    sdir = tmp_path / "scenarios"
    sdir.mkdir()  # 先建目录再落既有场景（_base_deps 的 mkdir 在其后才执行）
    target = sdir / "overwrite_me.yaml"
    target.write_text(_VALID_SCENARIO_YAML, encoding="utf-8")
    app = create_console_app(_base_deps(tmp_path))
    updated = _VALID_SCENARIO_YAML.replace("duration_s: 2.5", "duration_s: 9.5")
    with TestClient(app) as client:
        ok = client.put(
            "/api/scenarios/overwrite_me", json={"content": updated}
        )
        assert ok.status_code == 200
        assert ok.json()["saved"] is True
        bad = client.put(
            "/api/scenarios/overwrite_me", json={"content": _REDLINE_SCENARIO_YAML}
        )
        assert bad.status_code == 400
        assert bad.json()["detail"]["field"] == "content"
        # URL 侧非法名（带后缀的 stem/编码穿越）不进写路径：路由可达→400 拒；
        # %2F 解码后不匹配路由→404（同样未触写路径，安全属性等价）。
        suffixed = client.put(
            "/api/scenarios/evil.txt", json={"content": _VALID_SCENARIO_YAML}
        )
        assert suffixed.status_code == 400
        encoded = client.put(
            "/api/scenarios/..%2Fevil", json={"content": _VALID_SCENARIO_YAML}
        )
        assert encoded.status_code in (400, 404)
    assert "duration_s: 9.5" in target.read_text(encoding="utf-8")  # 覆写生效
    assert list(sdir.iterdir()) == [target]  # 逃逸/新增零落盘
    assert not (tmp_path / "evil.yaml").exists()


@needs_fastapi
def test_delete_scenario_removes_and_missing_404(tmp_path):
    """㉖ DELETE /api/scenarios/{name}：删已有→200 文件消失；不存在→404。"""
    sdir = tmp_path / "scenarios"
    sdir.mkdir()  # 先建目录再落既有场景（_base_deps 的 mkdir 在其后才执行）
    target = sdir / "gone_soon.yaml"
    target.write_text(_VALID_SCENARIO_YAML, encoding="utf-8")
    app = create_console_app(_base_deps(tmp_path))
    with TestClient(app) as client:
        resp = client.delete("/api/scenarios/gone_soon")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True, "name": "gone_soon"}
        again = client.delete("/api/scenarios/gone_soon")
        assert again.status_code == 404
    assert not target.exists()


# ---- run 状态可查（B19 对抗中#1：202 只给 run_id，终态凭此端点轮询） ----


@needs_fastapi
def test_get_run_by_id_failed_run_queryable(tmp_path):
    """㉗ GET /api/runs/{run_id}：failed run 可查（status/error 摘要）；未知 id→404。"""
    def bad_runner(scenario):
        raise RuntimeError("boom-in-runner")

    app = create_console_app(_base_deps(tmp_path, runner=bad_runner))
    with TestClient(app) as client:
        run_id = client.post("/api/run", json={"scenario": {"style": "tone"}}).json()[
            "run_id"
        ]
        assert _wait_status(app, run_id, "failed")
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run_id
        assert body["status"] == "failed"
        assert "RuntimeError" in body["error"]
        missing = client.get("/api/runs/deadbeef")
    assert missing.status_code == 404


# ---- /api/ledger 缺省路径（误导②：仓库根锚定，cwd 无关） ----


def test_default_ledger_path_anchored_to_repo_root():
    """误导② 回归：缺省 ledger 路径锚定仓库根绝对路径（本文件 parents[3]）——
    修复前为 cwd 相对 'docs/…'，从 fn_work 起服即 total=0 空读数误导。"""
    from pathlib import Path

    import src.serve_console.create_console_app as mod

    repo_root = Path(mod.__file__).resolve().parents[3]
    assert Path(mod.DEFAULT_LEDGER_PATH) == (
        repo_root / "docs" / "全功能实现清单-技术支持版.md"
    )
    assert Path(mod.DEFAULT_LEDGER_PATH).is_absolute()


@needs_fastapi
def test_get_ledger_default_path_reads_real_ledger_from_fn_work_cwd(
    tmp_path, monkeypatch
):
    """误导② 补例：从 fn_work cwd（其下无 docs/）起服、不注入 ledger_path →
    GET /api/ledger 仍读到真实清单 available=True 且 total=100（当前条目总数；
    修复前 cwd 相对路径在此落空 → total=0 available=False）。"""
    from pathlib import Path

    fn_work = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(fn_work)  # fn_work 下无 docs/——cwd 相对路径在此必落空
    app = create_console_app(_base_deps(tmp_path))  # 不注入 ledger_path → 缺省锚定
    with TestClient(app) as client:
        resp = client.get("/api/ledger")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["total"] == 100
    assert body["done"] > 0


# ---- B24 C1：停止路由 backend 贯通 + emergency_stopped 广播帧 ----


class _ProbeBackend:
    """停发射探针后端：记录 stop_tx/set_tx_gain 调用（真停直证）。"""

    def __init__(self):
        self.calls: list = []

    def stop_tx(self):
        self.calls.append("stop_tx")

    def set_tx_gain(self, gain):
        self.calls.append(("set_tx_gain", gain))


@needs_fastapi
def test_post_stop_syncs_backend_channel_from_shared_stop(tmp_path):
    """B24 C1①：共享停容器携 'backend'（run_scenario 后端打开后写回）→停止路由
    同步进 run_ctx，trigger 直停真后端（transmit.status='stopped' 且探针被实调）
    ——不再是 no_backend 空转。"""
    deps = _base_deps(tmp_path)
    backend = _ProbeBackend()
    deps["stop_flag"]["backend"] = backend
    app = create_console_app(deps)
    with TestClient(app) as client:
        resp = client.post("/api/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["emergency_stop"]["status"] == "stopped"
    assert body["emergency_stop"]["transmit"]["status"] == "stopped"  # 真停（非 no_backend）
    assert backend.calls[0] == "stop_tx"  # 真后端被实停
    assert app.state.run_ctx["backend"] is backend  # 通道同步进急停上下文


@needs_fastapi
def test_post_stop_broadcasts_emergency_stopped_frame(tmp_path):
    """B24 C1③：harden 后经 hub 广播 emergency_stopped 帧（形状对齐
    push_realtime_kpi 控制帧族：type/origin/status/stopped_at+sent_ms）——
    在线 WS 客户端收到帧（叶子红标的发送方补全）。"""
    deps = _base_deps(tmp_path)
    app = create_console_app(deps)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            hello = ws.receive_json()  # connected 握手帧
            assert hello["type"] == "connected"
            resp = client.post("/api/stop")
            assert resp.status_code == 200
            frame = ws.receive_json()  # 急停广播帧
    assert frame["type"] == "emergency_stopped"
    assert frame["origin"] == "console"
    assert frame["status"] == "stopped"
    assert frame["stopped_at"]
    assert isinstance(frame["sent_ms"], int)  # 发送戳在位（push 口径）
    assert any(
        f.get("type") == "emergency_stopped" for f in app.state.hub["history"]
    )  # 帧入广播历史（断线重连补画素材）
