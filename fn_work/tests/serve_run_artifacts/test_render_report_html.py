"""render_report_html 对抗测试：markdown→HTML 服务端渲染（表格/标题）+plots 图片
引用改写为端点引用+零外链产物断言（外部图/链接/协议相对/CSS url 变体全拒）+
XSS 渲染层消毒回归（源转义+URL 方案守卫——B25 C-1 对抗实证过的全部形态）+
文件不存在/损坏/非 str 路径/非法 run_id 的 ValueError 上抛口径。

R60 L1 叶子——上游覆盖策略：本文件单测即 serve_run_artifacts 上游的主证据
（责任文档 tested 策略「上游覆盖: serve_run_artifacts」）。
"""
import html
import re
from html.parser import HTMLParser

import pytest

from src.build_report.build_report import build_report
from src.serve_run_artifacts.render_report_html import render_report_html

#: 三元曲线三 PNG 名（与 build_report._PNG_NAMES 对齐——真实 report.md 形态）。
_PNG_NAMES = (
    "curve_a_per_vs_level.png",
    "curve_b_throughput_vs_per.png",
    "curve_c_event_timeline.png",
)


def _write_report(tmp_path, text, name="report.md"):
    """落盘一份 report.md 文本，返回路径。"""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _real_report_md():
    """仿真 build_report 产出的 report.md 片段（概要表+三图引用+引用块）。"""
    lines = [
        "# Run Report（20261013-120000）",
        "",
        "## 运行概要",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        "| 后端 | sim |",
        "| kpi.csv | 存在，12 行 |",
        "",
        "## 三元曲线",
        "",
        "![图A：误包率–干扰电平](plots/curve_a_per_vs_level.png)",
        "",
        "![图B：相对吞吐–误包率](plots/curve_b_throughput_vs_per.png)",
        "",
        "![图C：事件时间线](plots/curve_c_event_timeline.png)",
        "",
        "> 引用行：口径脚注（数字纪律）。",
    ]
    return "\n".join(lines) + "\n"


# ---- XSS 渲染层消毒回归（B25 C-1）——活标记判定辅助 ----


class _LiveTagScanner(HTMLParser):
    """渲染产物活标记扫描器：HTMLParser 只报真实解析出的标签/属性——转义为
    文本的形态（&lt;script&gt;）不会出现在这里（决定性区分「活标签」与「文本」）。"""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.tags: "list[str]" = []
        self.attrs: "list[tuple[str, str | None]]" = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)

    handle_startendtag = handle_starttag  # <img … /> 自闭合同报


#: 产物合法标签白名单（模板骨架+markdown 生成集——产物标签面白名单化）。
_SAFE_TAGS = {
    "html", "head", "meta", "title", "style", "body",
    "h1", "h2", "h3", "h4", "h5", "h6", "p",
    "table", "thead", "tbody", "tr", "th", "td",
    "img", "a", "blockquote", "code", "pre",
    "em", "strong", "ul", "ol", "li", "hr", "br",
}

#: URL 类属性（与实现 _URL_ATTR_VALUE_RE 扫描面同集）。
_URL_ATTRS = (
    "href", "src", "srcset", "action", "formaction",
    "poster", "background", "cite", "data",
)

_DANGEROUS_SCHEME_RE = re.compile(
    r"^(?:javascript|data|vbscript):", re.IGNORECASE
)
_URL_NOISE_RE = re.compile(r"[\s\x00-\x1f\x7f]")


