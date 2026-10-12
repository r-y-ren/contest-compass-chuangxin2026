"""SigMF v1.2 IQ 归档（磁盘预检→分块 cf32_le 写→自动标注 meta→完整性校验）——重写规约与签名意图详见 fn_docs/responsibility.md。

落地口径（R27，调用方 record_run_streams 录制路，录原始 IQ 非统计谱）：

- 磁盘预检：任何字节落盘前 shutil.disk_usage 查目标盘剩余空间；样本总数
  事先未知（无法按 n_samples×8 预估需求），以固定阈值 200MB 代——剩余
  < 200MB → StorageError 附路径与剩余/阈值两数。本函数不负责停发射：
  抛出即调用方责任（R27 停发射语义在 record_run_streams）；
- 数据写：run_dir 下 recordings/ 目录落 <run_id 消毒串>.sigmf-data，
  cf32_le 编码（每样本 8 字节 = float32 实部/虚部交错小端；numpy
  ascontiguousarray→view('<f4')→tobytes 转字节），块迭代逐块 flush；
- 块形状：块非 dict、或缺 'samples' 键 → ValueError（附块索引，选拒）；
  samples 非 ndarray/list 等不可迭代 → 同 ValueError；
- 非法样本：samples 元素非 complex（float/int/str/None/bool；Python
  complex 与 numpy 复数标量均算合法）→ 写 0+0j 占位并计数，不拒录——
  总数标注进 meta global 'jam:invalid_samples'（选计数标注）；
- 空块/空流合法：空录制 0 样本（data 0 字节 + meta core:num_samples=0）；
- meta：facts 先经 annotate_truth_labels 干跑（非法 facts → ValueError
  先于任何数据落盘），数据写完后在其 global 更新 core:num_samples 并
  校验 core:datatype == 'cf32_le'（不符 → StorageError），JSON 写同名
  .sigmf-meta（与 .sigmf-data 同目录同 stem 成对）；
- 完整性：数据写毕核对「write 返回的实际写入字节计数」与「盘上文件
  大小」均等于 num_samples×8，任一不符 → StorageError（截断/超长双向，
  附路径与两数）；
- 写失败：open/mkdir/写/取大小任一 OSError → StorageError 附路径与原因；
- 返回 {'data_path','meta_path','num_samples','bytes_written'}；
  ctx 缺 run_dir/facts（键缺、值为 None、run_dir 空串）→ ValueError。
"""
from __future__ import annotations

import json
import os
import re
import shutil

import numpy as np

from .annotate_truth_labels import annotate_truth_labels

__all__ = ["StorageError", "write_sigmf_recording"]

#: 磁盘预检固定阈值（样本总数未知，以 200MB 固定阈值代预估需求）。
_MIN_FREE_BYTES = 200 * 1024 * 1024

#: cf32_le：每样本 8 字节（float32 实部+虚部交错、小端）。
_BYTES_PER_SAMPLE = 8
_CF32 = np.dtype("<c8")
_F32 = np.dtype("<f4")
_DATATYPE = "cf32_le"


class StorageError(Exception):
    """SigMF 录制落盘失败：磁盘不足/写失败/完整性不符（附路径与原因）。

    本异常不含停发射动作——捕获方（record_run_streams）负责先停发射再善后。
    """


def _existing_ancestor(path: str) -> str:
    """目标路径最深的已存在祖先目录（disk_usage 只接受存在的路径）。"""
    probe = os.path.abspath(path)
    while not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:  # 到根仍未命中（被文件挡住的路径）
            return probe
        probe = parent
    return probe


def _check_disk(recordings_dir: str) -> None:
    """磁盘预检：剩余 < 200MB → StorageError（附探测点、剩余与阈值两数）。"""
    probe = _existing_ancestor(recordings_dir)
    try:
        free = shutil.disk_usage(probe).free
    except OSError as exc:
        raise StorageError(f"磁盘预检失败 {probe}: {exc}") from exc
    if free < _MIN_FREE_BYTES:
        raise StorageError(
            f"磁盘剩余空间不足：{probe} 剩 {free} 字节 < 阈值 {_MIN_FREE_BYTES}"
            f" 字节（200MB），拒录 {recordings_dir}"
        )


