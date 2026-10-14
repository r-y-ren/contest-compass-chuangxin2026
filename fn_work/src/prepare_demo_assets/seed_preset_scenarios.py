"""预置演示场景写入（R76 L1）：内置演示场景模板集（与手册总章清单一一对应）写为 scenarios/ 下 YAML；文件已存在计为冲突项不覆盖（幂等），显式 overwrite 才覆盖——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = ["PRESET_SCENARIOS", "seed_preset_scenarios"]

# 公共口径尾段（七个模板共享，README「场景文件怎么写」同款）：模拟后端 +
# 2.4G 法规白名单频段 + 屏蔽盒/自建链路两声明。模板字段全部以「能通过
# load_scenario 校验」为准（未知键会被装载器拒收，故只用在册字段；
# 字段形状照抄 tests/load_scenario 与 tests/run_demo 既有合法例）。
_COMMON_TAIL = """\
backend: sim
bands: [[2400, 2483.5]]
shielded_box: true
dut_scope: self_built
"""

#: 预置演示场景模板集（手册总章清单一一对应，恰好 7 个）：文件名 → YAML 文本。
#: 公共必填（style/fs/bands/shielded_box/dut_scope）之外给合理缺省——
#: freq_hz 2.45G、power_dbm -15（EMC 照抄既有用例取 -20）、dwell_s 0.5、
#: baseline_samples 10；duration_s 取小值保 sim 预跑秒级快路径。
PRESET_SCENARIOS: dict[str, str] = {
    # ① 冒烟（零失效口径）：单音 + 宽判据 0.999——整轮预期零失效，退出码 0。
    "demo_smoke.yaml": """\
# 演示冒烟（零失效口径）：单音 + 宽判据 0.999——整轮预期零失效，
# run_demo 退出码 0（演示开场「平台活着」的第一跑）。
style: tone
fs: 1000000
freq_hz: 2450000000
power_dbm: -15
duration_s: 0.005
judge_per_threshold: 0.999
dwell_s: 0.5
baseline_samples: 10
"""
    + _COMMON_TAIL,
    # ② 失效演示（核心产出口径）：单音 + 判据 0.10——中段功率档测到失效。
    #    sim_events/signal_power_db/link_power_db/judge_min_samples 照抄
    #    run_demo 内置 --demo 场景的失效配方（GB 阶梯 −25…0dBm 绝对电平，
    #    第 3 档 jsr=+5 处窗 per=0.10 恰达阈值）——否则文件路线缺省中性
    #    事件永不失效，退出码 1 口径落空。
    "demo_failure.yaml": """\
# 失效演示（核心产出口径）：单音 + 判据 0.10——中段功率档测到失效，
# run_demo 退出码 1 = 测到失效属预期产出（--demo 口径），不是故障。
# sim 事件按 GB 阶梯档位携带绝对干扰电平（与内置 --demo 场景同配方：
# 判据于第 3 档 -15dBm（jsr=+5）触发，窗 per=0.10 恰达阈值）。
style: tone
fs: 1000000
freq_hz: 2450000000
power_dbm: -15
duration_s: 0.005
judge_per_threshold: 0.10
scenario_type: gb42590
judge_min_samples: 2
dwell_s: 0.002
baseline_samples: 10
signal_power_db: -20
link_power_db: -20
dut: {source: sim, samples_per_event: 2}
sim_events:
  - {type: power_step, achieved_db: -25, ts: 0}
  - {type: power_step, achieved_db: -20, ts: 1}
  - {type: power_step, achieved_db: -15, ts: 2}
  - {type: power_step, achieved_db: -10, ts: 3}
  - {type: power_step, achieved_db: -5, ts: 4}
  - {type: power_step, achieved_db: 0, ts: 5}
"""
    + _COMMON_TAIL,
    # ③ 距离演变：1/3/7 米三档路损（l0=30 时三档全部可达，README 模板同款）。
    "demo_distance.yaml": """\
# 距离演变演示：干扰随 1/3/7 米三档路损加重（l0 取 30 时三档全部可达），
# 逐档看 PER 爬升与失效电平表。
style: tone
fs: 1000000
freq_hz: 2450000000
power_dbm: -15
duration_s: 0.005
scenario_type: distance
distances: [1, 3, 7]
model_params: {d0_m: 1, l0_db: 30, n: 2}
dwell_s: 0.5
baseline_samples: 10
"""
    + _COMMON_TAIL,
    # ④ 带录音攒数据：扫频 + record: true——落带标注 SigMF 录音供录音库/AI 页。
    "demo_record.yaml": """\
