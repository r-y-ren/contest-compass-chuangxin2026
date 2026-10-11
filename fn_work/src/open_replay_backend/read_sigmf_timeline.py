"""SigMF 解析为时间戳 IQ 块流+标注——重写规约与签名意图详见 fn_docs/responsibility.md。

不依赖 sigmf 第三方库：手写解析（json + struct）。支持 datatype：cf32_le/ci16_le/ci8_le。
"""
from __future__ import annotations

import json
import os
import struct
from typing import Iterator

# BackendError 单一事实源在注册表包（本包原先的本地定义已删除）：本模块 re-export
# 同一类——注册表侧调用方 `except BackendError` 能直接接住回放文件的错误，
# 外部 `from ...read_sigmf_timeline import BackendError` 的既有用法不破坏。
from src.manage_backend_registry.register_backend import BackendError

__all__ = ["BackendError", "read_sigmf_timeline"]


# datatype → (struct 解包码, 每复样本字节数, 满量程缩放；None=浮点原值不缩放)
_DATATYPES = {
    "cf32_le": ("<2f", 8, None),
    "ci16_le": ("<2h", 4, 32767.0),
    "ci8_le": ("<2b", 2, 127.0),
}


def _reject_nonfinite_literal(literal: str) -> float:
    """json.load 的 parse_constant 回调：NaN/Infinity/-Infinity 字面量一律拒。

    比逐字段后查更彻底——任何位置（含未来新增字段）的非有限字面量都在解析期即抛
    ValueError，由外层统一转 BackendError。（注意 parse_constant 只覆盖这三个常量
    字面量，普通数值溢出如 1e999 仍走各字段自身的域校验。）
    """
    raise ValueError(f"元数据含非有限数字字面量: {literal}")


def _field(obj: dict, name: str):
    """取 SigMF 字段：优先 core: 前缀（v1.x 规范写法），兼容无前缀；缺失返回 None。"""
    if f"core:{name}" in obj:
        return obj[f"core:{name}"]
    return obj.get(name)


