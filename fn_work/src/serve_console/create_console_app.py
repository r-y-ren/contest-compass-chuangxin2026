"""ASGI 应用纯工厂（路由/WS hub/异常处理）——重写规约与签名意图详见 fn_docs/responsibility.md。

可测试性设计（不绑端口，依赖全注入）：
- deps 五键必查（runner/stop_flag/scenario_dir/report_root/static_pages）——缺键/类型
  不符→AppError（ValueError 子类，携 field 指错字段）；ledger_path 为可选附加键
  （缺省取仓内默认清单路径）；hub 为可选附加键（R58：serve_console 预建共享
  /ws hub 容器传入则原对象优先，缺省就地新建）。
- FastAPI 延迟 import：缺库→AppError 带 pip 提示——本模块在无 fastapi 环境仍可
  import（AppError/依赖校验路径可独立测试）。
- 路由内一切参数/配置错误统一抛 AppError→400 JSON {'detail': {'field', 'error'}}
  （字段级指错口径，R47）；runner 后台线程异常只记入运行表，绝不炸服务。
- R59 快速通道（急停硬接线，申报）：POST /api/stop 委托 harden_emergency_stop
  （先 trigger_emergency_stop 停发射+事件留痕，再置共享 stop_flag——安全顺序
  不可倒置）；急停运行上下文 deps 可选 'run_ctx' 注入（backend/run_token 等，
  console 拿不到 backend 时缺省 None），app.state.run_ctx 承接（急停结果落
  run_ctx['emergency_stop']）。

注意：本模块**不可**使用 `from __future__ import annotations`——FastAPI 以字符串形式
对路由签名做注解解析时只查模块全局名，而 Request/WebSocket 等是工厂内延迟 import
的局部名；注解一旦变字符串，参数会被误判为 query 参数（POST 422/WS 1008 关闭）。
路由签名注解须在 def 时求值为真实类（工厂局部作用域内即可解析）。
"""
import asyncio
import json
import os
import re
import tempfile
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from src.harden_emergency_stop.harden_emergency_stop import harden_emergency_stop
from src.load_scenario.load_scenario import load_scenario
from src.load_scenario.validate_scenario_schema import ScenarioError
from src.localize_console_assets.mount_console_extensions import mount_console_extensions
from src.render_console_pages.build_scenario_cards import build_scenario_cards

if TYPE_CHECKING:  # 仅类型标注用——运行时延迟 import（缺库不炸模块装载）
    from fastapi import FastAPI

__all__ = ["AppError", "create_console_app", "DEFAULT_LEDGER_PATH", "FASTAPI_PIP_HINT"]

#: 必需依赖键（缺一即 AppError，消息点名缺失键）。
_REQUIRED_DEPS = ("runner", "stop_flag", "scenario_dir", "report_root", "static_pages")

#: 缺库安装提示（AppError 消息原文含 'pip'，测试据此断言）。
FASTAPI_PIP_HINT = "pip install fastapi（见 requirements.txt）"

