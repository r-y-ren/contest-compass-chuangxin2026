"""报告中心元数据行：扫描 report_root 各运行目录读 result.json/场景副本提取摘要——R61 L0。

行契约（每行恒齐 9 键；缺数据的键为 None/[]/'未知'——降级标注不虚构、行不剔除）：

- ``run_id``：运行目录名（report_root 下一级目录名——R60 三端点与
  /pages/reports?run=<run_id> 钻取链接的同一口径）；
- ``started_at``：result.json ``started_at``（epoch 秒，float；缺失/损坏→None
  ——排序回落目录 mtime，见下）；
- ``scenario_name``：场景名（场景副本 scenario.yaml 的 ``name``→``scenario_type``
  →'未知'——现行 run 管线场景副本不含 name，scenario_type 即场景类型名）；
- ``style``：样式（场景副本 ``style``→失效电平首条目 ``style``→'未知'）；
- ``backend``：后端（result.json ``backend``→场景副本 ``backend``→'未知'——
  result.json 侧为后端类名（如 'SimBackend'），场景副本侧为注册名（如 'sim'），
  均为真实记录，不归一不虚构）；
- ``status``：``'completed'|'failed'``（run_demo 双确认口径：result.json
  ``status``='done' **且** ``scenario_result.status``='completed' 才 completed
  ——判据触发/baseline_rejected/收尾失败均如实 'failed'）或 ``'no_result'``
  （result.json 缺失/损坏/非 JSON 对象——降级标注行不剔除，其余键尽力从场景
  副本与目录事实补齐）；
- ``failure_levels``：失效电平条目 list 原样（result.json
  ``scenario_result.result.failure_levels``——与 run_demo._failure_levels 同源
  口径；无→[]）；
- ``report_relpath``：``'report.md'``（run 目录内该文件存在才给，否则 None）
  ——「查看报告」链接仅在报告真实在位时给出；
- ``exit_code``：``0|1``（completed→0，其余（含 done 但场景未完成）→1，与
  run_demo 退出码语义一致；no_result 行→None——退出码不可考不虚构）。

排序：**新建在前**——按 (started_at‖目录 mtime, run_id) 降序；started_at 缺失的
no_result 行以目录 mtime 兜底（同为真实时间信号，不虚构）。
"""
import json
import math
import os
from numbers import Real

__all__ = ["list_run_summaries", "RESULT_FILENAME", "SCENARIO_FILENAME", "UNKNOWN_LABEL"]

#: run 结果文件（时间/后端/状态/场景结果来源；缺失或损坏→no_result 降级行）。
RESULT_FILENAME = "result.json"

#: 场景副本文件（scenario_name/style/backend 补缺来源）。
SCENARIO_FILENAME = "scenario.yaml"

#: 报告文件名（与 build_report.REPORT_FILENAME 对齐；在位才给 report_relpath）。
REPORT_FILENAME = "report.md"

#: 缺数据字段的占位标签（明示「不可考」，不虚构值）。
UNKNOWN_LABEL = "未知"

#: no_result 行的状态标注值（result.json 缺失/损坏——降级标注不剔除）。
NO_RESULT_STATUS = "no_result"


def _is_finite_real(value: object) -> bool:
    """有限实数判定（bool 不算——时间戳口径不接受布尔）。"""
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _display_text(*candidates: object) -> str:
    """按序取首个非空 str 候选（全落空→'未知'占位——多来源补缺的统一出口）。"""
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value
    return UNKNOWN_LABEL


def _scenario_name(scenario: dict) -> str:
    """场景名：场景副本 'name'→'scenario_type'→'未知'（现行副本不含 name，
    scenario_type 即场景类型名——真实记录不虚构）。"""
    if isinstance(scenario.get("name"), str) and scenario["name"].strip():
        return scenario["name"]
    return _display_text(scenario.get("scenario_type"))


