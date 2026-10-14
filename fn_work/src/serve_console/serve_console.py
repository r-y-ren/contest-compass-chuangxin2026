"""Web 服务入口：create_console_app 装配+uvicorn 拉起——重写规约与签名意图详见 fn_docs/responsibility.md。

可测试性设计（测试不真起服务）：
- config 形状错→ValueError（装配前拦截，消息指错键）；deps 由 config 组装——
  runner 缺省构造**真实运行器**（_make_default_runner：薄载荷名解析→场景文件
  全口径装载→薄字段覆盖合并→run_scenario 真跑测试，「开始」即真跑；R58 快速
  通道：缺省 runner 同时挂实时流桥——运行期三路帧经 push_realtime_kpi 推共享
  hub，延迟统计并入运行结果 'realtime' 键）、stop_flag 共享 dict（config 提供
  则原对象直通，供 /api/stop 与急停路径共享；B24 C1：缺省 runner 把它经
  run_scenario(stop=…) 贯通管线协作停，后端句柄写回其 'backend' 键）、
  run_ctx 急停运行上下文（B24 C1：deps['run_ctx']→app.state.run_ctx——停止
  路由把 stop_flag['backend'] 同步进去供 trigger_emergency_stop 直停真后端）、
  scenario_dir/report_root/static_pages 直传 create_console_app（deps 另携
  'hub' 共享 /ws hub 容器——create_console_app 原对象优先，极小改造已申报；
  显式 runner 不挂桥也不接停容器贯通）；
- 开箱即用（README 方式三）：scenario_dir 缺失→os.makedirs(exist_ok=True) 按
  config 路径建空目录（相对 cwd），/api/scenarios 即空卡而非 400；
- static_pages 未传（None）→ 七页产出（R56 断网全可用口径）：localize_console_assets
  缺省产出七区骨架（vendor 不向 scenario_dir 落死副本——/assets/vendor 路由恒
  服务仓内源文件，落盘无人消费即 157KB 白写；assets_dir 传仓内 vendor 自身位置，
  samefile 守卫短路跳过复制），运行页 index 的真实内容由 render_console_pages(
  scenario_dir, {}) 产出后经 replace_cdn_with_vendor 切本地 vendor（CDN script→
  /assets/vendor/vue.global.prod.js）覆盖注入 deps——用户无需预渲染即可 GET
  /pages/<七页 slug>，全站零 CDN；运行页另在 </body> 前注入 R57 场景编辑器
  区块（edit_scenario_ui 产出，装配期场景卡片为下拉/卡片视图初值）与 R58
  三路实时图区（stream_realtime_console 装配助手产出——KPI/频谱瀑布/事件
  时间线，消费 /ws 三路帧）；reports 页同式注入 R60 报告查看区
  （serve_run_artifacts 产出——?run=<id> 驱动 fetch /api/runs/{id}/report
  渲染上屏+plots 图列表+files 下载链接+溯源结论徽标）；
- config['dry_run']=True→不拉起不检端口，返回 {'app', 'launched': False, 'port',
  'host'}（测试经 TestClient 直接打 create 路由）；
- 真拉起序：先探端口占用→ConsoleError（dry_run 下不检）；再延迟 import uvicorn
  （缺库→ConsoleError 含 pip 提示）；uvicorn.run(app, host, port) 阻塞式服务，
  返回 {'launched': True, 'port', 'host'}。
- create_console_app 的装配错误（deps 缺键/fastapi 缺库）以 AppError 原样上抛
  （ValueError 子类，fastapi 缺库消息自带 pip 提示，不在此重复包装）。
"""
import os
import socket
import threading

