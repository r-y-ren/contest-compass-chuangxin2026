import sys
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.run_emc_conduction_sim.run_emc_conduction_sim import run_emc_conduction_sim
from src.run_emc_radiation_sim.run_emc_radiation_sim import run_emc_radiation_sim
from src.run_emc_sweep.run_emc_sweep import run_emc_sweep
c = run_emc_conduction_sim({}, {'freq_hz': 10e6, 'limit_line_dbmv': 20})
r = run_emc_radiation_sim({}, {'center_hz': 13e9, 'span_hz': 10e6})
s = run_emc_sweep({}, {'band': 'cispr_b', 'step_hz': 5e6, 'spurious_threshold_dbm': -95})
assert c['simulated'] and 'CISPR 16-1-1' in c['disclaimer'] and c['readings'][0]['power_dbuv'] == c['readings'][0]['power_dbm'] + 107
assert r['simulated'] and r['cleanliness']['in_band_peaks'] >= 1
assert s['simulated'] and s["n_points"] >= 5 and s['n_spurious'] >= 0
print(f"B16 EMC 三流程: 传导 dbuv={c['readings'][0]['power_dbuv']:.1f} margin={c['readings'][0]['margin_db']:.1f}；辐射峰数={r['cleanliness']['in_band_peaks']}；扫频 {s['n_points']} 点 spurious={s['n_spurious']}——全 simulated+CISPR 声明")
