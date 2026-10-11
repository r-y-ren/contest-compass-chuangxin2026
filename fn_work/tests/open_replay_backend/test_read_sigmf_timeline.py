"""read_sigmf_timeline 对抗单测（slug=backend_replay 的 SigMF 时间轴切块叶子）。"""
import json
import os
import struct

import pytest

from src.open_replay_backend.read_sigmf_timeline import BackendError, read_sigmf_timeline


def _write_pair(
    tmp_path,
    *,
    datatype="cf32_le",
    sample_rate=2_000_000,
    num_samples,
    samples_bytes,
    captures=None,
    annotations=None,
    name="rec",
    meta_override=None,
):
    """写一对 .sigmf-meta/.sigmf-data，返回 meta 路径 str。meta_override 直接覆盖顶层键。"""
    meta = {
        "global": {
            "core:datatype": datatype,
            "core:sample_rate": sample_rate,
            "core:version": "1.2.0",
            "core:num_samples": num_samples,
        },
        "captures": captures if captures is not None else [{"core:sample_start": 0}],
        "annotations": annotations if annotations is not None else [],
    }
    if meta_override:
        meta.update(meta_override)
    meta_path = tmp_path / f"{name}.sigmf-meta"
    data_path = tmp_path / f"{name}.sigmf-data"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    data_path.write_bytes(samples_bytes)
    return str(meta_path)


def _cf32_bytes(*iq_pairs):
    return struct.pack("<" + "2f" * len(iq_pairs), *[v for pair in iq_pairs for v in pair])


def test_cf32_roundtrip_exact_values(tmp_path):
    meta = _write_pair(
        tmp_path,
        num_samples=3,
        samples_bytes=_cf32_bytes((1.5, -2.25), (0.0, 0.5), (-3.0, 4.0)),
    )
    blocks = list(read_sigmf_timeline(meta))
    assert len(blocks) == 1
    b = blocks[0]
    assert b["samples"] == [complex(1.5, -2.25), 0.5j, complex(-3.0, 4.0)]
    assert b["sample_start"] == 0
    assert b["time_s"] == 0.0
    assert b["annotations"] == []


def test_ci16_scaling_one_over_32767(tmp_path):
    data = struct.pack("<6h", 32767, -32767, 16384, -16384, 0, 1)
    meta = _write_pair(tmp_path, datatype="ci16_le", num_samples=3, samples_bytes=data)
    (b,) = read_sigmf_timeline(meta)
    assert b["samples"] == [
        complex(32767 / 32767, -32767 / 32767),
        complex(16384 / 32767, -16384 / 32767),
        complex(0 / 32767, 1 / 32767),
    ]


def test_ci8_scaling_one_over_127(tmp_path):
    data = struct.pack("<4b", 127, -128, 0, -1)
    meta = _write_pair(tmp_path, datatype="ci8_le", num_samples=2, samples_bytes=data)
    (b,) = read_sigmf_timeline(meta)
    assert b["samples"] == [
        complex(127 / 127, -128 / 127),
        complex(0 / 127, -1 / 127),
    ]


def test_block_boundary_131072_samples_block_65536(tmp_path):
    n, block = 131072, 65536
    data = struct.pack("<2f", 1.0, 0.0) * n
    meta = _write_pair(
        tmp_path, sample_rate=1_000_000, num_samples=n, samples_bytes=data
    )
    blocks = list(read_sigmf_timeline(meta, block_size=block))
    assert len(blocks) == 2  # 恰 2 块，不多不少
    assert [b["sample_start"] for b in blocks] == [0, 65536]
    assert [len(b["samples"]) for b in blocks] == [65536, 65536]
    assert all(s == 1.0 + 0.0j for s in blocks[0]["samples"] + blocks[1]["samples"])
    assert blocks[1]["time_s"] == 65536 / 1_000_000


