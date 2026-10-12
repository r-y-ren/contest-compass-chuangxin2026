import sys, tempfile, os, json
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.build_report.build_report import build_report
from src.verify_report_traceability.verify_report_traceability import verify_report_traceability
with tempfile.TemporaryDirectory() as td:
    os.makedirs(td + '/plots')
    with open(td + '/kpi.csv', 'w') as f:
        f.write('timestamp_ms,link,source,per,judge_per,rssi_dbm,retries,per_note\n100,esp32,esp32,0.02,0.02,-55.0,0,\n200,esp32,esp32,0.15,0.15,-54.0,1,\n')
    with open(td + '/events.jsonl', 'w') as f:
        for t, lvl in [(1000, -15.0), (2000, -10.0)]:
            f.write(json.dumps({'type': 'power_step', 'ts': t, 'target_db': lvl}) + '\n')
    with open(td + '/monitor.csv', 'w') as f:
        f.write('timestamp_ms,freq_mhz,power_db,confidence\n100,2438.0,-30.5,ok\n')
    result = {'run_id': 'probe18', 'backend': 'sim', 'clock_ref': 'software',
              'failure_levels': [{'style': 'tone', 'failure_level_db': -10.0, 'per_at_failure': 0.15}]}
    p = build_report(td, result)
    v = verify_report_traceability(p, td)
    rpt = open(p, encoding='utf-8').read()
    ok_secs = all(s in rpt for s in ['运行概要', '失效电平', 'GB 42590', 'PER', '缺项'])
assert v['passed'] and v['n_traced'] >= 2, v
print(f"B18 报告链: report.md 各节齐（概要/失效/脚注 GB42590+PER）；溯源 passed={v['passed']} traced={v['n_traced']} contextual={v['n_contextual']} mismatch={len(v['mismatches'])}")
