"""render_console_pages 对抗测试：Vue CDN script+场景卡 JSON 内嵌+清单入口字样、
空目录空态、out_dir 落盘/不落盘、cards 计数、CDN 覆盖+http(s) 前缀消毒、
页面骨架标记、形状错 ValueError。
"""
from __future__ import annotations

import json
import re

import pytest

from src.render_console_pages.render_console_pages import render_console_pages

#: 内嵌卡片 JSON 注入行（正则可提取对拍：window.__CONSOLE_CARDS__ = [...];）。
_CARDS_LINE_RE = re.compile(r"window\.__CONSOLE_CARDS__ = (\[.*?\]);\n", re.DOTALL)


def _make_yaml(directory, name, text="style: tone\npower_dbm: -20\n"):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def test_console_ui_page_embeds_vue_cdn_cards_and_ledger_entry(tmp_path):
    """① 页面含 Vue CDN script（vue.global.prod.js/unpkg）+卡片 JSON 内嵌+清单入口字样。"""
    sdir = tmp_path / "scenarios"
    _make_yaml(sdir, "tone_demo.yaml", "# desc: 定频音\nstyle: tone\npower_dbm: -20\n")
    _make_yaml(sdir, "noise_mid.yaml", "style: noise\npower_dbm: -5\n")
    result = render_console_pages(str(sdir), {})
    html = result["pages"]["index.html"]
    assert "https://unpkg.com/vue@3/dist/vue.global.prod.js" in html
    assert "<script" in html and "vue.global.prod.js" in html
    assert "tone_demo" in html and "noise_mid" in html  # 场景卡 JSON 内嵌
    assert "清单完成度" in html  # 清单完成度入口字样
    assert result["assets"] == []  # 无 Node 构建——零本地资产


def test_console_ui_embedded_cards_json_parses(tmp_path):
    """② 内嵌 JSON 可解析：与目录内场景一一对应（name/risk 字段就位）。"""
    sdir = tmp_path / "scenarios"
    _make_yaml(sdir, "a.yaml", "# desc: 甲\nstyle: chirp\npower_dbm: -30\n")
    _make_yaml(sdir, "b.yaml", "style: noise\npower_dbm: -3\n")
    html = render_console_pages(str(sdir), {})["pages"]["index.html"]
    m = _CARDS_LINE_RE.search(html)
    assert m is not None
    cards = json.loads(m.group(1))
    by_name = {c["name"]: c for c in cards}
    assert set(by_name) == {"a", "b"}
    assert by_name["a"]["desc"] == "甲"
    assert by_name["b"]["risk"] == "mid"  # -3dBm 高于 -10 分档线


def test_console_ui_cards_count_and_non_yaml_ignored(tmp_path):
    """③ cards 计数=目录内 yaml 数，散文件（txt/py）不计入。"""
    sdir = tmp_path / "scenarios"
    _make_yaml(sdir, "one.yaml")
    _make_yaml(sdir, "two.yml")
    _make_yaml(sdir, "three.yaml")
    (sdir / "notes.txt").write_text("not a scenario", encoding="utf-8")
    result = render_console_pages(str(sdir), {})
    assert result["cards"] == 3
    assert "notes" not in result["pages"]["index.html"]


def test_console_ui_empty_dir_renders_empty_state(tmp_path):
    """④ 空目录→空态页面：cards=0、空态标记就位、内嵌 JSON 为空数组（不报错）。"""
    sdir = tmp_path / "empty"
    sdir.mkdir()
    result = render_console_pages(str(sdir), {})
    html = result["pages"]["index.html"]
    assert result["cards"] == 0
    assert isinstance(html, str) and html
    assert 'id="empty-state"' in html
    assert "暂无场景" in html
    assert "window.__CONSOLE_CARDS__ = [];" in html


def test_console_ui_missing_dir_renders_empty_state(tmp_path):
    """⑤ 目录不存在→同空态口径（cards=0，不抛）。"""
    result = render_console_pages(str(tmp_path / "nope"), {})
    assert result["cards"] == 0
    assert 'id="empty-state"' in result["pages"]["index.html"]


