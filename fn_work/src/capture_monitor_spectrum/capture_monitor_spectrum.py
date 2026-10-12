"""监测谱采集→monitor.csv 行流（频率 bin+功率+时间戳）——重写规约与签名意图详见 fn_docs/responsibility.md。

消费监测 IQ 块流（read_b210_rx_stream 产出协议：samples/ts/overflow），逐块做
numpy FFT 功率谱（dB），以块级 dict 流式产出 bin 行列表；enforce_bandwidth_limit
在采集参数处实施 56MHz 边界（分段计划+受限口径附首块 meta）；ctx/params 提供
泄漏标定表时按频点扣除自漏（calibrate_leakage 的读表/插值语义，生成器生命
周期内表只读一次；表缺/无效不扣并标注 False）。
"""
from __future__ import annotations

import math
import os
from typing import Any, Iterator

import numpy as np

from .enforce_bandwidth_limit import (
    DEFAULT_DEVICE_BW_MHZ,
    DEFAULT_FREQ_RANGE_MHZ,
    MonitorError,
    enforce_bandwidth_limit,
)
import src.calibrate_leakage.calibrate_leakage as _leakage_impl

__all__ = ["MonitorError", "capture_monitor_spectrum"]

_DEFAULT_NFFT = 1024
_UNSET = object()
# 全零样本块 |FFT|^2=0 → 10*log10(0)=-inf：压到 float 最小正数，保每 bin dB 恒有限。
_POWER_FLOOR = float(np.finfo(np.float64).tiny)


