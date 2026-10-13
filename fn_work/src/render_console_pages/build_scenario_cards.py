"""场景目录→卡片数据（损坏场景跳过标注）——重写规约与签名意图详见 fn_docs/responsibility.md。

轻量口径（不整套跑 load_scenario 的 schema/红线——那是装载路径的事）：
- name=文件名去扩展名；desc 优先取首见 `# desc: ...` 注释行，回退顶层 `desc:` 键
  （style/desc 值先剥行内注释——' # ' 起的尾部内容与首尾空白）；
- style_tags 取 `style:` 行值按 `,`/`/`/`;` 切分小写化（内联 [a, b] 括号剥掉），
  缺失→['unknown']；
- backend_hint 取 `backend:` 行值小写化，缺省 'sim'；
- risk：`# risk: low|mid` 注释显式覆盖优先；否则按 power_dbm 分档——高于
  -10 dBm（保守缺省档）标 'mid'，其余（含缺省/缺功率）'low'；
- 损坏场景（不可读/非 UTF-8/路径非 str）不炸整批：占位卡 {'name', 'error': 原因}，
  列表长度与输入一致（前端逐卡标注）。
"""
from __future__ import annotations

import os
import re

__all__ = ["build_scenario_cards"]

#: 风险分界（dBm）：power_dbm 高于该档（保守缺省 -10）标 'mid'。
_RISK_POWER_THRESHOLD_DBM = -10.0

# 注释行元数据：`# desc: ...` / `# risk: low|mid`（大小写宽容，首个命中生效）。
_DESC_COMMENT_RE = re.compile(r"^#\s*desc\s*:\s*(.+?)\s*$", re.IGNORECASE)
_RISK_COMMENT_RE = re.compile(r"^#\s*risk\s*:\s*(low|mid)\s*$", re.IGNORECASE)

# style 标签切分符：逗号/斜杠/分号（YAML 内联列表 [a, b] 先剥括号）。
_TAG_SPLIT_RE = re.compile(r"[,/;]")

# 行内注释（YAML 口径：'#' 前有空白即注释起点，如 `style: tone  # 六类`）——
# 卡片轻量解析不跑 PyYAML，须自行剥除，否则注释文本混入 style/desc 值。
_INLINE_COMMENT_RE = re.compile(r"\s+#.*$")


def _strip_inline_comment(value: str) -> str:
    """剥行内注释（' # ' 起的尾部内容，无前置空白的 '#' 不动）与首尾空白。"""
    return _INLINE_COMMENT_RE.sub("", value).strip()


def _parse_tags(value: str) -> list:
    """style 行值→小写标签列表：剥引号/内联括号后按分隔符切分，空段丢弃。"""
    text = value.strip().strip("'\"").strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    tags = [t.strip().strip("'\"").lower() for t in _TAG_SPLIT_RE.split(text)]
    return [t for t in tags if t]


def _scalar_float(text: str) -> float | None:
    """尽力数值化（power_dbm 分档用）；失败→None 不视为损坏。"""
    try:
        return float(text.strip().strip("'\""))
    except (TypeError, ValueError):
        return None


def _card_for_file(path: object) -> dict:
    """单场景文件→卡片；读取/解码失败→占位 error 卡（不抛出）。"""
    if not isinstance(path, str):
        return {"name": str(path), "error": f"路径必须为 str，实际 {type(path).__name__}"}
    name = os.path.splitext(os.path.basename(path))[0]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return {"name": name, "error": f"{type(exc).__name__}: {exc}"}

    desc = ""
    style_tags: list | None = None
    backend_hint = ""
    power_dbm: float | None = None
    risk_override: str | None = None

    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):  # 注释元数据（desc/risk 显式覆盖）
            m = _DESC_COMMENT_RE.match(stripped)
            if m and not desc:
                desc = _strip_inline_comment(m.group(1))
            m = _RISK_COMMENT_RE.match(stripped)
            if m and risk_override is None:
                risk_override = m.group(1).lower()
            continue
        if ":" not in stripped:  # 与卡片无关的行（列表项/杂行）直接略过
            continue
        key, _, rest = stripped.partition(":")
        key = key.strip().strip("'\"").lower()
        rest = rest.strip()
        if key == "desc" and not desc:
            desc = _strip_inline_comment(rest).strip("'\"")
        elif key == "style" and style_tags is None:
            style_tags = _parse_tags(_strip_inline_comment(rest)) or None
        elif key == "backend" and not backend_hint:
            backend_hint = rest.strip("'\"").lower()
        elif key == "power_dbm" and power_dbm is None:
            power_dbm = _scalar_float(rest)

    if risk_override is not None:
        risk = risk_override
    else:
        risk = (
            "mid"
            if power_dbm is not None and power_dbm > _RISK_POWER_THRESHOLD_DBM
            else "low"
        )
    return {
        "name": name,
        "desc": desc,
        "style_tags": style_tags if style_tags is not None else ["unknown"],
        "risk": risk,
        "backend_hint": backend_hint or "sim",
    }


def build_scenario_cards(scenario_files: list) -> list:
    """场景文件列表→卡片数据列表（前端渲染用，轻量解析不跑 schema/红线）。

    Args:
        scenario_files: 场景文件路径列表（通常 *.yaml/*.yml）。

    Returns:
        卡片 dict 列表，逐文件对应：正常→{'name','desc','style_tags','risk',
        'backend_hint'}；损坏（不可读/非 UTF-8）→{'name','error': 原因} 占位卡。

    Raises:
        ValueError: scenario_files 非 list（空 list 合法→[]）。
    """
    if not isinstance(scenario_files, list):
        raise ValueError(
            f"scenario_files 必须为 list[str]，实际收到 {type(scenario_files).__name__}: "
            f"{scenario_files!r}"
        )
    return [_card_for_file(path) for path in scenario_files]
