"""演示物料准备编排（R76 L0）：seed_preset_scenarios 预置场景 → prewarm_demo_runs 预跑 sim 历史（含 record:true 录音）→ 汇总物料报告与出发检查单数据；幂等不覆盖（冲突未授权→拒绝预跑不抛异常）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

# 既有 USRP 探测（autodetect_backend 包内单源）：不抛出、自带超时参数——
# 出发检查 env 自检按 5s 预算复用，缺工具（binary_missing）如实归"不在位"。
from src.autodetect_backend.probe_uhd_devices import probe_uhd_devices

from .prewarm_demo_runs import PrewarmDemoRunError, prewarm_demo_runs
from .seed_preset_scenarios import seed_preset_scenarios

__all__ = ["DEMO_CHECKLIST", "PREWARM_SCENARIOS", "prepare_demo_assets"]

#: 预跑场景选择（权威）：冒烟基线 / 带标注录音攒数据 / 失效演示三类历史——
#: 让操控台报告中心、录音库、AI 页均有数据可翻；demo_failure 的 exit 1 =
#: 测到失效（核心产出），与 exit 0 一样如实登记不算失败。
PREWARM_SCENARIOS: "list[str]" = [
    "demo_smoke.yaml",
    "demo_record.yaml",
    "demo_failure.yaml",
]

#: 出发前检查单（权威，手册总章按名 DEMO_CHECKLIST 引用——v2 口径：与手册
#: 0.1「演示设备全集清单」表/0.4「出发前检查单」同源**单列**）：单一清单
#: 18 项，序=手册 0.1 表行序（主机→B210+USB3 数据线→天线三组→衰减器/负载/
#: 转接线→ESP32×2+NRF24×2+USB 线→屏蔽盒→示波器/万用表/LattePanda/PIC→
#: 备件包）——单一真机方案不分档，两档词（便携档/全量档）不再出现。
DEMO_CHECKLIST: "list[str]" = [
    "笔记本（Arch Linux，fn_work/.venv 已建）",
    "USRP B210（K7 优化版）×1",
    "USB3 数据线（Type-C）×1",
    "2.4G/5.8G 双频胶棒天线（SMA）×2",
    "SRH789 拉杆天线（SMA）×2",
    "GPS/BD 有源天线×1",
    "30dB SMA 衰减器×1",
    "SMA 同轴负载（50Ω）×2",
    "MMCX 转 SMA 转接线×2",
    "ESP32 开发板（含 CH340/CP2102）×2",
    "NRF24L01 模块（含 PA 型）×2",
    "USB 数据线（ESP32 供电+串口）×2",
    "便携金属屏蔽盒（含吸波材料）",
    "示波器×1",
    "万用表×1",
    "LattePanda 3 Delta 单板机×1",
    "PIC18F4520 开发套件×1",
    "备件包（杜邦线×7 组/SMA 扳手/标签/USB 集线器）",
]

#: uhd 探测预算（秒）——检查单 env 自检的轻量口径（探测缺工具时毫秒即返）。
_UHD_PROBE_TIMEOUT_S = 5.0
#: platformio 版本探测预算（秒）——`-m platformio --version` 常规亚秒级，
#: 首跑导入较慢时留足余量（超时/缺模块一律如实记 None，不抛）。
_PIO_PROBE_TIMEOUT_S = 15.0


def prepare_demo_assets(
    scenario_dir: str | Path,
    runs_root: str | Path,
    *,
    overwrite: bool = False,
    rounds: int = 3,
) -> dict:
    """编排演示前准备物料（预置场景 + 预跑历史 + 检查单数据一站式报告）。

    输入: scenario_dir/runs_root 目标目录（均自动创建）；overwrite=False
      幂等（目标场景已存在计冲突不覆盖）；rounds 透传 prewarm_demo_runs
      （每场景预跑轮数，缺省 3）。
    输出: 物料报告 dict（演示命令可直接看结果，不抛业务异常）——
      - "written"/"conflicts": seed_preset_scenarios 透传（本次写入/冲突清单）；
      - "refused_conflicts": 因冲突未授权覆盖而拒绝预跑的清单（非拒绝时 []）；
      - "prewarm_runs": [(运行目录, 退出码), ...]——exit 0/1 均如实登记
        （1=测到失效=核心产出）；拒绝预跑或预跑中止时 []；
      - "prewarm_error": 预跑意外失败（PrewarmDemoRunError）的如实呈现
        （message/scenario/round_index/exit_code/detail/runs 已跑清单），
        正常时 None——不吞错不重抛，报告可直接查阅；
      - "checklist": [设备条目, ...] 出发检查单·单一清单 18 项
        （DEMO_CHECKLIST 快照，序=手册 0.1 设备全集表行序，手册 0.4 同清单
        ——单列口径，无两档词）；
      - "env": 出发环境自检 {"python", "venv_ok", "platformio", "uhd_probe"}。
    错误: 目录冲突未授权覆盖→拒绝预跑并列冲突项（refused_conflicts，不抛
      异常——部分新场景照写并计入 written）；PrewarmDemoRunError 捕获后
      并入报告不重抛；仅目录不可写等 OSError 族沿 seed_preset_scenarios
      原样上抛（环境性问题不是演示编排可恢复项）。
    """
    seed = seed_preset_scenarios(scenario_dir, overwrite=overwrite)
    report: dict = {
        "written": seed["written"],
        "conflicts": seed["conflicts"],
        "refused_conflicts": [],
        "prewarm_runs": [],
        "prewarm_error": None,
        # 检查单给快照（整列拷贝）：调用方改报告不得倒灌权威常量。
        "checklist": list(DEMO_CHECKLIST),
        "env": _probe_env(),
    }
    # 幂等拒绝口径：已有冲突且未授权覆盖 → 不预跑（避免在"场景归属不明"的
    # 目录上攒出与新场景混跑的历史），冲突清单如实呈报，演示者看清再决定。
    if seed["conflicts"] and not overwrite:
        report["refused_conflicts"] = list(seed["conflicts"])
        return report
    try:
        prewarm = prewarm_demo_runs(
            PREWARM_SCENARIOS,
            runs_root,
            rounds=rounds,
            scenario_dir=scenario_dir,
        )
        report["prewarm_runs"] = list(prewarm["runs"])
    except PrewarmDemoRunError as exc:
        # 不吞错不重抛：意外失败如实并入报告（含已跑清单），供演示命令查阅。
        report["prewarm_error"] = {
            "message": str(exc),
            "scenario": exc.scenario,
            "round_index": exc.round_index,
            "exit_code": exc.exit_code,
            "detail": exc.detail,
            "runs": list(exc.runs),
        }
    return report


def _probe_env() -> dict:
    """出发环境自检（轻量、失败不抛只如实记录）。

    输出: {"python": 版本串, "venv_ok": sys.executable 含 .venv 与否,
      "platformio": 版本串或 None（当前解释器 -m platformio 探测）,
      "uhd_probe": "在位"|"不在位"|"未探测"（既有 probe_uhd_devices 5s 预算；
      探测器意外崩溃归"未探测"）}。
    """
    return {
        "python": platform.python_version(),
        "venv_ok": ".venv" in sys.executable,
        "platformio": _probe_platformio_version(),
        "uhd_probe": _probe_uhd_presence(),
    }


def _probe_platformio_version(timeout_s: float = _PIO_PROBE_TIMEOUT_S) -> "str | None":
    """platformio 版本串探测（R85 口径：装进 .venv 不动全局→按当前解释器 -m 探测）。

    工具缺失（模块不在→非零退出）/超时/OSError 一律如实记 None，不抛。
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "platformio", "--version"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None  # 模块未装（"No module named platformio"）或内部错——不在位
    return (proc.stdout or "").strip() or None


def _probe_uhd_presence(timeout_s: float = _UHD_PROBE_TIMEOUT_S) -> str:
    """USRP 在位探测三态归一："在位"（有设备段）/"不在位"（探测完成无设备，
    含缺 uhd_find_devices 工具——缺工具即无从谈在位）/"未探测"（探测器本身
    意外崩溃，防御分支）。复用 autodetect_backend 既有探测（不抛出、5s 预算）。"""
    try:
        probe = probe_uhd_devices(timeout_s=timeout_s)
    except Exception:  # noqa: BLE001 - 自检防御分支：探测器崩溃归"未探测"不抛
        return "未探测"
    return "在位" if probe.get("devices") else "不在位"
