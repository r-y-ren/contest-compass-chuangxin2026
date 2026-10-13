"""localize_console_assets 对抗测试（用例名统一 test_console_offline_ 前缀——
`pytest -k console_offline` 整体发现本族，R56 核验命令口径）。

覆盖：vendor 落盘（仓内缺省源/vendor_source 覆盖/源缺失 ConsoleAssetError 禁回退
CDN/落盘 IO 失败）、七页骨架形状（导航条+页标识+title+完整文档）、六页 mounts
占位逐 id 在位、index 无容器（复用运行页区块口径）、每页本地 vendor script+
零外链、pages 子集（canonical 序/去重/未知 slug/形状错）、replace_cdn_with_vendor
（unpkg 缺省源/自定义镜像前缀/残留外链拒绝/干净直通/形状错）、仓内锚定与
mount_console_extensions 不漂移、serve_console 缺省装配七页经 /pages 托管+vendor
路由可达（R56 验收口径的 TestClient 侧证据）。

环境缺 fastapi（或 httpx）时 TestClient 族用例自动 skip。
"""
import re
from pathlib import Path

import pytest

import src.localize_console_assets.localize_console_assets as localize_mod
from src.localize_console_assets.localize_console_assets import (
    PAGE_SLUGS,
    VENDOR_SCRIPT_TAG,
    ConsoleAssetError,
    localize_console_assets,
    replace_cdn_with_vendor,
)
from src.localize_console_assets.mount_console_extensions import VENDOR_VUE_PATH

try:  # TestClient 同源依赖 fastapi+httpx——任一缺失即整族 skip
    from fastapi.testclient import TestClient

    _HAS_TESTCLIENT = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_TESTCLIENT = False

needs_fastapi = pytest.mark.skipif(
    not _HAS_TESTCLIENT, reason="环境缺 fastapi/httpx——TestClient 不可用"
)

#: 六页（除 index）各自应有的 mounts 占位 id 集（R56 规约枚举）。
SPEC_MOUNTS = {
    "overview": {"backend", "clock", "ledger", "recent-runs"},
    "reports": {"run-list", "report-view", "comparison"},
    "data": {"dataset-grid", "filters"},
    "ai": {"train-panel", "eval-panel", "infer-panel"},
    "instruments": {"instrument-panels", "visa-status"},
    "ledger": {"audit-report", "ledger-detail"},
}

#: 七页 slug→中文名（title/页标识对拍源）。
PAGE_LABELS = {
    "overview": "总览",
    "index": "运行",
    "reports": "报告",
    "data": "数据",
    "ai": "AI",
    "instruments": "仪表",
    "ledger": "台账",
}


# ---- vendor 落盘（缺省仓内源） ----


def test_console_offline_vendor_written_from_repo_default(tmp_path):
    """① 缺省调用：仓内 vue.global.prod.js 复制到 <assets_dir>/vendor/，
    逐字节一致（157924B 完整生产版体量）。"""
    result = localize_console_assets(str(tmp_path))
    written = tmp_path / "vendor" / "vue.global.prod.js"
    assert written.is_file()
    assert written.read_bytes() == VENDOR_VUE_PATH.read_bytes()
    assert written.stat().st_size == 157_924
    assert set(result) == set(PAGE_SLUGS)


def test_console_offline_repo_vendor_anchor_matches_mount_module():
    """② 仓内源锚定与 mount_console_extensions.VENDOR_VUE_PATH 同路径（两处锚定
    不漂移——vendor 路由服务的文件即本函数缺省复制的文件）。"""
    assert localize_mod._REPO_VENDOR_PATH == VENDOR_VUE_PATH


def test_console_offline_vendor_source_override_copied(tmp_path):
    """③ vendor_source 传入→以它为源落盘（测试/迁移路线），内容逐字节一致。"""
    src = tmp_path / "custom-vue.js"
    src.write_bytes(b"FAKE-VUE-3.5.13-PROD")
    localize_console_assets(str(tmp_path / "out"), vendor_source=str(src))
    written = tmp_path / "out" / "vendor" / "vue.global.prod.js"
    assert written.read_bytes() == b"FAKE-VUE-3.5.13-PROD"


