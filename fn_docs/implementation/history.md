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
