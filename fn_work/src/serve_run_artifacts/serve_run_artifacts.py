"""运行产物服务端点：report（markdown 渲染 HTML）/plots（PNG）/files（原始数据下载）+溯源结论回显+路径穿越拒绝——重写规约与签名意图详见 fn_docs/responsibility.md（R60 L0）。

端点语义（R60，经 mount_console_extensions 注册为 GET /api/runs/{run_id}/report、
/api/runs/{run_id}/plots/{name}、/api/runs/{run_id}/files/{name}；本函数为纯函数
核心——run_root 由调用方 deps 注入，不做 IO 之外的环境耦合）：
- kind='report'：report.md 经 render_report_html 服务端渲染（plots 相对引用已改
  指端点、零外链断言），并读该 run 的 result.json 'traceability' 字段——结论以
  徽标 ``<div id="traceability-badge" data-passed="true|false|none">`` 注入 body
  顶部（回显 verify_report_traceability 的溯源校验结论）+原对象随 dict 一并返回；
  result.json 缺失/损坏/无该字段→徽标标「无结论」不虚构、不反杀报告服务；
- kind='plots'：plots/<name> PNG 文件字节（name 须 .png 后缀、纯文件名）；
- kind='files'：白名单原始数据文件内容（kpi.csv/events.jsonl/monitor.csv/
  result.json/run.log/scenario.yaml/report.md——白名单外一律拒）；
- 错误不抛异常（路由层按返回 dict 的 error/status 转响应）：
  - NotFound 型 ``{'ok': False, 'error': 'not_found', 'status': 404, 'detail': …}``
    ——run_root 下无该 run 目录、report.md/目标 PNG/白名单文件不存在；
  - 拒绝型 ``{'ok': False, 'error': 'rejected', 'status': 400, 'detail': …}``
    ——name 路径穿越（含 ..、/、\\\\、绝对路径）、plots 非 .png、files 白名单外、
    kind 未知、run_id 含穿越形态（run_id 嵌入 URL，早拒）；
- 渲染错误上抛（本函数不捕获）：render_report_html 的 ValueError（文件损坏/零外链
  断言命中/读盘失败）原样传播——由端点转 500 带指错（R60 口径）。
"""
import json
import os

from .render_report_html import render_report_html

__all__ = ["serve_run_artifacts", "FILES_WHITELIST", "TRACEABILITY_BADGE_ID"]

#: files 白名单（文件名→Content-Type；run 八件套中的文件类成员——白名单外拒）。
FILES_WHITELIST = {
    "kpi.csv": "text/csv",
    "monitor.csv": "text/csv",
    "events.jsonl": "application/x-ndjson",
    "result.json": "application/json",
    "run.log": "text/plain",
    "scenario.yaml": "text/yaml",
    "report.md": "text/markdown",
}

#: 溯源结论徽标元素 id（注入报告 HTML body 顶部——报告页回显锚点）。
TRACEABILITY_BADGE_ID = "traceability-badge"

#: run 结果文件（溯源结论来源；缺失/损坏→徽标「无结论」，不虚构）。
_RESULT_FILENAME = "result.json"

#: 报告文件名（与 build_report.REPORT_FILENAME 对齐）。
_REPORT_FILENAME = "report.md"

#: 合法 kind 全集。
_KINDS = ("report", "plots", "files")


def _reject(detail: str) -> dict:
    """拒绝型标记（路由层转 400）：路径穿越/白名单外/形状非法。"""
    return {"ok": False, "error": "rejected", "status": 400, "detail": detail}


def _not_found(detail: str) -> dict:
    """NotFound 型标记（路由层转 404）：运行或文件不存在。"""
    return {"ok": False, "error": "not_found", "status": 404, "detail": detail}


