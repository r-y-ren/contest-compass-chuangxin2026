"""操控台资产本地化与七页骨架产出：Vue3 生产版单文件 vendor 落盘+/pages 托管+零外链断言（断网全可用）——重写规约与签名意图详见 fn_docs/responsibility.md。

产出口径（R56 L0）：
- vendor 落盘：Vue3 生产版单文件（仓内 src/localize_console_assets/vendor/
  vue.global.prod.js，与 mount_console_extensions.VENDOR_VUE_PATH 同锚定）复制到
  ``assets_dir/vendor/vue.global.prod.js``；vendor_source 传入时以它为源（测试/
  迁移用），缺省用仓内文件；源缺失→ConsoleAssetError（禁静默回退 CDN——断网全
  可用红线）。
- 七页骨架：dict[slug, html]（键即七页 slug：overview/index/reports/data/ai/
  instruments/ledger，序即导航产出序）。每页为完整 HTML 文档：render_console_navigation
  骨架（顶部导航+页标识+mounts 占位容器）+本地 vendor script（指 /assets/vendor/
  vue.global.prod.js，由 mount_console_extensions 注册的路由托管）。运行页 index
  不产 mounts 容器（真实内容归 render_console_pages，由 serve_console 装配后经
  replace_cdn_with_vendor 切本地 vendor——本模块不收 scenario_dir，不越权渲染）。
- 各页 mounts 占位（R57–R74 各块挂内容，本模块不产区块内容）：总览 backend/
  clock/ledger/recent-runs；报告 run-list/report-view/comparison；数据 dataset-grid/
  filters；AI train-panel/eval-panel/infer-panel；仪表 instrument-panels/visa-status；
  台账 audit-report/ledger-detail。
- 零外链断言：每个产出页断言无 http(s) 外部资源引用（html.unescape 实体解码后
  大小写不敏感匹配 http:///https:// 子串+属性值形态协议相对——大写/HTML 实体编码/
  协议相对三种旁路变体同判违规，与 render_console_navigation 测试同纪律的宁严勿漏）。
  协议相对形态四类全覆盖（定向复审 Minor 收尾）：引号属性值 src="//"/href="//"、
  无引号属性值 src=//、资源属性集（srcset/action/poster/formaction/background/
  cite/data）="…"、CSS url(//…（style 块/属性内——简单口径：页面产物里出现
  url(// 即拒，自产模板不该有），发现即 ConsoleAssetError。
- replace_cdn_with_vendor(html)->str：把 render_console_pages 产出的 Vue3 CDN
  script 引用（<script src="https?://…/vue@3/dist/vue.global.prod.js"></script>
  形态，大小写不敏感——HTTPS:// 等大写变体同被替换；cdn_base 可换源故前缀宽容）
  替换为本地 vendor 路由，替换后复查零外链——残留外链（CDN script 形态之外的
  外部引用，含协议相对/大写/实体编码变体）→ConsoleAssetError（不静默放行）。
"""
import html
import os
import re
import shutil
from pathlib import Path

from .mount_console_extensions import VENDOR_VUE_ROUTE
from .render_console_navigation import render_console_navigation

__all__ = [
    "ConsoleAssetError",
    "PAGE_SLUGS",
    "VENDOR_SCRIPT_TAG",
    "localize_console_assets",
    "replace_cdn_with_vendor",
]

#: 仓内 vendor 源文件（模块同级 vendor/——与 mount_console_extensions.VENDOR_VUE_PATH
#: 同锚定；运行时经模块全局名引用，测试可 monkeypatch 模拟文件被移走）。
_REPO_VENDOR_PATH = Path(__file__).resolve().parent / "vendor" / "vue.global.prod.js"

#: 页内 Vue3 本地 script 标签（指向 mount_console_extensions 注册的 vendor 路由）。
VENDOR_SCRIPT_TAG = f'<script src="{VENDOR_VUE_ROUTE}"></script>'

#: 七页 slug 全集（序即产出序，与 render_console_navigation 导航序一致）。
PAGE_SLUGS = ("overview", "index", "reports", "data", "ai", "instruments", "ledger")

#: 各页 <title> 用的中文名（与 render_console_navigation 导航标签同源对齐）。
_PAGE_TITLES = {
    "overview": "总览",
    "index": "运行",
    "reports": "报告",
    "data": "数据",
    "ai": "AI",
    "instruments": "仪表",
    "ledger": "台账",
}

