"""check_demo_manual 结构体检测试：完备通过/缺条目/缺四件套/缺两档/占位检出/FAQ 缺覆盖/围栏内两档词不算数/FAQ 散文单行不算覆盖/同名多章残章不掩盖/文件缺失+真实手册冒烟（B32 M3 三洞加固回归锚：⑧⑨⑩）；围栏内示例表格不算 FAQ 覆盖/缩进围栏内两档词不算数（B33 对抗 F2/F3 回归锚：⑪⑫）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.check_demo_manual.check_demo_manual import check_demo_manual

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_MANUAL = REPO_ROOT / "docs" / "功能演示手册.md"
REAL_README = REPO_ROOT / "fn_docs" / "README.md"

# —— fixture README：FAQ 列表形态照抄真实 fn_docs/README.md「常见问题」——加粗症状
#    短语+冒号+处置说明；列表后跟 ### 子节，验证 FAQ 解析止于下一任意层级标题。
_README_FIXTURE = """\
# 项目 README（fixture）

## 常见问题

- **报"场景校验未通过"**：看错误清单第几条——缺声明/超功率/超频段/样式拼错都会列明。
- **报"远程算力不可达"**：训练默认走远程显卡机；没有就加 `where='local'` 参数本地轻量训练。

### 现场演示手册

要看演示去 docs/功能演示手册.md。
"""

# FAQ 覆盖键锚：整条 FAQ 去标点后的前 12 字符（与实现口径一致的手算预期值）。
_FAQ_KEY_1 = "报场景校验未通过看错误清"
_FAQ_KEY_2 = "报远程算力不可达训练默认"

_HEADER = "# 功能演示手册（fixture）\n\n"

# —— 条目章 fixture：四件套齐+两档齐；操作步骤内含代码围栏（# 注释行不应被当成
#    手册标题——围栏感知解析的回归锚：若误判会截断本章导致「预期现象」漏检）。
_CHAPTER_ONE = """\
## 1. 一键测评

### 功能说明
一条命令跑完干扰测评全流程。

### 所需设备与连线
- 便携档：主机一台（sim 后端，无需射频硬件）。
- 全量档：主机+B210 射频设备+天线。

### 操作步骤
命令：

```bash
# 井号开头的命令注释不应被当成手册标题
.venv/bin/python -m src.run_demo --scenario tone_demo.yaml
```

### 预期现象
退出码 0，runs/ 下生成运行目录与报告。
"""

_CHAPTER_TWO = """\
## 2. AI 认干扰

### 功能说明
用录音库训练七分类识别模型。

### 所需设备与连线
- 便携档：本机轻量训练。
- 全量档：远程显卡机。

### 操作步骤
1. 网页 AI 页发起训练。