#: 清单完成度默认读数路径：锚定仓库根（本文件 fn_work/src/serve_console/
#: create_console_app.py 的 parents[3] 即仓库根）——与 run_demo.DEFAULT_LEDGER_PATH/
#: update_ledger.locate_ledger_row.DEFAULT_LEDGER_PATH 同式，从 fn_work、仓库根
#: 或任意其他 cwd 起服都指向同一份清单（修复前 'docs/…' 为 cwd 相对路径，离开
#: 仓库根即 total=0 available=False 的空读数误导）。实际部署由上层以
#: deps['ledger_path'] 显式注入。
DEFAULT_LEDGER_PATH = str(
    Path(__file__).resolve().parents[3] / "docs" / "全功能实现清单-技术支持版.md"
)

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
    # R58 快速通道（极小改造，申报）：可选 'hub'——serve_console 预建的共享 hub
    # 容器（缺省 runner 的实时流桥要在 app 创建前拿到 hub 引用）；非 dict 拒。
    if "hub" in deps and not isinstance(deps["hub"], dict):
        raise AppError(
            f"deps['hub'] 须为 dict（操控台 /ws hub 共享容器），实际 "
            f"{type(deps['hub']).__name__}",
            field="hub",
        )
    # R59 快速通道（急停硬接线，申报）：可选 'run_ctx'——急停运行上下文
    # （harden_emergency_stop→trigger_emergency_stop 消费：backend/run_token
    # 等；console 上下文拿不到 backend 时缺省 None）；非 dict 拒。
    if "run_ctx" in deps and not isinstance(deps["run_ctx"], dict):
        raise AppError(
            f"deps['run_ctx'] 须为 dict（急停运行上下文），实际 "
            f"{type(deps['run_ctx']).__name__}",
            field="run_ctx",
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


#: 场景名 stem 禁含字符（路径分隔/点号[穿越与双后缀]/NUL）——落盘统一 <name>.yaml。
_FORBIDDEN_NAME_CHARS = ("/", "\\", ".", "\x00")

#: 场景文件后缀（与 GET /api/scenarios 的 *.yaml|*.yml 扫描口径一致）。
_SCENARIO_SUFFIX = ".yaml"


def _validate_scenario_name(name: object) -> str:
    """场景名消毒：非空 str、纯文件名 stem（无 / \\ . NUL、无首尾空白、非 ./..）。

    合法→原样返回（落盘 scenario_dir/<name>.yaml）；非法→AppError(field='name')
    ——路径穿越（../evil、a/b）与非 stem 名（demo.yaml/demo.txt——避免
    <name>.yaml 双后缀与狸猫换后缀）一律拒 400。
    """
    if not isinstance(name, str) or not name.strip():
        raise AppError(
            f"场景名必须为非空 str（纯文件名 stem，落盘 <name>.yaml），实际: {name!r}",
            field="name",
        )
    if name != name.strip():
        raise AppError(f"场景名不得含首尾空白: {name!r}", field="name")
    if any(ch in name for ch in _FORBIDDEN_NAME_CHARS) or name in {".", ".."}:
        raise AppError(
            f"非法场景名 {name!r}（路径穿越或非纯 stem 名——仅允许不含 "
            f"{'/'.join(repr(c) for c in _FORBIDDEN_NAME_CHARS[:3])} 的文件名 stem，"
            f"落盘为 <name>.yaml）",
            field="name",
        )
    return name


def _check_scenario_content(content: object) -> str:
    """场景写前校验：内容先落临时文件→load_scenario 全口径把关（schema+guard
    红线，不可跳）——失败即 AppError(field='content') 附原因，目标目录绝不落盘。"""
    if not isinstance(content, str) or not content.strip():
        raise AppError(
            f"场景内容必须为非空 str（YAML 文本），实际: {type(content).__name__}",
            field="content",
        )
    with tempfile.TemporaryDirectory(prefix="console-scenario-check-") as tmpdir:
        probe = os.path.join(tmpdir, "probe.yaml")
        try:
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write(content)
            load_scenario(probe)  # 校验即弃——规范化产物不落盘
        except ScenarioError as exc:
            raise AppError(
                f"场景内容未过装载校验（schema/guard 红线）: {exc}", field="content"
            ) from exc
        except OSError as exc:
            raise AppError(
                f"校验临时文件不可写（内容校验无法进行）: {exc}", field="content"
            ) from exc
    return content


def _write_scenario(deps: dict, name: str, content: str) -> str:
    """把已校验的场景文本写盘 scenario_dir/<name>.yaml，返回落盘路径。

    scenario_dir 缺失/不可写→AppError(field='scenario_dir')（与 GET 列表同口径）。
    """
    path = os.path.join(deps["scenario_dir"], name + _SCENARIO_SUFFIX)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError as exc:
        raise AppError(
            f"场景写盘失败（scenario_dir 不存在或不可写）: {exc}",
            field="scenario_dir",
        ) from exc
    return path


def create_console_app(deps: dict) -> "FastAPI":
    """ASGI 应用纯工厂：组装路由/WS hub/静态资源/异常处理为 FastAPI 实例。

    路由合约（R47）：
      - GET  /api/scenarios——扫 scenario_dir 下 *.yaml|*.yml→build_scenario_cards
        卡片数据（损坏场景以 error 卡占位，不炸请求）；目录缺失→400 field='scenario_dir'；
      - POST /api/scenarios——保存场景：body {'name', 'content'}→写
        scenario_dir/<name>.yaml；name 非法（路径穿越/空/非纯 stem 名）→400
        field='name'；content 写前经 load_scenario 全口径校验（schema+guard 红线，
        临时文件承载）——失败 400 field='content' 附原因，目录不落盘；成功 201；
      - PUT  /api/scenarios/{name}——覆写同名场景（校验同 POST：name 消毒+内容
        红线把关；upsert 语义，不存在即建）；失败 400 同 POST 口径；
      - DELETE /api/scenarios/{name}——删除 <name>.yaml（不存在→404；name 非法
        →400 同 POST 口径）；
      - POST /api/run——JSON body {'scenario': dict}→后台线程调 runner，202 {'run_id'}；
        启动即复位 stop_flag（新 run 不吃旧停机信号）；body 非 JSON 对象→400
        field='body'，scenario 缺失/非 dict→400 field='scenario'；
      - GET  /api/runs——report_root 子目录名列表（新建在前）；根缺失→400
        field='report_root'；
      - GET  /api/runs/{run_id}——运行状态查询（app.state.runs：running/failed/
        done+result/error 摘要；未知 run_id→404）；
      - POST /api/stop——委托 harden_emergency_stop（R59 快速通道）：先
        trigger_emergency_stop（内部先 stop_transmit_safely 停发射并记录急停
        事件）再置 deps['stop_flag']['flag']=True（安全顺序不可倒置，停发射
        失败仍保证旗置位并在结果报错）；响应向后兼容——保留 'stopped' 键
        （编排旗已置 True），新增 'emergency_stop' 硬停结果键
        （harden_emergency_stop 返回值原样：停发射状态/事件序/来源）；
      - GET  /api/ledger——清单完成度 done/total 简数（deps 可选 'ledger_path'，
        缺省 DEFAULT_LEDGER_PATH；文件缺失→零值+available False）；
      - WS   /ws——实时流 hub：app.state.hub（sockets/history/broadcast dict），
        连接即入册回 connected 帧，收到消息向全体广播（简易实时流回路）；
      - GET  /pages/{name}——static_pages 资产托管（str→HTML，dict→JSON；缺→404；
        无后缀名回退 name+'.html'：/pages/index → index.html，对齐
        render_console_pages 产物键）。

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
    # R58 快速通道（极小改造，申报）：deps 携 'hub'（serve_console 预建共享
    # 容器）则原对象优先（缺省 runner 的实时流桥与路由共用同一 hub），
    # 否则就地新建；两路都保证 sockets/history/broadcast 三件套齐备。
    hub: dict = deps["hub"] if isinstance(deps.get("hub"), dict) else {}
    hub.setdefault("sockets", set())
    hub.setdefault("history", deque(maxlen=_HUB_HISTORY_MAX))

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

    # ---- R59 快速通道（急停硬接线）：急停运行上下文 ----
    # console 侧通常拿不到发射后端句柄（backend 缺省 None——
    # harden_emergency_stop→trigger_emergency_stop→stop_transmit_safely 幂等
    # 口径兜底 no_backend）；deps 可选 'run_ctx' 显式注入（backend/run_token
    # 等）则原对象直通（急停结果落 run_ctx['emergency_stop'] 供 deps 注入方
    # 观察）；'runs' 挂操控台活跃运行信息容器（观测用，已携则不越权覆盖）。
    run_ctx: dict = deps["run_ctx"] if isinstance(deps.get("run_ctx"), dict) else {}
    run_ctx.setdefault("runs", app.state.runs)
    app.state.run_ctx = run_ctx

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

    @app.post("/api/scenarios", status_code=201)
    async def save_scenario(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception as exc:  # JSONDecodeError/空 body 等→统一 400 field='body'
            raise AppError(
                f"请求体须为 JSON 对象 {{'name', 'content'}}: {type(exc).__name__}: {exc}",
                field="body",
            ) from exc
        if not isinstance(body, dict):
            raise AppError(
                f"请求体须为 JSON 对象，实际 {type(body).__name__}: {body!r}", field="body"
            )
        name = _validate_scenario_name(body.get("name"))
        content = _check_scenario_content(body.get("content"))
        path = _write_scenario(deps, name, content)
        return JSONResponse(
            status_code=201, content={"saved": True, "name": name, "path": path}
        )

    @app.put("/api/scenarios/{name}")
    async def overwrite_scenario(name: str, request: Request) -> dict:
        name = _validate_scenario_name(name)  # 与 POST 同口径消毒（URL 侧穿越也拒）
        try:
            body = await request.json()
        except Exception as exc:
            raise AppError(
                f"请求体须为 JSON 对象 {{'content'}}: {type(exc).__name__}: {exc}",
                field="body",
            ) from exc
        if not isinstance(body, dict):
            raise AppError(
                f"请求体须为 JSON 对象，实际 {type(body).__name__}: {body!r}", field="body"
            )
        content = _check_scenario_content(body.get("content"))
        path = _write_scenario(deps, name, content)  # upsert：不存在即建，存在即覆写
        return {"saved": True, "name": name, "path": path}

    @app.delete("/api/scenarios/{name}")
    async def delete_scenario(name: str) -> dict:
        name = _validate_scenario_name(name)
        path = os.path.join(deps["scenario_dir"], name + _SCENARIO_SUFFIX)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail=f"场景不存在: {name}")
        try:
            os.remove(path)
        except OSError as exc:
            raise AppError(
                f"场景删除失败（scenario_dir 不可写）: {exc}", field="scenario_dir"
            ) from exc
        return {"deleted": True, "name": name}

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
        # 启动即复位共享停机旗标——上一轮 /api/stop 的遗留信号不牵连本次运行
        # （新 run 不吃旧停机信号；对在途旧 run 的共享旗影响属共享旗设计固有口径）。
        deps["stop_flag"]["flag"] = False
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
        # R59 快速通道（急停硬接线，申报）：从「仅置 stop_flag」升级为委托
        # harden_emergency_stop——先 trigger_emergency_stop（内部先
        # stop_transmit_safely 停发射并记录急停事件）再置共享 stop_flag（安全
        # 顺序不可倒置；停发射失败仍保证旗置位并在结果报错，绝不 500）。
        # 响应向后兼容：保留既有 'stopped' 键（编排旗已置 True），新增
        # 'emergency_stop' 硬停结果键（停发射状态/事件序/来源——页面按钮
        # 状态与广播帧消费）。
        result = harden_emergency_stop(
            source="console", run_ctx=run_ctx, stop_flag=deps["stop_flag"]
        )
        return {"stopped": result.get("stop_flag_set") is True, "emergency_stop": result}

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

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict:
        # 运行状态可查（app.state.runs 运行表）：running/failed/done+result/error
        # 摘要；POST /api/run 的 202 只给 run_id，客户端凭此端点轮询终态。
        entry = app.state.runs.get(run_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}")
        return dict(entry)

    @app.get("/api/ledger")
    async def ledger_progress() -> dict:
        return _count_ledger(deps.get("ledger_path", DEFAULT_LEDGER_PATH))

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        hub["sockets"].add(websocket)
        # R58 快速通道：首连捕获服务事件循环——实时流桥线程经
        # run_coroutine_threadsafe 入环推送（跨线程 send_json 的正确驱动环）。
        hub["loop"] = asyncio.get_running_loop()
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

    @app.get("/", include_in_schema=False)
    async def _root_redirect():
        # 用户直访根路径 → 落到操控台首页（真实用户第一个动作就是开 http://host:port/）
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/pages/index", status_code=307)

    @app.get("/pages/{name}")
    async def static_page(name: str):  # noqa: ANN201 - HTML/JSON 双响应形态
        pages = deps["static_pages"]
        asset = pages.get(name) if pages else None
        if asset is None and not name.endswith(".html"):
            # 无后缀名回退 name+'.html'（/pages/index → index.html）——对齐
            # render_console_pages 产物键（pages 恒带 .html 后缀），README
            # 方式三的 /pages/index 直达无需用户知道后缀细节。
            asset = pages.get(name + ".html") if pages else None
        if asset is None:
            raise HTTPException(status_code=404, detail=f"页面资产不存在: {name}")
        if isinstance(asset, str):
            return HTMLResponse(asset)
        return JSONResponse(asset)

    # ---- 演进端点集中挂载（R56 快速通道②：唯一一处接线）----
    # R57–R74 各批次服务端点一律经 mount_console_extensions 按序注册，本工厂
    # 不再逐端点改动（vendor 资产路由等扩展路由自此有了单点挂载口）。
    mount_console_extensions(app, deps)

    return app
