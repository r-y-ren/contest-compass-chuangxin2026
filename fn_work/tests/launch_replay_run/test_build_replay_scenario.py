"""build_replay_scenario 单测（R64 L1）：录音条目→replay 场景组装契约/声明缺失拒/
损坏拒。

组装契约（被测实现口径，详见 src/launch_replay_run/build_replay_scenario.py
模块 docstring）：backend='replay'+sigmf_path+speed+沿用来源场景（source_scenario
显式 > run_dir 场景副本）的频段/安全声明/样式参数；红线（shielded_box 严格 True、
dut_scope 仅 'self_built'）不因回放松动——缺失/值不符/文件不可读→ScenarioError。
"""
import os

import pytest

from src.launch_replay_run.build_replay_scenario import (
    DEFAULT_REPLAY_SPEED,
    ScenarioError,
    build_replay_scenario,
)

#: 声明齐全的规范化来源场景（场景副本形状）。
_SOURCE_SCENARIO = {
    "style": "tone",
    "fs": 1.0e6,
    "freq_hz": 2.4e9,
    "power_dbm": -10.0,
    "duration_s": 0.005,
    "backend": "sim",
    "scenario_type": "gb42590",
    "bands": [[2400.0, 2483.5]],
    "shielded_box": True,
    "dut_scope": "self_built",
}


def _make_recording(tmp_path, name="20260101-120000", *, scenario=None):
    """造真录音条目素材：runs/<name>/{scenario.yaml, recordings/<name>.sigmf-*}。

    返回 (run_dir, meta_path)——scenario=None 时不落场景副本。
    """
    run_dir = tmp_path / "runs" / name
    recordings = run_dir / "recordings"
    recordings.mkdir(parents=True)
    if scenario is not None:
        import yaml

        (run_dir / "scenario.yaml").write_text(
            yaml.safe_dump(scenario), encoding="utf-8"
        )
    meta = recordings / f"{name}.sigmf-meta"
    meta.write_text("{}", encoding="utf-8")
    (recordings / f"{name}.sigmf-data").write_bytes(b"\x00" * 16)
    return str(run_dir), str(meta)


# ---- 组装契约 ----


def test_build_replay_scenario_from_run_dir_copy(tmp_path):
    """条目 {'run_id','path'}→从场景副本沿用频段/安全声明/样式参数；sigmf_path
    从 recordings 目录解析最早 meta；speed 缺省 1.0；scenario_type='custom'。"""
    run_dir, meta = _make_recording(tmp_path, scenario=dict(_SOURCE_SCENARIO))
    entry = {
        "run_id": "20260101-120000",
        "path": os.path.join(run_dir, "recordings"),
    }
    scenario = build_replay_scenario(entry)
    assert scenario["backend"] == "replay"
    assert scenario["sigmf_path"] == meta
    assert scenario["speed"] == DEFAULT_REPLAY_SPEED
    assert scenario["style"] == "tone"
    assert scenario["fs"] == 1.0e6
    assert scenario["freq_hz"] == 2.4e9
    assert scenario["power_dbm"] == -10.0
    assert scenario["duration_s"] == 0.005
    assert scenario["bands"] == [[2400.0, 2483.5]]  # 频段沿用
    assert scenario["shielded_box"] is True  # 安全声明沿用
    assert scenario["dut_scope"] == "self_built"
    assert scenario["scenario_type"] == "custom"  # 回放编排缺省
    assert scenario["record"] is False
    assert "sim_events" not in scenario  # 来源场景执行信封不混入回放组装


def test_build_replay_scenario_explicit_sigmf_path_and_source_scenario(tmp_path):
    """显式 sigmf_path+source_scenario 直给（浏览卡片/上游携带）优先于目录解析。"""
    run_dir, meta = _make_recording(tmp_path, scenario=None)  # 无副本——逼显式源
    entry = {
        "run_id": "20260101-120000",
        "sigmf_path": meta,
        "source_scenario": dict(_SOURCE_SCENARIO, style="chirp"),
        "speed": 2.0,
    }
    scenario = build_replay_scenario(entry)
    assert scenario["sigmf_path"] == meta
    assert scenario["style"] == "chirp"  # 显式来源场景真值
    assert scenario["speed"] == 2.0  # 倍速透传（域校验归 open_replay_backend）
    assert scenario["shielded_box"] is True and scenario["dut_scope"] == "self_built"


def test_build_replay_scenario_run_dir_explicit_key(tmp_path):
    """'run_dir' 显式键定位场景副本（path 缺失时的来源运行目录口径）。"""
    run_dir, meta = _make_recording(tmp_path, scenario=dict(_SOURCE_SCENARIO))
    entry = {"run_id": "20260101-120000", "run_dir": run_dir, "sigmf_path": meta}
    scenario = build_replay_scenario(entry)
    assert scenario["style"] == "tone"  # 副本经 run_dir 读到


# ---- 声明缺失拒（红线不因回放松动） ----


