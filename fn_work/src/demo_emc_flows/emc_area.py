"""仪表页 EMC 表单区：instruments 页 instrument-panels 挂载点上部的纯静态资产
（HTML+内联 JS）——重写规约与签名意图详见 fn_docs/responsibility.md（R68 EMC 表单区）。

产出口径（R68，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用 R57
edit_scenario_ui / R60 build_report_view_area / R63 build_dataset_area 的
serve_console 缺省装配注入模式）：

- 三流程表单：流程选择（conduction/radiation/sweep）+ 流程参数 JSON 文本域
  （缺省 {}）→ POST ``/api/emc/{flow}`` {'params': …} → 202 运行句柄（操控台
  运行表同 /api/run 口径）→ 轮询 GET ``/api/runs/{run_id}`` 至终态；
- 终态上屏：done 附 demo_emc_flows 演示视图——图谱段（chart 平行列表→内联
  canvas 2D 折线，频轴 MHz 对数口径——R58 三路实时图同口径，不引入 SVG 命名
  空间字面量以保零外链文本断言）+ make_disclaimer_block('emc') 口径声明原文+
  warnings 裁剪标注逐条上屏；failed 附错误原文（不静默）；
- 零外链：仅同源相对路径 fetch（/api/emc/{flow}、/api/runs/{id}），无任何
  http(s) 外部资源引用（R56 断网全可用口径）。
"""

#: 图谱 canvas 折线元素 class（页区协作锚点；模板内字面引用与此常量同值）。
EMC_CHART_CLASS = "emc-chart-line"


