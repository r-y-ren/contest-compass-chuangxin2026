"""report.md 服务端渲染为 HTML（markdown 库）：渲染层消毒（源转义+URL 方案守卫）+零外链+图片引用改指本服务 plots 端点——重写规约与签名意图详见 fn_docs/responsibility.md（R60 L1）。

产出口径（R60 L1，python markdown 库服务端渲染，不依赖浏览器 markdown 引擎）：
- XSS 消毒在渲染层自证安全（B25 C-1——不依赖上游字段白名单：恶意 style 等字段
  经 build_report 全链已在真实浏览器实证可执行，故渲染层自身兜底）：
  ① 源文本层：渲染前对 markdown 源做 HTML 转义（& < > → 实体）——markdown 库
     默认放行行内原始 HTML，先转义即令 ``<script>``/``onerror=``/``<svg
     onload=…>``/``srcdoc`` 恒为纯文本；markdown 自身语法不受影响（标题/表格/
     代码块/图片链接均不含这三种字符），行首 ``> `` 引用标记转义后还原
     （build_report 产 report.md 大量 '> ' 引用行——EMC/声明区/对比表口径）；
  ② 属性层：渲染后对生成 HTML 做 URL 方案守卫——所有 href/src（含 srcset/
     action 等资源属性，引号/无引号两态）仅放行非危险方案，javascript:/data:/
     vbscript: （大小写不敏感、剥空白/控制符后判定）一律替换为不可导航占位
     ``"#"``，srcdoc 属性整段剥离（正则后处理，零新依赖——markdown 原生链接
     ``[x](javascript:…)`` 是转义拦不住的活载体，须此层守卫）；
- 完整 HTML 文档（<!DOCTYPE html>+内联 <style>，无任何外部样式/脚本/字体引用）；
- 图片引用改写：report.md 的相对路径图片引用 ``![alt](plots/xxx.png)`` 在渲染前
  改写为本服务端点引用 ``/api/runs/{run_id}/plots/xxx.png``（build_report 产出的
  三元曲线图恒为该形态——站内可读，客户端无需知晓 run 目录盘上位置）；
- 零外链产物断言（与方案守卫互补——http(s)/协议相对外链仍是渲染错误而非消毒
  对象；口径沿用 localize_console_assets，宁严勿漏）：渲染产物经
  html.unescape 实体解码后大小写不敏感匹配 http(s):// 子串+属性值形态协议相对
  ``//`` 引用+CSS url(//——发现即 ValueError（不静默放行、不剥离外链改内容，
  报告若真含外部引用应在上游修，而不是渲染期掩耳盗铃）；
- 错误上抛（由端点转 500 带指错，R60 口径）：report_path 不存在/不是普通文件→
  ValueError；文件损坏（utf-8 解码失败）→ValueError 附原因；markdown 库缺失/
  渲染异常→原样上抛（ValueError 族）。本函数**不捕错不降级**——占位 report.md
  也只是普通 markdown 文本，照常渲染。
"""
import html as _html
import os
import re

import markdown as _markdown

__all__ = ["render_report_html", "REPORT_PLOTS_PREFIX"]

#: report.md 内图片相对路径前缀（build_report 三元曲线恒以 plots/ 引用落盘）。
REPORT_PLOTS_PREFIX = "plots/"

#: markdown 图片引用形态：![alt](plots/xxx.png)——alt 允许空、目标须以 plots/
#: 开头（相对路径图引用才改写；外链图引用不改写，交给零外链断言整体拒绝）。
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((plots/[^)\s]+)\)")

#: 外链协议标记（大小写不敏感：HTTP:///HTTPS:// 与混合大小写同违规——口径沿用
#: localize_console_assets._EXTERNAL_PROTOCOL_RE，本模块不导入它以保持叶子自足）。
_EXTERNAL_PROTOCOL_RE = re.compile(r"https?://", re.IGNORECASE)

#: 协议相对外链的属性名全集与属性值形态（引号与无引号两态通吃）。
_PROTO_RELATIVE_ATTRS = "src|href|srcset|action|poster|formaction|background|cite|data"
_PROTO_RELATIVE_ATTR_RE = re.compile(
    rf"""(?:{_PROTO_RELATIVE_ATTRS})\s*=\s*(?:["']\s*)?//""", re.IGNORECASE
)

#: CSS url() 协议相对形态（自产模板不该有，出现即拒）。
_CSS_URL_PROTO_RE = re.compile(r"url\(\s*//", re.IGNORECASE)

# ---- XSS 消毒层（B25 C-1：渲染层自证安全，不依赖上游字段白名单） ----