def _assert_no_live_xss(page_html: str) -> None:
    """决定性消毒断言：①解析面标签 ⊆ 白名单（script/iframe/svg/object/embed/
    form 等无从出现）；②零 on* 事件属性、零 srcdoc；③URL 类属性无危险方案
    （实体解码+剥空白/控制符后判定——与浏览器语义一致）。"""
    scanner = _LiveTagScanner()
    scanner.feed(page_html)
    scanner.close()
    assert set(scanner.tags) <= _SAFE_TAGS, scanner.tags
    for name, value in scanner.attrs:
        assert not name.lower().startswith("on"), (name, value)
        assert name.lower() != "srcdoc", (name, value)
        if name.lower() in _URL_ATTRS and value is not None:
            # HTMLParser 已按浏览器语义对属性值做了一次实体解码——不再二次
            # 解码（浏览器属性解析即单次：&amp;#106; 的产物是字面 &#106;，惰性）。
            probe = _URL_NOISE_RE.sub("", value)
            assert not _DANGEROUS_SCHEME_RE.match(probe), (name, value)


# ---- 渲染合约：markdown→HTML（标题/表格/引用块）+完整文档形态 ----


def test_render_basic_markdown_to_html_document(tmp_path):
    """① 常规渲染：标题→<h1>、表格（tables 扩展）→<table>、引用块→<blockquote>；
    产物为完整 HTML 文档（<!DOCTYPE>+<body>，内联 <style> 无外链样式表）。"""
    html = render_report_html(_write_report(tmp_path, _real_report_md()), "R1")
    assert html.startswith("<!DOCTYPE html>")
    assert "<body>" in html and "</body>" in html
    assert "<h1>" in html and "Run Report" in html
    assert "<table>" in html and "<th>" in html  # tables 扩展生效（概要表真成表）
    assert "<blockquote>" in html
    assert "<style>" in html and 'src="' not in html.split("<style>")[1].split(
        "</style>"
    )[0]


def test_render_title_carries_escaped_run_id(tmp_path):
    """② run_id 入标题且经 html.escape（尖括号等不破文档结构——防注入载体）。"""
    html = render_report_html(
        _write_report(tmp_path, "# Run Report"), 'x"><script>'
    )
    assert "x&quot;&gt;&lt;script&gt;" in html  # 转义后入 <title>
    assert "<script>alert" not in html


# ---- 图片引用改写：plots/xxx.png → /api/runs/{run_id}/plots/xxx.png ----


def test_render_rewrites_plots_refs_to_endpoint(tmp_path):
    """③ 决定性改写：report.md 的 ![alt](plots/xxx.png) 三图引用全部改写为
    /api/runs/{run_id}/plots/xxx.png 端点引用——产物零残留 src="plots/"。"""
    run_id = "20261013-120000"
    html = render_report_html(_write_report(tmp_path, _real_report_md()), run_id)
    for png in _PNG_NAMES:
        assert f'src="/api/runs/{run_id}/plots/{png}"' in html
    assert 'src="plots/' not in html  # 相对路径引用零残留
    assert 'alt="图A：误包率–干扰电平"' in html  # alt 文本保留


def test_render_keeps_non_plots_relative_refs_untouched_path(tmp_path):
    """④ 只改写 plots/ 前缀图引用：非 plots 相对链接（如 [x](kpi.csv)）不改写
    （端点域外内容不越权重写——kpi.csv 下载走 files 端点由视图区接线）。"""
    html = render_report_html(
        _write_report(tmp_path, "[数据](kpi.csv)\n\n![图](plots/curve_a_per_vs_level.png)"),
        "R",
    )
    assert 'href="kpi.csv"' in html  # 普通链接原样
    assert "/api/runs/R/plots/curve_a_per_vs_level.png" in html  # 图照常改写


# ---- 零外链产物断言（口径沿用 localize_console_assets，宁严勿漏） ----


