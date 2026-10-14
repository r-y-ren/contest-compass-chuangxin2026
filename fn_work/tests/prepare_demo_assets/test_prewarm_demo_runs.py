"""prewarm_demo_runs 对抗用例：R76 L1 预跑历史运行（slug=demo_assets 预跑叶）。

真实路径（sim 全流程，单轮 ~2 秒）：①运行目录生成且 result.json 存在；
②exit 1（国标测法测到失效=核心产出）如实登记不算失败；③非法场景（exit 2
口径）→ 意外失败路径中止且已跑清单非空（真实坏 YAML 文件，非 mock）；
④runs 条目数=场景数×轮次；外加 rounds 域拒与 scenario_dir=None 直传路径名。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.load_scenario.load_scenario import ScenarioError
from src.prepare_demo_assets.prewarm_demo_runs import (
    PrewarmDemoRunError,
    prewarm_demo_runs,
)

#: 冒烟场景（判据恒不触发 → exit 0）：最小合法 tone 场景，dwell 0 快路径，
#: sim 事件缺省生成（jsr=-20 悬崖左远端，窗 PER 恒 0 < 阈值 0.1）。
_SMOKE_YAML = """\
style: tone
fs: 1000000
freq_hz: 2400000000
power_dbm: -10
duration_s: 0.005
backend: sim
scenario_type: gb42590
judge_per_threshold: 0.1
judge_min_samples: 2
dwell_s: 0.0
baseline_samples: 10
bands:
  - [2400, 2483.5]
shielded_box: true
dut_scope: self_built
"""

#: 失效演示场景（--demo 同款判据爬升 → exit 1）：sim 事件按 GB 阶梯档位携带
#: 绝对干扰电平（achieved_db），signal_power_db=-20 → JSR 随档爬升，中段档
#: （-15dBm，jsr=+5）窗 PER 恰达阈值 0.1 → 判据触发 → exit 1（核心产出）。
_FAIL_YAML = """\
style: tone
fs: 1000000
freq_hz: 2400000000
power_dbm: -10
duration_s: 0.005
backend: sim
judge_per_threshold: 0.1
scenario_type: gb42590
judge_min_samples: 2
dwell_s: 0.0
baseline_samples: 10
signal_power_db: -20
link_power_db: -20
dut: {source: sim, samples_per_event: 2}
sim_events:
  - {type: power_step, achieved_db: -25.0, ts: 0.0}
  - {type: power_step, achieved_db: -20.0, ts: 1.0}
  - {type: power_step, achieved_db: -15.0, ts: 2.0}
  - {type: power_step, achieved_db: -10.0, ts: 3.0}
  - {type: power_step, achieved_db: -5.0, ts: 4.0}
  - {type: power_step, achieved_db: 0.0, ts: 5.0}
bands:
  - [2400, 2483.5]
