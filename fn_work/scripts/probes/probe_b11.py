import sys
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from src.drive_esp32_link.drive_esp32_link import drive_esp32_link
from src.drive_nrf24_link.drive_nrf24_link import drive_nrf24_link
from src.simulate_link_degradation.simulate_link_degradation import simulate_link_degradation
from src.normalize_kpi.normalize_kpi import normalize_kpi
lines = iter([b'ESP,1,100,5,2,-52.5', b'ESP,2,200,25,4,-51.0', b'ESP,3,300,90,9,-49.5'])
esp = [normalize_kpi(s, 'esp32') for s in drive_esp32_link({'source': 'lines', 'lines': lines})]
nrf = [normalize_kpi(s, 'nrf24') for s in drive_nrf24_link({'port': '/dev/null', 'source': iter([b'NRF,1,80,4,1,1', b'NRF,2,160,40,3,0'])})]
ev = iter([{'type': 'power_step', 'target_db': -30, 'ts': 1}, {'type': 'power_step', 'target_db': -5, 'ts': 2}])
sim = [normalize_kpi(s, 'sim') for s in simulate_link_degradation(ev, ctx={'signal_power_db': -20.0})]
assert abs(esp[1]['per'] - 20 / 100) < 1e-9 and esp[0]['rssi_dbm'] == -52.5 and esp[0]['rpd'] is None
assert nrf[1]['per'] == 36 / 80 and nrf[0]['rssi_dbm'] is None and nrf[0]['rpd'] is True
assert sim[-1]['per'] > sim[0]['per'] and sim[0]['jsr_db'] == -10.0
print(f"B11 三源贯通: esp per={esp[1]['per']:.2f} rssi={esp[0]['rssi_dbm']}；nrf per={nrf[1]['per']:.2f} 无rssi口径；sim PER 随 JSR 升（{sim[0]['per']:.3f}→{sim[-1]['per']:.3f}）")
