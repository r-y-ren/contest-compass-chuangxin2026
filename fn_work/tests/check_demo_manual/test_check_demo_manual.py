"""check_demo_manual 结构体检测试（R90 契约 v2）：完备通过/缺条目/缺三件套/两档词防回潮（正文检出·围栏/缩进围栏/HTML 注释/混合围栏内不算·编号章外不算）/总章清单完整性（设备边界节·唯一连接节·0.1 表核心设备项）/占位检出/FAQ 缺覆盖/围栏内示例表格不算 FAQ 覆盖/同名多章残章不掩盖/文件缺失+真实手册冒烟。
B32 M3 三洞加固回归锚（⑧⑨⑩）与 B33 对抗 F2/F3 回归锚（⑪⑫）随契约 v2 迁移（围栏/注释剥离语义保留——词级判定仍不可见围栏内容）；B42 重走 I1–I3 锚同批迁移（拼接章检出/混合围栏伪章/注释与标题档词）。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.check_demo_manual.check_demo_manual import _OVERVIEW_DEVICE_ITEMS, check_demo_manual

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

# —— 总章 fixture（R90 v2）：设备边界节+0. 总章（0.1 设备全集清单单表含核心
#    设备项+0.2 唯一连接）——分节常量便于总章完整性用例按节手术。
_BOUNDARY_SECTION = (
    "## 设备边界：为什么清单里没有大型仪器\n\n"
    "大仪器由 B210 和软件顶替（对照表从略）。\n\n"
)

_CLIST_SECTION = (
    "### 0.1 演示设备全集清单（一张表，不分档）\n\n"
    "| # | 设备 | 数量 |\n|---|---|---|\n"
    "| 1 | 笔记本 | 1 |\n"
    "| 2 | USRP B210 | 1 |\n"
    "| 3 | 30dB SMA 衰减器 | 1 |\n"
    "| 4 | 双频胶棒天线 | 2 |\n"
    "| 5 | GPS/BD 有源天线 | 1 |\n"
    "| 6 | SMA 同轴负载 | 2 |\n"
    "| 7 | ESP32 开发板 | 2 |\n"
    "| 8 | NRF24L01 模块 | 2 |\n"
    "| 9 | 便携金属屏蔽盒 | 1 |\n"
    "| 10 | 示波器 | 1 |\n"
    "| 11 | 万用表 | 1 |\n"
    "| 12 | LattePanda 3 Delta | 1 |\n"
    "| 13 | PIC18F4520 开发套件 | 1 |\n\n"
)

_CONNECT_SECTION = (
    "### 0.2 唯一连接方式（一张总图+一张总表）\n\n"
    "接线总表从略。\n\n"
)

_OVERVIEW = "## 0. 总章：带什么、怎么连、怎么开机\n\n" + _CLIST_SECTION + _CONNECT_SECTION

# —— 条目章 fixture（R90 v2 三件套：功能说明/操作步骤/预期现象——无"所需设备
#    与连线"节、零两档词）；操作步骤内含代码围栏（# 注释行不应被当成手册标题
#    ——围栏感知解析的回归锚：若误判会截断本章导致「预期现象」漏检）。
_CHAPTER_ONE = """\
## 1. 一键测评

### 功能说明
一条命令跑完干扰测评全流程。

### 操作步骤（命令与参数）
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

### 操作步骤（命令与参数）
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
    """组装 fixture 手册：设备边界+总章+2 条目章+附录（应急速查表行数可变——FAQ 覆盖用例的手术位）。"""
    return (
        _HEADER
        + _BOUNDARY_SECTION
        + _OVERVIEW
        + _CHAPTER_ONE
        + "\n"
        + _CHAPTER_TWO
        + "\n"
        + _appendix_with_rows(*rows)
    )


_COMPLETE_MANUAL = _manual_with_emergency_rows(_ROW_FAQ1, _ROW_FAQ2)

_EXPECTED = ["一键测评", "AI 认干扰"]


def _write_pair(tmp_path: Path, manual_text: str, readme_text: str = _README_FIXTURE) -> tuple[Path, Path]:
    """fixture 手册+README 落盘临时目录，返回 (手册路径, README 路径)。"""
    manual = tmp_path / "功能演示手册.md"
    readme = tmp_path / "README.md"
    manual.write_text(manual_text, encoding="utf-8")
    readme.write_text(readme_text, encoding="utf-8")
    return manual, readme


def _tier_hit_lines(manual_text: str) -> list[int]:
    """手术后手册中含两档词的**全部**行号（1 基）——用例手算预期值的复用件。"""
    return [
        i for i, raw in enumerate(manual_text.splitlines(), 1)
        if "便携档" in raw or "全量档" in raw
    ]


