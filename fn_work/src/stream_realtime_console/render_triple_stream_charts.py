"""三路 Canvas 图区：KPI 曲线/频谱瀑布/事件时间线三图布局与 /ws 帧消费渲染资产（断线横幅+自动重连续画）——重写规约与签名意图详见 fn_docs/responsibility.md。

产出口径（R58 render_triple_stream_charts：纯静态区块资产 HTML+内联 JS，
原生 JS+Canvas 2D，零外部依赖零 Vue 依赖，区块 id=triple-stream-charts）：
- 三 canvas：chart-kpi（KPI 折线，滚动窗口最近 N 点）、chart-spectrum（频谱
  瀑布，每帧一行、最新行在顶旧行向下滚动、功率 dB→色带映射）、chart-events
  （事件时间线，竖线+标签追加；急停帧红标）；
- /ws 连接沿用 index 运行页 connectWS 同源构造（location.protocol https→
  wss 否则 ws，拼 '//' + location.host + '/ws'）；断线→区块顶"已断线，重连中"
  横幅（hidden 出现/消失）+2s 自动重连，缓冲留在内存、重连成功后续画；
- 未知帧类型（含缺 type/坏 JSON）→区块角 skipped 计数，不中断流；
- window.__TSCHARTS_STATS__={kpi,spectrum,events,skipped} 每类帧消费计数
  （R58 接线申报的最小 window 计数器——e2e 断言钩子，不影响渲染行为）；
- 帧协议（push_realtime_kpi 帧为通用 dict：仅定义 emergency_stop 控制帧/
  emergency_stopped 通知帧并给全部广播帧盖 sent_ms 发送戳，无三路分类字段
  ——三路 type 分类为本区块约定，登记在 JS 顶部注释，stream_realtime_console
  接线时按此协议推帧）：
    KPI 帧     {'type': 'kpi',      'ts_ms': number, 'metrics': {名: number, ...}}
    频谱帧     {'type': 'spectrum', 'ts_ms': number, 'powers_db': [number, ...]}
    事件帧     {'type': 'event',    'ts_ms': number, 'label': str}
    急停通知帧 {'type': 'emergency_stopped', ...}（push_realtime_kpi 既有控制帧族）
    其余 type → 跳过计数；ts_ms 缺省回退 sent_ms，再缺省回退 Date.now()。
"""
import html
import json

__all__ = ["CHARTS_SECTION_ID", "render_triple_stream_charts"]

#: 区块根 id（serve_console 装配期注入 index 运行页，stream_realtime_console 挂图区）。
CHARTS_SECTION_ID = "triple-stream-charts"

#: 缺省配置（config=None 时逐项采用；键集即合法键集——未知键属非法形状）。
_DEFAULT_CONFIG = {
    "kpi_title": "KPI 曲线（实时）",
    "spectrum_title": "频谱瀑布（实时）",
    "events_title": "事件时间线（实时）",
    "kpi_buffer": 600,  # KPI 折线滚动窗口：最近 N 点
    "spectrum_rows": 128,  # 瀑布保留行数（超出丢最旧行）
    "events_buffer": 40,  # 时间线保留标记数
    "kpi_height": 220,  # 三画布高度（px，固定宽 920）
    "spectrum_height": 260,
    "events_height": 140,
}

_TITLE_KEYS = ("kpi_title", "spectrum_title", "events_title")
_BUFFER_KEYS = ("kpi_buffer", "spectrum_rows", "events_buffer")
_HEIGHT_KEYS = ("kpi_height", "spectrum_height", "events_height")