@pytest.mark.parametrize(
    "evil_md",
    [
        "![evil](https://evil.example/x.png)",  # 外部图（最典型外链资源）
        "[外链](http://evil.example/doc)",  # 外部链接
        "![evil](HTTPS://EVIL.EXAMPLE/x.png)",  # 大写协议变体
        "文本提及 https://evil.example 也算违规",  # 正文外链字样（宁严勿漏口径）
        '<img src="//evil.example/x.png">',  # 协议相对（引号属性值）
        "<img src=//evil.example/x.png>",  # 协议相对（无引号属性值）
        '<div style="background: url(//evil.example/x.png)">x</div>',  # CSS url(//
    ],
)
def test_render_rejects_external_links_variants(tmp_path, evil_md):
    """⑤ 零外链断言：外部图/链接、大写协议、正文外链字样、协议相对（引号/
    无引号）、CSS url(// 变体——渲染产物一律 ValueError 拒绝（不静默放行、不
    剥离改写）。注：实体编码旁路（``&#x68;…``）自 B25 C-1 源转义后已消毒为
    纯文本（不再构成外链），归⑭对抗族断言。"""
    with pytest.raises(ValueError) as ei:
        render_report_html(_write_report(tmp_path, evil_md), "R")
    assert "外" in str(ei.value)  # 消息指明外链口径


def test_render_own_template_is_zero_external(tmp_path):
    """⑥ 自产模板（内联样式+文档骨架）自身零外链——正常报告渲染不误伤。"""
    html = render_report_html(_write_report(tmp_path, _real_report_md()), "R9")
    assert "http://" not in html and "https://" not in html
    assert "url(" not in html


# ---- 错误上抛口径（由端点转 500 带指错——叶子不捕错不降级） ----


def test_render_missing_report_file_raises(tmp_path):
    """⑦ report.md 不存在→ValueError（消息含路径——上抛由端点转错误响应）。"""
    missing = str(tmp_path / "nope.md")
    with pytest.raises(ValueError, match="不存在"):
        render_report_html(missing, "R")


def test_render_directory_as_report_raises(tmp_path):
    """⑧ 路径是目录而非普通文件→ValueError（不是普通文件口径）。"""
    with pytest.raises(ValueError, match="不存在"):
        render_report_html(str(tmp_path), "R")


def test_render_corrupt_binary_report_raises(tmp_path):
    """⑨ 文件损坏（非法 utf-8 字节）→ValueError 附解码失败原因。"""
    corrupt = tmp_path / "corrupt.md"
    corrupt.write_bytes(b"\xff\xfe\x00 broken bytes")
    with pytest.raises(ValueError) as ei:
        render_report_html(str(corrupt), "R")
    assert "解码失败" in str(ei.value) or "UnicodeDecodeError" in str(ei.value)


@pytest.mark.parametrize("bad_path", [None, 42, ["report.md"]])
def test_render_non_str_path_raises(bad_path):
    """⑩ report_path 非 str/PathLike→ValueError（编程错误早暴露）。"""
    with pytest.raises(ValueError, match="report_path"):
        render_report_html(bad_path, "R")


@pytest.mark.parametrize(
    "bad_run_id",
    [None, 42, "", "  ", "../runs", "a/b", "a\\b", "/abs/run", "..", "."],
)
def test_render_illegal_run_id_raises(tmp_path, bad_run_id):
    """⑪ run_id 非 str/空/含穿越形态（run_id 嵌入 URL——穿越一律早拒）→ValueError。"""
    path = _write_report(tmp_path, "# R")
    with pytest.raises(ValueError, match="run_id"):
        render_report_html(path, bad_run_id)


def test_render_accepts_pathlib_path(tmp_path):
    """⑫ PathLike 路径透传（os.PathLike 合法入参）。"""
    path = tmp_path / "report.md"
    path.write_text("# R\n\n![a](plots/x.png)\n", encoding="utf-8")
    html = render_report_html(path, "RID")
    assert "/api/runs/RID/plots/x.png" in html


def test_render_result_json_independent(tmp_path):
    """⑬ 叶子只管 report.md→HTML：不读 result.json（溯源结论回显归父函数——
    result.json 缺失不影响渲染）。"""
    run_dir = tmp_path / "20261013-120000"
    run_dir.mkdir()
    (run_dir / "report.md").write_text(_real_report_md(), encoding="utf-8")
    html = render_report_html(str(run_dir / "report.md"), "20261013-120000")
    assert "/api/runs/20261013-120000/plots/curve_a_per_vs_level.png" in html
    assert not (run_dir / "result.json").exists()  # 全程未落 result.json


