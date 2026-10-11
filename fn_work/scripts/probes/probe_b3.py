import sys, json, tempfile
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.manage_run.manage_run import manage_run
class FakeTx:
    def __init__(self): self.stopped = False
    def stop_tx(self): self.stopped = True
tx = FakeTX = FakeTx()
with tempfile.TemporaryDirectory() as td:
    r = manage_run({'style': 'tone'}, lambda ctx: ctx['log']('INFO', 'demo', 'ok'), runs_root=td + '/runs', backend=tx)
    res = json.load(open(r['run_dir'] + '/result.json'))
    assert r['status'] == 'done' and res['status'] == 'done' and tx.stopped and not res['missing'], (r, res)
    print('manage_run 实跑: done+停发射+八件套齐 →', r['run_dir'].split('/')[-1])
