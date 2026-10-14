"""仪表页仪表面板区：instruments 页 instrument-panels/visa-status 挂载点消费
POST /api/instruments/{instrument}/{action}+GET /api/instruments 的纯静态资产
（HTML+内联 JS）——重写规约与签名意图详见 fn_docs/responsibility.md（R69 面板区）。

产出口径（R69，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用 R57
edit_scenario_ui / R60 build_report_view_area / R63 build_dataset_area 的
serve_console 缺省装配注入模式）：

- ``#instrument-panels`` 挂载点渲染五台模拟仪表卡（1433D/RSA513A/混频 13GHz/
  EMI 接收机/程控衰减器）：载入即 GET ``/api/instruments`` 刷面板状态；每卡
  「打开/读数演示/关闭」三按钮 → POST ``/api/instruments/{instrument}/{action}``
  （body 即 read 的可选配置 JSON）→ 读数/状态/超域 warnings 原文上屏；
- ``#visa-status`` 挂载点渲染 VISA 槽位状态：pyvisa 可用性+五台命令映射
  （builtin/generic）+真仪表接入层说明（create_visa_driver）——如实回显；
- 非法状态（未打开先读/先关 → 400）错误信息原样上屏（不静默）；
- 零外链：仅同源相对路径 fetch（/api/instruments、
  /api/instruments/{instrument}/{action}），无任何 http(s) 外部资源引用
  （R56 断网全可用口径）。
"""

#: 仪表卡片元素 class（页区协作锚点；模板内字面引用与此常量同值）。
PANEL_CARD_CLASS = "instrument-panel-card"