def _is_uint(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def read_sigmf_timeline(sigmf_pair: str, block_size: int = 65536) -> Iterator[dict]:
    """解析 SigMF 录制对，按 block_size 逐块产出时间戳 IQ 块+覆盖该块的标注。

    输入: sigmf_pair=.sigmf-meta 路径（.sigmf-data 同名替换后缀）、block_size=每块样本数。
    输出: 生成器，逐块 dict：{'samples': list[complex], 'sample_start': int,
          'time_s': sample_start/sample_rate, 'annotations': 覆盖该块的标注原对象列表}。
    错误: BackendError（meta/data 文件缺失、元数据损坏/含 NaN|Infinity 字面量或缺字段、
          datatype 不支持、声明 num_samples 与实际字节数不符、captures 非升序即时间轴断裂）；
          block_size<=0 → ValueError。所有校验在调用时即刻执行（首块前报错）。
    """
    if block_size <= 0:
        raise ValueError(f"block_size 必须为正整数，收到: {block_size!r}")

    meta_path = sigmf_pair
    if not os.path.isfile(meta_path):
        raise BackendError(f"SigMF 元数据文件不存在: {meta_path}")

    if meta_path.endswith(".sigmf-meta"):
        data_path = meta_path[: -len(".sigmf-meta")] + ".sigmf-data"
    else:
        data_path = os.path.splitext(meta_path)[0] + ".sigmf-data"
    if not os.path.isfile(data_path):
        raise BackendError(f"SigMF 数据文件不存在: {data_path}")

    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            # parse_constant 拒 NaN/Infinity/-Infinity 字面量（sample_rate=NaN 等在此即拒）
            meta = json.load(fh, parse_constant=_reject_nonfinite_literal)
    except (OSError, ValueError) as exc:  # ValueError 覆盖 JSONDecodeError/UnicodeDecodeError/非有限字面量
        raise BackendError(f"SigMF 元数据不可解析: {meta_path}: {exc}") from exc
    if not isinstance(meta, dict):
        raise BackendError("SigMF 元数据根必须是 JSON 对象")

    glob = meta.get("global")
    if not isinstance(glob, dict):
        raise BackendError("SigMF 元数据缺少 global 对象")

    sample_rate = _field(glob, "sample_rate")
    if (
        not isinstance(sample_rate, (int, float))
        or isinstance(sample_rate, bool)
        or sample_rate <= 0
    ):
        raise BackendError(f"global.sample_rate 缺失或非法: {sample_rate!r}")

    datatype = _field(glob, "datatype")
    if not isinstance(datatype, str) or datatype not in _DATATYPES:
        raise BackendError(
            f"不支持的 SigMF datatype: {datatype!r}（支持: {'/'.join(_DATATYPES)}）"
        )
    fmt, bytes_per_sample, scale = _DATATYPES[datatype]

    num_samples = _field(glob, "num_samples")
    if not _is_uint(num_samples):
        raise BackendError(f"global.num_samples 缺失或非法: {num_samples!r}")

    expected_bytes = num_samples * bytes_per_sample
    actual_bytes = os.path.getsize(data_path)
    if actual_bytes != expected_bytes:
        raise BackendError(
            f"数据文件截断/超长: 声明 num_samples={num_samples} 应为 {expected_bytes} 字节，"
            f"实际 {actual_bytes} 字节: {data_path}"
        )

    captures = meta.get("captures")
    if not isinstance(captures, list):
        raise BackendError("SigMF 元数据缺少 captures 数组")
    last_start: int | None = None
    for cap in captures:
        if not isinstance(cap, dict):
            raise BackendError(f"capture 必须是 JSON 对象: {cap!r}")
        start = _field(cap, "sample_start")
        if not _is_uint(start):
            raise BackendError(f"capture.sample_start 缺失或非法: {start!r}")
        if last_start is not None and start <= last_start:
            raise BackendError(
                f"captures 时间轴断裂（非升序）: sample_start {last_start} -> {start}"
            )
        last_start = start
    if num_samples > 0:
        if not captures:
            raise BackendError("num_samples>0 但 captures 为空，时间轴不完整")
        assert last_start is not None
        if last_start >= num_samples:
            raise BackendError(
                f"capture.sample_start={last_start} 超出数据范围 num_samples={num_samples}"
            )

    raw_annotations = meta.get("annotations", [])
    if not isinstance(raw_annotations, list):
        raise BackendError("SigMF annotations 必须是数组")
    annotations: list[tuple[int, int, dict]] = []
    for ann in raw_annotations:
        if not isinstance(ann, dict):
            raise BackendError(f"annotation 必须是 JSON 对象: {ann!r}")
        a_start = _field(ann, "sample_start")
        a_count = _field(ann, "sample_count")
        if not _is_uint(a_start) or not _is_uint(a_count):
            raise BackendError(
                f"annotation.sample_start/sample_count 缺失或非法: {a_start!r}/{a_count!r}"
            )
        annotations.append((a_start, a_count, ann))

    def blocks() -> Iterator[dict]:
        with open(data_path, "rb") as fh:
            for block_start in range(0, num_samples, block_size):
                count = min(block_size, num_samples - block_start)
                raw = fh.read(count * bytes_per_sample)
                samples = [
                    complex(i, q) if scale is None else complex(i / scale, q / scale)
                    for (i, q) in struct.iter_unpack(fmt, raw)
                ]
                block_end = block_start + count
                covered = [
                    ann
                    for (a_start, a_count, ann) in annotations
                    if a_count > 0 and a_start < block_end and block_start < a_start + a_count
                ]
                yield {
                    "samples": samples,
                    "sample_start": block_start,
                    "time_s": block_start / sample_rate,
                    "annotations": covered,
                }

    return blocks()
