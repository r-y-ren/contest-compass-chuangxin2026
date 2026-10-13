"""harden_emergency_stop 对抗测试：先停发射序断言（记录调用序的假对象证明发射侧
先于 stop_flag 置位）、停发射失败注入→标志仍置位+结果带 error、成功路径结果形状
（停发射状态/事件引用/来源）、腐化容器不抛、幂等重停、console /api/stop 集成
（TestClient+deps 注入观察：响应含硬停结果且共享旗置位）。

用例名统一 test_emergency_stop_ 前缀——`pytest -k emergency_stop` 可整体发现。
"""
from datetime import datetime

import pytest

from src.harden_emergency_stop.harden_emergency_stop import harden_emergency_stop
from src.serve_console.create_console_app import create_console_app

try:  # TestClient 同源依赖 fastapi+httpx——任一缺失即整族 skip
    from fastapi.testclient import TestClient

    _HAS_TESTCLIENT = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_TESTCLIENT = False

needs_fastapi = pytest.mark.skipif(
    not _HAS_TESTCLIENT, reason="环境缺 fastapi/httpx——TestClient 不可用"
)


class _OrderBackend:
    """记录调用序的探针后端：发射侧两步各自记入共享调用序；stop_tx 时刻另快照
    编排旗状态（应为「尚未置位」——先停发射后置旗的时点证据）。"""

    def __init__(self, order, stop_flag=None):
        self._order = order
        self._stop_flag = stop_flag
        self.snapshots = []

    def stop_tx(self):
        flag = None
        if isinstance(self._stop_flag, dict):
            try:
                flag = self._stop_flag.get("flag")
            except Exception:  # noqa: BLE001 - 快照失败不干扰安全路径
                flag = None
        self.snapshots.append(("stop_tx", flag))
        self._order.append("stop_tx")

    def set_tx_gain(self, gain):
        self._order.append(("set_tx_gain", gain))


class _RecordingFlag(dict):
    """记序共享旗（dict 子类）：'flag' 置 True 时记入共享调用序（证明编排旗
    在发射侧两步之后才置位）。"""

    def __init__(self, order):
        super().__init__({"flag": False})
        self._order = order

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key == "flag" and value is True:
            self._order.append("stop_flag")


class _FailingBackend:
    """发射侧两步全炸的后端（含 KeyboardInterrupt 族——安全路径不许穿透）。"""

    def stop_tx(self):
        raise RuntimeError("tx-hw-fault")

    def set_tx_gain(self, gain):
        raise KeyboardInterrupt("KI-during-gain")


class _UnwritableFlag(dict):
    """置位被拒的旗容器（dict 子类 __setitem__ 抛出——腐化容器留痕口径）。"""

    def __setitem__(self, key, value):
        raise RuntimeError("flag-container-locked")


# ---- 单元：安全顺序 / 失败处置 / 结果形状 ----


def test_emergency_stop_transmit_precedes_flag():
    """① 序断言（记录调用序的假对象）：trigger 的内部停发射（stop_tx→增益归零）
    先于 stop_flag 置位——安全顺序不可倒置。"""
    order = []
    flag = _RecordingFlag(order)
    backend = _OrderBackend(order, stop_flag=flag)
    run_ctx = {"backend": backend, "run_token": "tok-order"}
    result = harden_emergency_stop("console", run_ctx, flag)
    assert order == ["stop_tx", ("set_tx_gain", 0), "stop_flag"]
    assert backend.snapshots == [("stop_tx", False)]  # 停发射时刻编排旗尚未置位
    assert flag["flag"] is True
    assert result["status"] == "stopped"


