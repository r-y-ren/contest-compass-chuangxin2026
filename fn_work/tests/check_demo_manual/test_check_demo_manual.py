"""check_demo_manual 结构体检测试：完备通过/缺条目/缺四件套/缺两档/占位检出/FAQ 缺覆盖/文件缺失+真实手册冒烟。"""
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
## 功能演示：一键测评

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
## 功能演示：AI 认干扰

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


def _manual_with_emergency_rows(*rows: str) -> str:
    """组装 fixture 手册：2 条目章+附录（应急速查表行数可变——FAQ 覆盖用例的手术位）。"""
    appendix = (
        "## 附录：出发前检查单\n\n- 主机、充电器、U 盘。\n\n"
        "## 附录：现场应急速查表\n\n| 症状 | 处置 |\n| --- | --- |\n"
        + "\n".join(rows)
        + "\n"
    )
    return _HEADER + _CHAPTER_ONE + "\n" + _CHAPTER_TWO + "\n" + appendix


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