#: 源文本层：markdown 源 HTML 转义后，行首引用标记还原（build_report 产
#: report.md 的 '> ' 引用行——EMC/声明区/失效对比表全靠它成块；markdown 允许
#: 行首至多 3 空格前导）。还原仅限标记字符 '>' 本身——行内其余 '<' 已转义，
#: 引用块内容不构成注入面。
_SRC_ESCAPE_BLOCKQUOTE_RE = re.compile(r"^( {0,3})&gt;", re.MULTILINE)

#: 属性层：URL 类属性全集（引号/无引号两态通吃）——方案守卫的扫描面。
_URL_ATTR_VALUE_RE = re.compile(
    r"""\b(?P<attr>(?:href|src|srcset|action|formaction|poster|background|cite|data)\s*=\s*)"""
    r"""(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^\s>]*))""",
    re.IGNORECASE,
)

#: srcdoc 属性（内嵌 HTML 文档载荷）——任何形态整段剥离。
_SRCDOC_ATTR_RE = re.compile(
    r"""\bsrcdoc\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]*)""", re.IGNORECASE
)

#: 危险 URL 方案（大小写不敏感；data: 宁全勿漏——良性 data:image 同被换占位：
#: 产物图引用恒为 /api 端点相对路径，无 data: 需求）。
_DANGEROUS_SCHEME_RE = re.compile(r"^(?:javascript|data|vbscript):", re.IGNORECASE)

#: 浏览器 URL 方案解析前剥离的空白/控制符（"java\tscript:" 形态同判危险）。
_URL_NOISE_RE = re.compile(r"[\s\x00-\x1f\x7f]")

#: 危险方案属性值的替换占位（链接仍在、载荷死——不剥整个元素，保表格结构）。
_SAFE_URL_PLACEHOLDER = '"#"'


def _escape_markdown_source(md_text: str) -> str:
    """源文本层消毒：& < > → HTML 实体，行首引用标记还原（详见模块 docstring ①）。

    markdown 库默认放行行内原始 HTML——先转义即令 ``<script>``/``onerror=``/
    ``srcdoc`` 等一切标签形态恒为纯文本；markdown 自身语法（``#`` 标题、``|``
    表格、````` ````` 代码块、``![]()/[]()`` 图片链接）不含这三种字符，照常生成。
    """
    escaped = _html.escape(md_text, quote=False)
    return _SRC_ESCAPE_BLOCKQUOTE_RE.sub(
        lambda m: f"{m.group(1)}>", escaped
    )


def _neutralize_dangerous_urls(rendered_html: str) -> str:
    """属性层 URL 方案守卫：javascript:/data:/vbscript: → 不可导航占位，srcdoc 剥离。

    markdown 原生链接 ``[x](javascript:…)`` 经渲染生成活的 ``href="javascript:…"``
    ——这是源转义拦不住的载体（链接语法本身不含 & < >），须渲染后属性级守卫。
    判定口径与浏览器一致：值先经一次实体解码（浏览器属性解析语义）再剥空白/
    控制符、大小写不敏感匹配方案头。
    """
    no_srcdoc = _SRCDOC_ATTR_RE.sub("", rendered_html)

    def _guard(match: "re.Match[str]") -> str:
        value = match.group("dq")
        if value is None:
            value = (
                match.group("sq") if match.group("sq") is not None
                else match.group("bare")
            )
        probe = _URL_NOISE_RE.sub("", _html.unescape(value))
        if _DANGEROUS_SCHEME_RE.match(probe):
            return match.group("attr") + _SAFE_URL_PLACEHOLDER
        return match.group(0)

    return _URL_ATTR_VALUE_RE.sub(_guard, no_srcdoc)