def test_complete_manual_passes(tmp_path):
    """①完备手册（总章 v2+2 三件套条目+附录含 2 条 FAQ 键）→ ok=True、六清单全空、passed=2。"""
    manual, readme = _write_pair(tmp_path, _COMPLETE_MANUAL)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["ok"] is True
    assert report["missing_entries"] == []
    assert report["missing_sections"] == []
    assert report["placeholders"] == []
    assert report["faq_uncovered"] == []
    assert report["tier_regression"] == []
    assert report["overview_missing"] == []
    assert report["passed"] == 2


def test_missing_entry_named(tmp_path):
    """②缺条目（AI 认干扰整章移除）→ missing_entries 点名。"""
    manual, readme = _write_pair(tmp_path, _COMPLETE_MANUAL.replace(_CHAPTER_TWO + "\n", ""))
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["ok"] is False
    assert report["missing_entries"] == ["AI 认干扰"]
    assert report["passed"] == 1


def test_missing_expected_section_detected(tmp_path):
    """③「一键测评」章缺「预期现象」小节 → missing_sections 检出点名（三件套口径）。"""
    broken = _COMPLETE_MANUAL.replace("### 预期现象\n退出码 0", "### 预期结果\n退出码 0")
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["missing_sections"] == [{"entry": "一键测评", "missing": ["预期现象"]}]
    assert report["ok"] is False


def test_tier_words_in_chapter_body_regressed(tmp_path):
    """④（v2 防回潮）「一键测评」章正文混入两档词 → tier_regression 以行号点名。

    R90 v2：旧"两档标注齐"合规断言删除后，档词在功能章内出现即回潮；同行
    两词只记一个行号（行级点名）。
    """
    broken = _COMPLETE_MANUAL.replace(
        "一条命令跑完干扰测评全流程。",
        "一条命令跑完干扰测评全流程。\n\n> 便携档无需射频硬件；全量档接 B210。",
    )
    hits = _tier_hit_lines(broken)
    assert hits, "fixture 手术失败（两档词未注入）"
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["tier_regression"] == hits
    assert len(report["tier_regression"]) == 1  # 同行两词一个行号
    assert report["missing_sections"] == []  # 档词不影响三件套口径
    assert report["ok"] is False


def test_tier_words_on_chapter_heading_lines_regressed(tmp_path):
    """④b（v2 防回潮）残留小节标题自含档词（体空）也算回潮——标题行即可见文本。

    B42 重走 I3 的 v2 迁移：旧口径"标题自含档词+空体检出缺件"，v2 改为标题行
    本身入 tier_regression。
    """
    broken = _COMPLETE_MANUAL.replace(
        "### 预期现象\n退出码 0，runs/ 下生成运行目录与报告。\n",
        "### 预期现象\n退出码 0，runs/ 下生成运行目录与报告。\n\n### 所需设备与连线（便携档、全量档）\n",
    )
    hits = _tier_hit_lines(broken)
    assert hits, "fixture 手术失败（档词标题未注入）"
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["tier_regression"] == hits
    assert report["ok"] is False


def test_tier_words_outside_numbered_chapters_not_regressed(tmp_path):
    """④c（v2 口径界）附录（非编号章）内的两档词不在防回潮范围 → tier_regression 空。"""
    broken = _COMPLETE_MANUAL.replace(
        "- 主机、充电器、U 盘。",
        "- 主机、充电器、U 盘（便携档/全量档旧讲稿备注）。",
    )
    assert _tier_hit_lines(broken), "fixture 手术失败（附录档词未注入）"
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["tier_regression"] == []
    assert report["ok"] is True


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


def test_tier_words_only_inside_fence_not_regressed(tmp_path):
    """⑧（v2 迁移）「一键测评」章两档词仅现于代码围栏内的命令注释 → 不触发防回潮。

    M3 围栏洞回归锚的 v2 形态：词级判定仍剥离围栏内容（旧为防命令注释伪达标，
    v2 为防围栏示例误报）；正文出现才点名（对照④）。
    """
    broken = _COMPLETE_MANUAL.replace(
        "# 井号开头的命令注释不应被当成手册标题",
        "# 便携档：sim 后端，无需射频硬件；全量档：主机接 B210 射频设备",
    )
    assert _tier_hit_lines(broken), "fixture 手术失败（围栏内档词未注入）"
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["tier_regression"] == []
    assert report["ok"] is True


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
        tmp_path,
        _HEADER + _BOUNDARY_SECTION + _OVERVIEW + _CHAPTER_ONE + "\n" + _CHAPTER_TWO + "\n" + prose_appendix,
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
        tmp_path,
        _HEADER + _BOUNDARY_SECTION + _OVERVIEW + _CHAPTER_ONE + "\n" + _CHAPTER_TWO + "\n" + fenced_appendix,
    )
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["faq_uncovered"] == [_FAQ_KEY_1, _FAQ_KEY_2]
    assert report["ok"] is False


