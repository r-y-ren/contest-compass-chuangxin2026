"""RL 策略演示入口：run_rl_policy sim 小闭环冒烟（动作序列/回报上屏）；不收敛
回退固定策略如实标注——重写规约与签名意图详见 fn_docs/responsibility.md
（R73 demo_rl_policy L0；调用方 mount_console_extensions）。

落地口径（R73，沿用 R54 run_rl_policy 口径）：

- sim 小闭环环境（仅 sim、不开放辐射）：6 档动作（样式×功率档位子集——JSR
  阶梯 −10…+15dB），每步经 simulate_link_degradation 单事件产一个包级统计
  样本（悬崖退化模型，与 R-测链 sim 同源），reward=1−per_raw（链路质量代理
  ——低误码=好调度）；env 契约 reset/step 对齐 run_rl_policy（状态
  =[jsr 归一, per] 二维数值向量）；
- 短轮次固定参数：episodes=rounds（缺省 8；正 int，bool/非正/超 64 拒——演示
  防失控）、max_steps_per_episode=8、α/γ/ε 取 run_rl_policy 缺省、seed 固定
  20261013（演示复现口径）；
- 动作序列上屏：env 逐 episode 记录动作（reset 分界），演示视图给末轮动作
  序列+reward_history 全曲线（训练真值不粉饰）；
- 不收敛回退如实标注：run_rl_policy 收敛判定（后一半均值−前一半>容差）失败
  → fallback_fixed_strategy 固定策略兜底——fallback_used/policy/fallback_plan
  透传+回退原因注明（rounds=1 时前后半同轮必不收敛——单轮冒烟即回退分支的
  确定性演示）；
- PolicyError/ValueError 原样上抛（演示异常→失败原因上屏不静默——端点层转
  400）。
"""
from src.run_rl_policy.run_rl_policy import PolicyError, run_rl_policy
from src.simulate_link_degradation.simulate_link_degradation import (
    simulate_link_degradation,
)

__all__ = ["DEMO_ACTIONS", "DEMO_JS_LEVELS_DB", "DEMO_MAX_STEPS", "DEMO_ROUNDS", "demo_rl_policy"]

#: 演示动作数（6 档——run_rl_policy 缺省动作空间口径）。
DEMO_ACTIONS = 6

#: 6 档动作的 JSR 阶梯（dB：悬崖阈值 10dB 两侧跨布，动作 0 最优）。
DEMO_JS_LEVELS_DB = (-10.0, -5.0, 0.0, 5.0, 10.0, 15.0)

#: 单轮步数（短冒烟——8 步×6 轮秒级完成）。
DEMO_MAX_STEPS = 8

#: 缺省轮数（None=8——短轮次固定参数口径：ε 衰减过半、末半程平均回报改善）。
DEMO_ROUNDS = 8

#: 演示种子（固定——复现口径：同参数两次演示结果一致）。
DEMO_SEED = 20261013

#: 轮数上限（演示防失控——超出直接拒）。
_MAX_ROUNDS = 64

#: 信号电平（dBm——JSR 换算基准，与 run_demo --demo 口径同值）。
_SIGNAL_POWER_DB = -20.0

#: 演示视图的诚实基注（sim 小闭环+回退不粉饰口径）。
_SIM_NOTE = (
    "RL 策略演示为 sim 小闭环冒烟（simulate_link_degradation 悬崖模型，仅 sim、"
    "不开放辐射），reward=1−PER 链路质量代理；短轮次固定参数+固定种子（复现口径），"
    "非正式训练曲线；训练不收敛时自动回退固定策略并如实标注（R54 口径）"
)


