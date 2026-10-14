"""三路采集编排：DUT-KPI ∥ 监测谱 ∥ 注入事件统一单调钟+对齐落盘——B12 顶层，R22。

调用方：execute_gb42590_protocol / run_demo（采集阶段——核心闭环关键一跳）。
重写规约与签名意图详见 fn_docs/responsibility.md R22，落地口径（R8 实现）：

- 启动序：DUT 路（sim → simulate_link_degradation 消费 ctx['sim_events']
  （缺省回落 ctx['dut']['events']）；真链路 → drive_esp32_link /
  drive_nrf24_link 消费 dut['serial_config']，ctx 整体透传以共享
  backend/run_token 停发射凭据）→ 逐样本 normalize_kpi 归一 → kpi.csv 逐行
  （表头 timestamp_ms,link,source,per,judge_per,rssi_dbm,retries,per_note）；
  sim 源样本的 timestamp_ms 以**主机单调钟毫秒盖戳**（走查环 F2 修复：
  simulate_link_degradation 自带合成仿真钟（0/+100ms…）与 append_event 事件
  钟/监测块钟不同域，直接透传则三元曲线开窗与三路对齐无样本相交——盖戳后
  三路同域；真链路 drive_* 样本本就主机钟，原样透传）；
  监测路 backend.read_samples（真实契约 list[块]——逐块拆包归一：B210 块 dict
  直通、sim (samples, meta) 元组转块 dict；连续空读超阈判耗尽）→
  capture_monitor_spectrum（ctx['monitor']
  平铺或 {'params': …} 外包裹均收，透传采集参数）→ 逐块 monitor.csv 写 bin
  行（timestamp_ms,freq_mhz,power_db,confidence 四列——confidence 缺省 'ok'，
  块 overflow → 'overflow'）+ 每块 compute_spectrum_stats(reference) 统计行
  另存 monitor_stats.jsonl（不混 bin 行）；sim 元组块归一时 ts 由主机单调钟
  盖戳（毫秒域，与 kpi/事件同域——rx_ts 块号降级 'block_index' 附注）；
  事件路注入事件由 ladder 经
  append_event 落 events.jsonl（本函数不重复写），对齐读内存共享
  ctx['jam_events']（缺省回落 ctx['events_sink'] / events.jsonl 读回，
  对齐源统一 ts_ms 主机单调毫秒域：事件优先取 'ts_ms' 键，'ts'
  （append_event 权威盖戳键，同主机单调域）兜底映射）；
- 协作停：ctx['stop']['flag']=True → 三路 drain 收尾（DUT/监测生成器
  close，spec 规约的惰性：停检在每路拉取之间，块不再多读一个），记
  'cooperative_stop' 注并以 append_event 落一条 streams_stopped 记帐事件
  （镜像 ctx['events_sink']——本函数唯一的 events.jsonl 写入，非注入事件
  重复；写失败 EventWriteError 走停发射路径）；
- 录制开关：record=True → 监测原始 IQ 块流式 tee 进 write_sigmf_recording
  （块到达即喂 capture 又落录制——同流分叉，录制写迭代驱动采集 tick，非
  先缓冲后写）；record=False → 'recording' 为 None，recordings/ 不创建；
- 安全铁律：采集期任一路异常（LinkError/BackendError/EventWriteError/
  StorageError/KpiError 等）→ 先 stop_transmit_safely 再原样透传；形状错
  （ctx/caps/dut/monitor 参数域）在启动前 ValueError 直抛（链路未启，
  不停发射、不动文件）；
- 单路耗尽区分：DUT 耗尽（sim 事件尽 / lines 行流尽）记
  'dut_source_exhausted' 继续收其余路；监测块尽记 'monitor_source_exhausted'；
  链路异常断（LinkError）→ 停发射后透传（不吞）；
- 防失控上限：kpi 行数到 max_kpi_rows / 监测块数到 max_monitor_blocks →
  停采（记 *_capped 注）不抛，正常返回；
- 返回 {'kpi_rows', 'monitor_blocks', 'stats_rows', 'alignment'
  （compute_alignment_error 全量结果）, 'recording'（write_sigmf_recording
  结果 | None）, 'streams_note': [各路状态注]}。
"""
from __future__ import annotations

import csv
import json
import math
import os
import time
from numbers import Real
from typing import Iterator