# ---- XSS 渲染层消毒回归（B25 C-1：对抗实证过的全部形态——经渲染后全部不作为
# ---- 可执行标记存在：转义后为文本、或被换不可导航占位/剥离） ----


#: 对抗形态全集（源转义层拦：行内原始 HTML 标签族；属性层拦：markdown 原生
#: 链接/图片语法的危险方案族——含大小写、控制符混杂、实体编码变体）。
_ADVERSARIAL_MD_FORMS = [
    # 行内原始 HTML 族（markdown 库原样放行——B25 前真实浏览器实证可执行）：
    "<script>window.__XSS_PWNED__=1</script>",  # 经典 script
    "<SCRIPT>window.__XSS_PWNED__=1</SCRIPT>",  # 大写标签
    "<ScRiPt>window.__XSS_PWNED__=1</ScRiPt>",  # 混合大小写
    '<img src=x onerror="window.__XSS_PWNED__=1">',  # onerror 事件属性
    "<img src=x onerror=window.__XSS_PWNED__=1>",  # 无引号 onerror
    "<svg onload=window.__XSS_PWNED__=1></svg>",  # svg onload
    '<iframe src="javascript:window.__XSS_PWNED__=1"></iframe>',  # iframe js URL
    '<iframe srcdoc="<script>window.__XSS_PWNED__=1</script>"></iframe>',  # srcdoc 载荷
    '<object data="data:text/html;base64,PHNjcmlwdD4="></object>',  # object data:
    '<embed src="data:image/svg+xml;base64,AAAA">',  # embed data:
    # markdown 原生链接/图片语法族（源转义拦不住——属性级方案守卫的靶面）：
    "[点我](javascript:window.__XSS_PWNED__=1)",  # 链接 javascript:
    "[点我](JaVaScRiPt:window.__XSS_PWNED__=1)",  # 大写方案
    "[点我](java\tscript:window.__XSS_PWNED__=1)",  # 控制符混杂（浏览器仍执行）
    "[点我](\njavascript:window.__XSS_PWNED__=1)",  # 前导空白
    "[点我](vbscript:msgbox)",  # vbscript:
    "![x](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)",  # 图 data: 载荷
    "[x](DATA:text/html;base64,AAAA)",  # 大写 data:
    "[x](&#106;avascript:window.__XSS_PWNED__=1)",  # 实体编码方案（源转义拦）
    "![e](&#x68;&#x74;&#x74;&#x70;&#x3a;//evil.example/x.png)",  # 实体编码外链（B25 前为断言旁路）
]


@pytest.mark.parametrize("evil_md", _ADVERSARIAL_MD_FORMS)
def test_render_neutralizes_adversarial_forms(tmp_path, evil_md):
    """⑭ 消毒决定性断言：对抗形态经渲染后不作为可执行标记存在——解析面标签 ⊆
    白名单、零 on* 事件属性、零 srcdoc、URL 类属性无危险方案（HTMLParser 只报
    真实标记，转义为文本的形态天然出局）。"""
    html = render_report_html(_write_report(tmp_path, evil_md), "R")
    _assert_no_live_xss(html)
    # 字符串面双重证据：输出无活标签开标记（源转义层——'<' 恒成 &lt; 文本）。
    assert not re.search(r"<\s*script", html, re.IGNORECASE)
    assert not re.search(r"<\s*svg", html, re.IGNORECASE)
    assert not re.search(r"<\s*iframe", html, re.IGNORECASE)
    assert not re.search(r"<\s*object", html, re.IGNORECASE)
    assert not re.search(r"<\s*embed", html, re.IGNORECASE)
    # 转义证据：标签形态以实体文本存活（报告内容可读、不静默吞内容）——
    # srcdoc 载荷形态除外（其载荷随 srcdoc 属性整段剥离，B25 口径）。
    if "srcdoc" not in evil_md and re.search(r"<\s*script", evil_md, re.IGNORECASE):
        assert re.search(r"&lt;\s*script", html, re.IGNORECASE)


