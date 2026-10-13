"""B21 终装探针：run_demo --demo 全流程（判据中段触发口径，与 test_run_demo 同断言）。"""
import io
import sys
from contextlib import redirect_stdout

sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.run_demo.run_demo import run_demo

buffer = io.StringIO()
with redirect_stdout(buffer):  # 摘要行捕获后断言（不淹没断言输出）
    rc = run_demo(['--demo'])
summary = [line for line in buffer.getvalue().splitlines() if line.startswith('run_demo: run_dir=')][-1]
assert rc == 1, f'期望 exit 1（判据触发=运行失败），实际 {rc}'
assert 'status=failed' in summary, summary
assert 'failure_levels=1' in summary, summary
print(f"B21 终装探针: run_demo --demo → exit {rc}（中段档判据触发+失效电平登记）")
print(f"  摘要行: {summary}")
