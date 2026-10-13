"""七页骨架与导航条 HTML：统一顶部导航（当前页高亮）+区块挂载点，不含各功能区块内容——重写规约与签名意图详见 fn_docs/responsibility.md。

产出口径（R56 L1，纯 Python 字符串模板，无 Node/构建链）：
- 七页 slug→中文名（顺序即导航产出顺序）：overview→总览、index→运行、reports→报告、
  data→数据、ai→AI、instruments→仪表、ledger→台账；导航链接一律站内相对路径
  /pages/<slug>（零外链，断网全可用口径）；
- 当前页高亮：命中链接 class="nav-link active" 且 aria-current="page"（全导航唯一）；
- 页标识：<div id="page-identity" data-page="<slug>">当前页：<中文名></div>；
- mounts 给定（非空 dict）→ 追加页面容器 <main id="page-<slug>" ...>，容器内逐
  {挂载点id: 说明} 渲染 <div class="block-mount" id="..." data-mount="说明"></div>
  占位（id 即键，供 R57–R74 各块挂内容，本函数不产区块内容）；mounts 缺省 None/空
  dict→不产容器（运行页 index 复用既有 render_console_pages 页区块——wired 调用点
  只嵌导航条+页标识）；
- 挂载点 id/说明经 html.escape 消毒（防引号/尖括号截断属性注入载体）。
"""
import html

__all__ = ["render_console_navigation"]

#: 七页 slug→中文名（dict 序即导航产出顺序：总览/运行/报告/数据/AI/仪表/台账）。
_NAV_PAGES = {
    "overview": "总览",
    "index": "运行",
    "reports": "报告",
    "data": "数据",
    "ai": "AI",
    "instruments": "仪表",
    "ledger": "台账",
}

#: 导航链接前缀（站内相对路径 /pages/<slug>，无 http(s) 外链）。
_PAGES_PREFIX = "/pages/"


def _validate_page_name(page_name: object) -> str:
    """页名校验：非 str 或不在七页表→ValueError（消息列明合法 slug 域）。"""
    if not isinstance(page_name, str) or page_name not in _NAV_PAGES:
        raise ValueError(
            "page_name 必须为七页 slug 之一"
            "（overview/index/reports/data/ai/instruments/ledger），"
            f"实际收到 {type(page_name).__name__}: {page_name!r}"
        )
    return page_name


def _validate_mounts(mounts: object) -> dict:
    """挂载点形状校验：dict|None 且键=非空 str、值=str，否则 ValueError。"""
    if mounts is None:
        return {}
    if not isinstance(mounts, dict):
        raise ValueError(
            f"mounts 必须为 dict|None（{{挂载点id: 说明}}），实际 "
            f"{type(mounts).__name__}: {mounts!r}"
        )
    for mount_id, desc in mounts.items():
        if not isinstance(mount_id, str) or not mount_id:
            raise ValueError(
                f"mounts 键必须为非空 str 挂载点 id，实际 "
                f"{type(mount_id).__name__}: {mount_id!r}"
            )
        if not isinstance(desc, str):
            raise ValueError(
                f"mounts[{mount_id!r}] 说明必须为 str，实际 "
                f"{type(desc).__name__}: {desc!r}"
            )
    return dict(mounts)


def render_console_navigation(page_name: str, mounts: dict | None = None) -> str:
    """七页骨架与导航条 HTML：统一顶部导航（当前页高亮）+区块挂载点，不含各功能区块内容（详见 fn_docs/responsibility.md 功能块）。

    Args:
        page_name: 七页 slug（overview/index/reports/data/ai/instruments/ledger）。
        mounts: 可选 {挂载点id: 说明}——渲染为页面容器内 div 占位（id 即键，
            说明入 data-mount 属性），供后续批次挂内容；缺省 None→只产导航条+
            页标识（运行页 index 复用既有 render_console_pages 区块，不另产容器）。

    Returns:
        页面骨架 HTML 片段 str：`<nav id="console-nav">`（七链接，当前页
        class="nav-link active"+aria-current="page"）+ `<div id="page-identity"
        data-page="<slug>">`；mounts 非空时再附 `<main id="page-<slug>"
        class="page-container">` 容器与各 block-mount 占位 div。零外链（无
        http(s) 外部资源引用）。

    Raises:
        ValueError: page_name 未知（非七页 slug，含非 str）/ mounts 形状不符
            （非 dict|None、键非非空 str、值非 str）。
    """
    page_name = _validate_page_name(page_name)
    safe_mounts = _validate_mounts(mounts)

    links = []
    for slug, label in _NAV_PAGES.items():
        if slug == page_name:  # 当前页高亮：active class+aria-current（全导航唯一）
            links.append(
                f'<li><a class="nav-link active" aria-current="page" '
                f'href="{_PAGES_PREFIX}{slug}">{label}</a></li>'
            )
        else:
            links.append(
                f'<li><a class="nav-link" href="{_PAGES_PREFIX}{slug}">{label}</a></li>'
            )
    nav = (
        '<nav id="console-nav" class="console-nav" aria-label="操控台导航">\n'
        '  <ul class="nav-menu">\n    ' + "\n    ".join(links) + "\n  </ul>\n"
        "</nav>"
    )
    identity = (
        f'<div id="page-identity" class="page-identity" data-page="{page_name}">'
        f"当前页：{_NAV_PAGES[page_name]}</div>"
    )
    parts = [nav, identity]

    if safe_mounts:  # 占位容器仅在有挂载点时产出（运行页 index 复用既有区块）
        mount_divs = "\n    ".join(
            f'<div class="block-mount" id="{html.escape(mount_id)}" '
            f'data-mount="{html.escape(desc)}"></div>'
            for mount_id, desc in safe_mounts.items()
        )
        parts.append(
            f'<main id="page-{page_name}" class="page-container" '
            f'data-page="{page_name}">\n    {mount_divs}\n  </main>'
        )
    return "\n".join(parts)
