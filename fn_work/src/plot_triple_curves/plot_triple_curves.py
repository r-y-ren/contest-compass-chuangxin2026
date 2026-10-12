"""三元曲线三图绘制（中文字体零缺字，缺数据降级出图）——B13 顶层，R25；调用方 build_report。

职责口径（重写规约）：
- 输入 ``data``（build_curve_frames 的三路入参形状 ``{'kpi','events',
  'failure_levels'}``）、``out_dir``（plots/ 落盘目录，不存在自动建）、
  ``run_label``（图标题后缀，拼入三图标题形如「（RUN-xx）」）。
- 链路：build_curve_frames 出帧 → matplotlib（延迟 import，Agg 后端）绘三图：
  图A PER–干扰电平（折线+失效档红点，y 轴限 0–1；失效窗无判据样本时红点按
  PER=1 失效上界口径落点）；图B 相对吞吐–PER（y 轴标「相对吞吐（1−PER 等效）」
  代理口径注记）；图C 事件时间线（事件/KPI/失效三类散点+中文图例）。
- 中文字体：候选 ``['Noto Sans CJK SC','WenQuanYi Zen Hei','SimHei']`` 按
  font_manager 注册表精确探测；命中→rcParams 指定（保留 DejaVu 兜底字形）+
  unicode_minus 关闭→``font='cjk'``；全缺→rcParams 不设，各图右下角 fallback
  标注（中文渲染缺字警告不炸）→``font='fallback'``。
- 落盘：三 PNG（150 dpi：curve_a_per_vs_level.png / curve_b_throughput_vs_per.png
  / curve_c_event_timeline.png）+ ``curves_data.json``（三帧+绘制参数，报告溯源）。
- 降级：部分缺数据→已得图照出（空帧出标题+「partial：无数据」轴注），
  ``partial=True`` 且 ``missing`` 列缺项帧名；三路全空→:class:`CurvesError`。
- 返回：``{'png_paths': [三路径], 'data_path': str, 'partial': bool,
  'font': 'cjk'|'fallback', 'missing': [帧名]}``。
- 错误：matplotlib 缺（消息含 ``pip install matplotlib`` 提示）/三路全空/
  ``out_dir`` 不可写→:class:`CurvesError`；``data`` 形状错→
  :class:`ValueError` 透传 build_curve_frames（本函数不拦截）。
"""
from __future__ import annotations

import json
import os

from .build_curve_frames import build_curve_frames


class CurvesError(RuntimeError):
    """三元曲线绘制不可恢复错误（matplotlib 缺/三路数据全空/落盘目录不可写）。"""


#: 中文字体候选（按优先序；font_manager 注册表精确名匹配）。
_CJK_FONT_CANDIDATES = ("Noto Sans CJK SC", "WenQuanYi Zen Hei", "SimHei")

#: 三图文件名（png_paths 顺序：A/B/C）。
_PNG_NAMES = (
    "curve_a_per_vs_level.png",
    "curve_b_throughput_vs_per.png",
    "curve_c_event_timeline.png",
)

#: 落盘分辨率（dpi）。
_DPI = 150

#: 帧C三类散点样式：类别码→（中文图例名, 颜色）。
_KIND_STYLES = {
    0: ("事件", "#1f77b4"),
    1: ("KPI", "#2ca02c"),
    2: ("失效", "#d62728"),
}


def _import_pyplot():
    """延迟 import matplotlib（Agg 后端）；缺库→CurvesError 附 pip 提示。"""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager as fm
    except Exception as exc:  # ImportError 及后端初始化异常一并归口 CurvesError
        raise CurvesError(
            f"matplotlib 不可用（{exc}）；绘图依赖缺失，安装：pip install matplotlib"
        ) from exc
    return plt, fm


def _find_cjk_font(fm) -> str | None:
    """候选中文字体精确探测（font_manager 注册表）；全缺→None。"""
    installed = {entry.name for entry in fm.fontManager.ttflist}
    for name in _CJK_FONT_CANDIDATES:
        if name in installed:
            return name
    return None


