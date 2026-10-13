"""场景编辑器页面区块：表单/YAML 双模式+新建/编辑/删除接线既有场景 CRUD+校验错误逐条回显——重写规约与签名意图详见 fn_docs/responsibility.md。

产出口径（R57：纯静态资产 HTML+内联 JS，原生 fetch 自足，不依赖页面 Vue 实例）：
- 双模式切换：表单模式（字段级控件——style 七类白名单/fs/可选数值键/频段
  2.4G|5.8G 预设+安全声明必选项 shielded_box/dut_scope）与 YAML 文本模式
  （textarea 直接粘贴场景文本），一键互切；B24 N2 丢带防护——表单仅能表达
  单一频段，YAML 载入多带场景时切表单即警示、表单保存被阻止（countBands
  前端启发式：数 bands 行内流式对/块序列条目；服务端 load_scenario 仍为
  唯一权威校验）；
- 三操作接线既有场景 CRUD 端点：新建→POST /api/scenarios {'name','content'}、
  编辑→PUT /api/scenarios/{name} {'content'}（目标取场景下拉）、删除→DELETE
  /api/scenarios/{name}；表单模式提交前在浏览器内组装等价 YAML 文本，校验
  以服务端 load_scenario 全口径为准（前端不做影子校验）；
- 校验失败不吞错：400 响应体 detail.error 为多行错误清单（schema 编号清单或
  guard 红线条款），逐行成 <li> 上屏指明条目；404/网络错误同样入清单；
- 成功后刷新场景卡片：区块自带 #editor-cards 卡片视图，GET /api/scenarios
  重拉渲染（index 运行页卡片为装配期静态内嵌，刷新须走 API 实时数据）；
- cards 参数（build_scenario_cards 产物形状）经 '__/' 转义内嵌
  window.__EDITOR_CARDS__，供目标下拉与卡片视图初值；DOM 构建一律
  textContent（卡片名等用户数据不进 innerHTML）。
"""
import html
import json

__all__ = ["edit_scenario_ui"]

#: 区块根 id（serve_console 缺省装配在 index 运行页 </body> 前注入本区块）。
EDITOR_SECTION_ID = "scenario-editor"

