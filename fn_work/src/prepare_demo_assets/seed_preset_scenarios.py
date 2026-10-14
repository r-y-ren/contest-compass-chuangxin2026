"""预置演示场景写入（R76 L1）：内置演示场景模板集（与手册总章清单一一对应）写为 YAML；文件已存在且内容不同计冲突不覆盖——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

from pathlib import Path

__all__ = ["seed_preset_scenarios"]


def seed_preset_scenarios(scenario_dir: str | Path, *, overwrite: bool = False) -> dict:
    """写入预置场景集。

    输入: 目标目录（+overwrite 授权覆盖）。
    输出: {"written": [文件名...], "conflicts": [文件名...]}。
    错误: 目录不可写→上抛。
    """
    raise NotImplementedError("unimplemented:fn:seed_preset_scenarios")
