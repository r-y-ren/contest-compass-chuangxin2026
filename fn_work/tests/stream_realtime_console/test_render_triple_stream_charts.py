"""render_triple_stream_charts 纯资产测试：结构+JS 关键行为以字符串/正则断言（无浏览器）。

覆盖口径（R58 L1）：
- 三 canvas id（chart-kpi/chart-spectrum/chart-events）与区块 id 在位；config
  定制项（标题/高度/缓冲长度）生效；缺省值合理（config=None 全缺省产出）；
- JS 行为骨架：/ws 同源连接（沿用 render_console_pages connectWS 构造）、
  type 关键字三路分发、未知帧 skipped 计数、断线横幅出现/消失+自动重连；
- 零外链（沿用 localize_console_assets 口径：实体解码后大小写不敏感
  http(s):// 子串+属性值形态协议相对 src="//"/href="//"）+零 Vue 依赖；
- ValueError：config 非 dict/未知键/标题非 str/缓冲长度与画布高度非正整数
  （bool 不算整数——isinstance(True, int) 为 True 须显式排掉）。
"""
import html
import json
import re

import pytest

from src.stream_realtime_console.render_triple_stream_charts import (
    CHARTS_SECTION_ID,
    render_triple_stream_charts,
)

#: 外链协议标记（大小写不敏感——与 localize_console_assets._EXTERNAL_PROTOCOL_RE 同口径）。
_EXTERNAL_PROTOCOL_RE = re.compile(r"https?://", re.IGNORECASE)

#: 属性值形态的协议相对外链（src="//…"、href="//"）。
_PROTO_RELATIVE_ATTR_RE = re.compile(r"""(?:src|href)\s*=\s*["']\s*//""", re.IGNORECASE)


@pytest.fixture()
def default_block() -> str:
    """config=None 的缺省产物（全缺省合理值口径的断言对象）。"""
    return render_triple_stream_charts()


# ---- 结构：区块 id+三 canvas id+缺省标题/高度+缺省缓冲注入 ----


def test_block_and_canvas_ids_in_place(default_block):
    """① 区块 id=triple-stream-charts 与三 canvas id（chart-kpi/chart-spectrum/chart-events）全部在位。"""
    assert f'id="{CHARTS_SECTION_ID}"' in default_block
    assert 'id="chart-kpi"' in default_block
    assert 'id="chart-spectrum"' in default_block
    assert 'id="chart-events"' in default_block
    # 三 canvas 均为 Canvas 2D 画布元素（非 img/svg 占位）
    for cid in ("chart-kpi", "chart-spectrum", "chart-events"):
        m = re.search(rf'<canvas id="{cid}"[^>]*>', default_block)
        assert m, f"canvas {cid} 缺失"


def test_default_titles_and_heights(default_block):
    """② 缺省标题出现于产物、缺省画布高度落在 canvas 标签（合理值非零）。"""
    assert "KPI 曲线（实时）" in default_block
    assert "频谱瀑布（实时）" in default_block
    assert "事件时间线（实时）" in default_block
    assert re.search(r'<canvas id="chart-kpi"[^>]*height="220"', default_block)
    assert re.search(r'<canvas id="chart-spectrum"[^>]*height="260"', default_block)
    assert re.search(r'<canvas id="chart-events"[^>]*height="140"', default_block)


def test_default_buffers_injected(default_block):
    """③ 缺省缓冲长度注入 window.__TSCHARTS_CONFIG__（滚动窗口/行数/标记数）。"""
    m = re.search(
        r"window\.__TSCHARTS_CONFIG__ = (\{.*?\});", default_block, re.DOTALL
    )
    assert m, "缓冲配置未注入 JS"
    cfg = json.loads(m.group(1))
    assert cfg == {"kpi_buffer": 600, "spectrum_rows": 128, "events_buffer": 40}


def test_config_customization_applies():
    """④ config 定制项生效：三标题/三高度/三缓冲长度全部落到产物。"""
    out = render_triple_stream_charts(
        {
            "kpi_title": "链路指标",
            "spectrum_title": "监测瀑布",
            "events_title": "注入事件轴",
            "kpi_height": 300,
            "spectrum_height": 180,
            "events_height": 90,
            "kpi_buffer": 120,
            "spectrum_rows": 32,
            "events_buffer": 8,
        }
    )
    for title in ("链路指标", "监测瀑布", "注入事件轴"):
        assert title in out
    assert re.search(r'<canvas id="chart-kpi"[^>]*height="300"', out)
    assert re.search(r'<canvas id="chart-spectrum"[^>]*height="180"', out)
    assert re.search(r'<canvas id="chart-events"[^>]*height="90"', out)
    m = re.search(r"window\.__TSCHARTS_CONFIG__ = (\{.*?\});", out, re.DOTALL)
    assert json.loads(m.group(1)) == {
        "kpi_buffer": 120,
        "spectrum_rows": 32,
        "events_buffer": 8,
    }
    # 定制后缺省标题不应再出现
    assert "KPI 曲线（实时）" not in out


def test_title_html_escaped_injection():
    """⑤ 标题含尖括号/引号→html.escape 注入不破标签（安全注入口径）。"""
    out = render_triple_stream_charts({"kpi_title": 'PER<"x">&RSSI'})
    assert "<h3>PER&lt;&quot;x&quot;&gt;&amp;RSSI</h3>" in out
    assert 'PER<"x">' not in out