def test_emergency_stop_success_result_shape():
    """② 成功路径：结果含停发射状态/事件引用/来源，旗置位+事件落点 run_ctx。"""
    backend = _OrderBackend([])
    run_ctx = {"backend": backend, "run_token": "tok-shape"}
    stop_flag = {"flag": False}
    result = harden_emergency_stop("api", run_ctx, stop_flag)
    assert result["source"] == "api"  # 来源
    assert result["status"] == "stopped"
    assert result["error"] is None
    assert result["transmit"]["status"] == "stopped"  # 停发射状态
    assert [e["event"] for e in result["events"]][0:2] == [
        "emergency_stop_requested",
        "transmit_stopped",
    ]  # 事件引用（trigger 产出事件序）
    assert result["events"][0]["origin"] == "api"  # 来源进急停事件
    datetime.fromisoformat(result["stopped_at"])  # 合法 ISO 戳
    assert result["stop_flag_set"] is True
    assert stop_flag["flag"] is True  # 编排旗已置位
    assert run_ctx["stop"]["flag"] is True  # trigger 的场景侧停旗
    assert run_ctx["emergency_stop"] is result  # 事件落点（同一对象落 run_ctx）


def test_emergency_stop_transmit_failure_still_sets_flag():
    """③ 停发射失败注入（两步全炸含 KI）→标志仍置位+结果带 error，不抛出。"""
    run_ctx = {"backend": _FailingBackend(), "run_token": "tok-fail"}
    stop_flag = {"flag": False}
    result = harden_emergency_stop("watchdog", run_ctx, stop_flag)
    assert result["status"] == "stop_failed"
    assert result["error"] and "停发射失败" in result["error"]
    assert result["transmit"]["status"] == "failed"
    assert any(step["ok"] is False for step in result["transmit"]["steps"])
    assert stop_flag["flag"] is True  # 标志仍置位（失败不豁免编排终止）
    assert result["stop_flag_set"] is True
    assert run_ctx["stop"]["flag"] is True  # trigger 场景侧停旗不受发射失败牵连


@pytest.mark.parametrize(
    ("run_ctx", "stop_flag"),
    [
        (None, {"flag": False}),  # run_ctx 腐化（trigger 内部记 stop_failed）
        ("junk-ctx", {"flag": False}),
        ({}, None),  # stop_flag 腐化（置位失败→记原因不抛）
        ({}, ["flag"]),
    ],
)
def test_emergency_stop_corrupt_containers_never_raises(run_ctx, stop_flag):
    """④ 腐化容器（run_ctx/stop_flag 非 dict）→绝不抛出，结果 stop_failed 带 error。"""
    result = harden_emergency_stop("probe", run_ctx, stop_flag)
    assert isinstance(result, dict)
    assert result["status"] == "stop_failed"
    assert result["error"]
    assert result["stop_flag_set"] in (True, False)  # 形状齐备（值随容器可写性）


def test_emergency_stop_unwritable_flag_records_error():
    """⑤ 旗容器置位被拒→发射侧照停（no_backend 无失败），旗未置位如实上报+
    error 记原因——急停结果不虚报成功。"""
    run_ctx = {"backend": None, "run_token": "tok-lock"}
    flag = _UnwritableFlag()
    flag.update({"flag": False})  # dict.update 不走子类 __setitem__——初值可就位
    result = harden_emergency_stop("api", run_ctx, flag)
    assert result["transmit"]["status"] == "no_backend"  # 发射侧无失败
    assert result["stop_flag_set"] is False  # 如实：旗未置上
    assert result["status"] == "stop_failed"
    assert "stop_flag 置位失败" in result["error"]


def test_emergency_stop_idempotent_second_call():
    """⑥ 幂等重停：同 (backend, run_token) 二次急停→发射侧 already_stopped，
    顶层仍 stopped 且无 error（重复急停是安全冗余不是失败）。"""
    backend = _OrderBackend([])
    run_ctx = {"backend": backend, "run_token": "tok-idem"}
    stop_flag = {"flag": False}
    first = harden_emergency_stop("console", run_ctx, stop_flag)
    second = harden_emergency_stop("console", run_ctx, stop_flag)
    assert first["transmit"]["status"] == "stopped"
    assert second["transmit"]["status"] == "already_stopped"  # token 幂等生效
    assert second["status"] == "stopped"
    assert second["error"] is None
    assert stop_flag["flag"] is True