from src.edit_scenario_ui.edit_scenario_ui import edit_scenario_ui
from src.load_scenario.load_scenario import ScenarioError, load_scenario
from src.load_scenario.load_scenario import _ENVELOPE_KEYS as _SCENARIO_ENVELOPE_KEYS
from src.load_scenario.validate_scenario_schema import _KNOWN_KEYS as _SCENARIO_KNOWN_KEYS
from src.localize_console_assets.localize_console_assets import (
    localize_console_assets,
    replace_cdn_with_vendor,
)
from src.localize_console_assets.mount_console_extensions import VENDOR_VUE_PATH
from src.render_console_pages.build_scenario_cards import build_scenario_cards
from src.render_console_pages.render_console_pages import render_console_pages
from src.run_demo.run_demo import run_scenario
from src.serve_run_artifacts.report_view_area import build_report_view_area
from src.stream_realtime_console.stream_realtime_console import (
    build_realtime_charts,
    stream_realtime_console,
)

from .create_console_app import AppError, create_console_app

__all__ = [
    "AppError",
    "ConsoleError",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "UVICORN_PIP_HINT",
    "serve_console",
]

#: 缺省监听端口/地址（可用 config['port']/config['host'] 覆盖）。
DEFAULT_PORT = 8000
DEFAULT_HOST = "127.0.0.1"

#: uvicorn 缺库安装提示（ConsoleError 消息原文含 'pip'，测试据此断言）。
UVICORN_PIP_HINT = "pip install 'uvicorn[standard]'（见 requirements.txt）"

#: 薄载荷可覆盖合并的键域：validate_scenario_schema 在册键（场景字段+执行信封）
#: ∪ load_scenario 信封键（bands/shielded_box/dut_scope/declarations）——
#: 'name'（名解析专用）与 UI 专用键（如 'atten_db'，schema 不在册）不并入，
#: 否则合并产物过不了 run_scenario 的未知键校验。
_MERGEABLE_KEYS = frozenset(_SCENARIO_KNOWN_KEYS) | frozenset(_SCENARIO_ENVELOPE_KEYS)


def _index_cards(scenario_dir: str) -> list:
    """index 页编辑器区块的装配期卡片数据（与 render_console_pages 的内嵌口径
    一致：*.yaml|*.yml 排序→build_scenario_cards；目录不可读→[] 空卡不报错）。"""
    try:
        names = os.listdir(scenario_dir)
    except OSError:
        return []
    files = sorted(
        os.path.join(scenario_dir, n) for n in names if n.endswith((".yaml", ".yml"))
    )
    return build_scenario_cards(files)


class ConsoleError(RuntimeError):
    """服务拉起失败：端口被占用 / uvicorn 运行库缺失。"""


def _snapshot_run_dirs(report_root: str) -> "list[str]":
    """report_root 下既有运行目录名清单（不可读→[]——实时流桥发现基线素材）。"""
    try:
        names = os.listdir(report_root)
    except OSError:
        return []
    return [n for n in names if os.path.isdir(os.path.join(report_root, n))]


