"""render_report_html 对抗测试：markdown→HTML 服务端渲染（表格/标题）+plots 图片
引用改写为端点引用+零外链产物断言（外部图/链接/协议相对/CSS url 变体全拒）+
文件不存在/损坏/非 str 路径/非法 run_id 的 ValueError 上抛口径。

R60 L1 叶子——上游覆盖策略：本文件单测即 serve_run_artifacts 上游的主证据
（责任文档 tested 策略「上游覆盖: serve_run_artifacts」）。
"""
import pytest

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
        "![e](&#x68;&#x74;&#x74;&#x70;&#x3a;//evil.example/x.png)",  # 实体编码旁路
        '<img src="//evil.example/x.png">',  # 协议相对（引号属性值）
        "<img src=//evil.example/x.png>",  # 协议相对（无引号属性值）
        '<div style="background: url(//evil.example/x.png)">x</div>',  # CSS url(//
    ],
)
def test_render_rejects_external_links_variants(tmp_path, evil_md):
    """⑤ 零外链断言：外部图/链接、大写协议、正文外链字样、HTML 实体编码、
    协议相对（引号/无引号）、CSS url(// 变体——渲染产物一律 ValueError 拒绝
    （不静默放行、不剥离改写）。"""
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