@pytest.mark.parametrize("which", ["repo", "source"], ids=["repo-default", "source"])
def test_console_offline_missing_vendor_console_asset_error(tmp_path, monkeypatch, which):
    """④ vendor 缺失→ConsoleAssetError（禁静默回退 CDN）：仓内默认源被移走
    （monkeypatch 路径常量）或 vendor_source 指向不存在文件，消息都点名 vendor
    且声明不回退 CDN。"""
    absent = tmp_path / "gone" / "vue.global.prod.js"
    if which == "repo":
        monkeypatch.setattr(localize_mod, "_REPO_VENDOR_PATH", absent)
        with pytest.raises(ConsoleAssetError) as ei:
            localize_console_assets(str(tmp_path / "out"))
    else:
        with pytest.raises(ConsoleAssetError) as ei:
            localize_console_assets(
                str(tmp_path / "out"), vendor_source=str(absent)
            )
    assert "vendor" in str(ei.value)
    assert "CDN" in str(ei.value)  # 禁回退红线要在消息里可辨
    assert not (tmp_path / "out" / "vendor").exists() or not any(
        (tmp_path / "out" / "vendor").iterdir()
    )  # 缺源即不落任何产物


def test_console_offline_vendor_write_failure_console_asset_error(tmp_path):
    """⑤ 落盘 IO 失败（assets_dir 位置被同名文件挡住）→ConsoleAssetError 指明
    落盘失败，不静默。"""
    blocker = tmp_path / "vendor"
    blocker.write_text("not a dir", encoding="utf-8")
    with pytest.raises(ConsoleAssetError, match="落盘"):
        localize_console_assets(str(tmp_path))


# ---- 七页骨架形状 ----


def test_console_offline_seven_page_full_documents_in_nav_order(tmp_path):
    """⑥ 缺省产出：恰好七键且序=导航产出序；每页完整 HTML 文档（DOCTYPE/
    html/head/title）+导航条+页标识（data-page=<slug>+中文名）+title 含中文名。"""
    result = localize_console_assets(str(tmp_path))
    assert list(result) == list(PAGE_SLUGS)
    for slug in PAGE_SLUGS:
        doc = result[slug]
        assert doc.startswith("<!DOCTYPE html>")
        assert "<html lang=\"zh-CN\">" in doc and "</html>" in doc
        assert 'id="console-nav"' in doc
        assert f'data-page="{slug}"' in doc and f"当前页：{PAGE_LABELS[slug]}" in doc
        assert f"rf-console 操控台·{PAGE_LABELS[slug]}" in doc


@pytest.mark.parametrize("slug", sorted(SPEC_MOUNTS))
def test_console_offline_six_pages_have_spec_mounts(tmp_path, slug):
    """⑦ 六页 mounts 占位逐 id 在位（class=block-mount+id+data-mount 说明），
    数量与规约枚举一致。"""
    result = localize_console_assets(str(tmp_path))
    doc = result[slug]
    assert f'<main id="page-{slug}"' in doc
    mount_ids = set(re.findall(r'<div class="block-mount" id="([^"]+)"', doc))
    assert mount_ids == SPEC_MOUNTS[slug]
    for mid in mount_ids:
        assert f'data-mount=' in doc  # 每个占位都带说明属性


def test_console_offline_index_skeleton_no_mounts_container(tmp_path):
    """⑧ index 骨架不产 mounts 容器（运行页真实内容归 render_console_pages，
    serve_console 装配后覆盖）——导航条+页标识仍在。"""
    doc = localize_console_assets(str(tmp_path))["index"]
    assert "<main" not in doc and 'class="block-mount"' not in doc  # 无容器/无占位 div（CSS 规则声明不算）
    assert 'id="console-nav"' in doc and 'id="page-identity"' in doc
    assert 'data-page="index"' in doc


@pytest.mark.parametrize("slug", PAGE_SLUGS)
def test_console_offline_every_page_local_vendor_script_zero_external(tmp_path, slug):
    """⑨ 每页：本地 vendor script 标签在位（指 /assets/vendor 路由），且零外链
    （无 http(s) 外部资源引用——断网全可用红线）。"""
    doc = localize_console_assets(str(tmp_path))[slug]
    assert VENDOR_SCRIPT_TAG in doc
    assert doc.count('src="/assets/vendor/vue.global.prod.js"') == 1
    assert "http://" not in doc and "https://" not in doc


