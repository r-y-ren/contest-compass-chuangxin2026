"""switch_style 对抗测试（B8 顶层 R10）：取配方→预合成→原子替换——
切换完整性/二次切换/失败保旧值（未注册与 power 越红线）/defaults 合成/
六样式参数化/计时<2s/幂等/ctx 非 dict 拒/请求名落位。"""
from __future__ import annotations

import numpy as np
import pytest

from src.switch_style.lookup_style_recipe import StyleError
from src.switch_style.switch_style import switch_style

# 就绪实例写入形状契约（恰五键）。
_READY_KEYS = {"iq", "meta", "style", "prepared_at", "switch_ms"}

_SIX_STYLE_PARAMS = {
    "tone": {"freq_offset_hz": 1e3, "n_samples": 256, "fs": 1e6},
    "sweep": {"f0": -1e3, "f1": 1e3, "duration_s": 1e-3},
    "chirp": {"center_hz": 0.0, "bandwidth_hz": 10e3, "period_s": 1e-3, "n_samples": 512},
    "bandlimited_noise": {"bandwidth_hz": 10e3, "n_samples": 2048, "fs": 1e6, "seed": 11},
    "partial_band": {"fraction": 0.5, "victim_bw_hz": 10e3, "n_samples": 2048, "fs": 1e6, "seed": 12},
    "pulse": {"pulse_width_s": 1e-4, "repeat_hz": 1e3, "n_samples": 2048, "fs": 1e6},
}


def test_styles_switch_normal_replaces_current_style_with_full_keys():
    """正常切换：ctx['current_style'] 被替换为恰五键就绪实例，返回四键齐 + switch_ms≥0。"""
    ctx: dict = {"current_style": None, "run_id": "r1"}
    result = switch_style(ctx, "tone", {"freq_offset_hz": 1e3, "n_samples": 256, "fs": 1e6})
    ready = ctx["current_style"]
    assert set(ready) == _READY_KEYS
    assert isinstance(ready["iq"], np.ndarray) and ready["iq"].dtype == np.complex64
    assert isinstance(ready["meta"], dict)
    assert ready["switch_ms"] >= 0.0
    assert set(result) == {"style", "switch_ms", "prepared", "samples"}
    assert result["style"] == "tone"
    assert result["prepared"] is True
    assert result["samples"] == ready["iq"].size == 256
    assert result["switch_ms"] == ready["switch_ms"]
    assert ctx["run_id"] == "r1"  # 仅动 current_style 键


def test_styles_switch_second_switch_replaces_again():
    """二次切换：再替换——style 名更新且新旧就绪实例对象不同。"""
    ctx: dict = {}
    first = switch_style(ctx, "tone", {"freq_offset_hz": 1e3, "n_samples": 256, "fs": 1e6})
    ready_first = ctx["current_style"]
    assert first["style"] == "tone"
    second = switch_style(ctx, "chirp", {"bandwidth_hz": 10e3, "n_samples": 512, "fs": 1e6})
    ready_second = ctx["current_style"]
    assert second["style"] == ready_second["style"] == "chirp"
    assert ready_second is not ready_first
    assert ready_second["style"] != ready_first["style"]
    assert np.array_equal(ready_second["iq"], ctx["current_style"]["iq"])


def test_styles_switch_unregistered_name_keeps_old_style():
    """未注册名 → StyleError 且 ctx['current_style'] 保持旧值原对象（无部分写）。"""
    old_ready = {"style": "tone", "iq": np.zeros(4, dtype=np.complex64), "meta": {}}
    ctx: dict = {"current_style": old_ready}
    with pytest.raises(StyleError):
        switch_style(ctx, "no_such_style", {"fs": 1e6})
    assert ctx["current_style"] is old_ready
    assert set(ctx) == {"current_style"}  # 失败路径不新增任何键


