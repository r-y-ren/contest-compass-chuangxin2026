"""录音条目→replay 场景对象：backend=replay+sigmf_path+倍速+沿用来源场景频段/安全
声明（声明缺失即拒——红线不因回放松动）——重写规约与签名意图详见 fn_docs/responsibility.md（R64 build_replay_scenario L1）。

条目契约（形状自定，本 docstring 登记——输入为录音条目元数据 dict）：

- ``sigmf_path``: str，显式直给 .sigmf-meta 路径；缺省从 ``path``（recordings
  目录）取字典序最早 *.sigmf-meta（与 run_rff_pipeline/train_classifier/
  browse_dataset_library 的「目录→最早 meta 配对 data」口径一致）；
- ``speed``: 可选倍速——有限实数 ≥0.1 且非 bool（域校验归 open_replay_backend，
  本函数不重复判域；缺省 1.0）；
- 来源场景（频段/安全声明/样式参数的沿用来源，按优先序）：
  ① ``source_scenario``（dict——浏览卡片/上游随条目直接携带的来源运行场景副本，
  规范化场景形状：style/fs/freq_hz/power_dbm/duration_s/bands/shielded_box/
  dut_scope 等在册键）；
  ② 来源运行目录（``run_dir`` 显式键，或 ``path`` 的父目录）下 scenario.yaml
  场景副本（manage_run.create_run_workspace 落盘的规范化场景——真跑运行的
  真值来源，yaml.safe_load 直读）。

红线（不因回放松动）：来源场景的 shielded_box/dut_scope 经
check_env_declarations 全查——缺失或值不符（shielded_box 必须严格 True、
dut_scope 仅 'self_built'）→ScenarioError 逐条指明；来源场景整体不可得
（两路皆缺/副本损坏）→ScenarioError（无从沿用声明即拒）。

产出场景（规范化前的组装 dict，经操控台 runner→run_scenario 的
validate→guard→normalize 三件套再过闸）：

- ``backend='replay'`` + ``sigmf_path`` + ``speed``（R64 快速通道：
  run_demo._backend_params 按 backend 类型透传给 replay 后端工厂）；
- 沿用来源场景的 style/fs/freq_hz/power_dbm/duration_s/bands/shielded_box/
  dut_scope（频段与安全声明原文沿用）；
- ``scenario_type='custom'`` + judge_min_samples=2 + dwell_s=0.0 + record=False
  （回放编排缺省：replay 后端无发射能力——start_tx 即拒，gb42590 阶梯的起发射
  不可用；custom 梯度的衰减下发在 replay 后端为 no_tx 记录、监测路经 replay
  后端按录制时间轴回放真值 IQ；判据窗与档间停留取秒级快路径缺省）。
"""
import os

from src.guard_compliance.check_env_declarations import check_env_declarations
from src.load_scenario.validate_scenario_schema import ScenarioError

__all__ = ["DEFAULT_REPLAY_SPEED", "build_replay_scenario"]

#: 回放倍速缺省（1.0=按录制时间轴原速；域校验归 open_replay_backend）。
DEFAULT_REPLAY_SPEED = 1.0

#: 来源运行目录内场景副本文件名（与 manage_run.create_run_workspace 约定一致）。
SCENARIO_FILENAME = "scenario.yaml"

#: 组装时沿用来源场景的键（存在且类型合规才落位；style/fs 缺失即拒）。
_INHERIT_KEYS = ("fs", "freq_hz", "power_dbm", "duration_s")


