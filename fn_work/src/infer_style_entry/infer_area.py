"""AI 页推理面板页区：ai 页 infer-panel 挂载点消费 POST /api/ai/infer 的
纯静态资产（HTML+内联 JS）——重写规约与签名意图详见 fn_docs/responsibility.md
（R67 AI 页区）。

产出口格（R67，纯静态资产，原生 fetch 自足——沿用 R60 build_report_view_area /
R63 build_dataset_area 的 serve_console 缺省装配注入模式）：

- ``#infer-panel`` 挂载点渲染推理表单：运行/条目标识（run_id，空=全库首条）
  → POST ``/api/ai/infer`` {'run_id': …}（服务端自动回落缺省模型——
  run 目录根 models/style_classifier.json 在位即用）；
- 结果行：样式标签+置信度+模型版本+真值对照（truth.source/truth.style+
  hit 命中徽标——真值缺失如实「不可考」不虚构）；
- 模型缺失→提示态上屏（note 含「先训练」指引原文），不报错拦页；
- 零外链：仅同源相对路径 fetch（/api/ai/infer）。
"""


def build_infer_area() -> str:
    """AI 页推理面板页区（纯静态资产 str，serve_console 缺省装配注入 ai 页）。

    Returns:
        ``<section id="infer-panel-area">``+内联 <style>/<script> 的区块资产
        str——JS 填充 ai 骨架页的 #infer-panel 挂载点；零外链。
    """
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——推理结果运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="infer-panel-area" aria-label="AI 主动推理">
<style>
#infer-panel-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#infer-panel-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#infer-panel-area .ipa-status { color: #6b7486; font-size: 13px; margin: 6px 0; word-break: break-all; }
#infer-panel-area .ipa-error { color: #c0392b; font-size: 13px; margin: 6px 0; word-break: break-all; }
#infer-panel-area .ipa-form { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 8px 0; }
#infer-panel-area .ipa-form label { font-size: 13px; color: #1c2333; }
#infer-panel-area .ipa-form input { padding: 2px 6px; border: 1px solid #c9d4e4; border-radius: 4px; width: 200px; }
#infer-panel-area .ipa-form button { padding: 3px 12px; border: 1px solid #2c5aa0; border-radius: 4px; background: #f2f6fb; color: #2c5aa0; cursor: pointer; }
#infer-panel-area .ipa-row { font-size: 13px; margin: 4px 0; }
#infer-panel-area .ipa-hit { color: #1e7a35; font-weight: bold; }
#infer-panel-area .ipa-miss { color: #c0392b; font-weight: bold; }
#infer-panel-area .ipa-unknown { color: #6b7486; }
</style>
<h2>主动样式推理</h2>
<p class="ipa-status" id="ipa-status">填运行/条目标识后点「识别」（POST /api/ai/infer）。</p>
<script>
(function () {
  var panel = document.getElementById('infer-panel');
  if (!panel) { return; }
  var statusLine = document.getElementById('ipa-status');
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'ipa-error' : 'ipa-status';
  };
  var runInput = document.createElement('input');
  runInput.id = 'ipa-run-id'; runInput.placeholder = '运行/条目标识（空=全库首条）';
  var inferBtn = document.createElement('button');
  inferBtn.id = 'ipa-infer'; inferBtn.type = 'button'; inferBtn.textContent = '识别';
  var form = document.createElement('div'); form.className = 'ipa-form';
  var label = document.createElement('label'); label.textContent = '运行/条目：';
  form.appendChild(label); form.appendChild(runInput); form.appendChild(inferBtn);
  panel.appendChild(form);
  var resultMount = document.createElement('div');
  resultMount.id = 'ipa-result';
  panel.appendChild(resultMount);
  var row = function (text, cls) {
    var el = document.createElement('p'); el.className = 'ipa-row' + (cls ? ' ' + cls : '');
    el.textContent = text; return el;
  };
  inferBtn.addEventListener('click', function () {
    var body = {};
    if (runInput.value.trim()) { body.run_id = runInput.value.trim(); }
    else { body.query = {}; }
    say('识别中……（模型缺省回落 run 目录根 models/style_classifier.json）');
    fetch('/api/ai/infer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (resp) {
      if (!resp.ok) { return resp.json().then(function (err) {
        throw new Error('HTTP ' + resp.status + ' ' + JSON.stringify(err));
      }); }
      return resp.json();
    }).then(function (data) {
      resultMount.textContent = '';
      if (data.recognized) {
        var hitText;
        if (data.hit === true) { hitText = '命中'; }
        else if (data.hit === false) { hitText = '未命中'; }
        else { hitText = '不可考'; }
        var hitCls = data.hit === true ? 'ipa-hit' : (data.hit === false ? 'ipa-miss' : 'ipa-unknown');
        resultMount.appendChild(row('识别样式: ' + data.label + '（置信度 ' +
            (data.confidence != null ? data.confidence.toFixed(3) : '—') +
            '，模型 ' + (data.model_version || '?') + '）'));
        resultMount.appendChild(row('标准答案: ' + (data.truth.style || '不可考') +
            '（来源 ' + (data.truth.source || '无') + '）——对照' + hitText, hitCls));
        say('识别完成（源 ' + data.iq_source + '）。');
      } else {
        // 提示态行（no_model/no_iq/short_iq…）——note 原文上屏不报错拦页
        resultMount.appendChild(row('状态: ' + data.status + '——' + (data.note || '')));
        if (data.truth && data.truth.style) {
          resultMount.appendChild(row('标准答案: ' + data.truth.style +
              '（来源 ' + (data.truth.source || '无') + '）——对照不可考', 'ipa-unknown'));
        }
        say('识别未果（提示态，不阻塞）——详见结果行。');
      }
    }).catch(function (err) { say('识别失败: ' + err.message, true); });
  });
})();
</script>
</section>
"""