def test_styles_switch_synthesis_failure_power_over_redline_keeps_ctx():
    """合成失败（power_dbm=+3 越 0 dBm 红线）→ StyleError 且 ctx 不变。"""
    old_ready = {"style": "pulse", "iq": np.ones(8, dtype=np.complex64), "meta": {}}
    ctx: dict = {"current_style": old_ready}
    with pytest.raises(StyleError):
        switch_style(
            ctx,
            "tone",
            {"freq_offset_hz": 1e3, "n_samples": 256, "fs": 1e6, "power_dbm": 3.0},
        )
    assert ctx["current_style"] is old_ready


def test_styles_switch_params_none_synthesizes_from_recipe_defaults():
    """params=None：用配方 defaults 合成（chirp defaults 自带 fs/n_samples 等全参）。"""
    ctx: dict = {}
    result = switch_style(ctx, "chirp", None)
    ready = ctx["current_style"]
    assert result["prepared"] is True
    assert ready["style"] == "chirp"
    # defaults 落位：meta['params'] 即 defaults+显式（无显式）合并结果。
    assert ready["meta"]["params"]["n_samples"] == 4096
    assert ready["meta"]["params"]["fs"] == 1e6
    assert ready["iq"].size == 4096


@pytest.mark.parametrize("style", sorted(_SIX_STYLE_PARAMS))
def test_styles_switch_all_six_styles_produce_nonempty_iq(style):
    """六样式参数化切换全过：iq 非空 complex64，ctx 与返回三处 style 名一致。"""
    ctx: dict = {}
    result = switch_style(ctx, style, dict(_SIX_STYLE_PARAMS[style]))
    ready = ctx["current_style"]
    assert isinstance(ready["iq"], np.ndarray)
    assert ready["iq"].dtype == np.complex64
    assert ready["iq"].size > 0
    assert ready["style"] == result["style"] == style


def test_styles_switch_timing_under_two_seconds():
    """切换耗时在合理量级：六样式（含大样本）逐个切换，switch_ms 均 <2000ms。"""
    ctx: dict = {}
    heavy = {
        "tone": {"freq_offset_hz": 1e3, "n_samples": 65536, "fs": 4e6},
        "sweep": {"f0": -100e3, "f1": 100e3, "duration_s": 8e-3, "fs": 4e6},
        "chirp": {"bandwidth_hz": 100e3, "period_s": 1e-3, "n_samples": 65536, "fs": 4e6},
        "bandlimited_noise": {"bandwidth_hz": 100e3, "n_samples": 65536, "fs": 4e6, "seed": 7},
        "partial_band": {"fraction": 0.5, "victim_bw_hz": 100e3, "n_samples": 65536, "fs": 4e6, "seed": 8},
        "pulse": {"pulse_width_s": 1e-4, "repeat_hz": 1e3, "n_samples": 65536, "fs": 4e6},
    }
    for style, params in heavy.items():
        result = switch_style(ctx, style, dict(params))
        assert result["switch_ms"] < 2000.0, f"{style} 切换超 2s: {result['switch_ms']}ms"
        assert ctx["current_style"]["switch_ms"] == result["switch_ms"]


def test_styles_switch_rejects_non_dict_ctx():
    """ctx 非 dict → ValueError（list 与 None 双拒）。"""
    with pytest.raises(ValueError):
        switch_style(["not", "a", "ctx"], "tone", {"fs": 1e6})
    with pytest.raises(ValueError):
        switch_style(None, "tone", {"fs": 1e6})


def test_styles_switch_idempotent_same_params_bitwise_identical():
    """切换幂等：同参数（seed 固定）两次切换，iq 逐位一致。"""
    ctx: dict = {}
    params = {"bandwidth_hz": 10e3, "n_samples": 4096, "fs": 1e6, "seed": 42}
    first = switch_style(ctx, "bandlimited_noise", dict(params))
    iq_first = ctx["current_style"]["iq"].copy()
    second = switch_style(ctx, "bandlimited_noise", dict(params))
    iq_second = ctx["current_style"]["iq"]
    assert first["samples"] == second["samples"]
    assert np.array_equal(iq_first, iq_second)
    assert iq_first.tobytes() == iq_second.tobytes()  # 逐位（含非数值位形）一致