def _apply_font(plt, fm) -> str:
    """命中候选→rcParams 注册（'cjk'）；全缺→不动 rcParams（'fallback'）。"""
    font = _find_cjk_font(fm)
    if font is None:
        return "fallback"
    sans = plt.rcParams["font.sans-serif"]
    if not sans or sans[0] != font:  # 重复调用不致候选反复前插
        plt.rcParams["font.sans-serif"] = [font, *sans]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False
    return "cjk"


def _fallback_note(fig, font_mode: str) -> None:
    """字体 fallback 时图右下角标注（缺字可见但渲染不炸）。"""
    if font_mode == "fallback":
        fig.text(
            0.99,
            0.01,
            "字体 fallback：未找到中文字体，中文标注可能缺字",
            ha="right",
            va="bottom",
            fontsize=8,
            color="0.45",
        )


def _annotate_empty(ax) -> None:
    """空帧轴注：partial 降级在图上可见。"""
    ax.text(
        0.5,
        0.5,
        "partial：无数据",
        ha="center",
        va="center",
        transform=ax.transAxes,
        color="0.4",
    )


def _failure_points(frame_a: dict) -> list[tuple[float, float]]:
    """失效档红点坐标：failure_x 对位窗口；窗 PER None→按失效上界 1.0 口径。"""
    x, y = frame_a["x"], frame_a["y"]
    points: list[tuple[float, float]] = []
    for failure_x in frame_a["failure_x"]:
        if failure_x not in x:
            continue
        window_y = y[x.index(failure_x)]
        points.append((failure_x, 1.0 if window_y is None else window_y))
    return points


def _draw_frame_a(plt, frame: dict, suffix: str, font_mode: str):
    """图A：PER–干扰电平 折线+失效档红点（y 轴 0–1；None 窗为折线断点）。"""
    fig, ax = plt.subplots(figsize=(7.0, 4.5))
    ax.set_xlabel("干扰电平 (dBm)")
    ax.set_ylabel("误包率 PER")
    ax.set_title(f"误包率–干扰电平{suffix}")
    if frame["x"]:
        ax.plot(
            frame["x"], frame["y"], marker="o", color="#1f77b4", label="各档窗口 PER 均值"
        )
        failures = _failure_points(frame)
        if failures:
            failure_xs, failure_ys = zip(*failures)
            ax.scatter(failure_xs, failure_ys, color="red", s=70, zorder=3, label="失效档")
        ax.set_ylim(0.0, 1.0)
        ax.grid(True, alpha=0.3)
        ax.legend()
    else:
        _annotate_empty(ax)
    _fallback_note(fig, font_mode)
    return fig


def _draw_frame_b(plt, frame: dict, suffix: str, font_mode: str):
    """图B：相对吞吐–PER（y 轴 1−PER 等效代理口径注记）。"""
    fig, ax = plt.subplots(figsize=(7.0, 4.5))
    ax.set_xlabel("误包率 PER")
    ax.set_ylabel("相对吞吐（1−PER 等效）")
    ax.set_title(f"相对吞吐–误包率{suffix}")
    if frame["x"]:
        ax.plot(frame["x"], frame["y"], marker="s", color="#2ca02c")
        ax.grid(True, alpha=0.3)
    else:
        _annotate_empty(ax)
    _fallback_note(fig, font_mode)
    return fig


def _draw_frame_c(plt, frame: dict, suffix: str, font_mode: str):
    """图C：事件时间线三类散点（事件/KPI/失效，中文图例）。"""
    fig, ax = plt.subplots(figsize=(7.0, 4.5))
    ax.set_xlabel("时间 (ms)")
    ax.set_ylabel("类别")
    ax.set_title(f"事件时间线{suffix}")
    t, kinds = frame["t"], frame["kind"]
    if t:
        for code, (label, color) in _KIND_STYLES.items():
            ts_of_kind = [ti for ti, ki in zip(t, kinds) if ki == code]
            ax.scatter(ts_of_kind, [code] * len(ts_of_kind), color=color, s=42, label=label)
        ax.set_yticks(list(_KIND_STYLES))
        ax.set_yticklabels([label for label, _ in _KIND_STYLES.values()])
        ax.set_ylim(-0.5, 2.5)
        ax.grid(True, axis="x", alpha=0.3)
        ax.legend(title="类别")
    else:
        _annotate_empty(ax)
    _fallback_note(fig, font_mode)
    return fig


