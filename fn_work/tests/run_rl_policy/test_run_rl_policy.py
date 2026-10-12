"""run_rl_policy 对抗单测：slug=rl_policy——fallback GB 计划联动+动作序列+空场景+形状错；RL 玩具 env（4 状态 3 动作可学任务）收敛+不收敛回退 fallback_used+episodes 透传+env step 抛 PolicyError+形状错。"""
from __future__ import annotations

import pytest

from src.run_power_ladder.plan_ladder_steps import plan_ladder_steps
from src.run_rl_policy.fallback_fixed_strategy import fallback_fixed_strategy
from src.run_rl_policy.run_rl_policy import PolicyError, run_rl_policy


# --- fallback_fixed_strategy：固定动作序列（GB 计划联动） ---


def test_rl_policy_fallback_gb_plan_linkage_and_action_sequence():
    """GB 计划联动：动作序列与 plan_ladder_steps 同档，每档附 action/style。"""
    scenario = {"style": "chirp", "link_power_db": -10.0}
    actions = fallback_fixed_strategy(scenario)
    plan = plan_ladder_steps(-10.0, {})
    assert [a["target_db"] for a in actions] == [s["target_db"] for s in plan["steps"]]
    assert [a["step"] for a in actions] == [0, 1, 2, 3]  # -15/-10/-5/0 后红线截断
    for action, rung in zip(actions, plan["steps"]):
        assert action["action"] == "emit"
        assert action["style"] == "chirp"
        assert action["relative_db"] == pytest.approx(rung["relative_db"])
        assert action["note"] == rung["note"]


def test_rl_policy_fallback_default_link_power_zero_two_rungs():
    """缺省 link_power=0：GB 口径 −5/0 两档（0dBm 红线截断）。"""
    actions = fallback_fixed_strategy({"style": "pulse"})
    assert [a["target_db"] for a in actions] == [-5.0, 0.0]
    assert all(a["action"] == "emit" and a["style"] == "pulse" for a in actions)


def test_rl_policy_fallback_custom_ladder_params():
    """自定义 ladder_params：透传计划口径（custom note+stop 钳位档）。"""
    actions = fallback_fixed_strategy(
        {"style": "noise", "link_power_db": 0.0, "ladder_params": {"stop_db": -1.0}}
    )
    plan = plan_ladder_steps(0.0, {"stop_db": -1.0})
    assert [a["target_db"] for a in actions] == [s["target_db"] for s in plan["steps"]]
    assert actions[-1]["note"] == "custom"
    assert actions[-1]["target_db"] == pytest.approx(-1.0)


def test_rl_policy_fallback_empty_scenario_returns_empty():
    """空场景 → 空动作序列。"""
    assert fallback_fixed_strategy({}) == []


def test_rl_policy_fallback_shape_errors():
    """形状错 ValueError：非 dict/缺 style/style 非非空 str/ladder_params 非 dict/link 非实数。"""
    with pytest.raises(ValueError):
        fallback_fixed_strategy(None)
    with pytest.raises(ValueError):
        fallback_fixed_strategy(["style"])
    with pytest.raises(ValueError):
        fallback_fixed_strategy({"ladder_params": {}})  # 非空却缺 style
    with pytest.raises(ValueError):
        fallback_fixed_strategy({"style": 3})
    with pytest.raises(ValueError):
        fallback_fixed_strategy({"style": ""})
    with pytest.raises(ValueError):
        fallback_fixed_strategy({"style": "tone", "ladder_params": "gb"})
    with pytest.raises(ValueError):
        fallback_fixed_strategy({"style": "tone", "link_power_db": "high"})
    with pytest.raises(ValueError):
        fallback_fixed_strategy({"style": "tone", "link_power_db": float("nan")})


# --- run_rl_policy：numpy 表格式 Q-learning（sim 在环闭环） ---


class ChainEnv:
    """可学玩具 env：4 状态链、3 动作（进/退/停），reward=到达位置——向右学得动。"""

    def __init__(self, n=4):
        self.n = n

    def reset(self):
        self.pos = 0
        return self._state()

    def _state(self):
        return [float(self.pos), float(self.n - 1 - self.pos)]

    def step(self, action):
        if action == 0:
            self.pos = min(self.pos + 1, self.n - 1)
        elif action == 1:
            self.pos = max(self.pos - 1, 0)
        # action == 2: 原地
        return self._state(), float(self.pos), self.pos == self.n - 1


class FlatEnv:
    """不可学 env：动作无效、常数奖励 −1、4 步终止——均值零改善必不收敛。"""

    def reset(self):
        self.count = 0
        return [0.0]

    def step(self, action):
        self.count += 1
        return [float(self.count % 4)], -1.0, self.count >= 4