def test_console_offline_external_link_in_template_guard(tmp_path, monkeypatch):
    """⑩ 零外链断言的守卫分支：模板混入外链（monkeypatch 模板常量模拟回归）→
    ConsoleAssetError 如实指错，不放行。"""
    monkeypatch.setattr(
        localize_mod,
        "_PAGE_DOC_TEMPLATE",
        localize_mod._PAGE_DOC_TEMPLATE.replace(
            "</head>", '<link rel="stylesheet" href="https://evil.example/x.css"></head>'
        ),
    )
    with pytest.raises(ConsoleAssetError, match="外部资源引用"):
        localize_console_assets(str(tmp_path), pages=["overview"])


# ---- pages 参数 ----


def test_console_offline_pages_subset_canonical_order(tmp_path):
    """⑪ pages 子集：只产所选页，输出序恒为导航产出序（与传入序无关）。"""
    result = localize_console_assets(str(tmp_path), pages=["ledger", "overview"])
    assert list(result) == ["overview", "ledger"]


def test_console_offline_pages_duplicates_dedup(tmp_path):
    """⑫ 重复条目去重（单页单键）。"""
    result = localize_console_assets(str(tmp_path), pages=["ai", "ai"])
    assert list(result) == ["ai"]


@pytest.mark.parametrize(
    "bad", [["runs"], ["INDEX"], ["overview", "nope"], [123], [None], [""]], ids=[
        "unknown-slug", "case-mismatch", "one-unknown", "int-entry", "none-entry", "empty-str"
    ]
)
def test_console_offline_unknown_slug_valueerror(tmp_path, bad):
    """⑬ pages 含未知 slug（含大小写不符/非 str）→ValueError，消息列明合法域。"""
    with pytest.raises(ValueError, match="pages"):
        localize_console_assets(str(tmp_path), pages=bad)


@pytest.mark.parametrize("bad", ["overview", {"overview": 1}, 42, ("overview",)])
def test_console_offline_pages_shape_valueerror(tmp_path, bad):
    """⑭ pages 非 list[str]|None（str/dict/int/tuple）→ValueError。"""
    with pytest.raises(ValueError, match="pages"):
        localize_console_assets(str(tmp_path), pages=bad)


def test_console_offline_pages_empty_list_valueerror(tmp_path):
    """⑮ pages=[]（空列表）→ValueError（要么 None 全集要么非空子集）。"""
    with pytest.raises(ValueError, match="pages"):
        localize_console_assets(str(tmp_path), pages=[])


# ---- 参数形状：assets_dir / vendor_source ----


@pytest.mark.parametrize("bad", [None, "", 123])
def test_console_offline_assets_dir_shape_valueerror(bad):
    """⑯ assets_dir 非 str/空→ValueError。"""
    with pytest.raises(ValueError, match="assets_dir"):
        localize_console_assets(bad)


@pytest.mark.parametrize("bad", ["", 123])
def test_console_offline_vendor_source_shape_valueerror(tmp_path, bad):
    """⑰ vendor_source 非 str|None（空串/int）→ValueError。"""
    with pytest.raises(ValueError, match="vendor_source"):
        localize_console_assets(str(tmp_path), vendor_source=bad)


# ---- replace_cdn_with_vendor（serve_console 装配复用的替换函数） ----


def test_console_offline_replace_cdn_swaps_unpkg_default(tmp_path):
    """⑱ wired 形态回归：render_console_pages 默认 unpkg 源的 index 页→CDN
    script 换本地 vendor 路由，零外链，既有区块不回归。"""
    from src.render_console_pages.render_console_pages import render_console_pages

    raw = render_console_pages(str(tmp_path), {})["pages"]["index.html"]
    assert "https://unpkg.com/vue@3/dist/vue.global.prod.js" in raw  # 前置：确有 CDN
    out = replace_cdn_with_vendor(raw)
    assert VENDOR_SCRIPT_TAG in out
    assert "unpkg.com" not in out
    assert "http://" not in out and "https://" not in out  # 替换后复查零外链
    assert 'id="scenario-grid"' in out and 'id="status-panel"' in out  # 区块不动