def _make_sim_env(n_actions: int) -> dict:
    """sim 小闭环 env（reset/step 鸭子契约+逐轮动作记录）。

    动作 i → JSR 阶梯档 DEMO_JS_LEVELS_DB[i]；step 经 simulate_link_degradation
    单事件产一个样本，per=per_raw（包级统计量化 0.1 步长）；reset 分界记录
    逐轮动作序列（log['last'] 即末轮——演示视图消费）。
    """
    log = {"current": [], "last": []}

    def reset():
        log["last"] = log["current"]
        log["current"] = []
        return [0.0, 0.0]

    def step(action):
        if not isinstance(action, (int,)) or isinstance(action, bool) or not (
            0 <= action < n_actions
        ):
            raise PolicyError(f"演示 env 收到非法动作索引: {action!r}")
        level = DEMO_JS_LEVELS_DB[action]
        sample = next(
            simulate_link_degradation(
                [
                    {
                        "type": "power_step",
                        "jsr_db": level,
                        "ts": float(len(log["current"])),
                    }
                ],
                ctx={"signal_power_db": _SIGNAL_POWER_DB},
                samples_per_event=1,
            )
        )
        per = float(sample["per_raw"])
        log["current"].append(int(action))
        return [level / 20.0, per], 1.0 - per, False

    return {"reset": reset, "step": step, "log": log}


def demo_rl_policy(rounds: int | None = None) -> dict:
    """RL 策略演示入口：run_rl_policy sim 小闭环冒烟一轮；不收敛回退固定策略
    如实标注（详见 fn_docs/responsibility.md 功能块）。

    输入:
        rounds: 轮数|None（None=缺省 8；正 int 且 ≤64——bool/非 int/非正/超限
            ValueError 先拒）。

    输出:
        演示视图 dict：{'ok': True, 'rounds', 'action_space', 'max_steps',
        'action_sequence': 末轮动作序列 [int, ...], 'reward_history': 逐轮总
        奖励（run_rl_policy 真值透传）, 'final_reward_mean', 'converged',
        'fallback_used', 'policy': 'ql_table'|'fallback_fixed', 'fallback_plan',
        'fallback_note': 回退原因|None（未回退 None）, 'q_table_shape',
        'n_states', 'simulated': True, 'note': 诚实基注}。

    错误:
        ValueError: rounds 域错（bool/非正 int/超 64 上限）或 run_rl_policy
            透传的形状错。
        PolicyError: env 契约错（本演示 env 自洽，理论不触发——上抛供端点层
            400 失败原因上屏）。
    """
    if rounds is None:
        rounds = DEMO_ROUNDS
    if (
        isinstance(rounds, bool)
        or not isinstance(rounds, int)
        or rounds <= 0
        or rounds > _MAX_ROUNDS
    ):
        raise ValueError(
            f"rounds 必须为正 int（≤{_MAX_ROUNDS}——演示防失控），实际: {rounds!r}"
        )

    env = _make_sim_env(DEMO_ACTIONS)
    outcome = run_rl_policy(
        {
            "episodes": rounds,
            "actions": DEMO_ACTIONS,
            "max_steps_per_episode": DEMO_MAX_STEPS,
            "seed": DEMO_SEED,
            "scenario": {"style": "noise"},
        },
        lambda: env,
    )
    fallback_used = bool(outcome["fallback_used"])
    return {
        "ok": True,
        "rounds": outcome["episodes"],
        "action_space": outcome["n_actions"],
        "max_steps": DEMO_MAX_STEPS,
        "action_sequence": list(env["log"]["last"]),
        "reward_history": outcome["reward_history"],
        "final_reward_mean": outcome["final_reward_mean"],
        "converged": outcome["converged"],
        "fallback_used": fallback_used,
        "policy": outcome["policy"],
        "fallback_plan": outcome["fallback_plan"],
        "fallback_note": (
            "训练未收敛（后一半轮次平均回报未优于前一半——run_rl_policy 收敛判定），"
            "已回退固定策略 fallback_fixed（固定样式×GB 功率阶梯，永有可执行路径）"
            if fallback_used
            else None
        ),
        "q_table_shape": list(outcome["q_table_shape"]),
        "n_states": outcome["n_states"],
        "simulated": True,
        "note": _SIM_NOTE,
    }
