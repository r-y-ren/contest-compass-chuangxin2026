import sys
import numpy as np
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.capture_monitor_spectrum.capture_monitor_spectrum import capture_monitor_spectrum
from src.compute_spectrum_stats.compute_spectrum_stats import compute_spectrum_stats
fs = 56e6; nfft = 256
t = np.arange(nfft) / fs
tone = np.exp(2j * np.pi * 1e7 * t)
blocks = iter([{'samples': [c for c in tone], 'ts': 100, 'overflow': False}])
ctx = {}
caps = list(capture_monitor_spectrum(ctx, blocks, target_band=(2400.0, 2456.0), nfft=nfft))
peak = max(caps[0]['bins'], key=lambda b: b['power_db'])
assert abs(peak['freq_mhz'] - 2438.0) < 1.1  # 段中心 2428 + 10MHz 注入峰
win = {'bins': caps[0]['bins'], 'timestamp_ms': 100,
       'reference': {'signal_band': (2436.0, 2440.0), 'interference_band': (2440.0, 2450.0)}}
st = compute_spectrum_stats(win)
assert st['available'] and st['snr_db'] > 5
print(f"B10 顶层实跑: 监测谱峰 {peak['freq_mhz']:.1f}MHz（段中心 2428+10MHz 注入）；统计 full 模式 SNR={st['snr_db']:.1f}dB peak={st.get('peak_db', 0):.1f}dB")
