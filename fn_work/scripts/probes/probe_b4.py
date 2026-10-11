import sys
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
import src.open_sim_backend.open_sim_backend  # 触发自注册
from src.manage_backend_registry.manage_backend_registry import manage_backend_registry as mbr
r = mbr('lookup', 'sim'); assert r['factory'] is not None
be = r['factory']({'freq_hz': 2.45e9, 'sample_rate': 1e6})
be.start_tx(iter([[1+1j, 2+2j]]), effects={})
blk = be.read_samples(); be.stop_tx()
samples, meta = blk[0]
assert samples[:2] == [1+1j, 2+2j]
lst = mbr('list')
print('B4 顶层实跑: sim 经注册表取回→实例化→环回样本保真；注册表:', lst['available'])
