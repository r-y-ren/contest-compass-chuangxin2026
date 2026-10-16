"""prepare_demo_assets 对抗用例：R76 L0 演示物料准备编排（slug=demo_assets）。

① 端到端（临时目录，rounds=1，预跑场景集=权威三场景不收缩）：报告七键齐、
7 场景全写、prewarm_runs 3 条（exit∈{0,1} 且含 1=失效核心产出）、单列检查单
（19 项，R94 细分口径）齐、env 四键；② 幂等重跑：重跑→conflicts=7、场景文件
一字未改，且预跑照常进行（B49 fn-close 走查环 F1：预跑与种子冲突解耦——
prewarm 只读场景、从不写/覆盖场景）；②b 部分冲突：新场景照写 6、冲突 1 如实
列名、预跑照常进行；②c 交付形态：scenario_dir 预置仓内七场景（git 在位形态）
+ 空 runs_root → conflicts 列 7、prewarm_runs 非空、七场景文件字节不变
（证未覆盖——旧"冲突即早退拒预跑"守卫在该形态下致操控台历史恒空，故按新
契约改写，2026-10-16 B49）；③ overwrite=True 重跑授权覆盖（预跑收缩为
demo_smoke 单场景+rounds=1 控时，断言契约不变——收缩仅减运行条数，不改动
任何断言口径）；④ 预跑意外失败：monkeypatch 同包 prewarm_demo_runs 抛
PrewarmDemoRunError→并入报告不抛（含已跑清单）；⑤ env 探测容错（uhd 缺工具/
探测器崩溃/platformio 子进程异常均不抛、如实记录）；⑥ 检查单与预跑集权威常量
形状（手册总章按名 DEMO_CHECKLIST 引用——R90 单列化：list[str] 19 项保序
（R94 转接线细分），序=手册 0.1 表行序）。
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import src.prepare_demo_assets.prepare_demo_assets as pda
from src.prepare_demo_assets.prepare_demo_assets import (
    DEMO_CHECKLIST,
    prepare_demo_assets,
)
from src.prepare_demo_assets.prewarm_demo_runs import PrewarmDemoRunError
from src.prepare_demo_assets.seed_preset_scenarios import PRESET_SCENARIOS

#: 报告顶层契约（七键，B49 起 refused_conflicts 键作废删除）——演示命令直接
#: 消费的物料报告形状。
_REPORT_KEYS = {
    "written",
    "conflicts",
    "prewarm_runs",
    "prewarm_error",
    "checklist",
    "env",
}
#: 检查单条目数（R90 单列口径：手册 0.1 设备全集表全行数）。
_CHECKLIST_LEN = 19
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
    # 单列检查单（19 项）齐、env 四键。
    scenario_dir = tmp_path / "scenarios"
    runs_root = tmp_path / "runs"
    report = prepare_demo_assets(scenario_dir, runs_root, rounds=1)

    assert set(report) == _REPORT_KEYS
    assert report["written"] == list(PRESET_SCENARIOS)  # 7 个预置场景全写
    assert report["conflicts"] == []
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

    assert isinstance(report["checklist"], list)  # 单列检查单（非两档 dict）
    assert len(report["checklist"]) == _CHECKLIST_LEN  # 19 项
    assert report["checklist"] == DEMO_CHECKLIST  # 快照=权威常量（保序）
    _assert_env_shape(report["env"])


def test_rerun_lists_conflicts_and_still_prewarms(tmp_path: Path):
    # ② 幂等重跑：重跑同目录（overwrite 缺省 False）→ conflicts=7、场景文件
    # 一字未改，且预跑照常进行（prewarm 只读场景——B49 走查环 F1 解耦后契约；
    # 旧用例断言"冲突即早退拒预跑"，按新契约改写）。
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
    assert report["conflicts"] == list(PRESET_SCENARIOS)  # 冲突清单如实列名
    assert report["prewarm_error"] is None
    assert len(report["prewarm_runs"]) == 3  # 预跑照常进行（三场景 × 1 轮）
    assert all(code in {0, 1} for _, code in report["prewarm_runs"])
    assert set(report) == _REPORT_KEYS  # 报告完整可读（七键契约）
    _assert_env_shape(report["env"])
    for name in PRESET_SCENARIOS:
        assert (scenario_dir / name).read_text(encoding="utf-8") == before[name]
    run_dirs_after = {p.name for p in runs_root.iterdir()}
    assert run_dirs_before <= run_dirs_after  # 历史只增不破坏
    assert len(run_dirs_after - run_dirs_before) == 3  # 新攒 3 轮历史


def test_partial_conflict_still_seeds_new_and_prewarms(tmp_path: Path):
    # ②b 部分冲突：1 个已存在（内容不同）→ 其余 6 照写计入 written、
    # conflicts=[该 1 个] 如实列名、该文件未被覆盖、预跑照常进行
    # （按 B49 解耦契约改写；旧用例断言拒绝预跑）。
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "demo_emc.yaml").write_text("占位旧内容\n", encoding="utf-8")
    runs_root = tmp_path / "runs"

    report = prepare_demo_assets(scenario_dir, runs_root, rounds=1)

    assert report["conflicts"] == ["demo_emc.yaml"]
    assert report["written"] == [n for n in PRESET_SCENARIOS if n != "demo_emc.yaml"]
    assert (scenario_dir / "demo_emc.yaml").read_text(encoding="utf-8") == "占位旧内容\n"
    assert report["prewarm_error"] is None
    assert len(report["prewarm_runs"]) == 3  # 预跑照常进行（不因冲突早退）
    assert runs_root.is_dir()  # runs_root 已建并有历史可翻
    assert len([p for p in runs_root.iterdir() if p.is_dir()]) == 3


def test_repo_form_seven_conflicts_still_prewarms(tmp_path: Path):
    # ②c 交付形态（B49 走查环 F1 的走查实证形态）：scenario_dir 预置仓内
    # 七场景（字节同 fn_work/scenarios/——交付仓 git 在位形态）+ 空 runs_root
    # → conflicts 列 7、prewarm_runs 非空（操控台有历史可翻可达）、七场景
    # 文件字节不变（证 prewarm 未覆盖场景）。
    repo_scenarios = Path(__file__).resolve().parents[2] / "scenarios"
    assert repo_scenarios.is_dir()  # 仓内交付形态在位（git 跟踪）
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    for name in PRESET_SCENARIOS:
        (scenario_dir / name).write_bytes((repo_scenarios / name).read_bytes())
    digest_before = {
        name: hashlib.sha256((scenario_dir / name).read_bytes()).hexdigest()
        for name in PRESET_SCENARIOS
    }
    runs_root = tmp_path / "runs"  # 不存在——交付机上 runs/ 被 gitignore 的空目录形态

    report = prepare_demo_assets(scenario_dir, runs_root, rounds=1)

    assert report["written"] == []
    assert report["conflicts"] == list(PRESET_SCENARIOS)  # 七场景全列冲突
    assert report["prewarm_error"] is None
    assert len(report["prewarm_runs"]) == 3  # 预跑非空（解耦守卫后不再恒空）
    assert all(code in {0, 1} for _, code in report["prewarm_runs"])
    for name in PRESET_SCENARIOS:  # 字节不变——prewarm 只读、未授权不覆盖
        digest = hashlib.sha256((scenario_dir / name).read_bytes()).hexdigest()
        assert digest == digest_before[name], f"场景被改写: {name}"


def test_overwrite_true_rerun_reseeds_and_prewarms(tmp_path: Path, monkeypatch):
    # ③ overwrite=True 重跑：授权覆盖→written 7、预跑照常进行。
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
    # ⑥ 权威常量形状（手册总章按名引用，漂移即此处点名）：检查单单列
    # list[str] 恰 19 项且序=手册 0.1 设备全集表行序（逐位关键词锚+台式四件
    # 全文锚），条目无两档词（R90 防回潮）；预跑集三场景均出自预置模板集
    # （冒烟/录音/失效三口径）。
    assert isinstance(DEMO_CHECKLIST, list)
    assert len(DEMO_CHECKLIST) == _CHECKLIST_LEN  # 单列恰 19 项（0.1 表全行数）
    assert len(set(DEMO_CHECKLIST)) == _CHECKLIST_LEN  # 无重复条目
    assert all("便携档" not in item and "全量档" not in item for item in DEMO_CHECKLIST)
    # 保序锚：序=手册 0.1 表行序（0 起下标=表行号-1）。
    assert DEMO_CHECKLIST[0].startswith("笔记本")  # 1 演示主机
    assert "USRP B210" in DEMO_CHECKLIST[1]  # 2 B210 套件（拆出独立条目）
    assert "USB3 数据线" in DEMO_CHECKLIST[2]  # 3 B210↔主机
    assert "双频胶棒天线" in DEMO_CHECKLIST[3]  # 4 天线组一
    assert "SRH789" in DEMO_CHECKLIST[4]  # 5 天线组二
    assert "GPS" in DEMO_CHECKLIST[5]  # 6 天线组三（时钟演示可选）
    assert "衰减器" in DEMO_CHECKLIST[6]  # 7 发射链必串
    assert "负载" in DEMO_CHECKLIST[7]  # 8 传导闭合
    assert "母" in DEMO_CHECKLIST[8]  # 9a MMCX公转SMA母（GPS 天线用）
    assert "公转SMA公" in DEMO_CHECKLIST[9]  # 9b PPS/10M 备用
    assert "ESP32" in DEMO_CHECKLIST[10]  # 10 链路开发板
    assert "NRF24L01" in DEMO_CHECKLIST[11]  # 11 射频前端模块
    assert "USB 数据线" in DEMO_CHECKLIST[12]  # 12 供电+串口
    assert DEMO_CHECKLIST[13].startswith("便携金属屏蔽盒")  # 13 合规红线
    assert DEMO_CHECKLIST[14:18] == [  # 14–17 台式仪器与单板机/MCU 套件
        "示波器×1",
        "万用表×1",
        "LattePanda 3 Delta 单板机×1",
        "PIC18F4520 开发套件×1",
    ]
    assert DEMO_CHECKLIST[18].startswith("备件包")  # 19 殿后
    assert pda.PREWARM_SCENARIOS == [
        "demo_smoke.yaml",
        "demo_record.yaml",
        "demo_failure.yaml",
    ]
    assert all(name in PRESET_SCENARIOS for name in pda.PREWARM_SCENARIOS)


def test_checklist_manual_sync_anchor():
    """⑦ DEMO_CHECKLIST↔手册 0.1 表逐行同步锚（R94 对抗 F5 落地"后续加固项"）：
    0.1 表设备行数 == DEMO_CHECKLIST 长度；每项关键词在对应表行出现（序=行序）。"""
    import re as _re
    from pathlib import Path as _P

    manual = _P(__file__).resolve().parents[3] / "docs" / "功能演示手册.md"
    text = manual.read_text(encoding="utf-8")
    m = _re.search(r"### 0\.1 演示设备全集清单.*?(?=\n### )", text, _re.S)
    assert m, "0.1 节未找到"
    rows = [r for r in m.group(0).splitlines() if _re.match(r"\| \d+[ab]? \|", r)]
    assert len(rows) == len(DEMO_CHECKLIST), f"0.1 表 {len(rows)} 行 != checklist {len(DEMO_CHECKLIST)} 项"
    for row, item in zip(rows, DEMO_CHECKLIST):
        key = _re.match(r"\| \d+[ab]? \| ([^|]+) \|", row).group(1).strip()
        k4 = key.replace("（", "(").split("(")[0][:4]  # 表行取主名前 4 字
        assert k4 in item or item[:4] in key, f"不同步: 表行'{key}' vs 项'{item}'"
