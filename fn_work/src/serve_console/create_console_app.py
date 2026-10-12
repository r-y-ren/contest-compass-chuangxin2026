"""ASGI 应用纯工厂（路由/WS hub/异常处理）——重写规约与签名意图详见 fn_docs/responsibility.md。

可测试性设计（不绑端口，依赖全注入）：
- deps 五键必查（runner/stop_flag/scenario_dir/report_root/static_pages）——缺键/类型
  不符→AppError（ValueError 子类，携 field 指错字段）；ledger_path 为可选附加键
  （缺省取仓内默认清单路径）。
- FastAPI 延迟 import：缺库→AppError 带 pip 提示——本模块在无 fastapi 环境仍可
  import（AppError/依赖校验路径可独立测试）。
- 路由内一切参数/配置错误统一抛 AppError→400 JSON {'detail': {'field', 'error'}}
  （字段级指错口径，R47）；runner 后台线程异常只记入运行表，绝不炸服务。

注意：本模块**不可**使用 `from __future__ import annotations`——FastAPI 以字符串形式
对路由签名做注解解析时只查模块全局名，而 Request/WebSocket 等是工厂内延迟 import
的局部名；注解一旦变字符串，参数会被误判为 query 参数（POST 422/WS 1008 关闭）。
路由签名注解须在 def 时求值为真实类（工厂局部作用域内即可解析）。
"""
import json
import os
import re
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.render_console_pages.build_scenario_cards import build_scenario_cards

if TYPE_CHECKING:  # 仅类型标注用——运行时延迟 import（缺库不炸模块装载）
    from fastapi import FastAPI

__all__ = ["AppError", "create_console_app", "DEFAULT_LEDGER_PATH", "FASTAPI_PIP_HINT"]

#: 必需依赖键（缺一即 AppError，消息点名缺失键）。
_REQUIRED_DEPS = ("runner", "stop_flag", "scenario_dir", "report_root", "static_pages")

#: 缺库安装提示（AppError 消息原文含 'pip'，测试据此断言）。
FASTAPI_PIP_HINT = "pip install fastapi（见 requirements.txt）"

#: 清单完成度默认读数路径（与 update_ledger.locate_ledger_row.DEFAULT_LEDGER_PATH
#: 同源；实际部署由上层以 deps['ledger_path'] 显式注入）。
DEFAULT_LEDGER_PATH = "docs/全功能实现清单-技术支持版.md"

# 清单条目行（A–L 域，含 ▶ 进行中前缀变体）——与 locate_ledger_row 同口径的行判定；
# done 判定同源 B17 中#5：行内含 ✅ 或 'wired' 字样即完成。
_LEDGER_ROW_RE = re.compile(r"^\|\s*(?:▶\s*)?[A-L]\d{1,2}\s*\|")

#: WS 广播历史环形上限（hub['history'] 不无界增长）。
_HUB_HISTORY_MAX = 200


class AppError(ValueError):
    """工厂装配/路由参数错误（ValueError 子类）。

    field 属性携带指错字段名（如 'scenario'/'body'/'scenario_dir'），路由内抛出
    时由统一异常处理器转 400 JSON；工厂阶段抛出即直接异常（缺键/缺库）。
    """

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


def _now_iso() -> str:
    """UTC ISO 时间戳（与 stop_transmit_safely 同口径）。"""
    return datetime.now(timezone.utc).isoformat()


def _validate_deps(deps: dict) -> None:
    """依赖前置校验：非 dict、缺键、类型不符→AppError（消息点名问题键）。"""
    if not isinstance(deps, dict):
        raise AppError(
            f"deps 必须为 dict，实际收到 {type(deps).__name__}: {deps!r}", field="deps"
        )
    missing = [key for key in _REQUIRED_DEPS if key not in deps]
    if missing:
        raise AppError(
            f"deps 缺少必需键: {missing}（需要全部 {_REQUIRED_DEPS}）",
            field=missing[0],
        )
    if not callable(deps["runner"]):
        raise AppError(
            f"deps['runner'] 必须可调用（scenario dict→result dict），实际 {deps['runner']!r}",
            field="runner",
        )
    if not isinstance(deps["stop_flag"], dict):
        raise AppError(
            f"deps['stop_flag'] 必须为共享 dict（{{'flag': False}}），实际 "
            f"{type(deps['stop_flag']).__name__}",
            field="stop_flag",
        )
    for key in ("scenario_dir", "report_root"):
        if not isinstance(deps[key], str) or not deps[key]:
            raise AppError(
                f"deps[{key!r}] 必须为非空 str 路径，实际 {deps[key]!r}", field=key
            )
    if deps["static_pages"] is not None and not isinstance(deps["static_pages"], dict):
        raise AppError(
            f"deps['static_pages'] 须为 dict|None，实际 {type(deps['static_pages']).__name__}",
            field="static_pages",
        )


