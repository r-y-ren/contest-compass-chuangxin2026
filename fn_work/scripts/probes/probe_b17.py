import sys, tempfile, os, shutil
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
ROOT = '/mnt/data/Code/autoC/workspace/chuangxin2026'
from src.update_ledger.update_ledger import update_ledger
from src.update_ledger.locate_ledger_row import locate_ledger_row
from src.audit_ledger.audit_ledger import audit_ledger
from src.load_scenario.load_scenario import load_scenario
# 1) 真清单冒烟：audit（只读）
a = audit_ledger(ROOT + '/docs/全功能实现清单-技术支持版.md', ROOT + '/fn_work/src')
# 2) tmp 清单写入往返
tmp = tempfile.mktemp(suffix='.md')
shutil.copy(ROOT + '/docs/全功能实现清单-技术支持版.md', tmp)
r = update_ledger('B1', 'probe 冒烟 anchor（fn-guard probe）', ledger_path=tmp)
loc = locate_ledger_row('B1', ledger_path=tmp)
os.remove(tmp)
# 3) 场景装载
sc = tempfile.mktemp(suffix='.yaml')
open(sc, 'w').write('style: tone\nfs: 1000000\nfreq_hz: 2450000000\nbands:\n  - [2400, 2483.5]\nshielded_box: true\ndut_scope: self_built\n')
s = load_scenario(sc)
os.remove(sc)
assert a['total_entries'] == 100 and 'comment_ratio' in a
assert 'probe 冒烟' in loc['status_text'] and loc['has_done_mark']
assert s['style'] == 'tone' and s['power_dbm'] == -10.0
print(f"B17 台账+场景: audit 100 条 done={a['done_entries']} 注释率={a['comment_ratio']['ratio']:.2%}；写入往返 ✅；场景装载（默认功率 −10 过红线）✓")