def build_emc_area() -> str:
    """仪表页 EMC 表单区（纯静态资产 str，serve_console 缺省装配注入 instruments 页）。

    Returns:
        ``<section id="emc-flows-area">``+内联 <style>/<script> 的区块资产
        str——JS 注入 instruments 骨架页 #instrument-panels 挂载点顶部；零外链
        （站内相对路径自足）。
    """
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——运行/图谱数据运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="emc-flows-area" aria-label="EMC 三流程演示">
<style>
#emc-flows-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#emc-flows-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#emc-flows-area .efa-status { color: #6b7486; font-size: 13px; margin: 6px 0; word-break: break-all; }
#emc-flows-area .efa-error { color: #c0392b; font-size: 13px; margin: 6px 0; word-break: break-all; }
#emc-flows-area .efa-form { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 8px 0; }
#emc-flows-area .efa-form label { font-size: 13px; color: #1c2333; }
#emc-flows-area .efa-form select, #emc-flows-area .efa-form textarea { padding: 2px 6px; border: 1px solid #c9d4e4; border-radius: 4px; }
#emc-flows-area textarea { min-width: 320px; min-height: 40px; font-family: monospace; }
#emc-flows-area .efa-form button { padding: 3px 12px; border: 1px solid #2c5aa0; border-radius: 4px; background: #f2f6fb; color: #2c5aa0; cursor: pointer; }
#emc-flows-area pre.efa-disclaimer { margin: 6px 0; padding: 8px; background: #f6f8fb; border-left: 3px solid #2c5aa0; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
#emc-flows-area ul.efa-warnings { margin: 4px 0; padding-left: 20px; font-size: 12px; color: #8a6d1a; }
#emc-flows-area canvas.efa-chart { width: 100%; height: 160px; border: 1px solid #e3e9f2; background: #fff; }
</style>
<h2>EMC 三流程演示（传导 / 辐射 / 扫频）</h2>
<p class="efa-status" id="efa-status">选流程+参数后发起——经操控台运行器执行（/api/emc/{flow} → /api/runs/{id} 轮询）。</p>
<script>
(function () {
  var mount = document.getElementById('instrument-panels');
  if (!mount) { return; }
  var box = document.getElementById('emc-flows-area');
  var statusLine = document.getElementById('efa-status');
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'efa-error' : 'efa-status';
  };
  // ---- 表单：流程选择+参数 JSON → POST /api/emc/{flow} ----
  var flowSel = document.createElement('select');
  flowSel.id = 'efa-flow';
  ['conduction', 'radiation', 'sweep'].forEach(function (name) {
    var opt = document.createElement('option'); opt.value = name; opt.textContent = name; flowSel.appendChild(opt);
  });
  var paramsArea = document.createElement('textarea');
  paramsArea.id = 'efa-params'; paramsArea.placeholder = '{"band": "cispr_a"} 或 {"freq_hz": 10e6} —— 缺省 {}';
  var runBtn = document.createElement('button');
  runBtn.id = 'efa-run'; runBtn.type = 'button'; runBtn.textContent = '发起 EMC 演示';
  var form = document.createElement('div'); form.className = 'efa-form';
  [['流程', flowSel]].forEach(function (pair) {
    var label = document.createElement('label'); label.textContent = pair[0] + '：';
    form.appendChild(label); form.appendChild(pair[1]);
  });
  var pLabel = document.createElement('label'); pLabel.textContent = '参数(JSON)：';
  form.appendChild(pLabel); form.appendChild(paramsArea); form.appendChild(runBtn);
  box.insertBefore(form, statusLine ? statusLine.nextSibling : null);
  // ---- 图谱段渲染：chart 平行列表 → 内联 canvas 折线（频轴 MHz 对数口径；
  // canvas 2D 同 R58 三路实时图口径——零外链文本口径不引入 SVG 命名空间字面量） ----
  var renderChart = function (chart) {
    if (!chart || !chart.freq_hz || !chart.freq_hz.length) { return null; }
    var xs = chart.freq_hz.map(function (f) { return Math.log10(Math.max(f, 1) / 1e6); });
    var yKey = chart.power_db ? 'power_db' : (chart.power_dbm ? 'power_dbm' : 'power_dbuv');
    var ys = chart[yKey];
    if (!ys || ys.length !== xs.length) { return null; }
    var yLo = Math.min.apply(null, ys), yHi = Math.max.apply(null, ys);
    if (yHi === yLo) { yHi = yLo + 1.0; }
    var xLo = Math.min.apply(null, xs), xHi = Math.max.apply(null, xs);
    if (xHi === xLo) { xHi = xLo + 1.0; }
    var W = 600, H = 150, pad = 8;
    var canvas = document.createElement('canvas');
    canvas.width = W; canvas.height = H;
    canvas.className = 'emc-chart-line';
    canvas.setAttribute('aria-label', 'EMC 图谱段折线（模拟读数）');
    var ctx = canvas.getContext('2d');
    ctx.strokeStyle = '#2c5aa0'; ctx.lineWidth = 1.5;
    ctx.beginPath();
    xs.forEach(function (x, i) {
      var px = pad + (x - xLo) / (xHi - xLo) * (W - 2 * pad);
      var py = H - pad - (ys[i] - yLo) / (yHi - yLo) * (H - 2 * pad);
      if (i === 0) { ctx.moveTo(px, py); } else { ctx.lineTo(px, py); }
    });
    ctx.stroke();
    var caption = document.createElement('p');
    caption.className = 'efa-status';
    caption.textContent = '图谱段 kind=' + chart.kind + '：x=频轴 log10(MHz)，y=' + yKey + '（' + xs.length + ' 点，模拟读数）';
    var wrap = document.createElement('div');
    wrap.appendChild(canvas); wrap.appendChild(caption);
    return wrap;
  };
  // ---- 终态上屏：图谱+声明+warnings ----
  var renderOutcome = function (view) {
    var out = document.createElement('div');
    var head = document.createElement('p');
    head.className = 'efa-status';
    var run = view.run || {};
    head.textContent = 'EMC 演示完成：flow=' + view.flow + ' run status=' + run.status +
        ' exit_code=' + run.exit_code + (run.run_id ? '（运行 ' + run.run_id + '，实时曲线/报告中心可见）' : '');
    out.appendChild(head);
    var chartNode = renderChart(view.chart);
    if (chartNode) { out.appendChild(chartNode); }
    else {
      var none = document.createElement('p');
      none.className = 'efa-error';
      none.textContent = '图谱段不可得（chart=null）——' + (view.note || '');
      out.appendChild(none);
    }
    if (view.disclaimer) {
      var pre = document.createElement('pre');
      pre.className = 'efa-disclaimer';
      pre.textContent = view.disclaimer;
      out.appendChild(pre);
    }
    var warns = view.warnings || [];
    if (warns.length) {
      var ul = document.createElement('ul'); ul.className = 'efa-warnings';
      warns.forEach(function (w) {
        var li = document.createElement('li'); li.textContent = String(w); ul.appendChild(li);
      });
      out.appendChild(ul);
    }
    box.appendChild(out);
    say('EMC 演示完成（flow=' + view.flow + '）——图谱与口径声明已上屏；warnings ' + warns.length + ' 条。');
  };
  // ---- 发起：POST /api/emc/{flow} → 轮询 GET /api/runs/{run_id} ----
  runBtn.addEventListener('click', function () {
    var params = {};
    var text = paramsArea.value.trim();
    if (text) {
      try { params = JSON.parse(text); }
      catch (err) { say('参数 JSON 解析失败: ' + err.message, true); return; }
      if (typeof params !== 'object' || params === null || Array.isArray(params)) {
        say('参数 JSON 须为对象（如 {"band": "cispr_a"}）', true); return;
      }
    }
    say('EMC 演示提交中……（POST /api/emc/' + flowSel.value + '）');
    fetch('/api/emc/' + encodeURIComponent(flowSel.value), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ params: params })
    }).then(function (resp) {
      if (!resp.ok) { return resp.json().then(function (err) {
        throw new Error('HTTP ' + resp.status + ' ' + JSON.stringify(err));
      }); }
      return resp.json();
    }).then(function (data) {
      var poll = function () {
        fetch('/api/runs/' + encodeURIComponent(data.run_id)).then(function (resp) { return resp.json(); })
          .then(function (entry) {
            if (entry.status === 'running') { setTimeout(poll, 500); return; }
            if (entry.status === 'done') { renderOutcome(entry.result || {}); }
            else { say('EMC 演示失败（运行 ' + data.run_id + '）: ' + (entry.error || 'unknown'), true); }
          }).catch(function (err) { say('运行状态轮询失败: ' + err.message, true); });
      };
      say('EMC 演示已受理（运行 ' + data.run_id + '）——轮询终态中……');
      setTimeout(poll, 500);
    }).catch(function (err) { say('EMC 演示提交失败: ' + err.message, true); });
  });
})();
</script>
</section>
"""
