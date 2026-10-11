import sys
import numpy as np
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.synthesize_style.gen_tone import gen_tone
from src.synthesize_style.gen_sweep import gen_sweep
from src.synthesize_style.gen_chirp import gen_chirp
from src.synthesize_style.gen_bandlimited_noise import gen_bandlimited_noise
from src.synthesize_style.gen_partial_band import gen_partial_band
from src.synthesize_style.gen_pulse import gen_pulse
from src.synthesize_style.compose_jamming import compose_jamming
from src.synthesize_style.check_style_params import check_style_params
N, FS = 8192, 1.0
tone = gen_tone(0.10 * FS, N)
spec = np.abs(np.fft.fft(tone)); assert abs(np.argmax(spec) - int(0.10 * N)) <= 1
sw = gen_sweep(-0.2 * FS, 0.2 * FS, 1.0, fs=FS)
ch = gen_chirp(0.0, 0.4 * FS, 1.0, N, fs=FS)
nz, nm = gen_bandlimited_noise(0.1 * FS, N, fs=FS)
assert nm['flatness_db'] <= 4.0
pb, pm = gen_partial_band(0.25, 0.8 * FS, N, fs=FS)
pu, pum = gen_pulse(0.05, 10.0, N, fs=FS)
assert abs(pum['duty_cycle'] - 0.5) < 1e-9
cj, cm = compose_jamming([{'iq': gen_tone(0.05 * FS, N)}, {'iq': gen_tone(-0.05 * FS, N), 'phase_rad': 0.0}], fs=FS)
chk = check_style_params({'style': 'tone', 'power_dbm': -5.0})
assert chk['errors'] == []
print(f"B7 六样式+合成+校验探针全过: flat={nm['flatness_db']:.2f}dB duty={pum['duty_cycle']} share={[round(p,2) for p in cm['power_share']]}")
