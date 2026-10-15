"""报告总装：图谱/失效表/识别/EMC/口径脚注/频点图谱位——重写规约与签名意图详见 fn_docs/responsibility.md（R45 顶层）。

编排链（数字纪律：报告关键数字全部读回自本 run 数据文件/本 run 结果对象，不虚构）：

- ① 数据读回：run_dir 下 kpi.csv/events.jsonl/monitor.csv——存在才读，缺失段
  如实标「缺项」（缺项清单汇入缺项汇总段）；
- ② 三元曲线：run_dir/plots/ 三 PNG 齐备→复用不重绘；否则 plot_triple_curves
  以读回数据绘制（三路全空/绘制失败→该段标缺项，不抛）；
- ③ 失效电平对比：result['failure_levels'] 非空才调 compare_failure_boundaries
  （空→跳段标「无失效数据」）；对比表+结论整段以 '> ' 引用块嵌入（中位数等
  聚合值非数据原文——R46 按口径行计 contextual，防聚合值自噬，B18 中#7）；
- ④ 样式识别：run_dir/models/style_classifier.json 存在才载入 predict_style
  （不存在→段标「未识别（无模型）」，R32 口径不阻塞；IQ 取 result['iq_source']，
  缺则 recordings/ 首个 .sigmf-meta，再缺→no_iq 如实标注）；
- ⑤ EMC 段：result 含 'emc' 键才嵌入，经 render_emc_flow_section 按段内
  'flow' 标签三流程分节（conduction 传导摸底/radiation 辐射摸底/sweep 步进
  扫频；标签缺省按形状回推：readings 列表→传导、spectrum dict→辐射、其余→
  扫频），全段以 '> ' 引用行呈现（模拟读数非实测——R46 溯源时按口径行白名单
  计 contextual）；'emc' 非 dict → 缺项段（标题不含具体流程——形状不可知）且
  不据此附 simulated_parts/emc 级声明（B18 低#15）；动态文本单元格消毒
  （换行折叠 ' / '、'|' 转义——B18 中#8/#9；段渲染实现已迁
  render_emc_flow_section 模块——R89 快速通道留痕）；
- ⑥ 口径脚注：render_disclaimer_sections——backend/clock_ref/run_id 取自
  result，per_basis 恒 True（PER 口径平台级）；涉 EMC 段时 simulated_parts
  附「EMC 传导摸底段/EMC 辐射摸底段/EMC 步进扫频段」之一（payload 未给时的
  防御回退按 emc.flow 出段名，标签缺省按形状回推——同分发器口径，脚注段名
  与正文标题一致，I-2）；
- ⑦ 频点图谱位：result['freq_plots'] 直传 assemble_frequency_plots；未给→
  缺省占位口径「一期频点按 2.4G/5.8G 实有频点如实标注」+ monitor.csv 实测
  频点如实计位；
- ⑧ 落盘 run_dir/report.md（标题+运行概要表+各节+缺项汇总+脚注），返回其
  路径；缺项清单（'missing'——result 与文件双源核对）如实列出。
"""
from __future__ import annotations

import csv
import json
import os

from .assemble_frequency_plots import assemble_frequency_plots
from .render_disclaimer_sections import render_disclaimer_sections
from src.compare_failure_boundaries.compare_failure_boundaries import (
    compare_failure_boundaries,
)
from src.plot_triple_curves.plot_triple_curves import plot_triple_curves
from src.predict_style.predict_style import predict_style
from src.render_emc_flow_section.render_emc_flow_section import (
    render_emc_flow_section,
)

__all__ = ["build_report"]

#: 报告文件名（对齐 create_run_workspace 八件套）。
REPORT_FILENAME = "report.md"

#: 三路数据文件（存在才读回；缺失计缺项）。
DATA_FILES = ("kpi.csv", "events.jsonl", "monitor.csv")

#: 三元曲线三 PNG（plots/ 下齐备才复用，与 plot_triple_curves 落盘名一致）。
_PNG_NAMES = (
    "curve_a_per_vs_level.png",
    "curve_b_throughput_vs_per.png",
    "curve_c_event_timeline.png",
)

#: 三图 markdown 图片标题（与 _PNG_NAMES 对位）。
_PLOT_TITLES = ("图A：误包率–干扰电平", "图B：相对吞吐–误包率", "图C：事件时间线")

#: 样式识别模型 per-run 落点（存在才载入）。
_MODEL_RELPATH = os.path.join("models", "style_classifier.json")

