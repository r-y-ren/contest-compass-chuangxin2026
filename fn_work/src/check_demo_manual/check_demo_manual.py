"""手册结构体检（R84 L0，承载 R76–R84 各批自检）：期望条目集齐/每条目四件套与两档标注齐/零占位残留/附录应急表覆盖 README 常见问题全部条目。
    已知限界：条目匹配为子串级——章名拼接（如「A 与 B」一章可同时顶替 A/B 两期望条目）可伪覆盖，全等匹配加固留 B42（B35 对抗 F3 登记）。
    重写规约与签名意图详见 fn_docs/responsibility.md。

体检口径（R84；手册=docs/功能演示手册.md，FAQ 源=fn_docs/README.md「常见问题」）：

- 断言族一（期望条目集齐）：expected_entries 每个名字须在手册里有一个二级标题
  （^## 开头）包含该名字——期望集按已交付批登记（R77–R83 各批验收即本函数
  按批增长的期望集执行）；缺条目点名。**同名多章全审**（B32 M3 加固）：条目
  审计在全部含名二级标题章上做，不止首个——防前章为全章掩盖后章残缺（或前
  章为伪章）；任一命中章缺件即入 missing_sections（缺件章条目名可重名并列），
  全部命中章齐件才计 passed。
- 断言族二（四件套小节齐）：条目章（该条目二级标题到下一个二级标题）内须有
  四个三级标题（^###），分别含关键词 功能说明/所需设备与连线/操作步骤/预期现象。
- 断言族三（两档标注）：每个「所需设备与连线」小节内须同时出现「便携档」与
  「全量档」（小节体=该三级标题到下一任意层级标题；**围栏内词不算数**——B32
  M3 加固：小节体先剥离代码围栏（```/~~~ 块）再查两档词，防命令注释里的档名
  伪达标；B33 对抗 F3：围栏识别允许 0–3 空格缩进——缩进围栏内词同样不算数；
  4 空格缩进代码块本库手册不使用，限界不处理）；缺档记
  ``所需设备与连线:<档名>`` 入 missing_sections——无专字段，如实并入缺件清单）。
- 断言族四（零占位）：全文不得出现 待定/TODO/TBD/占位/待补充——注意**不匹配
  「待实测」**（平台合法口径词，README 标定演示条目明文使用）。
- 断言族五（FAQ 覆盖）：解析 README「常见问题」无序列表每个问题，手册附录
  「应急速查表」区（每个含「应急」的标题起到下一同级标题）须每条至少一行命中，
  且命中行必须是**表格行**（| 起始——B32 M3 加固：散文单行恰好复述 FAQ 症状
  短语不算覆盖）；且应急区先剥离代码围栏再收表格行（B33 对抗 F2 加固——
  围栏内的 | 行是示例表格源码，不算覆盖行）。匹配口径取保守实现：FAQ 整条
  文本去标点（剔一切非 \\w 字符）后的前 12 个字符为键，应急区表格行按同口径
  去标点后含该键即算覆盖——即应急表须逐字回应 FAQ 症状短语，而非仅同义词呼应。
- 分节归属：条目章边界=条目二级标题→下一个二级标题；标题解析跳过代码围栏
  （```/~~~ 行首、允许 0–3 空格缩进（B33 对抗 F3）——围栏内的 # 行不算标题，
  防命令注释伪标题截断章节）。

报告（六键）：
``ok``（四清单全空）、``missing_entries``（缺条目名清单）、``missing_sections``
（``{"entry": 名, "missing": [缺件...]}``——缺件含四件套关键词与
``所需设备与连线:<档名>`` 两档缺记）、``placeholders``（``<词>@L<行号>``
清单）、``faq_uncovered``（未覆盖 FAQ 的 12 字符键清单）、``passed``
（全过条目数=在册且四件套+两档齐的条目计数；FAQ/占位族不计数）。

本函数**只读不写**：手册或 README 文件缺失→上抛 FileNotFoundError；结构
缺件不抛——返回清单由调用方（pytest/验收命令）消费。
"""
from __future__ import annotations

import re
from pathlib import Path