### 预期现象
混淆矩阵与分数表格呈现。
"""

# 应急速查表行（去标点归一后须包含对应 FAQ 键——保守覆盖口径）。
_ROW_FAQ1 = '| 报"场景校验未通过" | 看错误清单第几条，缺声明/超功率都会列明 |'
_ROW_FAQ2 = '| 报"远程算力不可达" | 训练默认走远程显卡机，本地加 where=\'local\' 轻量跑 |'


def _appendix_with_rows(*rows: str) -> str:
    """附录 fixture：出发前检查单+现场应急速查表（表格行数可变——FAQ 覆盖用例手术位）。"""
    return (
        "## 附录：出发前检查单\n\n- 主机、充电器、U 盘。\n\n"
        "## 附录：现场应急速查表\n\n| 症状 | 处置 |\n| --- | --- |\n"
        + "\n".join(rows)
        + "\n"
    )


def _manual_with_emergency_rows(*rows: str) -> str:
    """组装 fixture 手册：2 条目章+附录（应急速查表行数可变——FAQ 覆盖用例的手术位）。"""
    return _HEADER + _CHAPTER_ONE + "\n" + _CHAPTER_TWO + "\n" + _appendix_with_rows(*rows)


_COMPLETE_MANUAL = _manual_with_emergency_rows(_ROW_FAQ1, _ROW_FAQ2)

_EXPECTED = ["一键测评", "AI 认干扰"]


def _write_pair(tmp_path: Path, manual_text: str, readme_text: str = _README_FIXTURE) -> tuple[Path, Path]:
    """fixture 手册+README 落盘临时目录，返回 (手册路径, README 路径)。"""
    manual = tmp_path / "功能演示手册.md"
    readme = tmp_path / "README.md"
    manual.write_text(manual_text, encoding="utf-8")
    readme.write_text(readme_text, encoding="utf-8")
    return manual, readme


def test_complete_manual_passes(tmp_path):
    """①完备手册（2 条目+附录含 2 条 FAQ 键）→ ok=True、四清单全空、passed≥2。"""
    manual, readme = _write_pair(tmp_path, _COMPLETE_MANUAL)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["ok"] is True
    assert report["missing_entries"] == []
    assert report["missing_sections"] == []
    assert report["placeholders"] == []
    assert report["faq_uncovered"] == []
    assert report["passed"] == 2


def test_missing_entry_named(tmp_path):
    """②缺条目（AI 认干扰整章移除）→ missing_entries 点名。"""
    manual, readme = _write_pair(tmp_path, _COMPLETE_MANUAL.replace(_CHAPTER_TWO + "\n", ""))
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["ok"] is False
    assert report["missing_entries"] == ["AI 认干扰"]
    assert report["passed"] == 1


def test_missing_expected_section_detected(tmp_path):
    """③「一键测评」章缺「预期现象」小节 → missing_sections 检出点名。"""
    broken = _COMPLETE_MANUAL.replace("### 预期现象\n退出码 0", "### 预期结果\n退出码 0")
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["missing_sections"] == [{"entry": "一键测评", "missing": ["预期现象"]}]
    assert report["ok"] is False


def test_missing_full_tier_mark_detected(tmp_path):
    """④「一键测评」的设备小节缺「全量档」标注 → missing_sections 以缺件形态检出。"""
    broken = _COMPLETE_MANUAL.replace("- 全量档：主机+B210 射频设备+天线。\n", "")
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["missing_sections"] == [{"entry": "一键测评", "missing": ["所需设备与连线:全量档"]}]
    assert report["ok"] is False


def test_placeholder_detected_and_legal_word_not_flagged(tmp_path):
    """⑤含「待定」→ placeholders 检出；合法口径词「待实测」不误报。"""
    broken = _COMPLETE_MANUAL.replace(
        "一条命令跑完干扰测评全流程。",
        "一条命令跑完干扰测评全流程。\n\n> 部分参数待定；增益表为待实测（合法口径词）。",
    )
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert len(report["placeholders"]) == 1
    assert "待定" in report["placeholders"][0]
    assert all("待实测" not in p for p in report["placeholders"])
    assert report["ok"] is False


def test_faq_uncovered_named(tmp_path):
    """⑥应急表只覆盖第 1 条 FAQ → 第 2 条以 12 字符键点名入 faq_uncovered。"""
    manual, readme = _write_pair(tmp_path, _manual_with_emergency_rows(_ROW_FAQ1))
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["faq_uncovered"] == [_FAQ_KEY_2]
    assert report["ok"] is False


def test_tier_marks_only_inside_fence_detected_missing(tmp_path):
    """⑧「一键测评」设备小节两档词仅现于代码围栏内（小节正文无）→ 检出两档缺件。

    M3 围栏洞回归锚：旧口径小节体含围栏内文本，命令注释里的「便携档/全量档」
    会伪达标——修复后小节体查两档词前剥离围栏块。
    """
    fenced_dev = (
        "### 所需设备与连线\n"
        "档位配置看命令注释：\n\n"
        "```bash\n"
        "# 便携档：sim 后端，无需射频硬件\n"
        "# 全量档：主机接 B210 射频设备\n"
        "```\n"
    )
    broken = _COMPLETE_MANUAL.replace(
        "### 所需设备与连线\n"
        "- 便携档：主机一台（sim 后端，无需射频硬件）。\n"
        "- 全量档：主机+B210 射频设备+天线。\n",
        fenced_dev,
    )
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["missing_sections"] == [
        {"entry": "一键测评", "missing": ["所需设备与连线:便携档", "所需设备与连线:全量档"]}
    ]
    assert report["ok"] is False


def test_faq_keys_in_prose_not_table_row_all_uncovered(tmp_path):
    """⑨应急区散文单行含全部 FAQ 键（旧口径可伪过）但非表格行 → faq_uncovered 全列。

    M3 散文洞回归锚：覆盖命中行必须是表格行（| 起始），散文复述症状短语不算。
    """
    prose_appendix = (
        "## 附录：出发前检查单\n\n- 主机、充电器、U 盘。\n\n"
        "## 附录：现场应急速查表\n\n"
        '报"场景校验未通过"：看错误清单第几条——缺声明/超功率/超频段/样式拼错都会列明（散文备注）。\n'
        "报\"远程算力不可达\"：训练默认走远程显卡机；没有就加 `where='local'` 参数本地轻量训练（散文备注）。\n"
    )
    manual, readme = _write_pair(
        tmp_path, _HEADER + _CHAPTER_ONE + "\n" + _CHAPTER_TWO + "\n" + prose_appendix
    )
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["faq_uncovered"] == [_FAQ_KEY_1, _FAQ_KEY_2]
    assert report["ok"] is False


def test_faq_keys_in_fenced_table_rows_not_coverage(tmp_path):
    """⑪应急区表格行全部位于代码围栏内（示例表格源码含全部 FAQ 键）→ faq_uncovered 全列。

    B33 对抗 F2 回归锚：旧口径应急区只按 | 起始收行、不剥围栏——围栏内示例
    表格恰好复述 FAQ 症状短语即伪达标；修复后应急区先剥离围栏再收表格行。
    """
    fenced_appendix = (
        "## 附录：出发前检查单\n\n- 主机、充电器、U 盘。\n\n"
        "## 附录：现场应急速查表\n\n"
        "速查表 markdown 源示例（演示讲稿排版参考）：\n\n"
        "```\n"
        "| 症状 | 处置 |\n| --- | --- |\n"
        + _ROW_FAQ1 + "\n" + _ROW_FAQ2 + "\n"
        "```\n"
    )
    manual, readme = _write_pair(
        tmp_path, _HEADER + _CHAPTER_ONE + "\n" + _CHAPTER_TWO + "\n" + fenced_appendix
    )
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["faq_uncovered"] == [_FAQ_KEY_1, _FAQ_KEY_2]
    assert report["ok"] is False


def test_tier_marks_only_inside_indented_fence_detected_missing(tmp_path):
    """⑫「一键测评」设备小节两档词仅现于 1–3 空格缩进围栏内 → 检出两档缺件。

    B33 对抗 F3 回归锚：旧口径 _FENCE_RE 只认顶格围栏，缩进围栏绕过剥离——
    缩进命令注释里的「便携档/全量档」按围栏外正文伪达标；修复后围栏识别允许
    0–3 空格缩进。4 空格缩进代码块非围栏、本库手册写法不使用（限界，不处理）。
    """
    indented_fence_dev = (
        "### 所需设备与连线\n"
        "档位配置看缩进命令注释：\n\n"
        "   ```bash\n"
        "   # 便携档：sim 后端，无需射频硬件\n"
        "   # 全量档：主机接 B210 射频设备\n"
        "   ```\n"
    )
    broken = _COMPLETE_MANUAL.replace(
        "### 所需设备与连线\n"
        "- 便携档：主机一台（sim 后端，无需射频硬件）。\n"
        "- 全量档：主机+B210 射频设备+天线。\n",
        indented_fence_dev,
    )
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["missing_sections"] == [
        {"entry": "一键测评", "missing": ["所需设备与连线:便携档", "所需设备与连线:全量档"]}
    ]
    assert report["ok"] is False


def test_duplicate_named_chapters_residual_not_masked(tmp_path):
    """⑩双同名「一键测评」章一残一全 → 残章缺件入 missing_sections（首匹配不再掩盖）。

    M3 首匹配歧义回归锚：审计须遍历全部含名二级标题章——首个全章不得掩盖
    后续残章；残章缺件时该条目不计 passed（passed=1 仅 AI 认干扰）。
    """
    residual = _CHAPTER_ONE.replace("### 预期现象\n退出码 0，runs/ 下生成运行目录与报告。\n", "")
    manual, readme = _write_pair(
        tmp_path,
        _HEADER
        + _CHAPTER_ONE
        + "\n"
        + residual
        + "\n"
        + _CHAPTER_TWO
        + "\n"
        + _appendix_with_rows(_ROW_FAQ1, _ROW_FAQ2),
    )
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["missing_sections"] == [{"entry": "一键测评", "missing": ["预期现象"]}]
    assert report["passed"] == 1
    assert report["ok"] is False


def test_missing_files_raise_file_not_found(tmp_path):
    """⑦手册或 README 路径不存在 → FileNotFoundError 上抛。"""
    readme = tmp_path / "README.md"
    readme.write_text(_README_FIXTURE, encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        check_demo_manual(tmp_path / "不存在的手册.md", readme, ["一键测评"])
    manual = tmp_path / "功能演示手册.md"
    manual.write_text(_COMPLETE_MANUAL, encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        check_demo_manual(manual, tmp_path / "不存在的README.md", ["一键测评"])


#: 期望集登记文件（随批增长）：一行一条目名，# 注释行与空行忽略；B32 为空
#: （仅总章交付），B35 起每批在此追加一行条目名——smoke 硬门随之加压。
_EXPECTED_ENTRIES_FILE = Path(__file__).resolve().parent / "expected_entries.txt"


def _load_expected_entries() -> list[str]:
    """读期望集登记文件：忽略 # 注释行与空行，其余每行去空白取一个条目名。"""
    lines = _EXPECTED_ENTRIES_FILE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def test_demo_manual_check_real_manual_smoke():
    """最外层集成锚（R77–R83 各批验收命令同源）：对真实 docs/功能演示手册.md 冒烟。

    期望集自 expected_entries.txt 读取（随批增长，B32 为空）：①三硬门随批
    生效——missing_entries/missing_sections/placeholders 必空；②总章锚在位
    ——0.1 便携档设备清单与 0.5 演示前准备两节标题必在；③FAQ 覆盖两态——
    附录应急速查表（存在含「应急」的标题）交付后 faq_uncovered 必空，
    B42 附录落地前不硬卡（跳过该断言）。
    """
    if not REAL_MANUAL.is_file():
        pytest.skip("docs/功能演示手册.md 尚未交付（真实手册逐步成型后本用例自动生效）")
    if not REAL_README.is_file():
        pytest.skip("fn_docs/README.md 不在预期位置，无法做真实手册冒烟")
    report = check_demo_manual(REAL_MANUAL, REAL_README, _load_expected_entries())
    # ① 随批硬门：期望集条目全在册且四件套/两档齐、零占位残留。
    assert report["missing_entries"] == []
    assert report["missing_sections"] == []
    assert report["placeholders"] == []
    # ② 总章锚：0.1 便携档设备清单与 0.5 演示前准备两节标题在位。
    manual_text = REAL_MANUAL.read_text(encoding="utf-8")
    assert "0.1 便携演示档设备清单" in manual_text
    assert "0.5 演示前准备" in manual_text
    # ③ FAQ 覆盖两态：附录已交付（含「应急」的标题在册）→ 须全覆盖；
    #    未交付（B42 前）→ 跳过该断言不硬卡。
    has_emergency_heading = any(
        raw.lstrip().startswith("#") and "应急" in raw
        for raw in manual_text.splitlines()
    )
    if has_emergency_heading:
        assert report["faq_uncovered"] == []


