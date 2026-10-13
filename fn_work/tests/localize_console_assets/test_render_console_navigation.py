"""render_console_navigation 对抗测试：七页导航链接序+当前页高亮唯一（active/
aria-current）、页标识 data-page+中文名、mounts 占位 div（id 即键+属性消毒）、
mounts 缺省不产容器（运行页复用既有 index 区块口径）、未知页名/mounts 形状错
ValueError、零外链断言（断网全可用）、wired 调用点回归（render_console_pages
的 index 页嵌导航条+页标识，Vue3 CDN script 不动）。
"""
import re

import pytest

from src.localize_console_assets.render_console_navigation import render_console_navigation

#: 七页 slug→中文名（对拍源；顺序即规约固定导航序）。
NAV_PAGES = {
    "overview": "总览",
    "index": "运行",
    "reports": "报告",
    "data": "数据",
    "ai": "AI",
    "instruments": "仪表",
    "ledger": "台账",
}


def test_nav_has_seven_links_in_spec_order():
    """① 七页链接齐且序固定：href=/pages/<slug>、中文标签逐一在位。"""
    html = render_console_navigation("overview")
    hrefs = re.findall(r'href="(/pages/[a-z]+)"', html)
    assert hrefs == [f"/pages/{slug}" for slug in NAV_PAGES]
    for label in NAV_PAGES.values():
        assert f">{label}</a>" in html


@pytest.mark.parametrize("page", list(NAV_PAGES))
def test_current_page_highlighted_exactly_once(page):
    """② 当前页高亮唯一：active class+aria-current 只落在当前页链接上，
    其余六页均为普通 nav-link。"""
    html = render_console_navigation(page)
    assert f'class="nav-link active" aria-current="page" href="/pages/{page}"' in html
    assert html.count("nav-link active") == 1
    assert html.count("aria-current") == 1
    for slug in NAV_PAGES:
        if slug != page:
            assert f'class="nav-link" href="/pages/{slug}"' in html


@pytest.mark.parametrize("page", list(NAV_PAGES))
def test_page_identity_marks_current_page(page):
    """③ 页标识：id=page-identity、data-page=<slug>、文案含当前页中文名。"""
    html = render_console_navigation(page)
    m = re.search(r'<div id="page-identity"[^>]*>', html)
    assert m is not None
    assert f'data-page="{page}"' in m.group(0)
    assert f"当前页：{NAV_PAGES[page]}" in html


def test_mounts_render_container_with_placeholder_divs():
    """④ mounts 给定→页面容器+逐占位 div：id 即键、说明入 data-mount。"""
    html = render_console_navigation(
        "reports", {"run-list": "运行摘要行", "compare-table": "跨轮对比表"}
    )
    assert (
        '<main id="page-reports" class="page-container" data-page="reports">' in html
    )
    assert 'id="run-list"' in html and 'data-mount="运行摘要行"' in html
    assert 'id="compare-table"' in html and 'data-mount="跨轮对比表"' in html
    assert html.count('class="block-mount"') == 2
    assert "</main>" in html  # 容器闭合


@pytest.mark.parametrize("no_mounts", [None, {}], ids=["none", "empty-dict"])
def test_no_mounts_no_container_but_nav_and_identity_remain(no_mounts):
    """⑤ mounts 缺省/空→不产页面容器（运行页 index 复用既有 render_console_pages
    区块，wired 调用点只嵌导航条+页标识），导航条与页标识仍在位。"""
    html = render_console_navigation("index", no_mounts)
    assert "<main" not in html and "block-mount" not in html
    assert 'id="console-nav"' in html and 'id="page-identity"' in html


def test_mount_id_and_desc_html_escaped():
    """⑥ 属性消毒：id/说明内引号/尖括号/& 经 html.escape，属性不可被截断逃逸。"""
    html = render_console_navigation("data", {'m"onmouseover="x': "<script>&"})
    assert 'id="m&quot;onmouseover=&quot;x"' in html
    assert 'data-mount="&lt;script&gt;&amp;"' in html
    assert "<script>" not in html  # 原样注入载体不出现


@pytest.mark.parametrize(
    "bad_page", ["runs", "", "Index", "overview/", "总览", 123, None]
)
def test_unknown_page_name_valueerror(bad_page):
    """⑦ 未知页名（含大小写不符/非 str）→ValueError，消息含七页 slug 域提示。"""
    with pytest.raises(ValueError, match="page_name"):
        render_console_navigation(bad_page)


@pytest.mark.parametrize("bad_mounts", [["a"], "a", 42])
def test_mounts_not_dict_valueerror(bad_mounts):
    """⑧ mounts 非 dict|None（list/str/int）→ValueError。"""
    with pytest.raises(ValueError, match="mounts"):
        render_console_navigation("overview", bad_mounts)


@pytest.mark.parametrize(
    "bad_mount",
    [{"": "说明"}, {7: "说明"}, {"ok": 42}, {"ok": None}],
    ids=["empty-id", "non-str-id", "non-str-desc", "none-desc"],
)
def test_mounts_item_shape_valueerror(bad_mount):
    """⑨ mounts 键非非空 str / 值非 str→ValueError（逐条指错，不静默转字符串）。"""
    with pytest.raises(ValueError, match="mounts"):
        render_console_navigation("overview", bad_mount)


@pytest.mark.parametrize("page", list(NAV_PAGES))
def test_output_zero_external_links(page):
    """⑩ 零外链：任一页输出（含 mounts 容器）不含 http(s) 外部资源引用
    （R56 断网全可用口径）。"""
    html = render_console_navigation(page, {"m1": "占位"})
    assert "http://" not in html and "https://" not in html


def test_wired_index_page_embeds_navigation(tmp_path):
    """⑪ wired 调用点回归（R56 改造点①）：render_console_pages 的 index 运行页
    头部嵌导航条+页标识（当前页=index 高亮），Vue3 CDN script 原样在位（本步不动）。"""
    from src.render_console_pages.render_console_pages import render_console_pages

    html = render_console_pages(str(tmp_path), {})["pages"]["index.html"]
    assert 'id="console-nav"' in html
    assert 'id="page-identity"' in html and 'data-page="index"' in html
    assert "当前页：运行" in html
    # 当前页高亮落在 /pages/index，且全页唯一
    assert 'class="nav-link active" aria-current="page" href="/pages/index"' in html
    assert html.count("nav-link active") == 1
    # 既有区块骨架不回归（运行页区块职责不变）
    assert 'id="scenario-grid"' in html and 'id="status-panel"' in html
    # Vue3 CDN script 标签本步不动
    assert "https://unpkg.com/vue@3/dist/vue.global.prod.js" in html