def test_partial_last_block(tmp_path):
    # 100 样本、block 64 → 64+36 两块
    vals = [(i, -i) for i in range(100)]
    data = struct.pack("<" + "2h" * 100, *[v for pair in vals for v in pair])
    meta = _write_pair(tmp_path, datatype="ci16_le", num_samples=100, samples_bytes=data)
    blocks = list(read_sigmf_timeline(meta, block_size=64))
    assert [len(b["samples"]) for b in blocks] == [64, 36]
    assert blocks[0]["samples"][63] == complex(63 / 32767, -63 / 32767)
    assert blocks[1]["samples"][0] == complex(64 / 32767, -64 / 32767)


def test_annotations_land_in_covered_blocks(tmp_path):
    ann_only_b0 = {
        "core:sample_start": 0,
        "core:sample_count": 32,
        "core:description": "style: noise",
        "power_dbm": -60,
    }
    ann_span = {"core:sample_start": 60, "core:sample_count": 10,
                "core:description": "style: pulse"}
    ann_only_b1 = {"core:sample_start": 64, "core:sample_count": 8,
                   "core:description": "style: chirp"}
    ann_past_end = {"core:sample_start": 120, "core:sample_count": 100,
                    "core:description": "style: sweep"}
    meta = _write_pair(
        tmp_path,
        num_samples=128,
        samples_bytes=b"\x00" * (128 * 8),
        annotations=[ann_only_b0, ann_span, ann_only_b1, ann_past_end],
    )
    blocks = list(read_sigmf_timeline(meta, block_size=64))
    assert blocks[0]["annotations"] == [ann_only_b0, ann_span]
    # ann_only_b1 起点=块0终点(64)，按左闭右开不覆盖块0；ann_span 跨界两块都归位
    assert blocks[1]["annotations"] == [ann_span, ann_only_b1, ann_past_end]


def test_num_samples_mismatch_raises(tmp_path):
    # 短文件（截断）与长文件（实际多于声明）双向都要报
    for declared, actual_samples in [(1000, 10), (1, 100)]:
        meta = _write_pair(
            tmp_path,
            num_samples=declared,
            samples_bytes=b"\x00" * (actual_samples * 8),
            name=f"mismatch_{declared}_{actual_samples}",
        )
        with pytest.raises(BackendError):
            list(read_sigmf_timeline(meta))


def test_captures_non_ascending_raises(tmp_path):
    for caps in (
        [{"core:sample_start": 0}, {"core:sample_start": 500}, {"core:sample_start": 200}],
        [{"core:sample_start": 0}, {"core:sample_start": 0}],  # 重复=非升序=断裂
    ):
        name = f"caps_{caps[-1]['core:sample_start']}_{len(caps)}"
        meta = _write_pair(
            tmp_path,
            num_samples=8,
            samples_bytes=b"\x00" * 64,
            captures=caps,
            name=name,
        )
        with pytest.raises(BackendError):
            read_sigmf_timeline(meta)


def test_unsupported_datatype_raises(tmp_path):
    for dt in ("cu8_le", "cf64_le", "cf32", "rf32_le"):
        meta = _write_pair(
            tmp_path,
            datatype=dt,
            num_samples=1,
            samples_bytes=b"\x00" * 8,
            name=f"dt_{dt.replace('.', '_')}",
        )
        with pytest.raises(BackendError):
            read_sigmf_timeline(meta)


def test_meta_file_missing_raises(tmp_path):
    with pytest.raises(BackendError):
        read_sigmf_timeline(str(tmp_path / "nope.sigmf-meta"))


def test_data_file_missing_raises(tmp_path):
    meta = _write_pair(tmp_path, num_samples=1, samples_bytes=b"\x00" * 8)
    os.remove(meta.replace(".sigmf-meta", ".sigmf-data"))
    with pytest.raises(BackendError):
        read_sigmf_timeline(meta)