# B42 重走变异回归锚（batches 终门处置行"拼接章检出/两档小节体删空检出"落测试化）
def _spoof_manual(spoof_title: str) -> str:
    """删 fixture 的两个期望章，塞一个四件套齐备的拼接章顶替两名。"""
    import re as _re

    t = _COMPLETE_MANUAL
    for ch in ("## 1. 一键测评", "## 2. AI 认干扰"):
        t = _re.sub(r"\n" + _re.escape(ch) + r"[^\n]*\n(?:(?!\n## ).)*", "\n", t, flags=_re.S)
    merged = [
        f"## {spoof_title}",
        "",
        "### 功能说明", "x",
        "### 所需设备与连线（便携档、全量档）", "便携档：a 全量档：b",
        "### 操作步骤（命令与参数）", "x",
        "### 预期现象", "x",
    ]
    return t.replace("## 1. 一键测评", "\n".join(merged) + "\n## 已删", 0) if "一键测评" in t else _insert_after_readme(t, merged)


def _insert_after_readme(text: str, block: list) -> str:
    lines = text.splitlines()
    out = []
    inserted = False
    for l in lines:
        out.append(l)
        if not inserted and l.startswith("## "):
            out.extend(block)
            inserted = True
    return "\n".join(out)


@pytest.mark.parametrize("spoof_title", ["一键测评与AI 认干扰", "3.一键测评与AI 认干扰", "3. 一键测评与AI 认干扰"])
def test_b42_redo_merged_chapter_spoof_detected(tmp_path, spoof_title):
    manual_p, readme_p = _write_pair(tmp_path, _spoof_manual(spoof_title))
    r = check_demo_manual(manual_p, readme_p, _EXPECTED)
    assert "一键测评" in r["missing_entries"] and "AI 认干扰" in r["missing_entries"]


