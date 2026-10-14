"""演进端点集中挂载点：把 R57-R74 各功能块服务端点按序注册到 ASGI 应用（旧函数仅一处接线）——重写规约与签名意图详见 fn_docs/responsibility.md。

扩展约定（R56 定，责任文档「单点接线」口径）：本函数体是 R57–R74 各批次服务端点
的**唯一**注册现场——后续批次到货时在函数体内按 R 号顺序逐批追加注册块（每块以
``# ---- R<n> 功能块名 ----`` 注释分隔），create_console_app 自身不再逐端点改动
（只保留 R56 快速通道②的唯一一处 mount_console_extensions(app, deps) 接线）。
本批（R56）在册：vendor 资产路由——GET /assets/vendor/vue.global.prod.js 服务
仓内 Vue3 生产版单文件（模块同级 vendor/ 目录，零 CDN、断网全可用）。
R60 追加在册：serve_run_artifacts 运行产物三端点——GET /api/runs/{run_id}/report
（report.md 服务端渲染 HTML+溯源结论徽标）、/api/runs/{run_id}/plots/{name}
（PNG 曲线图）、/api/runs/{run_id}/files/{name}（白名单数据文件下载）；
report_root 取 deps['report_root']（create_console_app 五必查键之一，天然贯通）。
R61 追加在册：list_run_summaries 报告中心元数据行端点——GET /api/runs/summaries
（扫描 report_root 各运行目录读 result.json/场景副本出摘要行，新建在前；字面
路由经注册序手术置于 GET /api/runs/{run_id} 之前，防参数路由先匹配吞掉）。
R62 追加在册：view_failure_comparison 跨轮失效对比端点——POST /api/runs/compare
（body {'run_ids': [...]}→读各轮失效电平→compare_failure_boundaries 对比表+
薄弱环节结论；无失效数据运行如实标注，全缺附「请选择其他运行」提示）。
R63 追加在册：browse_dataset_library 数据集浏览两端点——GET /api/dataset
（query 参数 style/date_from/date_to→index_dataset query 出 SigMF 真值对卡片，
索引未建→missing 状态提示+重建入口标志不拦页）与 POST /api/dataset/rebuild
（index_dataset rebuild 重建口径——runs_root=deps['report_root']，索引落
report_root/dataset-index.json）。
R64 追加在册：launch_replay_run 一键回放端点——POST /api/run/replay（body
{'run_id': 录音条目标识}→索引定位条目→build_replay_scenario 装载期组装（损坏
录音/声明缺失→400 错误信息进响应）→202+后台线程经 launch_replay_run(entry,
deps['runner']) 发起，运行表/实时曲线/报告中心可见）。B26 对抗中2 转 B27 随批
整改②（索引入口 runs_root 路径围栏）：条目 sigmf_path 解析后必须落在 runs_root
内（否则 ScenarioError→400）；index register 透传的 source_scenario 收缩
（仅取白名单键）——见 R64 注册块内围栏助手。
R65 追加在册：launch_classifier_training AI 训练三端点——POST /api/ai/train
（训练参数→后台任务 202+任务句柄，拒训终态 failed 附原文）、GET
/api/ai/train/{task_id}（任务状态轮询）、GET /api/ai/models（run 目录根
models/ 模型文件列表）。
R66 追加在册：view_cv_evaluation 评测端点——POST /api/ai/evaluate（数据筛选+
模型标识→混淆矩阵/Macro-F1/泄漏警告结果；EvalError（分组缺失等）→400 上屏）。
R67 追加在册：infer_style_entry 主动推理端点——POST /api/ai/infer（IQ 源选择
（run_id/sigmf_path/query）→识别结果行+真值对照；模型缺失提示态不报错）。

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
    分隔），create_console_app 不再逐端点改动。在册批次：R56 vendor 资产路由；
    R60 serve_run_artifacts 运行产物三端点（report/plots/files）；R61
    list_run_summaries 运行摘要端点（GET /api/runs/summaries）；R62
    view_failure_comparison 跨轮对比端点（POST /api/runs/compare）；R63
    browse_dataset_library 数据集浏览两端点（GET /api/dataset+POST
    /api/dataset/rebuild）；R64 launch_replay_run 一键回放端点（POST
    /api/run/replay——B26 对抗中2 转 B27 整改②：runs_root 路径围栏+
    source_scenario 白名单收缩）；R65 launch_classifier_training AI 训练三
    端点；R66 view_cv_evaluation 评测端点（POST /api/ai/evaluate）；R67
    infer_style_entry 主动推理端点（POST /api/ai/infer）。

    Args:
        app: FastAPI 应用（须具备路由注册能力——get 装饰器+routes 路由表；
            缺失→AppError）。
        deps: create_console_app 的依赖注入 dict（runner/static_pages 等；
            R56 vendor 路由不消费其键；R60 三端点与 R61/R62 端点请求期读
            deps['report_root']——缺键/非非空 str→AppError field='report_root'，
            与 create_console_app 的 GET /api/runs 同口径）。

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
        from fastapi import HTTPException, Request
        from fastapi.responses import FileResponse, HTMLResponse, Response
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

    # ---- R60 serve_run_artifacts：运行产物三端点（报告站内可读） ----
    # 语义核心在 src.serve_run_artifacts.serve_run_artifacts（纯函数，错误以
    # {'ok': False, 'error': 'rejected'|'not_found', 'status': 400|404} 标记
    # dict 返回）；本路由层只做薄转接：ok→Response（report=HTML，plots/files=
    # 字节+media_type）；标记→HTTPException 同状态码；叶子渲染错误（ValueError
    # 族——文件损坏/零外链断言）→500 带指错（R60 口径）。report_root 请求期取
    # deps（五必查键，create_console_app 装配侧天然贯通——与 GET /api/runs 同源）。

    def _serve_artifact(run_id: str, kind: str, name: "str | None" = None):
        """serve_run_artifacts 薄转接：dict 标记→HTTPException；ok→Response。"""
        # 延迟 import：与 R56 块同口径（注册期不加载服务模块，请求期才 import）。
        from src.serve_run_artifacts.serve_run_artifacts import serve_run_artifacts

        root = deps.get("report_root")
        if not isinstance(root, str) or not root:
            raise AppError(
                f"deps['report_root'] 未注入或非非空 str（R60 运行产物端点依赖），"
                f"实际: {root!r}",
                field="report_root",
            )
        try:
            outcome = serve_run_artifacts(root, run_id, kind, name)
        except ValueError as exc:  # 叶子渲染/读盘错误上抛→500 带指错（R60）
            raise HTTPException(
                status_code=500, detail=f"运行产物服务失败（{kind}）: {exc}"
            ) from exc
        if isinstance(outcome, dict) and outcome.get("ok") is True:
            if outcome.get("kind") == "report":
                return HTMLResponse(outcome["body"])
            return Response(
                content=outcome["body"], media_type=outcome["content_type"]
            )
        status = outcome.get("status") if isinstance(outcome, dict) else None
        detail = (
            outcome.get("detail") if isinstance(outcome, dict) else repr(outcome)
        )
        raise HTTPException(
            status_code=int(status) if status in (400, 404) else 500,
            detail=detail if isinstance(detail, str) else repr(detail),
        )

    @app.get("/api/runs/{run_id}/report")
    async def get_run_report(run_id: str):
        # report.md 服务端渲染 HTML（含溯源结论徽标）——路由不与 GET /api/runs/
        # {run_id} 冲突（该路由单段参数，本路由恒三段以上路径形态）。
        return _serve_artifact(run_id, "report")

    @app.get("/api/runs/{run_id}/plots/{name}")
    async def get_run_plot(run_id: str, name: str):
        # PNG 曲线图字节（name 非 .png/含穿越→400；不存在→404）。
        return _serve_artifact(run_id, "plots", name)

    @app.get("/api/runs/{run_id}/files/{name}")
    async def get_run_file(run_id: str, name: str):
        # 白名单原始数据文件下载（白名单外/穿越→400；不存在→404）。
        return _serve_artifact(run_id, "files", name)

    # ---- R61 list_run_summaries：报告中心元数据行端点 ----
    # 语义核心在 src.list_run_summaries.list_run_summaries（纯函数——扫描
    # report_root 各运行目录读 result.json/场景副本出摘要行，result.json 缺失/
    # 损坏行降级标注 no_result 不虚构不剔除）；本路由层薄转接：report_root 请求
    # 期取 deps（与 R60 三端点同口径），根目录缺失→AppError 400（与 GET
    # /api/runs 同语义）。注意：GET /api/runs/{run_id}（create_console_app 先
    # 注册）会先匹配 /api/runs/summaries——注册后做路由序手术把字面路由移到
    # 参数路由之前（Starlette 按注册序匹配，字面路由必须在前）。

    def _r61_report_root() -> str:
        """R61 端点的 report_root 提取（deps 必查键，与 R60 块同口径）。"""
        root = deps.get("report_root")
        if not isinstance(root, str) or not root:
            raise AppError(
                f"deps['report_root'] 未注入或非非空 str（R61 运行摘要端点依赖），"
                f"实际: {root!r}",
                field="report_root",
            )
        return root

    @app.get("/api/runs/summaries")
    async def run_summaries() -> dict:
        # 延迟 import：与 R60 块同口径（注册期不加载服务模块，请求期才 import）。
        import os

        from src.list_run_summaries.list_run_summaries import list_run_summaries

        root = _r61_report_root()
        if not os.path.isdir(root):
            raise AppError(
                f"report_root 不存在或非目录: {root}", field="report_root"
            )
        rows = list_run_summaries(root)
        return {"summaries": rows, "count": len(rows)}

    # 路由序手术：把 /api/runs/summaries 移到 /api/runs/{run_id} 之前（@app.get
    # 追加到路由表尾，而参数路由已在工厂阶段注册在前——不手术则 summaries 被
    # run_id='summaries' 吞掉 404）。找不到参数路由（假件 app）时放回尾部保注册。
    _summaries_route = app.routes[-1]
    app.routes.remove(_summaries_route)
    for _idx, _route in enumerate(list(app.routes)):
        if getattr(_route, "path", None) == "/api/runs/{run_id}":
            app.routes.insert(_idx, _summaries_route)
            break
    else:
        app.routes.append(_summaries_route)

    # ---- R62 view_failure_comparison：跨轮失效对比端点 ----
    # 语义核心在 src.view_failure_comparison.view_failure_comparison（纯函数——
    # 运行集→读各轮失效电平→compare_failure_boundaries（R26）对比表+薄弱环节
    # 结论；无失效数据运行标注「未失效/无结果」，全缺附「请选择其他运行」提示）；
    # 本路由层只做 body 解析与 run_ids 形状校验（AppError 400 字段级指错），
    # ValueError（形状/穿越）转 AppError(field='run_ids')。POST 方法与本路由
    # 路径均不与 GET /api/runs/{run_id} 冲突，无需路由序手术。

    @app.post("/api/runs/compare")
    async def compare_runs(request: Request) -> dict:
        # 延迟 import：与 R60/R61 块同口径（请求期才 import 服务模块）。
        from src.view_failure_comparison.view_failure_comparison import (
            view_failure_comparison,
        )

        try:
            body = await request.json()
        except Exception as exc:  # JSONDecodeError/空 body 等→400 field='body'
            raise AppError(
                f"请求体须为 JSON 对象 {{'run_ids': list[str]}}: "
                f"{type(exc).__name__}: {exc}",
                field="body",
            ) from exc
        if not isinstance(body, dict):
            raise AppError(
                f"请求体须为 JSON 对象，实际 {type(body).__name__}: {body!r}",
                field="body",
            )
        run_ids = body.get("run_ids")
        if not isinstance(run_ids, list) or not all(
            isinstance(item, str) for item in run_ids
        ):
            raise AppError(
                f"run_ids 必须为 list[str]（运行目录名列表），实际: {run_ids!r}",
                field="run_ids",
            )
        root = _r61_report_root()
        try:
            return view_failure_comparison(run_ids, root)
        except ValueError as exc:  # 穿越形态等叶子形状拒绝→400 带指错
            raise AppError(str(exc), field="run_ids") from exc

    # ---- R63 browse_dataset_library：数据集浏览两端点 ----
    # 语义核心在 src.browse_dataset_library.browse_dataset_library（纯函数——
    # 经 index_dataset query 出 SigMF 真值对卡片+样式/日期过滤，卡片真值双源
    # =索引条目+来源运行目录场景副本；索引未建→missing 状态提示+重建入口标志，
    # 不报错拦页）；本路由层只做 query 参数透传与 QueryError→400。索引口径：
    # runs_root=deps['report_root']（操控台运行目录根即 runs/<id>/result.json+
    # recordings/ 的扫描对象），index_path=report_root/dataset-index.json
    # （dataset_index_path 派生——R63/R64 端点共用唯一口径）。

    def _r63_paths():
        """R63/R64 端点的 (index_path, runs_root) 派生（deps 必查键，同 R60 口径）。"""
        from src.browse_dataset_library.browse_dataset_library import dataset_index_path

        root = deps.get("report_root")
        if not isinstance(root, str) or not root:
            raise AppError(
                f"deps['report_root'] 未注入或非非空 str（R63 数据集浏览端点依赖），"
                f"实际: {root!r}",
                field="report_root",
            )
        return dataset_index_path(root), root

    @app.get("/api/dataset")
    async def browse_dataset(
        style: "str | None" = None,
        date_from: "str | None" = None,
        date_to: "str | None" = None,
    ) -> dict:
        # 延迟 import：与 R60-R62 块同口径（注册期不加载服务模块，请求期才 import）。
        from src.index_dataset.index_dataset import QueryError

        from src.browse_dataset_library.browse_dataset_library import (
            browse_dataset_library,
        )

        index_path, runs_root = _r63_paths()
        query: dict = {}
        if isinstance(style, str) and style.strip():
            query["style"] = style.strip()
        if isinstance(date_from, str) and date_from.strip():
            query["date_from"] = date_from.strip()
        if isinstance(date_to, str) and date_to.strip():
            query["date_to"] = date_to.strip()
        try:
            return browse_dataset_library(
                query or None, index_path=index_path, runs_root=runs_root
            )
        except QueryError as exc:  # 条件非法（未知键/日期反序等）→400 带指错
            raise AppError(str(exc), field="query") from exc

    @app.post("/api/dataset/rebuild")
    async def rebuild_dataset_index() -> dict:
        # 重建口径归 index_dataset('rebuild')：扫描 runs_root 各 run 目录
        # （result.json+recordings），损坏运行 skipped 计数不短路；本层薄转接。
        from src.index_dataset.index_dataset import index_dataset

        index_path, runs_root = _r63_paths()
        outcome = index_dataset(
            "rebuild", index_path=index_path, runs_root=runs_root
        )
        return {
            "index_status": "ready",
            "rebuilt": outcome["rebuilt"],
            "skipped": outcome["skipped"],
            "index_path": index_path,
        }

    # ---- R64 launch_replay_run：一键回放端点 ----
    # body {'run_id': str}（录音条目标识——数据页卡片「回放此条」的载荷）→
    # 索引 list 定位条目→build_replay_scenario 装载期组装（损坏录音/声明缺失
    # →ScenarioError 转 400，错误信息进响应上屏——不进后台线程后知后觉）→
    # 202+后台线程经 launch_replay_run(entry, deps['runner']) 发起（与 /api/run
    # 同款执行器与运行表：app.state.runs 可轮询，实时曲线/报告中心可见）。
    # POST 路径不与 GET /api/runs/{run_id} 冲突，无需路由序手术。

    import threading as _threading
    import uuid as _uuid
    from datetime import datetime as _datetime
    from datetime import timezone as _timezone

    from fastapi.responses import JSONResponse as _JSONResponse

    #: B26 对抗中2 转 B27 整改②：source_scenario 白名单（register 额外键透传的
    #: 来源场景收缩域——build_replay_scenario 消费键集，超出键一律剥除）。
    _SOURCE_SCENARIO_KEYS = (
        "style",
        "fs",
        "freq_hz",
        "power_dbm",
        "duration_s",
        "bands",
        "shielded_box",
        "dut_scope",
    )

    def _fence_replay_entry(entry: dict, runs_root: str) -> dict:
        """索引入口 runs_root 路径围栏+source_scenario 收缩（B26 对抗中2 转
        B27 随批整改②，调用点=POST /api/run/replay 的条目消费边界）。

        - 围栏：条目 sigmf_path 解析（'sigmf_path' 显式 > 'path' 目录最早
          .sigmf-meta）后的 realpath 必须落在 realpath(runs_root) 内——越界
          （索引被投毒指向库外路径/穿越链）→ ScenarioError（外层转 400 带
          指错）；无可解析录音→不拦（交 build_replay_scenario 按既有口径拒）；
        - 收缩：index register 额外键原样透传的 'source_scenario' 仅保留
          白名单键（_SOURCE_SCENARIO_KEYS）——索引侧夹带的任意键在此剥除；
          收缩后为空 dict → 整键剥除（build_replay_scenario 走场景副本路）。
        """
        import os as _os

        from src.launch_replay_run.build_replay_scenario import ScenarioError as _ScenarioError

        sigmf = None
        explicit_meta = entry.get("sigmf_path")
        if isinstance(explicit_meta, str) and explicit_meta.strip():
            sigmf = explicit_meta.strip()
        else:
            recordings = entry.get("path")
            if isinstance(recordings, str) and recordings.strip():
                try:
                    names = _os.listdir(recordings)
                except OSError:
                    names = []
                metas = sorted(n for n in names if n.endswith(".sigmf-meta"))
                if metas:
                    sigmf = _os.path.join(recordings, metas[0])
        if sigmf is not None:
            fence_root = _os.path.realpath(runs_root)
            resolved = _os.path.realpath(sigmf)
            if _os.path.commonpath([fence_root, resolved]) != fence_root:
                raise _ScenarioError(
                    f"录音路径越界（索引入口 runs_root 围栏）: {sigmf} 解析后 "
                    f"{resolved} 不在运行目录根 {fence_root} 内——索引条目疑似"
                    "指向库外路径，拒绝回放"
                )
        source = entry.get("source_scenario")
        if isinstance(source, dict) and source:
            shrunk = {
                key: source[key] for key in _SOURCE_SCENARIO_KEYS if key in source
            }
            fenced = dict(entry)
            if shrunk:
                fenced["source_scenario"] = shrunk
            else:
                fenced.pop("source_scenario", None)
            return fenced
        return entry

    @app.post("/api/run/replay")
    async def replay_run(request: Request) -> "_JSONResponse":
        # 延迟 import：与 R60-R63 块同口径（请求期才 import 服务模块）。
        from src.index_dataset.index_dataset import index_dataset

        from src.launch_replay_run.build_replay_scenario import (
            ScenarioError,
            build_replay_scenario,
        )

        try:
            body = await request.json()
        except Exception as exc:  # JSONDecodeError/空 body 等→400 field='body'
            raise AppError(
                f"请求体须为 JSON 对象 {{'run_id': str}}: {type(exc).__name__}: {exc}",
                field="body",
            ) from exc
        if not isinstance(body, dict):
            raise AppError(
                f"请求体须为 JSON 对象，实际 {type(body).__name__}: {body!r}",
                field="body",
            )
        run_id = body.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise AppError(
                f"run_id 必须为非空 str（录音条目标识——数据页卡片运行来源），"
                f"实际: {run_id!r}",
                field="run_id",
            )
        run_id = run_id.strip()

        # 索引定位条目（list 全量→run_id 精确匹配；query 无 run_id 条件，list 即口径）
        index_path, runs_root = _r63_paths()
        entries = index_dataset(
            "list", index_path=index_path, runs_root=runs_root
        )["entries"]
        entry = next(
            (item for item in entries if item.get("run_id") == run_id), None
        )
        if entry is None:
            raise AppError(
                f"录音条目不在库: run_id={run_id!r}（索引 {len(entries)} 条——"
                f"先 POST /api/dataset/rebuild 重建后再回放）",
                field="run_id",
            )
        # 装载期组装（请求内完成——损坏录音/声明缺失的拒绝信息进响应）；
        # 先过索引入口围栏+source_scenario 收缩（B26 对抗中2 转 B27 整改②——
        # 越界/夹带键在此拦下，与组装拒绝同走 400；收缩后的条目即回放消费对象）。
        try:
            entry = _fence_replay_entry(entry, runs_root)
            build_replay_scenario(entry)
        except ScenarioError as exc:
            raise AppError(
                f"回放场景组装失败（录音损坏或安全声明缺失）: {exc}",
                field="run_id",
            ) from exc

        replay_uuid = _uuid.uuid4().hex[:8]
        # 启动即复位共享停机旗标（与 /api/run 同口径——上一轮 /api/stop 的遗留
        # 信号不牵连本次回放）。
        deps["stop_flag"]["flag"] = False
        app.state.runs[replay_uuid] = {
            "run_id": replay_uuid,
            "status": "running",
            "started_at": _datetime.now(_timezone.utc).isoformat(),
            "replay_of": run_id,
        }

        def _replay_in_background() -> None:
            # launch/runner 一切异常只落运行表——服务绝不因单次回放炸掉。
            from src.launch_replay_run.launch_replay_run import launch_replay_run

            try:
                outcome = launch_replay_run(entry, deps["runner"])
                app.state.runs[replay_uuid]["status"] = "done"
                app.state.runs[replay_uuid]["result"] = outcome
            except BaseException as exc:  # noqa: BLE001 - 后台线程隔离边界
                app.state.runs[replay_uuid]["status"] = "failed"
                app.state.runs[replay_uuid]["error"] = f"{type(exc).__name__}: {exc}"

        _threading.Thread(
            target=_replay_in_background,
            daemon=True,
            name=f"console-replay-{replay_uuid}",
        ).start()
        return _JSONResponse(
            status_code=202,
            content={"run_id": replay_uuid, "replay_of": run_id},
        )

    # ---- R65 launch_classifier_training：AI 训练任务三端点 ----
    # 语义核心在 src.launch_classifier_training.launch_classifier_training
    # （任务表自建键空间——后台线程调 train_classifier，拒训 TrainError 终态
    # failed 附原文；run 目录根 models/ 模型文件列表）；本路由层薄转接：
    # body 形状校验（AppError 400 字段级指错）+操控台域缺省注入（index_path/
    # runs_root 与 R63/R64 同口径派生；out_path 缺省 report_root/models/
    # style_classifier.json——GET /api/ai/models 的扫描对象，显式给出则尊重）。
    # POST 路径不与既有路由冲突；GET /api/ai/train/{task_id} 单段参数路由在
    # /api/ai 命名空间内无字面同段路由，无需路由序手术。

    def _ai_models_dir() -> str:
        """R65/R67 端点的模型目录（report_root/models——list_model_files 扫描对象）。"""
        import os

        root = deps.get("report_root")
        if not isinstance(root, str) or not root:
            raise AppError(
                f"deps['report_root'] 未注入或非非空 str（R65 AI 训练端点依赖），"
                f"实际: {root!r}",
                field="report_root",
            )
        return os.path.join(root, "models")

    @app.post("/api/ai/train")
    async def ai_train(request: Request) -> "_JSONResponse":
        # 延迟 import：与 R60-R64 块同口径（请求期才 import 服务模块）。
        import os

        from src.launch_classifier_training.launch_classifier_training import (
            DEFAULT_WHERE,
            launch_classifier_training,
        )

        try:
            body = await request.json()
        except Exception as exc:  # JSONDecodeError/空 body 等→400 field='body'
            raise AppError(
                f"请求体须为 JSON 对象 {{'query': dict, 'where', 'dry_run', "
                f"'hyperparams'}}: {type(exc).__name__}: {exc}",
                field="body",
            ) from exc
        if not isinstance(body, dict):
            raise AppError(
                f"请求体须为 JSON 对象，实际 {type(body).__name__}: {body!r}",
                field="body",
            )
        query = body.get("query", {})
        if query is None:
            query = {}
        if not isinstance(query, dict):
            raise AppError(
                f"query 必须为 dict（数据集检索条件——train_classifier 数据筛选），"
                f"实际: {query!r}",
                field="query",
            )
        where = body.get("where", DEFAULT_WHERE)
        if where is None:
            where = DEFAULT_WHERE
        if not isinstance(where, str) or where not in ("remote", "local"):
            raise AppError(
                f"where 必须为 'remote' 或 'local'（执行地），实际: {where!r}",
                field="where",
            )
        dry_run = body.get("dry_run", False)
        if not isinstance(dry_run, bool):
            raise AppError(
                f"dry_run 必须为 bool（远程不真派发开关），实际: {dry_run!r}",
                field="dry_run",
            )
        hyperparams = body.get("hyperparams")
        if hyperparams is None:
            hyperparams = {}
        if not isinstance(hyperparams, dict):
            raise AppError(
                f"hyperparams 必须为 dict | None（训练超参），实际 "
                f"{type(hyperparams).__name__}",
                field="hyperparams",
            )
        index_path, runs_root = _r63_paths()
        hp = dict(hyperparams)
        hp.setdefault("index_path", index_path)
        hp.setdefault("runs_root", runs_root)
        hp.setdefault(
            "out_path", os.path.join(_ai_models_dir(), "style_classifier.json")
        )
        try:
            handle = launch_classifier_training(
                {
                    "query": query,
                    "where": where,
                    "dry_run": dry_run,
                    "hyperparams": hp,
                }
            )
        except ValueError as exc:  # 形状错（端点层已前置校验同域——兜底同口径）
            raise AppError(str(exc), field="query") from exc
        return _JSONResponse(status_code=202, content=handle)

    @app.get("/api/ai/train/{task_id}")
    async def ai_train_status(task_id: str) -> dict:
        # 任务状态轮询：running/done（附 train_classifier 完整返回）/failed
        # （附拒训/远程不可达错误原文——信息原样上屏）。
        from src.launch_classifier_training.launch_classifier_training import (
            get_training_task,
        )

        task = get_training_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"训练任务不存在: {task_id}")
        return task

    @app.get("/api/ai/models")
    async def ai_models() -> dict:
        # 模型文件列表：run 目录根 models/ 下 *.json（新在前；labels 读取损坏
        # 文件如实 None）；目录缺失→空列表（未训练提示态，不报错）。
        from src.launch_classifier_training.launch_classifier_training import (
            list_model_files,
        )

        models_dir = _ai_models_dir()
        rows = list_model_files(models_dir)
        return {"models": rows, "count": len(rows), "models_dir": models_dir}

    # ---- R66 view_cv_evaluation：评测可视化端点 ----
    # 语义核心在 src.view_cv_evaluation.view_cv_evaluation（纯函数——取数+
    # 谱特征化→grouped_cv_evaluate 出混淆矩阵/Macro-F1/泄漏三旗标+警告文案
    # 捕获回显）；本路由层薄转接：body 形状校验+索引落点注入（query 传输键，
    # 与 R65 同口径）；EvalError（分组缺失/检索非法/零匹配等 R31 拒绝）→400
    # 错误信息进响应上屏。

    @app.post("/api/ai/evaluate")
    async def ai_evaluate(request: Request) -> dict:
        # 延迟 import：与 R60-R65 块同口径（请求期才 import 服务模块）。
        from src.view_cv_evaluation.view_cv_evaluation import (
            EvalError,
            view_cv_evaluation,
        )

        try:
            body = await request.json()
        except Exception as exc:
            raise AppError(
                f"请求体须为 JSON 对象 {{'query': dict, 'model_path': str}}: "
                f"{type(exc).__name__}: {exc}",
                field="body",
            ) from exc
        if not isinstance(body, dict):
            raise AppError(
                f"请求体须为 JSON 对象，实际 {type(body).__name__}: {body!r}",
                field="body",
            )
        query = body.get("query", {})
        if query is None:
            query = {}
        if not isinstance(query, dict):
            raise AppError(
                f"query 必须为 dict（数据集筛选），实际: {query!r}", field="query"
            )
        model_path = body.get("model_path", "models/style_classifier.json")
        if not isinstance(model_path, str) or not model_path.strip():
            raise AppError(
                f"model_path 必须为非空 str（模型标识——结果页溯源回显），"
                f"实际: {model_path!r}",
                field="model_path",
            )
        index_path, runs_root = _r63_paths()
        eval_query = dict(query)
        eval_query.setdefault("index_path", index_path)
        eval_query.setdefault("runs_root", runs_root)
        try:
            return view_cv_evaluation(eval_query, model_path)
        except EvalError as exc:  # R31 拒绝族→400 错误信息进响应上屏
            raise AppError(str(exc), field="query") from exc
        except ValueError as exc:  # nfft/k 等形状错→400 同口径
            raise AppError(str(exc), field="query") from exc

    # ---- R67 infer_style_entry：主动推理端点 ----
    # 语义核心在 src.infer_style_entry.infer_style_entry（纯函数——IQ 源三选一
    # 解析→predict_style 结果行+真值双源对照（SigMF 标注→场景副本）+hit 判定；
    # 模型缺失→no_model 提示态不报错）；本路由层薄转接：body 即 source 透传+
    # 索引落点注入+缺省模型回落（report_root/models/style_classifier.json 在位
    # 即用，'model' 显式给出则尊重）；一切提示态行 200 原样返回（不阻塞）。

    @app.post("/api/ai/infer")
    async def ai_infer(request: Request) -> dict:
        # 延迟 import：与 R60-R66 块同口径（请求期才 import 服务模块）。
        import os

        from src.infer_style_entry.infer_style_entry import infer_style_entry

        try:
            body = await request.json()
        except Exception as exc:
            raise AppError(
                f"请求体须为 JSON 对象 {{'run_id'|'sigmf_path'|'query', 'model'?}}: "
                f"{type(exc).__name__}: {exc}",
                field="body",
            ) from exc
        if not isinstance(body, dict):
            raise AppError(
                f"请求体须为 JSON 对象（IQ 源选择），实际 {type(body).__name__}: {body!r}",
                field="body",
            )
        source = dict(body)
        index_path, runs_root = _r63_paths()
        source.setdefault("index_path", index_path)
        source.setdefault("runs_root", runs_root)
        if "model" not in source:
            # 缺省模型回落：run 目录根 models/style_classifier.json 在位即用
            # （不在位保持 None——R32 no_model 提示态，不报错）。
            default_model = os.path.join(
                _ai_models_dir(), "style_classifier.json"
            )
            if os.path.isfile(default_model):
                source["model"] = default_model
        try:
            return infer_style_entry(source)
        except ValueError as exc:  # 源形状错→400 字段级指错（提示态不在此列）
            raise AppError(str(exc), field="source") from exc

    # ---- R68–R74 后续批次注册块：到货批次按 R 号顺序在此逐批追加 ----

    return app
