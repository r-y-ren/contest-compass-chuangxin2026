"""SITL 桥演示入口：选历史运行→提取 PER-功率台阶→bridge_to_sitl(dry_run=True)
映射预览上屏；SITL 不在位跳过标注不报错——重写规约与签名意图详见
fn_docs/responsibility.md（R72 demo_sitl_bridge L0；调用方 mount_console_extensions）。

落地口径（R72，沿用 R53 bridge_to_sitl 口径）：

- 选历史运行：``report_root/<run_id>/`` 运行目录（与 R60 产物端点/R61 摘要行
  同锚点）；run_id/report_root 非非空 str → ValueError（形状先拒）；
  B30 对抗①转 B31 随批落地（2026-10-14）：run_id 加 report_root realpath
  围栏（对齐 R60/R71 口径）——``realpath(join(report_root, run_id))`` 解析后
  必须落在 ``realpath(report_root)`` 内（commonpath 判），绝对路径（被
  os.path.join 丢弃根→界外读）与 ``..`` 穿越一律 ValueError（端点层转 400
  field='run_id'）；
- 提取 PER-功率台阶：run 目录 kpi.csv+events.jsonl 读回（build_report 同款
  只读——kpi 行 timestamp_ms/judge_per、events 逐行 JSON 含权威盖戳 ts）→
  build_curve_frames 帧A（power_step 事件开窗、窗内 judge_per 均值——R25 三图
  同源口径）→ 台阶表 ``[{'per': 窗均 judge_per, 'level_db': target_db}, ...]``
  （None 窗剔除）；无 power_step 事件或全窗无判据样本 → ValueError（运行无
  KPI 数据——提示选择其他运行）；
- 映射预览：``bridge_to_sitl({'steps_executed': 台阶表}, {'connection': None},
  dry_run=True)``——只产注入参数表（台阶→丢包/时延表），不 import pymavlink、
  不建任何连接（R53 dry_run 语义：映射口径 mock 层）；
- SITL 不在位跳过标注：pymavlink 延迟 import 探测（库缺 → sitl_available=False
  +skip_note 跳过标注与 pip 提示——dry_run 预览照常产出，不报错不阻塞）；
- 演示只读：不写 run 目录任何文件，输出恒带 read_only=True 与诚实基注。
"""
import csv
import json
import os

from src.bridge_to_sitl.bridge_to_sitl import bridge_to_sitl
from src.plot_triple_curves.build_curve_frames import build_curve_frames

__all__ = ["demo_sitl_bridge"]

#: 库缺安装提示（skip_note 附带——与 bridge_to_sitl._PIP_HINT 同文口径）。
_PIP_HINT = "pip install pymavlink"

#: 演示视图的诚实基注（dry_run 预览+只读口径）。
_SIM_NOTE = (
    "SITL 桥演示为 dry_run 映射预览（R53 口径）——只产台阶→丢包/时延参数表，"
    "不连接任何 SITL 实例；真实注入需 pymavlink 在位且配置连接串。本演示只读，"
    "不改写运行目录任何文件"
)


def _opt_float(text: object) -> "float | None":
    """CSV 单元格→float|None（空/坏值 None——build_report 同款降级）。"""
    if text is None or text == "":
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _read_kpi_rows(run_dir: str) -> list:
    """kpi.csv 读回（timestamp_ms/judge_per 列）；缺失/坏行→[]（降级不抛）。"""
    path = os.path.join(run_dir, "kpi.csv")
    if not os.path.isfile(path):
        return []
    rows: list = []
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            for record in csv.DictReader(handle):
                rows.append(
                    {
                        "timestamp_ms": _opt_float(record.get("timestamp_ms")),
                        "judge_per": _opt_float(record.get("judge_per")),
                    }
                )
    except OSError:
        return []
    return rows


def _read_events(run_dir: str) -> list:
    """events.jsonl 逐行 JSON 读回；缺失→[]；坏行跳过（build_report 同款）。"""
    path = os.path.join(run_dir, "events.jsonl")
    if not os.path.isfile(path):
        return []
    events: list = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    events.append(item)
    except OSError:
        return []
    return events


