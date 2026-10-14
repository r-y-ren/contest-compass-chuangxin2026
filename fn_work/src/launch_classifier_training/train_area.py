"""AI 页训练面板页区：ai 页 train-panel 挂载点消费 POST /api/ai/train+
GET /api/ai/train/{task_id}+GET /api/ai/models 的纯静态资产（HTML+内联 JS）——
重写规约与签名意图详见 fn_docs/responsibility.md（R65 AI 页区）。

产出口径（R65，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用 R57
edit_scenario_ui / R60 build_report_view_area / R63 build_dataset_area 的
serve_console 缺省装配注入模式）：

- ``#train-panel`` 挂载点渲染训练表单：样式筛选（style，空=全量）+执行地
  （remote/local）+dry_run 复选 → POST ``/api/ai/train`` {'query': {'style': …},
  'where', 'dry_run'} → 202 任务句柄 → 轮询 GET ``/api/ai/train/{task_id}``
  至终态（done 附 labels/n_samples/dispatched；failed 附拒训原因原文上屏）；
- 模型列表：载入即 GET ``/api/ai/models`` → 模型条目行（名称/标签/大小/
  修改时间）——未训练（空列表）如实提示不报错；
- 零外链：仅同源相对路径 fetch（/api/ai/train、/api/ai/train/{task_id}、
  /api/ai/models），无任何 http(s) 外部资源引用（R56 断网全可用口径）。
"""

#: 模型列表容器元素 class（页区协作锚点；模板内字面引用与此常量同值）。
MODEL_ROW_CLASS = "model-row"


def build_train_area() -> str:
    """AI 页训练面板页区（纯静态资产 str，serve_console 缺省装配注入 ai 页）。

    Returns:
        ``<section id="train-panel-area">``+内联 <style>/<script> 的区块资产
        str——JS 填充 ai 骨架页的 #train-panel 挂载点；零外链（站内相对路径
        自足）。
    """
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——任务/模型运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="train-panel-area" aria-label="AI 训练任务">
<style>
#train-panel-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#train-panel-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#train-panel-area .tpa-status { color: #6b7486; font-size: 13px; margin: 6px 0; word-break: break-all; }
#train-panel-area .tpa-error { color: #c0392b; font-size: 13px; margin: 6px 0; word-break: break-all; }
#train-panel-area .tpa-form { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 8px 0; }
#train-panel-area .tpa-form label { font-size: 13px; color: #1c2333; }
#train-panel-area .tpa-form input, #train-panel-area .tpa-form select { padding: 2px 6px; border: 1px solid #c9d4e4; border-radius: 4px; }
#train-panel-area .tpa-form button { padding: 3px 12px; border: 1px solid #2c5aa0; border-radius: 4px; background: #f2f6fb; color: #2c5aa0; cursor: pointer; }
#train-panel-area ul.tpa-models { margin: 6px 0 0; padding: 0; list-style: none; font-size: 13px; }
#train-panel-area li.model-row { padding: 3px 0; border-bottom: 1px dashed #e3e9f2; word-break: break-all; }
#train-panel-area li.model-row .tpa-labels { color: #1e7a35; }
</style>
<h2>样式分类器训练</h2>
<p class="tpa-status" id="tpa-status">模型列表载入中……（数据源 /api/ai/models）。</p>
<script>
(function () {
  var panel = document.getElementById('train-panel');
  if (!panel) { return; }
  var statusLine = document.getElementById('tpa-status');
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'tpa-error' : 'tpa-status';
  };
  // ---- 训练表单：样式筛选+执行地+dry_run → POST /api/ai/train ----
  var styleInput = document.createElement('input');
  styleInput.id = 'tpa-style'; styleInput.placeholder = '样式如 tone（空=全量）';
  var whereSel = document.createElement('select');
  whereSel.id = 'tpa-where';
  ['remote', 'local'].forEach(function (name) {
    var opt = document.createElement('option'); opt.value = name; opt.textContent = name; whereSel.appendChild(opt);
  });
  var dryBox = document.createElement('input');
  dryBox.id = 'tpa-dry-run'; dryBox.type = 'checkbox';
  var dryLabel = document.createElement('label');
  var dryInner = document.createElement('span'); dryInner.textContent = ' dry_run（不真派发）';
  dryLabel.appendChild(dryBox); dryLabel.appendChild(dryInner);
  var trainBtn = document.createElement('button');
  trainBtn.id = 'tpa-start'; trainBtn.type = 'button'; trainBtn.textContent = '发起训练';
  var form = document.createElement('div'); form.className = 'tpa-form';
  var addLabeled = function (text, el) {
    var label = document.createElement('label'); label.textContent = text + '：';
    form.appendChild(label); form.appendChild(el);
  };
  addLabeled('样式筛选', styleInput);
  addLabeled('执行地', whereSel);
  form.appendChild(dryLabel);
  form.appendChild(trainBtn);
  panel.appendChild(form);
  // ---- 模型列表：GET /api/ai/models ----
  var modelList = document.createElement('ul');
  modelList.className = 'tpa-models'; modelList.id = 'tpa-models';
  panel.appendChild(modelList);
  var loadModels = function () {
    fetch('/api/ai/models').then(function (resp) {
      if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
      return resp.json();
    }).then(function (data) {
      modelList.textContent = '';
      var rows = (data && data.models) || [];
      if (!rows.length) {
        var empty = document.createElement('li'); empty.className = 'model-row';
        empty.textContent = '尚无模型（先在上方发起一次 local 训练）——提示态，不阻塞。';
        modelList.appendChild(empty);
        return;
      }
      rows.forEach(function (row) {
        var li = document.createElement('li'); li.className = 'model-row';
        var labels = row.labels ? ' 标签=' + row.labels.join(',') : '';
        li.textContent = row.name + labels + ' ' + row.size_bytes + 'B ' + row.modified_at;
        modelList.appendChild(li);
      });
    }).catch(function (err) { say('模型列表载入失败: ' + err.message, true); });
  };
  // ---- 发起训练：POST /api/ai/train → 轮询 GET /api/ai/train/{task_id} ----
  trainBtn.addEventListener('click', function () {
    var body = { where: whereSel.value, dry_run: dryBox.checked };
    if (styleInput.value.trim()) { body.query = { style: styleInput.value.trim() }; }
    else { body.query = {}; }
    say('训练任务提交中……（POST /api/ai/train）');
    fetch('/api/ai/train', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (resp) {
      if (!resp.ok) { return resp.json().then(function (err) {
        throw new Error('HTTP ' + resp.status + ' ' + JSON.stringify(err));
      }); }
      return resp.json();
    }).then(function (data) {
      var poll = function () {
        fetch('/api/ai/train/' + encodeURIComponent(data.task_id)).then(function (resp) { return resp.json(); })
          .then(function (task) {
            if (task.status === 'running') { setTimeout(poll, 500); return; }
            if (task.status === 'done') {
              var r = task.result || {};
              say('训练完成：task=' + task.task_id + ' where=' + task.where +
                  ' n_samples=' + r.n_samples + ' labels=' + (r.labels || []).join(',') +
                  ' dispatched=' + r.dispatched + '（模型列表已刷新）');
              loadModels();
            } else {
              say('训练失败（拒训/远程不可达——原因原文）: ' + (task.error || 'unknown'), true);
            }
          }).catch(function (err) { say('任务状态轮询失败: ' + err.message, true); });
      };
      say('训练任务已受理：task=' + data.task_id + '——轮询终态中……');
      setTimeout(poll, 500);
    }).catch(function (err) { say('训练提交失败: ' + err.message, true); });
  });
  loadModels();
})();
</script>
</section>
"""