def test_build_replay_scenario_missing_declarations_rejected(tmp_path):
    """来源场景缺 shielded_box/dut_scope→ScenarioError 逐条指明（红线）。"""
    broken = {k: v for k, v in _SOURCE_SCENARIO.items()
              if k not in ("shielded_box", "dut_scope")}
    run_dir, meta = _make_recording(tmp_path, scenario=broken)
    entry = {"run_id": "r", "sigmf_path": meta, "run_dir": run_dir}
    with pytest.raises(ScenarioError, match="红线"):
        build_replay_scenario(entry)


def test_build_replay_scenario_dut_scope_wrong_value_rejected(tmp_path):
    """dut_scope='vendor'（非 self_built）→ScenarioError（真机声明红线）。"""
    wrong = dict(_SOURCE_SCENARIO, dut_scope="vendor")
    run_dir, meta = _make_recording(tmp_path, scenario=wrong)
    entry = {"run_id": "r", "sigmf_path": meta, "run_dir": run_dir}
    with pytest.raises(ScenarioError, match="dut_scope"):
        build_replay_scenario(entry)


def test_build_replay_scenario_shielded_box_false_rejected(tmp_path):
    """shielded_box=False→ScenarioError（必须严格 True）。"""
    wrong = dict(_SOURCE_SCENARIO, shielded_box=False)
    run_dir, meta = _make_recording(tmp_path, scenario=wrong)
    entry = {"run_id": "r", "sigmf_path": meta, "run_dir": run_dir}
    with pytest.raises(ScenarioError, match="shielded_box"):
        build_replay_scenario(entry)


def test_build_replay_scenario_no_source_scenario_rejected(tmp_path):
    """来源场景两路皆缺（无 source_scenario 且目录无副本）→ScenarioError 指明。"""
    run_dir, meta = _make_recording(tmp_path, scenario=None)
    entry = {"run_id": "r", "sigmf_path": meta, "run_dir": run_dir}
    with pytest.raises(ScenarioError, match="来源场景不可得"):
        build_replay_scenario(entry)


# ---- 损坏拒（文件不可读） ----


def test_build_replay_scenario_missing_meta_file_rejected(tmp_path):
    """sigmf_path 指向不存在文件→ScenarioError 指明路径。"""
    entry = {
        "run_id": "r",
        "sigmf_path": str(tmp_path / "nowhere.sigmf-meta"),
        "source_scenario": dict(_SOURCE_SCENARIO),
    }
    with pytest.raises(ScenarioError, match="不可读"):
        build_replay_scenario(entry)


def test_build_replay_scenario_data_pair_missing_rejected(tmp_path):
    """.sigmf-data 与 meta 不成对→ScenarioError（真值对不完整不可回放）。"""
    run_dir = tmp_path / "runs" / "r"
    recordings = run_dir / "recordings"
    recordings.mkdir(parents=True)
    (recordings / "r.sigmf-meta").write_text("{}", encoding="utf-8")  # 仅 meta
    entry = {
        "run_id": "r",
        "sigmf_path": str(recordings / "r.sigmf-meta"),
        "source_scenario": dict(_SOURCE_SCENARIO),
    }
    with pytest.raises(ScenarioError, match="sigmf-data"):
        build_replay_scenario(entry)


def test_build_replay_scenario_no_sigmf_resolvable_rejected(tmp_path):
    """无 sigmf_path 且 recordings 目录无 *.sigmf-meta→ScenarioError（定位失败）。"""
    run_dir = tmp_path / "runs" / "r"
    (run_dir / "recordings").mkdir(parents=True)
    (run_dir / "scenario.yaml").write_text("style: tone\n", encoding="utf-8")
    entry = {"run_id": "r", "path": os.path.join(str(run_dir), "recordings")}
    with pytest.raises(ScenarioError, match="录音定位失败"):
        build_replay_scenario(entry)


# ---- 形状与必字段 ----


def test_build_replay_scenario_entry_not_dict_rejected():
    """entry 非 dict→ScenarioError（契约指错）。"""
    with pytest.raises(ScenarioError, match="dict"):
        build_replay_scenario(["not", "a", "dict"])


def test_build_replay_scenario_missing_style_or_fs_rejected(tmp_path):
    """来源场景缺 style/fs（组装必需字段）→ScenarioError 指明。"""
    run_dir, meta = _make_recording(tmp_path, scenario=dict(_SOURCE_SCENARIO))
    entry = {"run_id": "r", "sigmf_path": meta, "run_dir": run_dir}
    no_style = dict(_SOURCE_SCENARIO)
    del no_style["style"]
    with pytest.raises(ScenarioError, match="style"):
        build_replay_scenario({**entry, "source_scenario": no_style})
    no_fs = dict(_SOURCE_SCENARIO)
    del no_fs["fs"]
    with pytest.raises(ScenarioError, match="fs"):
        build_replay_scenario({**entry, "source_scenario": no_fs})
