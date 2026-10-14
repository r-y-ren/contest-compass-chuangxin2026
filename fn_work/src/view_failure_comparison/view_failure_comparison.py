"""跨轮失效对比视图：运行集→compare_failure_boundaries 对比表+薄弱环节结论——R62 L0。

返回 dict 契约（页面/JSON 双消费；编排复用 R26，无对比口径重造）：

- ``run_ids``：请求的运行 id 列表（原样回显，顺序保请求序）；
- ``entries``：汇聚的失效电平条目（每条=run 内 result.json 的
  ``scenario_result.result.failure_levels`` 原样条目 + 补 ``run_id`` 来源键；
  条目缺 ``freq_mhz`` 且该 run 场景副本携带正有限 ``freq_hz`` 时补
  ``freq_mhz=freq_hz/1e6``——R26 频点维的真实数据来源，不虚构）；
- ``comparison``/``weakest_style``/``weakest_freq_mhz``/``tie``/``n_unknown``/
  ``n_freq_invalid``/``conclusion``：compare_failure_boundaries 返回原样
  （对比表按失效电平中位数升序；薄弱定位/降级口径全归 R26）；
- ``degraded``：True=有效样式恰 1（样本不足降级单样式——R26 口径：comparison
  置空、结论注明「单样式数据」；此处仅结构化透出该降级态）；
- ``runs_without_failure``：在位运行无失效数据的标注行
  ``[{'run_id', 'note'}]``——result.json 可读但无失效条目→note='未失效（无失效
  电平条目）'；result.json 缺失/损坏→note='无结果（result.json 缺失或损坏）'
  （不虚构不剔除）；
- ``missing_runs``：report_root 下不存在的 run_id 列表；
- 全缺（entries 空）时 conclusion 在 R26「无数据」结论后追加提示——
  「请选择其他运行」（R62 签名意图：全缺→提示选其他运行）。
"""
import math
import os
from numbers import Real

from src.compare_failure_boundaries.compare_failure_boundaries import (
    compare_failure_boundaries,
)

__all__ = ["view_failure_comparison", "NO_FAILURE_NOTE", "NO_RESULT_NOTE"]

#: 在位运行 result.json 可读但无失效电平条目的标注（R62：未失效行）。
NO_FAILURE_NOTE = "未失效（无失效电平条目）"

#: 在位运行 result.json 缺失/损坏的标注（降级行——不虚构失效数据）。
NO_RESULT_NOTE = "无结果（result.json 缺失或损坏）"

#: 全缺时追加的选择提示（R62 签名意图）。
_EMPTY_HINT = "——所选运行均无失效数据，请选择其他运行"

#: result.json / 场景副本文件名（与 list_run_summaries 同源）。
_RESULT_FILENAME = "result.json"
_SCENARIO_FILENAME = "scenario.yaml"


def _is_finite_real(value: object) -> bool:
    """有限实数判定（bool 不算——freq_hz 换算口径不接受布尔）。"""
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _has_traversal(run_id: object) -> bool:
    """run_id 穿越形态判定（与 serve_run_artifacts 同口径——URL 进来的名字早拒）。"""
    if not isinstance(run_id, str) or not run_id:
        return True
    return (
        os.path.isabs(run_id)
        or "/" in run_id
        or "\\" in run_id
        or ".." in run_id
        or run_id in {".", ".."}
    )