#: 渲染产物文档模板：__TITLE__/__BODY__ 两令牌 str.replace 注入（不用 format——
#: 避免 markdown 产物花括号冲突，与 render_console_pages 同手法）；内联样式仅
#: 排版（表格边框/图宽自适应），零外链。
_DOC_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
body { font-family: system-ui, sans-serif; margin: 0 auto; max-width: 1080px; color: #1c2333; padding: 0 12px; }
h1, h2, h3 { color: #2c5aa0; }
table { border-collapse: collapse; margin: 10px 0; }
th, td { border: 1px solid #c9d4e4; padding: 4px 10px; }
th { background: #eef2f8; }
img { max-width: 100%; height: auto; }
code, pre { background: #f4f6fa; border-radius: 4px; }
pre { padding: 8px; overflow-x: auto; }
blockquote { margin: 8px 0; padding: 4px 12px; border-left: 4px solid #2c5aa0; background: #f4f6fa; color: #4a5265; }
</style>
</head>
<body>
__BODY__
</body>
</html>
"""


def _as_path_str(value: object, name: str) -> str:
    """路径规整：os.PathLike → str；非 str/PathLike → ValueError（消息附类型）。"""
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str):
        raise ValueError(
            f"{name} 必须为 str/os.PathLike 路径，实际 {type(value).__name__}: {value!r}"
        )
    return value


def _assert_no_external_links(page_html: str) -> None:
    """零外链产物断言（R60 口径沿用 localize_console_assets，宁严勿漏）。

    判定：html.unescape 实体解码后——①http(s):// 子串（大小写不敏感，文本/
    注释里的外链字样同违规）；②属性值形态协议相对 ``src="//…"``/``src=//…``
    （资源属性集，大小写不敏感）；③CSS ``url(//``。命中即 ValueError 附片段
    （由端点转 500 带指错——不静默放行也不剥离改写）。
    """
    decoded = _html.unescape(page_html)
    hit = _EXTERNAL_PROTOCOL_RE.search(decoded)
    if hit:
        raise ValueError(
            f"渲染产物含外部资源引用（{hit.group(0)}…，R60 零外链口径：报告若"
            f"引用外部资源应在上游修正，渲染期不掩耳盗铃）"
        )
    relative_hit = _PROTO_RELATIVE_ATTR_RE.search(decoded)
    if relative_hit:
        raise ValueError(
            f"渲染产物含协议相对外部资源引用（{relative_hit.group(0)}…，"
            f"R60 零外链口径）"
        )
    css_hit = _CSS_URL_PROTO_RE.search(decoded)
    if css_hit:
        raise ValueError(
            f"渲染产物含协议相对 CSS url() 引用（{css_hit.group(0)}…，"
            f"R60 零外链口径）"
        )


def render_report_html(report_path: str, run_id: str) -> str:
    """report.md 服务端渲染为 HTML（markdown 库）：零外链、图片引用改指本服务 plots 端点（详见 fn_docs/responsibility.md 功能块）。

    Args:
        report_path: report.md 路径（run_dir/report.md；不存在或不是普通文件
            →ValueError，由调用端点转错误响应）。
        run_id: 运行标识（run 目录名——用于把 ``plots/xxx.png`` 相对引用改写为
            ``/api/runs/{run_id}/plots/xxx.png`` 端点引用并入页面标题；含路径
            分隔符/``..``→ValueError（run_id 会嵌入 URL，穿越形态一律早拒））。

    Returns:
        完整 HTML 文档 str（<!DOCTYPE html>+内联样式+markdown 渲染正文；图片
        src 已指向 /api/runs/{run_id}/plots/ 端点；正文经渲染层消毒——源转义+URL
        方案守卫；产物经零外链断言）。

    Raises:
        ValueError: report_path 不存在/非普通文件/非 str 路径；run_id 非 str、
            空或含穿越形态（/、\\\\、..、绝对路径）；文件损坏（utf-8 解码失败）；
            渲染产物残留外部资源引用（零外链断言，宁严勿漏）。
    """
    report_path = _as_path_str(report_path, "report_path")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError(
            f"run_id 必须为非空 str（run 目录名，嵌入 plots 端点 URL），实际: {run_id!r}"
        )
    if (
        os.path.isabs(run_id)
        or "/" in run_id
        or "\\" in run_id
        or ".." in run_id
        or run_id in {".", ".."}
    ):
        raise ValueError(
            f"run_id 不得含路径分隔符或穿越形态（/、\\\\、..）: {run_id!r}"
            f"——run_id 会嵌入 /api/runs/{{run_id}}/plots/ URL"
        )
    if not os.path.isfile(report_path):
        raise ValueError(f"报告文件不存在: {report_path!r}")

    try:
        with open(report_path, encoding="utf-8") as handle:
            report_md = handle.read()
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"报告文件损坏（utf-8 解码失败）: {report_path!r}: {exc}"
        ) from exc

    # 图片引用改写（渲染前，markdown 源层）：plots/xxx.png → 端点引用。
    rewritten = _MD_IMAGE_RE.sub(
        lambda m: f"![{m.group(1)}](/api/runs/{run_id}/plots/"
        f"{m.group(2)[len(REPORT_PLOTS_PREFIX):]})",
        report_md,
    )

    # XSS 消毒（B25 C-1，渲染层自证安全）：
    # ① 源文本转义——markdown 库放行的行内原始 HTML 恒成纯文本（![]()/[]()
    #    链接语法不含 & < >，改写结果不受影响）；
    # ② markdown 渲染；
    # ③ 属性级 URL 方案守卫——原生链接生成的 javascript:/data:/vbscript: href
    #    换不可导航占位、srcdoc 剥离。
    safe_md = _escape_markdown_source(rewritten)
    body_html = _markdown.markdown(
        safe_md, extensions=["tables", "fenced_code"]
    )
    body_html = _neutralize_dangerous_urls(body_html)

    safe_run_id = _html.escape(run_id, quote=True)
    page_html = _DOC_TEMPLATE.replace(
        "__TITLE__", f"Run Report {safe_run_id}"
    ).replace("__BODY__", body_html)
    _assert_no_external_links(page_html)
    return page_html
