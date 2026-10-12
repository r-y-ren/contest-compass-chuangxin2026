"""render_disclaimer_sections 对抗测试：基座关键词、上下文行 '> ' 前缀、per_basis
BER→PER 句、simulated_parts 追加 emc 级块、空 ctx 缺省补"未记录"、段序与幂等、
非 dict/字段类型错拒绝。"""
from __future__ import annotations

import pytest

from src.build_report.render_disclaimer_sections import render_disclaimer_sections
from src.shared.make_disclaimer_block import make_disclaimer_block


def _full_ctx() -> dict:
    return {
        "backend": "sim-replay-v2",
        "clock_ref": "time.monotonic",
        "per_basis": True,
        "simulated_parts": ["emc", "mixer"],
        "run_id": "run_20261011_01",
    }


def test_base_block_keywords_report_scene():
    """① 基座为 report 场景块：含 'GB 42590'/'屏蔽盒'，且不含 emc 专属句。"""
    out = render_disclaimer_sections(_full_ctx())
    assert "GB 42590" in out
    assert "屏蔽盒" in out
    assert make_disclaimer_block("report") in out


def test_backend_context_line_quoted():
    """② backend/clock_ref/run_id 各成上下文行：'> ' 前缀且携带原值。"""
    out = render_disclaimer_sections(_full_ctx())
    context_block = out.split("\n\n")[1]
    lines = context_block.split("\n")
    assert any(line.startswith("> ") and "sim-replay-v2" in line for line in lines)
    assert any(line.startswith("> ") and "time.monotonic" in line for line in lines)
    assert any(line.startswith("> ") and "run_20261011_01" in line for line in lines)


def test_per_basis_true_appends_ber_to_per_line():
    """③ per_basis=True：追加 BER→PER 声明句（同现 'PER' 与 'BER'）。"""
    out = render_disclaimer_sections(_full_ctx())
    assert "PER" in out and "BER" in out


def test_per_basis_false_or_missing_omits_line():
    """④ per_basis 缺省或 False：不出现 BER→PER 换算口径句。"""
    ctx = _full_ctx()
    ctx["per_basis"] = False
    assert "由 BER 换算" not in render_disclaimer_sections(ctx)
    del ctx["per_basis"]
    assert "由 BER 换算" not in render_disclaimer_sections(ctx)


def test_simulated_parts_appends_emc_block():
    """⑤ simulated_parts 非空：追加 emc 级整块（含 'CISPR 16-1-1' 与模拟段清单行）。"""
    out = render_disclaimer_sections(_full_ctx())
    assert "CISPR 16-1-1" in out
    assert "全部读数带 simulated 标记" in out
    assert make_disclaimer_block("emc") in out
    assert any("emc" in line and "mixer" in line for line in out.split("\n"))


def test_no_simulated_parts_no_emc_block():
    """⑥ simulated_parts 缺省/空列表：不混入 emc 级块（无 CISPR 16-1-1 句）。"""
    ctx = _full_ctx()
    ctx["simulated_parts"] = []
    assert "CISPR 16-1-1" not in render_disclaimer_sections(ctx)
    del ctx["simulated_parts"]
    out = render_disclaimer_sections(ctx)
    assert "CISPR 16-1-1" not in out
    assert out.count("\n\n") == 1  # 仅基座+上下文两段


def test_empty_ctx_fields_fill_missing_token():
    """⑦ 空 ctx 容忍：backend/clock_ref/run_id 缺省补 '未记录'（各三处）。"""
    out = render_disclaimer_sections({})
    assert out.count("未记录") == 3


def test_blank_string_fields_fill_missing_token():
    """⑦b 空白串字段同样补 '未记录'，不产出空白上下文行。"""
    out = render_disclaimer_sections({"backend": "  ", "clock_ref": "", "run_id": "\t"})
    assert out.count("未记录") == 3


def test_section_order_and_quote_prefix():
    """⑧ 段序：基座+空行+上下文+模拟段；上下文行逐行 '> ' 前缀，无裸行。"""
    out = render_disclaimer_sections(_full_ctx())
    sections = out.split("\n\n")
    assert len(sections) == 3
    assert sections[0] == make_disclaimer_block("report")
    assert sections[2] == make_disclaimer_block("emc")
    for line in sections[1].split("\n"):
        assert line.startswith("> ") and len(line) > 2, f"上下文行缺前缀: {line!r}"


def test_deterministic_idempotent_output():
    """⑨ 同 ctx 两次调用输出逐字相等（文案幂等，无时钟/随机混入）。"""
    assert render_disclaimer_sections(_full_ctx()) == render_disclaimer_sections(_full_ctx())


def test_non_dict_ctx_rejected():
    """⑩ report_ctx 非 dict（None/list/str/int）→ ValueError。"""
    for bad in (None, ["backend"], "backend", 7, ("backend",)):
        with pytest.raises(ValueError, match="dict"):
            render_disclaimer_sections(bad)


@pytest.mark.parametrize("field", ["backend", "clock_ref", "run_id"])
def test_non_string_text_fields_rejected(field):
    """⑪ str 字段给了非 str（int/list/bool）→ ValueError，消息含字段名。"""
    for bad in (7, ["x"], True):
        with pytest.raises(ValueError, match=field):
            render_disclaimer_sections({field: bad})


def test_non_bool_per_basis_rejected():
    """⑫ per_basis 给了非 bool（1/'true'/None）→ ValueError。"""
    for bad in (1, 0, "true", None):
        with pytest.raises(ValueError, match="per_basis"):
            render_disclaimer_sections({"per_basis": bad})


def test_bad_simulated_parts_rejected():
    """⑬ simulated_parts 非 list（tuple/str/None）或元素非 str → ValueError。"""
    for bad in (("emc",), "emc", None, {"emc": 1}):
        with pytest.raises(ValueError, match="simulated_parts"):
            render_disclaimer_sections({"simulated_parts": bad})
    with pytest.raises(ValueError, match="simulated_parts"):
        render_disclaimer_sections({"simulated_parts": ["emc", 3]})