def _read_result(run_dir: str):
    """读 result.json → payload dict | None（缺失/损坏/非对象→None）。"""
    import json

    path = os.path.join(run_dir, _RESULT_FILENAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _freq_mhz_from_scenario(run_dir: str):
    """场景副本 freq_hz（Hz，正有限实数）→ MHz float；不可得→None。"""
    path = os.path.join(run_dir, _SCENARIO_FILENAME)
    if not os.path.isfile(path):
        return None
    try:
        import yaml

        with open(path, encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except Exception:  # noqa: BLE001 - 副本损坏→频点补充失效，不影响电平维
        return None
    if not isinstance(payload, dict):
        return None
    freq_hz = payload.get("freq_hz")
    if not _is_finite_real(freq_hz) or float(freq_hz) <= 0.0:
        return None
    return float(freq_hz) / 1e6


def _run_failure_entries(run_dir: str):
    """单 run 的失效电平条目（list[dict]——形状链同 list_run_summaries 口径）。"""
    payload = _read_result(run_dir)
    if payload is None:
        return None  # 无结果（与空条目区分——标注口径不同）
    execute = payload.get("scenario_result")
    if not isinstance(execute, dict):
        return []
    nested = execute.get("result")
    if not isinstance(nested, dict):
        return []
    levels = nested.get("failure_levels")
    if not isinstance(levels, list):
        return []
    return [entry for entry in levels if isinstance(entry, dict)]


def view_failure_comparison(run_ids: list, report_root: str) -> dict:
    """跨轮失效对比视图：运行集→compare_failure_boundaries 对比表与薄弱环节结论
    （样本不足降级单样式并标注——R26 口径；详见 fn_docs/responsibility.md R62
    功能块）。

    Args:
        run_ids: 运行 id（report_root 下运行目录名）列表；非 list / 元素非 str /
            空白 / 穿越形态（含 ..、/、\\\\、绝对路径）→ValueError（端点转 400）。
        report_root: 运行根目录（与 list_run_summaries/serve_console
            deps['report_root'] 同源）；非 str/PathLike→ValueError。

    Returns:
        对比视图 dict（契约见模块 docstring）——运行无失效数据→
        runs_without_failure 标注行；全缺→conclusion 附「请选择其他运行」提示。

    Raises:
        ValueError: run_ids 形状非法（非 list/元素非 str/空白/穿越形态）或
            report_root 非 str/PathLike 路径。
    """
    if not isinstance(run_ids, list):
        raise ValueError(
            f"run_ids 必须为 list（运行目录名列表），实际 "
            f"{type(run_ids).__name__}: {run_ids!r}"
        )
    bad = [rid for rid in run_ids if _has_traversal(rid)]
    if bad:
        raise ValueError(
            f"run_ids 含非法运行名（须为 report_root 下纯目录名，禁含 /、\\\\、"
            f".. 或绝对路径）: {bad!r}"
        )
    if isinstance(report_root, os.PathLike):
        report_root = os.fspath(report_root)
    if not isinstance(report_root, str) or not report_root:
        raise ValueError(
            f"report_root 必须为 str/os.PathLike 路径（运行根目录），实际 "
            f"{type(report_root).__name__}: {report_root!r}"
        )

    entries: list = []
    runs_without_failure: "list[dict]" = []
    missing_runs: "list[str]" = []
    for run_id in run_ids:
        run_dir = os.path.join(report_root, run_id)
        if not os.path.isdir(run_dir):
            missing_runs.append(run_id)
            continue
        levels = _run_failure_entries(run_dir)
        if levels is None:
            runs_without_failure.append({"run_id": run_id, "note": NO_RESULT_NOTE})
            continue
        if not levels:
            runs_without_failure.append({"run_id": run_id, "note": NO_FAILURE_NOTE})
            continue
        freq_mhz = _freq_mhz_from_scenario(run_dir)
        for entry in levels:
            row = dict(entry)
            row["run_id"] = run_id
            # 频点维真实数据来源：条目自带 freq_mhz 优先，缺则场景副本 freq_hz 换算。
            if "freq_mhz" not in row and freq_mhz is not None:
                row["freq_mhz"] = freq_mhz
            entries.append(row)

    outcome = compare_failure_boundaries(entries)
    conclusion = outcome["conclusion"]
    if not entries and (runs_without_failure or missing_runs):
        conclusion = f"{conclusion}{_EMPTY_HINT}"

    # 降级单样式标注（R26 口径结构化）：有效样式（数值电平条目）恰 1——comparison
    # 已由 R26 置空、结论已注明「单样式数据」，此处透出布尔供页面/API 消费。
    usable_styles = {
        entry.get("style")
        for entry in entries
        if isinstance(entry.get("failure_level_db"), (int, float))
        and not isinstance(entry.get("failure_level_db"), bool)
    }
    degraded = len(usable_styles) == 1

    return {
        "run_ids": list(run_ids),
        "entries": entries,
        "comparison": outcome["comparison"],
        "weakest_style": outcome["weakest_style"],
        "weakest_freq_mhz": outcome["weakest_freq_mhz"],
        "tie": outcome["tie"],
        "n_unknown": outcome["n_unknown"],
        "n_freq_invalid": outcome["n_freq_invalid"],
        "conclusion": conclusion,
        "degraded": degraded,
        "runs_without_failure": runs_without_failure,
        "missing_runs": missing_runs,
    }
