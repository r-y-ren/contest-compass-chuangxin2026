"""AI 页评估面板页区：ai 页 eval-panel 挂载点消费 POST /api/ai/evaluate 的
纯静态资产（HTML+内联 JS）——重写规约与签名意图详见 fn_docs/responsibility.md
（R66 AI 页区）。

产出口径（R66，纯静态资产，原生 fetch 自足——沿用 R60 build_report_view_area /
R63 build_dataset_area 的 serve_console 缺省装配注入模式）：

- ``#eval-panel`` 挂载点渲染评测表单：样式筛选（style，空=全量）+模型标识
  （model_path 文本，溯源回显）→ POST ``/api/ai/evaluate`` {'query':
  {'style': …}, 'model_path': …}；
- 结果页：混淆矩阵表格化（行=真值/列=预测，表头标签列）+Macro-F1+
  per_fold 摘要+泄漏三旗标（leak_suspect/fold_class_starvation/
  below_target）+评测口径行（``eval_protocol``——B48/I-2：aligned_template
  （评测的=部署的）/intrinsic_dummy（内置对照）如实上屏）+泄漏检测警告文案
  （``warnings`` 原文如实回显）；
- 错误上屏：400（EvalError——分组缺失/检索非法等）错误信息原文进状态行；
- 零外链：仅同源相对路径 fetch（/api/ai/evaluate）。
"""


def build_eval_area() -> str:
    """AI 页评估面板页区（纯静态资产 str，serve_console 缺省装配注入 ai 页）。

    Returns:
        ``<section id="eval-panel-area">``+内联 <style>/<script> 的区块资产
        str——JS 填充 ai 骨架页的 #eval-panel 挂载点；零外链。
    """
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——评测结果运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="eval-panel-area" aria-label="AI 评测可视化">
<style>
#eval-panel-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#eval-panel-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#eval-panel-area .epa-status { color: #6b7486; font-size: 13px; margin: 6px 0; word-break: break-all; }
#eval-panel-area .epa-error { color: #c0392b; font-size: 13px; margin: 6px 0; word-break: break-all; }
#eval-panel-area .epa-form { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 8px 0; }
#eval-panel-area .epa-form label { font-size: 13px; color: #1c2333; }
#eval-panel-area .epa-form input { padding: 2px 6px; border: 1px solid #c9d4e4; border-radius: 4px; width: 220px; }
#eval-panel-area .epa-form button { padding: 3px 12px; border: 1px solid #2c5aa0; border-radius: 4px; background: #f2f6fb; color: #2c5aa0; cursor: pointer; }
#eval-panel-area table.epa-matrix { border-collapse: collapse; margin: 8px 0; font-size: 13px; }
#eval-panel-area table.epa-matrix th, #eval-panel-area table.epa-matrix td { border: 1px solid #c9d4e4; padding: 2px 10px; text-align: center; }
#eval-panel-area table.epa-matrix th { background: #f2f6fb; color: #2c5aa0; }
#eval-panel-area ul.epa-warnings { margin: 6px 0 0; padding: 0 0 0 18px; font-size: 13px; color: #a06a00; }
#eval-panel-area .epa-flags { font-size: 13px; color: #1c2333; margin: 6px 0; }
</style>
<h2>分组 CV 评测</h2>
<p class="epa-status" id="epa-status">填写筛选与模型标识后点「发起评测」（POST /api/ai/evaluate）。</p>
<script>
(function () {
  var panel = document.getElementById('eval-panel');
  if (!panel) { return; }
  var statusLine = document.getElementById('epa-status');
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'epa-error' : 'epa-status';
  };
  var styleInput = document.createElement('input');
  styleInput.id = 'epa-style'; styleInput.placeholder = '样式如 tone（空=全量）';
  var modelInput = document.createElement('input');
  modelInput.id = 'epa-model'; modelInput.value = 'models/style_classifier.json';
  modelInput.placeholder = '模型标识（如 models/style_classifier.json）';
  var evalBtn = document.createElement('button');
  evalBtn.id = 'epa-run'; evalBtn.type = 'button'; evalBtn.textContent = '发起评测';
  var form = document.createElement('div'); form.className = 'epa-form';
  var addLabeled = function (text, el) {
    var label = document.createElement('label'); label.textContent = text + '：';
    form.appendChild(label); form.appendChild(el);
  };
  addLabeled('样式筛选', styleInput);
  addLabeled('模型标识', modelInput);
  form.appendChild(evalBtn);
  panel.appendChild(form);
  var resultMount = document.createElement('div');
  resultMount.id = 'epa-result';
  panel.appendChild(resultMount);
  var cell = function (tag, text) {
    var el = document.createElement(tag); el.textContent = text; return el;
  };
  var render = function (data) {
    resultMount.textContent = '';
    var table = document.createElement('table'); table.className = 'epa-matrix';
    var confusion = data.confusion || { labels: [], matrix: [] };
    var head = document.createElement('tr');
    head.appendChild(cell('th', '真值\\预测'));
    confusion.labels.forEach(function (label) { head.appendChild(cell('th', label)); });
    table.appendChild(head);
    confusion.matrix.forEach(function (row, i) {
      var tr = document.createElement('tr');
      tr.appendChild(cell('th', confusion.labels[i]));
      row.forEach(function (value) { tr.appendChild(cell('td', String(value))); });
      table.appendChild(tr);
    });
    resultMount.appendChild(table);
    var flags = document.createElement('p'); flags.className = 'epa-flags';
    var targetNote = data.below_target ? '未达标——如实记录' : '达标';
    flags.textContent = 'Macro-F1=' + data.macro_f1.toFixed(4) +
        '（内部目标 0.85：' + targetNote + '）' +
        ' effective_k=' + data.effective_k + ' n_samples=' + data.n_samples +
        ' leak_suspect=' + data.leak_suspect +
        ' fold_class_starvation=' + data.fold_class_starvation +
        ' 模型在位=' + data.model_exists;
    resultMount.appendChild(flags);
    var proto = data.eval_protocol;
    var protoNote = proto === 'aligned_template'
        ? 'aligned_template（评测的=部署的）'
        : (proto === 'intrinsic_dummy' ? 'intrinsic_dummy（内置对照）' : String(proto));
    var protocolLine = document.createElement('p'); protocolLine.className = 'epa-flags';
    protocolLine.textContent = '评测口径：' + protoNote;
    resultMount.appendChild(protocolLine);
    if ((data.warnings || []).length) {
      var list = document.createElement('ul'); list.className = 'epa-warnings';
      data.warnings.forEach(function (text) { list.appendChild(cell('li', text)); });
      resultMount.appendChild(list);
    }
  };
  evalBtn.addEventListener('click', function () {
    var body = { model_path: modelInput.value.trim() || 'models/style_classifier.json' };
    if (styleInput.value.trim()) { body.query = { style: styleInput.value.trim() }; }
    else { body.query = {}; }
    say('评测运行中……（分组 CV 逐折训练/推理，秒级）');
    fetch('/api/ai/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (resp) {
      if (!resp.ok) { return resp.json().then(function (err) {
        throw new Error('HTTP ' + resp.status + ' ' + JSON.stringify(err));
      }); }
      return resp.json();
    }).then(function (data) {
      render(data);
      say('评测完成：matched=' + data.matched + ' skipped=' + data.skipped +
          '——矩阵与警告如上（评测以分组口径为准）。');
    }).catch(function (err) { say('评测失败: ' + err.message, true); });
  });
})();
</script>
</section>
"""