def test_console_offline_replace_cdn_swaps_custom_mirror(tmp_path):
    """⑲ cdn_base 换内网镜像源→同样被替换（前缀宽容，尾部形态锚定）。"""
    from src.render_console_pages.render_console_pages import render_console_pages

    raw = render_console_pages(
        str(tmp_path), {"cdn_base": "https://mirror.internal/base/"}
    )["pages"]["index.html"]
    assert "https://mirror.internal/base/vue@3/dist/vue.global.prod.js" in raw
    out = replace_cdn_with_vendor(raw)
    assert VENDOR_SCRIPT_TAG in out and "mirror.internal" not in out
    assert "https://" not in out


def test_console_offline_replace_cdn_rejects_leftover_external():
    """⑳ CDN script 之外还残留其他外链→ConsoleAssetError（无法本地化，不静默
    放行）。"""
    html = (
        "<html><head>"
        '<script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>'
        '<script src="https://evil.example.com/payload.js"></script>'
        "</head><body>x</body></html>"
    )
    with pytest.raises(ConsoleAssetError, match="外部资源引用"):
        replace_cdn_with_vendor(html)


def test_console_offline_replace_cdn_clean_passthrough():
    """㉑ 无外链的干净页→原样直通（幂等：已本地化的页面再过一次不变）。"""
    html = f"<html><head>{VENDOR_SCRIPT_TAG}</head><body>骨架</body></html>"
    assert replace_cdn_with_vendor(html) == html


@pytest.mark.parametrize("bad", [None, 42, b"<html>"])
def test_console_offline_replace_cdn_shape_valueerror(bad):
    """㉒ page_html 非 str→ValueError。"""
    with pytest.raises(ValueError, match="page_html"):
        replace_cdn_with_vendor(bad)


# ---- serve_console 缺省装配（R56 验收：七页经 /pages 托管、断网可加载的
# TestClient 侧证据；浏览器侧证据在 test_console_pages_e2e.py） ----


@needs_fastapi
def test_console_offline_serve_console_default_seven_pages_hosted(tmp_path):
    """㉓ serve_console 未传 static_pages→七页产出注入 deps（键带 .html 后缀对齐
    /pages 无后缀回退），逐页 GET /pages/<slug> 200：index 为 render_console_pages
    真实运行页（区块在位）经 CDN→vendor 切换（无 unpkg），其余六页为骨架
    （导航+mounts）；vendor 路由 200 逐字节对拍仓内文件。"""
    from src.serve_console.serve_console import serve_console

    sdir = tmp_path / "scenarios"
    sdir.mkdir()
    rroot = tmp_path / "reports"
    rroot.mkdir()
    result = serve_console(
        {
            "scenario_dir": str(sdir),
            "report_root": str(rroot),
            "port": 18123,
            "dry_run": True,
            "runner": lambda scenario: {"echo": scenario},
            "stop_flag": {"flag": False},
        }
    )
    static_pages = result["app"].state.deps["static_pages"]
    assert set(static_pages) == {f"{slug}.html" for slug in PAGE_SLUGS}
    with TestClient(result["app"]) as client:
        for slug in PAGE_SLUGS:
            resp = client.get(f"/pages/{slug}")  # 无后缀→<slug>.html 回退
            assert resp.status_code == 200, slug
            assert 'id="console-nav"' in resp.text
            assert VENDOR_SCRIPT_TAG in resp.text
            assert "http://" not in resp.text and "https://" not in resp.text
        index = client.get("/pages/index.html").text
        assert 'id="scenario-grid"' in index and 'id="status-panel"' in index  # 真实运行页
        assert "unpkg.com" not in index
        overview = client.get("/pages/overview").text
        for mid in SPEC_MOUNTS["overview"]:
            assert f'id="{mid}"' in overview
        vendor = client.get("/assets/vendor/vue.global.prod.js")
    assert vendor.status_code == 200
    assert vendor.content == VENDOR_VUE_PATH.read_bytes()
    assert (sdir / "vendor" / "vue.global.prod.js").is_file()  # vendor 落盘目标目录