__all__ = ["check_demo_manual"]

#: 任意层级标题行（`^#{1,6} 空格`——章/小节切分依据；围栏内行除外）。
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")

#: 代码围栏（```/~~~ 行首、允许 0–3 空格缩进——围栏开合切换，围栏内行不作
#: 标题解析/不参与小节体与应急区行收集；B33 对抗 F3：旧口径仅认顶格围栏，
#: 1–3 空格缩进围栏绕过剥离，围栏内词伪达标）。4 空格及以上缩进=markdown
#: 缩进代码块（非围栏），本库手册写法不使用——登记为限界，不作围栏处理。
_FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")

#: FAQ 无序列表项（「常见问题」节内 ^-/* 空格 起始行）。
_FAQ_ITEM_RE = re.compile(r"^\s*[-*]\s+(.+)$")

#: 标点清洗（剔一切非 \\w 字符——FAQ 键与应急表行匹配两侧同口径归一化）。
_STRIP_NON_WORD_RE = re.compile(r"[^\w]+")

#: 四件套小节关键词（断言族二——章内三级标题须逐一含之）。
_SECTION_KEYWORDS: tuple[str, ...] = ("功能说明", "所需设备与连线", "操作步骤", "预期现象")

#: 两档标注（断言族三——「所需设备与连线」小节体内须同时出现）。
_TIER_MARKS: tuple[str, ...] = ("便携档", "全量档")

#: 占位残留词（断言族四——不含合法口径词「待实测」）。
_PLACEHOLDER_TOKENS: tuple[str, ...] = ("待定", "TODO", "TBD", "占位", "待补充")

#: FAQ 覆盖键长（FAQ 整条去标点后的前 N 字符——保守覆盖口径）。
_FAQ_KEY_LEN = 12

#: 附录应急速查表标题针（含该词的标题起始到下一同级标题为应急表区）。
_EMERGENCY_MARKER = "应急"

#: README 常见问题节标题针。
_FAQ_SECTION_TITLE = "常见问题"


def check_demo_manual(manual_path: str | Path, readme_path: str | Path, expected_entries: list[str]) -> dict:
    """手册结构体检。

    输入: 手册路径+README 路径+期望条目清单（按已交付批登记增长）。
    输出: {"ok": bool, "missing_entries": [...], "missing_sections": [...], "placeholders": [...], "faq_uncovered": [...], "passed": int}。
    错误: 手册或 README 文件缺失→上抛 FileNotFoundError。
    """
    manual = Path(manual_path)
    readme = Path(readme_path)
    if not manual.is_file():
        raise FileNotFoundError(f"手册缺失: {manual}")
    if not readme.is_file():
        raise FileNotFoundError(f"README 缺失: {readme}")

    manual_lines = manual.read_text(encoding="utf-8").splitlines()
    manual_headings = _scan_headings(manual_lines)

    # 断言族一+二+三：逐期望条目检章在册（同名多章全审）、四件套齐、两档标注齐。
    missing_entries: list[str] = []
    missing_sections: list[dict] = []
    passed = 0
    for name in expected_entries:
        chapters = _find_chapters(manual_headings, name)
        if not chapters:
            missing_entries.append(name)
            continue
        # 同名多章全审：任一命中章缺件即记（重名章的缺件并列，互不掩盖），
        # 全部命中章齐件才计 passed（条目计数口径——非章计数）。
        chapter_bits: list[list[str]] = []
        for chapter in chapters:
            bits = _audit_chapter(manual_headings, manual_lines, chapter)
            if bits:
                chapter_bits.append(bits)
        if chapter_bits:
            for bits in chapter_bits:
                missing_sections.append({"entry": name, "missing": bits})
        else:
            passed += 1

    # 断言族四：全文占位残留（含围栏内——手册面向演示者，任何位置残留都算）。
    placeholders = _scan_placeholders(manual_lines)

    # 断言族五：README 常见问题逐条对应急速查表区做保守键覆盖。
    faq_uncovered = _audit_faq_coverage(manual_headings, manual_lines, readme)

    ok = not (missing_entries or missing_sections or placeholders or faq_uncovered)
    return {
        "ok": ok,
        "missing_entries": missing_entries,
        "missing_sections": missing_sections,
        "placeholders": placeholders,
        "faq_uncovered": faq_uncovered,
        "passed": passed,
    }