def test_block_size_non_positive_raises_value_error(tmp_path):
    meta = _write_pair(tmp_path, num_samples=1, samples_bytes=b"\x00" * 8)
    for bad in (0, -5):
        with pytest.raises(ValueError):
            read_sigmf_timeline(meta, block_size=bad)
    # block_size 校验先于任何文件 IO：不存在的路径 + block_size=0 仍是 ValueError
    with pytest.raises(ValueError):
        read_sigmf_timeline(str(tmp_path / "nope.sigmf-meta"), block_size=0)


def test_empty_recording_yields_nothing(tmp_path):
    meta = _write_pair(
        tmp_path,
        num_samples=0,
        samples_bytes=b"",
        captures=[{"core:sample_start": 0}],
    )
    assert list(read_sigmf_timeline(meta)) == []


def test_missing_required_fields_raise(tmp_path):
    cases = {
        "no_global": {"global": None},
        "no_sample_rate": {"global": {"core:datatype": "cf32_le", "core:num_samples": 1}},
        "no_datatype": {"global": {"core:sample_rate": 1e6, "core:num_samples": 1}},
        "no_num_samples": {"global": {"core:datatype": "cf32_le", "core:sample_rate": 1e6}},
        "no_captures": {"captures": None},
        "no_capture_start": {"captures": [{"core:frequency": 2_400_000_000}]},
        "no_annotation_start": {
            "annotations": [{"core:sample_count": 4, "core:description": "x"}]
        },
    }
    for name, override in cases.items():
        meta = _write_pair(
            tmp_path, num_samples=1, samples_bytes=b"\x00" * 8,
            meta_override=override, name=name,
        )
        with pytest.raises(BackendError):
            read_sigmf_timeline(meta)


def test_invalid_json_meta_raises(tmp_path):
    meta_path = tmp_path / "broken.sigmf-meta"
    (tmp_path / "broken.sigmf-data").write_bytes(b"\x00" * 8)
    meta_path.write_text("{not json!!", encoding="utf-8")
    with pytest.raises(BackendError):
        read_sigmf_timeline(str(meta_path))


def test_unprefixed_keys_accepted(tmp_path):
    # 兼容无 core: 前缀的简写元数据
    meta_path = tmp_path / "plain.sigmf-meta"
    (tmp_path / "plain.sigmf-data").write_bytes(_cf32_bytes((1.0, 1.0)))
    meta_path.write_text(
        json.dumps(
            {
                "global": {"datatype": "cf32_le", "sample_rate": 48_000, "num_samples": 1},
                "captures": [{"sample_start": 0}],
                "annotations": [],
            }
        ),
        encoding="utf-8",
    )
    (b,) = read_sigmf_timeline(str(meta_path))
    assert b["samples"] == [1.0 + 1.0j]
    assert b["time_s"] == 0.0


def test_nonfinite_number_literals_rejected_at_parse(tmp_path):
    # 对抗：NaN/Infinity/-Infinity 字面量（如 sample_rate=NaN）在 json 解析期即拒
    # （parse_constant），不进入逐字段校验，更不会把 NaN 传播进 time_s——BackendError
    for i, literal in enumerate(("NaN", "Infinity", "-Infinity")):
        meta_path = tmp_path / f"nf{i}.sigmf-meta"
        (tmp_path / f"nf{i}.sigmf-data").write_bytes(b"\x00" * 8)
        meta_path.write_text(
            '{"global": {"core:datatype": "cf32_le", "core:sample_rate": '
            + literal
            + ', "core:num_samples": 1}, "captures": [{"core:sample_start": 0}],'
            ' "annotations": []}',
            encoding="utf-8",
        )
        with pytest.raises(BackendError):
            read_sigmf_timeline(str(meta_path))


def test_backend_error_single_source_identity():
    # 对抗：本模块导出的 BackendError 与注册表侧为同一类（单一事实源）——
    # issubclass 同源成立，注册表调用方 except BackendError 能接住回放文件错误
    from src.manage_backend_registry.register_backend import BackendError as RegistryError

    assert BackendError is RegistryError
    assert issubclass(BackendError, RegistryError)
