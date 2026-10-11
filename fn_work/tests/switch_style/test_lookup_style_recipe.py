"""lookup_style_recipe 行为用例：六样式配方注册表查询+登记扩展点（对抗用例，fn-implement 阶段填充）。"""
from __future__ import annotations

import pytest
import numpy as np

from src.synthesize_style.gen_bandlimited_noise import gen_bandlimited_noise
from src.synthesize_style.gen_chirp import gen_chirp
from src.synthesize_style.gen_partial_band import gen_partial_band
from src.synthesize_style.gen_pulse import gen_pulse
from src.synthesize_style.gen_sweep import gen_sweep
from src.synthesize_style.gen_tone import gen_tone
from src.switch_style.lookup_style_recipe import (
    RECIPES,
    StyleError,
    lookup_style_recipe,
    register_recipe,
)

_SIX = ("tone", "sweep", "chirp", "bandlimited_noise", "partial_band", "pulse")

# 六样式期望契约：generator 引用 / defaults 键集 / required 列表（顺序即规约）。
_EXPECTED = {
    "tone": (
        gen_tone,
        {"freq_offset_hz", "n_samples"},
        ["freq_offset_hz", "n_samples"],
    ),
    "sweep": (
        gen_sweep,
        {"f0", "f1", "duration_s", "repeats", "fs"},
        ["f0", "f1", "duration_s"],
    ),
    "chirp": (
        gen_chirp,
        {"center_hz", "bandwidth_hz", "period_s", "n_samples", "fs", "shape"},
        ["center_hz", "bandwidth_hz", "period_s", "n_samples"],
    ),
    "bandlimited_noise": (
        gen_bandlimited_noise,
        {"bandwidth_hz", "n_samples", "fs", "center_offset_hz", "seed"},
        ["bandwidth_hz", "n_samples"],
    ),
    "partial_band": (
        gen_partial_band,
        {"fraction", "victim_bw_hz", "n_samples", "fs", "center_offset_hz", "seed"},
        ["fraction", "victim_bw_hz", "n_samples"],
    ),
    "pulse": (
        gen_pulse,
        {"pulse_width_s", "repeat_hz", "n_samples", "fs", "carrier_hz"},
        ["pulse_width_s", "repeat_hz", "n_samples"],
    ),
}


def _recipe_sandbox():
    """快照/恢复 RECIPES：登记类用例改册后还原，隔离不泄漏到其他用例。"""
    saved = {name: {
        "generator": r["generator"],
        "defaults": dict(r["defaults"]),
        "required": list(r["required"]),
    } for name, r in RECIPES.items()}
    return saved


@pytest.fixture()
def restore_registry():
    saved = _recipe_sandbox()
    yield RECIPES
    RECIPES.clear()
    RECIPES.update(saved)


def _valid_recipe():
    """合法最小配方（独立于六基础样式，供登记类用例）。"""
    return {
        "generator": gen_tone,
        "defaults": {"freq_offset_hz": 2e3, "n_samples": 128},
        "required": ["freq_offset_hz", "n_samples"],
    }


# ---------------------------------------------------------------------------
# 查询主路径
# ---------------------------------------------------------------------------

def test_six_styles_recipe_shape_generator_and_keys():
    """六样式查询：恰三键、generator 即对应生成器引用、defaults/required 键齐且序符规约。"""
    for name in _SIX:
        recipe = lookup_style_recipe(name)
        gen, def_keys, req_list = _EXPECTED[name]
        assert set(recipe) == {"generator", "defaults", "required"}, name
        assert recipe["generator"] is gen, name
        assert callable(recipe["generator"]), name
        assert set(recipe["defaults"]) == def_keys, name
        assert isinstance(recipe["defaults"], dict), name
        assert recipe["required"] == req_list, name
        assert isinstance(recipe["required"], list), name