def _make_default_runner(scenario_dir: str, report_root: str, hub: dict, stop_flag: dict):
    """构造缺省真实 runner（config['runner'] 未注入时）：网页「开始」真跑测试。

    载荷两形态（POST /api/run 的 scenario dict）：
    - 全载荷（含非空 'style'）→ 原样交 run_scenario（未知键如实报校验失败）；
    - 薄载荷（缺 'style'）→ 须携 'name'：读 scenario_dir/<name>.yaml 经
      load_scenario 全口径装载（schema+红线+规范化，与 CLI 文件路线同纪律），
      薄字段（power_dbm/judge_per_threshold 等在册键）作覆盖合并——'name' 与
      schema 不在册的 UI 键（如 'atten_db'）不并入。
    落位 run_scenario(out_root=report_root)：运行目录与 report.md 真实生成，
    /api/runs/{id} 的 result 即真实运行结果；台账不动（ledger=False，操控台
    不写清单——CLI --no-ledger 语义缺省化）。

    R58 快速通道（改造点，申报）：hub 挂实时流桥——run_scenario 为无头管线，
    不内嵌推帧钩子；runner 发起运行的同时启动 stream_realtime_console 尾随
    report_root 下新运行目录（发现基线在运行前快照，规避竞态），其 kpi.csv/
    monitor.csv/events.jsonl 三路增量转帧（叶子 render_triple_stream_charts
    帧协议）经 push_realtime_kpi 推入 hub（操控台 /ws）；运行收尾（stop 信号
    或 result.json 出现）桥退出，端到端延迟统计（行落盘→广播发送戳 P50/P95，
    measure_refresh_latency 口径）并入运行结果 'realtime' 键——
    app.state.runs 条目即「写入运行结果 JSON」的操控台侧落点。runner 的
    装载/合并语义不变；桥线程异常隔离（统计缺省不并入，绝不反杀运行）。

    B24 C1（急停真停接线，申报）：stop_flag 由 serve_console 传入（共享停容器
    ——/api/run 启动复位、/api/stop 置位的同一 dict）：① 经 run_scenario(stop=…)
    贯通管线协作检查（功率档间/阶段边界），后端打开后管线把句柄写回
    stop_flag['backend']，停止路由（create_console_app）同步进 deps['run_ctx']
    供 trigger_emergency_stop 直停真后端；② 桥停旗同用 stop_flag——/api/stop
    即刻冻结帧流（不再等运行收尾）；③ 运行收尾的 finally 置
    stop_flag['flag']=True（桥冲刷退出语义不变——共享旗由下一次 /api/run
    启动复位）。
    """

    def _runner(scenario: dict) -> dict:
        if not isinstance(scenario, dict):
            raise ValueError(
                f"scenario 必须为 dict（全载荷或薄载荷 {{'name', …}}），实际 "
                f"{type(scenario).__name__}: {scenario!r}"
            )
        merged = {k: v for k, v in scenario.items() if k != "name"}
        style = merged.get("style")
        if not (isinstance(style, str) and style.strip()):
            # 薄载荷：name→场景文件全口径装载，薄字段（在册键）覆盖合并。
            name = scenario.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    "薄载荷缺 'style' 时须携 'name'（场景名→"
                    f"{scenario_dir}/<name>.yaml 全口径装载），实际: {scenario!r}"
                )
            try:
                base = load_scenario(
                    os.path.join(scenario_dir, name.strip() + ".yaml")
                )
            except ScenarioError as exc:
                raise ValueError(
                    f"场景文件装载失败（{name.strip()}.yaml）: {exc}"
                ) from exc
            base.update(
                {k: v for k, v in merged.items() if k in _MERGEABLE_KEYS}
            )
            merged = base
        # R58：实时流桥——尾随线程与运行线程并行，收尾 stop→join 后并入统计。
        # B24 C1：桥停旗=共享停容器 stop_flag（/api/stop 即刻冻结帧流）。
        run_ctx_local = {
            "report_root": report_root,
            "baseline_runs": set(_snapshot_run_dirs(report_root)),
            "result": {},
            "stop": stop_flag,
        }
        bridge_stats: dict = {}

        def _run_bridge() -> None:
            try:
                bridge_stats["realtime"] = stream_realtime_console(run_ctx_local, hub)
            except Exception:  # noqa: BLE001 - 桥绝不反杀运行（统计缺省不并入）
                bridge_stats["realtime"] = None

        bridge = threading.Thread(
            target=_run_bridge, daemon=True, name="console-realtime-bridge"
        )
        bridge.start()
        try:
            result = run_scenario(merged, out_root=report_root, stop=stop_flag)
        finally:
            stop_flag["flag"] = True  # 运行收尾：桥最终冲刷后退出
            bridge.join(timeout=10)
        realtime = bridge_stats.get("realtime")
        if isinstance(result, dict) and isinstance(realtime, dict):
            result["realtime"] = realtime  # 延迟统计入运行结果 JSON（操控台侧）
        return result

    return _runner


