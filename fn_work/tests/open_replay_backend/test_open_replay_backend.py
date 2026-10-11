"""open_replay_backend 对抗单测（slug=backend_replay 的 replay 回放后端顶层）。"""
import json
import struct

import pytest

from src.open_replay_backend.open_replay_backend import (
    ReplayBackend,
    open_replay_backend,
)
from src.open_replay_backend.read_sigmf_timeline import BackendError


def _write_pair(
    tmp_path,
    *,
    num_samples,
    samples_bytes,
    annotations=None,
    name="rec",
    sample_rate=2_000_000,
    meta_text=None,
):
    """写一对 .sigmf-meta/.sigmf-data，返回 meta 路径 str；meta_text 非空时原样写入。"""
    if meta_text is None:
        meta = {
            "global": {
                "core:datatype": "cf32_le",
                "core:sample_rate": sample_rate,
                "core:version": "1.2.0",
                "core:num_samples": num_samples,
            },
            "captures": [{"core:sample_start": 0}],
            "annotations": annotations if annotations is not None else [],
        }
        meta_text = json.dumps(meta)
    meta_path = tmp_path / f"{name}.sigmf-meta"
    data_path = tmp_path / f"{name}.sigmf-data"
    meta_path.write_text(meta_text, encoding="utf-8")
    data_path.write_bytes(samples_bytes)
    return str(meta_path)


def _cf32_bytes(*iq_pairs):
    return struct.pack("<" + "2f" * len(iq_pairs), *[v for pair in iq_pairs for v in pair])


def test_backend_replay_read_samples_roundtrip_exact_values(tmp_path):
    meta = _write_pair(
        tmp_path,
        num_samples=3,
        samples_bytes=_cf32_bytes((1.5, -2.25), (0.0, 0.5), (-3.0, 4.0)),
    )
    backend = open_replay_backend(meta)
    assert isinstance(backend, ReplayBackend)
    block = backend.read_samples()
    assert block["samples"] == [complex(1.5, -2.25), 0.5j, complex(-3.0, 4.0)]
    assert block["sample_start"] == 0
    assert block["time_s"] == 0.0


def test_backend_replay_multi_block_sequential_reads(tmp_path):
    # 100 样本、block 64 → 64+36 两块，逐次弹出且保序
    vals = [(float(i), -float(i)) for i in range(100)]
    data = struct.pack("<" + "2f" * 100, *[v for pair in vals for v in pair])
    meta = _write_pair(tmp_path, num_samples=100, samples_bytes=data)
    backend = open_replay_backend(meta, block_size=64)
    b0 = backend.read_samples()
    b1 = backend.read_samples()
    assert [len(b["samples"]) for b in (b0, b1)] == [64, 36]
    assert b1["sample_start"] == 64
    assert b1["samples"][0] == complex(64.0, -64.0)


def test_backend_replay_exhausted_returns_empty_list_stably(tmp_path):
    meta = _write_pair(tmp_path, num_samples=1, samples_bytes=_cf32_bytes((1.0, 1.0)))
    backend = open_replay_backend(meta)
    assert len(backend.read_samples()["samples"]) == 1
    assert backend.read_samples() == []
    assert backend.read_samples() == []  # 一次性流不循环：耗尽后恒 []


def test_backend_replay_empty_recording_yields_empty_immediately(tmp_path):
    meta = _write_pair(tmp_path, num_samples=0, samples_bytes=b"")
    backend = open_replay_backend(meta)
    assert backend.read_samples() == []


def test_backend_replay_stop_tx_and_set_tx_gain_return_no_tx(tmp_path):
    meta = _write_pair(tmp_path, num_samples=1, samples_bytes=_cf32_bytes((1.0, 1.0)))
    backend = open_replay_backend(meta)
    assert backend.stop_tx() == {"status": "no_tx"}
    assert backend.set_tx_gain(30.0) == {"status": "no_tx"}
    # 调用记录 'replay 无发射能力' 事件（不抛）
    assert backend.events == ["replay 无发射能力", "replay 无发射能力"]


