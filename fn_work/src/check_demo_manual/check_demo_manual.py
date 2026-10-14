"""手册结构体检（R84 L0，承载 R76–R84 各批自检）：期望条目集齐/每条目四件套与两档标注齐/零占位残留/附录应急表覆盖 README 常见问题全部条目——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

from pathlib import Path

__all__ = ["check_demo_manual"]


def check_demo_manual(manual_path: str | Path, readme_path: str | Path, expected_entries: list[str]) -> dict:
    """手册结构体检。

    输入: 手册路径+README 路径+期望条目清单（按已交付批登记增长）。
    输出: {"ok": bool, "missing_entries": [...], "missing_sections": [...], "placeholders": [...], "faq_uncovered": [...], "passed": int}。
    错误: 手册或 README 文件缺失→上抛。
    """
    raise NotImplementedError("unimplemented:fn:check_demo_manual")