# ---- 集成：create_console_app 的 /api/stop 委托（deps 注入观察） ----


def _console_deps(tmp_path, run_ctx=None):
    """合法五键 deps（tmp 目录就位）+可选注入 run_ctx；返回 (deps, stop_flag)。"""
    sdir = tmp_path / "scenarios"
    sdir.mkdir(exist_ok=True)
    rroot = tmp_path / "reports"
    rroot.mkdir(exist_ok=True)
    stop_flag = {"flag": False}
    deps = {
        "runner": lambda scenario: {"echo": scenario},
        "stop_flag": stop_flag,
        "scenario_dir": str(sdir),
        "report_root": str(rroot),
        "static_pages": None,
    }
    if run_ctx is not None:
        deps["run_ctx"] = run_ctx
    return deps, stop_flag


@needs_fastapi
def test_emergency_stop_console_route_delegates_and_sets_flag(tmp_path):
    """⑦ 集成：POST /api/stop→响应含硬停结果（'emergency_stop' 键）且共享
    stop_flag 置位（deps 注入观察）；探针后端 stop_tx 时刻快照旗=False——
    路由级端到端证明先停发射后置旗。"""
    stop_flag = {"flag": False}
    backend = _OrderBackend([], stop_flag=stop_flag)
    run_ctx = {"backend": backend, "run_token": "tok-route"}
    deps, _ = _console_deps(tmp_path, run_ctx)
    app = create_console_app(deps)
    with TestClient(app) as client:
        resp = client.post("/api/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stopped"] is True  # 既有键向后兼容
    hard = body["emergency_stop"]  # 新增硬停结果键
    assert hard["status"] == "stopped"
    assert hard["source"] == "console"  # 路由以 'console' 来源委托
    assert hard["transmit"]["status"] == "stopped"  # 注入后端真被停发射
    assert deps["stop_flag"]["flag"] is True  # 共享旗置位（deps 注入观察）
    assert run_ctx["emergency_stop"]["source"] == "console"  # 事件落点
    assert app.state.run_ctx is run_ctx  # 注入的 run_ctx 原对象直通
    assert backend.snapshots == [("stop_tx", False)]  # 端到端安全顺序


@needs_fastapi
def test_emergency_stop_console_route_transmit_failure_still_stops(tmp_path):
    """⑧ 集成（失败路径）：注入炸发射后端→响应仍 stopped=True（旗置位不被发射
    失败牵连），硬停结果 status='stop_failed' 带 error，共享旗照置。"""
    run_ctx = {"backend": _FailingBackend(), "run_token": "tok-route-f"}
    deps, stop_flag = _console_deps(tmp_path, run_ctx)
    app = create_console_app(deps)
    with TestClient(app) as client:
        resp = client.post("/api/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stopped"] is True  # 旗置位→既有键语义保持
    assert body["emergency_stop"]["status"] == "stop_failed"
    assert body["emergency_stop"]["error"]
    assert body["emergency_stop"]["transmit"]["status"] == "failed"
    assert stop_flag["flag"] is True  # 标志仍置位


@needs_fastapi
def test_emergency_stop_console_route_default_run_ctx_no_backend(tmp_path):
    """⑨ 集成（缺省上下文）：deps 未注入 run_ctx→缺省上下文（backend None→
    no_backend 幂等口径）照常完成硬化序列，app.state.run_ctx 承接事件落点。"""
    deps, stop_flag = _console_deps(tmp_path)
    app = create_console_app(deps)
    with TestClient(app) as client:
        resp = client.post("/api/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stopped"] is True
    assert body["emergency_stop"]["status"] == "stopped"
    assert body["emergency_stop"]["transmit"]["status"] == "no_backend"
    assert stop_flag["flag"] is True
    assert app.state.run_ctx["emergency_stop"]["status"] == "stopped"  # 落点就位