# 区块模板（str.replace 令牌注入——不用 format：JS 花括号与 format 语法冲突；
# r 前缀：JS 字符串里的 '\n' 须原样落在产出资产中，不得被 Python 转义）。
_BLOCK_TEMPLATE = r"""<section id="scenario-editor" aria-label="场景编辑器">
<style>
#scenario-editor { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#scenario-editor h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#scenario-editor .sce-tabs { display: flex; gap: 6px; margin: 8px 0; }
#scenario-editor .sce-tab { padding: 4px 14px; border: 1px solid #2c5aa0; background: #fff; color: #2c5aa0; border-radius: 4px; cursor: pointer; }
#scenario-editor .sce-tab.active { background: #2c5aa0; color: #fff; font-weight: bold; }
#scenario-editor label { display: block; margin: 6px 0; font-size: 14px; }
#scenario-editor input, #scenario-editor select, #scenario-editor textarea { margin-left: 6px; }
#scenario-editor textarea { display: block; width: 98%; min-height: 160px; font-family: ui-monospace, monospace; font-size: 13px; }
#scenario-editor .sce-actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
#scenario-editor button { cursor: pointer; }
#scenario-editor .sce-danger { background: #c0392b; color: #fff; border: none; padding: 6px 16px; border-radius: 4px; }
#scenario-editor .sce-save { background: #2c5aa0; color: #fff; border: none; padding: 6px 16px; border-radius: 4px; }
#scenario-editor #editor-status { margin-top: 8px; font-size: 14px; }
#scenario-editor #editor-status.ok { color: #1e7a35; }
#scenario-editor #editor-status.err { color: #c0392b; }
#scenario-editor #editor-errors { margin: 6px 0; padding: 8px 8px 8px 28px; border: 1px solid #e4b6b0; background: #fdf0ee; border-radius: 6px; color: #a93226; font-size: 13px; }
#scenario-editor #editor-errors:empty { display: none; }
#scenario-editor #editor-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; margin-top: 8px; }
#scenario-editor .sce-card { border: 1px solid #c9d4e4; border-radius: 6px; padding: 8px; font-size: 13px; }
#scenario-editor .sce-card.sce-broken { border-color: #c0392b; background: #fdf0ee; }
#scenario-editor .sce-card h4 { margin: 0 0 4px; font-size: 14px; }
#scenario-editor .sce-hint { color: #6b7486; font-size: 12px; }
</style>
<h2>场景编辑器（新建 / 编辑 / 删除）</h2>
<div class="sce-tabs" role="tablist">
  <button type="button" id="editor-btn-mode-form" class="sce-tab active">表单模式</button>
  <button type="button" id="editor-btn-mode-yaml" class="sce-tab">YAML 模式</button>
</div>

<label>目标场景（选中即编辑/删除该场景；留空=新建）
  <select id="editor-target"><option value="">— 新建（不选目标）—</option>__TARGET_OPTIONS__</select>
</label>
<label>新场景名（新建时必填，落盘 &lt;name&gt;.yaml）
  <input type="text" id="editor-name" placeholder="如 tone_demo（不含扩展名）">
</label>

<div id="editor-panel-form">
  <label>描述（可选，写入 <code># desc:</code> 注释行）
    <input type="text" id="editor-f-desc" placeholder="一句话用途">
  </label>
  <label>样式 style（七类白名单）
    <select id="editor-f-style">
      <option value="tone">tone（定频音）</option>
      <option value="sweep">sweep（扫频）</option>
      <option value="chirp">chirp（啁啾）</option>
      <option value="bandlimited_noise">bandlimited_noise（带限噪声·须带宽）</option>
      <option value="partial_band">partial_band（部分频带·须带宽）</option>
      <option value="pulse">pulse（脉冲）</option>
      <option value="composite">composite（合成·须 components，请用 YAML 模式）</option>
    </select>
  </label>
  <label>采样率 fs（Hz，必填 &gt;0）
    <input type="text" id="editor-f-fs" value="1000000">
  </label>
  <label>频偏 freq_hz（Hz，可选，基带频偏可负）
    <input type="text" id="editor-f-freq" placeholder="如 2400000000">
  </label>
  <label>带宽 bandwidth_hz（Hz，可选 ≤56e6；带限类样式必填）
    <input type="text" id="editor-f-bw" placeholder="带限类样式必填">
  </label>
  <label>发射功率 power_dbm（dBm，红线 ≤0）
    <input type="text" id="editor-f-power" value="-10">
  </label>
  <label>时长 duration_s（秒，可选 &gt;0）
    <input type="text" id="editor-f-duration" value="1">
  </label>
  <label>占空比 duty_cycle（可选，开区间 (0,1)）
    <input type="text" id="editor-f-duty" placeholder="如 0.5">
  </label>
  <label>重复次数 repeats（可选，正整数）
    <input type="text" id="editor-f-repeats" placeholder="如 3">
  </label>
  <label>后端 backend
    <select id="editor-f-backend">
      <option value="sim">sim（仿真）</option>
      <option value="auto">auto（自动）</option>
      <option value="b210">b210（USRP B210）</option>
      <option value="replay">replay（回放）</option>
    </select>
  </label>
  <label>频段 bands（法定白名单单选）
    <select id="editor-f-band">
      <option value="2400.0,2483.5">2.4G（2400–2483.5 MHz）</option>
      <option value="5725.0,5829.0">5.8G（5725–5829 MHz）</option>
    </select>
  </label>
  <p class="sce-hint">表单模式仅能表达单一频段——多频段场景请用 YAML 模式（保存时表单只保留上方所选频段）。</p>
  <label>安全声明（红线必选，缺一即 400）：
    <input type="checkbox" id="editor-f-shield"> 屏蔽盒环境确认 shielded_box
    <input type="checkbox" id="editor-f-dut"> 仅测自建链路 dut_scope=self_built
  </label>
</div>

<div id="editor-panel-yaml" hidden>
  <label>场景 YAML 全文（服务端 load_scenario 全口径校验：schema+红线）
    <textarea id="editor-yaml" spellcheck="false" placeholder="style: tone&#10;fs: 1000000&#10;power_dbm: -10&#10;bands:&#10;  - [2400.0, 2483.5]&#10;shielded_box: true&#10;dut_scope: self_built"></textarea>
  </label>
  <p class="sce-hint">提示：编辑已有场景时先在上方「目标场景」选中名字（PUT 覆写），再粘贴修改后的全文。</p>
</div>

<div class="sce-actions">
  <button type="button" id="editor-btn-form-save" class="sce-save">保存场景（表单）</button>
  <button type="button" id="editor-btn-yaml-save" class="sce-save" hidden>保存场景（YAML）</button>
  <button type="button" id="editor-btn-delete" class="sce-danger">删除目标场景</button>
</div>
<div id="editor-status" role="status"></div>
<ul id="editor-errors" aria-label="校验错误清单"></ul>
<div id="editor-cards" aria-label="场景卡片（保存/删除后自动刷新）"></div>

<script>
window.__EDITOR_CARDS__ = __CARDS_JSON__;
(function () {
  'use strict';
  var section = document.getElementById('scenario-editor');
  if (!section || section.dataset.booted) { return; }
  section.dataset.booted = '1';
  function $(id) { return document.getElementById(id); }
  var targetSel = $('editor-target');
  var nameInput = $('editor-name');
  var statusBox = $('editor-status');
  var errorList = $('editor-errors');
  var cardsBox = $('editor-cards');

  // ---- 消息与错误清单（逐条上屏，textContent 防 XSS；不吞错） ----
  function setStatus(text, ok) {
    statusBox.textContent = text;
    statusBox.className = ok ? 'ok' : 'err';
  }
  function showErrors(lines) {
    while (errorList.firstChild) { errorList.removeChild(errorList.firstChild); }
    (lines || []).forEach(function (line) {
      var li = document.createElement('li');
      li.textContent = line;
      errorList.appendChild(li);
    });
  }
  function errorLinesFromBody(body, fallback) {
    // 400 响应体 {'detail': {'field', 'error'}}——error 为多行清单，逐行成条；
    // 404 等的 detail 为纯字符串；解析不出则退回 HTTP 状态回执。
    var detail = body && body.detail;
    if (detail && typeof detail === 'object' && typeof detail.error === 'string') {
      var prefix = detail.field ? '[' + detail.field + '] ' : '';
      return detail.error.split('\n').map(function (line) {
        return prefix + line.trim();
      }).filter(function (line) { return line.length > 0; });
    }
    if (typeof detail === 'string' && detail) { return [detail]; }
    return [fallback];
  }

  // ---- 模式切换（表单 ⇄ YAML） ----
  function setMode(mode) {
    var isForm = mode === 'form';
    $('editor-panel-form').hidden = !isForm;
    $('editor-panel-yaml').hidden = isForm;
    $('editor-btn-form-save').hidden = !isForm;
    $('editor-btn-yaml-save').hidden = isForm;
    $('editor-btn-mode-form').classList.toggle('active', isForm);
    $('editor-btn-mode-yaml').classList.toggle('active', !isForm);
    if (isForm) { warnMultiBandInForm(); }
  }
  $('editor-btn-mode-form').addEventListener('click', function () { setMode('form'); });
  $('editor-btn-mode-yaml').addEventListener('click', function () { setMode('yaml'); });

  // ---- B24 N2：多频段场景的表单丢带防护 ----
  // 表单只能表达单一频段（bands 单选）：YAML 载入多带场景后若以表单模式保存，
  // 将只保留所选频段静默丢带——此处检测 YAML 文本中的频段条目数，>1 时警示
  // 并阻止表单保存（前端启发式守门，服务端 load_scenario 仍是唯一权威校验）。
  var MULTI_BAND_WARNING = '该场景含多频段，表单模式保存将只保留所选频段——请用 YAML 模式';
  function countBands(text) {
    if (!text) { return 0; }
    var m = String(text).match(/^[^\S\n]*bands[^\S\n]*:[^\S\n]*(.*)$/m);
    if (!m) { return 0; }
    if (m[1].trim()) {  // 行内流式表：bands: [[a, b], [c, d]] ——数 [..] 对
      return (m[1].match(/\[[^\[\]]*\]/g) || []).length || 1;
    }
    var rest = String(text).slice(m.index + m[0].length);
    var block = rest.split(/^[^\s#-]/m)[0];  // bands: 之下、下一非缩进行之前的条目行
    return (block.match(/^[^\S\n]*-[^\S\n]/gm) || []).length;
  }
  function warnMultiBandInForm() {
    if (countBands($('editor-yaml').value) > 1) { showErrors([MULTI_BAND_WARNING]); }
  }

  // ---- 表单 → YAML 文本（数值域交服务端 load_scenario 把关，前端不影子校验） ----
  function fieldNum(id) {
    var raw = $(id).value.trim();
    return raw === '' ? null : raw;
  }
  function formToYaml() {
    var lines = [];
    var desc = $('editor-f-desc').value.trim();
    if (desc) { lines.push('# desc: ' + desc); }
    lines.push('style: ' + $('editor-f-style').value);
    lines.push('fs: ' + fieldNum('editor-f-fs'));
    var freq = fieldNum('editor-f-freq');
    if (freq !== null) { lines.push('freq_hz: ' + freq); }
    var bw = fieldNum('editor-f-bw');
    if (bw !== null) { lines.push('bandwidth_hz: ' + bw); }
    lines.push('power_dbm: ' + fieldNum('editor-f-power'));
    var dur = fieldNum('editor-f-duration');
    if (dur !== null) { lines.push('duration_s: ' + dur); }
    var duty = fieldNum('editor-f-duty');
    if (duty !== null) { lines.push('duty_cycle: ' + duty); }
    var reps = fieldNum('editor-f-repeats');
    if (reps !== null) { lines.push('repeats: ' + reps); }
    lines.push('backend: ' + $('editor-f-backend').value);
    lines.push('bands:');
    var band = $('editor-f-band').value.split(',');
    lines.push('  - [' + band[0].trim() + ', ' + band[1].trim() + ']');
    if ($('editor-f-shield').checked) { lines.push('shielded_box: true'); }
    if ($('editor-f-dut').checked) { lines.push('dut_scope: self_built'); }
    return lines.join('\n') + '\n';
  }

  // ---- 目标下拉与卡片视图（新建/编辑/删除共用，成功后刷新） ----
  function fillTargets(cards) {
    var keep = targetSel.value;
    while (targetSel.options.length > 1) { targetSel.remove(1); }
    cards.forEach(function (card) {
      if (!card || typeof card.name !== 'string' || !card.name) { return; }
      var opt = document.createElement('option');
      opt.value = card.name;
      opt.textContent = card.name;
      targetSel.appendChild(opt);
    });
    if (keep) {
      var rest = Array.prototype.some.call(targetSel.options, function (o) { return o.value === keep; });
      targetSel.value = rest ? keep : '';
    }
  }
  function renderCards(cards) {
    while (cardsBox.firstChild) { cardsBox.removeChild(cardsBox.firstChild); }
    if (!cards.length) {
      var empty = document.createElement('p');
      empty.className = 'sce-hint';
      empty.textContent = '（暂无场景——保存第一个场景后此处自动刷新）';
      cardsBox.appendChild(empty);
      return;
    }
    cards.forEach(function (card) {
      var box = document.createElement('article');
      box.className = 'sce-card' + (card.error ? ' sce-broken' : '');
      var title = document.createElement('h4');
      title.textContent = card.name;
      box.appendChild(title);
      if (card.error) {
        var err = document.createElement('p');
        err.textContent = '损坏场景：' + card.error;
        box.appendChild(err);
      } else {
        var desc = document.createElement('p');
        desc.textContent = card.desc || '（无描述）';
        var meta = document.createElement('p');
        meta.className = 'sce-hint';
        meta.textContent = '样式 ' + (card.style_tags || []).join('/') +
          ' · 风险 ' + card.risk + ' · 后端 ' + card.backend_hint;
        box.appendChild(desc);
        box.appendChild(meta);
      }
      cardsBox.appendChild(box);
    });
  }
  function applyCards(cards) { fillTargets(cards); renderCards(cards); }
  function refreshCards() {
    // 成功后的卡片刷新：index 页卡片为装配期静态内嵌，实时数据走 GET /api/scenarios。
    return fetch('/api/scenarios').then(function (resp) {
      if (!resp.ok) { throw new Error('GET /api/scenarios → ' + resp.status); }
      return resp.json();
    }).then(function (body) {
      applyCards(body.cards || []);
    }).catch(function (err) {
      showErrors(['场景卡片刷新失败: ' + err.message]);
    });
  }

  // ---- 三操作接线既有 CRUD：POST /api/scenarios、PUT /{name}、DELETE /{name} ----
  function save(content, target) {
    var req;
    if (target) {  // 编辑：PUT 覆写（upsert 语义）
      req = fetch('/api/scenarios/' + encodeURIComponent(target), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: content })
      });
    } else {  // 新建：POST
      req = fetch('/api/scenarios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: nameInput.value.trim(), content: content })
      });
    }
    return req.then(function (resp) {
      var fallback = '保存失败: HTTP ' + resp.status;
      return resp.json().catch(function () { return null; }).then(function (body) {
        if (!resp.ok) { showErrors(errorLinesFromBody(body, fallback)); return false; }
        setStatus('已保存场景 ' + (body && body.name ? body.name : (target || nameInput.value.trim()))
          + '（HTTP ' + resp.status + '）——卡片已刷新', true);
        showErrors([]);
        return refreshCards().then(function () { return true; });
      });
    }).catch(function (err) {
      showErrors(['保存请求失败（网络/服务不可达）: ' + err.message]);
      return false;
    });
  }
  function requireNewName() {
    var name = nameInput.value.trim();
    if (!name) {
      showErrors(['[name] 新建场景须先填写「新场景名」（或从「目标场景」选择编辑对象）']);
      return null;
    }
    return name;
  }
  function saveFromForm() {
    var target = targetSel.value;
    if (!target && !requireNewName()) { return; }
    if (countBands($('editor-yaml').value) > 1) {  // B24 N2：多频段丢带防护
      showErrors([MULTI_BAND_WARNING]);
      setStatus('表单模式已阻止保存（多频段场景不可由表单表达）', false);
      return;
    }
    save(formToYaml(), target);
  }
  function saveFromYaml() {
    var target = targetSel.value;
    if (!target && !requireNewName()) { return; }
    var text = $('editor-yaml').value;
    if (!text.trim()) { showErrors(['[content] YAML 文本为空——请粘贴场景全文后再保存']); return; }
    save(text, target);
  }
  function deleteTarget() {
    var target = targetSel.value;
    if (!target) { showErrors(['[name] 删除须先在「目标场景」下拉选中要删除的场景']); return; }
    fetch('/api/scenarios/' + encodeURIComponent(target), { method: 'DELETE' })
      .then(function (resp) {
        return resp.json().catch(function () { return null; }).then(function (body) {
          if (!resp.ok) {
            showErrors(errorLinesFromBody(body, '删除失败: HTTP ' + resp.status));
            return;
          }
          setStatus('已删除场景 ' + target + '（HTTP ' + resp.status + '）——卡片已刷新', true);
          showErrors([]);
          refreshCards();
        });
      })
      .catch(function (err) {
        showErrors(['删除请求失败（网络/服务不可达）: ' + err.message]);
      });
  }
  $('editor-btn-form-save').addEventListener('click', saveFromForm);
  $('editor-btn-yaml-save').addEventListener('click', saveFromYaml);
  $('editor-btn-delete').addEventListener('click', deleteTarget);

  // 初值：装配期卡片数据（cards 参数）先行上屏，再经 API 对齐一次。
  applyCards(window.__EDITOR_CARDS__ || []);
})();
</script>
</section>"""