from .compute_alignment_error import compute_alignment_error
from src.capture_monitor_spectrum.capture_monitor_spectrum import (
    capture_monitor_spectrum,
)
from src.compute_spectrum_stats.compute_spectrum_stats import compute_spectrum_stats
from src.drive_esp32_link.drive_esp32_link import drive_esp32_link
from src.drive_nrf24_link.drive_nrf24_link import drive_nrf24_link
from src.simulate_link_degradation.simulate_link_degradation import (
    simulate_link_degradation,
)
from src.normalize_kpi.normalize_kpi import normalize_kpi
from src.shared.append_event import append_event
from src.shared.stop_transmit_safely import stop_transmit_safely
from src.write_sigmf_recording.write_sigmf_recording import write_sigmf_recording

__all__ = ["append_kpi_rows", "record_run_streams"]

#: 运行目录内三路落盘文件名。
KPI_FILENAME = "kpi.csv"
MONITOR_FILENAME = "monitor.csv"
MONITOR_STATS_FILENAME = "monitor_stats.jsonl"

#: kpi.csv 表头（精确口径，判据/图谱消费方依赖）。
KPI_HEADER = (
    "timestamp_ms",
    "link",
    "source",
    "per",
    "judge_per",
    "rssi_dbm",
    "retries",
    "per_note",
)

#: monitor.csv bin 行表头（四列）。
MONITOR_HEADER = ("timestamp_ms", "freq_mhz", "power_db", "confidence")

#: DUT 路合法源。
_DUT_SOURCES = ("esp32", "nrf24", "sim")

#: streams_note 状态注词汇表。
NOTE_DUT_EXHAUSTED = "dut_source_exhausted"
NOTE_MONITOR_EXHAUSTED = "monitor_source_exhausted"
NOTE_COOPERATIVE_STOP = "cooperative_stop"
NOTE_KPI_CAPPED = "kpi_rows_capped"
NOTE_MONITOR_CAPPED = "monitor_blocks_capped"