def test_defaults_values_domain_valid_direct_generator_call():
    """defaults 值合理默认：整包直调对应生成器全过取值域，出 complex64 IQ。"""
    for name in _SIX:
        recipe = lookup_style_recipe(name)
        out = recipe["generator"](**recipe["defaults"])
        iq = out[0] if isinstance(out, tuple) else out  # 噪声/部分带/脉冲返 (iq, meta)
        assert isinstance(iq, np.ndarray) and iq.dtype == np.complex64, name
        defaults = recipe["defaults"]
        if "n_samples" in defaults:
            assert len(iq) == defaults["n_samples"], name
        else:  # sweep：长度 = round(duration_s*fs)*repeats
            expected = round(defaults["duration_s"] * defaults["fs"]) * defaults["repeats"]
            assert len(iq) == expected, name


def test_unknown_name_style_error_with_roster():
    """未知名 → StyleError 且信息附在册清单（六样式名逐一可见）。"""
    for bad in ("spread", "noise", "tone2", "fm"):
        with pytest.raises(StyleError) as excinfo:
            lookup_style_recipe(bad)
        msg = str(excinfo.value)
        for name in _SIX:
            assert name in msg, (bad, name)


def test_lookup_case_insensitive_and_surrounding_blank_tolerated():
    """大小写不敏感：任意大小写/混合及前后空白均命中同一配方。"""
    for spelled in ("TONE", "Chirp", "BandLimited_Noise", "PARTIAL_BAND", "  Pulse  ", "\tSWEEP\n"):
        recipe = lookup_style_recipe(spelled)
        canonical = spelled.strip().lower()
        assert recipe["generator"] is _EXPECTED[canonical][0], spelled
        assert set(recipe["defaults"]) == set(_EXPECTED[canonical][1]), spelled


def test_name_none_empty_blank_or_non_str_rejected():
    """名 None / 空 / 纯空白 / 非 str → StyleError（不是 TypeError）。"""
    for bad in (None, "", "   ", "\t \n", 123, ["tone"], ("tone",), {"tone"}, 3.0, True):
        with pytest.raises(StyleError):
            lookup_style_recipe(bad)


def test_returned_recipe_is_copy_registry_untouched():
    """返回副本：改写返回值（含 defaults/required 子层）不影响注册表与再查。"""
    before = _recipe_sandbox()
    recipe = lookup_style_recipe("tone")
    recipe["generator"] = None
    recipe["defaults"]["freq_offset_hz"] = -999.0
    recipe["defaults"]["injected_key"] = 1
    recipe["required"].append("injected_param")
    recipe["extra"] = "x"
    again = lookup_style_recipe("TONE")
    assert again["generator"] is gen_tone
    assert set(again["defaults"]) == {"freq_offset_hz", "n_samples"}
    assert again["required"] == ["freq_offset_hz", "n_samples"]
    assert set(again) == {"generator", "defaults", "required"}
    assert _recipe_sandbox() == before
    # 副本对象本身也不与注册表共享子结构
    assert again["defaults"] is not RECIPES["tone"]["defaults"]
    assert again["required"] is not RECIPES["tone"]["required"]


# ---------------------------------------------------------------------------
# 登记扩展点 register_recipe
# ---------------------------------------------------------------------------

def test_register_new_style_then_queryable(restore_registry):
    """登记新样式 → 可查（大小写同口径），返回副本与再查结果同构。"""
    registered = register_recipe("custom_cw", _valid_recipe())
    assert registered["generator"] is gen_tone
    looked = lookup_style_recipe("CUSTOM_CW")
    assert looked["generator"] is gen_tone
    assert looked["defaults"] == {"freq_offset_hz": 2e3, "n_samples": 128}
    assert looked["required"] == ["freq_offset_hz", "n_samples"]


def test_register_duplicate_without_override_rejected(restore_registry):
    """重名未 override → StyleError，注册表保持原配方不变。"""
    with pytest.raises(StyleError) as excinfo:
        register_recipe("tone", _valid_recipe())
    assert "override" in str(excinfo.value)
    assert RECIPES["tone"]["generator"] is gen_tone  # 原配方未被覆盖
    assert lookup_style_recipe("tone")["generator"] is gen_tone


