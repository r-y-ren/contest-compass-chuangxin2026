"""mount_console_extensions 对抗测试：vendor 资产路由合约（200+与仓内文件字节
一致+长度>150000+javascript MIME）、vendor 路径模块同级锚定（文件在位）、文件
缺失→404、deps 非 dict/app 无路由注册能力→AppError（与 create_console_app 同源
错误类型）、返回同一 app（链式）、wired 接线回归（create_console_app 装配即可
GET vendor 路由且既有路由不回归，R56 快速通道②唯一一处接线）。

环境缺 fastapi（或 httpx）时 TestClient 族用例自动 skip——AppError 参数校验
路径先于 fastapi 延迟 import，可独立覆盖。
"""
from pathlib import Path

import pytest

import src.localize_console_assets.mount_console_extensions as mount_mod
from src.localize_console_assets.mount_console_extensions import (
    VENDOR_VUE_PATH,
    VENDOR_VUE_ROUTE,
    mount_console_extensions,
)
from src.serve_console.create_console_app import AppError, create_console_app

try:  # TestClient 同源依赖 fastapi+httpx——任一缺失即整族 skip
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    _HAS_TESTCLIENT = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_TESTCLIENT = False

needs_fastapi = pytest.mark.skipif(
    not _HAS_TESTCLIENT, reason="环境缺 fastapi/httpx——TestClient 不可用"
)


def _base_deps(tmp_path):
    """合法五键 deps（与 test_create_console_app 同构造：tmp 目录+回显假件）。"""
    sdir = tmp_path / "scenarios"
    sdir.mkdir(exist_ok=True)
    rroot = tmp_path / "reports"
    rroot.mkdir(exist_ok=True)
    return {
        "runner": lambda scenario: {"echo": scenario},
        "stop_flag": {"flag": False},
        "scenario_dir": str(sdir),
        "report_root": str(rroot),
        "static_pages": None,
    }


# ---- 参数契约（AppError 与 create_console_app 同源，校验先于 fastapi import） ----


@pytest.mark.parametrize("bad_deps", [None, "deps", ["runner"], 42])
def test_deps_missing_or_not_dict_apperror(bad_deps):
    """① deps 缺失（None）/非 dict（str/list/int）→AppError，field 指错 deps。"""
    with pytest.raises(AppError) as ei:
        mount_console_extensions(object(), bad_deps)  # app 形状无关：deps 先校验
    assert ei.value.field == "deps"
    assert "deps" in str(ei.value)


@pytest.mark.parametrize("bad_app", [None, object(), {}, 42, "app"])
def test_app_without_route_registration_apperror(bad_app):
    """② app 无路由注册能力→AppError，field 指错 app（消息点名路由注册口）。

    含 dict 陷阱回归：dict 自带 get 方法但无 routes 路由表，同样必须被拒
    （starlette 1.x 已移除旧 route 方法，探测以 get 装饰器+routes 路由表为准）。
    """
    with pytest.raises(AppError) as ei:
        mount_console_extensions(bad_app, {})
    assert ei.value.field == "app"
    assert "路由" in str(ei.value)


# ---- vendor 资产锚定（纯路径断言，不依赖 fastapi） ----


def test_vendor_path_anchored_beside_module_and_file_present():
    """③ vendor 路径锚定模块同级 vendor/ 目录（绝对路径、cwd 无关），仓内文件
    在位且为完整生产版体量（>150000 字节——防误删/截断入仓）。"""
    mod_file = Path(mount_mod.__file__).resolve()
    assert VENDOR_VUE_PATH == mod_file.parent / "vendor" / "vue.global.prod.js"
    assert VENDOR_VUE_PATH.is_absolute()
    assert VENDOR_VUE_PATH.is_file()
    assert VENDOR_VUE_PATH.stat().st_size > 150_000
    assert VENDOR_VUE_ROUTE == "/assets/vendor/vue.global.prod.js"


# ---- vendor 路由合约（TestClient 族：缺 fastapi/httpx 自动 skip） ----


@needs_fastapi
def test_vendor_route_serves_repo_vue_file():
    """④ GET /assets/vendor/vue.global.prod.js：200+响应字节与仓内文件逐字节
    一致（>150000）+content-type 含 javascript（零 CDN，断网全可用口径）。"""
    app = mount_console_extensions(FastAPI(), {})
    with TestClient(app) as client:
        resp = client.get(VENDOR_VUE_ROUTE)
    assert resp.status_code == 200
    assert resp.content == VENDOR_VUE_PATH.read_bytes()  # 逐字节对拍仓内文件
    assert len(resp.content) > 150_000
    assert "javascript" in resp.headers["content-type"]


@needs_fastapi
def test_missing_vendor_file_404_no_cdn_fallback(tmp_path, monkeypatch):
    """⑤ vendor 文件缺失→404 指明仓内应有位置（禁止静默回退 CDN）——请求期探
    在位性（monkeypatch 路径常量模拟文件被移走）。"""
    absent = tmp_path / "vendor" / "vue.global.prod.js"
    monkeypatch.setattr(mount_mod, "VENDOR_VUE_PATH", absent)
    app = mount_console_extensions(FastAPI(), {})
    with TestClient(app) as client:
        resp = client.get(VENDOR_VUE_ROUTE)
    assert resp.status_code == 404
    assert "vendor" in resp.json()["detail"]


@needs_fastapi
def test_mount_returns_same_app_for_chaining():
    """⑥ 返回同一 app（便于链式 mount_console_extensions(app, deps)）。"""
    app = FastAPI()
    assert mount_console_extensions(app, {}) is app
    with TestClient(app) as client:  # 链式语义下路由确已注册
        assert client.get(VENDOR_VUE_ROUTE).status_code == 200


# ---- wired 接线回归（R56 快速通道②：create_console_app 唯一一处接线） ----


@needs_fastapi
def test_wired_create_console_app_serves_vendor_route(tmp_path):
    """⑦ wired 接线：create_console_app 装配后即可 GET vendor 路由（200+
    >150000+javascript），同 app 既有路由不回归（GET /api/scenarios 仍 200）。"""
    app = create_console_app(_base_deps(tmp_path))
    with TestClient(app) as client:
        vendor = client.get(VENDOR_VUE_ROUTE)
        legacy = client.get("/api/scenarios")
    assert vendor.status_code == 200
    assert len(vendor.content) > 150_000
    assert "javascript" in vendor.headers["content-type"]
    assert legacy.status_code == 200  # 既有路由原样在位（勿动既有路由口径）