def _scan_headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """围栏外标题清单 [(行号, 层级, 标题), ...]——代码围栏内的 # 行不算标题。"""
    out: list[tuple[int, int, str]] = []
    in_fence = False
    for idx, raw in enumerate(lines):
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(raw)
        if m:
            out.append((idx, len(m.group(1)), m.group(2).strip()))
    return out


def _strip_fenced(lines: list[str]) -> list[str]:
    """剥离代码围栏块（```/~~~ 开合区连同围栏行本身，允许 0–3 空格缩进），返回围栏外行清单。

    两档词族（族三）小节体检查与应急区表格行收集（族五，B33 对抗 F2）使用
    ——防围栏内命令注释的档名/围栏内示例表格伪达标（B32 M3 加固）；占位族
    （族四）全文扫描**仍含围栏内**（手册面向演示者，任何位置残留都算）——
    各族口径独立，本函数不改动其他族行为。
    """
    out: list[str] = []
    in_fence = False
    for raw in lines:
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        out.append(raw)
    return out


def _end_line(headings: list[tuple[int, int, str]], pos: int, level: int, total: int) -> int:
    """从 headings[pos] 起下一个同级或更高级标题的行号（无则文末 total）——章/小节边界。"""
    for idx, lvl, _title in headings[pos + 1 :]:
        if lvl <= level:
            return idx
    return total


def _find_chapters(headings: list[tuple[int, int, str]], name: str) -> list[tuple[int, int]]:
    """定位含条目名的**全部**二级标题，返回各章行区间 [起始行, 终止行) 清单；未命中返回空。

    不止取首个（B32 M3 加固）：同名多章或前章为伪章时，首匹配会让后章残缺
    被掩盖——调用方须逐章审计（缺件章并列入 missing_sections）。
    全等匹配（B42 加固，B35 F3 登记）：期望条目与章的契约是标题剥序号后**全等**
    （"## N. <名>"）——拼接章（"## 5. A 与 B"）不再顶替任何条目：无全等章即
    missing_entry，由调用方点名。子串匹配仅在无序号形态的非常规章上作回退。
    """
    exact: list[tuple[int, int]] = []
    substr: list[tuple[int, int]] = []
    for pos, (idx, level, title) in enumerate(headings):
        if level != 2 or name not in title:
            continue
        # 终止行取大数即可：返回值仅作 lines 切片上界，Python 切片自钳。
        span = (idx, _end_line(headings, pos, 2, 10**9))
        stripped = title.strip().lstrip('#').strip()
        # 序号剥除兼容 "N. " 与 "N."（无空格）两种形态（终门 M2：后者曾绕过）
        _seqless = re.split(r"^\d+\.\s*", stripped, maxsplit=1)
        _seqless = _seqless[1] if len(_seqless) == 2 else stripped
        # 全等 或 "条目名+括注后缀"（如「国标测法自动化（GB 42590 §5.11）」）；
        # 拼接章（「A 与 B」）的连接词后缀不算括注 → 不入 exact。
        _is_exact = _seqless == name or (
            _seqless.startswith(name)
            and len(_seqless) > len(name)
            and _seqless[len(name)] in "（(【["
        )
        (exact if _is_exact else substr).append(span)
    if exact:
        return exact
    # 回退：无序号/无空格序号形态的章，标题剥序号后须与条目名全等才收
    #（终门 M2：子串回退曾被无序号拼接章绕过——回退同权全等契约）
    return []