def _is_complex_sample(value) -> bool:
    """样本元素合法性：Python complex 或 numpy 复数标量（np.complex64/128…）。"""
    return isinstance(value, complex) or isinstance(value, np.complexfloating)


def _encode_samples(samples, block_index: int) -> tuple[bytes, int, int]:
    """单块 samples → (cf32_le 小端 payload, 样本数, 非法样本数)。

    合法元素直取复数值；非 complex 元素写 0+0j 占位并计数（选计数标注）。
    复数 dtype 的 ndarray 走零拷贝快路（ascontiguousarray+view）；其余
    （list/tuple/object 数组/float 数组等）逐元素甄别。samples 不可迭代 →
    ValueError（附块索引）。
    """
    if isinstance(samples, np.ndarray) and np.issubdtype(
        samples.dtype, np.complexfloating
    ):
        contiguous = np.ascontiguousarray(samples, dtype=_CF32)
        return contiguous.view(_F32).tobytes(), int(contiguous.size), 0

    if isinstance(samples, np.ndarray):
        items = samples.tolist()  # 非复数 dtype 数组：逐元素口径甄别
    else:
        try:
            items = list(samples)
        except TypeError:
            raise ValueError(
                f"iq_stream[{block_index}] samples 不可迭代"
                f"（须 list[complex]|ndarray），实际为 {type(samples).__name__}"
            ) from None

    values = np.zeros(len(items), dtype=_CF32)
    invalid = 0
    for i, item in enumerate(items):
        if _is_complex_sample(item):
            values[i] = item
        else:
            invalid += 1  # 非 complex → 0+0j 占位，计数标注进 meta
    return values.view(_F32).tobytes(), len(items), invalid


def _write_block(fileobj, samples, block_index: int) -> tuple[int, int, int]:
    """单块写入：编码→write（按实际返回计数）→flush，返回 (样本数, 非法数, 实写字节)。"""
    payload, n_samples, n_invalid = _encode_samples(samples, block_index)
    written = fileobj.write(payload)
    fileobj.flush()
    return n_samples, n_invalid, written


def _recording_stem(facts: dict) -> str:
    """facts.run_id → 文件名安全 stem（路径危险字符折叠为 '_'，空则 'recording'）。"""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(facts.get("run_id") or ""))
    return safe.strip("._") or "recording"


