import sys, tempfile, os
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.autodetect_backend.autodetect_backend import autodetect_backend
from src.resolve_clock_reference.resolve_clock_reference import resolve_clock_reference
from src.index_dataset.index_dataset import index_dataset
be, sel = autodetect_backend()  # auto：真机在位应选 b210
clock = resolve_clock_reference(be)
has_close = hasattr(be, 'close')
if has_close: be.close()
with tempfile.TemporaryDirectory() as td:
    ip = td + '/index.json'; rr = td + '/runs'
    index_dataset('register', record={'run_id': 'r1', 'path': td + '/a.sigmf-meta', 'style': 'tone', 'freq_mhz': 2450.0, 'date': '2026-10-11', 'backend': sel['backend']}, index_path=ip, runs_root=rr)
    q = index_dataset('query', query={'style': 'tone'}, index_path=ip, runs_root=rr)
assert sel['decision'] in ('probe_hit', 'auto_fallback') and clock['clock_ref'] in ('gpsdo', 'external', 'software') and q['matched'] == 1
print(f"B6 顶层实跑: 后端={sel['backend']}({sel['decision']})；时钟={clock['clock_ref']}；索引 register→query 往返 matched=1")
