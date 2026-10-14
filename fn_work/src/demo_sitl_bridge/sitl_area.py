"""仪表页 SITL 桥演示页区：instruments 页注入的纯静态资产（HTML+内联 JS）——
重写规约与签名意图详见 fn_docs/responsibility.md（R72 SITL 桥演示页区）。

产出口径（R72，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用 R70
build_calibration_status_area / R71 build_ledger_audit_area 的 serve_console
缺省装配注入模式）：

- run_id 输入+「生成映射预览」按钮 → POST ``/api/demo/sitl``（body
  ``{'run_id': str}``，同步演示——dry_run 纯计算秒级回）；
- 台阶表（level_db/per）+注入映射表（packet_loss/latency_ms/saturated）逐档
  渲染；SITL 不在位（sitl_available=False）→skip_note 跳过标注如实上屏
  （预览照常产出，不报错不阻塞——R53 口径）；
- 错误（运行无 KPI 数据等 400）→错误信息原样上屏（不静默）；
- 零外链：仅同源相对路径 fetch（/api/demo/sitl），无任何 http(s) 外部资源
  引用（R56 断网全可用口径）。
"""

#: 注入映射表条目 class（页区协作锚点；模板内字面引用与此常量同值）。
SITL_INJECTION_CLASS = "sitl-injection-row"


def build_sitl_bridge_area() -> str:
    """仪表页 SITL 桥演示页区（纯静态资产 str，serve_console 缺省装配注入）。"""
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——演示数据运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="sitl-bridge-area" aria-label="SITL 桥演示（dry_run 映射预览）">
<style>
#sitl-bridge-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#sitl-bridge-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#sitl-bridge-area .sba-status { color: #6b7486; font-size: 13px; margin: 6px 0; word-break: break-all; }
#sitl-bridge-area .sba-skip { color: #b3541e; font-size: 13px; margin: 6px 0; word-break: break-all; }
#sitl-bridge-area .sba-error { color: #c0392b; font-size: 13px; margin: 6px 0; word-break: break-all; }
#sitl-bridge-area input { padding: 3px 8px; border: 1px solid #c9d4e4; border-radius: 4px; }
#sitl-bridge-area button { margin: 6px 0 6px 8px; padding: 3px 12px; border: 1px solid #2c5aa0; border-radius: 4px; background: #f2f6fb; color: #2c5aa0; cursor: pointer; }
#sitl-bridge-area table.sba-table { border-collapse: collapse; font-size: 13px; margin: 6px 0; }
#sitl-bridge-area table.sba-table th, #sitl-bridge-area table.sba-table td { border: 1px solid #d7dee9; padding: 3px 8px; text-align: left; }
#sitl-bridge-area tr.sitl-injection-row td { font-variant-numeric: tabular-nums; }
</style>
<h2>SITL 链路退化注入桥演示（bridge_to_sitl dry_run 映射预览）</h2>
<p class="sba-status" id="sba-status">输入历史运行目录名（报告中心行口径）→提取 PER-功率台阶→生成台阶→丢包/时延注入映射预览（不真连 SITL）。</p>
<div>
  <label for="sba-run-input">run_id</label>
  <input id="sba-run-input" type="text" placeholder="运行目录名，如 20261013-083000-a1b2" />
  <button type="button" id="sba-run-btn">生成映射预览</button>
</div>
<div id="sba-result"></div>
<script>
(function () {
  var mount = document.getElementById('sba-result');
  var statusLine = document.getElementById('sba-status');
  var runBtn = document.getElementById('sba-run-btn');
  var runInput = document.getElementById('sba-run-input');
  if (!mount || !runBtn || !runInput) { return; }
  var say = function (text, isError, cls) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'sba-error' : (cls || 'sba-status');
  };
  var SITL_ROW_CLASS = 'sitl-injection-row';
  var makeTable = function (headers, rows) {
    var table = document.createElement('table');
    table.className = 'sba-table';
    var thead = document.createElement('tr');
    headers.forEach(function (h) {
      var th = document.createElement('th'); th.textContent = h; thead.appendChild(th);
    });
    table.appendChild(thead);
    rows.forEach(function (row) {
      var tr = document.createElement('tr');
      tr.className = SITL_ROW_CLASS;
      row.forEach(function (cell) {
        var td = document.createElement('td'); td.textContent = String(cell); tr.appendChild(td);
      });
      table.appendChild(tr);
    });
    return table;
  };
  var render = function (data) {
    mount.textContent = '';
    var h3 = document.createElement('h3'); h3.textContent = 'PER-功率台阶'; mount.appendChild(h3);
    mount.appendChild(makeTable(['档位 level_db', '窗均 PER'],
      (data.steps || []).map(function (s) { return [s.level_db, s.per]; })));
    h3 = document.createElement('h3'); h3.textContent = '注入映射预览（台阶→丢包/时延）'; mount.appendChild(h3);
    mount.appendChild(makeTable(['level_db', 'per', 'packet_loss', 'latency_ms', 'saturated'],
      (data.injections || []).map(function (inj) {
        return [inj.level_db, inj.per, inj.packet_loss, inj.latency_ms, inj.saturated];
      })));
    if (data.skip_note) {
      var p = document.createElement('p'); p.className = 'sba-skip';
      p.textContent = data.skip_note; mount.appendChild(p);
    }
    var note = document.createElement('p'); note.className = 'sba-status';
    note.textContent = data.note || ''; mount.appendChild(note);
  };
  var run = function () {
    var runId = (runInput.value || '').trim();
    if (!runId) { say('请先输入 run_id（运行目录名）', true); return; }
    say('映射预览生成中……（POST /api/demo/sitl，dry_run 纯计算）');
    fetch('/api/demo/sitl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId })
    }).then(function (resp) {
      if (!resp.ok) { return resp.json().then(function (err) {
        throw new Error('HTTP ' + resp.status + ' ' + JSON.stringify(err));
      }); }
      return resp.json();
    }).then(function (data) {
      render(data);
      say('映射预览完成（' + data.n_steps + ' 档台阶；sitl_available=' + data.sitl_available + '）——dry_run 未真连 SITL。');
    }).catch(function (err) { say('映射预览失败: ' + err.message, true); });
  };
  runBtn.addEventListener('click', run);
})();
</script>
</section>
"""
