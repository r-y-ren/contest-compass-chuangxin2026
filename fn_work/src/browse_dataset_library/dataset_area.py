"""数据页录音库页区：data 页 dataset-grid/filters 挂载点消费 GET /api/dataset 的
纯静态资产（HTML+内联 JS）——重写规约与签名意图详见 fn_docs/responsibility.md（R63
数据页区）。

产出口格（R63，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用 R57
edit_scenario_ui / R58 build_realtime_charts / R60 build_report_view_area / R61
build_run_list_area 的 serve_console 缺省装配注入模式）：

- 载入即 fetch ``/api/dataset``（无参数）→ SigMF 真值对卡片网格上屏
  ``#dataset-grid`` 挂载点：每卡样式/功率/时长/批次/运行来源/日期/后端字段
  （browse_dataset_library 卡片契约），外加「回放此条」按钮（R64 接线）；
- ``#filters`` 挂载点渲染筛选器：样式输入+日期起止输入+「筛选」按钮 →
  ``/api/dataset?style=&date_from=&date_to=``（卡片按真值过滤）；
- 索引未建（index_status='missing'）→ 状态行如实提示+「重建索引」按钮
  （POST /api/dataset/rebuild → 完成后重载卡片，不报错拦页）；
- 「回放此条」仅 replayable 卡可点 → POST /api/run/replay {'run_id': …} →
  202 返回操控台运行 id → 轮询 GET /api/runs/{id} 至终态（done/failed）上屏
  ——回放运行在实时曲线（/pages/index）与报告中心（/pages/reports）可见；
- 零外链：仅同源相对路径 fetch（/api/dataset、/api/dataset/rebuild、
  /api/run/replay、/api/runs/{id}），无任何 http(s) 外部资源引用
  （R56/R63 断网全可用口径）。
"""

#: 卡片网格元素 class（e2e/页区协作锚点；模板内字面引用与此常量同值）。
DATASET_CARD_CLASS = "dataset-card"