def test_console_ui_out_dir_writes_index_html(tmp_path):
    """⑥ out_dir 给定→落盘 index.html（内容与返回 str 一致，written 列路径）。"""
    sdir = tmp_path / "scenarios"
    _make_yaml(sdir, "tone_demo.yaml")
    out_dir = tmp_path / "out"
    result = render_console_pages(str(sdir), {"out_dir": str(out_dir)})
    written = result["written"]
    assert len(written) == 1 and written[0].endswith("index.html")
    page_file = out_dir / "index.html"
    assert page_file.exists()
    assert page_file.read_text(encoding="utf-8") == result["pages"]["index.html"]


def test_console_ui_without_out_dir_writes_nothing(tmp_path):
    """⑦ out_dir 缺省（None）→只返回 str 不落盘。"""
    sdir = tmp_path / "scenarios"
    _make_yaml(sdir, "tone_demo.yaml")
    result = render_console_pages(str(sdir), {})
    assert "written" not in result
    assert not (tmp_path / "index.html").exists()


def test_console_ui_cdn_base_override(tmp_path):
    """⑧ config['cdn_base'] 覆盖缺省 unpkg（内网镜像换源）。"""
    sdir = tmp_path / "scenarios"
    _make_yaml(sdir, "tone_demo.yaml")
    html = render_console_pages(
        str(sdir), {"cdn_base": "https://cdn.example.com"}
    )["pages"]["index.html"]
    assert "https://cdn.example.com/vue@3/dist/vue.global.prod.js" in html
    assert "unpkg.com" not in html


def test_console_ui_page_skeleton_markers(tmp_path):
    """⑨ 页面骨架标记：场景卡网格/滑杆/状态区/报告中心/清单入口/WS 图区+Canvas+
    断线重连横幅一应俱全。"""
    sdir = tmp_path / "scenarios"
    _make_yaml(sdir, "tone_demo.yaml")
    html = render_console_pages(str(sdir), {})["pages"]["index.html"]
    assert 'id="scenario-grid"' in html
    assert 'id="param-sliders"' in html and 'type="range"' in html
    assert 'id="status-panel"' in html
    assert 'id="report-center"' in html
    assert 'id="ledger-entry"' in html
    assert 'id="ws-charts"' in html and "<canvas" in html  # Canvas 实时图区
    assert 'id="ws-banner"' in html and "自动重连" in html  # 断线横幅+自动重连
    assert "WebSocket" in html  # WS 连接逻辑就位


def test_console_ui_non_empty_page_has_no_empty_state(tmp_path):
    """⑩ 空态块互斥注入：有卡片时页面不含 empty-state（空态仅 cards=0 出现）。"""
    sdir = tmp_path / "scenarios"
    _make_yaml(sdir, "tone_demo.yaml")
    html = render_console_pages(str(sdir), {})["pages"]["index.html"]
    assert 'id="empty-state"' not in html


@pytest.mark.parametrize("bad_config", [None, "opts", 42])
def test_console_ui_config_not_dict_valueerror(tmp_path, bad_config):
    """⑪ config 非 dict→ValueError。"""
    with pytest.raises(ValueError, match="config"):
        render_console_pages(str(tmp_path), bad_config)


def test_console_ui_scenario_dir_not_str_valueerror(tmp_path):
    """⑫ scenario_dir 非 str（int/list）→ValueError。"""
    with pytest.raises(ValueError, match="scenario_dir"):
        render_console_pages(123, {})


def test_console_ui_bad_out_dir_type_valueerror(tmp_path):
    """⑬ out_dir 非 str|None（空串/数字）→ValueError。"""
    with pytest.raises(ValueError, match="out_dir"):
        render_console_pages(str(tmp_path), {"out_dir": ""})
    with pytest.raises(ValueError, match="out_dir"):
        render_console_pages(str(tmp_path), {"out_dir": 7})