# 区块模板（str.replace 令牌注入——不用 format：JS 花括号与 format 语法冲突；
# r 前缀：JS 字符串里的 '\n' 须原样落在产出资产中，不得被 Python 转义）。
_BLOCK_TEMPLATE = r"""<section id="triple-stream-charts" aria-label="实时三路曲线">
<style>
#triple-stream-charts { margin: 16px 0; padding: 12px; border: 1px solid #d7dee9; border-radius: 8px; position: relative; }
#triple-stream-charts h2 { font-size: 15px; color: #2c5aa0; margin-top: 0; }
#triple-stream-charts h3 { font-size: 13px; color: #2c5aa0; margin: 10px 0 4px; }
#triple-stream-charts canvas { display: block; width: 100%; max-width: 920px; background: #f7fafd; border: 1px solid #c9d4e4; border-radius: 4px; }
#tscharts-banner { box-sizing: border-box; width: 100%; margin: 0 0 8px; padding: 6px 10px; border: 1px solid #e4b6b0; background: #fdf0ee; color: #a93226; font-size: 13px; font-weight: bold; border-radius: 4px; text-align: center; }
#tscharts-banner[hidden] { display: none; }
#tscharts-skipped { position: absolute; top: 10px; right: 12px; font-size: 12px; color: #6b7486; }
</style>
<h2>实时三路曲线（KPI / 频谱瀑布 / 事件时间线）</h2>
<div id="tscharts-banner" role="alert" hidden>已断线，重连中</div>
<span id="tscharts-skipped">未跳过未知帧</span>
<h3>__KPI_TITLE__</h3>
<canvas id="chart-kpi" width="920" height="__KPI_HEIGHT__" aria-label="KPI 曲线"></canvas>
<h3>__SPECTRUM_TITLE__</h3>
<canvas id="chart-spectrum" width="920" height="__SPECTRUM_HEIGHT__" aria-label="频谱瀑布"></canvas>
<h3>__EVENTS_TITLE__</h3>
<canvas id="chart-events" width="920" height="__EVENTS_HEIGHT__" aria-label="事件时间线"></canvas>

<script>
// 帧协议：{（经 push_realtime_kpi→/ws hub 广播的帧均带 sent_ms 毫秒发送戳）
//   KPI 帧     {'type':'kpi',      'ts_ms':number, 'metrics':{'<指标名>':number,...}}  → chart-kpi 折线（滚动窗口最近 N 点）
//   频谱帧     {'type':'spectrum', 'ts_ms':number, 'powers_db':[number,...]}           → chart-spectrum 瀑布（每帧一行，最新在顶向下滚动，功率→色带）
//   事件帧     {'type':'event',    'ts_ms':number, 'label':str}                        → chart-events 时间线（竖线+标签追加）
//   急停通知帧 {'type':'emergency_stopped',...}（push_realtime_kpi 既有控制帧族）      → 时间线急停红标
//   其余 type（含缺 type/坏 JSON）→ 跳过计数 skipped+1（区块角 #tscharts-skipped）；
//   ts_ms 缺省回退 sent_ms，再缺省回退 Date.now()。 }
window.__TSCHARTS_CONFIG__ = __CONFIG_JSON__;
(function () {
  'use strict';
  var section = document.getElementById('triple-stream-charts');
  if (!section || section.dataset.booted) { return; }
  section.dataset.booted = '1';
  var CFG = window.__TSCHARTS_CONFIG__ || { kpi_buffer: 600, spectrum_rows: 128, events_buffer: 40 };
  window.__TSCHARTS_CONFIG__ = null;  // 一次性配置：消费后置空防篡改（重复注入走缺省兜底）
  var STATS = window.__TSCHARTS_STATS__ = { kpi: 0, spectrum: 0, events: 0, skipped: 0 };  // 每类帧计数（e2e 断言钩子）
  var banner = document.getElementById('tscharts-banner');
  var skippedBox = document.getElementById('tscharts-skipped');
  var kpiCanvas = document.getElementById('chart-kpi');
  var specCanvas = document.getElementById('chart-spectrum');
  var evCanvas = document.getElementById('chart-events');

  var kpiBuf = [];   // KPI 滚动窗口（最近 kpi_buffer 点）
  var rows = [];     // 瀑布行（最近 spectrum_rows 行，rows[0] 最新）
  var events = [];   // 时间线标记（最近 events_buffer 个）
  var skipped = 0;
  var specMin = null;  // 瀑布全局功率域（颜色映射跨行稳定，不逐行重标）
  var specMax = null;
  var PALETTE = ['#2c5aa0', '#c0392b', '#1e7a35', '#8e5aa0', '#b8860b', '#0f7f8b'];

  function pushLimited(arr, item, limit) {
    arr.push(item);
    while (arr.length > limit) { arr.shift(); }
  }

  function idleText(canvas, text) {
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#6b7486';
    ctx.font = '12px sans-serif';
    ctx.fillText(text, 10, Math.max(14, canvas.height / 2));
  }

  function fmtNum(v) {
    return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
  }

  // ---- 图一：KPI 折线（滚动窗口最近 N 点，多指标多色线，y 自适应） ----
  function drawKpi() {
    var ctx = kpiCanvas.getContext('2d');
    var W = kpiCanvas.width, H = kpiCanvas.height;
    ctx.clearRect(0, 0, W, H);
    if (!kpiBuf.length) { idleText(kpiCanvas, '等待 KPI 帧…'); return; }
    var names = [];
    kpiBuf.forEach(function (p) {
      Object.keys(p.metrics).forEach(function (k) {
        if (names.indexOf(k) < 0) { names.push(k); }
      });
    });
    var lo = Infinity, hi = -Infinity;
    kpiBuf.forEach(function (p) {
      names.forEach(function (n) {
        var v = Number(p.metrics[n]);
        if (isFinite(v)) { if (v < lo) { lo = v; } if (v > hi) { hi = v; } }
      });
    });
    if (!isFinite(lo) || !isFinite(hi)) { idleText(kpiCanvas, 'KPI 帧无有效数值…'); return; }
    if (hi === lo) { hi = lo + 1; }
    var padL = 8, padR = 8, padT = 20, padB = 16;
    var plotW = W - padL - padR, plotH = H - padT - padB;
    ctx.strokeStyle = '#dfe6f0';
    ctx.fillStyle = '#6b7486';
    ctx.font = '10px sans-serif';
    [0, 0.25, 0.5, 0.75, 1].forEach(function (f) {
      var y = Math.round(padT + plotH * f) + 0.5;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
      ctx.fillText(fmtNum(hi - (hi - lo) * f), padL + 2, y - 2);
    });
    names.forEach(function (name, idx) {
      ctx.strokeStyle = PALETTE[idx % PALETTE.length];
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      var drawn = false;
      kpiBuf.forEach(function (p, i) {
        var v = Number(p.metrics[name]);
        if (!isFinite(v)) { return; }
        var x = padL + (kpiBuf.length === 1 ? 0 : (i / (kpiBuf.length - 1)) * plotW);
        var y = padT + plotH - ((v - lo) / (hi - lo)) * plotH;
        if (!drawn) { ctx.moveTo(x, y); drawn = true; } else { ctx.lineTo(x, y); }
      });
      ctx.stroke();
    });
    ctx.font = '11px sans-serif';
    var lx = padL;
    names.forEach(function (name, idx) {
      ctx.fillStyle = PALETTE[idx % PALETTE.length];
      ctx.fillText(name, lx, 12);
      lx += ctx.measureText(name).width + 24;
    });
  }

  // ---- 图二：频谱瀑布（每帧一行，最新行在顶、旧行向下滚动，功率→色带映射） ----
  function powerColor(t) {
    // 归一功率 t∈[0,1] → 色带五档插值（深蓝→青→绿→黄→红，暗底亮峰）。
    var stops = [
      [0.0, 11, 28, 58], [0.25, 20, 80, 142], [0.5, 30, 158, 138],
      [0.75, 224, 195, 65], [1.0, 226, 84, 59]
    ];
    var x = Math.max(0, Math.min(1, t));
    for (var i = 1; i < stops.length; i++) {
      if (x <= stops[i][0]) {
        var a = stops[i - 1], b = stops[i];
        var f = (x - a[0]) / (b[0] - a[0] || 1);
        var rgb = [0, 1, 2].map(function (c) {
          return Math.round(a[c + 1] + (b[c + 1] - a[c + 1]) * f);
        });
        return 'rgb(' + rgb.join(',') + ')';
      }
    }
    return 'rgb(226,84,59)';
  }
  function drawSpectrum() {
    var ctx = specCanvas.getContext('2d');
    var W = specCanvas.width, H = specCanvas.height;
    ctx.clearRect(0, 0, W, H);
    if (!rows.length) { idleText(specCanvas, '等待频谱帧…'); return; }
    rows.forEach(function (row) {
      row.forEach(function (v) {
        var n = Number(v);
        if (!isFinite(n)) { return; }
        if (specMin === null || n < specMin) { specMin = n; }
        if (specMax === null || n > specMax) { specMax = n; }
      });
    });
    if (specMin === null || specMax <= specMin) { specMax = (specMin || 0) + 1; }
    var rowH = Math.max(1, Math.floor(H / CFG.spectrum_rows));
    rows.forEach(function (row, r) {
      var y = r * rowH;  // rows[0] 最新画在顶，旧行随行号增大向下滚动
      if (y >= H) { return; }
      var bins = row.length;
      if (!bins) { return; }
      for (var x = 0; x < W; x++) {
        var v = Number(row[Math.min(bins - 1, Math.floor(x * bins / W))]);
        if (!isFinite(v)) { continue; }
        ctx.fillStyle = powerColor((v - specMin) / (specMax - specMin));
        ctx.fillRect(x, y, 1, rowH);
      }
    });
    ctx.fillStyle = '#6b7486';
    ctx.font = '10px sans-serif';
    ctx.fillText('顶=最新帧 ' + fmtNum(specMax) + 'dB', 4, H - 4);
  }

  // ---- 图三：事件时间线（竖线+标签追加；急停红标；标签交错两层避让） ----
  function drawEvents() {
    var ctx = evCanvas.getContext('2d');
    var W = evCanvas.width, H = evCanvas.height;
    ctx.clearRect(0, 0, W, H);
    if (!events.length) { idleText(evCanvas, '等待事件帧…'); return; }
    var t0 = events[0].ts, t1 = events[events.length - 1].ts;
    if (!(t1 > t0)) { t1 = t0 + 1; }  // 同刻多事件防除零
    var padT = 18, padB = 12;
    var plotH = H - padT - padB;
    events.forEach(function (ev, i) {
      var x = 10 + ((ev.ts - t0) / (t1 - t0)) * (W - 20);
      var isStop = ev.label.indexOf('急停') >= 0;
      ctx.strokeStyle = isStop ? '#c0392b' : '#2c5aa0';
      ctx.lineWidth = isStop ? 2 : 1;
      ctx.beginPath();
      ctx.moveTo(x, padT - 6);
      ctx.lineTo(x, padT + plotH);
      ctx.stroke();
      ctx.fillStyle = isStop ? '#c0392b' : '#2c5aa0';
      ctx.font = '10px sans-serif';
      var tw = ctx.measureText(ev.label).width;
      var tx = Math.min(Math.max(2, x - tw / 2), W - tw - 2);
      ctx.fillText(ev.label, tx, i % 2 === 0 ? 12 : 26);
    });
    ctx.strokeStyle = '#dfe6f0';
    ctx.beginPath();
    ctx.moveTo(0, padT + plotH + 0.5);
    ctx.lineTo(W, padT + plotH + 0.5);
    ctx.stroke();
  }

  // ---- 三路分发（type 关键字）与未知帧跳过计数 ----
  function markSkipped() {
    skipped += 1;
    STATS.skipped += 1;
    skippedBox.textContent = '已跳过未知帧 ×' + skipped;
  }
  function tsOf(frame) {
    var n = Number(frame.ts_ms !== undefined ? frame.ts_ms : frame.sent_ms);
    return isFinite(n) ? n : Date.now();
  }
  function dispatchFrame(frame) {
    if (!frame || typeof frame !== 'object') { markSkipped(); return; }
    var t = frame.type;
    if (t === 'kpi' && frame.metrics && typeof frame.metrics === 'object') {
      pushLimited(kpiBuf, { ts: tsOf(frame), metrics: frame.metrics }, CFG.kpi_buffer);
      STATS.kpi += 1;
      drawKpi();
    } else if (t === 'spectrum' && Array.isArray(frame.powers_db)) {
      pushLimited(rows, frame.powers_db.map(Number), CFG.spectrum_rows);
      STATS.spectrum += 1;
      drawSpectrum();
    } else if (t === 'event') {
      pushLimited(events, { ts: tsOf(frame), label: String(frame.label || '事件') }, CFG.events_buffer);
      STATS.events += 1;
      drawEvents();
    } else if (t === 'emergency_stopped') {
      pushLimited(events, { ts: tsOf(frame), label: '急停' }, CFG.events_buffer);
      STATS.events += 1;
      drawEvents();
    } else {
      markSkipped();
    }
  }

  // ---- /ws 连接（沿用 index 运行页 connectWS 同源构造）+断线横幅+自动重连续画 ----
  function connectWS() {
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var sock = new WebSocket(proto + '//' + location.host + '/ws');
    sock.onopen = function () {
      banner.hidden = true;  // 重连成功→横幅消失，缓冲数据续画
    };
    sock.onmessage = function (ev) {
      var frame;
      try { frame = JSON.parse(ev.data); } catch (err) { markSkipped(); return; }
      dispatchFrame(frame);
    };
    sock.onclose = function () {
      banner.hidden = false;  // 断线→区块顶横幅出现
      setTimeout(connectWS, 2000);  // 自动重连（期间缓冲留内存，重连后续画）
    };
  }

  idleText(kpiCanvas, '等待 KPI 帧…');
  idleText(specCanvas, '等待频谱帧…');
  idleText(evCanvas, '等待事件帧…');
  connectWS();
})();
</script>
</section>
"""