def test_b42_redo_tier_body_stripped_detected(tmp_path):
    manual = _COMPLETE_MANUAL
    import re as _re

    t = _re.sub(r"(### 所需设备与连线[^\n]*\n)(?:(?!\n###|\n## ).)*", r"\1", manual, count=1, flags=_re.S)
    manual_p, readme_p = _write_pair(tmp_path, t)
    r = check_demo_manual(manual_p, readme_p, _EXPECTED)
    assert r["missing_sections"], "两档小节体删空必须检出（终门 M3）"


# B42 重走 I1/I2/I3 加固锚
def test_b42_redo_mixed_fence_spoof_detected(tmp_path):
    """混合围栏（``` 开 ~~~ 关）内的伪章必须算未交付（重走 I1）。"""
    t = _COMPLETE_MANUAL.replace(
        "## 1. 一键测评",
        "```\n## 1. 一键测评\n~~~\n## 99. 一键测评占位章\n\n### 功能说明\nx\n"
        "### 所需设备与连线（便携档、全量档）\n便携档：a 全量档：b\n"
        "### 操作步骤（命令与参数）\nx\n### 预期现象\nx\n",
        1,
    )
    manual_p, readme_p = _write_pair(tmp_path, t)
    r = check_demo_manual(manual_p, readme_p, _EXPECTED)
    assert "一键测评" in r["missing_entries"], "混合围栏内的伪章必须检出"