def test_backend_replay_start_tx_raises_backend_error(tmp_path):
    meta = _write_pair(tmp_path, num_samples=1, samples_bytes=_cf32_bytes((1.0, 1.0)))
    backend = open_replay_backend(meta)
    with pytest.raises(BackendError, match="replay 后端无发射能力"):
        backend.start_tx(samples=[1.0 + 1.0j], center_freq=2.4e9)


def test_backend_replay_speed_recorded_in_capabilities(tmp_path):
    meta = _write_pair(tmp_path, num_samples=1, samples_bytes=_cf32_bytes((1.0, 1.0)))
    caps = open_replay_backend(meta, speed=2.5).capabilities()
    assert caps["speed"] == 2.5
    assert caps["name"] == "replay"
    assert caps["tx"] is False
    assert caps["sigmf_path"] == meta
    # 边界 speed=0.1 恰好接受
    assert open_replay_backend(meta, speed=0.1).capabilities()["speed"] == 0.1


def test_backend_replay_capabilities_shape(tmp_path):
    meta = _write_pair(tmp_path, num_samples=1, samples_bytes=_cf32_bytes((1.0, 1.0)))
    backend = open_replay_backend(meta, speed=2.0, block_size=1024)
    caps = backend.capabilities()
    assert caps["name"] == "replay"
    assert caps["tx"] is False
    assert caps["speed"] == 2.0
    assert caps["block_size"] == 1024


def test_backend_replay_speed_below_min_rejected(tmp_path):
    meta = _write_pair(tmp_path, num_samples=1, samples_bytes=_cf32_bytes((1.0, 1.0)))
    for bad in (0.05, 0.0, -1.0):
        with pytest.raises(ValueError):
            open_replay_backend(meta, speed=bad)
    # speed 校验先于文件打开：路径不存在 + speed=0.05 仍是 ValueError 而非 BackendError
    with pytest.raises(ValueError):
        open_replay_backend(str(tmp_path / "nope.sigmf-meta"), speed=0.05)


def test_backend_replay_bad_meta_raises_at_open_not_deferred(tmp_path):
    meta = _write_pair(
        tmp_path,
        num_samples=1,
        samples_bytes=_cf32_bytes((1.0, 1.0)),
        meta_text="{not json!!",
        name="broken",
    )
    with pytest.raises(BackendError):
        open_replay_backend(meta)  # 打开即抛，无需调 read_samples
    # 数据截断（声明 1000 实际 1 样本）同样在 open 时抛
    meta2 = _write_pair(
        tmp_path, num_samples=1000, samples_bytes=_cf32_bytes((1.0, 1.0)), name="short"
    )
    with pytest.raises(BackendError):
        open_replay_backend(meta2)


def test_backend_replay_block_size_passthrough_exact_two_blocks(tmp_path):
    n, block = 131072, 65536
    data = struct.pack("<2f", 1.0, 0.0) * n
    meta = _write_pair(tmp_path, sample_rate=1_000_000, num_samples=n, samples_bytes=data)
    backend = open_replay_backend(meta, block_size=block)
    b0 = backend.read_samples()
    b1 = backend.read_samples()
    assert [b["sample_start"] for b in (b0, b1)] == [0, 65536]
    assert [len(b["samples"]) for b in (b0, b1)] == [65536, 65536]
    assert all(s == 1.0 + 0.0j for s in b0["samples"] + b1["samples"])
    assert b1["time_s"] == 65536 / 1_000_000
    assert backend.read_samples() == []  # 恰 2 块，无第三块


def test_backend_replay_annotations_passthrough_in_block_meta(tmp_path):
    ann_b0 = {
        "core:sample_start": 0,
        "core:sample_count": 4,
        "core:description": "style: noise",
        "power_dbm": -60,
    }
    ann_b1 = {"core:sample_start": 70, "core:sample_count": 10,
              "core:description": "style: pulse"}
    vals = [(float(i), -float(i)) for i in range(128)]
    data = struct.pack("<" + "2f" * 128, *[v for pair in vals for v in pair])
    meta = _write_pair(
        tmp_path, num_samples=128, samples_bytes=data, annotations=[ann_b0, ann_b1]
    )
    backend = open_replay_backend(meta, block_size=64)
    b0 = backend.read_samples()
    b1 = backend.read_samples()
    assert b0["annotations"] == [ann_b0]
    assert b1["annotations"] == [ann_b1]


