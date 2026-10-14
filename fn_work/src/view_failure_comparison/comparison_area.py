"""跨轮失效对比页区：reports 页 comparison 挂载点消费 POST /api/runs/compare 的
纯静态资产（HTML+内联 JS）——重写规约与签名意图详见 fn_docs/responsibility.md（R62
对比页区）。

产出口径（R62，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用 R57/R58/
R60/R61 的 serve_console 缺省装配注入模式）：

- 运行集来自 **run-list 行勾选**（R61 运行列表行的 ``input.run-select`` 复选框
  ——同页协作，本区块不重复造运行选择器）：点「对比选中运行」→收集
  ``#run-list input.run-select:checked`` 的 data-run →POST ``/api/runs/compare``
  body ``{'run_ids': [...]}``；
- 响应上屏 ``#comparison`` 挂载点：结论段（R26 薄弱环节结论原文）+降级标注
  （degraded——样本不足降级单样式，R26 口径）+对比表（样式/中位失效电平 dB/
  有效条目数/最小/最大——按中位数升序）+无失效数据标注行（未失效/无结果）+
  缺失运行清单+条目计数；
- 未勾选任何运行→提示先勾选（不发包）；请求失败→错误行如实呈现不静默；
- 零外链：仅同源相对路径 fetch（/api/runs/compare），无任何 http(s) 外部资源
  引用（R56/R62 断网全可用口径）。
"""


def build_comparison_area() -> str:
    """跨轮失效对比页区（纯静态资产 str，serve_console 缺省装配注入 reports 页）。

    Returns:
        ``<section id="comparison-area">``+内联 <style>/<script> 的区块资产 str
        ——JS 填充 reports 骨架页的 #comparison 挂载点（多选运行→对比表+结论）；
        零外链（站内相对路径自足）。
    """
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——运行集运行期从 run-list 勾选取；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="comparison-area" aria-label="跨轮失效对比视图">
<style>
#comparison-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#comparison-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#comparison-area .cmp-status { color: #6b7486; font-size: 13px; margin: 6px 0; }
#comparison-area .cmp-error { color: #c0392b; font-size: 14px; margin: 6px 0; }
#comparison-area button { margin: 4px 0; padding: 4px 14px; border-radius: 4px;
  border: 1px solid #2c5aa0; background: #2c5aa0; color: #fff; font-size: 13px; }
#comparison-area #comparison-conclusion { background: #f2f6fb; border-left: 4px solid #2c5aa0;
  padding: 6px 10px; margin: 8px 0; font-size: 13px; }
#comparison-area .cmp-degraded { display: inline-block; margin: 4px 0; padding: 2px 10px;
  border-radius: 10px; font-size: 12px; border: 1px solid #8a6d3b; background: #fdf6ec; color: #8a6d3b; }
#comparison-area table { border-collapse: collapse; width: 100%; font-size: 13px; background: #fff; }
#comparison-area th, #comparison-area td { border: 1px solid #e3e9f2; padding: 4px 8px; text-align: left; }
#comparison-area th { background: #f2f6fb; color: #2c5aa0; }
#comparison-area ul { margin: 4px 0; padding-left: 22px; font-size: 13px; }
</style>
<h2>跨轮失效对比视图</h2>
<p class="cmp-status" id="cmp-status">在上方运行列表勾选两次（含）以上运行后点「对比选中运行」——
对比表+薄弱环节结论（数据源 POST /api/runs/compare）。</p>
<p><button id="cmp-run" type="button">对比选中运行</button></p>
<script>
(function () {
  var mount = document.getElementById('comparison');
  var statusLine = document.getElementById('cmp-status');
  var button = document.getElementById('cmp-run');
  if (!mount || !button) { return; }
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'cmp-error' : 'cmp-status';
  };
  var append = function (node) { mount.appendChild(node); };
  button.addEventListener('click', function () {
    // 运行集来自 R61 run-list 行勾选（同页协作——input.run-select 复选框）。
    var checked = Array.prototype.slice.call(
      document.querySelectorAll('#run-list input.run-select:checked'));
    var runIds = checked.map(function (box) { return box.getAttribute('data-run'); });
    mount.textContent = '';
    if (!runIds.length) {
      say('未勾选任何运行——请先在上方运行列表勾选要对比的运行。', true);
      return;
    }
    say('对比 ' + runIds.length + ' 次运行中……');
    fetch('/api/runs/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_ids: runIds })
    }).then(function (resp) {
      if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
      return resp.json();
    }).then(function (data) {
      mount.textContent = '';
      var conclusion = document.createElement('p');
      conclusion.id = 'comparison-conclusion';
      conclusion.textContent = data.conclusion || '';
      append(conclusion);
      if (data.degraded) {
        var badge = document.createElement('span');
        badge.className = 'cmp-degraded';
        badge.id = 'comparison-degraded';
        badge.textContent = '样本不足：仅单一样式，降级单样式报告（R26 口径）';
        append(badge);
      }
      var rows = data.comparison || [];
      if (rows.length) {
        var table = document.createElement('table');
        table.id = 'comparison-table';
        var thead = document.createElement('thead');
        var head = document.createElement('tr');
        ['样式', '中位失效电平(dB)', '有效条目数', '最小(dB)', '最大(dB)'].forEach(function (title) {
          var th = document.createElement('th'); th.textContent = title; head.appendChild(th);
        });
        thead.appendChild(head); table.appendChild(thead);
        var tbody = document.createElement('tbody');
        rows.forEach(function (row) {
          var tr = document.createElement('tr');
          [String(row.style), String(row.median_level_db), String(row.n_runs),
           String(row.min_db), String(row.max_db)].forEach(function (text) {
            var td = document.createElement('td'); td.textContent = text; tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        append(table);
      }
      var noFailure = data.runs_without_failure || [];
      if (noFailure.length) {
        var nfTitle = document.createElement('h3');
        nfTitle.textContent = '无失效数据运行（如实标注）';
        append(nfTitle);
        var ul = document.createElement('ul');
        ul.id = 'comparison-no-failure';
        noFailure.forEach(function (item) {
          var li = document.createElement('li');
          li.textContent = item.run_id + '：' + item.note;
          ul.appendChild(li);
        });
        append(ul);
      }
      var missing = data.missing_runs || [];
      if (missing.length) {
        var mTitle = document.createElement('h3');
        mTitle.textContent = '不存在的运行';
        append(mTitle);
        var mul = document.createElement('ul');
        mul.id = 'comparison-missing';
        missing.forEach(function (rid) {
          var li = document.createElement('li'); li.textContent = rid;
          mul.appendChild(li);
        });
        append(mul);
      }
      say('对比完成：汇聚 ' + (data.entries || []).length + ' 条失效电平条目'
          + (rows.length ? '，对比表 ' + rows.length + ' 行' : '，无跨样式对比表')
          + '。');
    }).catch(function (err) {
      say('对比失败: ' + err.message + '——400=运行名非法，500=对比失败', true);
    });
  });
})();
</script>
</section>
"""