def _read_scenario_copy(run_dir: object) -> dict:
    """读来源运行目录的场景副本 scenario.yaml → dict（缺/损坏/非 dict→{}）。"""
    if not isinstance(run_dir, str) or not run_dir.strip():
        return {}
    path = os.path.join(run_dir, SCENARIO_FILENAME)
    if not os.path.isfile(path):
        return {}
    try:
        import yaml

        with open(path, encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except Exception:  # noqa: BLE001 - 副本损坏视同不可得（调用方按来源缺失拒）
        return {}
    return payload if isinstance(payload, dict) else {}


def _run_dir_of(entry: dict) -> "str | None":
    """条目 → 来源运行目录：'run_dir' 显式 > 'path'（recordings）父目录。"""
    explicit = entry.get("run_dir")
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    path = entry.get("path")
    if isinstance(path, str) and path.strip():
        return os.path.dirname(path.rstrip(os.sep))
    return None


def _resolve_sigmf_path(entry: dict) -> "str | None":
    """条目 → .sigmf-meta 路径：'sigmf_path' 显式 > 'path' 目录最早 meta。"""
    explicit = entry.get("sigmf_path")
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    recordings = entry.get("path")
    if not isinstance(recordings, str) or not recordings.strip():
        return None
    try:
        names = os.listdir(recordings)
    except OSError:
        return None
    metas = sorted(name for name in names if name.endswith(".sigmf-meta"))
    if not metas:
        return None
    return os.path.join(recordings, metas[0])


def build_replay_scenario(entry: dict) -> dict:
    """录音条目 → replay 场景对象（backend='replay'+sigmf_path+倍速+沿用来源
    场景的频段/安全声明；声明缺失或文件不可读→ScenarioError 指明）。

    输入:
        entry: 录音条目元数据 dict（契约见模块 docstring——sigmf_path/speed/
            source_scenario/run_dir/path 键）。

    输出:
        组装后的 replay 场景 dict（形状见模块 docstring；经 run_scenario 的
        validate→guard→normalize 三件套再过闸后交 replay 后端执行）。

    错误:
        ScenarioError: entry 非 dict/录音定位失败（无 sigmf_path 可解析）/
            .sigmf-meta 或同名 .sigmf-data 文件不可读/来源场景两路皆不可得/
            来源场景缺 style 或 fs（无从组装）/安全声明缺失或值不符
            （check_env_declarations 逐条 violations 透传——红线不因回放松动）。
    """
    if not isinstance(entry, dict):
        raise ScenarioError(
            f"录音条目必须为 dict（sigmf_path/source_scenario 等键，见"
            f" build_replay_scenario docstring 契约），实际 {type(entry).__name__}: {entry!r}"
        )

    # ---- 录音真值对定位与在位校验（装载期拒绝，不推迟到运行期） ----
    sigmf_path = _resolve_sigmf_path(entry)
    if sigmf_path is None:
        raise ScenarioError(
            "录音定位失败：条目未携带 'sigmf_path'，且 'path'（recordings 目录）"
            f" 无 *.sigmf-meta——条目: run_id={entry.get('run_id')!r}, "
            f"path={entry.get('path')!r}"
        )
    if not os.path.isfile(sigmf_path):
        raise ScenarioError(f"录音元数据文件不可读（不存在）: {sigmf_path}")
    data_path = sigmf_path[: -len(".sigmf-meta")] + ".sigmf-data"
    if not os.path.isfile(data_path):
        raise ScenarioError(
            f"录音数据文件不可读（.sigmf-data 与 meta 不成对）: {data_path}"
        )

    # ---- 来源场景（频段/安全声明/样式参数沿用来源，两路按优先序） ----
    source = entry.get("source_scenario")
    if not isinstance(source, dict) or not source:
        source = _read_scenario_copy(_run_dir_of(entry))
    if not isinstance(source, dict) or not source:
        raise ScenarioError(
            "来源场景不可得：条目无 'source_scenario'，且来源运行目录缺可读的"
            f" {SCENARIO_FILENAME} 场景副本——频段/安全声明无从沿用（run_id="
            f"{entry.get('run_id')!r}, run_dir={_run_dir_of(entry)!r}）"
        )

    # ---- 红线（不因回放松动）：shielded_box/dut_scope 必须真值在 ----
    verdict = check_env_declarations(
        {
            "shielded_box": source.get("shielded_box"),
            "dut_scope": source.get("dut_scope"),
        }
    )
    if verdict["status"] != "pass":
        violations = "\n".join(f"  - {v}" for v in verdict["violations"])
        raise ScenarioError(
            f"来源场景安全声明未过红线（回放不放松）:\n{violations}"
            f"\n来源: run_id={entry.get('run_id')!r}"
        )

    style = source.get("style")
    if not isinstance(style, str) or not style.strip():
        raise ScenarioError(
            f"来源场景缺 'style'（非空 str，replay 场景组装必需），实际: {style!r}"
        )
    if "fs" not in source:
        raise ScenarioError("来源场景缺 'fs'（采样率，replay 场景组装必需）")

    scenario: dict = {
        "style": style.strip(),
        "backend": "replay",
        "sigmf_path": sigmf_path,
        "speed": entry.get("speed", DEFAULT_REPLAY_SPEED),
        "scenario_type": "custom",
        "judge_min_samples": 2,
        "dwell_s": 0.0,
        "record": False,
        "bands": source.get("bands"),
        "shielded_box": source.get("shielded_box"),
        "dut_scope": source.get("dut_scope"),
    }
    for key in _INHERIT_KEYS:
        if key in source:
            scenario[key] = source[key]
    return scenario
