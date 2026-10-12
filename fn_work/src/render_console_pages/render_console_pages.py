"""Vue3(CDN)+Canvas 页面资产（无 Node 构建）——重写规约与签名意图详见 fn_docs/responsibility.md。

产出口径（R48：单文件 HTML，无 Node 构建）：
- build_scenario_cards 取卡片数据→内嵌 JSON（window.__CONSOLE_CARDS__，'</' 转义
  防提前闭 script）；页面骨架以模板字符串生成——场景卡网格/滑杆调参/后端链路时钟
  状态区/报告中心/清单完成度入口/WS 实时图区（Canvas）+断线横幅自动重连；
- Vue3 走 CDN（缺省 unpkg 的 vue.global.prod.js，config['cdn_base'] 可换源）；
- scenario_dir 空/缺失→空态页面（cards=0，不报错）；写盘可选 config['out_dir']
  （None→只返回 str 不落盘，'written' 列出落盘路径）；assets 恒为 []（无本地构建物）。
"""
from __future__ import annotations

import json
import os

from .build_scenario_cards import build_scenario_cards

__all__ = ["DEFAULT_CDN_BASE", "render_console_pages"]

#: Vue3 生产构建 CDN 源（config['cdn_base'] 可覆盖，如内网镜像）。
DEFAULT_CDN_BASE = "https://unpkg.com"

#: CDN 上的 Vue3 全局构建路径（vue.global.prod.js，无 Node 构建约定）。
_VUE_CDN_PATH = "/vue@3/dist/vue.global.prod.js"

#: 页面标题缺省值（config['title'] 可覆盖）。
_DEFAULT_TITLE = "rf-console 操控台"