def _validate_config(config: dict) -> "tuple[int, str, bool]":
    """config 形状校验：非 dict/路径端口类型不符→ValueError；返回 (port, host, dry_run)。"""
    if not isinstance(config, dict):
        raise ValueError(
            f"config 必须为 dict（端口/运行根目录/runner 等），实际 "
            f"{type(config).__name__}: {config!r}"
        )
    for key in ("scenario_dir", "report_root"):
        value = config.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"config[{key!r}] 必须为非空 str 路径，实际 {value!r}")
    host = config.get("host", DEFAULT_HOST)
    if not isinstance(host, str) or not host:
        raise ValueError(f"config['host'] 必须为非空 str，实际 {host!r}")
    port = config.get("port", DEFAULT_PORT)
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValueError(f"config['port'] 必须为 int（1-65535），实际 {port!r}")
    if not 0 < port < 65536:
        raise ValueError(f"config['port'] 超出合法范围 1-65535: {port}")
    dry_run = config.get("dry_run", False)
    if not isinstance(dry_run, bool):
        raise ValueError(f"config['dry_run'] 必须为 bool，实际 {dry_run!r}")
    if "runner" in config and not callable(config["runner"]):
        raise ValueError(
            f"config['runner'] 必须可调用（scenario dict→result dict），实际 "
            f"{config['runner']!r}"
        )
    if "stop_flag" in config and not isinstance(config["stop_flag"], dict):
        raise ValueError(
            f"config['stop_flag'] 必须为共享 dict（{{'flag': False}}），实际 "
            f"{type(config['stop_flag']).__name__}"
        )
    if config.get("static_pages") is not None and not isinstance(config["static_pages"], dict):
        raise ValueError(
            f"config['static_pages'] 须为 dict|None，实际 "
            f"{type(config['static_pages']).__name__}"
        )
    return port, host, dry_run