def build_instrument_panels_area() -> str:
    """仪表页仪表面板区（纯静态资产 str，serve_console 缺省装配注入 instruments 页）。

    Returns:
        ``<section id="instrument-panels-area">``+内联 <style>/<script> 的区块
        资产 str——JS 填充 instruments 骨架页的 #instrument-panels/#visa-status
        挂载点；零外链（站内相对路径自足）。
    """
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——面板状态运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="instrument-panels-area" aria-label="五台模拟仪表面板">
<style>
#instrument-panels-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#instrument-panels-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#instrument-panels-area .ipa-status { color: #6b7486; font-size: 13px; margin: 6px 0; word-break: break-all; }
#instrument-panels-area .ipa-error { color: #c0392b; font-size: 13px; margin: 6px 0; word-break: break-all; }
#instrument-panels-area .ipa-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }
#instrument-panels-area .instrument-panel-card { border: 1px solid #e3e9f2; border-radius: 6px; padding: 8px 10px; background: #fff; font-size: 13px; }
#instrument-panels-area .instrument-panel-card h3 { margin: 0 0 4px; font-size: 13px; color: #2c5aa0; }
#instrument-panels-area .instrument-panel-card .ipa-state { font-weight: bold; }
#instrument-panels-area .instrument-panel-card .ipa-state.open { color: #1e7a35; }
#instrument-panels-area .instrument-panel-card .ipa-state.closed { color: #6b7486; }
#instrument-panels-area .instrument-panel-card button { margin: 2px 4px 2px 0; padding: 2px 10px; border: 1px solid #2c5aa0; border-radius: 4px; background: #f2f6fb; color: #2c5aa0; cursor: pointer; }
#instrument-panels-area .instrument-panel-card pre.ipa-readings { margin: 4px 0; padding: 6px; background: #f6f8fb; font-size: 11px; max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-all; }
#instrument-panels-area #visa-status { font-size: 13px; }
#instrument-panels-area ul.ipa-warnings { margin: 4px 0; padding-left: 18px; font-size: 12px; color: #8a6d1a; }
</style>
<h2>五台模拟仪表面板（open / read-demo / close）</h2>
<p class="ipa-status" id="ipa-status">面板状态载入中……（数据源 GET /api/instruments）。</p>
<div class="ipa-grid" id="ipa-grid"></div>
<script>
(function () {
  var grid = document.getElementById('ipa-grid');
  var visaMount = document.getElementById('visa-status');
  var statusLine = document.getElementById('ipa-status');
  if (!grid) { return; }
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'ipa-error' : 'ipa-status';
  };
  var pretty = function (value) {
    try { return JSON.stringify(value, null, 1); } catch (err) { return String(value); }
  };
  var renderReadings = function (card, view) {
    var pre = card.querySelector('pre.ipa-readings');
    if (!pre) {
      pre = document.createElement('pre');
      pre.className = 'ipa-readings';
      card.appendChild(pre);
    }
    var head = 'action=' + view.action + ' state=' + view.state +
        (view.readback_note ? '\n' + view.readback_note : '');
    pre.textContent = head + '\n' + pretty(view.readings);
    var warns = view.warnings || [];
    if (warns.length) {
      var ul = document.createElement('ul'); ul.className = 'ipa-warnings';
      warns.forEach(function (w) {
        var li = document.createElement('li'); li.textContent = String(w); ul.appendChild(li);
      });
      card.appendChild(ul);
    }
  };
  var setState = function (card, state) {
    var el = card.querySelector('.ipa-state');
    if (!el) { return; }
    el.textContent = state;
    el.className = 'ipa-state ' + state;
  };
  var act = function (card, instrument, action, body) {
    fetch('/api/instruments/' + encodeURIComponent(instrument) + '/' + encodeURIComponent(action), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    }).then(function (resp) {
      if (!resp.ok) { return resp.json().then(function (err) {
        throw new Error('HTTP ' + resp.status + ' ' + JSON.stringify(err));
      }); }
      return resp.json();
    }).then(function (view) {
      setState(card, view.state);
      if (view.action === 'read') { renderReadings(card, view); }
      say(instrument + ' ' + view.action + ' → ' + view.state + (view.note ? '（' + view.note + '）' : ''));
      load();
    }).catch(function (err) { say(instrument + ' ' + action + ' 失败: ' + err.message, true); });
  };
  var card = function (row) {
    var box = document.createElement('div');
    box.className = 'instrument-panel-card';
    box.setAttribute('data-instrument', row.instrument);
    var head = document.createElement('h3');
    head.textContent = row.label + ' ';
    var state = document.createElement('span');
    state.className = 'ipa-state ' + (row.state || 'closed');
    state.textContent = row.state || 'closed';
    head.appendChild(state);
    box.appendChild(head);
    var meta = document.createElement('p');
    meta.className = 'ipa-status';
    meta.textContent = '注册名 ' + (row.registry ? row.registry.name : '?') +
        '（在位: ' + (row.registry && row.registry.registered) + '）';
    box.appendChild(meta);
    [['open', '打开'], ['read-demo', '读数演示'], ['close', '关闭']].forEach(function (pair) {
      var btn = document.createElement('button');
      btn.type = 'button'; btn.textContent = pair[1];
      btn.addEventListener('click', function () {
        var body = {};
        if (pair[0] === 'read-demo') {
          var raw = window.prompt('读数配置 JSON（可选，缺省 {}）', '{}');
          if (raw === null) { return; }
          if (raw.trim()) {
            try { body = JSON.parse(raw); }
            catch (err) { say('配置 JSON 解析失败: ' + err.message, true); return; }
          }
        }
        act(box, row.instrument, pair[0], body);
      });
      box.appendChild(btn);
    });
    return box;
  };
  var load = function () {
    fetch('/api/instruments').then(function (resp) {
      if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
      return resp.json();
    }).then(function (data) {
      grid.textContent = '';
      (data.instruments || []).forEach(function (row) { grid.appendChild(card(row)); });
      say('五台面板状态已载入（全部 simulated 读数——' + (data.note || '') + '）');
      if (visaMount) { renderVisa(data.visa || {}); }
    }).catch(function (err) { say('面板状态载入失败: ' + err.message, true); });
  };
  var renderVisa = function (visa) {
    visaMount.textContent = '';
    var title = document.createElement('h2');
    title.textContent = 'VISA 槽位状态（真仪表接入层）';
    visaMount.appendChild(title);
    var line = document.createElement('p');
    line.textContent = 'pyvisa 可用: ' + visa.pyvisa_available +
        (visa.pyvisa_available ? '' : '——' + (visa.install_hint || ''));
    visaMount.appendChild(line);
    var ul = document.createElement('ul');
    (visa.slots || []).forEach(function (slot) {
      var li = document.createElement('li');
      li.textContent = slot.instrument + '：命令映射 ' + slot.command_map +
          '（' + slot.visa_driver + '）';
      ul.appendChild(li);
    });
    visaMount.appendChild(ul);
  };
  load();
})();
</script>
</section>
"""