def _has_traversal(name: object) -> bool:
    """穿越形态判定：非 str/空、含 / 或 \\\\、含 ..、绝对路径、. 本身。"""
    if not isinstance(name, str) or not name:
        return True
    return (
        os.path.isabs(name)
        or "/" in name
        or "\\" in name
        or ".." in name
        or name in {".", ".."}
    )


def _read_traceability(run_dir: str):
    """读 run 的 result.json 'traceability' 字段（best-effort）。

    Returns:
        (trace dict | None, 状态说明 str)——trace=None 且说明「无结论」时徽标
        data-passed="none"；result.json 缺失/损坏/字段非 dict 同为无结论，
        不虚构、不反杀报告服务。
    """
    path = os.path.join(run_dir, _RESULT_FILENAME)
    if not os.path.isfile(path):
        return None, f"无结论（{_RESULT_FILENAME} 不存在）"
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, f"无结论（{_RESULT_FILENAME} 读取失败: {type(exc).__name__}）"
    if not isinstance(payload, dict):
        return None, f"无结论（{_RESULT_FILENAME} 非 JSON 对象）"
    trace = payload.get("traceability")
    if not isinstance(trace, dict):
        return None, f"无结论（{_RESULT_FILENAME} 无 traceability 字段）"
    return trace, (
        "通过" if trace.get("passed") is True else "未通过（存在不可溯数字）"
    )


def _traceability_badge(trace, note: str) -> str:
    """溯源结论徽标 HTML（注入报告 body 顶部的回显锚点）。

    data-passed：true/false（trace 结论在案）/none（无结论——note 说明原因，
    不虚构）。文本附可溯计数摘要（字段缺失时省略，不编造）。
    """
    if trace is None:
        return (
            f'<div id="{TRACEABILITY_BADGE_ID}" class="trace-badge" '
            f'data-passed="none">溯源校验：{note}</div>'
        )
    passed = trace.get("passed") is True
    parts = [f"溯源校验：{'通过' if passed else '未通过'}"]
    n_numbers = trace.get("n_numbers")
    n_traced = trace.get("n_traced")
    if isinstance(n_numbers, int) and isinstance(n_traced, int):
        parts.append(f"可溯 {n_traced}/{n_numbers}")
    mismatches = trace.get("mismatches")
    if isinstance(mismatches, list):
        parts.append(f"差异 {len(mismatches)} 条")
    return (
        f'<div id="{TRACEABILITY_BADGE_ID}" class="trace-badge" '
        f'data-passed="{"true" if passed else "false"}">{" · ".join(parts)}</div>'
    )