shielded_box: true
dut_scope: self_built
"""

#: 非法场景（YAML 未闭合流序列 → 装载失败 = CLI exit 2 场景写错口径）。
_BROKEN_YAML = "style: tone\nfs: [1, 2\n"


def _seed(scenario_dir: Path, files: dict) -> None:
    """把场景文件写入目录（模拟 seed_preset_scenarios 的落盘产物）。"""
    for name, text in files.items():
        (scenario_dir / name).write_text(text, encoding="utf-8")


def test_prewarm_smoke_run_dir_and_result_json(tmp_path):
    # ① 单场景单轮：运行目录在 runs_root 下生成、result.json 存在且可解析。
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    _seed(scenario_dir, {"smoke.yaml": _SMOKE_YAML})
    runs_root = tmp_path / "runs"

    report = prewarm_demo_runs(
        ["smoke.yaml"], runs_root, rounds=1, scenario_dir=scenario_dir
    )

    runs = report["runs"]
    assert len(runs) == 1
    run_dir, code = runs[0]
    assert code == 0  # 冒烟零失效：跑完未失效
    assert isinstance(run_dir, str) and run_dir
    run_path = Path(run_dir)
    assert run_path.is_dir()
    assert run_path.parent == runs_root.resolve()  # 落点=runs_root（落点口径）
    result_path = run_path / "result.json"
    assert result_path.is_file()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)  # 可翻阅的结构化留痕（操控台/录音库数据源）


def test_prewarm_exit1_failure_registered_not_raised(tmp_path):
    # ② --demo 口径：exit 1=国标测法测到失效=核心产出——如实登记，不抛不中止。
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    _seed(scenario_dir, {"fail.yaml": _FAIL_YAML})

    report = prewarm_demo_runs(
        ["fail.yaml"], tmp_path / "runs", rounds=1, scenario_dir=scenario_dir
    )

    runs = report["runs"]
    assert len(runs) == 1
    run_dir, code = runs[0]
    assert code == 1  # 测到失效：预期产出，登记在册
    assert isinstance(run_dir, str) and Path(run_dir).is_dir()
    assert (Path(run_dir) / "result.json").is_file()  # 失效运行同样完整留痕


def test_prewarm_exit2_aborts_with_already_run_list(tmp_path):
    # ③ 场景=[好, 坏]：坏场景装载失败（exit 2 口径）→ PrewarmDemoRunError 即时
    # 中止，已跑清单恰为好场景那 1 轮（非空），runs_root 不再新增运行目录。
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    _seed(scenario_dir, {"smoke.yaml": _SMOKE_YAML, "broken.yaml": _BROKEN_YAML})
    runs_root = tmp_path / "runs"

    with pytest.raises(PrewarmDemoRunError) as ei:
        prewarm_demo_runs(
            ["smoke.yaml", "broken.yaml"], runs_root, rounds=1, scenario_dir=scenario_dir
        )

    err = ei.value
    assert err.exit_code == 2  # 场景写错口径
    assert err.scenario == "broken.yaml"
    assert len(err.runs) == 1  # 已跑清单非空：好场景那轮在册
    assert err.runs[0][1] == 0
    assert "smoke.yaml" in str(err) and "broken.yaml" in str(err)  # 消息列明场景与清单
    assert isinstance(err.__cause__, ScenarioError)  # 不吞错：装载异常链保留
    subdirs = [p for p in runs_root.iterdir() if p.is_dir()]
    assert len(subdirs) == 1  # 中止后无新轮落盘


def test_prewarm_runs_count_equals_scenarios_times_rounds(tmp_path):
    # ④ 条目数=场景数×轮次（2×2=4，运行目录互异——同秒冲突由 manage_run 去重）；
    # 本用例走 scenario_dir=None 路线（绝对路径名直传），覆盖另一解析分支。
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    _seed(scenario_dir, {"a.yaml": _SMOKE_YAML, "b.yaml": _SMOKE_YAML})
    names = [str(scenario_dir / "a.yaml"), str(scenario_dir / "b.yaml")]

    report = prewarm_demo_runs(names, tmp_path / "runs", rounds=2)

    runs = report["runs"]
    assert len(runs) == 2 * 2
    dirs = [Path(d) for d, _ in runs]
    assert all(d.is_dir() for d in dirs)
    assert len({str(d) for d in dirs}) == 4  # 每轮独立运行目录
    assert all(code == 0 for _, code in runs)


def test_prewarm_rounds_domain_rejected(tmp_path):
    # rounds<1 属配置编程错：ValueError 早暴露（不进任何运行）。
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    _seed(scenario_dir, {"smoke.yaml": _SMOKE_YAML})
    for bad in (0, -1):
        with pytest.raises(ValueError):
            prewarm_demo_runs(
                ["smoke.yaml"], tmp_path / "runs", rounds=bad, scenario_dir=scenario_dir
            )
    assert not (tmp_path / "runs").exists()  # 域拒在运行前：未建 runs_root