def test_rl_policy_toy_env_converges():
    """玩具 env（4 状态 3 动作可学任务）：converged、ql_table、Q 表形状 (4,3)。"""
    out = run_rl_policy(
        {"actions": 3, "episodes": 40, "seed": 7, "scenario": {"style": "tone"}},
        ChainEnv,
    )
    assert out["converged"] is True
    assert out["fallback_used"] is False
    assert out["policy"] == "ql_table"
    assert out["fallback_plan"] == []
    assert tuple(out["q_table_shape"]) == (4, 3)
    assert out["episodes"] == 40
    # 训练曲线如实记录：后一半均值（final_reward_mean）优于前一半
    half = 20
    hist = out["reward_history"]
    assert len(hist) == 40
    first = sum(hist[:half]) / half
    assert out["final_reward_mean"] == pytest.approx(sum(hist[-half:]) / half)
    assert out["final_reward_mean"] > first


def test_rl_policy_nonconverging_env_falls_back_to_fixed_strategy():
    """不收敛 env：fallback_used=True、policy=fallback_fixed、计划为可执行 emit 动作。"""
    out = run_rl_policy(
        {
            "actions": 2,
            "episodes": 12,
            "seed": 3,
            "scenario": {"style": "noise", "link_power_db": -10.0},
        },
        FlatEnv,
    )
    assert out["converged"] is False
    assert out["fallback_used"] is True
    assert out["policy"] == "fallback_fixed"
    assert out["final_reward_mean"] == pytest.approx(-4.0)  # 每 episode 恒 −4
    plan = out["fallback_plan"]
    assert len(plan) == 4  # plan_ladder_steps(-10) GB：-15/-10/-5/0
    assert all(a["action"] == "emit" and a["style"] == "noise" for a in plan)


def test_rl_policy_episodes_passthrough():
    """episodes 透传：训练曲线长度=episodes、返回 episodes 同值。"""
    out = run_rl_policy({"episodes": 7, "actions": 2, "seed": 1}, FlatEnv)
    assert out["episodes"] == 7
    assert len(out["reward_history"]) == 7


def test_rl_policy_default_actions_six():
    """缺省动作数 6 档：Q 表列数=6。"""
    out = run_rl_policy({"episodes": 3, "seed": 0}, FlatEnv)
    assert out["n_actions"] == 6
    assert out["q_table_shape"][1] == 6


def test_rl_policy_env_step_raises_policy_error():
    """env step/reset 抛 → PolicyError（终止训练，附原文）。"""

    class BoomStep:
        def reset(self):
            return [0.0]

        def step(self, action):
            raise RuntimeError("sim crashed")

    with pytest.raises(PolicyError, match="sim crashed"):
        run_rl_policy({"episodes": 2, "actions": 2}, BoomStep)

    class BoomReset:
        def reset(self):
            raise OSError("sim dead")

        def step(self, action):
            return [0.0], 0.0, True

    with pytest.raises(PolicyError, match="sim dead"):
        run_rl_policy({"episodes": 2, "actions": 2}, BoomReset)


def test_rl_policy_env_factory_raises_policy_error():
    """env_factory 本身抛 → PolicyError（环境异常终止训练）。"""
    def bad_factory():
        raise RuntimeError("no backend")

    with pytest.raises(PolicyError, match="no backend"):
        run_rl_policy({"episodes": 2}, bad_factory)


def test_rl_policy_shape_errors():
    """形状错 ValueError：train_config 非 dict/env_factory 不可调用/env 缺方法/超参域错/状态非数值。"""
    with pytest.raises(ValueError):
        run_rl_policy(["cfg"], ChainEnv)
    with pytest.raises(ValueError):
        run_rl_policy({}, "not-callable")
    with pytest.raises(ValueError):
        run_rl_policy({}, lambda: {"reset": ChainEnv().reset})  # 缺 step
    with pytest.raises(ValueError):
        run_rl_policy({"episodes": 0}, ChainEnv)
    with pytest.raises(ValueError):
        run_rl_policy({"episodes": True}, ChainEnv)
    with pytest.raises(ValueError):
        run_rl_policy({"actions": 0}, ChainEnv)
    with pytest.raises(ValueError):
        run_rl_policy({"alpha": 2.0}, ChainEnv)
    with pytest.raises(ValueError):
        run_rl_policy({"seed": "seven"}, ChainEnv)

    class BadStateEnv:
        def reset(self):
            return "not-a-state"

        def step(self, action):
            return [0.0], 0.0, True

    with pytest.raises(ValueError):
        run_rl_policy({"episodes": 1, "actions": 2}, BadStateEnv)

    class BadTupleEnv:
        def reset(self):
            return [0.0]

        def step(self, action):
            return [0.0, 1.0]  # 非三元组

    with pytest.raises(ValueError):
        run_rl_policy({"episodes": 1, "actions": 2}, BadTupleEnv)


def test_rl_policy_default_scenario_for_fallback():
    """缺省回退场景：无 scenario 时用 style（缺省 noise）组默认场景出计划。"""
    out = run_rl_policy({"actions": 2, "episodes": 6, "seed": 5}, FlatEnv)
    assert out["fallback_used"] is True
    plan = out["fallback_plan"]
    assert len(plan) == 2  # 缺省 link=0：-5/0 两档
    assert all(a["style"] == "noise" and a["action"] == "emit" for a in plan)
