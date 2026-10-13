"""edit_scenario_ui 单测：纯静态区块资产的结构/接线/消毒断言（无浏览器——
e2e 路径在 test_scenario_editor_e2e.py，playwright 覆盖交互闭环）。

用例名统一 test_scenario_editor_ 前缀；`pytest -k scenario_editor` 可连带
发现 e2e 族（scenario_editor_e2e）。
"""
import pytest

from src.edit_scenario_ui.edit_scenario_ui import EDITOR_SECTION_ID, edit_scenario_ui

#: 七类样式白名单（与 validate_scenario_schema.SCENARIO_STYLE_WHITELIST 同口径）。
_SEVEN_STYLES = (
    "tone",
    "sweep",
    "chirp",
    "bandlimited_noise",
    "partial_band",
    "pulse",
    "composite",
)

#: 法定频段预设（MHz，与 check_band_whitelist.BAND_WHITELIST 同口径）。
_BAND_PRESETS = ("2400.0,2483.5", "5725.0,5829.0")

#: 正常卡（build_scenario_cards 产物形状）。
_GOOD_CARD = {
    "name": "tone_demo",
    "desc": "定频音演示",
    "style_tags": ["tone"],
    "risk": "low",
    "backend_hint": "sim",
}

#: 损坏占位卡（同产物形状的 error 分支）。
_BROKEN_CARD = {"name": "corrupt_one", "error": "UnicodeDecodeError: boom"}


def test_scenario_editor_returns_static_section_with_dual_modes():
    """① 产出为 str 且含区块根 id+表单/YAML 双面板与模式切换钮（hidden 初始单显）。"""
    block = edit_scenario_ui([])
    assert isinstance(block, str)
    assert f'id="{EDITOR_SECTION_ID}"' in block
    assert 'id="editor-panel-form"' in block
    assert 'id="editor-panel-yaml"' in block
    assert 'id="editor-panel-yaml" hidden' in block  # 初始表单模式，YAML 面板隐藏
    assert 'id="editor-btn-mode-form"' in block
    assert 'id="editor-btn-mode-yaml"' in block


def test_scenario_editor_form_fields_cover_schema_and_guard_domains():
    """② 表单控件覆盖 schema 必填/可选键与红线取值域：style 七类白名单、fs、
    可选数值键、bands 2.4G/5.8G 预设、安全声明必选项 shielded_box/dut_scope。"""
    block = edit_scenario_ui([])
    for field_id in (
        "editor-f-style",
        "editor-f-fs",
        "editor-f-freq",
        "editor-f-bw",
        "editor-f-power",
        "editor-f-duration",
        "editor-f-duty",
        "editor-f-repeats",
        "editor-f-backend",
        "editor-f-band",
        "editor-f-shield",
        "editor-f-dut",
    ):
        assert f'id="{field_id}"' in block
    for style in _SEVEN_STYLES:
        assert f'value="{style}"' in block
    for preset in _BAND_PRESETS:
        assert f'value="{preset}"' in block
    assert "shielded_box" in block and "dut_scope" in block


def test_scenario_editor_wires_crud_endpoints_with_native_fetch():
    """③ 三操作接线既有 CRUD 端点（POST/PUT/DELETE /api/scenarios）且用原生
    fetch——不引用 Vue（区块自足，不依赖页面 Vue 实例）。"""
    block = edit_scenario_ui([])
    assert "fetch('/api/scenarios'" in block  # POST 新建 + GET 卡片刷新
    assert "fetch('/api/scenarios/' + encodeURIComponent(target)" in block
    assert "method: 'POST'" in block
    assert "method: 'PUT'" in block
    assert "method: 'DELETE'" in block
    assert "Vue" not in block


def test_scenario_editor_error_list_renders_lines_from_400_body():
    """④ 错误清单逐条上屏基建在位：#editor-errors 容器+detail.error 按行切分
    （400 响应体 {'detail': {'field','error'}} 的多行清单逐行成 li）。"""
    block = edit_scenario_ui([])
    assert 'id="editor-errors"' in block
    assert "errorLinesFromBody" in block
    assert ".split('\\n')" in block  # JS 源中的 '\n' 字面（r 模板保真）


def test_scenario_editor_cards_embedded_with_script_escape_and_options():
    """⑤ cards 内嵌 window.__EDITOR_CARDS__（'</' 转义防提前闭 script）且
    正常卡/损坏卡都进目标下拉 option。"""
    block = edit_scenario_ui([_GOOD_CARD, _BROKEN_CARD])
    assert "window.__EDITOR_CARDS__" in block
    assert '"tone_demo"' in block and '"corrupt_one"' in block
    assert '<option value="tone_demo">tone_demo</option>' in block
    assert '<option value="corrupt_one">corrupt_one</option>' in block
    hostile = [{"name": "x</script>y", "desc": "", "style_tags": [], "risk": "low",
                "backend_hint": "sim"}]
    hostile_block = edit_scenario_ui(hostile)
    assert 'name": "x<\\/script>y"' in hostile_block  # JSON 内嵌已转义
    assert "x</script>y" not in hostile_block.split("window.__EDITOR_CARDS__", 1)[1]


def test_scenario_editor_cards_not_list_valueerror():
    """⑥ cards 非 list→ValueError 指错（空 list 合法——空态区块照常产出）。"""
    with pytest.raises(ValueError, match="cards"):
        edit_scenario_ui({"name": "not-a-list"})
    empty = edit_scenario_ui([])
    assert 'id="scenario-editor"' in empty
    target_select = empty.split('id="editor-target"', 1)[1].split("</select>", 1)[0]
    assert target_select.count("<option ") == 1  # 仅「— 新建 —」占位项，无场景选项


def test_scenario_editor_card_refresh_after_success():
    """⑦ 成功后刷新场景卡片：#editor-cards 视图+GET /api/scenarios 刷新路径在位。"""
    block = edit_scenario_ui([])
    assert 'id="editor-cards"' in block
    assert "refreshCards" in block
    assert "fetch('/api/scenarios')" in block
