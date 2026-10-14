"""prepare_demo_assets 对抗用例：R76 L0 演示物料准备编排（slug=demo_assets）。

① 端到端（临时目录，rounds=1，预跑场景集=权威三场景不收缩）：报告八键齐、
7 场景全写、prewarm_runs 3 条（exit∈{0,1} 且含 1=失效核心产出）、两档检查单
齐、env 四键；② 幂等拒绝：重跑→refused_conflicts=7、不预跑、文件未被改写；
②b 部分冲突：新场景照写 6、冲突 1 拒绝预跑；③ overwrite=True 重跑授权覆盖
（预跑收缩为 demo_smoke 单场景+rounds=1 控时，断言契约不变——收缩仅减运行
条数，不改动任何断言口径）；④ 预跑意外失败：monkeypatch 同包
prewarm_demo_runs 抛 PrewarmDemoRunError→并入报告不抛（含已跑清单）；
⑤ env 探测容错（uhd 缺工具/探测器崩溃/platformio 子进程异常均不抛、如实
记录）；⑥ 检查单与预跑集权威常量形状（手册总章按名 DEMO_CHECKLIST 引用）。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import src.prepare_demo_assets.prepare_demo_assets as pda
from src.prepare_demo_assets.prepare_demo_assets import (
    DEMO_CHECKLIST,
    prepare_demo_assets,
)
from src.prepare_demo_assets.prewarm_demo_runs import PrewarmDemoRunError
from src.prepare_demo_assets.seed_preset_scenarios import PRESET_SCENARIOS

#: 报告顶层契约（八键）——演示命令直接消费的物料报告形状。
_REPORT_KEYS = {
    "written",
    "conflicts",
    "refused_conflicts",
    "prewarm_runs",
    "prewarm_error",
    "checklist",
    "env",
}
#: 检查单两档键。
_CHECKLIST_TIERS = {"便携档", "全量档"}
#: env 自检四键。
_ENV_KEYS = {"python", "venv_ok", "platformio", "uhd_probe"}


def _assert_env_shape(env: dict) -> None:
    """env 契约断言：四键齐、类型口径正确、uhd_probe 三态取值。"""
    assert set(env) == _ENV_KEYS
    assert isinstance(env["python"], str) and env["python"]
    assert isinstance(env["venv_ok"], bool)
    assert env["platformio"] is None or isinstance(env["platformio"], str)
    assert env["uhd_probe"] in {"在位", "不在位", "未探测"}


def test_end_to_end_full_report(tmp_path: Path):
    # ① 端到端（真实 sim 全流程，预跑集不收缩=权威三场景，rounds=1 控时）：
    # 报告完整、7 场景全写、3 条预跑（exit 语义如实：含 1=测到失效核心产出）、
    # 两档检查单齐、env 四键。
    scenario_dir = tmp_path / "scenarios"
    runs_root = tmp_path / "runs"
    report = prepare_demo_assets(scenario_dir, runs_root, rounds=1)

    assert set(report) == _REPORT_KEYS
    assert report["written"] == list(PRESET_SCENARIOS)  # 7 个预置场景全写
    assert report["conflicts"] == []
    assert report["refused_conflicts"] == []
    assert report["prewarm_error"] is None

    runs = report["prewarm_runs"]
    assert len(runs) == 3  # 三场景 × 1 轮
    codes = [code for _, code in runs]
    assert all(code in {0, 1} for code in codes)  # 0=未失效 / 1=测到失效，均如实登记
    assert codes[0] == 0  # 冒烟基线（判据 0.999）居首且零失效
    assert 1 in codes  # 失效演示场景 exit 1=核心产出，在册不算失败
    for run_dir, code in runs:
        path = Path(run_dir)
        assert path.is_dir()
        assert path.parent == runs_root.resolve()  # 落点=runs_root
        assert (path / "result.json").is_file()  # 操控台/录音库可翻阅的留痕
    assert len([p for p in runs_root.iterdir() if p.is_dir()]) == 3

    assert set(report["checklist"]) == _CHECKLIST_TIERS  # 两档检查单齐
    assert report["checklist"]["便携档"] == DEMO_CHECKLIST["便携档"]
    assert report["checklist"]["全量档"] == DEMO_CHECKLIST["全量档"]
    _assert_env_shape(report["env"])


def test_rerun_refuses_conflicts_and_skips_prewarm(tmp_path: Path):
    # ② 幂等拒绝：重跑同目录（overwrite 缺省 False）→ refused_conflicts=7、
    # 不预跑（prewarm_runs 空）、场景文件一字未改、runs_root 无新目录。
    scenario_dir = tmp_path / "scenarios"
    runs_root = tmp_path / "runs"
    prepare_demo_assets(scenario_dir, runs_root, rounds=1)
    before = {
        name: (scenario_dir / name).read_text(encoding="utf-8")
        for name in PRESET_SCENARIOS
    }
    run_dirs_before = {p.name for p in runs_root.iterdir()}

    report = prepare_demo_assets(scenario_dir, runs_root, rounds=1)

    assert report["written"] == []
    assert report["conflicts"] == list(PRESET_SCENARIOS)
    assert report["refused_conflicts"] == list(PRESET_SCENARIOS)  # 拒绝清单=冲突清单
    assert report["prewarm_runs"] == []  # 拒绝口径：不预跑
    assert report["prewarm_error"] is None  # 未进预跑，不是预跑错误
    assert set(report) == _REPORT_KEYS  # 拒绝报告同样完整可读（友好口径）
    _assert_env_shape(report["env"])
    for name in PRESET_SCENARIOS:
        assert (scenario_dir / name).read_text(encoding="utf-8") == before[name]
    assert {p.name for p in runs_root.iterdir()} == run_dirs_before  # 无新运行目录


def test_partial_conflict_still_seeds_new_and_refuses_prewarm(tmp_path: Path):
    # ②b 部分冲突：1 个已存在（内容不同）→ 其余 6 照写计入 written、
    # refused_conflicts=[该 1 个]、不预跑（不与新场景混跑攒历史）。
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "demo_emc.yaml").write_text("占位旧内容\n", encoding="utf-8")
    runs_root = tmp_path / "runs"

    report = prepare_demo_assets(scenario_dir, runs_root, rounds=1)

    assert report["conflicts"] == ["demo_emc.yaml"]
    assert report["refused_conflicts"] == ["demo_emc.yaml"]
    assert report["written"] == [n for n in PRESET_SCENARIOS if n != "demo_emc.yaml"]
    assert (scenario_dir / "demo_emc.yaml").read_text(encoding="utf-8") == "占位旧内容\n"
    assert report["prewarm_runs"] == []
    assert not runs_root.exists()  # 拒绝预跑：连 runs_root 都未建


def test_overwrite_true_rerun_reseeds_and_prewarms(tmp_path: Path, monkeypatch):
    # ③ overwrite=True 重跑：授权覆盖→written 7、无 refused、预跑照常进行。
    # 控时收缩（申报）：预跑场景集收缩为 demo_smoke 单场景+rounds=1——仅减少
    # 运行条数（1 条），授权覆盖与预跑进行两条断言口径不变。
    scenario_dir = tmp_path / "scenarios"
    runs_root = tmp_path / "runs"
    prepare_demo_assets(scenario_dir, runs_root, rounds=1)
    (scenario_dir / "demo_smoke.yaml").write_text("被改过的内容\n", encoding="utf-8")
    monkeypatch.setattr(pda, "PREWARM_SCENARIOS", ["demo_smoke.yaml"])

    report = prepare_demo_assets(scenario_dir, runs_root, overwrite=True, rounds=1)

    assert report["written"] == list(PRESET_SCENARIOS)  # 7 个全重写
    assert report["conflicts"] == []
    assert report["refused_conflicts"] == []  # 授权覆盖：无拒绝
    assert (
        (scenario_dir / "demo_smoke.yaml").read_text(encoding="utf-8")
        == PRESET_SCENARIOS["demo_smoke.yaml"]  # 恢复模板原文
    )
    assert report["prewarm_error"] is None
    assert len(report["prewarm_runs"]) == 1  # 预跑照常进行（收缩后 1 条）
    assert report["prewarm_runs"][0][1] == 0  # 冒烟单场景零失效


def test_prewarm_error_merged_into_report_not_raised(tmp_path: Path, monkeypatch):
    # ④ 预跑意外失败：monkeypatch 同包引用 prewarm_demo_runs 抛
    # PrewarmDemoRunError（携已跑清单）→ 不上抛、prewarm_error 如实呈现
    # （含 runs 已跑清单），且此前的 seed 产物保持（written=7）。
    def _boom(scenarios, runs_root, *, rounds=3, scenario_dir=None):
        raise PrewarmDemoRunError(
            "预跑意外失败即中止: 场景=demo_failure.yaml 第2/3轮 exit=2（场景写错）",
            runs=[("runs/already-1", 0), ("runs/already-2", 1)],
            scenario="demo_failure.yaml",
            round_index=1,
            exit_code=2,
            detail="ScenarioError: 非法场景",
        )

    monkeypatch.setattr(pda, "prewarm_demo_runs", _boom)
    report = prepare_demo_assets(tmp_path / "scenarios", tmp_path / "runs", rounds=3)

    assert set(report) == _REPORT_KEYS
    assert report["written"] == list(PRESET_SCENARIOS)  # seed 先行完成
    assert report["prewarm_runs"] == []  # 中止口径：成功清单空
    err = report["prewarm_error"]
    assert isinstance(err, dict)  # 不吞错不重抛：错误并入报告
    assert err["scenario"] == "demo_failure.yaml"
    assert err["round_index"] == 1
    assert err["exit_code"] == 2
    assert err["detail"] == "ScenarioError: 非法场景"
    assert "demo_failure.yaml" in err["message"]
    assert err["runs"] == [("runs/already-1", 0), ("runs/already-2", 1)]  # 已跑清单
    _assert_env_shape(report["env"])


def test_env_probe_fault_tolerant(monkeypatch, tmp_path: Path):
    # ⑤ env 探测容错：uhd 缺工具（binary_missing）→"不在位"不抛；探测器本身
    # 崩溃→"未探测"不抛；platformio 子进程 OSError→None 不抛。
    def _missing_tool(**kwargs):
        return {"devices": [], "raw": "", "available": False, "error": "binary_missing"}

    monkeypatch.setattr(pda, "probe_uhd_devices", _missing_tool)
    env = pda._probe_env()
    _assert_env_shape(env)
    assert env["uhd_probe"] == "不在位"  # 缺工具：无从谈在位，如实归不在位

    def _crash(**kwargs):
        raise RuntimeError("探测器崩溃")

    monkeypatch.setattr(pda, "probe_uhd_devices", _crash)
    env = pda._probe_env()
    _assert_env_shape(env)
    assert env["uhd_probe"] == "未探测"  # 防御分支：崩溃归未探测不外抛

    def _pio_oserror(*args, **kwargs):
        raise OSError("no such interpreter")

    # 全局 subprocess.run 被打桩期间不走真实 sim 管线（防管线内部子进程被
    # 误伤）：prewarm 一并打桩，编排仍真跑 seed+env 汇总——探测异常不外抛。
    monkeypatch.setattr(subprocess, "run", _pio_oserror)
    monkeypatch.setattr(
        pda, "prewarm_demo_runs", lambda *a, **k: {"runs": [("runs/stub", 0)]}
    )
    report = prepare_demo_assets(tmp_path / "scenarios", tmp_path / "runs", rounds=1)
    _assert_env_shape(report["env"])
    assert report["env"]["platformio"] is None
    assert report["env"]["uhd_probe"] == "未探测"  # crash 桩仍在位（同一 monkeypatch 会话）
    assert report["prewarm_runs"] == [("runs/stub", 0)]  # 编排其余部分不受探测影响


def test_authoritative_constants_shape():
    # ⑥ 权威常量形状（手册总章按名引用，漂移即此处点名）：
    # 便携档恰 12 项；全量档=便携档全部+4 项台式补充且保序；预跑集三场景
    # 均出自预置模板集（冒烟/录音/失效三口径）。
    portable, full = DEMO_CHECKLIST["便携档"], DEMO_CHECKLIST["全量档"]
    assert len(portable) == 12
    assert full[: len(portable)] == portable  # 全量档=便携档全部（保序）+补充
    assert full[len(portable) :] == [
        "示波器",
        "万用表",
        "LattePanda 3 Delta 单板机",
        "PIC18F4520 开发套件",
    ]
    assert pda.PREWARM_SCENARIOS == [
        "demo_smoke.yaml",
        "demo_record.yaml",
        "demo_failure.yaml",
    ]
    assert all(name in PRESET_SCENARIOS for name in pda.PREWARM_SCENARIOS)