# ---- JS 行为骨架：/ws 连接+三路分发+跳过计数+断线横幅 ----


def test_ws_connection_same_origin_convention(default_block):
    """⑥ /ws 连接沿用 render_console_pages connectWS 同源构造（https→wss 否则 ws，拼 location.host）。"""
    assert "new WebSocket(" in default_block
    assert "location.protocol === 'https:' ? 'wss:' : 'ws:'" in default_block
    assert "location.host + '/ws'" in default_block
    assert "'//'" in default_block  # proto + '//' + host + '/ws' 拼接形态


def test_dispatch_skeleton_by_type(default_block):
    """⑦ 三路分发骨架：type 关键字 kpi/spectrum/event 分支+急停通知帧红标分支。"""
    for keyword in ("kpi", "spectrum", "event", "emergency_stopped"):
        assert f"=== '{keyword}'" in default_block, f"type 分支 {keyword} 缺失"
    # JS 顶部登记帧协议（stream_realtime_console 接线依据）
    assert "帧协议：{" in default_block
    assert "'metrics'" in default_block
    assert "'powers_db'" in default_block
    assert "'label'" in default_block
    # KPI 帧消费 metrics 数值 → 折线；频谱帧消费 powers_db 数组 → 瀑布
    assert "drawKpi()" in default_block
    assert "drawSpectrum()" in default_block
    assert "drawEvents()" in default_block


def test_unknown_frame_skip_counter(default_block):
    """⑧ 未知帧类型→跳过计数：#tscharts-skipped 角标+skipped 递增并上屏。"""
    assert 'id="tscharts-skipped"' in default_block
    assert re.search(r"skipped \+= 1", default_block)
    assert re.search(r"skippedBox\.textContent", default_block)
    # 非 dict 帧（坏 JSON 解析失败）同样计入跳过，不中断流
    assert "markSkipped()" in default_block


def test_disconnect_banner_logic(default_block):
    """⑨ 断线→区块顶"已断线，重连中"横幅（hidden 出现/消失）+自动重连续画。"""
    assert 'id="tscharts-banner"' in default_block
    assert "已断线，重连中" in default_block
    assert "hidden" in default_block
    assert "banner.hidden = false" in default_block  # onclose：横幅出现
    assert "banner.hidden = true" in default_block  # onopen：重连成功横幅消失
    assert re.search(r"setTimeout\(connectWS, 2000\)", default_block)


def test_zero_vue_dependency(default_block):
    """⑩ 零 Vue 依赖：原生 JS+Canvas 2D 自足（无 Vue 全局/CDN 形态）。"""
    lowered = default_block.lower()
    assert "vue" not in lowered
    assert "getContext('2d')" in default_block


# ---- 零外链（沿用 localize_console_assets 口径） ----


@pytest.mark.parametrize(
    "label",
    ["default", "customized"],
)
def test_zero_external_links(label):
    """⑪ 产物零外链：实体解码后无 http(s):// 子串（大小写不敏感）、无属性值形态协议相对引用。"""
    out = (
        render_triple_stream_charts()
        if label == "default"
        else render_triple_stream_charts(
            {
                "kpi_title": "自定义 KPI",
                "spectrum_title": "自定义瀑布",
                "events_title": "自定义事件",
            }
        )
    )
    decoded = html.unescape(out)
    assert not _EXTERNAL_PROTOCOL_RE.search(decoded), "产物含 http(s) 外部资源引用"
    assert not _PROTO_RELATIVE_ATTR_RE.search(decoded), "产物含协议相对外链属性"


# ---- ValueError：config 非法形状 ----


@pytest.mark.parametrize(
    ("bad_config", "why"),
    [
        ("not-a-dict", "config 非 dict"),
        (42, "config 非 dict（数值）"),
        ([], "config 非 dict（list）"),
        ({"kpi_buffer": 0}, "缓冲长度非正整数（0）"),
        ({"spectrum_rows": -3}, "缓冲长度非正整数（负）"),
        ({"events_buffer": 2.5}, "缓冲长度非整数（浮点）"),
        ({"kpi_buffer": True}, "缓冲长度 bool 不算整数"),
        ({"kpi_buffer": "600"}, "缓冲长度非 int（str）"),
        ({"kpi_height": 0}, "画布高度非正整数（0）"),
        ({"spectrum_height": -100}, "画布高度非正整数（负）"),
        ({"events_height": 88.5}, "画布高度非整数（浮点）"),
        ({"kpi_title": 123}, "标题非 str"),
        ({"spectrum_title": "  "}, "标题空白串"),
        ({"unknown_key": 1}, "未知键"),
    ],
)
def test_invalid_config_valueerror(bad_config, why):
    """⑫ config 非法形状全家谱→ValueError 指错（不静默吞键/不落半产物）。"""
    with pytest.raises(ValueError, match="config"):
        render_triple_stream_charts(bad_config)


def test_none_config_is_legal():
    """⑬ config=None 合法（缺省产出），与缺省 fixture 同物。"""
    assert render_triple_stream_charts(None) == render_triple_stream_charts()