#: 各页 mounts 占位（{挂载点id: 说明}；index 为空 dict→不产容器，运行页真实内容
#: 归 render_console_pages/serve_console 装配）。
_PAGE_MOUNTS = {
    "overview": {
        "backend": "后端链路状态",
        "clock": "时钟状态",
        "ledger": "清单完成度",
        "recent-runs": "最近运行列表",
    },
    "index": {},
    "reports": {
        "run-list": "运行报告列表",
        "report-view": "报告阅读视图",
        "comparison": "跨轮对比视图",
    },
    "data": {
        "dataset-grid": "数据集卡片网格",
        "filters": "数据筛选器",
    },
    "ai": {
        "train-panel": "训练面板",
        "eval-panel": "评估面板",
        "infer-panel": "推理面板",
    },
    "instruments": {
        "instrument-panels": "仪表面板组",
        "visa-status": "VISA 连接状态",
    },
    "ledger": {
        "audit-report": "审计报告",
        "ledger-detail": "台账明细",
    },
}

#: Vue3 CDN script 引用形态（render_console_pages 恒以
#: cdn_base.rstrip('/') + '/vue@3/dist/vue.global.prod.js' 注入 __CDN_URL__——
#: 前缀随 config['cdn_base'] 变，尾部路径固定，故正则仅锚定尾部确切形态；
#: 大小写不敏感——HTTPS://…/VUE@3/… 等大写变体同样命中换源，不因大小写漏过
#: 后被零外链断言整体拒绝）。
_CDN_SCRIPT_RE = re.compile(
    r'<script src="https?://[^"]*/vue@3/dist/vue\.global\.prod\.js"></script>',
    re.IGNORECASE,
)

#: 外链协议标记（大小写不敏感：HTTP:///HTTPS:// 与混合大小写同违规）。
_EXTERNAL_PROTOCOL_RE = re.compile(r"https?://", re.IGNORECASE)

#: 协议相对外链的属性名全集（src/href 之外纳入资源属性：srcset/action/poster/
#: formaction/background/cite/data——定向复审 Minor 四形态收尾；只认属性值形态，
#: 注释/正文里的 "//" 字样不误杀；大小写不敏感覆盖 SRC=/HREF= 等，容忍 = 与
#: 引号间空白）。
_PROTO_RELATIVE_ATTRS = "src|href|srcset|action|poster|formaction|background|cite|data"

#: 属性值形态的协议相对外链（引号与无引号两态通吃：``src="//…"``/``src=//…``——
#: 引号可选，无引号形态以属性名前缀锚定、不误杀正文文本）。
_PROTO_RELATIVE_ATTR_RE = re.compile(
    rf"""(?:{_PROTO_RELATIVE_ATTRS})\s*=\s*(?:["']\s*)?//""", re.IGNORECASE
)

#: CSS url() 协议相对形态（style 块/style 属性内——简单口径：页面产物里出现
#: url(// 即拒，自产模板不该有；大小写不敏感覆盖 URL(//，容忍 url( 与 // 间空白）。
_CSS_URL_PROTO_RE = re.compile(r"url\(\s*//", re.IGNORECASE)

