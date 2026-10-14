"""仪表页标定看板区：instruments 页 instrument-panels 挂载点附近的纯静态资产
（HTML+内联 JS）——重写规约与签名意图详见 fn_docs/responsibility.md（R70 标定看板区）。

产出口径（R70，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用 R57
edit_scenario_ui / R60 build_report_view_area / R69 build_instrument_panels_area
的 serve_console 缺省装配注入模式）：

- 标定三件只读看板：载入即 GET ``/api/calibration`` 刷增益标定表/自漏标定/
  全链路补偿（link_loss+antenna）当前状态——在位（附条目数）/【待实测】占位
  如实显示/损坏 error 原文上屏（不虚构不静默）；
- 合成数据演示一键走：「合成演示」按钮 → GET ``/api/calibration?demo=1`` →
  三分支结果上屏（合成建表成功+loader 回读条目数/非单调拒用原文/样本不足拒用
  原文）——演示仅写临时目录，只读不改真实标定表（按钮无任何 POST，无写口）；
- 零外链：仅同源相对路径 fetch（/api/calibration），无任何 http(s) 外部资源
  引用（R56 断网全可用口径）。
"""

#: 看板表状态卡元素 class（页区协作锚点；模板内字面引用与此常量同值）。
CALIBRATION_CARD_CLASS = "calibration-table-card"


def build_calibration_status_area() -> str:
    """仪表页标定看板区（纯静态资产 str，serve_console 缺省装配注入 instruments 页）。

    Returns:
        ``<section id="calibration-status-area">``+内联 <style>/<script> 的区块
        资产 str——JS 填充 instruments 骨架页 #instrument-panels 挂载点附近；
        零外链（站内相对路径自足）。
    """
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——看板/演示数据运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="calibration-status-area" aria-label="标定三件只读看板">
<style>
#calibration-status-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#calibration-status-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#calibration-status-area .csa-status { color: #6b7486; font-size: 13px; margin: 6px 0; word-break: break-all; }
#calibration-status-area .csa-error { color: #c0392b; font-size: 13px; margin: 6px 0; word-break: break-all; }
#calibration-status-area .csa-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }
#calibration-status-area .calibration-table-card { border: 1px solid #e3e9f2; border-radius: 6px; padding: 8px 10px; background: #fff; font-size: 13px; }
#calibration-status-area .calibration-table-card h3 { margin: 0 0 4px; font-size: 13px; color: #2c5aa0; }
#calibration-status-area .calibration-table-card .csa-state { font-weight: bold; }
#calibration-status-area .calibration-table-card .csa-state.ok { color: #1e7a35; }
#calibration-status-area .calibration-table-card .csa-state.placeholder { color: #8a6d1a; }
#calibration-status-area .calibration-table-card .csa-state.insufficient { color: #8a6d1a; }
#calibration-status-area .calibration-table-card .csa-state.error { color: #c0392b; }
#calibration-status-area button { margin: 6px 0; padding: 3px 12px; border: 1px solid #2c5aa0; border-radius: 4px; background: #f2f6fb; color: #2c5aa0; cursor: pointer; }
#calibration-status-area pre.csa-demo { margin: 4px 0; padding: 6px; background: #f6f8fb; font-size: 11px; max-height: 260px; overflow: auto; white-space: pre-wrap; word-break: break-all; }
</style>
<h2>标定三件只读看板（增益标定 / 自漏标定 / 全链路补偿）</h2>
<p class="csa-status" id="csa-status">看板状态载入中……（数据源 GET /api/calibration，只读）。</p>
<div class="csa-grid" id="csa-grid"></div>
<button type="button" id="csa-demo-btn">合成数据演示（建表→非单调拒用等分支，只读不改真实表）</button>
<pre class="csa-demo" id="csa-demo" hidden></pre>
<script>
(function () {
  var grid = document.getElementById('csa-grid');
  var statusLine = document.getElementById('csa-status');
  var demoBtn = document.getElementById('csa-demo-btn');
  var demoPre = document.getElementById('csa-demo');
  if (!grid) { return; }
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'csa-error' : 'csa-status';
  };
  var pretty = function (value) {
    try { return JSON.stringify(value, null, 1); } catch (err) { return String(value); }
  };
  var renderCard = function (tableView) {
    var box = document.createElement('div');
    box.className = 'calibration-table-card';
    var head = document.createElement('h3');
    head.textContent = tableView.label + ' ';
    var state = document.createElement('span');
    state.className = 'csa-state ' + (tableView.status || 'placeholder');
    state.textContent = tableView.status;
    head.appendChild(state);
    box.appendChild(head);
    var meta = document.createElement('p');
    meta.className = 'csa-status';
    meta.textContent = (tableView.note || '') +
        (tableView.source ? '\nsource: ' + tableView.source : '') +
        (typeof tableView.entry_count === 'number' ? '（entry_count=' + tableView.entry_count + '）' : '');
    box.appendChild(meta);
    return box;
  };
  var renderPiece = function (piece, view) {
    if (piece === 'compensation') {
      var wrap = document.createElement('div');
      var title = document.createElement('h3');
      title.textContent = '全链路补偿（两表）';
      wrap.appendChild(title);
      ['link_loss', 'antenna'].forEach(function (name) {
        if (view[name]) { wrap.appendChild(renderCard(view[name])); }
      });
      return wrap;
    }
    return renderCard(view);
  };
  var load = function () {
    fetch('/api/calibration').then(function (resp) {
      if (!resp.ok) { throw new Error('HTTP ' + resp.status + ' ' + resp.statusText); }
      return resp.json();
    }).then(function (data) {
      grid.textContent = '';
      Object.keys(data.calibrations || {}).forEach(function (piece) {
        grid.appendChild(renderPiece(piece, data.calibrations[piece]));
      });
      say('标定三件状态已载入（目录 ' + (data.calibration_dir || '?') + '，只读——' + (data.note || '') + '）');
    }).catch(function (err) { say('看板状态载入失败: ' + err.message, true); });
  };
  if (demoBtn) {
    demoBtn.addEventListener('click', function () {
      if (demoPre) { demoPre.hidden = false; demoPre.textContent = '合成数据演示执行中……（GET /api/calibration?demo=1，仅写临时目录）'; }
      fetch('/api/calibration?demo=1').then(function (resp) {
        if (!resp.ok) { return resp.json().then(function (err) {
          throw new Error('HTTP ' + resp.status + ' ' + JSON.stringify(err));
        }); }
        return resp.json();
      }).then(function (data) {
        if (demoPre) { demoPre.textContent = pretty(data.demo); }
        say('合成数据演示完成（分支 ' + ((data.demo && data.demo.branches) || []).length +
            ' 条，wrote_real_table=' + (data.demo && data.demo.wrote_real_table) + '）');
      }).catch(function (err) {
        if (demoPre) { demoPre.textContent = ''; }
        say('合成数据演示失败: ' + err.message, true);
      });
    });
  }
  load();
})();
</script>
</section>
"""
