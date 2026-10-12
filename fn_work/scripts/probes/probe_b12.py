import sys, tempfile, json, os
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
import numpy as np
from src.record_run_streams.record_run_streams import record_run_streams
from src.run_baseline_check.run_baseline_check import run_baseline_check
class SimBe:
    def __init__(s): s.n = 0; s.stopped = False
    def read_samples(s, max_blocks=1):
        s.n += 1
        if s.n > 3: return []
        t = np.arange(64) / 56e6
        return [{'samples': [complex(np.exp(2j*np.pi*1e7*tt), 0) for tt in t], 'ts': s.n*100, 'overflow': False}]
    def stop_tx(s): s.stopped = True
    def set_tx_gain(s, g): pass
events = [{'type': 'power_step', 'target_db': -30, 'ts': 1}, {'type': 'power_step', 'target_db': -5, 'ts': 2}]
sink = []
with tempfile.TemporaryDirectory() as td:
    os.makedirs(td + '/recordings')
    ctx = {'run_dir': td, 'backend': SimBe(), 'record': True,
           'jam_events': events, 'events_sink': sink,
           'dut': {'source': 'sim', 'events': events},
           'monitor': {'target_band': (2400.0, 2456.0), 'nfft': 64},
           'scenario': {'style': 'tone', 'params': {}, 'power_steps': []},
           'stop': {'flag': False}}
    ctx['facts'] = {'style': 'tone', 'params': {}, 'backend': 'sim', 'clock_ref': 'software',
                    'freq_hz': 2.44e9, 'sample_rate': 56e6, 'run_id': 'probe12', 'power_steps': events}
    r = record_run_streams(ctx)
    kpi = open(td + '/kpi.csv').read().count('\n') - 1
    stats_lines = sum(1 for _ in open(td + '/monitor_stats.jsonl'))
    rec_ok = r['recording'] and r['recording']['num_samples'] > 0
    base = run_baseline_check(r.get('baseline_rows') or [{'judge_per': 0.0} for _ in range(10)])
assert kpi == 6 and stats_lines >= 1 and rec_ok and base['passed']
print(f"B12 准闭环: kpi={kpi} 行 stats={stats_lines} 行 SigMF={r['recording']['num_samples']} 样本 对齐p50={r['alignment']['kpi_delay_p50_ms']}ms 基线过={base['passed']}")
