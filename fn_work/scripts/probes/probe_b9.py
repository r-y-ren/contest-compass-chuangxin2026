import sys, tempfile
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.run_power_ladder.run_power_ladder import run_power_ladder
from src.map_distance_to_loss.map_distance_to_loss import map_distance_to_loss
calls = []
be = type('B', (), {'set_attenuation': lambda s, db: calls.append(db), 'stop_tx': lambda s: calls.append('STOP'), 'set_tx_gain': lambda s, g: None})()
with tempfile.TemporaryDirectory() as td:
    r1 = run_power_ladder({'backend': be, 'run_dir': td}, None, failure_cb=lambda info: {'failed': info['step'] == 1}, dwell_s=0.0, link_power_db=-15.0)
r2 = map_distance_to_loss([10.0, 100.0], {'d0_m': 10.0, 'l0_db': 30.0, 'n': 2.0})
assert r1['reason'] == 'failure' and r1['stopped_at'] == 1 and calls[-1] == 'STOP'
assert abs(r2['points'][0]['loss_db'] - 30.0) < 1e-9 and abs(r2['points'][1]['loss_db'] - 50.0) < 1e-9
print(f"B9 顶层实跑: 阶梯 failure 第2档停发射在末位={calls[-1]=='STOP'}；距离→损耗 30→50dB 组合={[p['combo']['coarse'] for p in r2['points']]}")