def test_register_duplicate_with_override_replaces(restore_registry):
    """重名 + override=True → 覆盖生效，再查返回新配方。"""
    new_recipe = _valid_recipe()
    new_recipe["defaults"] = {"freq_offset_hz": 5e3, "n_samples": 64}
    register_recipe("Tone", new_recipe, override=True)  # 归一后同为 'tone'
    looked = lookup_style_recipe("tone")
    assert looked["defaults"] == {"freq_offset_hz": 5e3, "n_samples": 64}


def test_register_missing_key_rejected(restore_registry):
    """配方缺任一必需键 → StyleError，不入册。"""
    for drop in ("generator", "defaults", "required"):
        broken = _valid_recipe()
        del broken[drop]
        with pytest.raises(StyleError) as excinfo:
            register_recipe("custom_cw", broken)
        assert drop in str(excinfo.value)
    assert "custom_cw" not in RECIPES


def test_register_extra_key_rejected(restore_registry):
    """配方含未知多余键 → StyleError（形状契约：恰三键），不入册。"""
    broken = _valid_recipe()
    broken["meta"] = {"doc": "x"}
    with pytest.raises(StyleError) as excinfo:
        register_recipe("custom_cw", broken)
    assert "meta" in str(excinfo.value)
    assert "custom_cw" not in RECIPES


def test_register_wrong_types_rejected(restore_registry):
    """类型错拒：defaults 非 dict / required 非 list（tuple/str/dict）/ generator 不可调用。"""
    cases = (
        {"generator": gen_tone, "defaults": ["freq_offset_hz", 1e3], "required": ["freq_offset_hz"]},
        {"generator": gen_tone, "defaults": "freq_offset_hz", "required": []},
        {"generator": gen_tone, "defaults": None, "required": []},
        {"generator": gen_tone, "defaults": {}, "required": ("freq_offset_hz",)},  # tuple 拒
        {"generator": gen_tone, "defaults": {}, "required": "freq_offset_hz"},  # str 拒
        {"generator": gen_tone, "defaults": {}, "required": {"freq_offset_hz"}},  # set 拒
        {"generator": gen_tone, "defaults": {}, "required": 42},  # int 拒
        {"generator": "gen_tone", "defaults": {}, "required": []},  # 不可调用拒
        {"generator": None, "defaults": {}, "required": []},
        {"generator": 123, "defaults": {}, "required": []},
        {"generator": gen_tone, "defaults": {}, "required": [123, None]},  # 元素非 str 拒
        {"generator": gen_tone, "defaults": {}, "required": ["freq_offset_hz", ""]},  # 空串拒
    )
    for broken in cases:
        with pytest.raises(StyleError):
            register_recipe("custom_cw", broken)
    assert "custom_cw" not in RECIPES


def test_register_non_dict_recipe_or_bad_name_rejected(restore_registry):
    """配方非 dict / 名 None/空/非 str → StyleError，注册表不变。"""
    before = _recipe_sandbox()
    for broken in (None, [], ("generator",), 42, "generator"):
        with pytest.raises(StyleError):
            register_recipe("custom_cw", broken)
    for bad_name in (None, "", "   ", 123, ["x"]):
        with pytest.raises(StyleError):
            register_recipe(bad_name, _valid_recipe())
    assert _recipe_sandbox() == before
    assert set(RECIPES) == set(before)


def test_register_stores_copy_caller_mutation_isolated(restore_registry):
    """入册存副本：登记后改写调用方原 recipe 不影响注册表与再查。"""
    original = _valid_recipe()
    register_recipe("custom_cw", original)
    original["generator"] = None
    original["defaults"]["freq_offset_hz"] = -1.0
    original["defaults"]["extra"] = 0
    original["required"].append("extra_param")
    looked = lookup_style_recipe("custom_cw")
    assert looked["generator"] is gen_tone
    assert looked["defaults"] == {"freq_offset_hz": 2e3, "n_samples": 128}
    assert looked["required"] == ["freq_offset_hz", "n_samples"]