_FRAME_KEYS = ("frame_a", "frame_b", "frame_c")
_DRAWERS = (_draw_frame_a, _draw_frame_b, _draw_frame_c)


def plot_triple_curves(data: dict, out_dir: str, run_label: str = "") -> dict:
    """三元曲线三图绘制：build_curve_frames 出帧→三 PNG+curves_data.json 落盘。

    输入/输出/错误口径见模块 docstring；示例::

        result = plot_triple_curves(
            {'kpi': [...], 'events': [...], 'failure_levels': [...]},
            out_dir='plots/', run_label='RUN-07',
        )
        # result['png_paths'] == ['plots/curve_a_per_vs_level.png', ...]
        # result['partial'] False / result['font'] 'cjk'

    - 部分缺数据：已得图照出+空帧轴注「partial：无数据」，``partial=True``；
    - 三路全空→:attr:`CurvesError`；matplotlib 缺/``out_dir`` 不可写→
      :attr:`CurvesError`（缺库消息含 ``pip install matplotlib`` 提示）；
    - ``data`` 形状错→:attr:`ValueError` 透传 build_curve_frames。

    :raises CurvesError: matplotlib 缺失、三路数据全空或 ``out_dir`` 不可写。
    :raises ValueError: ``data`` 形状不合规（透传 build_curve_frames）。
    """
    frames = build_curve_frames(data)  # 形状错 ValueError 透传（本函数不拦截）

    if (
        frames["n_windows"] == 0
        and frames["n_kpi_rows"] == 0
        and not frames["frame_c"]["t"]
    ):
        raise CurvesError(
            "三路数据全空（kpi/events/failure_levels 均无可绘内容），拒绝输出空图"
        )

    plt, fm = _import_pyplot()
    font_mode = _apply_font(plt, fm)

    if os.path.exists(out_dir) and not os.path.isdir(out_dir):
        raise CurvesError(f"out_dir 已被文件占用，不是可写目录: {out_dir!r}")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        raise CurvesError(
            f"out_dir 不可写（目录创建失败）: {out_dir!r}（{exc}）"
        ) from exc

    suffix = f"（{run_label}）" if run_label else ""
    png_paths: list[str] = []
    for name, key, draw in zip(_PNG_NAMES, _FRAME_KEYS, _DRAWERS):
        fig = draw(plt, frames[key], suffix, font_mode)
        path = os.path.join(out_dir, name)
        try:
            fig.savefig(path, dpi=_DPI)
        except OSError as exc:
            plt.close(fig)
            raise CurvesError(
                f"PNG 落盘失败（out_dir 不可写?）: {path!r}（{exc}）"
            ) from exc
        plt.close(fig)
        png_paths.append(path)

    plottable_a = sum(1 for value in frames["frame_a"]["y"] if value is not None)
    plottable_b = len(frames["frame_b"]["x"])
    missing = [
        key
        for key, empty in (
            ("frame_a", plottable_a == 0),
            ("frame_b", plottable_b == 0),
            ("frame_c", not frames["frame_c"]["t"]),
        )
        if empty
    ]
    partial = bool(missing) or plottable_a < 2 or plottable_b < 2

    data_path = os.path.join(out_dir, "curves_data.json")
    payload = {
        "frames": frames,
        "plot": {
            "dpi": _DPI,
            "png_names": list(_PNG_NAMES),
            "font": font_mode,
            "run_label": run_label,
            "partial": partial,
            "missing": missing,
        },
    }
    try:
        with open(data_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except OSError as exc:
        raise CurvesError(
            f"curves_data.json 落盘失败: {data_path!r}（{exc}）"
        ) from exc

    return {
        "png_paths": png_paths,
        "data_path": data_path,
        "partial": partial,
        "font": font_mode,
        "missing": missing,
    }
