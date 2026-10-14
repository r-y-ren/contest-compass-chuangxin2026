"""台账页审计页区：ledger 页 audit-report/ledger-detail 挂载点消费
GET /api/ledger/audit 的纯静态资产（HTML+内联 JS）——重写规约与签名意图详见
fn_docs/responsibility.md（R71 审计页区）。

产出口径（R71，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用 R57
edit_scenario_ui / R60 build_report_view_area / R69 build_instrument_panels_area
的 serve_console 缺省装配注入模式）：

- ``#ledger-detail`` 挂载点渲染 done/total 明细（完成度+剩余条数，缺省仓库根
  锚定清单路径回显）；
- ``#audit-report`` 挂载点渲染审计报告：锚点失效清单（dead_anchor 逐条
  entry_id+detail）+其余差异（false_negative/ambiguous）+注释率（ratio/target/
  gap/meets_target）——「运行审计」按钮触发 GET ``/api/ledger/audit``（GET
  只读，无任何 POST 写口）；
- 审计失败（清单路径不存在等）→错误信息原样上屏（不静默）；
- 零外链：仅同源相对路径 fetch（/api/ledger/audit），无任何 http(s) 外部资源
  引用（R56 断网全可用口径）。
"""

#: 审计差异清单条目 class（页区协作锚点；模板内字面引用与此常量同值）。
AUDIT_ISSUE_CLASS = "ledger-audit-issue"


def build_ledger_audit_area() -> str:
    """台账页审计页区（纯静态资产 str，serve_console 缺省装配注入 ledger 页）。

    Returns:
        ``<section id="ledger-audit-area">``+内联 <style>/<script> 的区块资产
        str——JS 填充 ledger 骨架页 #ledger-detail/#audit-report 挂载点；
        零外链（站内相对路径自足）。
    """
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——审计数据运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="ledger-audit-area" aria-label="台账审计（只读）">
<style>
#ledger-audit-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#ledger-audit-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#ledger-audit-area .laa-status { color: #6b7486; font-size: 13px; margin: 6px 0; word-break: break-all; }
#ledger-audit-area .laa-error { color: #c0392b; font-size: 13px; margin: 6px 0; word-break: break-all; }
#ledger-audit-area button { margin: 6px 0; padding: 3px 12px; border: 1px solid #2c5aa0; border-radius: 4px; background: #f2f6fb; color: #2c5aa0; cursor: pointer; }
#ledger-audit-area table.laa-table { border-collapse: collapse; font-size: 13px; margin: 6px 0; }
#ledger-audit-area table.laa-table th, #ledger-audit-area table.laa-table td { border: 1px solid #d7dee9; padding: 3px 8px; text-align: left; }
#ledger-audit-area ul.ledger-audit-issues { margin: 4px 0; padding-left: 20px; font-size: 12px; }
#ledger-audit-area li.ledger-audit-issue { color: #c0392b; margin: 2px 0; word-break: break-all; }
#ledger-audit-area pre.laa-ratio { margin: 4px 0; padding: 6px; background: #f6f8fb; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
</style>
<h2>台账审计（audit_ledger 上页——只读，无写清单入口）</h2>
<p class="laa-status" id="laa-status">台账审计待触发（GET /api/ledger/audit，缺省仓库根锚定清单；只读）。</p>
<button type="button" id="laa-run-btn">运行审计（只读）</button>
<script>
(function () {
  var detailMount = document.getElementById('ledger-detail');
  var reportMount = document.getElementById('audit-report');
  var statusLine = document.getElementById('laa-status');
  var runBtn = document.getElementById('laa-run-btn');
  if (!detailMount || !reportMount) { return; }
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'laa-error' : 'laa-status';
  };
  var renderDetail = function (data) {
    detailMount.textContent = '';
    var title = document.createElement('h2');
    title.textContent = 'done/total 明细';
    detailMount.appendChild(title);
    var s = data.summary || {};
    var table = document.createElement('table');
    table.className = 'laa-table';
    [['done（完成条目）', s.done], ['total（总条目）', s.total], ['remaining（未完成）', s.remaining]].forEach(function (row) {
      var tr = document.createElement('tr');
      var th = document.createElement('th'); th.textContent = row[0];
      var td = document.createElement('td'); td.textContent = String(row[1]);
      tr.appendChild(th); tr.appendChild(td); table.appendChild(tr);
    });
    detailMount.appendChild(table);
    var path = document.createElement('p');
    path.className = 'laa-status';
    path.textContent = '清单: ' + data.ledger_path + '（代码树: ' + data.code_root + '）';
    detailMount.appendChild(path);
  };
  var renderReport = function (data) {
    reportMount.textContent = '';
    var title = document.createElement('h2');
    title.textContent = '审计报告（锚点失效清单+注释率）';
    reportMount.appendChild(title);
    var cleanLine = document.createElement('p');
    cleanLine.className = data.clean ? 'laa-status' : 'laa-error';
    cleanLine.textContent = data.clean ? 'clean=true——无差异条目' :
        'clean=false——差异 ' + (data.issues || []).length + ' 条（锚点失效 ' + (data.anchor_failures || []).length + ' 条）';
    reportMount.appendChild(cleanLine);
    (data.anchor_failures || []).forEach(function (issue) {
      var ul = document.createElement('ul'); ul.className = 'ledger-audit-issues';
      var li = document.createElement('li'); li.className = 'ledger-audit-issue';
      li.textContent = issue.entry_id + ' [' + issue.kind + ']: ' + issue.detail;
      ul.appendChild(li); reportMount.appendChild(ul);
    });
    var others = (data.issues || []).filter(function (issue) { return issue.kind !== 'dead_anchor'; });
    others.forEach(function (issue) {
      var ul = document.createElement('ul'); ul.className = 'ledger-audit-issues';
      var li = document.createElement('li'); li.className = 'ledger-audit-issue';
      li.textContent = issue.entry_id + ' [' + issue.kind + ']: ' + issue.detail;
      ul.appendChild(li); reportMount.appendChild(ul);
    });
    var ratio = data.comment_ratio || {};
    var pre = document.createElement('pre');
    pre.className = 'laa-ratio';
    pre.textContent = '注释率: ' + ratio.ratio + '（target ' + ratio.target +
        '，gap ' + ratio.gap + '，meets_target ' + ratio.meets_target + '）';
    reportMount.appendChild(pre);
    var note = document.createElement('p');
    note.className = 'laa-status';
    note.textContent = data.note || '';
    reportMount.appendChild(note);
  };
  var run = function () {
    say('审计执行中……（GET /api/ledger/audit，只读）');
    fetch('/api/ledger/audit').then(function (resp) {
      if (!resp.ok) { return resp.json().then(function (err) {
        throw new Error('HTTP ' + resp.status + ' ' + JSON.stringify(err));
      }); }
      return resp.json();
    }).then(function (data) {
      renderDetail(data);
      renderReport(data);
      say('台账审计完成（done ' + data.summary.done + '/' + data.summary.total +
          '，clean=' + data.clean + '）——只读，未写清单。');
    }).catch(function (err) { say('台账审计失败: ' + err.message, true); });
  };
  if (runBtn) { runBtn.addEventListener('click', run); }
  run();
})();
</script>
</section>
"""
