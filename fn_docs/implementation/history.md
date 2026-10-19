# history.md —— 历史表（已完成批次队列，只追加不删改）
> fn-implement 独占更新。每批次完成后尾部追加留痕。

| 完成日期 | 批次 | 任务/函数清单（含操作与来源说明） | 验收摘要 |
|---|---|---|---|
| 10-11 | B1 | check_power_cap, check_band_whitelist, check_env_declarations, guard_compliance（3 叶并行子代理+顶层 1 子代理；Ruling×2 见 tracker） | 40 用例全绿；compliance_guard 7 用例；顶层实跑三条款拒；4 函数 commit+哈希补记 d5f0299 |
| 10-11 | B1+ | 批间用户裁决=缺陷审查后继续：对抗审查发现 2 高（NaN 功率/NaN cap 绕过红线）1 中（空白豁免）3 低 + 4 类盲区 → 修复+35 回归，75 用例全绿（fix commit 见 git） | 红线绕过全堵死；端到端 NaN/inf 拒绝 |
| 10-11 | B2 | load_calibration_table, check_monotonicity, calibrate_leakage（波1 并行）, lookup_jsr, build_gain_calibration, compensate_link_power（波2 并行）；Ruling④ flat JSON | 全库 223 用例绿；三顶层实跑探针过；6 函数 wired |
| 10-11 | B2+ | 批间用户裁决=漏洞审查后继续：对抗审查高7（异常逃逸家族：OverflowError/RecursionError/IsADirectoryError）中1（数值等价档摆动）低1（负容差）→ 全修复+24 回归；审查中子代理误删 fn_work 已 git 恢复（完整性复核 176 文件/223→247 绿） | 不抛出契约全恢复；同档数值等价去重 |
| 10-11 | B3 | stop_transmit_safely, create_run_workspace, append_run_log, finalize_run（波1 并行）, manage_run（波2） | 315 全库绿；manage_run 实跑 done+停发射+八件套；探针入库 scripts/probes |
| 10-11 | B3+ | 批间评审附 1 低危观察（降级缓冲→log_degraded 链不完整）→ wind_down 缓冲重放+滞留补正（manage_run 内最小侵入，不改 finalize） | 317 全库绿；重放/滞留两例新覆盖 |
| 10-11 | B3+ | 用户裁决二轮对抗审查：高2（跨运行缓冲污染/幂等跨运行失效跳停发射）中5（KI 安全路径/收尾兜底/终态冲突/NaN 字面量/回退序列化器回滚）低2 → 全修复+16 回归 | 333 全库绿；高危两项实测复测 PASS |
| 10-11 | B4 | register_backend, lookup_backend, loopback_sim_stream, read_sigmf_timeline（波1）, manage_backend_registry, open_sim_backend, open_replay_backend（波2） | 451 全库绿；注册表链探针（lookup sim→实例化→环回样本保真） |
| 10-11 | B4+ | 双审（三轴+对抗）：三轴附条件（replay 未自注册）+对抗 高1中4低4 → 九项全修复（replay 注册/BackendError 单源/溢出夹紧/NaN 拒/原子拒绝/大小写口径/streaming/speed/测试隔离），14 回归；Ruling⑥ 记账范围 | 465 全库绿；lookup(replay) 生产链路恢复 |
| 10-11 | B5 | configure_b210_channels, write_b210_tx_stream, read_b210_rx_stream, exchange_scpi（波1）, open_b210_backend, create_visa_driver（波2） | 574 全库绿；B210 真机在位（31B92DD）实开实测；Ruling⑥ per-fn commit 生效 |
| 10-11 | B5+ | 双审：三轴过门（2 观察）+对抗 中3低9 → 12 项全修复（BackendError 契约族/空转熔断/真机域对齐/校验边角），24 回归 | 602 全库绿（含真机）；Ruling⑦ 留痕 |
| 10-11 | B6 | probe_uhd_devices, probe_gpsdo_status, make_spectrogram, query_dataset（波1）, autodetect_backend, resolve_clock_reference, index_dataset（波2） | 699 全库绿；真机 auto→b210 实开；Ruling⑧ 两处歧义取舍 |
| 10-11 | B6+ | 双审：三轴过门（3 观察）+对抗 中6低8 → 13 项修复+23 回归；Ruling⑨（R29 口径回写） | 723 全库绿；真机 get_clock_source='internal' 时基链可达 |
| 10-11 | B7 | check_style_params, gen_tone, gen_sweep, gen_chirp（波1）, gen_bandlimited_noise, gen_partial_band, gen_pulse, compose_jamming（波2） | 1108 全库绿；六样式签名探针；Ruling⑩ 两处裁定 |
| 10-11 | B7+ | 双审：三轴过门（2 观察）+对抗 中5低7 → 12 项修复+82 回归；Ruling⑪ | 1190 全库绿 |
| 10-11 | B8 | append_event, lookup_style_recipe, plan_attenuator_combo（波1）, synthesize_style, switch_style, set_channel_attenuation（波2） | 1314 全库绿；三顶层探针（装配谱峰/切换 6ms/衰减下发+事件）；Ruling⑫ |
| 10-11 | B8+ | 双审：三轴过门（2 观察）+对抗 高1中2低3 → 6 项修复+26 回归；Ruling⑬ | 1340 全库绿 |
| 10-12 | B9 | plan_ladder_steps, compute_pathloss（波1）, run_power_ladder, map_distance_to_loss（波2） | 1494 全库绿；两顶层探针（失效即停/距离→损耗→组合）；Ruling⑭ |
| 10-12 | B9+ | 双审：三轴过门（1 观察留 B13 JSR 接线）+对抗 中3低2 → 5 项修复+11 回归；Ruling⑮ | 1505 全库绿 |
| 10-12 | B10 | enforce_bandwidth_limit, estimate_snr, check_flatness（波1）, capture_monitor_spectrum, compute_spectrum_stats（波2）+B9 两边界顺手修（_auto token/reason 优先级） | 1631 全库绿；探针谱峰定位 2438.1+SNR 19dB |
| 10-12 | B10+ | 双审：三轴过门（4 低观察）+对抗 高1中1低4 → 6 项修复+11 回归；Ruling⑯ | 1642 全库绿 |
| 10-12 | B11 | parse_esp32_frame, parse_nrf24_frame, apply_cliff_model, compute_per（波1）, drive_esp32_link, drive_nrf24_link, simulate_link_degradation, normalize_kpi（波2）+B10 空表边角顺手修 | 1792 全库绿；三源贯通探针（esp 0.20/nrf 0.45/sim 悬崖）；Ruling⑰ 三处分歧待双审 |
| 10-12 | B11+ | 双审：三轴过门（固件申报+ESP token）+对抗 高1中3低3 → 8 项修复+33 回归；Ruling⑰⑱ | 1825 全库绿 |
| 10-12 | B12 | compute_alignment_error, annotate_truth_labels, run_baseline_check（波1）, write_sigmf_recording（波2）, record_run_streams（波3）+esp 对齐修+read_samples 契约修（真缺陷，探针抓到） | 1917 全库绿；准闭环探针（kpi/stats/SigMF/基线）全过；Ruling⑲ |
| 10-12 | B12+ | 双审收口：中3低3 全修+13 回归；Ruling⑳ | 1930 全库绿 |
| 10-12 | B13 | check_failure, record_failure_level, compare_failure_boundaries, build_curve_frames（波1）, execute_gb42590_protocol, plot_triple_curves（波2） | 2020 全库绿；全链探针（GB failed+P_crit−20dB+三 PNG cjk+weakest 定位）——完整测评闭环成形 |
| 10-12 | B13+ | 双审：三轴全过+对抗 中1低5 → 6 项修复+10 回归；Ruling㉑ | 2030 全库绿 |
| 10-12 | B14 | make_group_splits, dispatch_remote_training, predict_style（波1）, train_classifier, grouped_cv_evaluate（波2） | 2118 全库绿；AI 管线探针（训练 48 两类/推理 tone 0.94/分组 CV F1=1.00 泄漏 False）；Ruling㉒ |
| 10-12 | B14+ | 双审：三轴过门（2 低观察）+对抗 中3低3 → 5 修 1 申报+18 回归；Ruling㉓ | 2136 全库绿 |
| 10-12 | B14++ | 修复后复核：5+1 全生效；2 新发现（饥饿吞泄漏/验收措辞）→ 当场修；Ruling㉔ | 2137 全库绿 |
| 10-12 | B15 | upconvert_with_image_rejection, open_sim_siggen, open_sim_analyzer, open_sim_emi_receiver, open_sim_attenuator（波1）, open_sim_mixer（波2） | 2266 全库绿；五后端链探针（13G 混频/±1.5dB/底噪公式/30dB 数学/1ppm）；Ruling㉕ |
| 10-12 | B15+ | 双审：三轴附条件过+对抗 中2低4 → 8 项修复+8 回归；Ruling㉖ | 2275 全库绿 |
| 10-12 | B16 | make_disclaimer_block, plan_frequency_sweep（波1）, run_emc_conduction_sim, run_emc_radiation_sim, run_emc_sweep（波2） | 2338 全库绿；EMC 三流程探针（dbuv 换算/洁净度/7 点扫频）；Ruling㉗ |
| 10-12 | B16+ | 双审：三轴过门（1 观察）+对抗 高1中2低3 → 7 项修复+19 回归；Ruling㉘ | 2362 全库绿 |
| 10-12 | B17 | locate_ledger_row, count_comment_ratio, validate_scenario_schema, normalize_scenario（波1）, update_ledger, audit_ledger, load_scenario（波2） | 2467 全库绿；台账探针（audit 100 条注释率 36%/写入往返）+场景红线联动；Ruling㉙ |
| 10-12 | B17+ | 双审：三轴过门（低2）+对抗 高1中4低4 → 修7申报2+24 回归；Ruling㉚（真清单状态列 append 方案——台账机制关键缺陷修复） | 2491 全库绿 |
| 10-12 | B18 | render_disclaimer_sections, assemble_frequency_plots, extract_report_numbers（波1）, build_report, verify_report_traceability（波2） | 2576 全库绿；报告链探针（各节齐/脚注 GB42590+PER/溯源 passed） |
| 10-12 | B18+ | 双审：三轴过门（3 观察）+对抗 高2中8低6 → 修13申报3+28 回归；Ruling㉛ | 2604 全库绿 |
| 10-12 | B18++ | 修复后复核：13/13 生效+等值盲区申报；Ruling㉜ | 2604 全库绿 |
| 10-12 | B19 | create_console_app, build_scenario_cards, measure_refresh_latency, trigger_emergency_stop（波1）, serve_console, render_console_pages, push_realtime_kpi（波2） | 2707 全库绿；Web 探针（dry_run+TestClient/Vue CDN 页/实时流）；Ruling㉝（装库暴露 6 真缺陷含 FastAPI annotations 注解解析） |
| 10-12 | B19+ | 双审：三轴修订后过门+对抗 中2低4 → 9 项修复+25 回归；Ruling㉞ | 2732 全库绿 |
| 10-12 | B20 | map_per_to_injection, fallback_fixed_strategy, bridge_to_sitl, run_rl_policy, run_rff_pipeline | 2765 全库绿；二期探针（SITL 注入表/固定策略 5 动作/RL ql_table 收敛）；Ruling㉟ |
| 10-12 | B20+ | 双审：三轴过门+对抗 中1低3 → 6 项修复+5 回归；Ruling㊱ | 2770 全库绿 |
| 10-12 | B21 | execute_scenario（波1）, run_demo（波2 终装）——**全员 wired 119/119、桩归零** | 2810 全库绿；真 --demo 实跑 exit 0（0.63s 八件套+报告+溯源 passed） |
| 10-12 | B21+ | 终批双审：三轴过门+对抗 高1中1低1+TX 真机 → 全修+74 回归；Ruling㊲——**21/21 批·119/119 函数 wired 收官** | 2884 全库绿 |
| 10-13 | B22 | write_b210_tx_stream np.complexfloating 修复（终检发现 1，真机验证零置零）+runs gitignore（发现 2） | 2890 全库绿；真机 1024 样本全量送达 |
| 10-13 | B23 | render_console_navigation（41 测）+render_console_pages 改造点①导航并入、mount_console_extensions（14 测）+create_console_app 改造点②一处接线+vendor 资产路由、localize_console_assets（console_offline 48+断网 e2e 8）+serve_console 七页装配（Ruling 第 3 触点） | R56 验收双绿（console_offline/console_pages_e2e）；全套件 3028 零回归；commits b72b261/d7000fc/401ccd8 |
| 10-13 | B24 | edit_scenario_ui（8+e2e 1）+render_triple_stream_charts（27）+stream_realtime_console（22+e2e 2 真sim）+harden_emergency_stop（12+族24）；改造点：serve_console runner 挂 hub+图区注入、create_console_app 停止路由委托；随批整改 I1 ws 防线+N1 守卫四形态 | R57-R59 验收全绿（scenario_editor_e2e/realtime_streams_e2e/emergency_stop）；全套件 3111 零回归；commits b125d10/a794e50/962e9f8/6c90e2b |
| 10-14 | B25 | render_report_html（31）+serve_run_artifacts（40+e2e 2）+list_run_summaries（14+e2e 3）+view_failure_comparison（13）；三端点+两页区+路由序手术（summaries 先于参数路由） | R60-R62 验收绿（report_view/report_center_e2e/boundary_view 族）；全套件 3225 零回归；commits 95cfe63/7b4854f/ad9eb38/8148d85 |
| 10-14 | B26 | browse_dataset_library（14+e2e 2）+build_replay_scenario（12）+launch_replay_run（21 含端到端）；R64 改造点 _backend_params 透传+数据页区 | R63/R64 验收绿（dataset_view_e2e/replay_run）；全套件 3296 零回归；commits 3885ed3/d755baa/9dc39e3 |
| 10-14 | B27 | 三函数（ai_train/eval/infer_view 11/10/13）+AI 页区+围栏 5 例+e2e 整改 | R65-R67 验收绿；全套件 3336 零回归；整批单提交 6097ba7 |
| 10-14 | B28 | demo_emc_flows+demo_instrument_panels（emc/instruments_view 10+10）+emc 子类型改造点+B27 随批补测；中断续做 | R68/R69 验收绿；全套件 3358+5skip 零回归；整批单提交 7c6eb8d |
| 10-14 | B29 | view_calibration_status+view_ledger_audit（15 测）+B28 随批 | R70/R71 验收绿；全套件 3375+5skip 零回归；整批单提交 af44c40 |
| 10-14 | B30 | demo_sitl_bridge+demo_rl_policy+demo_rff_pipeline（sitl/rl/rff_view 6+7+7）+B29 随批围栏/field；网络中断续做 | R72-R74 验收绿；全套件 3400+5skip 零回归；整批单提交 106a19a |
| 10-14 | B31 | audit_responsibility_alignment（6 测）+旧块回登记×4+资产件注+R72 围栏+B24 三观察 | R75 验收绿；桩归零 fn-check①PASS；全套件 3411+5skip；整批单提交 146d04d；域二十 25/25 完成 |
| B32 | seed_preset_scenarios, prewarm_demo_runs, prepare_demo_assets, check_demo_manual + 手册总章（87623e4/433e43e/e986122/d7ffabc/cace4ac；19+8 用例，全套件 3456 绿） | ①demo_assets 测试绿+prepare_demo_assets wired 实跑（临时目录物料真实生成）；②demo_manual_check 绿（总章期望集）；③总章=两档设备清单+ASCII 连接图+接线表+环境启动+演示前准备 | R76 全量；R84 检查器前置实现（期望集随批增长、FAQ 覆盖全集 B42 收口） |
| B33 | compose_esp32_frame, encode_esp32_frame, udp_stream_task, kpi_report_task, esp32_wifi_firmware（R85；9243754 整批单提交；37+4 用例+M3 加固 11 用例，全套件 3500 绿） | pio run tx/rx SUCCESS + dut_esp32 往返族全绿 + tests/firmware_esp32 镜像自证（fn-check③不扫 firmware 的盲区补偿） | R85；烧录联调随 R87；整批单提交（多函数单子代理惯例） |
| B34 | compose_nrf24_frame, encode_nrf24_frame, esb_traffic_task, counter_report_task, nrf24_link_firmware（R86；d430d65 整批单提交；31+5 用例+ARC/PLOS 口径申报；全套件 3544 绿） | pio run reporter/peer SUCCESS + dut_nrf24 往返族全绿 + tests/firmware_nrf24 镜像自证 | R86；同上 |
| B35 | 手册·测评核心五章（R77；五章四件套+两档标注；sim 走查真实退出码 1/0/1/0/0；期望集+5 硬门 passed=5） | 每章四件套+两档设备标注；章内命令 sim 侧逐条走查绿；check_demo_manual 期望集 +5 | R77 文档批 |
| B36 | 手册·记录与报告四章（R78；溯源 2048 traced+篡改点名实证；索引口径如实 SimBackend/样式靠显式登记；期望集+4 硬门 passed=9） | 同 B35 口径；期望集 +4 | R78 文档批 |
| B37 | 手册·AI 识别章（R79；dry_run 数据面+1<20 拒训+no_model 降级三态走查；期望集+1 硬门 passed=10） | 同上（训练走 dry_run/本地轻量演示路径）；期望集 +1 | R79 文档批 |
| B38 | 手册·模拟与扩展三章（R80；EMC 节实证+五表读数+replay 端到端 completed 走查；期望集+3 硬门 passed=13） | 同上；期望集 +3 | R80 文档批 |
| B39 | 手册·安全与台账二章（R81；三拒绝违例原文+台账副本 30 行实改+audit 100/100 走查；期望集+2 硬门 passed=15） | 同上（台账演示走 --ledger 副本清单）；期望集 +2 | R81 文档批 |
| B40 | 手册·二期进阶三章（R82 [P1]；SITL dry_run ok+RL 冒烟 ok+RFF 拒跑分支走查；期望集+3 硬门 passed=18） | 同上（dry_run/冒烟演示口径）；期望集 +3 | R82 文档批 [P1] |
| B41 | 手册·操控台八条目（R83；七页章+标定演示；七页 200 走查；期望集+8 硬门 passed=26） | 页面操作实起服务/playwright 走查绿；期望集 +8 | R83 文档批 |
| B42 | 手册附录+总装（R84 收口；应急表 FAQ 键全命中+检查器全等加固；全集硬门 ok=True passed=26 零遗漏零占位；全套件 3544 绿；批表清空=周期② B32–B42 全完成） | check_demo_manual 全集绿：26 条目四件套齐+两档标注齐+FAQ 覆盖零遗漏+零占位 | R84 收口 |
| B43 | 手册 v2 原子切换：总章重写（单一清单+大仪器替代节前置+唯一连接方案+0.4/0.5 修订）+26 章刷三件套+附录同步（应急表兜底/检查单单列）+改造点 check_demo_manual 契约 v2（三件套/删两档断言/防回潮/总章清单完整性+测试同步）+改造点 DEMO_CHECKLIST 单列化（+测试）+随批红#1（audit 快速通道阈值动态化） | 契约 v2 全集绿（passed=26 三件套+零占位+FAQ 零遗漏+防回潮零命中）；DEMO_CHECKLIST 单列报告实证；audit 红点清零；分离双审门（进行中）；整批提交 d7b8d6f | R90 单批原子切换（契约与手册互斥，分批必红）；批号协调——本批为本会话占用，并行缺陷批请续号 B44 起；红#2=B210 探测/打开不一致环境波动注记在案 |
| B44 | R88 子树：normalize_monitor_block（shared 上提，7 用例）+ _pull_tick/_make_tick_dwell_cb/tap_tx_window_blocks（25 用例，收编 25e3388）+ 改造点×4（record_run_streams prewindow 47 用例 12de3be / run_power_ladder dwell_cb 73 用例 40ca634 / _execute_stage stop 贯通 249dd93 / execute_gb42590_protocol tap 装配 d77a520+装配缝保护 805e5ae 48 用例）+ sim_delivery 交窗族 3 用例（8 绿）+ user-guide 两句随真值改写 + 手册点位清单（R90 v2 后坐标 L162/L237/L340/L547，供用户自改） | 交窗硬判据实测：录音首块=发射环回 tone（+27.7dB vs 底噪 -110dBm 级）、窗内 monitor 57344 行、tone/bandlimited_noise PAPR 差 12.17dB 可辨；急停 dwell 分片 0.60s 截断先行；replay 不启用；全套件 3603 passed 零失败（基线 3552+4F→R90 修红+本批新增）；对抗 0C/3I 全处置（I-1 措辞对齐+I-2 装配缝修复+I-3 判据换算登记入 requirements 变更记录）、M-1 发射窗缓冲无上界随 R87 真机批次设界 | R88 缺陷闭合 |
| B45 | R89 子树：_emc_conduction_md/_emc_radiation_md/_emc_sweep_md（11 用例，收编 bafa338）+ render_emc_flow_section 分发器（flow 标签优先/形状回推）+ 改造点×2（build_report 入口切换 263f81d——_emc_md 移除 60 用例；_report_payload 三形状映射 a528a9c——sweep 误挂传导标题口径缝端到端闭合）+ 端到端三流程 3 例（envelope 8 绿）+ 对抗处置 FIX=5d08609（I-1 空 detector 守卫+I-2 脚注回退随 flow+M-1 zip 不齐注记，74 绿） | 三流程端到端 report.md 要素齐全（传导四列+passed 判定/辐射 16 行谱表+洁净度+补偿/扫频点表+spurious，标题随流程）；全套件 3622 passed 零失败；三轴 PASS+对抗 0C/2I/6M（2I+M1 已修，M-3 文档登记在案，M-2 空字典回推标题/M-5 spurious 字面量/M-6 延迟私有导入=口径注记登记不追）；验收点「两流程」实交付三流程（含 sweep 回归）随记 | R89 缺陷闭合；批表清空=演进轮③ B44–B45 全完成 |
| B46 | 手册四处修订（0.1 清单行细分/0.2 TRX1·RX2 真端口重写+MMCX 归位/0.3 FPGA 三事实步/边界表与残留清扫）+改造点 DEMO_CHECKLIST 第 9 行细分（18→19 项+测试同步） | 旧接法 grep -qE 零命中；契约 v2 八键绿；DEMO_CHECKLIST 报告 19 项实证；分离双审门（进行中）；整批提交 c7e4369 | R94 单批轻量；批号协调——并行演进轮④（R91-R93 识别器批）续 B47 起；B210 说明 PDF 已登记参考资料 |
| B47 | R91+R92 子树：spectral_template_match（shared 新上提，0d0cdfe）+_signal_features/_extract_gate_segments/_rule_decision（三叶提出，77afff5/447ed3a/b048e56）+_template_classify（1bb61cd）+_classify_dummy 门控感知改造（8013afd：连续分流 0.9/最长单段≥3nfft/两层门控兜底/features 扩键）+_predict_one 模板分流改造（f2b6913：含 _load_model 顶层模板规整·快速通道）+predict_style 顶层 docstring（263c506）+门处置（0368f0b）；Ruling 行=段内判据最长单段（防碎片拼接误判） | R91 六样式识别器级硬判全对（tone 0.943/sweep 0.700/chirp 0.750/noise 0.837/partial 0.550/pulse 0.901 兜底）+composite 弱判；R92 真链用例（rebuild→local→模型文件→识别 6/6）+合成版；防退化（合成短脉冲仍 pulse/连续仍原类）；全套件 3690 绿；三轴 PASS 附条件+对抗 0C/3I/5M 全处置（I-1 真链补齐/I-2 回退 note/I-3 NaN 拒收）；用户裁决「继续下一批」（2026-10-15） | R91+R92 识别准确率协同改造；批号协调=并行 R94 批占 B46 |
| B49 | prepare_demo_assets[改造]（fn-close 走查环 F1：预跑与种子冲突解耦；0e77e83）——早退守卫删除（冲突未授权也照常预跑）、refused_conflicts 键作废删除（消费方=本体+tests 同步）、docstring/注释改解耦契约；测试 19→21：交付形态新用例（预置仓内七场景+空 runs_root→conflicts=7+prewarm 非空+字节不变）+② ②b 旧早退用例按新契约改写（注释说明理由） | 定向 21 passed；顶层实跑双口径（仓内 conflicts=7+prewarm 9 轮+场景字节不变 / 空临时目录 written=7+prewarm 9 轮照旧）；全套件 3708 passed/5 skipped 零失败；三轴+对抗内联真命令（派发无子代理通道，如实登记） | 走查环显式修复派发；裁决面=fn-close 走查环（返回报告即回裁决面）；不碰手册（主会话同步） |
| B48 | R93 子树：make_predict_style_callbacks（对齐回调；3964f65+回补）+ grouped_cv_evaluate[改造]（R93 口径标注+对齐回调；5b88d6b——含责任块调用方勘误：真实调用面=view_cv_evaluation.py:24+run_rff_pipeline.py:37，旧块「train_classifier 训练后评测」为 c1 期失准）+ view_cv_evaluation[改造]（R93 默认注入 aligned_template；e33e80b） | tests/grouped_cv_evaluate → 53 passed（六类全对角 macro_f1==1.0/缺省 intrinsic_dummy 锚/对齐回调可分）+tests/view_cv_evaluation → 14 passed；全套件 3703 绿；门双审处置在案（三轴 S-1/I-1/S-2/I-2/A-1/M-1/M-3/M-4+对抗 0C/2I/7M；R93 验收补全登记=requirements 变更记录 10-16：特征向量级六类用例承载+eval_protocol 上屏+query protocol 键） | R93 评测口径对齐推理口径；**本行为 2026-10-17 对账补记**——原归档步被跳过（批表 ▶ 行滞留+本表缺行），随演进轮⑤进入第④步修复；证据=functions.md B48 三行 wired+git 三哈希在库 |
| B50 | get_tx_gain[新]（22982f2——读回优先/跟踪回退/异常透传三语义+_METHOD_NAMES 五名+register_backend._OPTIONAL_METHOD_NAMES 词汇表扩名=Ruling B50①）+记账收口（d4f64a9） | pytest -k get_tx_gain → 8 passed；邻域四目录 274 绿；全量 3721 passed/0 skip（3713+8）；三轴 12 判据全过+对抗 0C/1I/4M（I1 勘误 :1806；M1-M3 转 B51；M4 观察项）；用户裁决「继续」（10-17） | R96 地基；落序第一；批表移行本行即真值（脚本误标 B51 行已当场修复） |
| B51 | R95 映射四单元：resolve_base_tx_gain（be727a0）+_dispatch_backend 形态②正增益+M1/M2/M3（22b84f2）+双白名单 schema/run_demo（338a10a）+对抗 C1 修复 _ensure_b210_tx_gain effective 注入+I4/M1（d32c196）+门档（f23e98d） | pytest -k b210_gain_mapping → 10 绿；全量 3775 passed/0 failed（3721+54）；三轴 10 PASS/2 部分（I2/M2 同源已修）；对抗 1C/4I/4M 全处置——C1=注入判定解耦场景键字面（selection 真值补设）、I2/I3 档案勘误、I1+M4 口径入 requirements、I4 normalize 数值化、M1 bool 拒、M3 登记；scoped 复审 5PASS 但"stop_tx 独立补证"为假账——仓内失败路径用例抓获后代码兑现+勘误；用户裁决「继续」（10-17） | R95 映射；6 旧断言随语义改写；sim 零扰动三证（零 diff+42 绿+实跑 unknown_gain 在位） |
| B52 | R97 记账如实化两单元：_dispatch_backend 事件 tx_gain_db/coarse_semantics='gain_budget' 双列+applied_via 入事件体（I1 承接）+sim 零变化三重保证（9321127）+门档（462cdfd） | pytest -k attenuation_truthful → 4 绿；全量 3781 passed/0 failed 双源；三轴 13/13；对抗 0C/1I/4M——I-1 git index 被置旧 blob（根因未明环境异常）复位三证+MM 常设自检，M-1 转 B53/M-2 修/M-3·M-4 登记；变异测试实证反断言真拦；用户裁决「继续B53」（10-17） | R97 语义；脚注内联定桩（条件判据 make_disclaimer_block 不承载）；旧键集断言改写必要性数学实证 |
| B53 | 真机最小实证：真机轮重跑（runs/20261019-142850，事件双列全绿+unknown_gain 清零）+A/B/C 三相位物理判据（顶档 +67.0dB≥15 判据 4.5 倍余量/六档单调 43.1→67.0/旧缺陷对照+30.3dB）+overflow 全 0+M-4 回读 set==get+M-1 键集钉住（dec987f）+实证入档（0140762/c360b4c，机读 JSON） | 三轴 13/13+对抗 0C/2I/3M 全处置（I-1 机读档案/I-2 跨实验标度注记/M-A·M-B 勘误/M-C 转 R87）；run-path monitor 窗口结构性发现（Ruling+requirements 口径行，R87 归位）；全量 3782 passed/0 failed；LED=用户豁免/延后（offered 选项，谱判据承载）；用户裁决=调用 /fn-close（收口载体） | 演进轮⑤终批——R95–R97 全批完成（B50–B53），批表清空 |