def test_b42_redo_html_comment_tier_spoof_detected(tmp_path):
    """HTML 注释里的档词不算两档达标（重走 I2）。"""
    import re as _re

    t = _re.sub(
        r"(### 所需设备与连线[^\n]*\n)(?:(?!\n###|\n## ).)*",
        r"\1<!-- 便携档 全量档 -->\n",
        _COMPLETE_MANUAL,
        count=1,
        flags=_re.S,
    )
    manual_p, readme_p = _write_pair(tmp_path, t)
    r = check_demo_manual(manual_p, readme_p, _EXPECTED)
    assert r["missing_sections"], "HTML 注释档词必须检出"


def test_b42_redo_tier_in_title_only_detected(tmp_path):
    """M3 回退盲锚：小节标题含档词+小节体无档词必须检出（重走 I3/B7 形态）。"""
    import re as _re

    t = _COMPLETE_MANUAL.replace(
        "### 所需设备与连线", "### 所需设备与连线（便携档、全量档）", 1
    )
    t = _re.sub(
        r"(### 所需设备与连线（便携档、全量档）\n)(?!便携档)(?:(?!\n###|\n## ).)*",
        r"\1",
        t,
        count=1,
        flags=_re.S,
    )
    manual_p, readme_p = _write_pair(tmp_path, t)
    r = check_demo_manual(manual_p, readme_p, _EXPECTED)
    assert r["missing_sections"], "标题自含档词+空体必须检出"
