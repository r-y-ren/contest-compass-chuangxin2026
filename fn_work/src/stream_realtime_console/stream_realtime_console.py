"""实时流接通：运行期三路帧（KPI/监测谱/注入事件）经 push_realtime_kpi 推入操控台 /ws hub+延迟统计入结果 JSON——重写规约与签名意图详见 fn_docs/responsibility.md。

口径（R58；帧协议=render_triple_stream_charts 顶部「帧协议」注释约定）：
- 文件尾随桥：run_scenario 是无头管线（不内嵌推帧钩子）——本函数以解耦桥
  接通：发现/轮询 run_ctx['report_root'] 下新运行目录（首个不在发现基线里的
  目录），尾随其 kpi.csv（→kpi 帧 metrics={per,judge_per,rssi_dbm,retries}）、
  monitor.csv（→spectrum 帧 powers_db 按块时间戳聚合，可配时间窗）、
  events.jsonl（→event 帧 label=事件摘要），逐批经 push_realtime_kpi 推入
  hub（操控台 /ws hub：sockets/history dict，帧带 sent_ms 发送戳）；
- 推送调度：hub 携 'loop'（create_console_app WS 首连捕获的服务事件循环）
  且非当前线程运行环时，run_coroutine_threadsafe 入环执行 push（真实
  uvicorn 下 send_json 在正确事件环驱动）；否则当前线程直调（同步枢纽
  契约，push_realtime_kpi 原状口径）；
- 延迟统计（measure_refresh_latency 口径）：每帧配对 {'sent_ms': 行可见戳
  （尾随轮询首次看到该行的墙钟 ms——落盘时刻的可观测上界）, 'acked_ms':
  广播发送戳（push_realtime_kpi 盖的 frame['sent_ms']）}，收尾经
  measure_refresh_latency 出 P50/P95/超阈率；统计写入 run_ctx['result']
  ['realtime']（操控台侧由 serve_console 缺省 runner 并入该运行结果——
  app.state.runs 条目即「写入运行结果 JSON」的操控台落点），'on_result'
  回调（可给）同步收旨；
- 积压降频（沿用 R49 口径）：push_realtime_kpi 判 degraded（累计断连 ≥2
  或广播异常率严格 >50%）或 hub['degraded'] 已置位→推送轮询间隔升档
  （×4 封顶 degrade_max_interval_s）、后续帧盖 'degraded': True 标注、
  统计落 degrade_note；
- 错误语义：无订阅者→帧照常消费计数不报错；hub 失联（push 抛出，如
  hub 非 dict）→该批帧降级离线落盘 report_root/realtime_offline.jsonl
  不中断运行；新运行目录未出现（如校验失败不建目录）→discovery_timeout_s
  后安静退出（stopped_reason='discovery_timeout'）。
"""
import asyncio
import csv
import io
import json
import os
import time

from src.push_realtime_kpi.measure_refresh_latency import measure_refresh_latency
from src.push_realtime_kpi.push_realtime_kpi import push_realtime_kpi

from .render_triple_stream_charts import render_triple_stream_charts

__all__ = [
    "DISCOVERY_TIMEOUT_S",
    "MAX_FOLLOW_S",
    "OFFLINE_FILENAME",
    "POLL_INTERVAL_S",
    "build_realtime_charts",
    "stream_realtime_console",
]

#: 尾随轮询间隔缺省（秒）——降频升档的基数。
POLL_INTERVAL_S = 0.05

#: 新运行目录发现窗口缺省（秒）——校验失败等不建目录的运行安静退出。
DISCOVERY_TIMEOUT_S = 30.0

#: 尾随总时长安全上限缺省（秒）——防失控兜底（正常路径 result.json/stop 先到）。
MAX_FOLLOW_S = 900.0

#: result.json 出现后的静默收尾窗口缺省（秒）——吸走落盘竞态的尾行。
QUIESCE_S = 0.4

#: 降频升档后的间隔封顶缺省（秒）。
DEGRADE_MAX_INTERVAL_S = 1.0

#: 运行目录内三路落盘文件名（与 create_run_workspace 八件套口径一致）。
KPI_FILENAME = "kpi.csv"
MONITOR_FILENAME = "monitor.csv"
EVENTS_FILENAME = "events.jsonl"
RESULT_FILENAME = "result.json"

#: hub 失联时的离线落盘文件名（report_root 下，行级 JSONL：{'detected_ms','frames'}）。
OFFLINE_FILENAME = "realtime_offline.jsonl"

