"""报告中心运行列表页区：reports 页 run-list 挂载点消费 GET /api/runs/summaries 的
纯静态资产（HTML+内联 JS）——重写规约与签名意图详见 fn_docs/responsibility.md（R61
报告中心页区）。

产出口格（R61，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用 R57
edit_scenario_ui / R58 build_realtime_charts / R60 build_report_view_area 的
serve_console 缺省装配注入模式）：

- 载入即 fetch ``/api/runs/summaries`` → 元数据表格上屏 ``#run-list`` 挂载点
  （新建在前，服务端已排序）：列=选择（复选框，供 R62 对比页区勾选）/时间
  （started_at，UTC）/场景/样式/后端/状态/失效电平/操作（「查看报告」链接）；
- 「查看报告」链接仅在 ``report_relpath`` 在位时给出 → ``/pages/reports?run=<run_id>``
  （R60 报告查看区同页钻取——共页协作）；
- no_result 行如实标注（状态列 data-status='no_result'、时间/退出码 '—'——
  不虚构不剔除）；
- 与 R60 报告查看区共页协作：其无 ``?run=`` 参数分支也会写 #run-list（运行名
  清单）——本区块以 MutationObserver 守护表格归属（被覆写即重挂，最终稳定为
  元数据表格；R60 分支为一次性 fetch，无循环竞争）；
- 零外链：仅同源相对路径 fetch/链接（/api/runs/summaries、/pages/reports），
  无任何 http(s) 外部资源引用（R56/R61 断网全可用口径）。
"""

#: 元数据表格元素 id（e2e/区块协作锚点；MutationObserver 守护判定亦用——模板内
#: 三处字面引用与此常量同值）。
RUN_SUMMARY_TABLE_ID = "run-summary-table"


def build_run_list_area() -> str:
    """报告中心运行列表页区（纯静态资产 str，serve_console 缺省装配注入 reports 页）。

    Returns:
        ``<section id="run-list-area">``+内联 <style>/<script> 的区块资产 str
        ——JS 填充 reports 骨架页的 #run-list 挂载点；零外链（站内相对路径自足）。
    """
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——数据运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="run-list-area" aria-label="运行报告列表">
<style>
#run-list-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#run-list-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#run-list-area .rla-status { color: #6b7486; font-size: 13px; margin: 6px 0; }
#run-list-area .rla-error { color: #c0392b; font-size: 14px; margin: 6px 0; }
#run-list-area table { border-collapse: collapse; width: 100%; font-size: 13px; background: #fff; }
#run-list-area th, #run-list-area td { border: 1px solid #e3e9f2; padding: 4px 8px; text-align: left; }
#run-list-area th { background: #f2f6fb; color: #2c5aa0; }
#run-list-area td[data-status="completed"] { color: #1e7a35; }
#run-list-area td[data-status="failed"] { color: #c0392b; }
#run-list-area td[data-status="no_result"] { color: #8a6d3b; background: #fdf6ec; }
#run-list-area a { color: #2c5aa0; }
</style>
<h2>运行报告列表</h2>
<p class="rla-status" id="rla-status">载入运行摘要中……（数据源 /api/runs/summaries，新建在前）。</p>
<script>
(function () {
  var TABLE_ID = 'run-summary-table';
  var mount = document.getElementById('run-list');
  var statusLine = document.getElementById('rla-status');
  if (!mount) { return; }
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'rla-error' : 'rla-status';
  };
  var fmtTime = function (ts) {
    if (typeof ts !== 'number' || !isFinite(ts)) { return '—'; }
    return new Date(ts * 1000).toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  };
  var fmtLevels = function (levels) {
    if (!Array.isArray(levels) || !levels.length) { return '—'; }
    return levels.map(function (e) {
      return (e && typeof e === 'object') ? String(e.failure_level_db) : '?';
    }).join(', ');
  };
  var buildTable = function (rows) {
    var table = document.createElement('table');
    table.id = TABLE_ID;
    var thead = document.createElement('thead');
    var head = document.createElement('tr');
    ['选', '时间', '场景', '样式', '后端', '状态', '失效电平(dB)', '操作'].forEach(function (title) {
      var th = document.createElement('th'); th.textContent = title; head.appendChild(th);
    });
    thead.appendChild(head); table.appendChild(thead);
    var tbody = document.createElement('tbody');
    rows.forEach(function (row) {
      var tr = document.createElement('tr');
      tr.setAttribute('data-run', row.run_id);
      var sel = document.createElement('td');
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.className = 'run-select';           // R62 对比页区从此勾选运行集
      box.setAttribute('data-run', row.run_id);
      box.setAttribute('aria-label', '选择运行 ' + row.run_id);
      sel.appendChild(box); tr.appendChild(sel);
      [fmtTime(row.started_at), String(row.scenario_name), String(row.style),
       String(row.backend)].forEach(function (text) {
        var td = document.createElement('td'); td.textContent = text; tr.appendChild(td);
      });
      var st = document.createElement('td');
      st.setAttribute('data-status', row.status);
      st.textContent = row.status === 'no_result' ? 'no_result（无结果）' : row.status;
      tr.appendChild(st);
      var lv = document.createElement('td'); lv.textContent = fmtLevels(row.failure_levels);
      tr.appendChild(lv);
      var op = document.createElement('td');
      if (row.report_relpath) {
        var a = document.createElement('a');
        a.className = 'view-report-link';
        a.href = '/pages/reports?run=' + encodeURIComponent(row.run_id);
        a.textContent = '查看报告';
        op.appendChild(a);
      } else {
        op.textContent = '—';
      }
      tr.appendChild(op);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return table;
  };
  fetch('/api/runs/summaries').then(function (resp) {
    if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
    return resp.json();
  }).then(function (data) {
    var rows = (data && data.summaries) || [];
    mount.textContent = '';
    if (!rows.length) {
      say('暂无运行——发起一次运行后此处列出元数据行。');
      return;
    }
    mount.appendChild(buildTable(rows));
    say('共 ' + rows.length + ' 次运行（新建在前；勾选后可在下方跨轮对比区出对比表）。');
    // 共页守护：R60 报告查看区无 ?run= 参数分支也会写 #run-list——被覆写即重挂
    // 本表格（其分支为一次性 fetch，无循环竞争；?run= 钻取路径互不干扰）。
    if (typeof MutationObserver !== 'undefined') {
      new MutationObserver(function () {
        if (!mount.querySelector('#' + TABLE_ID)) {
          var table = buildTable(rows);
          mount.textContent = '';
          mount.appendChild(table);
        }
      }).observe(mount, { childList: true });
    }
  }).catch(function (err) {
    say('运行摘要载入失败: ' + err.message + '——400=report_root 未配置，500=扫描失败', true);
  });
})();
</script>
</section>
"""
