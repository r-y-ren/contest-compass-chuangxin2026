# 验收报告：无人机链路抗干扰测试平台·展示层全能力演进周期（c2）
> fn-close 独占产出（演进周期，旧报告归档 acceptance-c1.md）。核验输出原样粘贴，禁止转述。
> 本报告不宣布"验收通过"——终审归用户。
> 终检时点：2026-10-14（走查环修复后六道全量重跑口径；修复 commit d554481）。

## 终检一览

| 终检 | 命令 | 结果 | 证据 |
|---|---|---|---|
| ① 桩+全量测试+镜像 | scripts/fn-check.sh | ①PASS 桩 0 ②PASS 3429 passed+5 skipped ③WARN（检查器命名/pycache 噪声，c1 已裁定） | §1/§2 |
| ② 接线与实跑 | — | 144/144 调用点在（cross 140/test+entry 3/same-file 1）；三入口实跑有可观察输出 | §3 |
| ③ 矩阵双向 | fn-doc-lint.py+独立核对 | lint 308 错=解析器与演进文档格式脱节（四族逐族证伪，c1 同源）；独立双向 75/75 有函数全 wired、144/144 调用链、桩 0、tracker 五步 144/144 齐且三方一致 | §4 |
| ④ 非功能对照 | — | 10 条逐条过（含演进轮离线可用 57+9、顺手改登记 6 处） | §5 |
| ⑤ 报告完整性 | — | 无自封结论、末行固定句在 | — |
| ⑥ 目录清点 | — | scratch 无/vendor 无/runs 空/依赖清单齐可复建/外部依赖登记齐（含走查修复后 playwright 口径） | §6 |

## 1 桩检查（fn-check.sh ①段原文）
```
== ① 残留桩 ==
PASS 残留桩 0 处
```

## 2 全量测试（fn-check.sh ②段，修复后新鲜全量）
```
== ② 全量测试 ==
============ 3429 passed, 5 skipped, 2 warnings in 90.57s (0:01:30) ============
PASS 全量测试
```
（5 skip 全为 B210 真机环境类运行时门禁，设备未枚举时自动跳过；3429=演进前基线 2894 → +535，其中域二十 25 函数及其 e2e/走查修复族贡献。③段镜像 WARN 为检查器命名规则/pycache 噪声，c1 报告已逐文件裁定，未新增实质缺失。）

## 3 接线与实跑
- **144 函数静态调用点**：探针判定 144/144 通过（cross 140 / test+entry 3 / same-file 1），MISSING 清单为空（逐函数判定表见采集原文，functions.md 144 行全 wired）。
- **run_demo(['--demo']) 实跑**：`status=failed failure_levels=1 traceability=passed`、exit 1（--demo 中段失效=核心产出演示口径，测试锚定 test_run_demo.py:209）。
- **serve_console 真服务**：GET /pages/index → 200/41388B；GET /assets/vendor/vue.global.prod.js → 200/157924B（vue v3.5.13 头在）。
- **audit_responsibility_alignment 真文档对账**：ok=True，registered 8 项，missing 0，fast_track_notes=6，known_keys_len=63。

