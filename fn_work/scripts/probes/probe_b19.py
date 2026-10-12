import sys, tempfile, os
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
from fastapi.testclient import TestClient
from src.serve_console.serve_console import serve_console
from src.render_console_pages.render_console_pages import render_console_pages
from src.push_realtime_kpi.push_realtime_kpi import push_realtime_kpi
with tempfile.TemporaryDirectory() as td:
    sdir = os.path.join(td, 'scenarios'); os.makedirs(sdir)
    with open(os.path.join(sdir, 'tone_demo.yaml'), 'w') as f:
        f.write('# desc: 定频音干扰\nstyle: tone\npower_dbm: -15\nbackend: sim\n')
    r = serve_console({'scenario_dir': sdir, 'report_root': td, 'dry_run': True, 'port': 8901})
    pages = render_console_pages(sdir, {'out_dir': os.path.join(td, 'ui')})
    with TestClient(r['app']) as c:
        resp = c.get('/api/scenarios'); cards = resp.json()
        stop = c.post('/api/stop')
    hub = {'sockets': [], 'history': [], 'acks': []}
    push = push_realtime_kpi(iter([{'per': 0.05}, {'per': 0.2}, {'per': 0.4}]), hub)
    ok = (r['launched'] is False and cards['count'] == 1 and stop.status_code == 200
          and pages['written'][0].endswith('index.html') and os.path.isfile(pages['written'][0])
          and 'vue.global.prod.js' in pages['pages']['index.html']
          and push['n_pushed'] == 3 and 'latency' in push)
    assert ok, (cards, push['n_pushed'], pages['written'])
print(f"B19 Web 探针: dry_run 服务+API（场景卡 {cards['count']}/stop ok）；Vue CDN 页面落盘；实时流 3 帧+latency 键集齐")
