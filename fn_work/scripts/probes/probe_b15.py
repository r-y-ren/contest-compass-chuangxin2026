import sys
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
import numpy as np
import src.open_sim_siggen.open_sim_siggen, src.open_sim_analyzer.open_sim_analyzer
import src.open_sim_mixer.open_sim_mixer, src.open_sim_emi_receiver.open_sim_emi_receiver
import src.open_sim_attenuator.open_sim_attenuator
from src.manage_backend_registry.lookup_backend import lookup_backend
sg = lookup_backend('sim_siggen_1433d')[0]({'freq_hz': 12.85e9 + 150e6, 'power_dbm': -10})
sg.set_freq(13e9); sg.output_on()
az = lookup_backend('sim_rsa513a')[0]({'center_hz': 13e9})
t = az.measure(None); peak = max(t['power_db'])
mx = lookup_backend('sim_mixer_13g')[0]({})
chain = mx.chain_demo()
em = lookup_backend('sim_emi_receiver')[0]({'freq_hz': 10e6})
noise = em.measure(None)
at = lookup_backend('sim_attenuator')[0]({'attenuation_db': 30})
iq = np.exp(2j * np.pi * 0.1 * np.arange(256))
att_iq = at.pass_through(iq)
assert abs(chain['rf_freq_hz'] - 13e9) < 1 and chain['phase_noise_dbc_hz'] == -100.0
assert abs(peak - (-30)) <= 1.5 and t['simulated'] and t['uncertainty_db'] == 1.5
assert abs(noise['power_dbm'] - (-150 + 10 * np.log10(9000))) < 0.01 and noise['simulated']
assert abs(np.max(np.abs(att_iq)) - 1.0 * 10 ** (-30 / 20)) < 1e-6
assert sg.get_freq() == 13e9 * 1.000001
print(f"B15 五后端链: 混频链 RF={chain['rf_freq_hz']/1e9:.2f}GHz 相噪={chain['phase_noise_dbc_hz']}；分析仪内置音 {peak:.1f}dBm±1.5；EMI 底噪 {noise['power_dbm']:.1f}dBm；衰减 30dB 数学 ✓；信号源 1ppm 回读 ✓")