def _audit_chapter(
    headings: list[tuple[int, int, str]], lines: list[str], chapter: tuple[int, int]
) -> list[str]:
    """条目章内四件套+两档标注体检；返回缺件清单（空=全过）。

    缺件形态：四件套缺→关键词本身；两档缺→``所需设备与连线:<档名>``（小节
    本身缺失时不重复点名两档——缺小节已含其义；小节体查两档词前剥离代码
    围栏——围栏内命令注释的档名不算数，B32 M3 加固）。
    """
    start, end = chapter
    missing: list[str] = []
    dev_pos: int | None = None
    for kw in _SECTION_KEYWORDS:
        pos = _find_h3(headings, chapter, kw)
        if pos is None:
            missing.append(kw)
        elif kw == "所需设备与连线":
            dev_pos = pos
    if dev_pos is not None:
        h_start = headings[dev_pos][0]
        h_end = _end_line(headings, dev_pos, 3, len(lines))
        body = "\n".join(_strip_fenced(lines[h_start + 1 : h_end]))  # +1 跳过标题行（终门 M3：标题自含两档词曾自满足）
        for tier in _TIER_MARKS:
            if tier not in body:
                missing.append(f"所需设备与连线:{tier}")
    return missing


def _find_h3(headings: list[tuple[int, int, str]], chapter: tuple[int, int], kw: str) -> int | None:
    """章内定位含关键词的首个三级标题（返回 headings 下标）；越出章界即未命中。"""
    start, end = chapter
    for pos, (idx, level, title) in enumerate(headings):
        if idx < start:
            continue
        if idx >= end:
            return None
        if level == 3 and kw in title:
            return pos
    return None


def _scan_placeholders(lines: list[str]) -> list[str]:
    """全文占位残留扫描：命中的词按 ``<词>@L<行号>`` 记（同词同行只记一次）。"""
    hits: list[str] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(lines, start=1):
        for token in _PLACEHOLDER_TOKENS:
            if token in raw:
                entry = f"{token}@L{lineno}"
                if entry not in seen:
                    seen.add(entry)
                    hits.append(entry)
    return hits


def _emergency_lines(
    headings: list[tuple[int, int, str]], lines: list[str]
) -> list[str]:
    """附录应急速查表区**表格行**（| 起始）：每个含「应急」的标题起到下一同级标题。

    只收表格行（B32 M3 加固）——散文单行恰好复述 FAQ 症状短语不算覆盖，
    防正文段落伪达标；且应急区文本先剥离代码围栏（与族三同法复用
    _strip_fenced——B33 对抗 F2 加固）：围栏内的 | 行（示例表格源码/命令
    注释里的伪表格行）不算覆盖行，防围栏内表格伪达标；多区拼接。
    """
    out: list[str] = []
    for pos, (idx, level, title) in enumerate(headings):
        if _EMERGENCY_MARKER in title:
            region = lines[idx : _end_line(headings, pos, level, len(lines))]
            out.extend(raw for raw in _strip_fenced(region) if raw.startswith("|"))
    return out


def _parse_faq_items(readme_text: str) -> list[str]:
    """README「常见问题」无序列表条目文本（该标题直接下挂的列表项，止于下一任意层级标题）。"""
    lines = readme_text.splitlines()
    headings = _scan_headings(lines)
    for pos, (idx, level, title) in enumerate(headings):
        if level == 2 and _FAQ_SECTION_TITLE in title:
            stop = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
            items = []
            for raw in lines[idx + 1 : stop]:
                m = _FAQ_ITEM_RE.match(raw)
                if m:
                    items.append(m.group(1).strip())
            return items
    return []


def _audit_faq_coverage(
    headings: list[tuple[int, int, str]], lines: list[str], readme: Path
) -> list[str]:
    """FAQ 覆盖审计：每条 FAQ 去标点前 12 字符为键，应急区表格行（| 起始）同口径含之即覆盖。"""
    emergency = _emergency_lines(headings, lines)
    normalized_rows = [_normalize(raw) for raw in emergency]
    uncovered: list[str] = []
    for item in _parse_faq_items(readme.read_text(encoding="utf-8")):
        key = _normalize(item)[:_FAQ_KEY_LEN]
        if key and not any(key in row for row in normalized_rows):
            uncovered.append(key)
    return uncovered


def _normalize(text: str) -> str:
    """去标点归一化：剔一切非 \\w 字符（空白/中西标点/markdown 符号均除）。"""
    return _STRIP_NON_WORD_RE.sub("", text)