#: kpi.csv 表头列序（record_run_streams KPI_HEADER 口径）。
_KPI_HEADER_TUPLE = (
    "timestamp_ms",
    "link",
    "source",
    "per",
    "judge_per",
    "rssi_dbm",
    "retries",
    "per_note",
)

#: kpi.csv 数值列 → kpi 帧 metrics 键。
_KPI_METRIC_COLUMNS = ("per", "judge_per", "rssi_dbm", "retries")


def _now_ms() -> float:
    """墙钟毫秒戳（行可见/广播戳同源时钟，差值方可为端到端口径）。"""
    return round(time.time() * 1000.0, 3)


def _as_number(value: object) -> "float | None":
    """数值宽容转换：int/float 可（bool 不算），失败/NaN→None。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number != number:  # NaN（math.isnan 免 import）
        return None
    return number


def _validate_run_ctx(run_ctx: dict) -> None:
    """run_ctx 形状校验：非 dict/缺 report_root（非空 str）→ValueError。"""
    if not isinstance(run_ctx, dict):
        raise ValueError(
            f"run_ctx 必须为 dict（report_root/result/stop 等），实际 "
            f"{type(run_ctx).__name__}: {run_ctx!r}"
        )
    root = run_ctx.get("report_root")
    if not isinstance(root, str) or not root.strip():
        raise ValueError(
            f"run_ctx['report_root'] 必须为非空 str（被尾随的运行根目录），实际 {root!r}"
        )


class _FileTail:
    """单文件行尾随：read_new_lines() 返回自上次调用以来的完整行清单。

    文件缺失/暂未创建→[]（运行目录八件套创建有先后，缺文件是常态不报错）；
    尾部不完整行（缓冲块边界截断）留待下次补齐（CSV/JSONL 行级落盘口径）。
    重写自愈：record_run_streams 每采集段以 'w' 重写 kpi.csv/monitor.csv——
    以「已消费末行+\n」锚点验证（纯比长度会漏判重写后反而变长的文件）：
    锚点不在原偏移（或文件变短）即判被重写，归零重读全文（可能重复推少量
    帧，实时曲线缓冲容忍；绝不卡死在旧偏移漏读重写后的新行）。运行产物
    文件量级小（百行级），整读重扫成本可忽略。
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._consumed = 0  # 已消费的完整行末字符偏移（text 域）
        self._last_line: "str | None" = None  # 已消费末行（重写检测锚点）

    def _read_all(self) -> "str | None":
        try:
            with open(self._path, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return None  # 未创建/暂不可读：下轮再看

    def read_new_lines(self) -> "list[str]":
        content = self._read_all()
        if not content:
            return []
        anchor_offset = 0
        if self._last_line is not None:
            verify = self._last_line + "\n"
            end = self._consumed
            rewritten = len(content) < end or content[end - len(verify):end] != verify
            if rewritten:
                self._consumed = 0
                self._last_line = None
            else:
                anchor_offset = end
        region = content[anchor_offset:]
        lines = region.split("\n")
        partial = lines.pop()  # 末段：无换行符的尾块（下次整读重扫补齐）
        if lines:
            self._last_line = lines[-1]
            self._consumed = anchor_offset + len(region) - len(partial)
        return [line for line in lines if line.strip()]


def _csv_rows(lines: "list[str]") -> "list[list[str]]":
    """CSV 行批 → 单元格行（csv.reader 处理引号转义；空行丢弃）。"""
    if not lines:
        return []
    return [row for row in csv.reader(io.StringIO("\n".join(lines))) if row]


def _cell_number(cell: object) -> "float | None":
    """CSV 单元格 → 有限 float（''/'None'/文本/NaN/±inf→None）。"""
    if not isinstance(cell, str) or not cell.strip() or cell.strip() == "None":
        return None
    try:
        number = float(cell)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _kpi_frames(rows: "list[list[str]]", detect_ms: float) -> "list[dict]":
    """kpi.csv 新行 → kpi 帧（表头行跳过；数值列宽容转 metrics，空值列省略）。"""
    frames: list[dict] = []
    for row in rows:
        if not row or row[0].strip() == "timestamp_ms":  # 表头行
            continue
        cells = dict(zip(_KPI_HEADER_TUPLE, row))
        metrics = {}
        for key in _KPI_METRIC_COLUMNS:
            number = _cell_number(cells.get(key, ""))
            if number is not None:
                metrics[key] = number
        ts = _cell_number(cells.get("timestamp_ms", ""))
        frames.append(
            {
                "type": "kpi",
                "ts_ms": ts if ts is not None else detect_ms,
                "metrics": metrics,
            }
        )
    return frames


def _spectrum_frames(
    rows: "list[list[str]]", window_ms: float, detect_ms: float
) -> "list[dict]":
    """monitor.csv 新行 → spectrum 帧（powers_db 按块时间戳聚合）。

    同块 bin 行共享块时间戳（capture_monitor_spectrum 逐块落盘口径）：
    window_ms<=0 按时间戳精确分组（一块一帧）；>0 时按 floor(ts/窗) 分组
    （时间窗聚合）。非数值功率行丢弃；聚空组不发帧。
    """
    frames: list[dict] = []
    group_key: "float | int | None" = None
    group_ts: "float | None" = None
    powers: list[float] = []

    def _flush() -> None:
        nonlocal powers
        if powers and group_key is not None:
            frames.append(
                {
                    "type": "spectrum",
                    "ts_ms": group_ts if group_ts is not None else detect_ms,
                    "powers_db": powers,
                }
            )
        powers = []

    for row in rows:
        if not row or row[0].strip() == "timestamp_ms":  # 表头行
            continue
        ts = _cell_number(row[0])
        power = _cell_number(row[2]) if len(row) > 2 else None
        key = None if ts is None else (ts if window_ms <= 0 else int(ts // window_ms))
        if key != group_key:
            _flush()
            group_key = key
            group_ts = ts
        if power is not None:
            powers.append(power)
    _flush()
    return frames


#: 事件摘要优先展示键（label 短文本，叶子时间线标注用）。
_EVENT_LABEL_KEYS = ("step", "status", "passed", "target_db", "d_m", "reason")


def _event_label(event: dict) -> str:
    """事件行 → 时间线标签（type+一个可辨别字段，截 40 字符防撑爆画布）。"""
    etype = str(event.get("type") or "event").strip() or "event"
    for key in _EVENT_LABEL_KEYS:
        if key in event:
            value = event[key]
            if isinstance(value, bool):
                value = "通过" if value else "未过"
            return f"{etype} {key}={value}"[:40]
    return etype[:40]


def _event_frames(lines: "list[str]", detect_ms: float) -> "list[dict]":
    """events.jsonl 新行 → event 帧（坏行跳过；ts 单调毫秒域缺省行可见戳）。"""
    frames: list[dict] = []
    for line in lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        ts = _as_number(event.get("ts"))
        frames.append(
            {
                "type": "event",
                "ts_ms": ts if ts is not None else detect_ms,
                "label": _event_label(event),
            }
        )
    return frames


def _push_batch(batch: "list[dict]", hub: dict) -> dict:
    """一批帧经 push_realtime_kpi 推 hub（loop 在环外→run_coroutine_threadsafe）。

    hub['loop'] 为运行中的服务事件循环且不是当前线程的运行环时入环执行
    （真实 uvicorn 的 send_json 须在其事件环驱动）；否则当前线程直调
    （同步契约：fake socket/无服务环境）。入环调度失败回落直调；直调抛出
    由调用方按「hub 失联」走离线落盘。
    """
    loop = hub.get("loop")
    if isinstance(loop, asyncio.AbstractEventLoop) and not loop.is_closed():
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is not loop:
            async def _push_in_loop() -> dict:
                return push_realtime_kpi(iter(batch), hub)

            return asyncio.run_coroutine_threadsafe(_push_in_loop(), loop).result(
                timeout=10
            )
    return push_realtime_kpi(iter(batch), hub)


def _append_offline(report_root: str, batch: "list[dict]", detect_ms: float) -> int:
    """hub 失联降级：帧批离线落盘 report_root/realtime_offline.jsonl（尽力而为）。"""
    try:
        os.makedirs(report_root, exist_ok=True)
        with open(
            os.path.join(report_root, OFFLINE_FILENAME), "a", encoding="utf-8"
        ) as fh:
            fh.write(json.dumps({"detected_ms": detect_ms, "frames": batch}, ensure_ascii=False, default=str) + "\n")
        return len(batch)
    except OSError:
        return 0  # 连离线落盘都失败：只剩计数（绝不反杀运行）


def _snapshot_run_dirs(report_root: str) -> "list[str]":
    """report_root 下既有运行目录名清单（不可读→[]——空基线，容后自愈）。"""
    try:
        names = os.listdir(report_root)
    except OSError:
        return []
    return [n for n in names if os.path.isdir(os.path.join(report_root, n))]


def stream_realtime_console(run_ctx: dict, hub: dict) -> dict:
    """实时流接通：运行期三路帧（KPI/监测谱/事件）经 push_realtime_kpi 推入操控台 /ws hub+延迟统计入结果 JSON（详见 fn_docs/responsibility.md 功能块）。

    Args:
        run_ctx: 运行上下文 dict——'report_root'（必填非空 str：被尾随的运行根
            目录，新运行目录发现域）；'baseline_runs'（可选 set|list[str]：发现
            基线——既有运行目录名，None=启动时自快照；runner 侧应在发起运行前
            快照传入，规避竞态）；'result'（可选 dict：延迟统计落点容器——收尾
            写入本函数返回值于 'realtime' 键，缺省内建 {}）；'on_result'（可选
            callable(stats)：统计回调，与 'result' 并行生效）；'stop'（可选
            dict {'flag': bool}：提前停信号——runner 在运行收尾置 True）；'poll_interval_s'
            （缺省 0.05）、'discovery_timeout_s'（缺省 30——新运行目录未出现
            的安静退出窗口）、'max_follow_s'（缺省 900——尾随安全上限）、
            'quiesce_s'（缺省 0.4——result.json 出现后的静默收尾窗）、
            'spectrum_window_ms'（缺省 0——monitor 行聚合窗，0=按块时间戳
            一块一帧）、'degrade_max_interval_s'（缺省 1.0——降频升档封顶）。
        hub: 操控台 /ws hub dict（create_console_app 产出/serve_console 共享
            容器：sockets/history/broadcast；可选 'loop'=服务事件循环——推送
            经 run_coroutine_threadsafe 入环执行）。非 dict/失效时每批帧按
            「hub 失联」降级离线落盘，不中断运行。

    Returns:
        {'followed_run': 目录名|None, 'run_dir': 绝对路径|None, 'frames':
        {'kpi': n, 'spectrum': n, 'event': n}, 'n_pushed': 经 push 消费帧数,
        'n_disconnected': 断连计数, 'n_offline': 离线落盘帧数,
        'latency': measure_refresh_latency 结果（行可见→广播发送戳 P50/P95/
        超阈率）, 'ack_latency': 末批 push 的回执口径延迟（hub['acks']）,
        'degraded': 降频标志, 'degrade_note': str|None, 'poll_interval_s':
        收尾时推送间隔, 'stopped_reason': 'stop_flag'|'result_json'|
        'discovery_timeout'|'max_follow'}；同一 dict 写入 run_ctx['result']
        ['realtime'] 并（若给）交 'on_result' 回调。

    Raises:
        ValueError: run_ctx 非 dict / report_root 非非空 str（形状错显式拒）。
    """
    _validate_run_ctx(run_ctx)
    report_root = run_ctx["report_root"]
    poll_interval = float(run_ctx.get("poll_interval_s") or POLL_INTERVAL_S)
    discovery_timeout = float(run_ctx.get("discovery_timeout_s") or DISCOVERY_TIMEOUT_S)
    max_follow = float(run_ctx.get("max_follow_s") or MAX_FOLLOW_S)
    quiesce = float(run_ctx.get("quiesce_s") if run_ctx.get("quiesce_s") is not None else QUIESCE_S)
    spectrum_window = float(run_ctx.get("spectrum_window_ms") or 0.0)
    degrade_cap = float(run_ctx.get("degrade_max_interval_s") or DEGRADE_MAX_INTERVAL_S)
    stop_flag = run_ctx.get("stop") if isinstance(run_ctx.get("stop"), dict) else None

    stats = {
        "followed_run": None,
        "run_dir": None,
        "frames": {"kpi": 0, "spectrum": 0, "event": 0},
        "n_pushed": 0,
        "n_disconnected": 0,
        "n_offline": 0,
        "latency": None,
        "ack_latency": None,
        "degraded": False,
        "degrade_note": None,
        "poll_interval_s": poll_interval,
        "stopped_reason": "stop_flag",
    }
    frame_stamps: "list[dict]" = []

    def _stop_requested() -> bool:
        return bool(stop_flag and stop_flag.get("flag"))

    # ---- ① 发现新运行目录（首个不在基线里的目录；停止/超窗安静退出） ----
    baseline = run_ctx.get("baseline_runs")
    if baseline is None:
        baseline = set(_snapshot_run_dirs(report_root))
    else:
        baseline = set(baseline)
    followed: "str | None" = None
    discover_deadline = time.monotonic() + discovery_timeout
    while followed is None and not _stop_requested():
        for name in sorted(_snapshot_run_dirs(report_root)):
            if name not in baseline:
                followed = name
                break
        if followed is not None:
            break
        if time.monotonic() >= discover_deadline:
            stats["stopped_reason"] = "discovery_timeout"
            break
        time.sleep(poll_interval)

    # ---- ② 尾随三路文件 → 帧批 → push_realtime_kpi 推 hub ----
    if followed is not None:
        run_dir = os.path.join(report_root, followed)
        stats["followed_run"] = followed
        stats["run_dir"] = os.path.abspath(run_dir)
        tails = {
            "kpi": _FileTail(os.path.join(run_dir, KPI_FILENAME)),
            "monitor": _FileTail(os.path.join(run_dir, MONITOR_FILENAME)),
            "events": _FileTail(os.path.join(run_dir, EVENTS_FILENAME)),
        }
        result_path = os.path.join(run_dir, RESULT_FILENAME)
        follow_start = time.monotonic()
        result_seen_at: "float | None" = None
        stop_now = False
        while True:
            stop_now = _stop_requested()
            detect_ms = _now_ms()
            batch: list[dict] = []
            kpi_frames = _kpi_frames(_csv_rows(tails["kpi"].read_new_lines()), detect_ms)
            spectrum_frames_batch = _spectrum_frames(
                _csv_rows(tails["monitor"].read_new_lines()), spectrum_window, detect_ms
            )
            event_frames_batch = _event_frames(tails["events"].read_new_lines(), detect_ms)
            batch = kpi_frames + spectrum_frames_batch + event_frames_batch
            stats["frames"]["kpi"] += len(kpi_frames)
            stats["frames"]["spectrum"] += len(spectrum_frames_batch)
            stats["frames"]["event"] += len(event_frames_batch)

            if batch:
                if stats["degraded"]:
                    for frame in batch:
                        frame["degraded"] = True  # 降频期帧标注（R49 口径）
                try:
                    push_stats = _push_batch(batch, hub)
                except Exception:  # noqa: BLE001 - hub 失联：离线落盘不中断运行
                    stats["n_offline"] += _append_offline(report_root, batch, detect_ms)
                    push_stats = None
                if push_stats is not None:
                    stats["n_pushed"] += push_stats.get("n_pushed", 0)
                    stats["n_disconnected"] += push_stats.get("n_disconnected", 0)
                    stats["ack_latency"] = push_stats.get("latency")
                    degraded_now = bool(push_stats.get("degraded")) or bool(
                        hub.get("degraded") if isinstance(hub, dict) else False
                    )
                    if degraded_now and not stats["degraded"]:
                        old_interval = poll_interval
                        poll_interval = min(poll_interval * 4, degrade_cap)
                        stats["degraded"] = True
                        stats["degrade_note"] = (
                            f"R49 口径积压降频：推送间隔 {old_interval:.3f}s→"
                            f"{poll_interval:.3f}s（累计断连 ≥2 或广播异常率>50%），"
                            "降频期帧盖 degraded 标注"
                        )
                    for frame in batch:
                        sent = frame.get("sent_ms")
                        if _as_number(sent) is not None:
                            frame_stamps.append(
                                {"sent_ms": detect_ms, "acked_ms": sent}
                            )

            if stop_now:
                stats["stopped_reason"] = "stop_flag"
                break
            if os.path.isfile(result_path):
                if result_seen_at is None:
                    result_seen_at = time.monotonic()
                # result.json 已现且静默窗内无新行 → 运行收尾完成，尾随退出
                if time.monotonic() - result_seen_at >= quiesce and not batch:
                    stats["stopped_reason"] = "result_json"
                    break
            elif time.monotonic() - follow_start >= max_follow:
                stats["stopped_reason"] = "max_follow"
                break
            time.sleep(poll_interval)
        stats["poll_interval_s"] = poll_interval

    # ---- ③ 延迟统计（行可见→广播发送戳）+ 落点写回 ----
    stats["latency"] = measure_refresh_latency(frame_stamps)
    result_container = run_ctx.get("result")
    if not isinstance(result_container, dict):
        result_container = {}
        run_ctx["result"] = result_container
    result_container["realtime"] = stats
    on_result = run_ctx.get("on_result")
    if callable(on_result):
        try:
            on_result(stats)
        except Exception:  # noqa: BLE001 - 统计回调失败不反杀桥（落点已有 result）
            pass
    return stats


def build_realtime_charts(config: "dict | None" = None) -> str:
    """装配期三路图区资产（R58 接线：serve_console 注入 index 运行页的区块产物）。

    经手叶子 render_triple_stream_charts（responsibility 调用链：serve_console
    →本装配助手→叶子；config 形状校验与缺省口径归叶子，ValueError 原样透传）。
    运行期帧桥（stream_realtime_console）与装配期图区同源同协议。
    """
    return render_triple_stream_charts(config)
