"""seed_preset_scenarios 单测（R76）：预置 7 场景首写全落且逐个过 load_scenario
装载（硬断言）；幂等重跑全列冲突不覆盖；overwrite=True 授权重写；目标目录
不存在自动创建；目录不可写（chmod 0o500）→PermissionError 上抛（root 跳过）。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.load_scenario.load_scenario import load_scenario
from src.prepare_demo_assets.seed_preset_scenarios import (
    PRESET_SCENARIOS,
    seed_preset_scenarios,
)

#: 模板集清单一一对应（恰好 7 个——冒烟/失效/距离/录音/多音/EMC/编辑器练手，
#: 与手册总章演示条目同序）。
_EXPECTED_NAMES = [
    "demo_smoke.yaml",
    "demo_failure.yaml",
    "demo_distance.yaml",
    "demo_record.yaml",
    "demo_composite.yaml",
    "demo_emc.yaml",
    "editor_practice.yaml",
]


def test_first_seed_writes_all_and_each_loads(tmp_path: Path):
    """① 临时目录首写：7 文件全落（written 全名/conflicts 空）且逐个能被
    load_scenario 装载通过（schema+红线+规范化全链——硬断言）。"""
    assert list(PRESET_SCENARIOS) == _EXPECTED_NAMES  # 与手册总章清单一一对应
    report = seed_preset_scenarios(tmp_path)
    assert report["written"] == _EXPECTED_NAMES
    assert report["conflicts"] == []
    for name in _EXPECTED_NAMES:
        path = tmp_path / name
        assert path.is_file()
        scenario = load_scenario(str(path))  # 装载不抛即过 schema/红线/规范化
        assert scenario["backend"] == "sim"
        assert scenario["bands"] == [[2400, 2483.5]]
        assert scenario["shielded_box"] is True
        assert scenario["dut_scope"] == "self_built"


def test_first_seed_template_traits(tmp_path: Path):
    """①b 各模板定义性特征装载后保真（判据口径/类型/分量清单/录音开关）。"""
    seed_preset_scenarios(tmp_path)

    def _load(name: str) -> dict:
        return load_scenario(str(tmp_path / name))

    smoke = _load("demo_smoke.yaml")
    assert smoke["style"] == "tone" and smoke["judge_per_threshold"] == 0.999
    failure = _load("demo_failure.yaml")
    assert failure["style"] == "tone" and failure["judge_per_threshold"] == 0.10
    # 失效配方透传（GB 阶梯绝对电平事件——退出码 1 口径的成失败条件）。
    assert failure["scenario_type"] == "gb42590"
    assert len(failure["sim_events"]) == 6
    assert failure["signal_power_db"] == -20 and failure["link_power_db"] == -20
    distance = _load("demo_distance.yaml")
    assert distance["scenario_type"] == "distance"
    assert distance["distances"] == [1, 3, 7]
    assert distance["model_params"] == {"d0_m": 1, "l0_db": 30, "n": 2}
    record = _load("demo_record.yaml")
    assert record["style"] == "sweep" and record["record"] is True
    composite = _load("demo_composite.yaml")
    assert composite["style"] == "composite"
    assert [c["style"] for c in composite["components"]] == ["tone"] * 3
    emc = _load("demo_emc.yaml")
    assert emc["style"] == "bandlimited_noise" and emc["scenario_type"] == "emc"
    assert emc["band"] == "cispr_b" and emc["step_hz"] == 5.0e6
    editor = _load("editor_practice.yaml")
    assert editor["style"] == "bandlimited_noise"
    assert editor["bandwidth_hz"] == 5.0e5 and editor["fs"] == 2.0e6  # 带宽 ≤fs/2


def test_rerun_reports_conflicts_and_keeps_files(tmp_path: Path):
    """② 幂等重跑：7 项全列 conflicts、written 空、文件内容一字不变。"""
    seed_preset_scenarios(tmp_path)
    before = {
        name: (tmp_path / name).read_text(encoding="utf-8")
        for name in _EXPECTED_NAMES
    }
    report = seed_preset_scenarios(tmp_path)
    assert report["written"] == []
    assert report["conflicts"] == _EXPECTED_NAMES
    for name in _EXPECTED_NAMES:
        assert (tmp_path / name).read_text(encoding="utf-8") == before[name]


def test_partial_conflict_only_existing_listed(tmp_path: Path):
    """②b 混合：仅已存在的那 1 个（内容不同）进 conflicts 不覆盖，其余照写。"""
    (tmp_path / "demo_emc.yaml").write_text("style: tone\n", encoding="utf-8")
    report = seed_preset_scenarios(tmp_path)
    assert report["conflicts"] == ["demo_emc.yaml"]
    assert report["written"] == [n for n in _EXPECTED_NAMES if n != "demo_emc.yaml"]
    # 冲突项保持原内容（未被模板覆盖）。
    assert (tmp_path / "demo_emc.yaml").read_text(encoding="utf-8") == "style: tone\n"


def test_overwrite_true_rewrites(tmp_path: Path):
    """③ overwrite=True：已存在文件全部重写成功（written 满/conflicts 空，
    被改过的文件恢复为模板原文）。"""
    seed_preset_scenarios(tmp_path)
    (tmp_path / "demo_smoke.yaml").write_text("改过的内容\n", encoding="utf-8")
    report = seed_preset_scenarios(tmp_path, overwrite=True)
    assert report["written"] == _EXPECTED_NAMES
    assert report["conflicts"] == []
    assert (
        (tmp_path / "demo_smoke.yaml").read_text(encoding="utf-8")
        == PRESET_SCENARIOS["demo_smoke.yaml"]
    )


def test_missing_target_dir_created(tmp_path: Path):
    """④ 目标目录不存在：自动创建（含父目录）后 7 文件落位。"""
    target = tmp_path / "nested" / "scenarios"
    report = seed_preset_scenarios(target)
    assert report["written"] == _EXPECTED_NAMES
    assert report["conflicts"] == []
    assert all((target / name).is_file() for name in _EXPECTED_NAMES)


@pytest.mark.skipif(
    os.geteuid() == 0, reason="root 权限下 chmod 0o500 不构成写保护"
)
def test_unwritable_dir_raises(tmp_path: Path):
    """⑤ 目录不可写（chmod 0o500）→PermissionError 上抛（不吞错、不落盘）。"""
    target = tmp_path / "scenarios"
    target.mkdir()
    os.chmod(target, 0o500)
    try:
        with pytest.raises(PermissionError):
            seed_preset_scenarios(target)
        assert list(target.iterdir()) == []  # 早拒：未写入任何文件
    finally:
        os.chmod(target, 0o700)  # 还原权限便于清理
