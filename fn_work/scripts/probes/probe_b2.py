import sys; sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.lookup_jsr.lookup_jsr import lookup_jsr
from src.build_gain_calibration.build_gain_calibration import build_gain_calibration
from src.compensate_link_power.compensate_link_power import compensate_link_power
r1 = lookup_jsr('g1', 2.45e9, -20.0, {'calibration_dir': '/nonexistent_dir_xx'})
assert r1['status'] == 'missing_table', r1
r2 = build_gain_calibration([{'gain_step': 'g1', 'power_dbm': -10.0}, {'gain_step': 'g2', 'power_dbm': -5.0, 'out_path': '/tmp/bgc_probe.json'}])
assert r2['placeholder'] is False and r2['points'] == 2, r2
r3 = compensate_link_power([(2450.0, -40.0)], {'calibration_dir': '/nonexistent_dir_xx'},
                           tables={'link_loss': {2400.0: 3.0, 2500.0: 4.0}, 'antenna': {2400.0: 1.0, 2500.0: 1.2}})
assert abs(r3[0]['p_actual'] - (-40.0 + 3.5 + 1.1)) < 1e-9 and r3[0]['confidence'] == 'ok', r3
print('三顶层实跑: lookup_jsr=missing_table；build_gain=建表2点；compensate=-35.4dB ok')
