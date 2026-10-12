"""D3QN 干扰策略 sim 在环闭环（不收敛回退固定策略）——重写规约与签名意图详见 fn_docs/responsibility.md（R54 顶层；调用方 CLI 入口/run_demo 策略场景可选）。

落地口径（轻量实现：不引 torch——numpy 表格式 Q-learning 承 D3QN 调度位）：

- 环境契约：``env_factory()`` → env（dict 或对象）含
  ``reset() → state``（离散化数值向量/标量）与
  ``step(action_idx) → (next_state, reward, done)``——sim 在环
  （open_sim_backend+simulate_link_degradation 族），仅 sim、不开放辐射；
- 动作空间：``train_config['actions']``（缺省 6 档——样式×档位子集的离散
  动作数）；状态动态登记（首次到达即入 Q 表，行以 N(0, 0.01) 随机初始化）；
- 训练：numpy Q 表+ε-greedy（ε 起始 1.0、衰减 0.9、下限 0.05）、
  α=0.5/γ=0.9 缺省可配，episodes（缺省 20，透传返回）；训练曲线
  （逐 episode 总奖励）如实记录进 ``reward_history``；
- 收敛判定：后一半 episodes 平均奖励比前一半改善（差 > 收敛容差）→
  ``converged=True``；不收敛 → ``fallback_fixed_strategy`` 兜底
  （scenario 取 ``train_config['scenario']``，缺省由 style/ladder_params/
  link_power_db 组装）——``fallback_used=True``、``policy='fallback_fixed'``；
- 错误：train_config/env 形状错 → ValueError；env_factory/reset/step 抛 →
  PolicyError（终止训练，附原文）；回退段的场景形状错由
  fallback_fixed_strategy 以 ValueError 透传。

返回：``{'q_table_shape': (n_states, n_actions), 'episodes', 'converged',
'final_reward_mean', 'fallback_used', 'policy': 'ql_table'|'fallback_fixed',
'reward_history', 'fallback_plan', 'n_states', 'n_actions'}``。
"""
from __future__ import annotations

import math
from numbers import Real

import numpy as np

from src.run_rl_policy.fallback_fixed_strategy import fallback_fixed_strategy

__all__ = ["PolicyError", "run_rl_policy"]

#: 训练轮数缺省与上限（防失控——配置巨额 episodes 直接拒）。
_DEFAULT_EPISODES = 20
_MAX_EPISODES = 100_000
#: 动作数缺省（样式×档位子集：6 档）。
_DEFAULT_ACTIONS = 6
_MAX_ACTIONS = 4096
#: 单 episode 步数上限缺省与上限。
_DEFAULT_MAX_STEPS = 50
_MAX_MAX_STEPS = 10_000
#: Q-learning 缺省超参。
_DEFAULT_ALPHA = 0.5  # 学习率（表格式可用较大步长加速收敛）
_DEFAULT_GAMMA = 0.9  # 折扣
_DEFAULT_EPSILON = 1.0  # ε-greedy 起始探索率
_EPSILON_MIN = 0.05  # 探索率下限（保底探索，防策略过早锁死）
_EPSILON_DECAY = 0.9  # 逐 episode 探索率衰减
#: 收敛容差：后一半均值 − 前一半均值 > 容差才判收敛（常数奖励环境差恰 0 → 不收敛）。
_CONVERGE_MARGIN = 1e-9


class PolicyError(Exception):
    """策略训练环境异常：env_factory/reset/step 抛错（终止训练，附原文）。"""


def _pos_int(value: object, name: str, cap: int) -> int:
    """正整数超参校验：拒 bool/非 int/≤0/超上限。"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} 必须为正 int（bool/非 int/≤0 拒绝），得到 {value!r}")
    if value > cap:
        raise ValueError(f"{name}={value} 超上限 {cap}（防失控）")
    return value


def _unit_interval(value: object, name: str, *, lo_inclusive: float, hi_inclusive: float) -> float:
    """[0,1] 族实数超参校验：拒 bool/非实数/NaN/±inf/越界。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} 必须为实数（bool/非数值拒绝），得到 {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} 必须为有限数（拒 NaN/±inf），得到 {value!r}")
    if not (lo_inclusive <= number <= hi_inclusive):
        raise ValueError(
            f"{name} 必须在 [{lo_inclusive:g}, {hi_inclusive:g}] 内，得到 {number!r}"
        )
    return number