def _extract_per_steps(run_dir: str) -> list:
    """run 目录→PER-功率台阶表（帧A：power_step 窗 judge_per 均值）。

    build_curve_frames 的帧A 与 R25 三图同源——x=target_db 档位序、y=窗内
    judge_per 均值（None 窗=无判据样本，剔除）；全空 → ValueError（无 KPI 数据）。
    """
    frames = build_curve_frames(
        {
            "kpi": _read_kpi_rows(run_dir),
            "events": _read_events(run_dir),
            "failure_levels": [],
        }
    )
    steps = [
        {"per": float(per), "level_db": float(level)}
        for level, per in zip(frames["frame_a"]["x"], frames["frame_a"]["y"])
        if level is not None and per is not None
    ]
    if not steps:
        raise ValueError(
            f"运行无 KPI 数据（无 power_step 台阶或各档窗口无 judge_per 样本）: "
            f"{run_dir}——请选择其他运行（报告中心有失效电平/功率阶梯的运行才可桥接）"
        )
    return steps


def _probe_sitl_library() -> "tuple[bool, str | None]":
    """pymavlink 在位性探测（延迟 import，不建连接）→ (在位, 跳过标注|None)。"""
    try:
        import pymavlink  # noqa: F401 - 只探在位性，绝不真连
    except Exception:  # noqa: BLE001 - ImportError 及任何构建期异常按库缺处理
        return False, (
            "SITL 不在位：pymavlink 未安装——真实注入跳过（不阻塞），本次仅输出 "
            f"dry_run 映射预览；安装: {_PIP_HINT}"
        )
    return True, None


def demo_sitl_bridge(run_id: str, report_root: str) -> dict:
    """SITL 桥演示入口：选历史运行→PER 台阶→bridge_to_sitl(dry_run) 映射预览；
    SITL 不在位跳过标注（详见 fn_docs/responsibility.md 功能块）。

    输入:
        run_id: 运行目录名（report_root 下一级——R60/R61 同锚点；非非空 str 拒）。
        report_root: 运行目录根（操控台 deps['report_root']；非非空 str 拒）。

    输出:
        演示视图 dict：{'ok': True, 'read_only': True, 'run_id', 'report_root',
        'steps': [{'per','level_db'}, ...] PER-功率台阶表, 'n_steps',
        'bridge': bridge_to_sitl dry_run 完整返回（bridged/dry_run/injections/
        n_injections/connection）, 'injections': 台阶→丢包/时延参数表（透传）,
        'sitl_available': bool（pymavlink 在位性）, 'skip_note': 不在位跳过
        标注|None, 'note': 诚实基注}。

    错误:
        ValueError: run_id/report_root 形状错；运行目录不存在；运行无 KPI 数据
            （无 power_step 台阶或全窗无判据样本——消息提示选择其他运行）；
            台阶表域错（per/level_db 非有限实数）由 bridge_to_sitl 透传。
    """
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError(
            f"run_id 必须为非空 str（运行目录名——报告中心行的同一口径），"
            f"实际: {run_id!r}"
        )
    if not isinstance(report_root, str) or not report_root.strip():
        raise ValueError(
            f"report_root 必须为非空 str（运行目录根），实际: {report_root!r}"
        )
    run_id = run_id.strip()
    run_dir = os.path.join(report_root, run_id)
    # B30 对抗①转 B31 随批：report_root realpath 围栏（对齐 R60/R71 口径）——
    # 绝对路径（os.path.join 丢弃根）与 ../ 穿越解析后落界外 → 早拒（越界
    # 目标即便真实存在也不读——演示只接受 report_root 下运行目录）。
    fence_root = os.path.realpath(report_root)
    resolved = os.path.realpath(run_dir)
    try:
        inside = os.path.commonpath([fence_root, resolved]) == fence_root
    except ValueError:  # 不同盘符/混合形态——按越界处理（Linux 不触，防御口径）
        inside = False
    if not inside:
        raise ValueError(
            f"run_id 越界（report_root 围栏，对齐 R60/R71 口径）: {run_id!r} 解析后 "
            f"{resolved} 不在 {fence_root} 内——只接受 report_root 下一级运行目录名"
        )
    if not os.path.isdir(run_dir):
        raise ValueError(
            f"运行目录不存在: {run_dir}（run_id={run_id!r}）——请选择其他运行"
        )

    steps = _extract_per_steps(run_dir)
    available, skip_note = _probe_sitl_library()
    outcome = bridge_to_sitl(
        {"steps_executed": steps}, {"connection": None}, dry_run=True
    )
    return {
        "ok": True,
        "read_only": True,
        "run_id": run_id,
        "report_root": report_root,
        "steps": steps,
        "n_steps": len(steps),
        "bridge": outcome,
        "injections": outcome["injections"],
        "sitl_available": available,
        "skip_note": skip_note,
        "note": _SIM_NOTE,
    }
