"""全局模型目录解析（R107）——重写规约与签名意图详见 fn_docs/responsibility.md 共享函数节。"""
from __future__ import annotations

from pathlib import Path

__all__ = ["resolve_models_dir"]


def resolve_models_dir(repo_root=None):
    """解析全局模型目录 fn_work/models（仓库根锚定，cwd 无关）。

    输入: 可选仓库根 / 输出: Path / 错误: 目录创建失败→OSError。
    """
    raise NotImplementedError("unimplemented:fn:resolve_models_dir")