def _state_key(state: object) -> tuple:
    """环境状态 → 可哈希离散键（数值向量/标量 → float 元组）。

    非数值状态/空向量/含 NaN/±inf → ValueError（环境契约形状错）。
    """
    if isinstance(state, (str, bytes, bool)) or state is None:
        raise ValueError(
            f"env 状态须为数值向量/标量（list/tuple/ndarray/number），得到 {state!r}"
        )
    try:
        arr = np.asarray(state, dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"env 状态须为数值向量/标量，无法解析: {state!r}") from exc
    if arr.size == 0:
        raise ValueError("env 状态向量不能为空")
    if not np.isfinite(arr).all():
        raise ValueError(f"env 状态含非有限值（NaN/±inf）: {state!r}")
    # 离散化口径：数值规整到 1e-9 网格再取元组（吸收浮点抖动，等值状态同一行）。
    return tuple(float(v) for v in np.round(arr / 1e-9))


def _env_methods(env: object):
    """env（dict 或鸭子类型对象）→ (reset, step) 可调用对；缺一即 ValueError。"""
    if isinstance(env, dict):
        reset, step = env.get("reset"), env.get("step")
    else:
        reset, step = getattr(env, "reset", None), getattr(env, "step", None)
    if not callable(reset) or not callable(step):
        raise ValueError(
            "env 必须含可调用 'reset'()→state 与 'step'(action_idx)→"
            f"(state, reward, done)，实际 reset={reset!r}, step={step!r}"
        )
    return reset, step


