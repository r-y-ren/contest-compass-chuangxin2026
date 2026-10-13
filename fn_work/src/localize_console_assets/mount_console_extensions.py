"""演进端点集中挂载点：把 R57-R74 各功能块服务端点按序注册到 ASGI 应用（旧函数仅一处接线）——重写规约与签名意图详见 fn_docs/responsibility.md。

扩展约定（R56 定，责任文档「单点接线」口径）：本函数体是 R57–R74 各批次服务端点
的**唯一**注册现场——后续批次到货时在函数体内按 R 号顺序逐批追加注册块（每块以
``# ---- R<n> 功能块名 ----`` 注释分隔），create_console_app 自身不再逐端点改动
（只保留 R56 快速通道②的唯一一处 mount_console_extensions(app, deps) 接线）。
本批（R56）在册：vendor 资产路由——GET /assets/vendor/vue.global.prod.js 服务
仓内 Vue3 生产版单文件（模块同级 vendor/ 目录，零 CDN、断网全可用）。

注意：本模块同 create_console_app，**不可**使用 `from __future__ import
annotations`——路由处理器签名注解须在 def 时求值为真实类（FileResponse 是本函数
体内延迟 import 的名字，注解一旦变字符串，FastAPI 只查模块全局名即解析失败）。
"""
from pathlib import Path

__all__ = ["mount_console_extensions", "VENDOR_VUE_ROUTE", "VENDOR_VUE_PATH"]

#: vendor 资产目录（模块同级 vendor/——Vue3 生产版单文件入仓处，零 CDN）。
_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"

#: 本批（R56）注册的唯一演进路由：七页骨架的 Vue3 <script src> 指向此处。
VENDOR_VUE_ROUTE = "/assets/vendor/vue.global.prod.js"

#: VENDOR_VUE_ROUTE 服务的仓内 vendor 文件（Vue 3.5.13 生产版，157924 字节）。
#: 请求期再探在位性——文件缺失→404，禁止静默回退 CDN（R56 断网全可用红线）。
VENDOR_VUE_PATH = _VENDOR_DIR / "vue.global.prod.js"


def _validate_app(app: object) -> None:
    """app 路由注册能力前置校验：缺 get 装饰器或 routes 路由表→AppError。

    探测口径：现行注册口为 FastAPI 的 get 装饰器+routes 路由表（starlette 1.x
    已移除旧 route 方法，此处以「实际可注册」为准）；dict 等带 get 方法的假件
    因无 routes 路由表同样被拒。
    """
    from src.serve_console.create_console_app import AppError

    if not callable(getattr(app, "get", None)) or not isinstance(
        getattr(app, "routes", None), list
    ):
        raise AppError(
            f"app 必须为可注册路由的 FastAPI 应用（带 get 装饰器与 routes "
            f"路由表），实际收到 {type(app).__name__}: {app!r}",
            field="app",
        )


def mount_console_extensions(app, deps: dict):
    """演进端点集中挂载点：把 R57–R74 各功能块的服务端点按序注册到 ASGI 应用（详见 fn_docs/responsibility.md 功能块）。

    扩展约定：本函数体是 R57–R74 各批次服务端点的唯一注册现场——后续批次到货时
    在下方注册块区按 R 号顺序逐批追加（每块以 ``# ---- R<n> 功能块名 ----`` 注释
    分隔），create_console_app 不再逐端点改动。本批（R56）在册：vendor 资产路由。

    Args:
        app: FastAPI 应用（须具备路由注册能力——get 装饰器+routes 路由表；
            缺失→AppError）。
        deps: create_console_app 的依赖注入 dict（runner/static_pages 等；本批
            vendor 路由不消费其键，后续批次注册块按需取用）。

    Returns:
        注册完成后的同一 app（便于链式：mount_console_extensions(app, deps)）。

    Raises:
        AppError: deps 缺失（None）/非 dict；app 无路由注册能力；fastapi 缺库
            （消息含 pip 提示，与 create_console_app 同口径）。
    """
    # 延迟 import：AppError 与 create_console_app 同源（字段级指错同口径）——
    # 本模块被 create_console_app 模块级导入，此处若模块级互导即循环导入。
    from src.serve_console.create_console_app import FASTAPI_PIP_HINT, AppError

    if not isinstance(deps, dict):
        raise AppError(
            f"deps 必须为 dict（依赖注入映射），实际收到 "
            f"{type(deps).__name__}: {deps!r}",
            field="deps",
        )
    _validate_app(app)

    # 延迟 import：无 fastapi 环境给 AppError+pip 提示（经 create_console_app
    # 接线时 fastapi 已在工厂阶段就位，此处为独立调用兜底，同工厂口径）。
    try:
        from fastapi import HTTPException
        from fastapi.responses import FileResponse
    except ImportError as exc:  # pragma: no cover - 环境相关，工厂侧已先拒
        raise AppError(f"FastAPI 运行库缺失——{FASTAPI_PIP_HINT}") from exc

    # ---- R56 localize_console_assets：vendor 资产路由（零 CDN，断网全可用） ----

    @app.get(VENDOR_VUE_ROUTE)
    async def serve_vendor_vue() -> FileResponse:
        # 请求期探在位：文件被移走/未入仓→404 指明仓内应有位置（不回退 CDN）。
        if not VENDOR_VUE_PATH.is_file():
            raise HTTPException(
                status_code=404,
                detail=(
                    f"vendor 资产缺失: {VENDOR_VUE_PATH}"
                    "（仓内 localize_console_assets/vendor/ 应有 vue.global.prod.js）"
                ),
            )
        return FileResponse(VENDOR_VUE_PATH, media_type="application/javascript")

    # ---- R57–R74 后续批次注册块：到货批次按 R 号顺序在此逐批追加 ----

    return app