def _validate_config(config: object) -> dict:
    """形状校验并回填缺省：config 非 dict/未知键/标题非 str/缓冲与高度非正整数
    →ValueError（非法形状显式拒，不静默吞键）。"""
    if config is None:
        return dict(_DEFAULT_CONFIG)
    if not isinstance(config, dict):
        raise ValueError(
            f"config 必须为 dict|None（标题/缓冲长度/画布高度），实际 "
            f"{type(config).__name__}: {config!r}"
        )
    merged = dict(_DEFAULT_CONFIG)
    for key, value in config.items():
        if key not in _DEFAULT_CONFIG:
            raise ValueError(
                f"config 含未知键 {key!r}（合法键：{sorted(_DEFAULT_CONFIG)}）"
            )
        merged[key] = value
    for key in _TITLE_KEYS:
        if not isinstance(merged[key], str) or not merged[key].strip():
            raise ValueError(
                f"config[{key!r}] 必须为非空 str（图标题），实际 {merged[key]!r}"
            )
    for key in _BUFFER_KEYS:
        v = merged[key]
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            raise ValueError(
                f"config[{key!r}] 必须为正整数（缓冲长度），实际 {v!r}"
            )
    for key in _HEIGHT_KEYS:
        v = merged[key]
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            raise ValueError(
                f"config[{key!r}] 必须为正整数（画布高度 px），实际 {v!r}"
            )
    return merged