def run_rl_policy(train_config: dict, env_factory) -> dict:
    """sim 在环 Q-learning 干扰策略闭环（不收敛回退固定策略）。

    Args:
        train_config: 训练配置——``episodes``（缺省 20）、``actions``（缺省 6）、
            ``max_steps_per_episode``（缺省 50）、``alpha``（缺省 0.5）、
            ``gamma``（缺省 0.9）、``epsilon``（缺省 1.0）、``seed``（可选 int，
            复现实验）、``scenario``（回退场景 dict；缺省由 ``style``/
            ``ladder_params``/``link_power_db`` 组装）。
        env_factory: ``() → env``（含 reset/step，见模块 docstring 环境契约）。

    Returns:
        见模块 docstring 返回口径（训练曲线 reward_history+回退标记如实记录）。

    Raises:
        ValueError: train_config/env 形状错（非 dict/不可调用/缺方法/超参域错/
            状态或转移元组形状错）。
        PolicyError: env_factory/reset/step 运行期抛错（终止训练）。
    """
    if not isinstance(train_config, dict):
        raise ValueError(
            f"train_config 必须为 dict（训练配置），实际: {type(train_config).__name__}"
        )
    if not callable(env_factory):
        raise ValueError(
            f"env_factory 必须为可调用（()→env），实际: {type(env_factory).__name__}"
        )

    episodes = _pos_int(train_config.get("episodes", _DEFAULT_EPISODES), "train_config['episodes']", _MAX_EPISODES)
    n_actions = _pos_int(train_config.get("actions", _DEFAULT_ACTIONS), "train_config['actions']", _MAX_ACTIONS)
    max_steps = _pos_int(
        train_config.get("max_steps_per_episode", _DEFAULT_MAX_STEPS),
        "train_config['max_steps_per_episode']",
        _MAX_MAX_STEPS,
    )
    alpha = _unit_interval(train_config.get("alpha", _DEFAULT_ALPHA), "train_config['alpha']", lo_inclusive=1e-12, hi_inclusive=1.0)
    gamma = _unit_interval(train_config.get("gamma", _DEFAULT_GAMMA), "train_config['gamma']", lo_inclusive=0.0, hi_inclusive=1.0 - 1e-12)
    epsilon0 = _unit_interval(train_config.get("epsilon", _DEFAULT_EPSILON), "train_config['epsilon']", lo_inclusive=0.0, hi_inclusive=1.0)
    seed = train_config.get("seed")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, (int, np.integer))):
        raise ValueError(f"train_config['seed'] 必须为 int | None（bool 拒），得到 {seed!r}")
    rng = np.random.default_rng(None if seed is None else int(seed))

    try:
        env = env_factory()
    except Exception as exc:  # noqa: BLE001 - 工厂抛错属环境异常（终止训练）
        raise PolicyError(f"env_factory 调用失败: {type(exc).__name__}: {exc}") from exc
    reset, step = _env_methods(env)

    # Q 表：状态动态登记（首达即入表，行随机初始化 N(0, 0.01)——numpy 表承载 D3QN 位）。
    state_index: dict = {}
    q_table = np.zeros((0, n_actions), dtype=float)

    def _ensure_row(key: tuple) -> int:
        nonlocal q_table
        row = state_index.get(key)
        if row is None:
            row = q_table.shape[0]
            state_index[key] = row
            q_table = np.vstack([q_table, rng.normal(0.0, 0.01, size=(1, n_actions))])
        return row

    def _parse_step_return(raw: object, where: str):
        """step 返回值 (next_state, reward, done) 契约校验：形状错 ValueError。"""
        if not isinstance(raw, (tuple, list)) or len(raw) != 3:
            raise ValueError(
                f"env.step 须返回 (next_state, reward, done) 三元组，{where}返回: {raw!r}"
            )
        next_state, reward, done = raw
        if isinstance(reward, bool) or not isinstance(reward, Real):
            raise ValueError(f"env.step 奖励须为实数（bool/非数值拒绝），得到 {reward!r}")
        reward_f = float(reward)
        if not math.isfinite(reward_f):
            raise ValueError(f"env.step 奖励须为有限数（拒 NaN/±inf），得到 {reward!r}")
        if not isinstance(done, (bool, np.bool_, int, np.integer)):
            raise ValueError(f"env.step done 须为 bool/int，得到 {done!r}")
        return next_state, reward_f, bool(done)

    def _run_episode(epsilon: float) -> float:
        """单 episode：ε-greedy 交互+Q 表更新，返回总奖励（真实曲线记录口径）。"""
        nonlocal q_table
        try:
            state = reset()
        except Exception as exc:  # noqa: BLE001 - reset 抛错属环境异常（终止训练）
            raise PolicyError(f"env.reset 抛错（终止训练）: {type(exc).__name__}: {exc}") from exc
        row = _ensure_row(_state_key(state))
        total = 0.0
        for _ in range(max_steps):
            if rng.random() < epsilon:
                action = int(rng.integers(n_actions))
            else:
                action = int(np.argmax(q_table[row]))
            try:
                raw = step(action)
            except Exception as exc:  # noqa: BLE001 - step 抛错属环境异常（终止训练）
                raise PolicyError(
                    f"env.step(action={action}) 抛错（终止训练）: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            next_state, reward, done = _parse_step_return(raw, "env.step")
            next_row = _ensure_row(_state_key(next_state))
            target = reward if done else reward + gamma * float(np.max(q_table[next_row]))
            q_table[row, action] += alpha * (target - q_table[row, action])
            total += reward
            row = next_row
            if done:
                break
        return total

    reward_history: list = []
    epsilon = epsilon0
    for _ in range(episodes):
        reward_history.append(_run_episode(epsilon))
        epsilon = max(_EPSILON_MIN, epsilon * _EPSILON_DECAY)

    # 收敛判定：后一半均值 − 前一半均值 > 容差（改善即收敛；常数奖励恰 0 → 不收敛）。
    half = max(1, episodes // 2)
    first_mean = float(np.mean(reward_history[:half]))
    last_mean = float(np.mean(reward_history[-half:]))
    converged = bool(last_mean - first_mean > _CONVERGE_MARGIN)

    # 不收敛 → fallback_fixed_strategy 兜底（策略场景永有可执行路径）。
    fallback_used = not converged
    fallback_plan: list = []
    if fallback_used:
        scenario = train_config.get("scenario")
        if scenario is None:
            scenario = {"style": train_config.get("style") or "noise"}
            if train_config.get("ladder_params") is not None:
                scenario["ladder_params"] = train_config["ladder_params"]
            if train_config.get("link_power_db") is not None:
                scenario["link_power_db"] = train_config["link_power_db"]
        fallback_plan = fallback_fixed_strategy(scenario)  # 形状错 ValueError 透传

    return {
        "q_table_shape": (int(q_table.shape[0]), int(n_actions)),
        "episodes": int(episodes),
        "converged": converged,
        "final_reward_mean": last_mean,
        "fallback_used": fallback_used,
        "policy": "ql_table" if converged else "fallback_fixed",
        "reward_history": [float(r) for r in reward_history],
        "fallback_plan": fallback_plan,
        "n_states": int(q_table.shape[0]),
        "n_actions": int(n_actions),
    }