def write_sigmf_recording(iq_stream, ctx: dict) -> dict:
    """SigMF v1.2 归档（磁盘预检/分块写/完整性校验）。

    输入: iq_stream 为块 dict 的可迭代序列（每块 {'samples': list[complex]|
    ndarray, 'ts'…}，ts 等余键忽略——录原始 IQ）；ctx 须含 'run_dir'
    （其下 recordings/ 落盘）与 'facts'（annotate_truth_labels 标注素材）。
    输出: {'data_path','meta_path','num_samples','bytes_written'}（路径为
    str，data/meta 同目录同 stem 成对）。
    错误: ctx 缺 run_dir/facts、块非 dict/缺 samples 键/samples 不可迭代、
    facts 形状非法 → ValueError；磁盘剩余 < 200MB、写失败（OSError）、
    datatype/完整性（num_samples×8 与实写及盘上大小任一不符，截断/超长
    双向）→ StorageError（附路径与原因；停发射是调用方责任）。
    """
    if not isinstance(ctx, dict):
        raise ValueError(f"ctx 必须为 dict，实际为 {type(ctx).__name__}")
    run_dir_raw = ctx.get("run_dir")
    if run_dir_raw is None or not isinstance(run_dir_raw, (str, os.PathLike)):
        raise ValueError(
            f"ctx['run_dir'] 缺失或非路径（str|PathLike），实际为 {run_dir_raw!r}"
        )
    if not str(run_dir_raw).strip():
        raise ValueError("ctx['run_dir'] 为空路径，无法定位 recordings/ 落盘目录")
    if ctx.get("facts") is None:
        raise ValueError("ctx['facts'] 缺失（须为 annotate_truth_labels 标注素材 dict）")
    try:
        blocks = iter(iq_stream)
    except TypeError:
        raise ValueError(
            f"iq_stream 必须为块 dict 的可迭代序列，实际为 {type(iq_stream).__name__}"
        ) from None

    run_dir = str(run_dir_raw)
    recordings_dir = os.path.join(run_dir, "recordings")

    # ① 磁盘预检：先于任何写（含目录创建）。
    _check_disk(recordings_dir)

    # ③ 前置干跑：facts 非法 → ValueError 先于任何数据落盘；meta 结构留待收尾补数。
    meta = annotate_truth_labels(ctx["facts"])
    global_meta = meta.setdefault("global", {})
    if global_meta.get("core:datatype") != _DATATYPE:
        raise StorageError(
            "SigMF 元数据 datatype 校验不符：期望 "
            f"{_DATATYPE}，实际 {global_meta.get('core:datatype')!r}"
        )

    stem = _recording_stem(ctx["facts"])
    data_path = os.path.join(recordings_dir, stem + ".sigmf-data")
    meta_path = os.path.join(recordings_dir, stem + ".sigmf-meta")

    # ② 流式写 .sigmf-data（cf32_le，逐块 flush）。
    num_samples = 0
    invalid_samples = 0
    bytes_written = 0
    try:
        os.makedirs(recordings_dir, exist_ok=True)
        with open(data_path, "wb") as data_file:
            for index, block in enumerate(blocks):
                if not isinstance(block, dict):
                    raise ValueError(
                        f"iq_stream[{index}] 必须为 dict（含 'samples' 键），"
                        f"实际为 {type(block).__name__}"
                    )
                if "samples" not in block:
                    raise ValueError(
                        f"iq_stream[{index}] 缺 'samples' 键（实际键为 "
                        f"{sorted(map(str, block))}），无法归档该 IQ 块"
                    )
                n_samples, n_invalid, written = _write_block(
                    data_file, block["samples"], index
                )
                num_samples += n_samples
                invalid_samples += n_invalid
                bytes_written += written
    except OSError as exc:
        raise StorageError(f"SigMF 数据写失败 {data_path}: {exc}") from exc

    # ④ 完整性校验：实写字节与盘上大小均须等于 num_samples×8（截断/超长双向）。
    expected_bytes = num_samples * _BYTES_PER_SAMPLE
    if bytes_written != expected_bytes:
        raise StorageError(
            f"SigMF 录制完整性不符 {data_path}：{num_samples} 样本应 "
            f"{expected_bytes} 字节，实际写入 {bytes_written} 字节（截断/短写）"
        )
    try:
        on_disk_bytes = os.path.getsize(data_path)
    except OSError as exc:
        raise StorageError(
            f"SigMF 录制完整性核对失败（读取数据文件大小）{data_path}: {exc}"
        ) from exc
    if on_disk_bytes != expected_bytes:
        direction = "截断" if on_disk_bytes < expected_bytes else "超长"
        raise StorageError(
            f"SigMF 录制完整性不符（{direction}）{data_path}：应 "
            f"{expected_bytes} 字节，盘上 {on_disk_bytes} 字节"
        )

    # ③ 收尾：更新 core:num_samples、标注非法样本计数，写 .sigmf-meta JSON。
    global_meta["core:num_samples"] = num_samples
    global_meta["jam:invalid_samples"] = invalid_samples
    try:
        with open(meta_path, "w", encoding="utf-8") as meta_file:
            json.dump(meta, meta_file, ensure_ascii=False, indent=2)
            meta_file.write("\n")
    except OSError as exc:
        raise StorageError(f"SigMF 元数据写失败 {meta_path}: {exc}") from exc

    return {
        "data_path": data_path,
        "meta_path": meta_path,
        "num_samples": num_samples,
        "bytes_written": bytes_written,
    }