def _as_positive_int(value: object, name: str) -> int:
    """正整数校验（bool 是 int 子类，一并排除），非法抛 ValueError。"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} 必须为正整数，收到: {value!r}")
    return int(value)


def _load_coupling_table(table_path: str | None):
    """按路径单次加载泄漏标定表（复用 calibrate_leakage 的读表/校验/插值件）。

    生成器生命周期内只读一次文件；表路径空/文件缺失/结构无效 → None（不扣除，
    不抛——与 calibrate_leakage 扣除请求的容错口径一致）。
    """
    if not table_path or not os.path.isfile(table_path):
        return None
    try:
        return _leakage_impl._load_table(table_path)
    except (OSError, ValueError, TypeError, KeyError):
        return None


def capture_monitor_spectrum(
    ctx: dict | None,
    stream: Any,
    params: dict | None = None,
    *,
    target_band: Any = _UNSET,
    nfft: Any = _UNSET,
    device_bw_mhz: Any = _UNSET,
    freq_range_mhz: Any = _UNSET,
    max_bins: Any = _UNSET,
    leakage_table_path: Any = _UNSET,
) -> Iterator[dict]:
    """监测谱采集：消费监测 IQ 块流，逐块产出功率谱 bin 行（生成器）。

    输入: ctx=运行上下文 dict|None（可含 'leakage_table_path'）；stream=监测 IQ 块
          迭代器（块 dict：'samples' 复数 IQ 序列、'ts' 块时间戳（缺则块序号兜底）、
          'overflow' 溢出标志（缺则 False））；params=采集参数 dict 或 None，
          键：target_band=(lo, hi) MHz 必填、nfft=1024、device_bw_mhz=56、
          freq_range_mhz=(70, 6000)、max_bins=每块最多产出 bin 数（默认 nfft 全出，
          超出按 nfft 截断）、leakage_table_path=泄漏标定表路径（可选）——同名关键字
          参数 > params > ctx（仅 leakage_table_path）> 缺省。
    输出: 生成器逐块 dict（跳过块不产出）：{'timestamp_ms': 流块 ts 或产出块序号,
          'segment': 段索引（按产出块序在计划段间轮转扫描）, 'center_mhz': 段中心,
          'bins': [{'freq_mhz': float, 'power_db': float}] 升频序列表（FFT bin 频点=
          段中心+fftshift(fftfreq(nfft, 1/设备带宽))，受限计划的收窄末段按段实际
          span 等比缩放，功率=10*log10(|FFT|²/nfft)；max_bins 截断保低频端）,
          'overflow': 流块溢出标志透传, 'leak_corrected':
          本块任一 bin 完成自漏扣除（表缺/无效→False 不抛）, 'invalid_blocks_so_far':
          迄今含 NaN/不可解析 IQ 而跳过的块计数}；首块另附 'plan'=enforce_bandwidth_limit
          全量计划（segments/limited/note，受限口径入 meta）。
    错误: 参数/计划错（target_band 缺失或形状非法、nfft/max_bins 非正整数、
          device_bw 非法 → ValueError；目标频段超设备能力域 → MonitorError）在调用时
          即刻抛出（不推迟到首块 next）；流迭代抛出的异常（BackendError 族）原样
          透传不包装；流块非 dict → MonitorError（流中断，走停发射路径）。
    口径: FFT 频窗为设备实时带宽（复基带满带宽采样）；受限分段计划中收窄的末段
          bin 频轴按段实际 span 等比缩放（段中心±span/2，不越目标带顶），其余段
          频轴为设备带宽口径。
    """
    if ctx is not None and not isinstance(ctx, dict):
        raise ValueError(f"ctx 必须为 dict 或 None，实际类型: {type(ctx).__name__}")
    if params is None:
        effective: dict = {}
    elif isinstance(params, dict):
        effective = params
    else:
        raise ValueError(f"params 必须为 dict 或 None，实际类型: {type(params).__name__}")

    def pick(name: str, kwarg: Any, default: Any = None) -> Any:
        """关键字参数 > params 键 > 缺省值 的三级取值。"""
        if kwarg is not _UNSET:
            return kwarg
        if name in effective:
            return effective[name]
        return default

    band = pick("target_band", target_band, _UNSET)
    if band is _UNSET:
        raise ValueError("缺少 target_band（目标观测频段 (lo, hi) MHz）：须经 params 或关键字参数提供")

    nfft_eff = _as_positive_int(pick("nfft", nfft, _DEFAULT_NFFT), "nfft")

    bins_cap_raw = pick("max_bins", max_bins, None)
    if bins_cap_raw is None:
        bins_cap = nfft_eff
    else:
        bins_cap = min(_as_positive_int(bins_cap_raw, "max_bins"), nfft_eff)

    device_bw_eff = pick("device_bw_mhz", device_bw_mhz, DEFAULT_DEVICE_BW_MHZ)
    freq_range_eff = pick("freq_range_mhz", freq_range_mhz, DEFAULT_FREQ_RANGE_MHZ)

    table_eff = pick("leakage_table_path", leakage_table_path, None)
    if table_eff is None and isinstance(ctx, dict):
        table_eff = ctx.get("leakage_table_path")
    if table_eff is None:
        table_path: str | None = None
    elif isinstance(table_eff, (str, os.PathLike)) and str(table_eff).strip():
        table_path = str(table_eff)
    else:
        raise ValueError(f"leakage_table_path 必须为非空路径，收到: {table_eff!r}")

    if stream is None:
        raise ValueError("stream 不能为 None（监测 IQ 块迭代器）")
    try:
        chunk_iter = iter(stream)
    except TypeError as exc:
        raise ValueError(f"stream 须为可迭代的监测 IQ 块流: {stream!r}") from exc

    # 采集计划在调用时即刻生成（受限口径随首块入 meta）；计划错透传（MonitorError/ValueError）。
    plan = enforce_bandwidth_limit(band, device_bw_mhz=device_bw_eff, freq_range_mhz=freq_range_eff)
    return _iter_monitor_blocks(chunk_iter, plan, nfft_eff, float(device_bw_eff), bins_cap, table_path)


def _iter_monitor_blocks(
    chunk_iter: Iterator[Any],
    plan: dict,
    nfft: int,
    sample_rate_mhz: float,
    bins_cap: int,
    table_path: str | None,
) -> Iterator[dict]:
    """实际采集循环：入口校验与计划已就绪，此处纯流式产出逻辑。"""
    segments = plan["segments"]
    n_segments = len(segments)
    # bin 基准频轴只依赖 nfft 与设备带宽（复基带满带宽采样），逐块复用；
    # 受限计划的收窄末段按段实际 span 等比缩放（频轴不越目标带顶）。
    bin_offsets = np.fft.fftshift(np.fft.fftfreq(nfft, d=1.0 / sample_rate_mhz))
    narrowed_plan = bool(plan.get("limited"))
    axis_by_segment: dict[int, np.ndarray] = {}
    # 泄漏标定表单次读入（生成器生命周期内复用；缺/无效 → None 不扣除）。
    coupling_table = _load_coupling_table(table_path)

    invalid_so_far = 0  # 含 NaN/不可解析 IQ 的跳过块累计（透传到后续产出块 meta）
    block_index = 0     # 产出块序号（跳过块不占号；驱动段轮转与 ts 兜底）

    for chunk in chunk_iter:
        if not isinstance(chunk, dict):
            raise MonitorError(
                f"监测流块必须为 dict（samples/ts/overflow），收到: {type(chunk).__name__}: {chunk!r}"
            )
        raw = chunk.get("samples")
        if raw is None:
            continue  # 空块（无样本）：跳过不产出、不计无效
        try:
            samples = np.asarray(raw, dtype=np.complex128)
        except (TypeError, ValueError):
            invalid_so_far += 1  # IQ 不可解析为复数：按无效块跳过计数
            continue
        if samples.size == 0:
            continue  # 空块跳过（不占产出块号、不计无效）
        if samples.ndim != 1 or not bool(np.all(np.isfinite(samples))):
            invalid_so_far += 1  # 形状异常或含 NaN/Inf：跳过计数，下一产出块透出累计
            continue

        # 加窗前规整到 nfft：长块截首、短块补零（谱分辨率恒为 nfft 口径）。
        if samples.size >= nfft:
            window = samples[:nfft]
        else:
            window = np.zeros(nfft, dtype=np.complex128)
            window[: samples.size] = samples
        spectrum = np.fft.fftshift(np.fft.fft(window))
        power = np.abs(spectrum) ** 2 / float(nfft)
        power_db = 10.0 * np.log10(np.maximum(power, _POWER_FLOOR))

        segment_index = block_index % n_segments
        center_mhz = float(segments[segment_index]["center_mhz"])
        offsets = axis_by_segment.get(segment_index)
        if offsets is None:
            span_mhz = float(segments[segment_index]["span_mhz"])
            offsets = (
                bin_offsets * (span_mhz / sample_rate_mhz)
                if narrowed_plan and span_mhz < sample_rate_mhz
                else bin_offsets
            )
            axis_by_segment[segment_index] = offsets
        timestamp = chunk.get("ts")
        if timestamp is None:
            timestamp = block_index

        leak_corrected = False
        rows: list[dict] = []
        for offset, db_value in zip(offsets, power_db):
            freq_mhz = float(offset + center_mhz)
            power_value = float(db_value)
            # 自漏扣除：频点查表插值回加（corrected = measured + coupling，表已
            # 单次读入）；表缺/无效 → 不扣不抛，块级标注 False。
            if coupling_table is not None and freq_mhz > 0.0 and math.isfinite(power_value):
                coupling_db = _leakage_impl._lookup_coupling(coupling_table, freq_mhz)[0]
                power_value = float(power_value + coupling_db)
                leak_corrected = True
            rows.append({"freq_mhz": freq_mhz, "power_db": power_value})

        block_out: dict = {
            "timestamp_ms": timestamp,
            "segment": segment_index,
            "center_mhz": center_mhz,
            "bins": rows[:bins_cap],
            "overflow": bool(chunk.get("overflow", False)),
            "leak_corrected": leak_corrected,
            "invalid_blocks_so_far": invalid_so_far,
        }
        if block_index == 0:
            block_out["plan"] = plan  # 分段计划+受限口径只附首块
        yield block_out
        block_index += 1