@pytest.mark.parametrize(
    "evil_cdn",
    [
        "javascript:alert(1)",  # 脚本注入载体
        "data:text/html;base64,e2g6MX0=",  # data 伪协议
        "ftp://cdn.example.com",  # 非 http(s) scheme
        "//evil.example.com",  # 协议相对（继承页面协议，可被降级利用）
        "evil.example.com/vue",  # 裸主机名（src 变相对路径）
    ],
)
def test_console_ui_cdn_base_scheme_sanitized_valueerror(tmp_path, evil_cdn):
    """⑭（B19 对抗低#6）CDN 消毒：cdn_base 非 https://|http:// 前缀→ValueError
    （<script src> 注入源只放行 http(s)）。"""
    with pytest.raises(ValueError, match="cdn_base"):
        render_console_pages(str(tmp_path), {"cdn_base": evil_cdn})


def test_console_ui_cdn_base_http_mirror_allowed(tmp_path):
    """⑮ http:// 内网镜像前缀放行（与 https 等权的换源口径）。"""
    sdir = tmp_path / "scenarios"
    _make_yaml(sdir, "tone_demo.yaml")
    html = render_console_pages(
        str(sdir), {"cdn_base": "http://mirror.intra"}
    )["pages"]["index.html"]
    assert "http://mirror.intra/vue@3/dist/vue.global.prod.js" in html


def test_console_ui_start_run_polls_run_status_to_completion(tmp_path):
    """阻断①(c) 回归：startRun 提交后轮询 /api/runs/{id}（1s 间隔、上限 120s），
    提交即提示「运行中…」；完成时状态区 run-result 行显示 status/failure_levels/
    report 路径（可复制文本，非超链接）。"""
    result = render_console_pages(str(tmp_path), {})
    html = result["pages"]["index.html"]
    assert "async pollRun(runId)" in html  # 轮询协程就位（startRun 提交后驱动）
    assert "'/api/runs/' + runId" in html  # 轮询目标端点（run_id 拼接）
    assert "setTimeout(resolve, 1000)" in html  # 1s 轮询间隔
    assert "120000" in html  # 轮询上限 120s（超时提示转报告中心）
    assert "运行中…" in html  # 提交即提示（不再止步「已提交」）
    assert 'id="run-result"' in html  # 状态区结果行挂载点
    assert "failure_levels" in html and "report_path" in html  # 结果行字段
    assert "运行完成" in html  # 终态回显（done/failed 两分支文案）
    assert "运行失败" in html


def test_console_ui_emergency_stop_four_branch_copy_true_values_first(tmp_path):
    """⑯ B24 观察③（B31 随批）：急停按钮四分支文案字符串级在位——按
    /api/stop 响应真值分流（emergency_stop.transmit.status 优先），不虚报
    「发射已停」；分支序=异常/已停/无后端/兜底（含网络失败 catch）。"""
    html = render_console_pages(str(tmp_path), {})["pages"]["index.html"]
    assert 'id="emergency-stop"' in html  # 急停按钮锚点
    assert "fetch('/api/stop'" in html  # 接线端点
    copy_pairs = [
        ("es.status === 'stop_failed'", "急停异常（发射侧失败，旗已置位）"),
        ("tx.status === 'stopped'", "急停已执行（发射已停）"),
        ("tx.status === 'no_backend'", "急停旗已置（当前无发射后端在途）"),
    ]
    for condition, copy in copy_pairs:
        assert condition in html, condition  # 分流条件（真值优先）
        assert copy in html, copy  # 对应文案原文
    # 兜底分支双文案+网络失败 catch（四分支+异常路径全覆盖）
    assert "急停旗已置" in html and "急停请求发送（无在途发射）" in html
    assert "急停失败: " in html
    # 真值优先于兜底：stop_failed 分流先于 transmit 状态分流
    assert html.index("es.status === 'stop_failed'") < html.index(
        "tx.status === 'stopped'"
    )
