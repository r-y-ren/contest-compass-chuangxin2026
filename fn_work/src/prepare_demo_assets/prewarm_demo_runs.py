"""预跑演示历史运行（R76 L1）：按配置逐轮走 run_demo 既有入口落 runs/（含带标注 SigMF 录音供录音库/AI 页翻阅）；--demo 口径 exit 1=测到失效属预期产出；单轮意外失败即中止不吞错——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

from pathlib import Path

__all__ = ["prewarm_demo_runs"]


def prewarm_demo_runs(scenarios: list[str], runs_root: str | Path, *, rounds: int = 3) -> dict:
    """预跑历史运行。

    输入: 场景名清单+runs_root+轮次配置。
    输出: {"runs": [(运行目录, 退出码)...]}。
    错误: 意外退出码→中止并列已跑清单。
    """
    raise NotImplementedError("unimplemented:fn:prewarm_demo_runs")
