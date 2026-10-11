import sys
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
import src.open_b210_backend.open_b210_backend as ob
from src.manage_backend_registry.lookup_backend import lookup_backend
from src.create_visa_driver.create_visa_driver import create_visa_driver
f, m = lookup_backend('b210'); assert m['caps']['tx'] and m['caps']['rx']
avail = ob.probe_b210_available()
sess = type('S', (), {'write': lambda s, c: None, 'read': lambda s: 'CETC 1433D,仿真,1.0'})()
drv = create_visa_driver('GPIB0::16::INSTR', '1433d', session=sess)
ident = drv.exchange('query_id')
print(f'B5 顶层实跑: b210 注册在案 caps={m["caps"]}；真机在位={avail}；visa query_id → {ident["value"]!r}')