#: 各段固定文案（测试锚点；如实标注口径）。
_NO_FAILURE_NOTE = (
    "无失效数据：result['failure_levels'] 为空——跳过失效电平对比段（不虚构对比表）"
)
_FREQ_DEFAULT_NOTE = (
    "频点口径：一期频点按 2.4G/5.8G 实有频点如实标注"
    "（未提供 freq_plots 登记，按 monitor.csv 实测频点如实计位）"
)
_FREQ_SATISFIED_NOTE = "满足 ≥5 频点图谱位要求"
_PLOT_REUSE_NOTE = "绘制口径：复用 plots/ 下已有三张 PNG（本次未重绘）"
_NO_MISSING_NOTE = "无缺项：本 run 数据文件与报告产物双源核对齐备"


def _as_path_str(value: object, name: str) -> str:
    """路径规整：os.PathLike → str；非 str/PathLike → ValueError（消息附类型）。"""
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str):
        raise ValueError(
            f"{name} 必须为 str/os.PathLike 路径，实际 {type(value).__name__}: {value!r}"
        )
    return value


def _str_or_none(value: object) -> str | None:
    """上下文字段规整：非空 str 透传，其余 None（render_disclaimer 补「未记录」）。"""
    if isinstance(value, str) and value.strip():
        return value
    return None


def _opt_float(text: object) -> float | None:
    """CSV 单元格 → float；空/非法 → None（不虚构数值）。"""
    if text is None:
        return None
    try:
        return float(str(text).strip())
    except ValueError:
        return None


def _read_kpi_rows(path: str) -> list[dict] | None:
    """kpi.csv 读回（表头按 record_run_streams 口径）；文件不存在 → None。"""
    if not os.path.isfile(path):
        return None
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            rows.append(
                {
                    "timestamp_ms": _opt_float(record.get("timestamp_ms")),
                    "judge_per": _opt_float(record.get("judge_per")),
                }
            )
    return rows


def _read_events(path: str) -> list[dict] | None:
    """events.jsonl 逐行 JSON 读回；文件不存在 → None；坏行跳过（不虚构）。"""
    if not os.path.isfile(path):
        return None
    events: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                events.append(item)
    return events


def _read_monitor(path: str) -> tuple[int | None, list[str] | None]:
    """monitor.csv 读回 → (行数, 去重频点原始字符串序)；文件不存在 → (None, None)。

    频点保留 CSV 原始字符串（回查时与文件原文逐字一致——数字纪律）。
    """
    if not os.path.isfile(path):
        return None, None
    n_rows = 0
    freqs: list[str] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            n_rows += 1
            freq_raw = (record.get("freq_mhz") or "").strip()
            if freq_raw and freq_raw not in freqs:
                freqs.append(freq_raw)
    return n_rows, freqs


def _quote_line(line: str) -> str:
    """引用行规整：已是 '>' 前缀原样；否则补 '> '（EMC/声明区统一引用口径）。"""
    return line if line.startswith(">") else f"> {line}"


def _sanitize_cell(text: str) -> str:
    """表格/单行单元格消毒：'\\n' → ' / '、'|' → '\\|'（注入字段不破坏表格与
    行结构——B18 中#8/#9）。"""
    return text.replace("\n", " / ").replace("|", "\\|")


def _quoted_text_lines(text: str) -> list[str]:
    """多行文本 → 逐行 '|'-转义 + '> ' 引用行组（换行不逃出引用块——B18 中#8）。"""
    return [_quote_line(_sanitize_cell(part)) for part in text.splitlines()]


def _summary_md(
    run_dir: str,
    run_id_disp: str,
    backend_disp: str,
    clock_disp: str,
    kpi_rows: list[dict] | None,
    events: list[dict] | None,
    monitor_n: int | None,
) -> str:
    """运行概要表：目录/标识/后端/时钟 + 三数据文件在位性与行数（缺→缺项）。
    动态 str 单元格消毒（换行折叠 ' / '、'|' 转义——注入不破表格，B18 中#8/#9）。"""
    kpi_cell = f"存在，{len(kpi_rows)} 行" if kpi_rows is not None else "缺项（文件不存在）"
    events_cell = (
        f"存在，{len(events)} 条" if events is not None else "缺项（文件不存在）"
    )
    monitor_cell = (
        f"存在，{monitor_n} 行" if monitor_n is not None else "缺项（文件不存在）"
    )
    return "\n".join(
        [
            "## 运行概要",
            "",
            "| 项 | 值 |",
            "| --- | --- |",
            f"| 运行目录 | {_sanitize_cell(run_dir)} |",
            f"| 运行标识 | {_sanitize_cell(run_id_disp)} |",
            f"| 后端 | {_sanitize_cell(backend_disp)} |",
            f"| 时钟基准 | {_sanitize_cell(clock_disp)} |",
            f"| kpi.csv | {kpi_cell} |",
            f"| events.jsonl | {events_cell} |",
            f"| monitor.csv | {monitor_cell} |",
        ]
    )