def _count_ledger(path: str) -> dict:
    """读清单 Markdown 数完成度：条目行总数与 ✅/wired 行数（缺文件→零值+False 标志）。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return {"done": 0, "total": 0, "available": False, "path": path}
    total = done = 0
    for line in lines:
        if _LEDGER_ROW_RE.match(line):
            total += 1
            if "✅" in line or "wired" in line.lower():
                done += 1
    return {"done": done, "total": total, "available": True, "path": path}


def create_console_app(deps: dict) -> "FastAPI":
    """ASGI 应用纯工厂：组装路由/WS hub/静态资源/异常处理为 FastAPI 实例。

    路由合约（R47）：
      - GET  /api/scenarios——扫 scenario_dir 下 *.yaml|*.yml→build_scenario_cards
        卡片数据（损坏场景以 error 卡占位，不炸请求）；目录缺失→400 field='scenario_dir'；
      - POST /api/run——JSON body {'scenario': dict}→后台线程调 runner，202 {'run_id'}；
        body 非 JSON 对象→400 field='body'，scenario 缺失/非 dict→400 field='scenario'；
      - POST /api/stop——置 deps['stop_flag']['flag']=True，返回 {'stopped': True}
        （trigger_emergency_stop 的发射侧语义由上层端点叠加）；
      - GET  /api/runs——report_root 子目录名列表（新建在前）；根缺失→400
        field='report_root'；
      - GET  /api/ledger——清单完成度 done/total 简数（deps 可选 'ledger_path'，
        缺省 DEFAULT_LEDGER_PATH；文件缺失→零值+available False）；
      - WS   /ws——实时流 hub：app.state.hub（sockets/history/broadcast dict），
        连接即入册回 connected 帧，收到消息向全体广播（简易实时流回路）；
      - GET  /pages/{name}——static_pages 资产托管（str→HTML，dict→JSON；缺→404）。

    Raises:
        AppError: deps 非 dict/缺必需键/类型不符；fastapi 缺库（消息含 pip 提示）。
    """
    _validate_deps(deps)

    # 延迟 import：无 fastapi 环境本工厂给 AppError+pip 提示（模块装载不受影响）。
    try:
        from fastapi import FastAPI, HTTPException, Request, WebSocket
        from fastapi.responses import HTMLResponse, JSONResponse
    except ImportError as exc:  # pragma: no cover - 由 test_fastapi_missing_* 覆盖
        raise AppError(f"FastAPI 运行库缺失——{FASTAPI_PIP_HINT}") from exc

    app = FastAPI(title="rf-console", docs_url=None, redoc_url=None)

    # ---- 工厂级状态（测试探针口）：hub dict / 运行表 / 原始 deps ----
    hub: dict = {"sockets": set(), "history": deque(maxlen=_HUB_HISTORY_MAX)}

    async def _broadcast(message: dict) -> int:
        """向全部在线 WS 发 JSON；失效连接剔除，返回成功发送数。"""
        sent = 0
        for sock in list(hub["sockets"]):
            try:
                await sock.send_json(message)
                sent += 1
            except Exception:  # noqa: BLE001 - 掉线剔除属于正常路径
                hub["sockets"].discard(sock)
        hub["history"].append(message)
        return sent

    hub["broadcast"] = _broadcast

    app.state.deps = deps
    app.state.hub = hub
    app.state.runs: dict = {}

    # ---- 统一 400：路由内 AppError→JSON 字段级指错 ----
    @app.exception_handler(AppError)
    async def _apperror_to_400(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": {"field": exc.field, "error": str(exc)}},
        )

    @app.get("/api/scenarios")
    async def list_scenarios() -> dict:
        sdir = deps["scenario_dir"]
        if not os.path.isdir(sdir):
            raise AppError(f"scenario_dir 不存在或非目录: {sdir}", field="scenario_dir")
        try:
            names = os.listdir(sdir)
        except OSError as exc:
            raise AppError(f"scenario_dir 不可读: {sdir}（{exc}）", field="scenario_dir")
        files = sorted(
            os.path.join(sdir, n) for n in names if n.endswith((".yaml", ".yml"))
        )
        cards = build_scenario_cards(files)
        return {"cards": cards, "count": len(cards)}

    @app.post("/api/run")
    async def start_run(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception as exc:  # JSONDecodeError/空 body 等→统一 400 field='body'
            raise AppError(
                f"请求体须为 JSON 对象 {{'scenario': dict}}: {type(exc).__name__}: {exc}",
                field="body",
            ) from exc
        if not isinstance(body, dict):
            raise AppError(
                f"请求体须为 JSON 对象，实际 {type(body).__name__}: {body!r}", field="body"
            )
        scenario = body.get("scenario")
        if scenario is None:
            raise AppError("缺少必填字段 'scenario'（场景 dict）", field="scenario")
        if not isinstance(scenario, dict):
            raise AppError(
                f"scenario 必须为 dict，实际 {type(scenario).__name__}: {scenario!r}",
                field="scenario",
            )
        run_id = uuid.uuid4().hex[:8]
        app.state.runs[run_id] = {
            "run_id": run_id,
            "status": "running",
            "started_at": _now_iso(),
            "scenario": scenario,
        }

        def _run_in_background() -> None:
            # runner 一切异常（含 BaseException 族）只落运行表——服务绝不因单次运行炸掉。
            try:
                result = deps["runner"](scenario)
                app.state.runs[run_id]["status"] = "done"
                app.state.runs[run_id]["result"] = (
                    result if isinstance(result, dict) else {"result": result}
                )
            except BaseException as exc:  # noqa: BLE001 - 后台线程隔离边界
                app.state.runs[run_id]["status"] = "failed"
                app.state.runs[run_id]["error"] = f"{type(exc).__name__}: {exc}"

        threading.Thread(
            target=_run_in_background, daemon=True, name=f"console-run-{run_id}"
        ).start()
        return JSONResponse(status_code=202, content={"run_id": run_id})

    @app.post("/api/stop")
    async def stop_run() -> dict:
        # 此端点只管场景侧软停（共享旗标）；发射侧急停语义由上层叠加
        # trigger_emergency_stop（见 push_realtime_kpi）——工厂保持纯装配。
        deps["stop_flag"]["flag"] = True
        return {"stopped": True}

    @app.get("/api/runs")
    async def list_runs() -> dict:
        root = deps["report_root"]
        if not os.path.isdir(root):
            raise AppError(f"report_root 不存在或非目录: {root}", field="report_root")
        try:
            entries = os.listdir(root)
        except OSError as exc:
            raise AppError(f"report_root 不可读: {root}（{exc}）", field="report_root")
        names = sorted(
            (n for n in entries if os.path.isdir(os.path.join(root, n))), reverse=True
        )
        return {"runs": names, "count": len(names)}

    @app.get("/api/ledger")
    async def ledger_progress() -> dict:
        return _count_ledger(deps.get("ledger_path", DEFAULT_LEDGER_PATH))

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        hub["sockets"].add(websocket)
        try:
            await websocket.send_json({"type": "connected", "ts": _now_iso()})
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    msg = {"type": "text", "data": raw}
                if not isinstance(msg, dict):
                    msg = {"type": "text", "data": raw}
                await _broadcast(msg)
        except Exception:  # noqa: BLE001 - 断开/坏帧均为连接生命周期常态
            pass
        finally:
            hub["sockets"].discard(websocket)

    @app.get("/pages/{name}")
    async def static_page(name: str):  # noqa: ANN201 - HTML/JSON 双响应形态
        pages = deps["static_pages"]
        if not pages or name not in pages:
            raise HTTPException(status_code=404, detail=f"页面资产不存在: {name}")
        asset = pages[name]
        if isinstance(asset, str):
            return HTMLResponse(asset)
        return JSONResponse(asset)

    return app
