import sys, tempfile, os, json
sys.path.insert(0, '/mnt/data/Code/autoC/workspace/chuangxin2026/fn_work')
import numpy as np
from src.index_dataset.index_dataset import index_dataset
from src.train_classifier.train_classifier import train_classifier
from src.grouped_cv_evaluate.grouped_cv_evaluate import grouped_cv_evaluate
from src.predict_style.predict_style import predict_style
rng = np.random.default_rng(7)
def write_pair(d, name, samples):
    if 'probe' in name:
        iq = np.exp(2j*np.pi*0.10*samples)  # 探测文件用纯单音（训练对仍为单音+噪声拼接）
    else:
        iq = np.concatenate([np.exp(2j*np.pi*0.10*samples), (rng.normal(size=len(samples))+1j*rng.normal(size=len(samples)))*0.3])
    with open(os.path.join(d, name + '.sigmf-data'), 'wb') as f:
        f.write(iq.astype('<c8').tobytes())
    meta = {'global': {'core:datatype': 'cf32_le', 'core:sample_rate': 1e6, 'core:version': '1.2.0', 'core:num_samples': len(iq)},
            'captures': [{'core:sample_start': 0, 'core:frequency': 2.44e9}], 'annotations': []}
    with open(os.path.join(d, name + '.sigmf-meta'), 'w') as f:
        json.dump(meta, f)
    return os.path.join(d, name + '.sigmf-meta')
with tempfile.TemporaryDirectory() as td:
    ip, rr = td + '/index.json', td + '/runs'
    for i in range(24):
        p = write_pair(td, 'tone_%02d' % i, np.arange(512))
        index_dataset('register', record={'run_id': 't%d' % i, 'path': p, 'style': 'tone', 'freq_mhz': 2450.0, 'date': '2026-10-12', 'backend': 'sim'}, index_path=ip, runs_root=rr)
    for i in range(24):
        p = write_pair(td, 'noise_%02d' % i, np.arange(512))
        index_dataset('register', record={'run_id': 'n%d' % i, 'path': p, 'style': 'bandlimited_noise', 'freq_mhz': 2450.0, 'date': '2026-10-12', 'backend': 'sim'}, index_path=ip, runs_root=rr)
    t = train_classifier({'style': ['tone', 'bandlimited_noise']}, {'index_path': ip, 'runs_root': rr, 'out_path': td + '/m.json', 'min_samples': 10}, where='local')
    model = json.load(open(t['model_path']))
    r = predict_style(td + '/probe.sigmf-meta' if False else write_pair(td, 'probe', np.arange(512)), model)
    samples = [{'label': 'tone' if j % 2 else 'bandlimited_noise', 'batch_key': 'b%d' % (j % 6),
                'features': ([5.0]*8 if j % 2 else [0.1]*8)} for j in range(48)]
    e = grouped_cv_evaluate(samples, k=3)
ok_t = t['n_samples'] == 48 and len(t['labels']) == 2
ok_r = r['status'] == 'ok' and r['label'] in ('tone', 'bandlimited_noise')
ok_e = e['macro_f1'] > 0.9 and not e['leak_suspect']
assert ok_t and ok_r and ok_e, (t, r, e['macro_f1'])
print(f"B14 AI 管线: 训练 {t['n_samples']} 样本两类；推理 label={r['label']} conf={r['confidence']:.2f}；分组 CV F1={e['macro_f1']:.2f} 泄漏={e['leak_suspect']}")