def _curves_md(
    run_dir: str,
    kpi_rows: list[dict] | None,
    events: list[dict] | None,
    failure_levels: list,
    run_label: str,
    missing: list[str],
) -> str:
    """三元曲线段：三 PNG 齐备复用；否则 plot_triple_curves 绘制；失败→缺项。"""
    lines = ["## 三元曲线", ""]
    plots_dir = os.path.join(run_dir, "plots")
    existing = [
        name for name in _PNG_NAMES if os.path.isfile(os.path.join(plots_dir, name))
    ]
    if len(existing) == len(_PNG_NAMES):
        for title, name in zip(_PLOT_TITLES, _PNG_NAMES):
            lines.append(f"![{title}](plots/{name})")
        lines.append(_PLOT_REUSE_NOTE)
        return "\n".join(lines)

    data = {
        "kpi": kpi_rows or [],
        "events": events or [],
        "failure_levels": failure_levels,
    }
    try:
        plot_result = plot_triple_curves(data, plots_dir, run_label=run_label)
    except (RuntimeError, ValueError, OSError) as exc:  # CurvesError ⊂ RuntimeError
        missing.append(f"三元曲线（绘图失败：{type(exc).__name__}: {exc}）")
        lines.append(
            f"缺项：本次无可绘数据或绘制失败（{type(exc).__name__}: {exc}）——曲线段如实标注缺项。"
        )
        return "\n".join(lines)

    for title, path in zip(_PLOT_TITLES, plot_result["png_paths"]):
        lines.append(f"![{title}](plots/{os.path.basename(path)})")
    note = (
        f"绘制口径：本次绘制（font={plot_result['font']}，"
        f"partial={plot_result['partial']}）"
    )
    if plot_result["missing"]:
        note += f"；缺帧：{'、'.join(plot_result['missing'])}"
    if plot_result["partial_reason"]:
        note += f"；partial 成因：{plot_result['partial_reason']}"
    lines.append(note)
    return "\n".join(lines)


def _failure_md(failure_levels: list, missing: list[str]) -> str:
    """失效电平对比段：compare_failure_boundaries 表+结论，整段 '> ' 引用块嵌入
    （中位数等聚合值非数据文件原文——R46 溯源按口径行白名单计 contextual，
    防「报告自产聚合值反被自检判虚构」的自噬，B18 中#7）；空→无失效数据跳段。"""
    lines = ["## 失效电平对比", ""]
    if not failure_levels:
        lines.append(_NO_FAILURE_NOTE)
        return "\n".join(lines)
    try:
        boundary = compare_failure_boundaries(failure_levels)
    except ValueError as exc:
        missing.append(f"失效电平对比（输入形状错：{exc}）")
        lines.append(f"缺项：失效电平对比输入形状错（{exc}）——不虚构对比表。")
        return "\n".join(lines)
    if boundary["comparison"]:
        lines.append(
            "> | 样式 | 失效电平中位数 (dB) | 有效条目数（按条目计） | 最小 (dB) | 最大 (dB) |"
        )
        lines.append("> | --- | --- | --- | --- | --- |")
        for row in boundary["comparison"]:
            lines.append(
                f"> | {_sanitize_cell(str(row['style']))} | {row['median_level_db']} dB"
                f" | {row['n_runs']}"
                f" | {row['min_db']} dB | {row['max_db']} dB |"
            )
        lines.append("")
    lines.extend(f"> 结论：{part}" for part in str(boundary["conclusion"]).splitlines())
    return "\n".join(lines)


