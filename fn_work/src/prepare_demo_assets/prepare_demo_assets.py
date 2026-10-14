"""演示物料准备编排（R76 L0）：seed_preset_scenarios 预置场景 → prewarm_demo_runs 预跑 sim 历史（含 record:true 录音）→ 汇总物料报告与出发检查单数据；幂等不覆盖——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

from pathlib import Path

__all__ = ["prepare_demo_assets"]


def prepare_demo_assets(
    scenario_dir: str | Path,
    runs_root: str | Path,
    *,
    overwrite: bool = False,
    rounds: int = 3,
) -> dict:
    """编排演示前准备物料。

    输入: scenario_dir/runs_root 目标目录；overwrite=False 幂等；rounds 预跑轮次配置。
    输出: 物料报告（写入场景清单+预跑运行目录列表+各轮退出码+出发检查单数据）。
    错误: 目录冲突未授权覆盖→拒绝并列冲突项。
    """
    raise NotImplementedError("unimplemented:fn:prepare_demo_assets")