def _port_in_use(host: str, port: int) -> bool:
    """探测 (host, port) 是否已被占用（探测 bind 失败即占用；SO_REUSEADDR 不影响
    与活动监听的冲突判定，只放宽 TIME_WAIT 复用）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return True
    return False


def serve_console(config: dict) -> dict:
    """Web 服务入口：组装 deps→create_console_app→按 dry_run 决定是否 uvicorn 拉起。

    Args:
        config: 服务配置 dict——必需 'scenario_dir'/'report_root'（非空 str 路径；
            scenario_dir 缺失即按该路径建空目录——相对 cwd 解析，空态页面/空卡
            列表开箱即用）；可选 'port'（int 1-65535，缺省 8000）、'host'（str，
            缺省 127.0.0.1）、'runner'（callable，缺省 _make_default_runner 构造
            真实运行器——薄载荷合并场景文件后 run_scenario 真跑）、'stop_flag'
            （共享 dict，缺省新建）、'static_pages'（dict|None，缺省 None=七页
            产出：localize_console_assets 骨架+render_console_pages 运行页经
            CDN→vendor 切换，全站零 CDN）、'dry_run'
            （bool，缺省 False）。

    Returns:
        dry_run: {'app': FastAPI 实例, 'launched': False, 'port', 'host'}；
        真拉起（uvicorn.run 返回后）: {'launched': True, 'port', 'host'}。

    Raises:
        ValueError: config 形状错（非 dict/键类型不符/端口越界）。
        ConsoleError: scenario_dir 创建失败 / 端口被占用 / uvicorn 运行库缺失
            （消息含 pip 提示）。
        AppError: deps 装配失败或 fastapi 缺库（create_console_app 原样透传）。
    """
    port, host, dry_run = _validate_config(config)

    # ---- 开箱即用：scenario_dir 缺失即建空目录（相对 cwd；空态页面/空卡） ----
    scenario_dir = config["scenario_dir"]
    try:
        os.makedirs(scenario_dir, exist_ok=True)
    except OSError as exc:  # 路径不可达/无权限等：起服务也无从服务场景列表
        raise ConsoleError(
            f"scenario_dir 创建失败: {scenario_dir}（{exc}）——请检查路径与权限"
        ) from exc

    # ---- 开箱即用：static_pages 未传 → 七页产出（R56 断网全可用口径） ----
    # localize_console_assets 缺省产出七区骨架；assets_dir 指到仓内 vendor 自身
    # 所在位置（VENDOR_VUE_PATH 的上两级=localize 模块目录），落盘目标恰为仓内
    # vendor 源文件自身——samefile 守卫短路跳过复制，scenario_dir 零 vendor 落盘
    # （/assets/vendor 路由恒服务仓内文件，副本无人消费即白写；vendor 源缺失仍
    # 照常 ConsoleAssetError 禁回退 CDN）。运行页 index 的真实内容由
    # render_console_pages 产出后经 replace_cdn_with_vendor 切本地 vendor 覆盖
    # （键带 .html 后缀，对齐 /pages 无后缀名回退口径）。
    static_pages = config.get("static_pages")
    if static_pages is None:
        skeleton = localize_console_assets(str(VENDOR_VUE_PATH.parent.parent))
        static_pages = {f"{slug}.html": doc for slug, doc in skeleton.items()}
        index_html = replace_cdn_with_vendor(
            render_console_pages(scenario_dir, {})["pages"]["index.html"]
        )
        # R57 快速通道：场景编辑器区块注入 index 运行页（调用方=serve_console
        # 运行页区块挂载）——纯静态资产，在 </body> 前单点插入（Vue 的 #app
        # 之外，区块自足不依赖 Vue 实例）；显式 static_pages 直通不注入。
        # R58 快速通道：三路实时图区紧随其后注入（经 stream_realtime_console
        # 装配助手 build_realtime_charts→叶子 render_triple_stream_charts——
        # KPI 曲线/频谱瀑布/事件时间线，消费 /ws 三路帧；同样仅缺省装配路径）。
        static_pages["index.html"] = index_html.replace(
            "</body>",
            edit_scenario_ui(_index_cards(scenario_dir))
            + "\n"
            + build_realtime_charts()
            + "\n</body>",
            1,
        )
        # R60 快速通道：报告查看区注入 reports 页（报告阅读视图挂载点——JS 从
        # URL 参数 ?run=<运行目录名> 取运行号→fetch /api/runs/{id}/report 服务端
        # 渲染 HTML 上屏+plots 图列表+files 下载链接+溯源结论徽标；端点经
        # mount_console_extensions 注册，report_root 即本 deps['report_root']）。
        # 同 R57/R58 口径：仅缺省装配路径注入，显式 static_pages 直通不注入。
        static_pages["reports.html"] = static_pages["reports.html"].replace(
            "</body>", build_report_view_area() + "\n</body>", 1
        )

    stop_flag = config.get("stop_flag")
    if not isinstance(stop_flag, dict):
        stop_flag = {"flag": False}
    # R58 快速通道：serve_console 先建共享 /ws hub 容器——缺省 runner 的实时
    # 流桥此刻就要持有 hub 引用（create_console_app 稍后才创建 app：deps 携
    # 'hub' 则原对象优先——create_console_app 极小改造，已申报）。
    hub: dict = {}
    # B24 C1：急停运行上下文（deps['run_ctx']→app.state.run_ctx）——含 backend
    # 通道：缺省 runner 的共享停容器在 run_scenario 后端打开后写回 'backend'
    # 键，create_console_app 停止路由同步进本 ctx，trigger_emergency_stop 即
    # 直停真后端（此前 console 侧恒拿不到句柄→no_backend 空转）；急停结果落
    # run_ctx['emergency_stop']。显式 runner 不写回句柄，维持缺省 None 口径。
    run_ctx: dict = {}
    deps = {
        "runner": (
            config["runner"]
            if "runner" in config
            else _make_default_runner(
                scenario_dir, config["report_root"], hub, stop_flag
            )
        ),
        "stop_flag": stop_flag,
        "scenario_dir": scenario_dir,
        "report_root": config["report_root"],
        "static_pages": static_pages,
        "hub": hub,
        "run_ctx": run_ctx,
    }
    app = create_console_app(deps)

    if dry_run:  # 测试路径：不起服务不检端口，app 交由 TestClient 直接驱动
        return {"app": app, "launched": False, "port": port, "host": host}

    if _port_in_use(host, port):
        raise ConsoleError(
            f"端口已被占用: {host}:{port}（换 config['port'] 或先释放占用进程）"
        )

    try:  # 延迟 import：无 uvicorn 环境给 ConsoleError+pip 提示（不炸模块装载）
        import uvicorn
    except ImportError as exc:
        raise ConsoleError(f"uvicorn 运行库缺失——{UVICORN_PIP_HINT}") from exc

    uvicorn.run(app, host=host, port=port)
    return {"launched": True, "port": port, "host": host}
