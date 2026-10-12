"""plot_triple_curves 对抗单测（B13 顶层，R25）：三 PNG 落盘/json 溯源/字体/降级/错误路径。

覆盖（≥11）：三 PNG 存在+魔数头+尺寸>0+返回契约、curves_data.json 可解析含三帧
且失效红点数据在 json、缺 matplotlib→CurvesError 含 pip 提示、全空 data→
CurvesError、单窗数据→partial True 两图仍出、out_dir 不存在自动建、out_dir 为
文件→CurvesError、帧A None 断点（窗口无判据）不炸、run_label 进三图标题、
字体全缺→fallback 不炸、data 形状错透传 ValueError、仅 KPI 无事件→partial+
missing 标注。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.plot_triple_curves import plot_triple_curves as ptc
from src.plot_triple_curves.plot_triple_curves import CurvesError, plot_triple_curves

#: PNG 魔数头（89 50 4E 47 0D 0A 1A 0A）。
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

_PNG_NAMES = (
    "curve_a_per_vs_level.png",
    "curve_b_throughput_vs_per.png",
    "curve_c_event_timeline.png",
)


def _full_data():
    """两窗+失效档标准夹具：帧A x=[-10,-5]、y=[0.10,0.30]、failure_x=[-5.0]。"""
    return {
        "kpi": [
            {"ts_ms": 150, "judge_per": 0.08},
            {"ts_ms": 250, "judge_per": 0.12},
            {"ts_ms": 350, "judge_per": 0.30},
        ],
        "events": [
            {"type": "power_step", "ts_ms": 100, "step": 0, "target_db": -10.0},
            {"type": "power_step", "ts_ms": 300, "step": 1, "target_db": -5.0},
        ],
        "failure_levels": [{"step": 1, "ts_ms": 320}],
    }


def _assert_png(path: Path) -> None:
    assert path.is_file(), f"PNG 未落盘: {path}"
    assert path.stat().st_size > 0, f"PNG 为空文件: {path}"
    assert path.read_bytes()[:8] == _PNG_MAGIC, f"非 PNG 魔数头: {path}"


def test_triple_curves_full_data_three_pngs_with_magic_and_contract(tmp_path):
    out = tmp_path / "plots"
    result = plot_triple_curves(_full_data(), str(out))

    assert [Path(p).name for p in result["png_paths"]] == list(_PNG_NAMES)
    for png in result["png_paths"]:
        _assert_png(Path(png))
    assert Path(result["data_path"]).name == "curves_data.json"
    assert Path(result["data_path"]).is_file()
    assert result["partial"] is False
    assert result["font"] in ("cjk", "fallback")
    assert result["missing"] == []


def test_triple_curves_json_parsable_with_frames_and_failure_points(tmp_path):
    result = plot_triple_curves(_full_data(), str(tmp_path))

    payload = json.loads(Path(result["data_path"]).read_text(encoding="utf-8"))
    assert set(payload["frames"]) >= {"frame_a", "frame_b", "frame_c"}
    # 失效红点数据（报告溯源）：step=1 → 对位窗 x=-5.0
    assert payload["frames"]["frame_a"]["failure_x"] == [-5.0]
    assert payload["frames"]["frame_a"]["y"] == pytest.approx([0.10, 0.30])
    assert payload["frames"]["frame_b"]["y"] == pytest.approx([0.90, 0.70])
    assert payload["plot"]["dpi"] == 150
    assert payload["plot"]["partial"] is False


def test_triple_curves_missing_matplotlib_curves_error_with_pip_hint(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "matplotlib", None)  # import 即 ImportError

    with pytest.raises(CurvesError) as excinfo:
        plot_triple_curves(_full_data(), str(tmp_path))

    assert "pip install matplotlib" in str(excinfo.value)


def test_triple_curves_all_empty_data_raises_curves_error(tmp_path):
    with pytest.raises(CurvesError):
        plot_triple_curves(
            {"kpi": [], "events": [], "failure_levels": []}, str(tmp_path)
        )


def test_triple_curves_single_window_partial_still_renders_ab(tmp_path):
    data = {
        "kpi": [{"ts_ms": 150, "judge_per": 0.2}],
        "events": [
            {"type": "power_step", "ts_ms": 100, "step": 0, "target_db": -10.0}
        ],
        "failure_levels": [],
    }
    out = tmp_path / "plots"

    result = plot_triple_curves(data, str(out))

    assert result["partial"] is True
    _assert_png(out / "curve_a_per_vs_level.png")
    _assert_png(out / "curve_b_throughput_vs_per.png")


def test_triple_curves_missing_out_dir_auto_created(tmp_path):
    out = tmp_path / "deep" / "nested" / "plots"

    result = plot_triple_curves(_full_data(), str(out))

    assert out.is_dir()
    for name in _PNG_NAMES:
        _assert_png(out / name)


def test_triple_curves_out_dir_is_file_raises_curves_error(tmp_path):
    target = tmp_path / "occupied"
    target.write_text("not a directory", encoding="utf-8")

    with pytest.raises(CurvesError):
        plot_triple_curves(_full_data(), str(target))


def test_triple_curves_none_breakpoint_window_renders_without_crash(tmp_path):
    data = {
        # 窗1 两行均无判据样本 → 帧A y=[0.1, None]（绘图断点）
        "kpi": [{"ts_ms": 150, "judge_per": 0.1}, {"ts_ms": 350}],
        "events": [
            {"type": "power_step", "ts_ms": 100, "step": 0, "target_db": -10.0},
            {"type": "power_step", "ts_ms": 300, "step": 1, "target_db": -5.0},
        ],
        "failure_levels": [],
    }

    result = plot_triple_curves(data, str(tmp_path))

    assert result["partial"] is True
    for png in result["png_paths"]:
        _assert_png(Path(png))
    payload = json.loads(Path(result["data_path"]).read_text(encoding="utf-8"))
    assert payload["frames"]["frame_a"]["y"][1] is None


def test_triple_curves_run_label_appears_in_all_titles(tmp_path, monkeypatch):
    import matplotlib.axes

    titles: list[str] = []
    original_set_title = matplotlib.axes.Axes.set_title

    def spy_set_title(self, label, *args, **kwargs):
        titles.append(str(label))
        return original_set_title(self, label, *args, **kwargs)

    monkeypatch.setattr(matplotlib.axes.Axes, "set_title", spy_set_title)

    plot_triple_curves(_full_data(), str(tmp_path), run_label="RUN-42")

    assert sum("RUN-42" in title for title in titles) >= 3  # 三图标题均带后缀


def test_triple_curves_font_fallback_when_no_cjk_font(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ptc, "_CJK_FONT_CANDIDATES", ("NoSuchFontA", "NoSuchFontB")
    )

    result = plot_triple_curves(_full_data(), str(tmp_path))

    assert result["font"] == "fallback"
    for png in result["png_paths"]:
        _assert_png(Path(png))  # 缺字警告但不炸、图照出


def test_triple_curves_bad_data_shape_value_error_passthrough(tmp_path):
    with pytest.raises(ValueError):
        plot_triple_curves(
            {"kpi": "not-a-list", "events": [], "failure_levels": []}, str(tmp_path)
        )
    with pytest.raises(ValueError):
        plot_triple_curves(["not-a-dict"], str(tmp_path))


def test_triple_curves_kpi_only_partial_missing_frame_ab(tmp_path):
    data = {"kpi": [{"ts_ms": 100, "judge_per": 0.5}], "events": [], "failure_levels": []}

    result = plot_triple_curves(data, str(tmp_path))

    assert result["partial"] is True
    assert set(result["missing"]) == {"frame_a", "frame_b"}
    # 图C（KPI 时间线点）仍出
    _assert_png(tmp_path / "curve_c_event_timeline.png")