def _style_md(result: dict, run_dir: str, missing: list[str]) -> str:
    """样式识别段：模型存在才载入 predict_style；结果行如实（未识别不虚构）。"""
    model_path = os.path.join(run_dir, _MODEL_RELPATH)
    has_model = os.path.isfile(model_path)
    if not has_model:
        missing.append(f"{_MODEL_RELPATH}（样式识别模型不存在——识别段未识别）")

    iq_source = result.get("iq_source")
    if iq_source is None:
        recordings = os.path.join(run_dir, "recordings")
        if os.path.isdir(recordings):
            metas = sorted(
                name for name in os.listdir(recordings) if name.endswith(".sigmf-meta")
            )
            if metas:
                iq_source = os.path.join(recordings, metas[0])
    try:
        predicted = predict_style(
            iq_source, model=model_path if has_model else None
        )
    except ValueError as exc:  # nfft 非法等参数域错——段标缺项不虚构
        missing.append(f"样式识别（推理失败：{exc}）")
        return "\n".join(
            ["## 样式识别", "", f"缺项：识别推理失败（{exc}）。"]
        )

    rows = predicted if isinstance(predicted, list) else [predicted]
    lines = ["## 样式识别", ""]
    for row in rows:
        if isinstance(row, dict) and row.get("recognized"):
            confidence = row.get("confidence")
            conf_text = (
                f"{float(confidence):.2f}"
                if isinstance(confidence, (int, float))
                and not isinstance(confidence, bool)
                else "未记录"
            )
            lines.append(
                f"识别样式：{row.get('label')}"
                f"（置信度 {conf_text}，模型版本 {row.get('model_version')}）"
            )
        elif isinstance(row, dict):
            lines.append(str(row.get("note")))
        else:
            lines.append(f"未识别：{row!r}")
    return "\n".join(lines)


def _freq_md(
    result: dict,
    monitor_n: int | None,
    monitor_freqs: list[str] | None,
    missing: list[str],
) -> str:
    """频点图谱位段：freq_plots 直传或缺省占位口径；monitor 实测频点如实计位。"""
    lines = ["## 频点图谱位", ""]
    if monitor_n is not None:
        if monitor_freqs:
            lines.append(
                f"实有频点（monitor.csv 读回，{len(monitor_freqs)} 个）："
                + "、".join(f"{freq} MHz" for freq in monitor_freqs)
            )
        else:
            lines.append("实有频点：monitor.csv 存在但无频点行（0 个）。")
    else:
        lines.append("缺项：monitor.csv 不存在——无频点统计。")

    given = result.get("freq_plots")
    if isinstance(given, dict):
        source_note = "图谱位口径：result['freq_plots'] 直传。"
        plots_input = given
    else:
        source_note = _FREQ_DEFAULT_NOTE
        plots_input = {"freq_mhz": list(monitor_freqs or []), "images": {}}
    try:
        freq_result = assemble_frequency_plots(plots_input)
    except ValueError as exc:
        missing.append(f"频点图谱位（组装失败：{exc}）")
        lines.append(f"缺项：频点图谱位组装失败（{exc}）。")
        return "\n".join(lines)

    lines.append(source_note)
    lines.append(f"图谱位：实有 {freq_result['slots']}/需 {freq_result['required']}")
    if freq_result["satisfied"]:
        lines.append(_FREQ_SATISFIED_NOTE)
    else:
        lines.append(freq_result["deficit_note"])
        missing.append(f"频点图谱位（{freq_result['deficit_note']}）")
    if freq_result["images"]:
        lines.append(f"可用图谱键：{'、'.join(freq_result['images'])}")
    return "\n".join(lines)


def _missing_md(missing: list[str]) -> str:
    """缺项汇总段：result 与文件双源核对的缺项清单（空→无缺项注记）。"""
    lines = ["## 缺项汇总（result 与文件双源核对）", ""]
    if not missing:
        lines.append(f"- {_NO_MISSING_NOTE}")
    else:
        lines.extend(f"- {item}" for item in missing)
    return "\n".join(lines)


def _emc_simulated_part_label(emc: dict) -> str:
    """EMC 模拟段脚注标签回推（I-2）：按段内 flow 标签出三流程段名。

    标签缺省/未知时按形状回推（readings 列表→conduction、spectrum dict→
    radiation、其余→sweep）——与 render_emc_flow_section 分发口径一致，
    保证脚注段名与正文标题不矛盾（旧回退恒「EMC 传导摸底段」，radiation/
    sweep 场景下脚注与标题自相矛盾）。
    """
    flow = emc.get("flow")
    if flow not in ("conduction", "radiation", "sweep"):
        if isinstance(emc.get("readings"), list):
            flow = "conduction"
        elif isinstance(emc.get("spectrum"), dict):
            flow = "radiation"
        else:
            flow = "sweep"
    if flow == "conduction":
        return "EMC 传导摸底段"
    if flow == "radiation":
        return "EMC 辐射摸底段"
    return "EMC 步进扫频段"


