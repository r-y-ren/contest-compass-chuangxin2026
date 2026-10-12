import sys, tempfile, os
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.execute_gb42590_protocol.execute_gb42590_protocol import execute_gb42590_protocol
from src.plot_triple_curves.plot_triple_curves import plot_triple_curves
from src.compare_failure_boundaries.compare_failure_boundaries import compare_failure_boundaries
import json
class Be:
    def __init__(s): s.calls = []
    def start_tx(s, iq, effects=None): s.calls.append('start')
    def stop_tx(s): s.calls.append('stop')
    def set_tx_gain(s, g): pass
    def set_attenuation(s, db): s.calls.append(('att', db))
    def read_samples(s, max_blocks=1): return []
lines = iter([b'ESP,%d,%d,%d,0,-55' % (i, i * 100, 0 if i <= 12 else (i - 12) * 60) for i in range(1, 31)])
with tempfile.TemporaryDirectory() as td:
    os.makedirs(td + '/plots')
    ctx = {'run_dir': td, 'backend': Be(), 'dwell_s': 0.0, 'link_power_db': -15.0,
           'scenario': {'style': 'tone', 'params': {'freq_offset_hz': 1e5, 'n_samples': 64, 'fs': 1e6}},
           'dut': {'source': 'esp32', 'serial_config': {'source': 'lines', 'lines': lines}}, 'judge_min_samples': 2,
           'monitor': {'target_band': (2400.0, 2456.0), 'nfft': 64}, 'facts': {'style': 'tone', 'backend': 'sim', 'freq_hz': 2.44e9, 'sample_rate': 1e6, 'run_id': 'probe13', 'power_steps': []}}
    r = execute_gb42590_protocol(ctx)
    data = {'kpi': [{'timestamp_ms': i * 50, 'judge_per': 0.0 if i < 2 else 0.5, 'ts_ms': i * 50} for i in range(6)],
            'events': [{'ts_ms': i * 100, 'type': 'power_step', 'target_db': -15.0 + i * 5, 'step': i} for i in range(3)],
            'failure_levels': r['failure_levels']}
    p = plot_triple_curves(data, td + '/plots', 'probe13')
    c = compare_failure_boundaries(r['failure_levels'] + [{'style': 'noise', 'failure_level_db': -25.0, 'per_at_failure': 0.2}])
    ok_status = r['status'] == 'failed' and len(r['failure_levels']) == 1 and len(p['png_paths']) == 3
    ok_png = all(open(f,'rb').read(4) == b'\x89PNG' for f in p['png_paths'])  # with 块内校验（临时目录未清理）
    ok_weak = c['weakest_style'] in ('tone', 'noise')
assert ok_status and ok_png and ok_weak
print(f"B13 全链: GB {r['status']} P_crit={r['failure_levels'][0]['failure_level_db']}dB；三 PNG 齐（font={p['font']}）；weakest={c['weakest_style']}")