def test_styles_switch_ctx_style_equals_requested_name():
    """切换后 ctx['current_style']['style'] 等于请求名（返回值同步）。"""
    ctx: dict = {"current_style": None}
    result = switch_style(ctx, "pulse", {"pulse_width_s": 1e-4, "repeat_hz": 1e3, "n_samples": 1024, "fs": 1e6})
    assert ctx["current_style"]["style"] == "pulse"
    assert result["style"] == "pulse"
    # 大小写不敏感请求：落位为规范小写名，与 meta 同口径。
    result_ci = switch_style(ctx, "CHIRP", {"bandwidth_hz": 10e3, "n_samples": 512, "fs": 1e6})
    assert ctx["current_style"]["style"] == result_ci["style"] == "chirp"


# ---- B8低#4/#6 回归：tone 缺省可切 / composite 可达 ----


def test_defect_b8_tone_params_none_switchable():
    """switch_style(ctx, 'tone', None) 成功：tone defaults 已补 fs（B8低#4），
    仅凭配方缺省即可预合成切换。"""
    ctx: dict = {}
    result = switch_style(ctx, "tone", None)
    ready = ctx["current_style"]
    assert result["prepared"] is True and result["style"] == "tone"
    assert result["samples"] == 4096  # defaults n_samples
    assert ready["meta"]["params"]["fs"] == 1e6
    assert ready["meta"]["params"]["freq_offset_hz"] == 1e5


@pytest.mark.parametrize("style", sorted(_SIX_STYLE_PARAMS))
def test_defect_b8_all_six_styles_params_none_switchable(style):
    """六样式 params=None 全部可切：iq 非空 complex64（各样式 defaults 自带 fs）。"""
    ctx: dict = {}
    result = switch_style(ctx, style, None)
    ready = ctx["current_style"]
    assert result["prepared"] is True
    assert ready["style"] == result["style"] == style
    assert isinstance(ready["iq"], np.ndarray) and ready["iq"].dtype == np.complex64
    assert ready["iq"].size > 0
    assert ready["meta"]["params"]["fs"] > 0


def test_defect_b8_switch_composite_success():
    """switch_style 切 'composite' 成功（B8低#6）：跳过配方查找直接合成，
    ctx 就绪实例 style='composite'，meta 带 components_meta。"""
    ctx: dict = {"current_style": None}
    result = switch_style(
        ctx,
        "composite",
        {
            "fs": 1e6,
            "components": [
                {"style": "tone", "freq_offset_hz": 20e3, "n_samples": 512},
                {"style": "tone", "freq_offset_hz": -20e3, "n_samples": 512},
            ],
        },
    )
    ready = ctx["current_style"]
    assert set(ready) == _READY_KEYS  # 写入形状与其他样式同构（恰五键）
    assert result["style"] == ready["style"] == "composite"
    assert result["samples"] == 512
    assert ready["meta"]["style"] == "composite"
    assert ready["meta"]["n_components"] == 2
    assert len(ready["meta"]["components_meta"]) == 2


def test_defect_b8_switch_composite_missing_components_styleerror():
    """switch_style 切 'composite' 缺 components → StyleError（由 synthesize_style
    判定），ctx['current_style'] 保持旧值原对象不变。"""
    old_ready = {"style": "tone", "iq": np.zeros(4, dtype=np.complex64), "meta": {}}
    ctx: dict = {"current_style": old_ready}
    with pytest.raises(StyleError) as ei:
        switch_style(ctx, "composite", {"fs": 1e6})
    assert "components" in str(ei.value)
    assert ctx["current_style"] is old_ready
    assert set(ctx) == {"current_style"}  # 失败路径不新增任何键


def test_defect_b8_switch_composite_case_insensitive():
    """composite 请求大小写不敏感：'COMPOSITE' 与小写同路径（模式分支同口径）。"""
    ctx: dict = {}
    result = switch_style(
        ctx,
        "  COMPOSITE  ",
        {"fs": 1e6, "components": [
            {"style": "tone", "freq_offset_hz": 1e3, "n_samples": 64}
        ]},
    )
    assert result["style"] == "composite"
    assert ctx["current_style"]["style"] == "composite"