def _read_result(run_dir: str):
    """读 result.json → payload dict | None。

    缺失/读取失败/JSON 损坏/非 JSON 对象→None（no_result 降级口径——单行提取
    失败只降级该行，列表不失败）。
    """
    path = os.path.join(run_dir, RESULT_FILENAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_scenario(run_dir: str) -> dict:
    """读场景副本 scenario.yaml → dict（补缺来源；缺失/损坏/非 dict→{}）。"""
    path = os.path.join(run_dir, SCENARIO_FILENAME)
    if not os.path.isfile(path):
        return {}
    try:
        import yaml

        with open(path, encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except Exception:  # noqa: BLE001 - 场景副本损坏→补缺来源失效，不反杀摘要行
        return {}
    return payload if isinstance(payload, dict) else {}


def _failure_levels(payload: dict) -> list:
    """失效电平条目提取（run_demo._failure_levels 同源口径）。

    形状链：payload['scenario_result']['result']['failure_levels']——execute
    回调返回并入 result.json 'scenario_result' 键（B21 中#2）；任一环节形状
    不符→[]（不虚构）。
    """
    inner = payload.get("scenario_result")
    if not isinstance(inner, dict):
        return []
    nested = inner.get("result")
    if not isinstance(nested, dict):
        return []
    levels = nested.get("failure_levels")
    if isinstance(levels, list):
        return [entry for entry in levels if isinstance(entry, dict)]
    return []


def _row_sort_ts(row: dict, report_root: str) -> float:
    """行排序时间戳：started_at（有限实数）> 目录 mtime > 0.0（均不可考的兜底）。"""
    started = row.get("started_at")
    if _is_finite_real(started):
        return float(started)
    try:
        return os.path.getmtime(os.path.join(report_root, row["run_id"]))
    except OSError:
        return 0.0


def list_run_summaries(report_root: str) -> "list[dict]":
    """报告中心元数据行：扫描各运行目录读 result.json/场景副本提取摘要（新建在前；
    result.json 缺失/损坏行降级标注 no_result 不虚构不剔除——详见
    fn_docs/responsibility.md R61 功能块）。

    Args:
        report_root: 运行根目录（各 run 目录的父，与 serve_console
            deps['report_root'] 同源）；非 str/PathLike→ValueError（编程错误
            早暴露）；目录不存在或不可读→[]（空报告中心，不报错拦页）。

    Returns:
        摘要行列表（新建在前），行契约见模块 docstring——每行恒齐
        run_id/started_at/scenario_name/style/backend/status/failure_levels/
        report_relpath/exit_code 9 键；单行提取失败只降级该行
        （status='no_result'），列表不失败。

    Raises:
        ValueError: report_root 非 str/PathLike 路径。
    """
    if isinstance(report_root, os.PathLike):
        report_root = os.fspath(report_root)
    if not isinstance(report_root, str) or not report_root:
        raise ValueError(
            f"report_root 必须为 str/os.PathLike 路径（运行根目录），实际 "
            f"{type(report_root).__name__}: {report_root!r}"
        )
    try:
        entries = sorted(os.listdir(report_root))
    except OSError:
        return []

    rows: "list[dict]" = []
    for run_id in entries:
        run_dir = os.path.join(report_root, run_id)
        if not os.path.isdir(run_dir):
            continue  # 只收运行目录（与 GET /api/runs 同口径）
        payload = _read_result(run_dir)
        scenario = _read_scenario(run_dir)

        if payload is None:
            # 降级标注行：result.json 缺失/损坏——不虚构不剔除，场景副本尽力补缺。
            rows.append(
                {
                    "run_id": run_id,
                    "started_at": None,
                    "scenario_name": _scenario_name(scenario),
                    "style": _display_text(scenario.get("style")),
                    "backend": _display_text(scenario.get("backend")),
                    "status": NO_RESULT_STATUS,
                    "failure_levels": [],
                    "report_relpath": REPORT_FILENAME
                    if os.path.isfile(os.path.join(run_dir, REPORT_FILENAME))
                    else None,
                    "exit_code": None,
                }
            )
            continue

        failure_levels = _failure_levels(payload)
        # 状态双确认（run_demo 口径）：run 状态机 done 且场景执行 completed。
        execute = payload.get("scenario_result")
        scenario_status = execute.get("status") if isinstance(execute, dict) else None
        completed = payload.get("status") == "done" and scenario_status == "completed"
        started_at = payload.get("started_at")
        style = _display_text(scenario.get("style"))
        if style == UNKNOWN_LABEL and failure_levels:
            # 场景副本缺 style 时回落失效电平条目的样式记录（同为真实数据）。
            style = _display_text(failure_levels[0].get("style"))
        rows.append(
            {
                "run_id": run_id,
                "started_at": float(started_at) if _is_finite_real(started_at) else None,
                "scenario_name": _scenario_name(scenario),
                "style": style,
                "backend": _display_text(
                    payload.get("backend"), scenario.get("backend")
                ),
                "status": "completed" if completed else "failed",
                "failure_levels": failure_levels,
                "report_relpath": REPORT_FILENAME
                if os.path.isfile(os.path.join(run_dir, REPORT_FILENAME))
                else None,
                "exit_code": 0 if completed else 1,
            }
        )

    # 新建在前：时间戳降序（同秒以 run_id 降序决胜——目录名时间戳格式下仍保确定序）。
    rows.sort(
        key=lambda row: (_row_sort_ts(row, report_root), row["run_id"]), reverse=True
    )
    return rows
