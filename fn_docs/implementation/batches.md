# batches.md —— 批次表（待办导航）
> fn-implement 独占更新。▶ = 下一批要完成的任务；未经批间门批准不得增删批次内容。

| 批次 | 函数/任务清单 | 验收点 | 注 |
|---|---|---|---|
| ▶ B12 | compute_alignment_error, record_run_streams, run_baseline_check, annotate_truth_labels, write_sigmf_recording | 对齐绿（align_streams）；放行/中止（baseline_guard）；SigMF 往返（sigmf_record） | 采集对齐族 |
| B13 | check_failure, record_failure_level, execute_gb42590_protocol, compare_failure_boundaries, build_curve_frames, plot_triple_curves | 失效电平预期档±1（gb42590_executor）；定位（boundary_compare）；三图 PNG（triple_curves） | 测评族 |
| B14 | dispatch_remote_training, train_classifier, make_group_splits, grouped_cv_evaluate, predict_style | sanity 收敛+拒训（train_classifier）；无泄漏（grouped_cv）；识别（infer_service） | AI 族 |
| B15 | open_sim_siggen, open_sim_analyzer, upconvert_with_image_rejection, open_sim_mixer, open_sim_emi_receiver, open_sim_attenuator | 五模拟后端 wired（sim_1433d/sim_rsa513a/sim_mixer13g/sim_emi_receiver/sim_attenuator） | 远期仪表模拟族 |
| B16 | make_disclaimer_block, run_emc_conduction_sim, run_emc_radiation_sim, plan_frequency_sweep, run_emc_sweep | 三流程 wired+口径声明（emc_conduction/emc_radiation/emc_sweep） | EMC 模拟+共享声明 |
| B17 | locate_ledger_row, update_ledger, count_comment_ratio, audit_ledger, validate_scenario_schema, normalize_scenario, load_scenario | 台账写/自检绿（ledger_update/ledger_audit）；场景六非法拒（scenario_validate） | 台账+场景族 |
| B18 | render_disclaimer_sections, assemble_frequency_plots, build_report, extract_report_numbers, verify_report_traceability | 报告字段/口径/溯源绿（report_builder/report_traceability） | 报告族 |
| B19 | create_console_app, serve_console, build_scenario_cards, render_console_pages, measure_refresh_latency, trigger_emergency_stop, push_realtime_kpi | API 合约+急停+实时（console_api/console_ui/realtime_console） | Web 族 |
| B20 | map_per_to_injection, bridge_to_sitl, fallback_fixed_strategy, run_rl_policy, run_rff_pipeline | SITL 映射+RL 冒烟+RFF smoke（sitl_bridge/rl_policy/rff_pipeline） | 二期族（P1） |
| B21 | execute_scenario, run_demo | run_demo wired：sim 全流程 0 退出八件套+报告（demo_pipeline） | 终批总装 |

## 变更记录（计划层事件：签名微调、需求变更往返、放弃等）
| 日期 | 事件 | 说明 |
|---|---|---|
| 10-11 | 初建 22 批 | 119 函数全排入；依赖序=红线→标定→运行骨架→后端→样式→功率→监测→链路→采集→测评→AI→模拟仪表→EMC→台账场景→报告→Web→二期→总装 |
| 10-11 | Ruling①重排 22→21 批 | shared 四函数从独立 B1 移入首个调用方批次（wired 步需真实调用点：load_calibration_table→B2、stop_transmit_safely→B3、append_event→B8、make_disclaimer_block→B16）；批内顺序改自底向上（子先顶后）。原因：独立 shared 批内五步的 wired 不可合规达成。代价：无（函数总数与验收点不变） |
| 10-11 | Ruling②基线时序留痕 | 基线 429ae52 打在 B1 三叶子实现之后，叶实现被基线吞入——三个叶子 wired commit（88caee7/7fa737c/cee4b01）为零代码变更；终态正确、哈希与消息对应，代码真值在基线内 |
| 10-11 | Ruling③签名意图对齐 | guard_compliance 错误字段 ComplianceError→不抛出 rejected 返回式（与 R52 需求及实现一致，评审规格轴指出后当场对齐 fn-divide 文档） |
| 10-11 | Ruling④表格式 | build_gain_calibration 写 flat JSON（顶层=entries）——与 loader 顶层键校验兼容，placeholder 语义在 loader 视图；子代理实现时申报 |
| 10-11 | Ruling⑤评审附条件 | 签名意图对齐×2（不抛出语义）+gain 表单维明文化+探针入库 scripts/probes（B3 起） |
| 10-11 | Ruling⑥记账范围 | B4 波内代码被首函数提交收编（add -A），后续 wired 提交零代码（同 B1 型）；B5 起 per-fn commit 只 add 本函数路径 |
| 10-11 | Ruling⑦B5 双审 | configure 错误字段对齐；rx 溢出熔断语义 B8 复评；对抗 中3低9 全修（真机能力对齐：tx 天线仅 TX/RX、rx 增益≤76） |
| 10-11 | Ruling⑧B6 歧义取舍 | 谱图 frames 公式（期望值 7=1+ceil）；索引读 IO 失败≠损坏（写口径不被短路） |
| 10-11 | Ruling⑨B6 双审 | R29 空输入口径回写；中6低7 全修（真机时基链打通）；autodetect_backend.py 修复落点申报 |
| 10-11 | Ruling⑩B7 歧义裁定 | chirp 三角中点=峰值非中心（双侧四分点验证）；compose 分量等长严格拒 |
| 10-11 | Ruling⑪B7 双审 | 中5低7 全修+82 回归；探针 fs 参数随欠定域新口径更新 |
| 10-11 | Ruling⑫B8 申报 | synthesize 单参签名；style 键归注册表；衰减残差最优先 |
| 10-11 | Ruling⑬B8 双审 | R12 档位标定口径回写；高1中2低3 全修+26 回归 |
| 10-12 | Ruling⑭B9 勘误 | ladder link=−10 实为 4 档（提示算术错）；阶梯下发=|target| 作衰减；探针损耗改域内 |
| 10-12 | Ruling⑮B9 双审 | 中3低2 全修+11 回归（每轮 token/负损耗容错/增益地板如实/警告留痕/reason 细分） |
| 10-12 | Ruling⑯B10 双审 | 高1中1低4 全修+11 回归；泄漏表缓存语义取舍申报；B13 开批注意携带 JSR 接线条目 |
| 10-12 | Ruling⑰B11 分歧 | NRF/ESP config 形状/None-vs-0/坏帧阈 三处口径分歧申报待双审统一 |
| 10-12 | Ruling⑱B11 双审 | Ruling⑰ 三裁决落地+高1中3低3+ESP token；固件顺延集成批申报；预判反转留痕 |