def render_triple_stream_charts(config: dict | None = None) -> str:
    """三路 Canvas 图区：KPI 曲线/频谱瀑布/事件时间线三图布局与 /ws 帧消费渲染资产（详见 fn_docs/responsibility.md 功能块）。

    Args:
        config: 可选配置（缺省合理值）——kpi_title/spectrum_title/events_title
            （三图标题 str）、kpi_buffer（KPI 折线滚动窗口最近 N 点，缺省 600）、
            spectrum_rows（瀑布保留行数，缺省 128）、events_buffer（时间线保留
            标记数，缺省 40）、kpi_height/spectrum_height/events_height（三画布
            高度 px，缺省 220/260/140）。

    Returns:
        纯静态区块资产 str（<section id="triple-stream-charts"> + 三个 canvas
        chart-kpi/chart-spectrum/chart-events + 内联 JS——原生 JS+Canvas 2D，
        零外部依赖零 Vue 依赖）：连 /ws 按帧 type 字段分发三图，未知帧跳过计数
        （区块角 #tscharts-skipped），断线→区块顶"已断线，重连中"横幅+2s 自动
        重连续画。帧协议登记于 JS 顶部注释（stream_realtime_console 接线依据）。

    Raises:
        ValueError: config 非 dict/含未知键/标题非非空 str/缓冲长度或画布高度
            非正整数（bool 不算整数）。
    """
    cfg = _validate_config(config)
    # 标题经 html.escape（含引号/尖括号也不破标签）；缓冲配置 JSON 注入 JS。
    titles = {key: html.escape(cfg[key], quote=True) for key in _TITLE_KEYS}
    buffers = {key: cfg[key] for key in _BUFFER_KEYS}
    buffers_json = json.dumps(buffers, ensure_ascii=False).replace("</", "<\\/")
    block = (
        _BLOCK_TEMPLATE.replace("__KPI_TITLE__", titles["kpi_title"])
        .replace("__SPECTRUM_TITLE__", titles["spectrum_title"])
        .replace("__EVENTS_TITLE__", titles["events_title"])
        .replace("__KPI_HEIGHT__", str(cfg["kpi_height"]))
        .replace("__SPECTRUM_HEIGHT__", str(cfg["spectrum_height"]))
        .replace("__EVENTS_HEIGHT__", str(cfg["events_height"]))
        .replace("__CONFIG_JSON__", buffers_json)
    )
    return block
