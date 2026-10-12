"""serve_console 对抗测试：dry_run 装配+TestClient 路由可达/uvicorn 拉起 mock+
缺库 ConsoleError pip 提示/端口占用拒（dry_run 不检）/config 形状错 ValueError。

测试不真起服务：真拉起路径以 sys.modules 注入假 uvicorn（MagicMock 断言调用，
不真跑）；缺库路径以 sys.modules 注入 None（无论环境是否装有 uvicorn 均可复现）。
"""
from __future__ import annotations

import socket
import sys
import types
from unittest.mock import MagicMock

import pytest

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
def test_serve_console_dry_run_returns_app_not_launched(tmp_path):
    """① dry_run=True→{'app', 'launched': False, 'port', 'host'}，不起服务。"""
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    result = serve_console(cfg)
    assert result["launched"] is False
    assert result["port"] == 8123
    assert result["host"] == "127.0.0.1"
    assert hasattr(result["app"], "state")  # create_console_app 产物（ASGI app）


@needs_fastapi
def test_serve_console_dry_run_app_serves_scenarios_route(tmp_path):
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
def test_serve_console_default_port_when_omitted(tmp_path):
    """③ config 缺 port/host→缺省 8000/127.0.0.1 原样回显。"""
    cfg = _base_config(tmp_path)
    del cfg["port"]
    del cfg["host"]
    result = serve_console({**cfg, "dry_run": True})
    assert result["port"] == 8000
    assert result["host"] == "127.0.0.1"


@needs_fastapi
def test_serve_console_default_runner_placeholder(tmp_path):
    """④ 未注入 runner→deps 里为可调用占位（noop 回执），不炸装配。"""
    cfg = _base_config(tmp_path)
    assert "runner" not in cfg
    result = serve_console({**cfg, "dry_run": True})
    runner = result["app"].state.deps["runner"]
    assert callable(runner)
    assert runner({"style": "tone"})["status"] == "noop"


@needs_fastapi
def test_serve_console_shared_stop_flag_wired_by_identity(tmp_path):
    """⑤ config['stop_flag'] 原对象直通 app.state.deps（/api/stop 与急停共享）。"""
    cfg = _base_config(tmp_path)
    cfg["dry_run"] = True
    result = serve_console(cfg)
    assert result["app"].state.deps["stop_flag"] is cfg["stop_flag"]


# ---- 真拉起：mock uvicorn，不真跑 ----


def test_serve_console_real_launch_invokes_uvicorn_run(tmp_path, monkeypatch):
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


def test_serve_console_missing_uvicorn_console_error_pip_hint(tmp_path, monkeypatch):
    """⑦ uvicorn 缺库（sys.modules 注入 None）→ConsoleError 且消息含 pip 提示。"""
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    cfg = _base_config(tmp_path)
    cfg["port"] = _free_port()
    with pytest.raises(ConsoleError) as ei:
        serve_console(cfg)
    assert "pip" in str(ei.value)


# ---- 端口占用 ----


def test_serve_console_port_in_use_raises_console_error(tmp_path):
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
def test_serve_console_dry_run_skips_port_check(tmp_path):
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
def test_serve_console_config_not_dict_valueerror(bad):
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
def test_serve_console_bad_config_fields_valueerror(tmp_path, mutate):
    """⑪ 各键形状错（缺路径/类型不符/端口越界/runner 不可调用…）→ValueError 指错键。"""
    cfg = _base_config(tmp_path)
    mutate(cfg)
    with pytest.raises(ValueError):
        serve_console(cfg)
