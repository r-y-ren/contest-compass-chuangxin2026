"""仪表页 RFF 管道演示页区：instruments 页注入的纯静态资产（HTML+内联 JS）——
重写规约与签名意图详见 fn_docs/responsibility.md（R74 RFF 管道演示页区）。

产出口径（R74，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用
R70-R73 的 serve_console 缺省装配注入模式）：

- 「运行 smoke」按钮 → POST ``/api/demo/rff``（body 可空——小样本固定参数，
  同步演示秒级回）；
- 四阶段进度（取数→谱特征→分组 CV→部署模拟）逐阶段 detail+产物清单（model/
  evaluation/deployment 行）上屏；macro_f1/参数量/latency_note 缺位申报如实
  回显；
- 数据不足拒跑（400 TrainError 原文）→拒跑提示原样上屏（不静默）；
- 零外链：仅同源相对路径 fetch（/api/demo/rff）。
"""

#: 阶段进度条目 class（页区协作锚点；模板内字面引用与此常量同值）。
RFF_STAGE_CLASS = "rff-stage-row"


def build_rff_pipeline_area() -> str:
    """仪表页 RFF 管道演示页区（纯静态资产 str，serve_console 缺省装配注入）。"""
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——演示数据运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="rff-pipeline-area" aria-label="RFF 管道演示（smoke）">
<style>
#rff-pipeline-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#rff-pipeline-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#rff-pipeline-area .rfa-status { color: #6b7486; font-size: 13px; margin: 6px 0; word-break: break-all; }
#rff-pipeline-area .rfa-error { color: #c0392b; font-size: 13px; margin: 6px 0; word-break: break-all; }
#rff-pipeline-area button { margin: 6px 0; padding: 3px 12px; border: 1px solid #2c5aa0; border-radius: 4px; background: #f2f6fb; color: #2c5aa0; cursor: pointer; }
#rff-pipeline-area table.rfa-table { border-collapse: collapse; font-size: 13px; margin: 6px 0; }
#rff-pipeline-area table.rfa-table th, #rff-pipeline-area table.rfa-table td { border: 1px solid #d7dee9; padding: 3px 8px; text-align: left; }
#rff-pipeline-area tr.rff-stage-row td:first-child { white-space: nowrap; }
</style>
<h2>射频指纹识别管道演示（run_rff_pipeline smoke）</h2>
<p class="rfa-status" id="rfa-status">取数→谱特征→分组 CV→部署模拟四阶段 smoke（小样本固定参数）；数据不足如实拒跑提示。</p>
<button type="button" id="rfa-run-btn">运行 smoke</button>
<div id="rfa-result"></div>
<script>
(function () {
  var mount = document.getElementById('rfa-result');
  var statusLine = document.getElementById('rfa-status');
  var runBtn = document.getElementById('rfa-run-btn');
  if (!mount || !runBtn) { return; }
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'rfa-error' : 'rfa-status';
  };
  var makeTable = function (headers, rows, rowClass) {
    var table = document.createElement('table');
    table.className = 'rfa-table';
    var thead = document.createElement('tr');
    headers.forEach(function (h) {
      var th = document.createElement('th'); th.textContent = h; thead.appendChild(th);
    });
    table.appendChild(thead);
    rows.forEach(function (row) {
      var tr = document.createElement('tr');
      if (rowClass) { tr.className = rowClass; }
      row.forEach(function (cell) {
        var td = document.createElement('td'); td.textContent = String(cell); tr.appendChild(td);
      });
      table.appendChild(tr);
    });
    return table;
  };
  var render = function (data) {
    mount.textContent = '';
    var h3 = document.createElement('h3'); h3.textContent = '阶段进度（' + data.stage_progress + '）'; mount.appendChild(h3);
    mount.appendChild(makeTable(['阶段', '状态', '明细'],
      (data.stages || []).map(function (s) { return [s.stage, s.status, s.detail]; }),
      'rff-stage-row'));
    h3 = document.createElement('h3'); h3.textContent = '产物清单'; mount.appendChild(h3);
    mount.appendChild(makeTable(['产物', '类型', '明细'],
      (data.artifacts || []).map(function (a) {
        if (a.name === 'model') {
          return [a.name, a.kind, 'labels=' + (a.labels || []).join('/') + '，参数量 ' + a.n_params];
        }
        if (a.name === 'evaluation') {
          return [a.name, a.kind, 'macro_f1=' + a.macro_f1 + '，折数 ' + a.n_folds];
        }
        return [a.name, a.kind, 'endpoint=' + a.endpoint + '，latency_note=' + a.latency_note];
      })));
    var note = document.createElement('p'); note.className = 'rfa-status';
    note.textContent = data.note || ''; mount.appendChild(note);
  };
  var run = function () {
    say('管道 smoke 运行中……（POST /api/demo/rff）');
    fetch('/api/demo/rff', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}'
    }).then(function (resp) {
      if (!resp.ok) { return resp.json().then(function (err) {
        throw new Error('HTTP ' + resp.status + ' ' + JSON.stringify(err));
      }); }
      return resp.json();
    }).then(function (data) {
      render(data);
      say('smoke 完成（有效样本 ' + data.n_samples + '，跳段 ' + data.skipped +
          '，macro_f1=' + data.evaluation.macro_f1 + '）——部署时延为缺位申报（simulated）。');
    }).catch(function (err) { say('管道演示拒跑/失败: ' + err.message, true); });
  };
  runBtn.addEventListener('click', run);
})();
</script>
</section>
"""
