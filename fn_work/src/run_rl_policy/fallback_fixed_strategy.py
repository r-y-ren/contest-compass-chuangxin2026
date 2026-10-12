"""固定策略回退（不学习，永有可执行路径）——重写规约与签名意图详见 fn_docs/responsibility.md（R54 叶子；调用方 run_rl_policy）。

落地口径：

- 计划联动：``scenario['ladder_params']``（可选 dict，缺省 None→{}）+
  ``link_power_db``（取 ``scenario['link_power_db']``，缺省 0）原样透传
  ``plan_ladder_steps``（GB 42590 §5.11：−5dB 起、5dB 步、0dBm 红线截断）；
- 动作序列：计划每档展开为 ``{**rung, 'action': 'emit', 'style':
  scenario['style']}``——保留 rung 的 step/target_db/relative_db/note 溯源字段；
- 空场景（``{}``）→ 空动作序列 ``[]``（无样式可发即无动作）；
- 形状错 ValueError：scenario 非 dict/非空却缺 'style' 或 style 非非空 str/
  ladder_params 非 dict|None/link_power_db 为 bool/非实数/NaN/±inf；
- ``plan_ladder_steps`` 的 PlanError（链路功率高于 0dBm 红线等计划域错误）
  原样透传——域错误不是形状错误。
"""
from __future__ import annotations

import math
from numbers import Real

from src.run_power_ladder.plan_ladder_steps import plan_ladder_steps

__all__ = ["fallback_fixed_strategy"]

#: 缺省被测链路发射功率（dBm）：场景未给即以 0dBm 口径出 GB 计划。
_DEFAULT_LINK_POWER_DB = 0.0


def fallback_fixed_strategy(scenario: dict) -> list:
    """固定策略回退：场景样式×GB 功率阶梯计划 → 固定动作序列（不学习）。

    Args:
        scenario: ``{'style': 非空 str, 'ladder_params': dict|可选,
        'link_power_db': 实数|可选（缺省 0）}``；空 dict → ``[]``。

    Returns:
        ``[{**plan_ladder_steps 档位, 'action': 'emit', 'style': ...}, ...]``
        ——档位含 'step'/'target_db'/'relative_db'/'note'；红线截断口径由
        plan_ladder_steps 决定（GB 缺省 link=0 时为 −5/0 两档）。

    Raises:
        ValueError: scenario 形状错（详见模块 docstring）。
        PlanError: plan_ladder_steps 计划域错误（如 link_power_db>0 越红线）。
    """
    if not isinstance(scenario, dict):
        raise ValueError(
            f"scenario 必须为 dict（策略场景），实际: {type(scenario).__name__}"
        )
    if not scenario:
        return []  # 空场景：无样式可发——空动作序列（永有可执行路径的退化态）

    style = scenario.get("style")
    if not isinstance(style, str) or not style:
        raise ValueError(
            f"scenario['style'] 必须为非空 str（固定策略要发的干扰样式），得到 {style!r}"
        )

    ladder_params = scenario.get("ladder_params")
    if ladder_params is None:
        ladder_params = {}
    if not isinstance(ladder_params, dict):
        raise ValueError(
            f"scenario['ladder_params'] 必须为 dict | None（透传 plan_ladder_steps），"
            f"实际: {type(ladder_params).__name__}"
        )

    link_raw = scenario.get("link_power_db", _DEFAULT_LINK_POWER_DB)
    if isinstance(link_raw, bool) or not isinstance(link_raw, Real):
        raise ValueError(
            f"scenario['link_power_db'] 必须为实数（bool/非数值拒绝），得到 {link_raw!r}"
        )
    link = float(link_raw)
    if not math.isfinite(link):
        raise ValueError(f"scenario['link_power_db'] 必须为有限数（拒 NaN/±inf）：{link_raw!r}")

    plan = plan_ladder_steps(link, ladder_params)
    return [{**rung, "action": "emit", "style": style} for rung in plan["steps"]]