# 单文件页面骨架：__TITLE__/__CDN_URL__/__CARDS_JSON__/__EMPTY_STATE__ 四个
# 令牌以 str.replace 注入（不用 format——Vue 模板花括号与 format 语法冲突）。
_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
body { font-family: system-ui, sans-serif; margin: 0 auto; max-width: 1080px; color: #1c2333; }
header { display: flex; align-items: baseline; gap: 12px; border-bottom: 2px solid #2c5aa0; }
h1 { font-size: 20px; }
h2 { font-size: 15px; color: #2c5aa0; }
section { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; }
.card { border: 1px solid #c9d4e4; border-radius: 6px; padding: 10px; }
.card.error { border-color: #c0392b; background: #fdf0ee; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; padding: 0; list-style: none; }
.tags li { background: #eef2f8; border-radius: 4px; padding: 1px 6px; font-size: 12px; }
.banner { background: #b3541e; color: #fff; padding: 6px 12px; border-radius: 6px; }
.empty { color: #6b7486; padding: 18px; text-align: center; }
label { display: block; margin: 6px 0; }
canvas { width: 100%; border: 1px solid #d7dee9; border-radius: 6px; background: #fbfcfe; }
</style>
</head>
<body>
<div id="app">
  <div id="ws-banner" class="banner" v-show="disconnected">实时连接已断开——自动重连中…</div>
  <header><h1>__TITLE__</h1><span id="conn-state">{{ connState }}</span></header>

  <section id="scenario-grid" aria-label="场景卡网格">
    <h2>场景卡</h2>
    <div class="grid">
      <article class="card" v-for="card in cards" :key="card.name" :class="{ error: !!card.error }">
        <h3>{{ card.name }}</h3>
        <p v-if="card.error" class="err">损坏场景：{{ card.error }}</p>
        <template v-else>
          <p>{{ card.desc || '（无描述）' }}</p>
          <ul class="tags"><li v-for="tag in card.style_tags" :key="tag">{{ tag }}</li></ul>
          <p>风险 {{ card.risk }} · 推荐后端 {{ card.backend_hint }}</p>
          <button :disabled="busy" @click="startRun(card)">启动运行</button>
        </template>
      </article>
    </div>
  </section>

  <section id="param-sliders" aria-label="滑杆调参">
    <h2>参数滑杆</h2>
    <label>发射功率 <input type="range" min="-30" max="0" step="1" v-model.number="powerDbm"> {{ powerDbm }} dBm</label>
    <label>链路衰减 <input type="range" min="0" max="60" step="1" v-model.number="attenDb"> {{ attenDb }} dB</label>
    <button :disabled="busy" @click="applyParams">应用参数</button>
  </section>

  <section id="status-panel" aria-label="状态区">
    <h2>状态</h2>
    <ul>
      <li>后端：{{ status.backend }}</li>
      <li>链路：{{ status.link }}</li>
      <li>时钟：{{ status.clock }}</li>
    </ul>
  </section>

  <section id="ws-charts" aria-label="WS 实时图区">
    <h2>实时 KPI 曲线</h2>
    <canvas id="kpi-canvas" width="640" height="240"></canvas>
  </section>

  <section id="report-center" aria-label="报告中心">
    <h2>报告中心</h2>
    <ul><li v-for="name in runs" :key="name">{{ name }}</li></ul>
    <button @click="loadRuns">刷新报告列表</button>
  </section>

  <nav id="ledger-entry-nav">清单完成度入口：<a id="ledger-entry" href="/api/ledger">清单完成度</a></nav>
  __EMPTY_STATE__
</div>
<script src="__CDN_URL__"></script>
<script>
window.__CONSOLE_CARDS__ = __CARDS_JSON__;
const app = Vue.createApp({
  data() {
    return {
      cards: window.__CONSOLE_CARDS__,
      powerDbm: -10, attenDb: 0, busy: false,
      status: { backend: '未知', link: '未知', clock: '未知' },
      runs: [], kpiSeries: [], disconnected: false, connState: '未连接',
    };
  },
  methods: {
    async startRun(card) {
      this.busy = true;
      try {
        const resp = await fetch('/api/run', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ scenario: { name: card.name, power_dbm: this.powerDbm, atten_db: this.attenDb } }),
        });
        if (!resp.ok) throw new Error('run ' + resp.status);
        this.connState = '已提交运行';
      } finally { this.busy = false; }
    },
    async applyParams() { this.connState = '参数已更新'; },
    async loadRuns() {
      const resp = await fetch('/api/runs');
      if (resp.ok) { const body = await resp.json(); this.runs = body.runs || []; }
    },
    onKpiFrame(frame) {
      this.kpiSeries.push(frame);
      if (this.kpiSeries.length > 600) this.kpiSeries.shift();
      this.drawKpi();
    },
    drawKpi() {
      const canvas = document.getElementById('kpi-canvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#2c5aa0';
      ctx.beginPath();
      const series = this.kpiSeries.slice(-canvas.width);
      series.forEach((f, i) => {
        const y = canvas.height / 2 - (Number(f.value) || 0) * canvas.height / 4;
        if (i === 0) ctx.moveTo(i, y); else ctx.lineTo(i, y);
      });
      ctx.stroke();
    },
    connectWS() {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const sock = new WebSocket(proto + '//' + location.host + '/ws');
      sock.onopen = () => { this.disconnected = false; this.connState = '实时已连接'; };
      sock.onmessage = (ev) => { this.onKpiFrame(JSON.parse(ev.data)); };
      sock.onclose = () => {
        this.disconnected = true; this.connState = '重连中';
        setTimeout(() => this.connectWS(), 2000);  // 断线横幅+自动重连
      };
    },
  },
  mounted() { this.connectWS(); this.loadRuns(); },
});
app.mount('#app');
</script>
</body>
</html>
"""

#: 空态提示块（仅 cards 为 0 时注入；非空页不出现该 id）。
_EMPTY_STATE_HTML = (
    '<div id="empty-state" class="empty">暂无场景——请将 *.yaml 场景文件放入场景目录后重新渲染</div>'
)


def _list_scenario_files(scenario_dir: str) -> list:
    """目录内 *.yaml/*.yml 排序列表；目录空/缺失/不可读→[]（空态，不报错）。"""
    if not scenario_dir or not os.path.isdir(scenario_dir):
        return []
    try:
        names = os.listdir(scenario_dir)
    except OSError:
        return []
    return sorted(
        os.path.join(scenario_dir, n) for n in names if n.endswith((".yaml", ".yml"))
    )


def _validate_config(config: dict, scenario_dir: str) -> "tuple[str, object, str]":
    """形状校验：config 非 dict/scenario_dir 非 str/键类型不符→ValueError。"""
    if not isinstance(config, dict):
        raise ValueError(
            f"config 必须为 dict（cdn_base/out_dir/title 等），实际 "
            f"{type(config).__name__}: {config!r}"
        )
    if not isinstance(scenario_dir, str):
        raise ValueError(
            f"scenario_dir 必须为 str 路径，实际 {type(scenario_dir).__name__}: "
            f"{scenario_dir!r}"
        )
    cdn_base = config.get("cdn_base", DEFAULT_CDN_BASE)
    if not isinstance(cdn_base, str) or not cdn_base:
        raise ValueError(f"config['cdn_base'] 必须为非空 str，实际 {cdn_base!r}")
    out_dir = config.get("out_dir")
    if out_dir is not None and (not isinstance(out_dir, str) or not out_dir):
        raise ValueError(
            f"config['out_dir'] 须为非空 str|None（None=只返回不落盘），实际 {out_dir!r}"
        )
    title = config.get("title", _DEFAULT_TITLE)
    if not isinstance(title, str) or not title:
        raise ValueError(f"config['title'] 必须为非空 str，实际 {title!r}")
    return cdn_base, out_dir, title


def render_console_pages(scenario_dir: str, config: dict) -> dict:
    """场景目录→单文件 HTML 页面资产（Vue3 CDN+Canvas，无 Node 构建）。

    Args:
        scenario_dir: 场景目录（内 *.yaml/*.yml 经 build_scenario_cards 转卡片数据
            内嵌 JSON；空/缺失目录→空态页面，cards=0，不报错）。
        config: 可选 'cdn_base'（Vue CDN 源，缺省 unpkg）、'out_dir'（非 None 则
            落盘 index.html）、'title'（页面标题）。

    Returns:
        {'pages': {'index.html': 完整 HTML str}, 'cards': 卡片数, 'assets': []}；
        落盘时附 'written': [index.html 绝对/相对落盘路径列表]。

    Raises:
        ValueError: config 非 dict / scenario_dir 非 str / 键类型不符。
    """
    cdn_base, out_dir, title = _validate_config(config, scenario_dir)

    cards = build_scenario_cards(_list_scenario_files(scenario_dir))
    # '</' 转义：内嵌 JSON 中的字面 </ 会让浏览器提前闭合 <script> 标签。
    cards_json = json.dumps(cards, ensure_ascii=False).replace("</", "<\\/")

    html = (
        _PAGE_TEMPLATE.replace("__TITLE__", title)
        .replace("__CDN_URL__", cdn_base.rstrip("/") + _VUE_CDN_PATH)
        .replace("__CARDS_JSON__", cards_json)
        .replace("__EMPTY_STATE__", _EMPTY_STATE_HTML if not cards else "")
    )

    result = {"pages": {"index.html": html}, "cards": len(cards), "assets": []}
    if out_dir is not None:
        os.makedirs(out_dir, exist_ok=True)
        written = []
        for name, content in result["pages"].items():
            path = os.path.join(out_dir, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            written.append(path)
        result["written"] = written
    return result