def _positive_int(value: object, name: str) -> int:
    """正整数校验（bool 是 int 子类，一并排除），非法抛 ValueError。"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} 必须为正 int，收到 {value!r}")
    return int(value)


def _finite_number(value: object) -> bool:
    """时间戳/数值合法性：有限实数（bool 不算）。"""
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _cell(value: object) -> str:
    """CSV 单元格：None → 空串，其余 str() 化。"""
    return "" if value is None else str(value)


def _jsonable(value):
    """递归把 float NaN/±Inf 规整为 None（jsonl 行严格可解析），容器不原地改动。"""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _stop_requested(stop: object) -> bool:
    """协作停判定：stop 为 dict 且 'flag' 为真（非 dict 形状忽略，不抛）。"""
    return isinstance(stop, dict) and bool(stop.get("flag"))


def _note(state: dict, note: str) -> None:
    """状态注去重追加（streams_note 按出现序）。"""
    if note not in state["noted"]:
        state["noted"].add(note)
        state["notes"].append(note)


#: 监测源空读熔断阈：read_samples 连续空读（[]/{}/None）达此数即判源耗尽收尾。
#: 真后端（sim/B210）瞬时无数据 ≠ 流尽（环回泵迟滞/采集间隙），阈内空读继续
#: 轮询；一次性流（replay 耗尽后恒 []）在阈内自然滑完不虚耗。
_MONITOR_EMPTY_READ_LIMIT = 50


def _as_monitor_block(block: object) -> object:
    """后端块形状归一：dict 直通；(samples, meta) 元组（sim 契约）转块 dict。

    SimBackend.read_samples 的元素是 (rx_block, meta) 二元组（meta 含 'rx_ts'
    单调**块号**，非毫秒域），而 capture_monitor_spectrum / write_sigmf_recording
    只认块 dict（samples/ts/overflow）——在此归一。归一时 ts 以**主机单调钟
    盖戳**（time.monotonic()*1000，与 kpi 样本（drive_*）及 append_event 事件
    同一毫秒域：rx_ts 块号直接当 ts 用会让 monitor.csv/统计行/对齐配对错单位，
    块号降级为 'block_index' 附注保留溯源）；其余形状原样透传（由 capture 的
    块形状校验拒，走停发射路径）。
    """
    if isinstance(block, dict):
        return block
    if isinstance(block, tuple) and len(block) == 2 and isinstance(block[1], dict):
        samples, meta = block
        return {
            "samples": samples,
            # 主机单调钟毫秒盖戳（B12 中#1）：块号非毫秒域，不得充当 ts；
            # 浮点毫秒保逐块严格递增（同毫秒内两块 int 会并列）。
            "ts": time.monotonic() * 1000.0,
            "block_index": meta.get("rx_ts"),  # sim 块号附注（溯源用，非时间戳）
            "overflow": bool(meta.get("overflow", False)),
        }
    return block


def _tee_backend_stream(state: dict) -> Iterator[dict]:
    """监测原始 IQ 块源（生成器）：read_samples 返回值按真实后端契约逐块拆包。

    真实契约（sim/B210）：read_samples() → list[块]（无数据 []）——逐块经
    _as_monitor_block 归一（B210 块即 dict；sim 块为 (samples, meta) 元组转
    块 dict，ts 以主机单调钟毫秒盖戳——rx_ts 块号非毫秒域）后 yield，绝不可
    把整个返回值当单块传下游；replay 旧契约为单块
    dict（耗尽恒 []），按单块直通兼容。空返回记一次空读并继续轮询，连续空读
    达 _MONITOR_EMPTY_READ_LIMIT 判源耗尽自然收尾（不抛——耗尽注由 _advance
    的 StopIteration 路径记 'monitor_source_exhausted'）。record=True 时每块
    同步入 tee_queue 供录制路消费（流式 tee：块到达即喂 capture 又可落录制）。
    """
    read = state["read_samples"]
    empty_reads = 0
    while True:
        result = read()
        if isinstance(result, list):
            blocks: list = result
        elif result:
            blocks = [result]  # replay 单块 dict / 未知单块形状透传（capture 拒）
        else:
            blocks = []  # []/{}/None——记一次空读
        if not blocks:
            empty_reads += 1
            if empty_reads >= _MONITOR_EMPTY_READ_LIMIT:
                return
            continue
        empty_reads = 0
        for raw_block in blocks:
            block = _as_monitor_block(raw_block)
            if state["record"]:
                state["tee_queue"].append(block)
            yield block


def _recording_stream(state: dict) -> Iterator[dict]:
    """录制路驱动流：write_sigmf_recording 的每次迭代 = 一个采集 tick。

    先排空 tee_queue（含收尾块），再推进 tick（DUT 拉取 + 监测块拉取/处理），
    采集 done 后收束——录制写迭代即采集主循环（同流分叉，无需先整体缓冲。
    """
    while True:
        if state["tee_queue"]:
            yield state["tee_queue"].pop(0)
            continue
        if state["done"]:
            return
        _advance(state)


def _advance(state: dict) -> None:
    """单采集 tick：停检 → DUT 拉一样本归一落盘 → 停检 → 监测拉一块处理。

    停检在每路拉取之间（协作停惰性：不再多读一个块）；任一路异常直接上抛
    （由 record_run_streams 统一先停发射再透传）；单路耗尽记注继续另一路；
    caps 到顶置 done 停采不抛。
    """
    if state["done"]:
        return
    if _stop_requested(state["stop"]):
        _note(state, NOTE_COOPERATIVE_STOP)
        state["done"] = True
        return

    if not state["dut_done"]:
        try:
            raw_sample = next(state["dut_gen"])
        except StopIteration:
            # 单路耗尽（sim 事件尽 / lines 行流尽）：正常收尾记注，继续其余路。
            state["dut_done"] = True
            _note(state, NOTE_DUT_EXHAUSTED)
        else:
            row = normalize_kpi(raw_sample, state["dut_source"])
            if state["dut_source"] == "sim":
                # 走查环 F2 修复：sim 源样本自带合成仿真钟（0/+100ms…）与
                # append_event 事件钟（time.monotonic 毫秒）不同域——开窗/对齐
                # 无样本相交。此处以主机单调钟毫秒盖戳（与事件/监测块同域，
                # _as_monitor_block 同式），原仿真钟不丢失口径：样本序即事件序
                # （生成器逐事件顺序产出），溯源归 kpi.csv 行序。
                row["timestamp_ms"] = time.monotonic() * 1000.0
            state["kpi_writer"].writerow(
                [
                    _cell(row["timestamp_ms"]),
                    _cell(row["link"]),
                    _cell(row["source"]),
                    _cell(row["per"]),
                    _cell(row["judge_per"]),
                    _cell(row["rssi_dbm"]),
                    _cell(row["retries"]),
                    _cell(row["meta"].get("per_note")),
                ]
            )
            state["kpi_rows"] += 1
            state["kpi_rows_list"].append(row)
            if state["kpi_rows"] >= state["max_kpi_rows"]:
                _note(state, NOTE_KPI_CAPPED)
                state["done"] = True
                return

    if _stop_requested(state["stop"]):
        _note(state, NOTE_COOPERATIVE_STOP)
        state["done"] = True
        return

    if not state["mon_done"]:
        try:
            spec_block = next(state["capture_gen"])
        except StopIteration:
            state["mon_done"] = True
            _note(state, NOTE_MONITOR_EXHAUSTED)
        else:
            _process_monitor_block(state, spec_block)
            if state["monitor_blocks"] >= state["max_monitor_blocks"]:
                _note(state, NOTE_MONITOR_CAPPED)
                state["done"] = True
                return

    if state["dut_done"] and state["mon_done"]:
        state["done"] = True


def _process_monitor_block(state: dict, block: dict) -> None:
    """一个谱块 → monitor.csv bin 行 + compute_spectrum_stats 统计行（jsonl）。"""
    ts = block.get("timestamp_ms")
    confidence = "overflow" if block.get("overflow") else "ok"
    bins = block.get("bins") or []
    for bin_row in bins:
        state["monitor_writer"].writerow(
            [
                _cell(ts),
                _cell(bin_row.get("freq_mhz")),
                _cell(bin_row.get("power_db")),
                confidence,
            ]
        )
    state["monitor_blocks"] += 1
    state["monitor_ts"].append({"timestamp_ms": ts})

    window: dict = {"bins": list(bins), "timestamp_ms": ts}
    if state["reference"] is not None:
        window["reference"] = state["reference"]
    stats_row = compute_spectrum_stats(window, state["reference"])
    state["stats_file"].write(
        json.dumps(_jsonable(stats_row), ensure_ascii=False) + "\n"
    )
    state["stats_rows"] += 1


def _read_events_jsonl(run_dir: str) -> list:
    """events.jsonl 读回（jam_events/events_sink 均缺省时的对齐兜底）。

    逐行解析，坏行/非 dict 行跳过不抛（对齐兜底尽力而为，事件真值的写路径
    归 append_event）。
    """
    path = os.path.join(run_dir, "events.jsonl")
    rows: list = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def _alignment_events(ctx: dict, run_dir: str) -> list:
    """对齐事件源解析：ctx['jam_events'] > ctx['events_sink'] > events.jsonl 读回。

    共享 list 在采集收尾后快照（各写方已同步 append 完）；对齐源统一 ts_ms
    主机单调毫秒域（与 sim 元组块归一盖戳 / kpi 样本钟同域）：事件优先取
    'ts_ms' 键，缺键时以 'ts'（append_event 权威盖戳键，同主机单调域）兜底
    映射；非 dict / 非有限 ts 条目防御性剔除（compute_alignment_error 的
    严格校验归其自有用例，编排层不替抛）。本函数不覆盖调用方事件数据——
    域统一由"优先 ts_ms + ts 兜底"的取值口径达成。
    """
    source = ctx.get("jam_events")
    if not isinstance(source, list):
        source = ctx.get("events_sink")
    if not isinstance(source, list):
        source = _read_events_jsonl(run_dir)
    events: list = []
    for entry in source:
        if not isinstance(entry, dict):
            continue
        if "ts_ms" not in entry and "ts" in entry:
            entry = {**entry, "ts_ms": entry["ts"]}
        if _finite_number(entry.get("ts_ms")):
            events.append(entry)
    return events


def _write_stop_bookkeeping(ctx: dict, run_dir: str) -> dict:
    """协作停记帐事件：append_event 落 events.jsonl 并镜像 events_sink。

    本函数唯一的 events.jsonl 写入（streams_stopped 是运行边界事实，非注入
    事件重复）；写失败 EventWriteError 由调用路径走停发射铁律。
    """
    line = append_event(
        run_dir,
        {
            "type": "streams_stopped",
            "reason": NOTE_COOPERATIVE_STOP,
            "origin": "record_run_streams",
        },
    )
    sink = ctx.get("events_sink")
    if isinstance(sink, list):
        sink.append(line)
    return line


def append_kpi_rows(run_dir: object, rows: list) -> int:
    """归一 KPI 行逐行追加 run_dir/kpi.csv（列映射 KPI_HEADER），返回写入行数。

    走查环 F2 配套（2026-10-14）：gb 判据路窗口样本此前只活在判据聚合里不落
    kpi.csv（采集阶段 record_run_streams 以 'w' 重写后三元曲线开窗只剩末窗样本
    ——各 power_step 窗普遍无判据样本）。本函数供 run_demo._execute_stage 在
    采集重写后按 ctx['judge_kpi_sink'] 重追加（与 distance 档行同款"就近补写"
    口径）；rows 元素为 normalize_kpi 归一行（timestamp_ms/link/source/per/
    judge_per/rssi_dbm/retries/meta.per_note——None → 空串）。文件不存在/为空
    先补 KPI_HEADER；run_dir 为 None 或 rows 非 list/为空 → 0（不抛）。
    """
    if run_dir is None or not isinstance(rows, list) or not rows:
        return 0
    owner = os.fspath(run_dir)
    path = os.path.join(owner, KPI_FILENAME)
    need_header = not os.path.exists(path) or os.path.getsize(path) == 0
    written = 0
    with open(path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if need_header:
            writer.writerow(KPI_HEADER)
        for row in rows:
            if not isinstance(row, dict):
                continue
            meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
            writer.writerow(
                [
                    _cell(row.get("timestamp_ms")),
                    _cell(row.get("link")),
                    _cell(row.get("source")),
                    _cell(row.get("per")),
                    _cell(row.get("judge_per")),
                    _cell(row.get("rssi_dbm")),
                    _cell(row.get("retries")),
                    _cell(meta.get("per_note")),
                ]
            )
            written += 1
    return written


def _recording_ctx(ctx: dict, run_dir: str, backend: object) -> dict:
    """录制路 ctx：run_dir + facts（ctx['facts'] 直给，缺省由 scenario 降级构建）。"""
    facts = ctx.get("facts")
    if not isinstance(facts, dict):
        scenario = ctx.get("scenario") if isinstance(ctx.get("scenario"), dict) else {}
        freq_hz = scenario.get("freq_hz")
        if freq_hz is None:
            freq_hz = (scenario.get("freq_mhz") or 0.0) * 1e6
        sample_rate = scenario.get("sample_rate")
        if sample_rate is None:
            sample_rate = scenario.get("sample_rate_hz") or 1.0
        run_id = scenario.get("run_id") or ctx.get("run_id")
        if not run_id:
            run_id = os.path.basename(run_dir.strip(os.sep)) or "run"
        facts = {
            "style": scenario.get("style") or scenario.get("jamming_style") or "unspecified",
            "backend": scenario.get("backend") or ctx.get("backend_name") or type(backend).__name__,
            "freq_hz": freq_hz,
            "sample_rate": sample_rate,
            "run_id": run_id,
        }
    return {"run_dir": run_dir, "facts": facts}


def record_run_streams(
    ctx: dict, max_kpi_rows: int = 10000, max_monitor_blocks: int = 1000
) -> dict:
    """三路采集编排：DUT-KPI ∥ 监测谱 ∥ 注入事件，统一单调钟盖戳+对齐落盘。

    输入: ctx——{'run_dir': 已存在运行目录, 'backend': 具备 read_samples 的监测
          后端（错误路径经 stop_transmit_safely 停发射）, 'scenario': 样式/
          freq/power 参数（录制 facts 降级素材、sim 信号电平）, 'dut':
          {'source': 'esp32'|'nrf24'|'sim', 'serial_config': 真链路配置,
          'events'/'model_params'/'samples_per_event': sim 配置}, 'monitor':
          采集参数 dict（平铺或 {'params': …} 外包裹，透传
          capture_monitor_spectrum，须含 target_band）, 'reference': 统计参考
          （可缺——缺省 power_only 口径）, 'record': IQ 录制开关, 'stop':
          {'flag': bool} 协作停（可缺）, 'sim_events': sim 注入事件源,
          'jam_events': 对齐共享事件 list（缺省回落 events_sink/events.jsonl）,
          'events_sink': 事件镜像 list, 'facts': 录制标注素材（可缺）,
          'run_token': 停发射运行级幂等 token（可缺）}；
          max_kpi_rows / max_monitor_blocks：防失控上限（到顶停采不抛）。
    输出: {'kpi_rows': int, 'monitor_blocks': int, 'stats_rows': int,
          'alignment': compute_alignment_error 结果, 'recording':
          write_sigmf_recording 结果|None, 'streams_note': [状态注…]}；
          副产物 run_dir 下 kpi.csv / monitor.csv / monitor_stats.jsonl
          （record=True 另有 recordings/ SigMF 对与协作停记帐 events.jsonl 行）。
    错误: ctx 形状错（非 dict / 缺 run_dir / dut 缺源 / sim 缺事件源 / 真链路
          缺 serial_config / monitor 参数坏 / caps 非正 int）→ ValueError（启动
          前直抛，不停发射）；采集期任一路异常（LinkError/BackendError/
          EventWriteError/StorageError/KpiError 等）→ 先 stop_transmit_safely
          再原样透传（安全铁律）。
    """
    # ---------- 阶段 A：形状校验 + 三路源构建（纯 ValueError，链路未启） ----------
    if not isinstance(ctx, dict):
        raise ValueError(f"ctx 必须为 dict，收到 {type(ctx).__name__}")
    max_kpi_rows = _positive_int(max_kpi_rows, "max_kpi_rows")
    max_monitor_blocks = _positive_int(max_monitor_blocks, "max_monitor_blocks")

    run_dir_raw = ctx.get("run_dir")
    if run_dir_raw is None or not isinstance(run_dir_raw, (str, os.PathLike)):
        raise ValueError(
            f"ctx['run_dir'] 缺失或非路径（str|PathLike），收到 {run_dir_raw!r}"
        )
    run_dir = os.fspath(run_dir_raw)
    if not run_dir.strip():
        raise ValueError("ctx['run_dir'] 为空路径，无法定位三路落盘文件")
    if not os.path.isdir(run_dir):
        raise ValueError(f"ctx['run_dir'] 不是已存在目录: {run_dir}")

    backend = ctx.get("backend")
    read_samples = getattr(backend, "read_samples", None) if backend is not None else None
    if not callable(read_samples):
        raise ValueError("ctx['backend'] 缺失或不具备 read_samples（监测路 IQ 块源）")

    dut = ctx.get("dut")
    if not isinstance(dut, dict):
        raise ValueError(
            f"ctx['dut'] 必须为 dict（source/serial_config/events…），"
            f"收到 {type(dut).__name__}"
        )
    dut_source = dut.get("source")
    if dut_source not in _DUT_SOURCES:
        raise ValueError(
            f"ctx['dut']['source'] 必须为 {_DUT_SOURCES} 之一，收到 {dut_source!r}"
        )

    monitor_cfg = ctx.get("monitor")
    if monitor_cfg is None:
        monitor_params: dict = {}
    elif isinstance(monitor_cfg, dict):
        # 平铺形状与 {'params': …} 外包裹形状均收（params 透传 capture）。
        nested = monitor_cfg.get("params")
        monitor_params = nested if isinstance(nested, dict) else monitor_cfg
    else:
        raise ValueError(
            f"ctx['monitor'] 必须为 dict（采集参数透传 capture_monitor_spectrum），"
            f"收到 {type(monitor_cfg).__name__}"
        )

    scenario = ctx.get("scenario") if isinstance(ctx.get("scenario"), dict) else {}
    stop_holder = ctx.get("stop")
    if stop_holder is not None and not isinstance(stop_holder, dict):
        stop_holder = None  # 非 dict 形状忽略（协作停凭据缺省不生效，不抛）

    # DUT 路生成器（drive_*/simulate 均在调用点急切校验，坏参数此刻 ValueError）。
    if dut_source == "sim":
        sim_events = ctx.get("sim_events")
        if sim_events is None:
            sim_events = dut.get("events")
        if sim_events is None:
            raise ValueError(
                "source='sim' 需要注入事件源：ctx['sim_events']（或 ctx['dut']['events']）"
                "须为 Iterable[dict]（调用方构造）"
            )
        sim_ctx = None
        if "signal_power_db" in scenario:
            sim_ctx = {"signal_power_db": scenario["signal_power_db"]}
        dut_gen = simulate_link_degradation(
            sim_events,
            model_params=dut.get("model_params"),
            ctx=sim_ctx,
            samples_per_event=dut.get("samples_per_event", 3),
        )
    else:
        serial_config = dut.get("serial_config")
        if not isinstance(serial_config, dict):
            raise ValueError(
                f"source={dut_source!r} 需要 ctx['dut']['serial_config']（dict），"
                f"收到 {serial_config!r}"
            )
        driver = drive_esp32_link if dut_source == "esp32" else drive_nrf24_link
        # ctx 整体透传：drive 取 backend/run_token 停发射凭据（token 缺省自生成
        # 写回 ctx，与本函数错误路径同 token 幂等——不重复实停）。
        dut_gen = driver(serial_config, ctx)

    state: dict = {
        "backend": backend,
        "read_samples": read_samples,
        "record": bool(ctx.get("record", False)),
        "stop": stop_holder,
        "reference": ctx.get("reference"),
        "dut_source": dut_source,
        "dut_gen": dut_gen,
        "dut_done": False,
        "capture_gen": None,
        "mon_done": False,
        "done": False,
        "notes": [],
        "noted": set(),
        "tee_queue": [],
        "kpi_rows": 0,
        "kpi_rows_list": [],
        "monitor_blocks": 0,
        "monitor_ts": [],
        "stats_rows": 0,
        "max_kpi_rows": max_kpi_rows,
        "max_monitor_blocks": max_monitor_blocks,
        "kpi_writer": None,
        "monitor_writer": None,
        "stats_file": None,
    }

    # 监测路（capture 构造即校验计划/参数：坏 target_band 等此刻 ValueError）。
    state["capture_gen"] = capture_monitor_spectrum(
        None, _tee_backend_stream(state), monitor_params
    )

    # ---------- 阶段 B：采集（任一异常先停发射再透传；finally 收生成器） ----------
    recording_result = None
    try:
        with open(
            os.path.join(run_dir, KPI_FILENAME), "w", newline="", encoding="utf-8"
        ) as kpi_file, open(
            os.path.join(run_dir, MONITOR_FILENAME), "w", newline="", encoding="utf-8"
        ) as monitor_file, open(
            os.path.join(run_dir, MONITOR_STATS_FILENAME), "w", encoding="utf-8"
        ) as stats_file:
            state["kpi_writer"] = csv.writer(kpi_file)
            state["kpi_writer"].writerow(KPI_HEADER)
            state["monitor_writer"] = csv.writer(monitor_file)
            state["monitor_writer"].writerow(MONITOR_HEADER)
            state["stats_file"] = stats_file

            if state["record"]:
                # 流式 tee：录制写迭代驱动采集主循环（块到达即喂 capture 又落录制）。
                recording_result = write_sigmf_recording(
                    _recording_stream(state), _recording_ctx(ctx, run_dir, backend)
                )
            else:
                while not state["done"]:
                    _advance(state)
            state["stats_file"] = None

        if NOTE_COOPERATIVE_STOP in state["noted"]:
            _write_stop_bookkeeping(ctx, run_dir)

        alignment = compute_alignment_error(
            {
                "events": _alignment_events(ctx, run_dir),
                "kpi": [
                    {"timestamp_ms": row.get("timestamp_ms")}
                    for row in state["kpi_rows_list"]
                    if _finite_number(row.get("timestamp_ms"))
                ],
                "monitor": [
                    row for row in state["monitor_ts"] if _finite_number(row.get("timestamp_ms"))
                ],
            }
        )
    except Exception as exc:  # noqa: BLE001 - 安全铁律：先停发射再原样透传
        stop_transmit_safely(
            backend,
            context={
                "origin": "record_run_streams",
                "reason": "stream_error",
                "error": f"{type(exc).__name__}: {exc}",
            },
            run_token=ctx.get("run_token"),
        )
        raise
    finally:
        # 协作停/异常路径统一 drain：两路生成器 close（close 失败不得掩盖主结果）。
        for gen in (state["dut_gen"], state.get("capture_gen")):
            close = getattr(gen, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001
                    pass

    return {
        "kpi_rows": state["kpi_rows"],
        "monitor_blocks": state["monitor_blocks"],
        "stats_rows": state["stats_rows"],
        "alignment": alignment,
        "recording": recording_result,
        "streams_note": list(state["notes"]),
    }
