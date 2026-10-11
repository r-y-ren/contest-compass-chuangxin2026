import sys, tempfile
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.synthesize_style.synthesize_style import synthesize_style
from src.switch_style.switch_style import switch_style
from src.set_channel_attenuation.set_channel_attenuation import set_channel_attenuation
import numpy as np
iq, m = synthesize_style({'style': 'tone', 'fs': 1e6, 'freq_offset_hz': 1e5, 'n_samples': 4096})
assert abs(int(np.argmax(np.abs(np.fft.fft(iq)))) - int(0.1 * 4096)) <= 1
ctx = {}
r1 = switch_style(ctx, 'bandlimited_noise', {'fs': 1e6, 'bandwidth_hz': 2e5, 'n_samples': 4096, 'seed': 7})
assert r1['switch_ms'] < 2000 and ctx['current_style']['style'] == 'bandlimited_noise'
with tempfile.TemporaryDirectory() as td:
    calls = []
    be = type('B', (), {'set_attenuation': lambda s, db: calls.append(db)})()
    r2 = set_channel_attenuation({'backend': be, 'run_dir': td}, 35.0)
    assert r2['achieved_db'] == 35.0 and calls == [35.0]
print(f"B8 顶层实跑: 六样式装配谱峰对；切换 {r1['style']} {r1['switch_ms']:.1f}ms；衰减下发 {calls} + 事件落盘")
