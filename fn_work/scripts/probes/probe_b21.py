import sys
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.run_demo.run_demo import run_demo
rc = run_demo(['--demo'])
assert rc == 0, rc
print(f"B21 终装探针: run_demo --demo → exit {rc}（全流程 0 退出）")