def serve_run_artifacts(run_root: str, run_id: str, kind: str, name: str | None = None) -> dict:
    """运行产物服务端点：report（markdown 渲染 HTML）/plots（PNG）/files（原始数据下载）+溯源结论回显+路径穿越拒绝（详见 fn_docs/responsibility.md 功能块）。

    Args:
        run_root: 运行根目录（report_root——各 run 目录的父；非 str/PathLike
            →ValueError（编程错误早暴露））。
        run_id: 运行目录名（run_root 下一级目录名；含穿越形态→拒绝型标记）。
        kind: 'report'|'plots'|'files'（未知→拒绝型标记）。
        name: plots/files 的文件名（纯文件名；report 忽略该参数）。穿越形态
            （含 ..、/、\\\\、绝对路径）→拒绝型标记；plots 须 .png 后缀；
            files 须在 FILES_WHITELIST 白名单内。

    Returns:
        成功（'ok': True）:
          - kind='report'：``{'ok': True, 'kind': 'report', 'content_type':
            'text/html', 'body': HTML str（body 顶部含 #traceability-badge 徽标）,
            'traceability': dict|None（result.json 的 traceability 原对象，
            无结论为 None）, 'run_id': run_id}``；
          - kind='plots'：``{'ok': True, 'kind': 'plots', 'content_type':
            'image/png', 'body': bytes（PNG 文件字节）, 'name': name,
            'run_id': run_id}``；
          - kind='files'：``{'ok': True, 'kind': 'files', 'content_type':
            <白名单映射>, 'body': bytes（文件原始字节）, 'name': name,
            'run_id': run_id}``；
        失败（'ok': False，不抛异常——路由层按 'status' 键转 HTTP 状态）:
          - ``{'ok': False, 'error': 'rejected', 'status': 400, 'detail': …}``
            ——路径穿越/非 .png/白名单外/未知 kind；
          - ``{'ok': False, 'error': 'not_found', 'status': 404, 'detail': …}``
            ——运行目录或目标文件不存在。

    Raises:
        ValueError: run_root 非 str/PathLike 路径（编程错误）；render_report_html
            的渲染错误（文件损坏/零外链断言命中等）原样上抛——由端点转 500 带指错。
    """
    if isinstance(run_root, os.PathLike):
        run_root = os.fspath(run_root)
    if not isinstance(run_root, str) or not run_root:
        raise ValueError(
            f"run_root 必须为 str/os.PathLike 路径（report_root），实际 "
            f"{type(run_root).__name__}: {run_root!r}"
        )

    if _has_traversal(run_id):
        return _reject(
            f"run_id 非法（须为 run_root 下的纯目录名，禁含 /、\\\\、.. 或绝对"
            f"路径——run_id 嵌入 /api/runs/{{run_id}}/ URL）: {run_id!r}"
        )
    if kind not in _KINDS:
        return _reject(
            f"kind 必须为 {'/'.join(_KINDS)} 之一，实际: {kind!r}"
        )

    run_dir = os.path.join(run_root, run_id)
    if not os.path.isdir(run_dir):
        return _not_found(f"运行不存在: {run_id!r}（{run_root} 下无该目录）")

    if kind == "report":
        report_path = os.path.join(run_dir, _REPORT_FILENAME)
        if not os.path.isfile(report_path):
            return _not_found(
                f"报告不存在: {run_id!r}/{_REPORT_FILENAME}"
            )
        body = render_report_html(report_path, run_id)  # 渲染错误原样上抛（→500）
        trace, note = _read_traceability(run_dir)
        badge = _traceability_badge(trace, note)
        body = body.replace("<body>", f"<body>\n{badge}", 1)
        return {
            "ok": True,
            "kind": "report",
            "content_type": "text/html",
            "body": body,
            "traceability": trace,
            "run_id": run_id,
        }

    if kind == "plots":
        if _has_traversal(name):
            return _reject(
                f"plots 文件名非法（须为纯文件名，禁含 /、\\\\、.. 或绝对路径）: "
                f"{name!r}"
            )
        if not isinstance(name, str) or not name.lower().endswith(".png"):
            return _reject(f"plots 仅服务 PNG 曲线图（.png 后缀）: {name!r}")
        path = os.path.join(run_dir, "plots", name)
        if not os.path.isfile(path):
            return _not_found(f"曲线图不存在: {run_id!r}/plots/{name}")
        with open(path, "rb") as handle:
            return {
                "ok": True,
                "kind": "plots",
                "content_type": "image/png",
                "body": handle.read(),
                "name": name,
                "run_id": run_id,
            }

    # kind == 'files'
    if _has_traversal(name):
        return _reject(
            f"files 文件名非法（须为纯文件名，禁含 /、\\\\、.. 或绝对路径）: {name!r}"
        )
    if name not in FILES_WHITELIST:
        return _reject(
            f"文件不在下载白名单 {sorted(FILES_WHITELIST)} 内: {name!r}"
        )
    path = os.path.join(run_dir, name)
    if not os.path.isfile(path):
        return _not_found(f"文件不存在: {run_id!r}/{name}")
    with open(path, "rb") as handle:
        return {
            "ok": True,
            "kind": "files",
            "content_type": FILES_WHITELIST[name],
            "body": handle.read(),
            "name": name,
            "run_id": run_id,
        }
