"""报告查看区页面区块：reports 页 report-view 挂载点消费 ?run=<id> 的纯静态资产（HTML+内联 JS）——重写规约与签名意图详见 fn_docs/responsibility.md（R60 报告页视图区）。

产出口径（R60，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用 R57
edit_scenario_ui / R58 build_realtime_charts 的 serve_console 缺省装配注入模式）：
- 从 URL 参数 ``?run=<run 目录名>`` 取运行号→GET /api/runs/{id}/report 取服务端
  渲染 HTML（含溯源结论徽标 #traceability-badge 与 plots 端点图引用）注入
  #report-html 上屏；
- plots 图列表：从已渲染报告的 <img> 提取（服务端已把 plots/xxx.png 改写为
  /api/runs/{id}/plots/xxx.png 端点引用）成链接清单；
- files 下载链接：白名单文件（与 serve_run_artifacts.FILES_WHITELIST 对齐的
  数据文件子集）逐个成下载链接；
- 溯源结论徽标：随报告 HTML 服务端注入（#traceability-badge，data-passed=
  true/false/none），区块只负责透显；
- 未带 ?run= 参数：提示用法并列出 GET /api/runs 运行清单（run-list 挂载点
  消费，链接回本页 ?run=<name>）；请求失败（404 运行不存在/400 非法名/500
  渲染失败）如实入区块错误行，不静默。
- 零外链：仅同源相对路径 fetch/链接（/api/runs/…、/pages/reports），无任何
  http(s) 外部资源引用（R56/R60 断网全可用口径）。
"""


def build_report_view_area() -> str:
    """报告查看区页面区块（纯静态资产 str，serve_console 缺省装配注入 reports 页）。

    Returns:
        ``<section id="report-view-area">``+内联 <style>/<script> 的区块资产
        str——JS 填充 reports 骨架页的 #report-view 挂载点（?run=<id> 驱动）；
        零外链（站内相对路径自足）。
    """
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——运行号运行期从 URL 取；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="report-view-area" aria-label="报告查看区">
<style>
#report-view-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#report-view-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#report-view-area .rva-status { color: #6b7486; font-size: 13px; margin: 6px 0; }
#report-view-area .rva-error { color: #c0392b; font-size: 14px; margin: 6px 0; }
#report-view-area #report-html { border: 1px solid #e3e9f2; border-radius: 6px; padding: 10px; margin: 8px 0; background: #fff; }
#report-view-area #traceability-badge { display: inline-block; margin: 6px 0; padding: 4px 12px; border-radius: 12px; font-size: 13px; border: 1px solid #9fb3cd; background: #f2f6fb; }
#report-view-area #traceability-badge[data-passed="true"] { border-color: #1e7a35; background: #eaf7ee; color: #1e7a35; }
#report-view-area #traceability-badge[data-passed="false"] { border-color: #c0392b; background: #fdf0ee; color: #c0392b; }
#report-view-area h3 { font-size: 14px; color: #2c5aa0; margin: 12px 0 4px; }
#report-view-area ul { margin: 4px 0; padding-left: 22px; font-size: 13px; }
#report-view-area a { color: #2c5aa0; }
</style>
<h2>报告查看区</h2>
<p class="rva-status" id="rva-status">用法：本页带 <code>?run=&lt;运行目录名&gt;</code> 参数即展示该运行的报告（渲染 HTML+曲线图+数据文件下载+溯源结论）。</p>
<script>
(function () {
  // 与 serve_run_artifacts.FILES_WHITELIST 对齐的数据文件子集（下载链接清单）。
  var FILES = ['kpi.csv', 'events.jsonl', 'monitor.csv', 'result.json', 'run.log',
               'scenario.yaml', 'report.md'];
  var mount = document.getElementById('report-view');
  var statusLine = document.getElementById('rva-status');
  if (!mount) { return; }
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'rva-error' : 'rva-status';
  };
  var runId = new URLSearchParams(window.location.search).get('run');

  if (!runId) {
    // 未指定运行：拉运行清单（run-list 挂载点），链接回本页 ?run=<name>。
    say('未指定运行——请带 ?run=<运行目录名> 访问，或从下方运行列表选择。');
    fetch('/api/runs').then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var listMount = document.getElementById('run-list');
        if (!listMount || !data || !data.runs || !data.runs.length) { return; }
        var ul = document.createElement('ul');
        data.runs.forEach(function (name) {
          var li = document.createElement('li');
          var a = document.createElement('a');
          a.href = '/pages/reports?run=' + encodeURIComponent(name);
          a.textContent = name;
          li.appendChild(a);
          ul.appendChild(li);
        });
        listMount.textContent = '';
        listMount.appendChild(ul);
      }).catch(function () { /* 运行清单尽力而为：失败不掩报告主路径 */ });
    return;
  }

  var base = '/api/runs/' + encodeURIComponent(runId);
  say('加载报告中：' + runId);
  fetch(base + '/report').then(function (resp) {
    if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
    return resp.text();
  }).then(function (htmlText) {
    mount.textContent = '';
    // 服务端渲染产物（零外链已断言）整体上屏：正文+曲线图（端点引用）+
    // 溯源结论徽标一并就位。
    var box = document.createElement('div');
    box.id = 'report-html';
    box.innerHTML = htmlText;
    mount.appendChild(box);

    // plots 图列表：从已渲染报告提取 img（服务端已改写为 plots 端点引用）。
    var imgs = Array.prototype.slice.call(box.querySelectorAll('img'));
    var plotBox = document.createElement('div');
    plotBox.id = 'plot-list';
    var ph = document.createElement('h3');
    ph.textContent = '曲线图（' + imgs.length + ' 张）';
    plotBox.appendChild(ph);
    var pul = document.createElement('ul');
    imgs.forEach(function (img) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = img.getAttribute('src');
      a.textContent = img.getAttribute('alt') || img.getAttribute('src');
      li.appendChild(a);
      pul.appendChild(li);
    });
    plotBox.appendChild(pul);
    mount.appendChild(plotBox);

    // files 下载链接（白名单数据文件）。
    var fileBox = document.createElement('div');
    fileBox.id = 'files-list';
    var fh = document.createElement('h3');
    fh.textContent = '原始数据文件下载';
    fileBox.appendChild(fh);
    var ful = document.createElement('ul');
    FILES.forEach(function (fname) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = base + '/files/' + fname;
      a.textContent = fname;
      li.appendChild(a);
      ful.appendChild(li);
    });
    fileBox.appendChild(ful);
    mount.appendChild(fileBox);
    say('运行 ' + runId + ' 的报告已载入（渲染 HTML+曲线图+溯源结论+数据下载）。');
  }).catch(function (err) {
    say('报告加载失败（' + runId + '）：' + err.message +
        '——404=运行不存在，400=非法运行名，500=报告渲染失败', true);
  });
})();
</script>
</section>
"""