#: 单文件页面骨架文档：__TITLE__/__NAV_HTML__ 两令牌 str.replace 注入（不用
#: format——避免与后续区块模板花括号冲突，与 render_console_pages 同手法）。
_PAGE_DOC_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
body { font-family: system-ui, sans-serif; margin: 0 auto; max-width: 1080px; color: #1c2333; }
.console-nav { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; padding: 4px 0 8px; border-bottom: 2px solid #2c5aa0; }
.nav-menu { display: flex; flex-wrap: wrap; gap: 4px; margin: 0; padding: 0; list-style: none; }
.nav-link { padding: 2px 10px; border-radius: 4px; text-decoration: none; color: #2c5aa0; }
.nav-link.active { background: #2c5aa0; color: #fff; font-weight: bold; }
.page-identity { color: #6b7486; font-size: 13px; }
.page-container { margin: 12px 0; }
.block-mount { margin: 10px 0; padding: 14px; border: 1px dashed #c9d4e4; border-radius: 6px; color: #6b7486; }
.block-mount::before { content: "区块占位：" attr(data-mount); font-size: 13px; }
</style>
</head>
<body>
__NAV_HTML__
<script src="/assets/vendor/vue.global.prod.js"></script>
<script>
(function () {
  // 离线就绪标记：本地 vendor 真实装载后把 Vue 版本号记入页标识 data-vue
  // （e2e/调试一眼可辨；vendor 缺失时不置位、不产生 console error）。
  var identity = document.getElementById('page-identity');
  if (identity && window.Vue) { identity.setAttribute('data-vue', window.Vue.version); }
})();
</script>
</body>
</html>
"""


class ConsoleAssetError(RuntimeError):
    """操控台资产本地化失败：vendor 源缺失/落盘失败，或产出页残留外部资源引用。"""


def _assert_no_external_links(page_html: str, context: str) -> None:
    """零外链断言：命中即 ConsoleAssetError（R56 断网全可用红线，不静默放行）。

    判定口径（宁严勿漏，与 render_console_navigation 测试同纪律）：
    - 先 html.unescape 实体解码再匹配——``https&#x3a;//…`` 等编码形态无处遁形；
    - http:///https:// 子串判定大小写不敏感（HTTP:///HTTPS:// 同违规——文本/
      注释里的外链字样同样算违规，骨架与模板自产内容可控）；
    - 协议相对 ``//`` 只认属性值形态（src/href/srcset/action/poster 等资源属性，
      引号与无引号两态——无引号形态以属性名前缀锚定，避免误杀注释/正文里的
      "//" 字样），属性名大小写不敏感；
    - CSS url(//…（style 块/属性内）同拒——自产模板不该有该形态。
    """
    decoded = html.unescape(page_html)
    protocol_hit = _EXTERNAL_PROTOCOL_RE.search(decoded)
    if protocol_hit:
        raise ConsoleAssetError(
            f"页面含外部资源引用（{protocol_hit.group(0)}…，R56 断网全可用红线：零外链）"
            f"——{context}"
        )
    relative_hit = _PROTO_RELATIVE_ATTR_RE.search(decoded)
    if relative_hit:
        raise ConsoleAssetError(
            f"页面含协议相对外部资源引用（{relative_hit.group(0)}…，"
            f"R56 断网全可用红线：零外链）——{context}"
        )
    css_hit = _CSS_URL_PROTO_RE.search(decoded)
    if css_hit:
        raise ConsoleAssetError(
            f"页面含协议相对 CSS url() 引用（{css_hit.group(0)}…，"
            f"R56 断网全可用红线：零外链）——{context}"
        )


def replace_cdn_with_vendor(page_html: str) -> str:
    """把页面中的 Vue3 CDN script 引用替换为本地 vendor 路由（替换后复查零外链）。

    供 serve_console 装配复用：render_console_pages 产出的 index 运行页（Vue3
    走 CDN）经本函数切到 /assets/vendor/vue.global.prod.js 后即断网全可用。

    Args:
        page_html: 完整页面 HTML str（含 ``<script src="https?://…/vue@3/dist/
            vue.global.prod.js"></script>`` 形态的 CDN 引用；前缀随
            render_console_pages 的 config['cdn_base'] 可变）。

    Returns:
        替换后的 HTML str：全部 CDN script 引用换为本地 vendor 路由标签。

    Raises:
        ValueError: page_html 非 str。
        ConsoleAssetError: 替换后仍残留外部资源引用（CDN 形态之外的外链——
            无法本地化，不静默放行）。
    """
    if not isinstance(page_html, str):
        raise ValueError(
            f"page_html 必须为 str（完整页面 HTML），实际 {type(page_html).__name__}: "
            f"{page_html!r}"
        )
    replaced = _CDN_SCRIPT_RE.sub(VENDOR_SCRIPT_TAG, page_html)
    # 复查零外链：CDN script 之外的残留外链（其他外部 script/样式/图片）无法
    # 本地化——如实报错，禁止静默放行（R56 禁回退 CDN 红线）。
    _assert_no_external_links(replaced, "replace_cdn_with_vendor 替换后复查")
    return replaced


def _validate_assets_dir(assets_dir: object) -> str:
    """assets_dir 形状校验：非空 str→原样返回，否则 ValueError。"""
    if not isinstance(assets_dir, str) or not assets_dir:
        raise ValueError(
            f"assets_dir 必须为非空 str 路径（vendor 落盘目标目录），实际 "
            f"{assets_dir!r}"
        )
    return assets_dir


def _validate_vendor_source(vendor_source: object):
    """vendor_source 形状校验：None 或非空 str→放行，否则 ValueError。"""
    if vendor_source is None:
        return None
    if not isinstance(vendor_source, str) or not vendor_source:
        raise ValueError(
            f"vendor_source 须为非空 str 文件路径|None（None=用仓内 vendor），实际 "
            f"{vendor_source!r}"
        )
    return vendor_source


def _validate_pages(pages: object) -> "list[str]":
    """pages 形状校验：None→七页全集；list 内逐条须为已知 slug（未知→ValueError）；
    重复条目去重。返回按导航产出序排列的去重 slug 列表（输出序与传入序无关，
    恒定 canonical——对 /pages 托管方与调用方都可预期）。"""
    if pages is None:
        return list(PAGE_SLUGS)
    if not isinstance(pages, list):
        raise ValueError(
            f"pages 必须为 list[str]|None（七页 slug 子集），实际 "
            f"{type(pages).__name__}: {pages!r}"
        )
    if not pages:
        raise ValueError("pages 不能为空列表（至少一个七页 slug，或 None=全集）")
    selected = set()
    for slug in pages:
        if not isinstance(slug, str) or slug not in _PAGE_TITLES:
            raise ValueError(
                "pages 条目必须为七页 slug 之一"
                "（overview/index/reports/data/ai/instruments/ledger），"
                f"实际 {slug!r}"
            )
        selected.add(slug)
    return [slug for slug in PAGE_SLUGS if slug in selected]


def _materialize_vendor(assets_dir: str, vendor_source) -> None:
    """vendor 落盘：源文件（vendor_source 或仓内默认）→ assets_dir/vendor/
    vue.global.prod.js。源缺失→ConsoleAssetError；落盘 IO 失败→ConsoleAssetError。"""
    src = Path(vendor_source) if vendor_source is not None else _REPO_VENDOR_PATH
    if not src.is_file():
        raise ConsoleAssetError(
            f"vendor 资产缺失: {src}（Vue3 生产版单文件 vue.global.prod.js 须在位；"
            "禁止静默回退 CDN——R56 断网全可用红线）"
        )
    dst = Path(assets_dir) / "vendor" / "vue.global.prod.js"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not (dst.exists() and os.path.samefile(src, dst)):  # 同文件不自我覆写
            shutil.copyfile(src, dst)
    except OSError as exc:
        raise ConsoleAssetError(f"vendor 落盘失败: {src} → {dst}（{exc}）") from exc


def localize_console_assets(assets_dir: str, vendor_source: str | None = None, pages: list[str] | None = None) -> dict:
    """操控台资产本地化与七页骨架产出：Vue3 生产版单文件 vendor 落盘+/pages 托管+零外链断言（断网全可用）（详见 fn_docs/responsibility.md 功能块）。

    Args:
        assets_dir: 资产目标目录——vendor 落盘到 ``<assets_dir>/vendor/
            vue.global.prod.js``（目录不存在则创建；/pages 静态托管由调用方把
            返回页面字典并入 static_pages，vendor 的 HTTP 服务由
            mount_console_extensions 注册的 /assets/vendor 路由承担）。
        vendor_source: 可选 vendor 源文件路径（测试/迁移用；缺省 None=仓内
            src/localize_console_assets/vendor/vue.global.prod.js）。
        pages: 可选页 slug 子集（缺省 None=七页全集；未知 slug→ValueError；
            输出恒按导航产出序排列）。

    Returns:
        dict[slug, html]——七页（或 pages 子集）完整 HTML 文档骨架：导航条+页
        标识+mounts 占位容器（index 除外）+本地 vendor script。每页零外链
        （断网全可用）。

    Raises:
        ValueError: assets_dir/vendor_source/pages 形状不符（非 str、pages 条目
            未知、空列表等）。
        ConsoleAssetError: vendor 源缺失或落盘失败 / 产出页残留外部资源引用
            （禁静默回退 CDN）。
    """
    assets_dir = _validate_assets_dir(assets_dir)
    vendor_source = _validate_vendor_source(vendor_source)
    selected = _validate_pages(pages)

    _materialize_vendor(assets_dir, vendor_source)

    result: dict = {}
    for slug in selected:
        doc = (
            _PAGE_DOC_TEMPLATE.replace("__TITLE__", f"rf-console 操控台·{_PAGE_TITLES[slug]}")
            .replace("__NAV_HTML__", render_console_navigation(slug, _PAGE_MOUNTS[slug]))
        )
        _assert_no_external_links(doc, f"七页骨架 {slug}")
        result[slug] = doc
    return result