def test_render_replaces_dangerous_url_attrs_with_placeholder(tmp_path):
    """⑮ 方案守卫口径：markdown 原生链接 javascript:/data: → href 换不可导航
    占位 ``"#"``（链接元素在、载荷死——不剥整个元素保表格/行文结构）。"""
    html = render_report_html(
        _write_report(
            tmp_path,
            "[a](javascript:window.__XSS_PWNED__=1)\n\n"
            "[b](data:text/html;base64,AAAA)\n\n"
            "[好链](kpi.csv)\n\n"
            "![图](plots/curve_a_per_vs_level.png)",
        ),
        "R",
    )
    assert 'href="#"' in html  # 危险方案换占位
    assert "javascript:" not in html  # 属性值零残留
    assert "data:" not in html
    assert 'href="kpi.csv"' in html  # 相对路径链接不受影响
    assert 'src="/api/runs/R/plots/curve_a_per_vs_level.png"' in html  # 端点图照常
    _assert_no_live_xss(html)


def test_render_escape_keeps_markdown_syntax_alive(tmp_path):
    """⑯ 源转义不伤 markdown 自身语法：标题/表格/代码块/图片链接/引用块照常
    生成（'&lt;' 文本可正常出现——转义不吞内容）。"""
    html = render_report_html(
        _write_report(
            tmp_path,
            "# 标题\n\n"
            "| 项 | 值 |\n| --- | --- |\n| a<b | c&d |\n\n"
            "```\ncode <block> & text\n```\n\n"
            "![图](plots/curve_a_per_vs_level.png)\n\n"
            "> 引用行 5 > 3 & 2 < 7\n",
        ),
        "R",
    )
    assert "<h1>" in html
    assert "<table>" in html and "<td>" in html
    assert "<pre>" in html  # 代码块照常
    assert 'src="/api/runs/R/plots/curve_a_per_vs_level.png"' in html
    assert "<blockquote>" in html  # 行首 '>' 标记还原（引用块照常成块）
    assert "a&lt;b" in html and "c&amp;d" in html  # 单元格特殊字符成文本不破表
    _assert_no_live_xss(html)


def test_render_full_chain_malicious_style_neutralized(tmp_path):
    """⑰ 全链决定性回归（B25 C-1 复现口径）：恶意 style 字段→真 build_report
    产 report.md（对抗实证：B25 前该链路产物含活 ``<script>``）→render→断言
    无 script 活标记（解析面白名单+字符串面零 ``<script``）+正常报告结构在。"""
    run_dir = tmp_path / "20261013-ev1l"
    run_dir.mkdir()
    result = {
        "run_id": "20261013-ev1l",
        "backend": "SimBackend",
        "failure_levels": [
            {
                "style": "<script>window.__XSS_PWNED__=1</script>",
                "failure_level_db": -15.0,
            },
            {
                "style": '<img src=x onerror="window.__XSS_PWNED__=1">',
                "failure_level_db": -16.0,
            },
            {"style": "<svg onload=alert(1)>", "failure_level_db": -17.0},
            {"style": "bandlimited_noise", "failure_level_db": -20.0},
        ],
    }
    report_path = build_report(str(run_dir), result)
    md_text = open(report_path, encoding="utf-8").read()
    assert "<script>" in md_text  # 前置：恶意 style 确实渗入 report.md（载体在）
    html = render_report_html(report_path, "20261013-ev1l")
    _assert_no_live_xss(html)
    assert not re.search(r"<\s*script", html, re.IGNORECASE)  # 零活 script
    assert "&lt;script&gt;" in html  # 以文本存活（不吞内容）
    assert "<table>" in html and "<h1>" in html  # 报告结构完好
    assert "bandlimited_noise" in html  # 良性样式照常呈现