# 带录音攒数据（供录音库/AI 页演示）：扫频 + record: true——每轮落带标注
# SigMF 录音，攒够样本后可发起 AI 训练/当场识别。
style: sweep
fs: 1000000
freq_hz: 2450000000
power_dbm: -15
duration_s: 0.01
record: true
dwell_s: 0.5
baseline_samples: 10
"""
    + _COMMON_TAIL,
    # ⑤ 多音复合（国标多音口径）：composite 分量清单叠三支单音
#    （分量形状照抄 tests/synthesize_style 与 schema 校验既有合法例）。
    "demo_composite.yaml": """\
# 多音复合演示（国标多音口径）：composite 分量清单叠三支单音
# （-200k/0/+200k 三点频），components 逐分量按场景校验同口径递归把关。
style: composite
fs: 1000000
freq_hz: 2450000000
power_dbm: -15
duration_s: 0.005
components:
  - {style: tone, fs: 1000000, freq_offset_hz: -200000}
  - {style: tone, fs: 1000000, freq_offset_hz: 0}
  - {style: tone, fs: 1000000, freq_offset_hz: 200000}
dwell_s: 0.5
baseline_samples: 10
"""
    + _COMMON_TAIL,
    # ⑥ EMC 摸底（模拟口径）：bandlimited_noise + CISPR B 频段步进扫频
#    （字段形状照抄 tests/run_demo/test_emc_scenario_envelope 既有用例；
#    emc_flow 等流程键为操控台 dict 通道专用——文件路线 schema 不在册，
#    不写，execute_scenario 分派缺省 sweep）。
    "demo_emc.yaml": """\
# EMC 摸底演示（模拟口径）：带限噪声载波 + CISPR B 频段步进扫频。
# 注：emc_flow 等流程键走操控台 dict 通道（文件路线 schema 不在册），
# 此处不写——execute_scenario 分派缺省 sweep。
style: bandlimited_noise
fs: 10000000
bandwidth_hz: 2000000
freq_hz: 2450000000
power_dbm: -20
duration_s: 0.01
scenario_type: emc
band: cispr_b
step_hz: 5000000
dwell_s: 0.5
baseline_samples: 10
"""
    + _COMMON_TAIL,
    # ⑦ 编辑器练手：中性带限噪声——供场景编辑器页面演示改参数保存重跑。
    "editor_practice.yaml": """\
# 场景编辑器练手（中性场景）：带限噪声 + 常规判据——页面演示改参数
# （功率/带宽/判据阈值等）后保存重跑，无失效戏剧性，适合练手。
# 带宽 ≤fs/2（gen_bandlimited_noise 物理域：fs 2M → 带宽上限 1M，取 500k）。
style: bandlimited_noise
fs: 2000000
bandwidth_hz: 500000
freq_hz: 2450000000
power_dbm: -15
duration_s: 0.005
judge_per_threshold: 0.10
dwell_s: 0.5
baseline_samples: 10
"""
    + _COMMON_TAIL,
}


def seed_preset_scenarios(scenario_dir: str | Path, *, overwrite: bool = False) -> dict:
    """写入预置场景集。

    输入: 目标目录（+overwrite 授权覆盖）。
    输出: {"written": [文件名...], "conflicts": [文件名...]}——written 为本次
      落盘的文件名（按模板集清单序），conflicts 为已存在而未覆盖的文件名。
      幂等口径：目标文件已存在即计冲突不覆盖（重跑列出全部已存在项、
      written 为空，内容一字不动），显式 overwrite=True 才覆盖重写。
    错误: 目录不可写→上抛（PermissionError）；目标路径是已存在文件等
      OSError 族异常原样透传。
    """
    target = Path(scenario_dir)
    if target.is_dir():
        # 已存在目录：写权限预检（chmod 0o500 之类在此早拒，不写到一半才炸）。
        if not os.access(target, os.W_OK):
            raise PermissionError(f"目标目录不可写: {target}")
    else:
        # 目录不存在：自动创建（含父目录；父目录不可写等 OSError 自然上抛）。
        target.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    conflicts: list[str] = []
    for name, template in PRESET_SCENARIOS.items():
        path = target / name
        if path.exists() and not overwrite:
            conflicts.append(name)  # 已存在不覆盖（幂等；授权归 overwrite）
            continue
        path.write_text(template, encoding="utf-8")  # OSError（含只读文件）自然上抛
        written.append(name)
    return {"written": written, "conflicts": conflicts}