def edit_scenario_ui(cards: list[dict]) -> str:
    """场景编辑器页面区块：表单/YAML 双模式+新建/编辑/删除接线既有场景 CRUD+校验错误逐条回显（详见 fn_docs/responsibility.md 功能块）。

    Args:
        cards: 当前场景卡片数据（build_scenario_cards 产物形状——正常卡
            {'name','desc','style_tags','risk','backend_hint'}、损坏卡
            {'name','error'}），用于目标下拉（编辑/删除对象选择）与卡片视图
            的装配期初值；成功操作后区块自行 GET /api/scenarios 刷新。

    Returns:
        纯静态区块资产 str（<section id="scenario-editor"> + 内联 JS，原生
        fetch 自足，不依赖页面 Vue 实例）——由 serve_console 在缺省装配时
        注入 index 运行页（R57 wired 调用点）。

    Raises:
        ValueError: cards 非 list（空 list 合法——空态区块照常产出）。
    """
    if not isinstance(cards, list):
        raise ValueError(
            f"cards 必须为 list[dict]（build_scenario_cards 产物），实际收到 "
            f"{type(cards).__name__}: {cards!r}"
        )
    # '</' 转义：卡片名等用户数据内嵌 <script> 时防字面 </ 提前闭合标签。
    cards_json = json.dumps(cards, ensure_ascii=False).replace("</", "<\\/")
    # 下拉 option 的服务端初值：卡片名经 html.escape（文件名含引号/尖括号也不破属性）。
    options = "".join(
        f'<option value="{escaped}">{escaped}</option>'
        for card in cards
        if isinstance(card, dict)
        and isinstance(card.get("name"), str)
        and card["name"]
        for escaped in (html.escape(card["name"], quote=True),)
    )
    return (
        _BLOCK_TEMPLATE.replace("__CARDS_JSON__", cards_json)
        .replace("__TARGET_OPTIONS__", options)
    )
