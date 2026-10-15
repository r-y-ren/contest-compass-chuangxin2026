# 验收报告：无人机链路抗干扰测试平台（缺陷闭合轮③——R88 录音窗覆盖发射窗 + R89 EMC 三流程报告节）
> fn-close 独占产出（2026-10-15）。核验输出原样粘贴，禁止转述、禁止"概括为通过"。
> 本报告不宣布"验收通过"——终审归用户。上周期报告归档于 acceptance-c2.md。

## 终检一览
| 终检 | 命令 | 结果 | 证据 |
|---|---|---|---|
| ① 桩+全量测试+镜像 | scripts/fn-check.sh | 三项全过（桩 0/3631 绿/镜像警告级） | §1/§2 |
| ② 接线与实跑 | — | 过（8 新函数+6 改造点锚在案；顶层实跑 2 式） | §3 |
| ③ 矩阵双向 | scripts/fn-doc-lint.py | 机械输出在案+全量分诊证伪（c2 先例族）+独立核对替代 | §4 |
| ④ 非功能对照 | — | 16 条逐条（新增 3 条用例级实证） | §5 |
| ⑤ 报告完整性 | — | 无自封结论、末行固定句在 | — |
| ⑥ 目录清点 | — | 无 scratch/vendor 残留、依赖清单入库、venv 在位 | §6 |
| ⑦ 外发终检 | — | 不适用（非交付型外发任务） | — |

## 1 桩检查（fn-check §① 原文）
```
== ① 残留桩 ==
PASS 残留桩 0 处
```

## 2 全量测试（fn-check §② 原文，修复后六道重跑）
```
== ② 全量测试 ==
================= 3631 passed, 2 warnings in 163.48s (0:02:43) =================
PASS 全量测试
```
（3631 = c2 基线 3551 → 演进轮③净增 74 用例：R88 族+R89 族+走查修复；B210 真机在位，3 例实机用例本轮实测通过。）

## 3 接线与实跑（本周期新增/改造面）
**8 新函数静态调用点**（grep 锚）：
- `tap_tx_window_blocks(ctx)` ← execute_gb42590_protocol.py:745（装配缝受停发射保护 try 内，tap_assembly_error 分支）
- `render_emc_flow_section(result, missing)` ← build_report.py:486
- `normalize_monitor_block(block)` ← record_run_streams.py:174（薄壳）+ tap _pull_tick
- `_make_tick_dwell_cb`/`_pull_tick` ← tap_tx_window_blocks.py 闭包消费；`_emc_conduction/radiation/sweep_md` ← render_emc_flow_section.py 分派

**6 改造点锚**：run_power_ladder dwell_cb（签名/发射前校验/调用三处）；_execute_stage `ctx["stop"] = stop`；record_run_streams prewindow_blocks；execute_gb42590_protocol tap_kit 装配；_report_payload flow 标签三分支；build_report `_emc_simulated_part_label` 脚注回退随流程。

**顶层实跑**：
```
run_demo --demo → status=failed failure_levels=1（中段失效演示口径）report 生成 traceability=passed
dict 通道 conduction → COND_EXIT=0 status=completed；report.md 含「## EMC 传导摸底（模拟）」「> passed：合规（演示口径，非认证）」
```

## 4 需求→函数对照（R88/R89；R1–R87 沿 c2 在册）
| 需求 | 函数 | 核验命令 | 结果 |
|---|---|---|---|
| R88 交窗硬判据 | tap_tx_window_blocks 子树+4 改造点 | pytest tests/run_demo/test_sim_delivery_record_true.py -q | 8 passed（窗内行 57344/环回块 +27.7dB/PAPR 差 12.17dB） |
| R88 急停先行 | _make_tick_dwell_cb | pytest tests/tap_tx_window_blocks -q | 25 passed（端到端 0.60s 截断在 B44 对抗报告） |
| R88 上限贯通 | record_run_streams prewindow | pytest tests/record_run_streams -q | 47 passed |
| R89 三形状分支 | render_emc_flow_section+3 叶 | pytest tests/render_emc_flow_section tests/build_report -q | 74 passed（-k report_builder 25） |
| R89 端到端三流程 | _report_payload 映射 | pytest tests/run_demo/test_emc_scenario_envelope.py -q | 8 passed（sweep 误挂传导标题闭合） |
| 走查 C1 修复 | index_dataset/train_classifier | pytest tests/index_dataset tests/train_classifier -q | 79 passed（含端到端封堵 n_samples==2） |

**fn-doc-lint 机械输出**：全量 380 ERR/47 WARN 逐类分诊证伪——167 死代码=动态装配/括注调用方切分假阳（c2 先例族，本周期 tap/render 等 8 函数同族）；89+14=演进格式矩阵解析脱节（R1–R90 全挂=全局假阳）；Ruling 文本行/X1 模板行/R90 状态词装饰=格式误读。独立核对替代：矩阵正向 R88/R89 有 wired 函数；反向无孤儿（调用链 §3）；functions.md 8 行 hash 与 git 对账一致；桩标记交叉零错。

## 5 非功能约束逐条（16 条）
既有 13 条（合规红线/实时性/样式切换/插槽/先停发射/可溯源/平台/数字纪律/离线/顺手改登记/演示零出错/手册单文件）全套件用例承载绿；**演进轮③新增 3 条**：采集提前不扰发射（dwell_cb 缺省纯睡眠 4 用例+分片开销 +1.6% 实测）、录音可复现（同 seed 两轮 sha 相同，B44 对抗复算）、防失控上限沿用（prewindow 计数 3 用例）。

## 6 目录清点
`.scratch/`/`fn_work/.scratch/`/`fn_docs/vendor/` 均不存在；`fn_work/requirements.txt` 入库（16 包）、`fn_work/.venv` 在位（走查子代理 /tmp 全新复建 PIP_EXIT=0 实证可复建）；外部依赖与参考资料登记节在册。

## 用户走查环记录
首轮（全文走查子代理）：**C1**（索引链 style 断链——「攒样可训」在网页主路径拒训+错误消息误导）+**I1**（noise_floor 元数据标注不落盘）+**I2**（卡片需重启）+**I3**（急停报告占位未披露）+**I4**（训练/索引测试 fixture 假绿）+5M。处置：C1/I4 派 /fn-implement 修复子代理（f44b6e9：index_dataset 自场景副本补全 style/freq_mhz+train 跳段归因分列+端到端封堵用例）；I1/I2/I3/M1/M2 手册直改（内容级可辨口径/重启提示/已知限制 9/16 包/658M）。复走查（scoped 修复面）：**Critical 0 / Important 0 清零**。Minor 留档：「环回约 -10dB 级」数字随场景功率漂移（实测分离 140+dB 实质成立）；发射窗缓冲无上界与 B210 序号域 ts 随 R87。

## 未完成项
无（R87 真机复查为独立延后条目，非本轮未完成）。

---
以上为终检事实，验收与否由用户判定。