def build_report(run_dir: str, result: dict) -> str:
    """报告总装（R45）：数据读回→三元曲线→失效对比→识别→EMC→频点图谱位→脚注→report.md。

    Args:
        run_dir: 运行目录（kpi.csv/events.jsonl/monitor.csv/plots/ 读回与
            report.md 落盘点；不存在则自动创建——全部段如实标缺项）。
        result: 本 run 结果对象——'run_id'/'backend'/'clock_ref'（脚注与概要，
            缺→「未记录」）、'failure_levels'（失效对比，空→跳段）、'iq_source'
            （识别 IQ，缺则 recordings/ 首个 .sigmf-meta）、'emc'（含键才嵌入
            EMC 段）、'freq_plots'（直传频点图谱位登记）、'simulated_parts'
            （脚注模拟段清单覆写）。

    Returns:
        report.md 路径（os.path.join(run_dir, 'report.md')）。

    Raises:
        ValueError: run_dir 非 str/os.PathLike，或 result 非 dict。各产物缺失/
        绘制失败不抛——对应段如实标「缺项」并汇入缺项汇总段（不虚构）。
    """
    if not isinstance(result, dict):
        raise ValueError(
            f"result 必须为 dict，实际 {type(result).__name__}: {result!r}"
        )
    run_dir = _as_path_str(run_dir, "run_dir")

    # ① 数据读回（存在才用；缺→缺项）
    kpi_rows = _read_kpi_rows(os.path.join(run_dir, "kpi.csv"))
    events = _read_events(os.path.join(run_dir, "events.jsonl"))
    monitor_n, monitor_freqs = _read_monitor(os.path.join(run_dir, "monitor.csv"))

    failure_levels = result.get("failure_levels")
    if not isinstance(failure_levels, list):
        failure_levels = []

    missing: list[str] = []
    for name in DATA_FILES:
        if not os.path.isfile(os.path.join(run_dir, name)):
            missing.append(f"{name}（数据文件不存在——相关段按缺项标注）")

    run_id = _str_or_none(result.get("run_id")) or ""
    backend = _str_or_none(result.get("backend"))
    clock_ref = _str_or_none(result.get("clock_ref"))

    # ②~⑦ 各节组装（各节函数按需向 missing 追加缺项）
    sections: list[str] = []
    safe_run_id = _sanitize_cell(run_id)
    sections.append(
        "# Run Report" + (f"（{safe_run_id}）" if run_id else "")
    )
    sections.append(
        _summary_md(
            run_dir,
            run_id or "未记录",
            backend or "未记录",
            clock_ref or "未记录",
            kpi_rows,
            events,
            monitor_n,
        )
    )
    sections.append(
        _curves_md(run_dir, kpi_rows, events, failure_levels, run_id, missing)
    )
    sections.append(_failure_md(failure_levels, missing))
    sections.append(_style_md(result, run_dir, missing))
    emc_section = render_emc_flow_section(result, missing)
    # 仅 dict 形状的 emc 才算真有模拟读数段（非 dict → 缺项段，不算模拟段——
    # 不据此附 simulated_parts/emc 级声明，B18 低#15）。
    emc_is_simulated = isinstance(result.get("emc"), dict)
    if emc_section is not None:
        sections.append(emc_section)
    sections.append(_freq_md(result, monitor_n, monitor_freqs, missing))
    sections.append(_missing_md(missing))

    # ⑥ 口径脚注（backend/clock_ref/run_id 缺→「未记录」；per_basis 恒 True）
    simulated_parts = result.get("simulated_parts")
    if not isinstance(simulated_parts, list) or not all(
        isinstance(part, str) for part in simulated_parts
    ):
        # 防御回退随流程（I-2）：无 simulated_parts 键时按 emc 段 flow 出段名
        # （传导/辐射/扫频——脚注与正文标题一致，旧恒「EMC 传导摸底段」回退
        # 在 radiation/sweep 场景与标题自相矛盾）。
        simulated_parts = (
            [_emc_simulated_part_label(result["emc"])] if emc_is_simulated else []
        )
    footnote = render_disclaimer_sections(
        {
            "backend": backend,
            "clock_ref": clock_ref,
            "run_id": run_id or None,
            "per_basis": True,
            "simulated_parts": simulated_parts,
        }
    )
    sections.append("## 口径声明（脚注）\n\n" + footnote)

    # ⑧ 落盘并返回路径
    report_md = "\n\n".join(sections) + "\n"
    os.makedirs(run_dir, exist_ok=True)
    report_path = os.path.join(run_dir, REPORT_FILENAME)
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(report_md)
    return report_path