## 4 需求→函数对照（R56–R75 演进周期 20 条；R1–R55 沿 c1 §4 不变）
| R | 函数 | 核验命令 | 结果 |
|---|---|---|---|
| R56 | localize_console_assets(+navigation/mount) | pytest -k console_offline → 57 passed；-k console_pages_e2e → 9 passed（断网真装载） | wired |
| R57 | edit_scenario_ui | -k scenario_editor_e2e → 1 passed（表单/YAML/400 逐条/多带防护） | wired |
| R58 | stream_realtime_console(+triple_charts) | -k realtime_streams_e2e → 2 passed（真 sim 帧到浏览器，修复后 spectrum>0） | wired |
| R59 | harden_emergency_stop | -k emergency_stop → 27 passed（含真运行急停 1.5s 提前终止 e2e） | wired |
| R60 | serve_run_artifacts(+render_report_html) | -k report_view → 2 passed+52 单测（XSS 消毒 20 形态） | wired |
| R61 | list_run_summaries | tests/list_run_summaries/ → 13+e2e 3（场景名回落修复后） | wired |
| R62 | view_failure_comparison | -k boundary_view → 8 passed | wired |
| R63 | browse_dataset_library | -k dataset_view_e2e → 2 passed | wired |
| R64 | launch_replay_run(+build_replay_scenario) | -k replay_run → 21 passed（录制→回放 exit 0+围栏 7） | wired |
| R65 | launch_classifier_training | -k ai_train_view → 11 passed | wired |
| R66 | view_cv_evaluation | -k ai_eval_view → 10 passed | wired |
| R67 | infer_style_entry | -k ai_infer_view → 13 passed | wired |
| R68 | demo_emc_flows | -k emc_view → 11 passed（含真装配 7 例，F1 修复后） | wired |
| R69 | demo_instrument_panels | -k instruments_view → 10 passed | wired |
| R70 | view_calibration_status | -k calibration_view → 8 passed | wired |
| R71 | view_ledger_audit | -k ledger_audit_view → 11 passed（围栏修复后） | wired |
| R72 | demo_sitl_bridge | -k sitl_view → 8 passed（F4 修复后非空映射） | wired |
| R73 | demo_rl_policy | -k rl_view → 7 passed | wired |
| R74 | demo_rff_pipeline | -k rff_view → 7 passed | wired |
| R75 | audit_responsibility_alignment | -k responsibility_alignment → 6 passed；责任文档回登记×4 | wired |
| — | 走查修复（F1-F6） | -k "emc_view_real or sim_delivery or emc_envelope" → 17 passed | 修复实证 |

## 5 非功能约束逐条（10/10）
合规红线 75+32 绿｜实时<500ms（latency 8+e2e 2）｜样式切换<2s（41）｜插槽可扩展（80）｜先停发射（急停族 27+21）｜可溯源（59+report_view 2）｜Linux 无外网可用｜数字纪律（【待实测】40 处占位在位）｜**离线可用（console_offline 57+断网 e2e 9）**｜**顺手改登记（快速通道 6 处+变更记录 4 行）**。

## 6 目录清点
.scratch/ 不存在｜fn_docs/vendor/ 不存在（无外购件）｜runs/ 交付空态｜fn_work/calibrations/ 未产出（【待实测】口径，按需创建）｜requirements.txt 15 包（演进轮 +markdown/playwright）与 .venv 可复建验证过（pyvenv.cfg --system-site-packages；pip check 3 条投诉全来自系统侧继承包，声明集内零投诉）｜外部依赖表 vue vendor/markdown/playwright 三行齐。

## 走查环留痕
首轮：21 通过 + Critical 1（EMC 真装配必败）/Important 3（sim 采集窗同根族）/Minor 3 → 修复 d554481（EMC 完整场景+sim 非发射态底噪块+钟域统一+判据窗镜像+场景名回落+stopped_at 回填；"monitor 恒空"口径作废申报入变更记录）→ scoped 复走查 **Critical 0/Important 0/Minor 0 清零**，交付态恢复（scenarios/runs 空态）。

## 已知限制（如实，终审参考）
sim 静默期数据为合成底噪（synthetic:noise_floor 标注）｜标定表【待实测】占位｜R72 run_id="." 只读无害过栏｜audit 伪块头同号顶替（本地工具）｜RL 收敛判据弱（已标注）｜AI 为轻量替身模型、sim 侧训练闭环需真机录音｜固件 PlatformIO 顺延（Ruling⑱）｜fn-doc-lint 解析器与演进文档格式脱节（308 错均证伪，独立核对替代）。

以上为终检事实，验收与否由用户判定。
