import sys
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.bridge_to_sitl.bridge_to_sitl import bridge_to_sitl
from src.run_rl_policy.run_rl_policy import run_rl_policy
from src.run_rl_policy.fallback_fixed_strategy import fallback_fixed_strategy
res = {'steps_executed': [{'step': 0, 'target_db': -20.0, 'level_db': -20.0, 'per': 0.02}, {'step': 1, 'target_db': -15.0, 'level_db': -15.0, 'per': 0.35}]}
b = bridge_to_sitl(res, {}, dry_run=True)
fb = fallback_fixed_strategy({'style': 'tone', 'link_power_db': -15.0})
import numpy as np
class Chain:
    def __init__(s): s.i = 0
    def reset(s): s.i = 0; return [float(s.i)]
    def step(s, a):
        s.i += 1
        done = s.i >= 4
        r = 1.0 if (a == 1 and s.i >= 3) or done else -0.1
        return [float(min(s.i, 3))], r, done
rl = run_rl_policy({'episodes': 40}, Chain)
assert b['bridged'] and b['dry_run'] and len(b['injections']) == 2 and b['injections'][1]['packet_loss'] == 0.35
assert len(fb) >= 2 and fb[0]['action'] == 'emit'
assert rl['policy'] in ('ql_table', 'fallback_fixed') and 'converged' in rl
print(f"B20 二期探针: SITL 注入表 {len(b['injections'])} 档（loss 0.35）；固定策略 {len(fb)} 动作；RL {rl['policy']} converged={rl['converged']} fallback={rl['fallback_used']}")