def test_backend_replay_speed_wallclock_annotation_without_sleep(tmp_path):
    meta = _write_pair(
        tmp_path,
        sample_rate=1000,
        num_samples=2,
        samples_bytes=_cf32_bytes((1.0, 0.0), (0.0, 1.0)),
    )
    fast = open_replay_backend(meta, speed=4.0, block_size=1)
    b0 = fast.read_samples()
    b1 = fast.read_samples()
    # 倍速不改录制时间轴 time_s，只改 wallclock 语义标注；块产出即出不 sleep
    assert b0["time_s"] == 0.0
    assert b1["time_s"] == 1 / 1000
    assert b0["wallclock_s"] == 0.0
    assert b1["wallclock_s"] == (1 / 1000) / 4.0


def test_backend_replay_registered_in_registry_lookup_and_instantiate(tmp_path):
    # 集成: import open_sim_backend 与 open_replay_backend 两模块后，lookup('replay')
    # 可取回自注册工厂（import 期 override=True 幂等），并按注册表惯例（单 params dict）
    # 实例化出可读的 ReplayBackend
    import src.open_sim_backend.open_sim_backend  # noqa: F401 —— 两后端共存注册互不干扰
    from src.manage_backend_registry.lookup_backend import lookup_backend

    factory, meta = lookup_backend("replay")
    assert callable(factory)
    assert meta["kind"] == "replay"
    assert meta["caps"] == {"tx": False, "rx": True}
    assert set(meta["params"]) == {"sigmf_path", "speed", "block_size"}  # 参数形状已注明
    meta_path = _write_pair(
        tmp_path, num_samples=2, samples_bytes=_cf32_bytes((1.0, 0.0), (0.0, 1.0))
    )
    inst = factory({"sigmf_path": meta_path, "speed": 2.0, "block_size": 1})
    assert isinstance(inst, ReplayBackend)
    b0, b1 = inst.read_samples(), inst.read_samples()
    assert b0["samples"] == [1.0 + 0j] and b0["wallclock_s"] == 0.0
    assert b1["wallclock_s"] == (1 / 2_000_000) / 2.0  # speed=2 透传生效
    # speed/block_size 可缺省（按 meta['params'] 注明的缺省值）
    inst2 = factory({"sigmf_path": meta_path})
    caps = inst2.capabilities()
    assert caps["speed"] == 1.0 and caps["block_size"] == 65536


def test_backend_replay_speed_non_finite_or_bool_rejected(tmp_path):
    # 对抗：speed=inf/-inf/NaN/bool 一律 ValueError（与 sim 侧数值口径一致），
    # 且校验先于文件打开（路径不存在 + speed=inf 仍是 ValueError 非 BackendError）
    meta = _write_pair(tmp_path, num_samples=1, samples_bytes=_cf32_bytes((1.0, 1.0)))
    for bad in (float("inf"), float("-inf"), float("nan"), True, False):
        with pytest.raises(ValueError):
            open_replay_backend(meta, speed=bad)
    with pytest.raises(ValueError):
        open_replay_backend(str(tmp_path / "nope.sigmf-meta"), speed=float("inf"))


def test_backend_replay_error_registry_side_except_catches(tmp_path):
    # 对抗：BackendError 单源——模块侧与注册表侧同一类；注册表侧 except 能接住
    # replay 文件错误（文件缺失），issubclass 同源成立
    from src.manage_backend_registry.register_backend import BackendError as RegistryError
    from src.open_replay_backend.open_replay_backend import BackendError as ReplayError

    assert ReplayError is RegistryError
    assert issubclass(ReplayError, RegistryError)
    missing = str(tmp_path / "missing.sigmf-meta")
    with pytest.raises(RegistryError):
        open_replay_backend(missing)  # 注册表调用方用同一 except 即可接住
