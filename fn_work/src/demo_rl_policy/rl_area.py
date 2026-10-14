"""仪表页 RL 策略演示页区：instruments 页注入的纯静态资产（HTML+内联 JS）——
重写规约与签名意图详见 fn_docs/responsibility.md（R73 RL 策略演示页区）。

产出口径（R73，纯静态资产，原生 fetch 自足，不依赖页面 Vue 实例——沿用
R70/R71/R72 的 serve_console 缺省装配注入模式）：

- 轮数输入（缺省 6）+「冒烟一轮」按钮 → POST ``/api/demo/rl``（body
  ``{'rounds': int}`` 可省，同步演示——sim 小闭环秒级回）；
- 末轮动作序列+逐轮回报曲线（reward_history）上屏；converged/fallback 徽标
  ——不收敛回退固定策略时 fallback_note 回退原因+fallback_plan 动作表如实
  上屏（不粉饰）；
- 错误（rounds 域错等 400）→错误信息原样上屏（不静默）；
- 零外链：仅同源相对路径 fetch（/api/demo/rl）。
"""

#: 回退标注行 class（页区协作锚点；模板内字面引用与此常量同值）。
RL_FALLBACK_CLASS = "rl-fallback-note"


def build_rl_policy_area() -> str:
    """仪表页 RL 策略演示页区（纯静态资产 str，serve_console 缺省装配注入）。"""
    return _BLOCK_TEMPLATE


