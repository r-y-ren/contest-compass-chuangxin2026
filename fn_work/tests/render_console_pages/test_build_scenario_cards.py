"""build_scenario_cards 对抗测试：正常卡字段、损坏跳过+error 卡、空/非 list 拒、
style 缺省 unknown、risk 分档与显式覆盖、注释 desc 优先。"""
from __future__ import annotations

import pytest

from src.render_console_pages.build_scenario_cards import build_scenario_cards

VALID_YAML = (
    "# desc: 定频音干扰演示\n"
    "style: tone\n"
    "fs: 2000000\n"
    "freq_hz: 2440000000\n"
    "power_dbm: -10\n"
    "backend: SIM\n"
)


def _write(tmp_path, text, name="scenario.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_valid_yaml_card_fields(tmp_path):
    """① 正常场景→完整卡：name=文件名、注释 desc、style 小写、backend 小写。"""
    path = _write(tmp_path, VALID_YAML, name="tone_demo.yaml")
    cards = build_scenario_cards([path])
    assert cards == [
        {
            "name": "tone_demo",
            "desc": "定频音干扰演示",
            "style_tags": ["tone"],
            "risk": "low",  # -10dBm 不高于分档线
            "backend_hint": "sim",
        }
    ]


def test_broken_file_error_card_others_kept(tmp_path):
    """② 损坏（不存在路径）→占位 error 卡，同批其余卡完好，长度不缩。"""
    good = _write(tmp_path, VALID_YAML, name="good.yaml")
    cards = build_scenario_cards([good, str(tmp_path / "ghost.yaml")])
    assert len(cards) == 2
    assert cards[0]["name"] == "good" and "style_tags" in cards[0]
    bad = cards[1]
    assert bad["name"] == "ghost"
    assert "error" in bad and "error" not in cards[0]
    assert "FileNotFoundError" in bad["error"]  # 原因可读


def test_binary_garbage_error_card(tmp_path):
    """③ 非 UTF-8 二进制垃圾→error 卡（UnicodeDecodeError 原因），不炸整批。"""
    p = tmp_path / "binary.yaml"
    p.write_bytes(b"\xff\xfe\x00\x01not-utf8")
    cards = build_scenario_cards([str(p)])
    assert cards[0]["name"] == "binary"
    assert "UnicodeDecodeError" in cards[0]["error"]


def test_empty_list_returns_empty():
    """④ 空列表→[]（场景目录空态）。"""
    assert build_scenario_cards([]) == []


@pytest.mark.parametrize("bad", ["a.yaml", None, 42])
def test_non_list_input_rejected(bad):
    """⑤ 非 list 输入（str/None/int）→ValueError。"""
    with pytest.raises(ValueError):
        build_scenario_cards(bad)


def test_style_missing_defaults_unknown(tmp_path):
    """⑥ 无 style 行→style_tags=['unknown']。"""
    path = _write(tmp_path, "power_dbm: -20\nbackend: sim\n", name="plain.yaml")
    cards = build_scenario_cards([path])
    assert cards[0]["style_tags"] == ["unknown"]


def test_style_multi_tags_parsed(tmp_path):
    """⑦ style 值多标签（逗号/内联括号）→切分小写标签列表。"""
    path = _write(tmp_path, "style: [Chirp, Noise/pulse]\n", name="mix.yaml")
    cards = build_scenario_cards([path])
    assert cards[0]["style_tags"] == ["chirp", "noise", "pulse"]


def test_risk_mid_above_power_threshold(tmp_path):
    """⑧ power_dbm 高于 -10 分档线→risk='mid'（缺省 backend→'sim'）。"""
    path = _write(tmp_path, "style: tone\npower_dbm: -5\n", name="hot.yaml")
    cards = build_scenario_cards([path])
    assert cards[0]["risk"] == "mid"
    assert cards[0]["backend_hint"] == "sim"


def test_risk_comment_override(tmp_path):
    """⑨ `# risk: mid` 注释显式覆盖分档（低功率也标 mid）。"""
    path = _write(
        tmp_path, "# risk: mid\nstyle: tone\npower_dbm: -30\n", name="marked.yaml"
    )
    cards = build_scenario_cards([path])
    assert cards[0]["risk"] == "mid"


def test_desc_from_yaml_key_fallback(tmp_path):
    """⑩ 无注释 desc 时回退顶层 `desc:` 键。"""
    path = _write(tmp_path, "desc: 键值描述\nstyle: tone\n", name="kv.yaml")
    cards = build_scenario_cards([path])
    assert cards[0]["desc"] == "键值描述"