def build_dataset_area() -> str:
    """数据页录音库页区（纯静态资产 str，serve_console 缺省装配注入 data 页）。

    Returns:
        ``<section id="dataset-library-area">``+内联 <style>/<script> 的区块资产
        str——JS 填充 data 骨架页的 #dataset-grid/#filters 挂载点；零外链
        （站内相对路径自足）。
    """
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——数据运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="dataset-library-area" aria-label="录音库与数据集浏览">
<style>
#dataset-library-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#dataset-library-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#dataset-library-area .dsla-status { color: #6b7486; font-size: 13px; margin: 6px 0; }
#dataset-library-area .dsla-error { color: #c0392b; font-size: 14px; margin: 6px 0; }
#dataset-library-area .dsla-filters { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 8px 0; }
#dataset-library-area .dsla-filters label { font-size: 13px; color: #1c2333; }
#dataset-library-area .dsla-filters input { padding: 2px 6px; border: 1px solid #c9d4e4; border-radius: 4px; }
#dataset-library-area .dsla-filters button { padding: 3px 12px; border: 1px solid #2c5aa0; border-radius: 4px; background: #f2f6fb; color: #2c5aa0; cursor: pointer; }
#dataset-library-area .dsla-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
#dataset-library-area .dataset-card { border: 1px solid #e3e9f2; border-radius: 6px; padding: 8px 10px; background: #fff; font-size: 13px; }
#dataset-library-area .dataset-card h3 { margin: 0 0 4px; font-size: 13px; color: #2c5aa0; word-break: break-all; }
#dataset-library-area .dataset-card dl { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 2px 8px; }
#dataset-library-area .dataset-card dt { color: #6b7486; }
#dataset-library-area .dataset-card dd { margin: 0; word-break: break-all; }
#dataset-library-area .dataset-card button.replay-btn { margin-top: 6px; padding: 2px 10px; border: 1px solid #1e7a35; border-radius: 4px; background: #eaf7ee; color: #1e7a35; cursor: pointer; }
#dataset-library-area .dataset-card button.replay-btn:disabled { border-color: #b6bdc9; background: #f2f4f7; color: #b6bdc9; cursor: not-allowed; }
</style>
<h2>录音库与数据集</h2>
<p class="dsla-status" id="dsla-status">载入数据集索引中……（数据源 /api/dataset）。</p>
<script>
(function () {
  var grid = document.getElementById('dataset-grid');
  var filtersMount = document.getElementById('filters');
  var statusLine = document.getElementById('dsla-status');
  if (!grid || !filtersMount) { return; }
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'dsla-error' : 'dsla-status';
  };
  // ---- 筛选器（#filters 挂载点）：样式/日期 → /api/dataset 查询参数 ----
  var styleInput = document.createElement('input');
  styleInput.id = 'dsla-style'; styleInput.placeholder = '样式如 tone';
  var fromInput = document.createElement('input');
  fromInput.id = 'dsla-date-from'; fromInput.placeholder = '起始 YYYYMMDD';
  var toInput = document.createElement('input');
  toInput.id = 'dsla-date-to'; toInput.placeholder = '截止 YYYYMMDD';
  var filterBtn = document.createElement('button');
  filterBtn.id = 'dsla-apply'; filterBtn.type = 'button'; filterBtn.textContent = '筛选';
  filterBtn.addEventListener('click', function () { load(); });
  var rebuildBtn = document.createElement('button');
  rebuildBtn.id = 'dsla-rebuild'; rebuildBtn.type = 'button'; rebuildBtn.textContent = '重建索引';
  rebuildBtn.addEventListener('click', function () { rebuild(); });
  [['样式', styleInput], ['日期起', fromInput], ['日期止', toInput]].forEach(function (pair) {
    var label = document.createElement('label'); label.textContent = pair[0] + '：';
    filtersMount.appendChild(label); filtersMount.appendChild(pair[1]);
  });
  filtersMount.appendChild(filterBtn);
  filtersMount.appendChild(rebuildBtn);
  var query = function () {
    var parts = [];
    if (styleInput.value.trim()) { parts.push('style=' + encodeURIComponent(styleInput.value.trim())); }
    if (fromInput.value.trim()) { parts.push('date_from=' + encodeURIComponent(fromInput.value.trim())); }
    if (toInput.value.trim()) { parts.push('date_to=' + encodeURIComponent(toInput.value.trim())); }
    return parts.length ? '?' + parts.join('&') : '';
  };
  // ---- 回放按钮（R64 接线）：POST /api/run/replay → 轮询 /api/runs/{id} ----
  var replay = function (runId) {
    fetch('/api/run/replay', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId })
    }).then(function (resp) {
      if (!resp.ok) { return resp.json().then(function (err) {
        throw new Error('HTTP ' + resp.status + ' ' + JSON.stringify(err));
      }); }
      return resp.json();
    }).then(function (data) {
      say('回放已发起（运行 ' + data.run_id + '，源自 ' + data.replay_of + '）——轮询终态中……');
      var poll = function () {
        fetch('/api/runs/' + encodeURIComponent(data.run_id)).then(function (resp) { return resp.json(); })
          .then(function (entry) {
            if (entry.status === 'running') { setTimeout(poll, 500); return; }
            if (entry.status === 'done') {
              var result = entry.result || {};
              say('回放完成：运行 ' + data.run_id + ' status=' + result.status +
                  ' exit_code=' + result.exit_code + '（实时曲线/报告中心可见）');
            } else {
              say('回放失败：运行 ' + data.run_id + ' ' + (entry.error || 'unknown'), true);
            }
          }).catch(function (err) { say('回放状态轮询失败: ' + err.message, true); });
      };
      setTimeout(poll, 500);
    }).catch(function (err) { say('回放发起失败: ' + err.message, true); });
  };
  // ---- 卡片渲染（browse_dataset_library 卡片契约） ----
  var card = function (row) {
    var box = document.createElement('div');
    box.className = 'dataset-card';
    box.setAttribute('data-run', row.run_id);
    box.setAttribute('data-style', row.style);
    var head = document.createElement('h3');
    head.textContent = '录音 ' + row.source_run;
    box.appendChild(head);
    var dl = document.createElement('dl');
    var add = function (term, text) {
      var dt = document.createElement('dt'); dt.textContent = term;
      var dd = document.createElement('dd'); dd.textContent = text;
      dl.appendChild(dt); dl.appendChild(dd);
    };
    add('样式', row.style);
    add('功率(dBm)', row.power_dbm === null || row.power_dbm === undefined ? '—' : String(row.power_dbm));
    add('时长(s)', row.duration_s === null || row.duration_s === undefined ? '—' : String(row.duration_s));
    add('批次', row.batch_key || '—');
    add('运行来源', row.source_run);
    add('日期', row.date || '—');
    add('后端', row.backend);
    add('频点(MHz)', row.freq_mhz === null || row.freq_mhz === undefined ? '—' : String(row.freq_mhz));
    box.appendChild(dl);
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'replay-btn';
    btn.textContent = '回放此条';
    btn.disabled = !row.replayable;
    if (!row.replayable) { btn.title = '录音 .sigmf-meta/.sigmf-data 真值对不完整，不可回放'; }
    btn.addEventListener('click', function () { replay(row.run_id); });
    box.appendChild(btn);
    return box;
  };
  // ---- 载入（当前筛选条件）----
  var load = function () {
    say('载入数据集卡片中……');
    fetch('/api/dataset' + query()).then(function (resp) {
      if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
      return resp.json();
    }).then(function (data) {
      grid.textContent = '';
      if (data.index_status === 'missing') {
        say(data.hint || '数据集索引未建——先点「重建索引」。');
        return;
      }
      var rows = (data && data.cards) || [];
      if (!rows.length) {
        say('无匹配录音条目（共 ' + (data.total || 0) + ' 条在库）——调整筛选或重建索引。');
        return;
      }
      rows.forEach(function (row) { grid.appendChild(card(row)); });
      say('共 ' + rows.length + ' / ' + (data.total || rows.length) + ' 条录音匹配当前筛选。');
    }).catch(function (err) {
      say('数据集载入失败: ' + err.message + '——400=条件非法/未配置，500=索引读失败', true);
    });
  };
  // ---- 重建（index_dataset rebuild 口径：POST /api/dataset/rebuild）----
  var rebuild = function () {
    say('索引重建中……（扫描运行目录根，秒级）');
    fetch('/api/dataset/rebuild', { method: 'POST' }).then(function (resp) {
      if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
      return resp.json();
    }).then(function (data) {
      say('索引重建完成：收录 ' + (data.rebuilt || 0) + ' 条，跳过 ' + (data.skipped || 0) + ' 个无效运行。');
      load();
    }).catch(function (err) { say('索引重建失败: ' + err.message, true); });
  };
  load();
})();
</script>
</section>
"""