def test_tier_words_only_inside_indented_fence_not_regressed(tmp_path):
    """⑫（v2 迁移）「一键测评」章两档词仅现于 1–3 空格缩进围栏内 → 不触发防回潮。

    B33 对抗 F3 回归锚的 v2 形态：围栏识别允许 0–3 空格缩进——缩进命令注释里
    的「便携档/全量档」按围栏内文本剥离；4 空格缩进代码块非围栏、本库手册
    写法不使用（限界，不处理）。
    """
    indented_fence = (
        "   ```bash\n"
        "   # 便携档：sim 后端，无需射频硬件\n"
        "   # 全量档：主机接 B210 射频设备\n"
        "   .venv/bin/python -m src.run_demo --scenario tone_demo.yaml\n"
        "   ```\n"
    )
    broken = _COMPLETE_MANUAL.replace(
        "```bash\n"
        "# 井号开头的命令注释不应被当成手册标题\n"
        ".venv/bin/python -m src.run_demo --scenario tone_demo.yaml\n"
        "```\n",
        indented_fence,
    )
    assert _tier_hit_lines(broken), "fixture 手术失败（缩进围栏内档词未注入）"
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["tier_regression"] == []
    assert report["ok"] is True


def test_duplicate_named_chapters_residual_not_masked(tmp_path):
    """⑩双同名「一键测评」章一残一全 → 残章缺件入 missing_sections（首匹配不再掩盖）。

    M3 首匹配歧义回归锚：审计须遍历全部含名二级标题章——首个全章不得掩盖
    后续残章；残章缺件时该条目不计 passed（passed=1 仅 AI 认干扰）。
    """
    residual = _CHAPTER_ONE.replace("### 预期现象\n退出码 0，runs/ 下生成运行目录与报告。\n", "")
    manual, readme = _write_pair(
        tmp_path,
        _HEADER
        + _BOUNDARY_SECTION
        + _OVERVIEW
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


# —— 总章清单完整性（断言族六，R90 v2 新增）——
def test_overview_boundary_anchor_removal_named(tmp_path):
    """删「## 设备边界」节（标题+体）→ overview_missing 点名「设备边界节」。"""
    broken = _COMPLETE_MANUAL.replace(_BOUNDARY_SECTION, "")
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["overview_missing"] == ["设备边界节"]
    assert report["passed"] == 2  # 总章族不计数——条目口径不受影响
    assert report["ok"] is False


def test_overview_connection_anchor_removal_named(tmp_path):
    """「唯一连接」节锚词丢失（0.2 改名）→ overview_missing 点名「唯一连接节」。"""
    broken = _COMPLETE_MANUAL.replace(
        "### 0.2 唯一连接方式（一张总图+一张总表）", "### 0.2 连接方式（总图+总表）"
    )
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["overview_missing"] == ["唯一连接节"]
    assert report["ok"] is False


def test_overview_core_device_item_removal_named(tmp_path):
    """0.1 表删「示波器」行（关键设备项缺失）→ overview_missing 点名「示波器」。"""
    broken = _COMPLETE_MANUAL.replace("| 10 | 示波器 | 1 |\n", "")
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["overview_missing"] == ["示波器"]
    assert report["ok"] is False


def test_overview_clist_section_removal_names_all_core_items(tmp_path):
    """0.1 设备全集清单节整体缺失 → 全部核心设备项点名（核心项清单全列）。"""
    broken = _COMPLETE_MANUAL.replace(_CLIST_SECTION, "")
    manual, readme = _write_pair(tmp_path, broken)
    report = check_demo_manual(manual, readme, _EXPECTED)
    assert report["overview_missing"] == list(_OVERVIEW_DEVICE_ITEMS)
    assert report["ok"] is False


#: 期望集登记文件（随批增长）：一行一条目名，# 注释行与空行忽略；B32 为空
#: （仅总章交付），B35 起每批在此追加一行条目名——smoke 硬门随之加压。
_EXPECTED_ENTRIES_FILE = Path(__file__).resolve().parent / "expected_entries.txt"


def _load_expected_entries() -> list[str]:
    """读期望集登记文件：忽略 # 注释行与空行，其余每行去空白取一个条目名。"""
    lines = _EXPECTED_ENTRIES_FILE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def test_demo_manual_check_real_manual_smoke():
    """最外层集成锚（R77–R83 各批验收命令同源；R90 契约 v2）：对真实 docs/功能演示手册.md 冒烟。

    期望集自 expected_entries.txt 读取（随批增长）：①随批硬门——missing_entries/
    missing_sections/placeholders 必空且 passed==期望数（三件套契约 v2）；②v2
    防回潮与总章硬门——tier_regression/overview_missing 必空；③总章锚在位
    ——设备边界节与 0.1 设备全集清单/0.4 演示前准备节标题必在；④FAQ 覆盖
    ——附录应急速查表（含「应急」的标题）交付后 faq_uncovered 必空。
    """
    if not REAL_MANUAL.is_file():
        pytest.skip("docs/功能演示手册.md 尚未交付（真实手册逐步成型后本用例自动生效）")
    if not REAL_README.is_file():
        pytest.skip("fn_docs/README.md 不在预期位置，无法做真实手册冒烟")
    expected = _load_expected_entries()
    report = check_demo_manual(REAL_MANUAL, REAL_README, expected)
    # ① 随批硬门：期望集条目全在册且三件套齐、零占位残留。
    assert report["missing_entries"] == []
    assert report["missing_sections"] == []
    assert report["placeholders"] == []
    assert report["passed"] == len(expected)
    # ② v2 硬门：两档词零回潮+总章清单完整（设备边界/唯一连接/0.1 核心设备项）。
    assert report["tier_regression"] == []
    assert report["overview_missing"] == []
    assert report["ok"] is True
    # ③ 总章锚：设备边界节与 0.1 设备全集清单/0.4 演示前准备节标题在位（v2 锚）。
    manual_text = REAL_MANUAL.read_text(encoding="utf-8")
    assert "## 设备边界" in manual_text
    assert "### 0.1 演示设备全集清单" in manual_text
    assert "### 0.4 演示前准备" in manual_text
    # ④ FAQ 覆盖：附录已交付（含「应急」的标题在册）→ 须全覆盖。
    has_emergency_heading = any(
        raw.lstrip().startswith("#") and "应急" in raw
        for raw in manual_text.splitlines()
    )
    if has_emergency_heading:
        assert report["faq_uncovered"] == []


# B42 重走变异回归锚（batches 终门处置行"拼接章检出"落测试化；v2 迁移：拼接
# 章顶替 fixture 改三件套形态，档词相关锚并入防回潮族）
def _spoof_manual(spoof_title: str) -> str:
    """删 fixture 的两个期望章，塞一个三件套齐备的拼接章顶替两名。"""
    t = _COMPLETE_MANUAL
    for ch in ("## 1. 一键测评", "## 2. AI 认干扰"):
        t = re.sub(r"\n" + re.escape(ch) + r"[^\n]*\n(?:(?!\n## ).)*", "\n", t, flags=re.S)
    merged = "\n".join([
        f"## {spoof_title}",
        "",
        "### 功能说明", "x",
        "### 操作步骤（命令与参数）", "x",
        "### 预期现象", "x",
        "",
    ])
    return t.replace("\n## 0. 总章", "\n" + merged + "\n## 0. 总章", 1)


@pytest.mark.parametrize("spoof_title", ["一键测评与AI 认干扰", "3.一键测评与AI 认干扰", "3. 一键测评与AI 认干扰"])
def test_b42_redo_merged_chapter_spoof_detected(tmp_path, spoof_title):
    manual_p, readme_p = _write_pair(tmp_path, _spoof_manual(spoof_title))
    r = check_demo_manual(manual_p, readme_p, _EXPECTED)
    assert "一键测评" in r["missing_entries"] and "AI 认干扰" in r["missing_entries"]
    assert r["tier_regression"] == []  # 三件套拼接章无档词——防回潮族不误报


# B42 重走 I1/I2 加固锚（v2 迁移）
def test_b42_redo_mixed_fence_spoof_detected(tmp_path):
    """混合围栏（``` 开 ~~~ 关）内的伪章必须算未交付（重走 I1）。

    v2 迁移：混合围栏内的档词同时不触发防回潮——围栏态全文件连续+同型闭合，
    按章切片重置态会把跨章围栏体误判为可见（本用例即该形态的回归锚）。
    """
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
    assert r["tier_regression"] == [], "混合围栏内的档词不算回潮命中（同型闭合）"


def test_b42_redo_html_comment_tier_spoof_ignored(tmp_path):
    """HTML 注释里的档词不算回潮命中（重走 I2 的 v2 迁移——不可见内容不参与判定）。"""
    broken = _COMPLETE_MANUAL.replace(
        "一条命令跑完干扰测评全流程。",
        "一条命令跑完干扰测评全流程。\n\n<!-- 便携档 全量档 -->",
    )
    assert _tier_hit_lines(broken), "fixture 手术失败（注释档词未注入）"
    manual_p, readme_p = _write_pair(tmp_path, broken)
    r = check_demo_manual(manual_p, readme_p, _EXPECTED)
    assert r["tier_regression"] == [], "HTML 注释档词必须剥离（不触发防回潮）"
    assert r["ok"] is True
