"""write_sigmf_recording 对抗测试：cf32 精确字节/往返、空录制、磁盘预检先于任何写、写失败与截断/超长 StorageError、非法样本计数入 meta、ctx/块形状拒、大块性能冒烟、data/meta 成对。"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import src.write_sigmf_recording.write_sigmf_recording as write_sigmf_recording_module
from src.write_sigmf_recording.write_sigmf_recording import (
    StorageError,
    write_sigmf_recording,
)

_FACTS = {
    "style": "chirp",
    "params": {"bw_mhz": 2.0},
    "power_steps": [
        {"step": 0, "target_db": -10.0, "ts": 0.0},
        {"step": 1, "target_db": 0.0, "ts": 500.0},
    ],
    "backend": "sim",
    "clock_ref": "mono",
    "freq_hz": 2450e6,
    "sample_rate": 15.36e6,
    "run_id": "run-042",
    "window": {"start_ts": 0.0, "end_ts": 1000.0},
}

_TWO_BLOCKS = [
    {"samples": [1 + 2j, -0.5 - 0.25j, 3.5 + 0j], "ts": 0.0},
    {"samples": [0j, 1j, -1j, 1 + 1j, 2 - 2j], "ts": 1.0},
]


def _ctx(tmp_path) -> dict:
    """标准合法 ctx：run_dir 指向 tmp 目录，facts 为完整标注素材。"""
    return {"run_dir": str(tmp_path), "facts": dict(_FACTS)}


def _read_data(result: dict) -> np.ndarray:
    """录制的 .sigmf-data → cf32_le 复样本 ndarray。"""
    return np.frombuffer(Path(result["data_path"]).read_bytes(), dtype="<c8")


def _read_meta(result: dict) -> dict:
    """录制的 .sigmf-meta → 解析后的 JSON dict。"""
    return json.loads(Path(result["meta_path"]).read_text(encoding="utf-8"))


def test_sigmf_record_two_blocks_exact_bytes_num_samples_and_jam_meta(tmp_path):
    """① 两块 IQ→data 字节数精确 8×8、num_samples=8、meta 可解析含 jam 标注。"""
    result = write_sigmf_recording(_TWO_BLOCKS, _ctx(tmp_path))
    assert result["num_samples"] == 8
    assert result["bytes_written"] == 64
    assert os.path.getsize(result["data_path"]) == 64
    meta = _read_meta(result)
    assert meta["global"]["core:num_samples"] == 8
    assert meta["global"]["core:datatype"] == "cf32_le"
    assert meta["global"]["core:version"] == "1.2.0"
    assert meta["global"]["jam:backend"] == "sim"
    assert meta["global"]["jam:invalid_samples"] == 0
    assert meta["captures"][0]["core:frequency"] == 2450e6
    assert len(meta["annotations"]) == 2
    assert meta["annotations"][0]["jam:style"] == "chirp"
    assert meta["annotations"][1]["jam:power_db"] == 0.0


def test_sigmf_record_cf32_roundtrip_values_exact(tmp_path):
    """② cf32_le 编码往返：读回 float32 交错序与复样本值均精确（float32 可表示值）。"""
    samples = [1.0 + 2.0j, -0.5 - 0.25j, 3.5 + 0.0j, 0.0 - 1.5j]
    result = write_sigmf_recording([{"samples": samples}], _ctx(tmp_path))
    raw = np.frombuffer(Path(result["data_path"]).read_bytes(), dtype="<f4")
    assert raw.size == 8
    assert raw[0] == 1.0 and raw[1] == 2.0  # 实部/虚部交错小端序
    assert raw[2] == -0.5 and raw[3] == -0.25
    decoded = _read_data(result)
    assert np.array_equal(decoded, np.array(samples, dtype="<c8"))


def test_sigmf_record_empty_stream_and_empty_blocks_legal_zero_samples(tmp_path):
    """③ 空流/空块→空录制 0 样本合法：data 0 字节、meta core:num_samples=0。"""
    result = write_sigmf_recording([], _ctx(tmp_path))
    assert result["num_samples"] == 0
    assert result["bytes_written"] == 0
    assert os.path.getsize(result["data_path"]) == 0
    assert _read_meta(result)["global"]["core:num_samples"] == 0

    result_blocks = write_sigmf_recording(
        [{"samples": [], "ts": 0.0}, {"samples": []}], _ctx(tmp_path)
    )
    assert result_blocks["num_samples"] == 0
    assert os.path.getsize(result_blocks["data_path"]) == 0


def test_sigmf_record_disk_insufficient_storage_error_before_any_write(
    tmp_path, monkeypatch
):
    """④ 磁盘 mock 剩 100MB<200MB 阈值→StorageError 附路径，且先于任何写（无落盘）。"""
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=10**9, used=900 * 1024 * 1024, free=100 * 1024 * 1024),
    )
    with pytest.raises(StorageError) as excinfo:
        write_sigmf_recording(_TWO_BLOCKS, _ctx(tmp_path))
    assert str(tmp_path / "recordings") in str(excinfo.value)
    assert "200" in str(excinfo.value)  # 阈值随异常回报
    assert list(tmp_path.iterdir()) == []  # 目录/文件均未创建


def test_sigmf_record_disk_free_exactly_at_threshold_proceeds(tmp_path, monkeypatch):
    """⑤ 剩余恰等 200MB 阈值（不小于）→放行录制成功（仅严格小于才拒）。"""
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=10**9, used=10**9 - 200 * 1024 * 1024, free=200 * 1024 * 1024),
    )
    result = write_sigmf_recording([{"samples": [1j, 2j]}], _ctx(tmp_path))
    assert result["num_samples"] == 2
    assert os.path.isfile(result["data_path"])


def test_sigmf_record_write_failure_directory_deleted_midstream(tmp_path):
    """⑥ 流中途删 recordings 目录（写路径失效）→StorageError 附数据路径。"""
    recordings = tmp_path / "recordings"

    def vanishing_stream():
        yield {"samples": [1j, 2j]}
        shutil.rmtree(recordings)
        yield {"samples": [3j]}

    with pytest.raises(StorageError) as excinfo:
        write_sigmf_recording(vanishing_stream(), _ctx(tmp_path))
    assert str(recordings) in str(excinfo.value)
    assert "sigmf-data" in str(excinfo.value)


def test_sigmf_record_integrity_mismatch_truncated_and_overlong(tmp_path, monkeypatch):
    """⑦ 完整性不符双向：monkeypatch 编码器写半截/多写→StorageError（截断与超长）。"""
    original_encode = write_sigmf_recording_module._encode_samples

    def half_payload(samples, block_index):
        payload, n_samples, n_invalid = original_encode(samples, block_index)
        return payload[: len(payload) // 2], n_samples, n_invalid

    monkeypatch.setattr(write_sigmf_recording_module, "_encode_samples", half_payload)
    with pytest.raises(StorageError, match="完整性不符.*截断"):
        write_sigmf_recording([{"samples": [1j, 2j, 3j, 4j]}], _ctx(tmp_path))

    def overlong_payload(samples, block_index):
        payload, n_samples, n_invalid = original_encode(samples, block_index)
        return payload + b"\x00" * 8, n_samples, n_invalid

    monkeypatch.setattr(
        write_sigmf_recording_module, "_encode_samples", overlong_payload
    )
    with pytest.raises(StorageError, match="完整性不符"):
        write_sigmf_recording([{"samples": [1j, 2j, 3j, 4j]}], _ctx(tmp_path))


def test_sigmf_record_non_complex_samples_counted_and_zero_filled(tmp_path):
    """⑧ 非 complex 元素→0+0j 占位、计数标注 meta 'jam:invalid_samples'（不拒录）。"""
    samples = [1 + 1j, 2.5, "x", None, 3 + 4j]
    result = write_sigmf_recording([{"samples": samples}], _ctx(tmp_path))
    assert result["num_samples"] == 5
    meta = _read_meta(result)
    assert meta["global"]["jam:invalid_samples"] == 3
    decoded = _read_data(result)
    expected = np.array([1 + 1j, 0j, 0j, 0j, 3 + 4j], dtype="<c8")
    assert np.array_equal(decoded, expected)


def test_sigmf_record_block_missing_samples_key_rejected_valueerror(tmp_path):
    """⑨ 块缺 'samples' 键→ValueError（选拒），消息含块索引与实际键。"""
    with pytest.raises(ValueError, match="iq_stream\\[1\\].*samples"):
        write_sigmf_recording(
            [{"samples": [1j]}, {"ts": 5.0}], _ctx(tmp_path)
        )


def test_sigmf_record_ctx_missing_run_dir_or_facts_rejected(tmp_path):
    """⑩ ctx 缺 run_dir/facts（含值为 None）→ValueError；facts 形状非法先于落盘拒。"""
    with pytest.raises(ValueError, match="run_dir"):
        write_sigmf_recording([], {"facts": dict(_FACTS)})
    with pytest.raises(ValueError, match="facts"):
        write_sigmf_recording([], {"run_dir": str(tmp_path)})
    with pytest.raises(ValueError, match="facts"):
        write_sigmf_recording([], {"run_dir": str(tmp_path), "facts": None})

    bad_facts = {key: value for key, value in _FACTS.items() if key != "style"}
    with pytest.raises(ValueError, match="style"):
        write_sigmf_recording(
            [{"samples": [1j]}], {"run_dir": str(tmp_path), "facts": bad_facts}
        )
    assert not (tmp_path / "recordings").exists()  # 干跑校验先于任何数据落盘


def test_sigmf_record_large_block_smoke_under_two_seconds(tmp_path):
    """⑪ 1e6 样本大块性能冒烟：<2s 完成，字节数恰 8e6。"""
    rng = np.random.default_rng(7)
    big = (rng.standard_normal(1_000_000) + 1j * rng.standard_normal(1_000_000)).astype(
        np.complex64
    )
    start = time.perf_counter()
    result = write_sigmf_recording([{"samples": big}], _ctx(tmp_path))
    elapsed = time.perf_counter() - start
    assert result["num_samples"] == 1_000_000
    assert result["bytes_written"] == 8_000_000
    assert os.path.getsize(result["data_path"]) == 8_000_000
    assert elapsed < 2.0


def test_sigmf_record_data_and_meta_same_stem_pair(tmp_path):
    """⑫ data 与 meta 同目录同 stem 成对落盘（路径断言），stem 派生自 run_id。"""
    result = write_sigmf_recording([{"samples": [1j]}], _ctx(tmp_path))
    data_path, meta_path = result["data_path"], result["meta_path"]
    assert os.path.isfile(data_path)
    assert os.path.isfile(meta_path)
    assert data_path.endswith(".sigmf-data")
    assert meta_path.endswith(".sigmf-meta")
    assert os.path.dirname(data_path) == os.path.dirname(meta_path)
    data_stem = os.path.splitext(os.path.basename(data_path))[0]
    meta_stem = os.path.splitext(os.path.basename(meta_path))[0]
    assert data_stem == meta_stem
    assert data_stem.startswith("run-042")  # run_id 派生命名


def test_sigmf_record_ndarray_complex_blocks_fast_path_roundtrip(tmp_path):
    """⑬ complex64/complex128 ndarray 块→零拷贝快路：样本数/往返/invalid=0。"""
    block64 = np.array([1 + 2j, 3 - 4j], dtype=np.complex64)
    block128 = np.array([-1.5 + 0.5j], dtype=np.complex128)
    result = write_sigmf_recording(
        [{"samples": block64}, {"samples": block128}], _ctx(tmp_path)
    )
    assert result["num_samples"] == 3
    assert _read_meta(result)["global"]["jam:invalid_samples"] == 0
    decoded = _read_data(result)
    expected = np.array([1 + 2j, 3 - 4j, -1.5 + 0.5j], dtype="<c8")
    assert np.array_equal(decoded, expected)