#: 区块模板（纯静态，无令牌注入——演示数据运行期 fetch；r 前缀保 JS 原样）。
_BLOCK_TEMPLATE = r"""<section id="rl-policy-area" aria-label="RL 策略演示（sim 小闭环冒烟）">
<style>
#rl-policy-area { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
#rl-policy-area h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#rl-policy-area .rla-status { color: #6b7486; font-size: 13px; margin: 6px 0; word-break: break-all; }
#rl-policy-area .rla-error { color: #c0392b; font-size: 13px; margin: 6px 0; word-break: break-all; }
#rl-policy-area p.rl-fallback-note { color: #b3541e; font-size: 13px; margin: 6px 0; word-break: break-all; }
#rl-policy-area input { width: 5em; padding: 3px 8px; border: 1px solid #c9d4e4; border-radius: 4px; }
#rl-policy-area button { margin: 6px 0 6px 8px; padding: 3px 12px; border: 1px solid #2c5aa0; border-radius: 4px; background: #f2f6fb; color: #2c5aa0; cursor: pointer; }
#rl-policy-area table.rla-table { border-collapse: collapse; font-size: 13px; margin: 6px 0; }
#rl-policy-area table.rla-table th, #rl-policy-area table.rla-table td { border: 1px solid #d7dee9; padding: 3px 8px; text-align: left; }
#rl-policy-area pre.rla-seq { margin: 4px 0; padding: 6px; background: #f6f8fb; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
#rl-policy-area .rla-badge-ok { color: #1e7a3c; font-weight: bold; }
#rl-policy-area .rla-badge-fb { color: #b3541e; font-weight: bold; }
</style>
<h2>RL 干扰策略器演示（run_rl_policy sim 小闭环冒烟）</h2>
<p class="rla-status" id="rla-status">短轮次固定参数冒烟：动作序列+逐轮回报上屏；训练不收敛自动回退固定策略并如实标注。</p>
<div>
  <label for="rla-rounds-input">轮数</label>
  <input id="rla-rounds-input" type="number" min="1" max="64" placeholder="6" />
  <button type="button" id="rla-run-btn">冒烟一轮</button>
</div>
<div id="rla-result"></div>
<script>
(function () {
  var mount = document.getElementById('rla-result');
  var statusLine = document.getElementById('rla-status');
  var runBtn = document.getElementById('rla-run-btn');
  var roundsInput = document.getElementById('rla-rounds-input');
  if (!mount || !runBtn || !roundsInput) { return; }
  var say = function (text, isError) {
    if (!statusLine) { return; }
    statusLine.textContent = text;
    statusLine.className = isError ? 'rla-error' : 'rla-status';
  };
  var makeTable = function (headers, rows) {
    var table = document.createElement('table');
    table.className = 'rla-table';
    var thead = document.createElement('tr');
    headers.forEach(function (h) {
      var th = document.createElement('th'); th.textContent = h; thead.appendChild(th);
    });
    table.appendChild(thead);
    rows.forEach(function (row) {
      var tr = document.createElement('tr');
      row.forEach(function (cell) {
        var td = document.createElement('td'); td.textContent = String(cell); tr.appendChild(td);
      });
      table.appendChild(tr);
    });
    return table;
  };
  var render = function (data) {
    mount.textContent = '';
    var badge = document.createElement('p');
    badge.className = data.fallback_used ? 'rla-badge-fb' : 'rla-badge-ok';
    badge.textContent = data.fallback_used
        ? '未收敛 → 已回退固定策略（policy=' + data.policy + '）'
        : '已收敛（policy=' + data.policy + '，末半程平均回报改善）';
    mount.appendChild(badge);
    if (data.fallback_note) {
      var fb = document.createElement('p');
      fb.className = 'rl-fallback-note';
      fb.textContent = data.fallback_note;
      mount.appendChild(fb);
    }
    mount.appendChild(makeTable(
      ['轮数 rounds', '动作空间', '单轮步数', '状态数 n_states', '末半程平均回报'],
      [[data.rounds, data.action_space, data.max_steps, data.n_states, data.final_reward_mean]]
    ));
    var h3 = document.createElement('h3'); h3.textContent = '逐轮回报曲线（reward_history）'; mount.appendChild(h3);
    var pre = document.createElement('pre'); pre.className = 'rla-seq';
    pre.textContent = (data.reward_history || []).map(function (r, i) {
      return '第' + (i + 1) + '轮: ' + r.toFixed(4);
    }).join('\n') || '（无）';
    mount.appendChild(pre);
    h3 = document.createElement('h3'); h3.textContent = '末轮动作序列（JSR 档位索引 0-5）'; mount.appendChild(h3);
    pre = document.createElement('pre'); pre.className = 'rla-seq';
    pre.textContent = (data.action_sequence || []).join(' → ') || '（无）';
    mount.appendChild(pre);
    if (data.fallback_used && (data.fallback_plan || []).length) {
      h3 = document.createElement('h3'); h3.textContent = '固定策略回退动作表（fallback_plan）'; mount.appendChild(h3);
      mount.appendChild(makeTable(['step', 'target_db', 'action', 'style'],
        (data.fallback_plan || []).map(function (act) {
          return [act.step, act.target_db, act.action, act.style];
        })));
    }
    var note = document.createElement('p'); note.className = 'rla-status';
    note.textContent = data.note || ''; mount.appendChild(note);
  };
  var run = function () {
    var body = {};
    var raw = (roundsInput.value || '').trim();
    if (raw) {
      var n = Number(raw);
      if (!Number.isInteger(n) || n < 1) { say('轮数必须为正整数（1-64）', true); return; }
      body.rounds = n;
    }
    say('sim 小闭环冒烟中……（POST /api/demo/rl）');
    fetch('/api/demo/rl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (resp) {
      if (!resp.ok) { return resp.json().then(function (err) {
        throw new Error('HTTP ' + resp.status + ' ' + JSON.stringify(err));
      }); }
      return resp.json();
    }).then(function (data) {
      render(data);
      say('冒烟完成（' + data.rounds + ' 轮，converged=' + data.converged + '）——sim 小闭环，不开放辐射。');
    }).catch(function (err) { say('演示失败: ' + err.message, true); });
  };
  runBtn.addEventListener('click', run);
})();
</script>
</section>
"""
