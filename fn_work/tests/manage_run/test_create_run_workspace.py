"""create_run_workspace 对抗测试：八件套/表头/同秒去重/自动建根/文件根/中文副本/磁盘预检/只读根。"""
from __future__ import annotations

import collections
import os
from datetime import datetime
from pathlib import Path

import pytest

import src.manage_run.create_run_workspace as crw
from src.manage_run.create_run_workspace import (
    KPI_CSV_HEADER,
    MONITOR_CSV_HEADER,
    RunDirError,
    create_run_workspace,
)

FIXED_NOW = datetime(2026, 10, 11, 12, 34, 56)
FIXED_STAMP = "20261011-123456"

SCENARIO = {
    "name": "实验室台架-辐射发射",
    "notes": '含"双引号"与\'单引号\'',
    "multiline": "第一行\n第二行\n\t制表缩进",
    "count": 3,
    "ratio": 0.125,
    "enabled": True,
    "comment": None,
    "tags": ["中文标签", "带\"引号", "行1\n行2"],
    "items": [{"a": 1, "b": "x"}, {"a": 2}],
    "nested": {"child": {"deep": [1, 2.5, None, False]}, "empty_dict": {}, "empty_list": []},
}

FILE_PIECES = {"scenario.yaml", "kpi.csv", "events.jsonl", "monitor.csv", "report.md", "run.log"}
DIR_PIECES = {"recordings", "plots"}


def test_eight_pieces_all_exist(tmp_path):
    result = create_run_workspace(str(tmp_path), SCENARIO)

    run_dir = Path(result["run_dir"])
    assert os.path.isabs(result["run_dir"])
    assert run_dir.is_dir()
    assert run_dir.parent == tmp_path
    assert result["files"] == list(crw.WORKSPACE_FILES)
    assert set(result["files"]) == FILE_PIECES | DIR_PIECES
    for name in FILE_PIECES:
        assert (run_dir / name).is_file(), name
    for name in DIR_PIECES:
        assert (run_dir / name).is_dir(), name
    assert (run_dir / "report.md").read_text(encoding="utf-8").splitlines()[0] == crw.REPORT_TITLE


def test_csv_headers_exact(tmp_path):
    result = create_run_workspace(str(tmp_path), {"a": 1})
    run_dir = Path(result["run_dir"])
    assert (run_dir / "kpi.csv").read_text(encoding="utf-8") == KPI_CSV_HEADER + "\n"
    assert (run_dir / "monitor.csv").read_text(encoding="utf-8") == MONITOR_CSV_HEADER + "\n"


def test_empty_streams_created(tmp_path):
    result = create_run_workspace(str(tmp_path), {})
    run_dir = Path(result["run_dir"])
    assert (run_dir / "events.jsonl").read_text(encoding="utf-8") == ""
    assert (run_dir / "run.log").read_text(encoding="utf-8") == ""
    assert (run_dir / "events.jsonl").stat().st_size == 0


def test_same_second_suffix_dedup(tmp_path, monkeypatch):
    monkeypatch.setattr(crw, "_now", lambda: FIXED_NOW)
    results = [create_run_workspace(str(tmp_path), SCENARIO) for _ in range(3)]
    names = sorted(Path(r["run_dir"]).name for r in results)
    assert names == [FIXED_STAMP, f"{FIXED_STAMP}-2", f"{FIXED_STAMP}-3"]
    assert len({r["run_dir"] for r in results}) == 3
    for r in results:
        assert Path(r["run_dir"]).is_dir()


def test_runs_root_autocreated(tmp_path):
    deep = tmp_path / "a" / "b" / "runs"
    result = create_run_workspace(str(deep), {"k": "v"})
    assert deep.is_dir()
    assert Path(result["run_dir"]).parent == deep


def test_runs_root_is_file_rejected(tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.write_text("not a dir", encoding="utf-8")
    with pytest.raises(RunDirError):
        create_run_workspace(str(runs_root), {"k": "v"})


def test_scenario_yaml_roundtrip_unicode(tmp_path):
    yaml = pytest.importorskip("yaml")
    result = create_run_workspace(str(tmp_path), SCENARIO)
    loaded = yaml.safe_load((Path(result["run_dir"]) / "scenario.yaml").read_text(encoding="utf-8"))
    assert loaded == SCENARIO


def test_fallback_serializer_roundtrip(tmp_path, monkeypatch):
    yaml = pytest.importorskip("yaml")
    monkeypatch.setattr(crw, "_yaml_mod", None)  # 强制手写序列化器路径
    result = create_run_workspace(str(tmp_path), SCENARIO)
    text = (Path(result["run_dir"]) / "scenario.yaml").read_text(encoding="utf-8")
    assert yaml.safe_load(text) == SCENARIO
    assert crw._fallback_dump_yaml(SCENARIO) == text


def test_disk_space_precheck_rejects(tmp_path, monkeypatch):
    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(crw.shutil, "disk_usage", lambda _p: usage(10**9, 10**9, 50 * 1024 * 1024))
    with pytest.raises(RunDirError, match="空间不足"):
        create_run_workspace(str(tmp_path), {"k": "v"})
    assert list(tmp_path.iterdir()) == []  # 预检先于任何落盘


@pytest.mark.skipif(os.geteuid() == 0, reason="root 无视权限位")
def test_readonly_runs_root_rejected(tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    os.chmod(runs_root, 0o444)
    try:
        with pytest.raises(RunDirError):
            create_run_workspace(str(runs_root), {"k": "v"})
        assert list(runs_root.iterdir()) == []
    finally:
        os.chmod(runs_root, 0o755)


def test_fallback_serializer_unsupported_key_type_rolls_back(tmp_path, monkeypatch):
    """回退序列化器遇 bytes 键（PyYAML 缺失路径）→ RunDirError（含类型名）；
    已建 run_dir 回滚清除，runs/ 下不留残骸。"""
    monkeypatch.setattr(crw, "_yaml_mod", None)  # 强制手写序列化器路径
    runs_root = tmp_path / "runs"
    with pytest.raises(RunDirError, match="bytes"):
        create_run_workspace(str(runs_root), {b"raw": 1})
    assert not runs_root.exists() or list(runs_root.iterdir()) == []  # 无残留


def test_fallback_serializer_unsupported_value_type_rolls_back(tmp_path, monkeypatch):
    """回退序列化器遇 datetime 值 → RunDirError（含类型名），run_dir 同样回滚。"""
    monkeypatch.setattr(crw, "_yaml_mod", None)
    runs_root = tmp_path / "runs"
    with pytest.raises(RunDirError, match="datetime"):
        create_run_workspace(str(runs_root), {"when": FIXED_NOW})
    assert not runs_root.exists() or list(runs_root.iterdir()) == []
