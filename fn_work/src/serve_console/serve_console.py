"""Web 服务入口：create_console_app 装配+uvicorn 拉起——重写规约与签名意图详见 fn_docs/responsibility.md。

可测试性设计（测试不真起服务）：
- config 形状错→ValueError（装配前拦截，消息指错键）；deps 由 config 组装——
  runner 缺省构造**真实运行器**（_make_default_runner：薄载荷名解析→场景文件
  全口径装载→薄字段覆盖合并→run_scenario 真跑测试，「开始」即真跑）、stop_flag
  共享 dict（config 提供则原对象直通，供 /api/stop 与急停路径共享）、
  scenario_dir/report_root/static_pages 直传 create_console_app；
- 开箱即用（README 方式三）：scenario_dir 缺失→os.makedirs(exist_ok=True) 按
  config 路径建空目录（相对 cwd），/api/scenarios 即空卡而非 400；
  static_pages 未传（None）→ 就地调 render_console_pages(scenario_dir, {})
  自动产出缺省页面资产（Vue3 CDN 单文件 HTML，pages 键带 .html 后缀）注入
  deps——用户无需预渲染即可 GET /pages/index；
- config['dry_run']=True→不拉起不检端口，返回 {'app', 'launched': False, 'port',
  'host'}（测试经 TestClient 直接打 create 路由）；
- 真拉起序：先探端口占用→ConsoleError（dry_run 下不检）；再延迟 import uvicorn
  （缺库→ConsoleError 含 pip 提示）；uvicorn.run(app, host, port) 阻塞式服务，
  返回 {'launched': True, 'port', 'host'}。
- create_console_app 的装配错误（deps 缺键/fastapi 缺库）以 AppError 原样上抛
  （ValueError 子类，fastapi 缺库消息自带 pip 提示，不在此重复包装）。
"""
from __future__ import annotations

import os
import socket

from src.load_scenario.load_scenario import ScenarioError, load_scenario
from src.load_scenario.load_scenario import _ENVELOPE_KEYS as _SCENARIO_ENVELOPE_KEYS
from src.load_scenario.validate_scenario_schema import _KNOWN_KEYS as _SCENARIO_KNOWN_KEYS
from src.render_console_pages.render_console_pages import render_console_pages
from src.run_demo.run_demo import run_scenario

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


class ConsoleError(RuntimeError):
    """服务拉起失败：端口被占用 / uvicorn 运行库缺失。"""


def _make_default_runner(scenario_dir: str, report_root: str):
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
        return run_scenario(merged, out_root=report_root)

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
            （共享 dict，缺省新建）、'static_pages'（dict|None，缺省 None=就地
            render_console_pages(scenario_dir, {}) 自动渲染注入）、'dry_run'
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

    # ---- 开箱即用：static_pages 未传 → 自动渲染缺省页面资产（Vue3 CDN 单文件） ----
    static_pages = config.get("static_pages")
    if static_pages is None:
        static_pages = render_console_pages(scenario_dir, {})["pages"]

    stop_flag = config.get("stop_flag")
    if not isinstance(stop_flag, dict):
        stop_flag = {"flag": False}
    deps = {
        "runner": (
            config["runner"]
            if "runner" in config
            else _make_default_runner(scenario_dir, config["report_root"])
        ),
        "stop_flag": stop_flag,
        "scenario_dir": scenario_dir,
        "report_root": config["report_root"],
        "static_pages": static_pages,
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
