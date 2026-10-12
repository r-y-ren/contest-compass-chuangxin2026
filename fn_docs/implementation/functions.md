# functions.md —— 函数级实现清单（唯一状态真值）
> fn-implement 独占更新。**代码是真值，本表只是导航。**
> **改任何状态前必须先跑核验命令、在对话中贴出输出，绿了才许改。**
> **改后读回贴出改后行（读回断言）：脚本/命令打印成功不算写入证据，落盘的字节才算。**

| 函数 | 批次 | 状态(日期) | 核验命令+摘要 | commit |
|---|---|---|---|---|
| check_power_cap | B1 | wired 10-11 | pytest tests/guard_compliance/test_check_power_cap.py → 17 passed；调用点 guard_compliance.py:52 | 88caee7 |
| check_band_whitelist | B1 | wired 10-11 | pytest → 9 passed；调用点 guard_compliance.py | 7fa737c |
| check_env_declarations | B1 | wired 10-11 | pytest → 7 passed；调用点 guard_compliance.py | cee4b01 |
| guard_compliance | B1 | wired 10-11 | pytest -k compliance_guard → 7 passed；目录 40 passed；实跑三条款拒 | 15e55eb |
| load_calibration_table | B2 | wired 10-11 | 16 passed；调用点 lookup_jsr.py:83 + compensate_link_power.py:78 | 74fc657 |
| lookup_jsr | B2 | wired 10-11 | 11 passed；顶层实跑状态机四态 | 8d36398 |
| check_monotonicity | B2 | wired 10-11 | 34 passed；调用点 build_gain_calibration.py | 3ddcd27 |
| build_gain_calibration | B2 | wired 10-11 | 16 新用例（目录 50）；建表→loader 读回集成 | 88ebaaa |
| calibrate_leakage | B2 | wired 10-11 | 10 passed；顶层实跑 subtract 未扣除路径 | 3fc2907 |
| compensate_link_power | B2 | wired 10-11 | 11 passed；公式(6) 实跑 -35.4dB 断言 | 1adffb9 |
| stop_transmit_safely | B3 | wired 10-11 | 18 passed；调用点 manage_run.py | 64db422 |
| create_run_workspace | B3 | wired 10-11 | 10 passed；八件套骨架 | 21438d9 |
| append_run_log | B3 | wired 10-11 | 11 passed；行级落盘+环形缓冲降级 | 1180b83 |
| finalize_run | B3 | wired 10-11 | 18 passed；result.json+missing 清单 | b77903d |
| manage_run | B3 | wired 10-11 | 12 passed；实跑 done+停发射+八件套 | 6156e9b |
| register_backend | B4 | wired 10-11 | 15 passed；调用点 manage_backend_registry.py | abd0680 |
| lookup_backend | B4 | wired 10-11 | 28 passed；别名+相近名提示 | 70fa979 |
| manage_backend_registry | B4 | wired 10-11 | 11 passed；实跑注册表链 | 2298078 |
| loopback_sim_stream | B4 | wired 10-11 | 22 passed；四效应+夹紧+种子复现 | 50e877e |
| open_sim_backend | B4 | wired 10-11 | 16 passed；REGISTRY 自注册+鸭子接口 | 16ce2cd |
| read_sigmf_timeline | B4 | wired 10-11 | 16 passed；三 datatype 手写解析 | 88c288b |
| open_replay_backend | B4 | wired 10-11 | 13 passed；急切校验+no_tx 语义 | e2853ca |
| configure_b210_channels | B5 | wired 10-11 | 23 passed；域校验+回读容差+NaN 拒 | c782435 |
| write_b210_tx_stream | B5 | wired 10-11 | 11 passed；欠载熔断+元素规整 | f36dddc |
| read_b210_rx_stream | B5 | wired 10-11 | 12 passed；溢出熔断+惰性 | 5ec4459 |
| open_b210_backend | B5 | wired 10-11 | 26 passed 含真机 open/close；注入传输适配 | 14aef7a |
| exchange_scpi | B5 | wired 10-11 | 20 passed；四类解析+Timeout 重试 | 14ceea2 |
| create_visa_driver | B5 | wired 10-11 | 19 passed；三型号映射+注入会话 | cb4c63a |
| probe_uhd_devices | B6 | wired 10-11 | 9 passed 含真机；永不抛出 | 3e0d515 |
| autodetect_backend | B6 | wired 10-11 | 18 passed 含真机 auto 实开；三态决策 | 6c12605 |
| probe_gpsdo_status | B6 | wired 10-11 | 20 passed；传感器序列探测 | d4cbdf9 |
| resolve_clock_reference | B6 | wired 10-11 | 13 passed；三时基+驯服降级 | 64e4283 |
| make_spectrogram | B6 | wired 10-11 | 12 passed；纯 numpy STFT | 5a2f4d9 |
| query_dataset | B6 | wired 10-11 | 15 passed；AND 过滤+批次分组 | 627ca94 |
| index_dataset | B6 | wired 10-11 | 14 passed；四动作+自愈 rebuild | 1b1bbbf |
| check_style_params | B7 | wired 10-11 | 65 passed；六样式域+红线 | 0d84adc |
| gen_tone | B7 | wired 10-11 | 36 passed；FFT 峰 bin±1 | 13d9392 |
| gen_sweep | B7 | wired 10-11 | 29 passed；相位连续+瞬时频率 | 0030ad2 |
| gen_chirp | B7 | wired 10-11 | 33 passed；跨周期相位连续 | ae433a0 |
| gen_bandlimited_noise | B7 | wired 10-11 | 58 passed；平坦度≤4dB 实测 | 15bc852 |
| gen_partial_band | B7 | wired 10-11 | 66 passed；占比+带容约束 | 6d8a229 |
| gen_pulse | B7 | wired 10-11 | 64 passed；门控+跨脉冲相位连续+fmod 加固 | 8b1a58c |
| compose_jamming | B7 | wired 10-11 | 34 passed；公式(1) 程序化 | 259b8e7 |
| append_event | B8 | wired 10-11 | 21 passed；单调钟 ts+NaN 占位+显式抛 | b9f1e48 |
| synthesize_style | B8 | wired 10-11 | 23 passed；六样式+composite 签名单参（Ruling⑫） | 88ca590 |
| lookup_style_recipe | B8 | wired 10-11 | 14 passed；六配方+扩展点 | 9d67678 |
| switch_style | B8 | wired 10-11 | 15 passed；六样式切换<2s 实测毫秒级 | dca9f74 |
| plan_attenuator_combo | B8 | wired 10-11 | 39 passed；残差最优先（Ruling⑫） | 7af2220 |
| set_channel_attenuation | B8 | wired 10-11 | 15 passed；鸭子下发+事件真值+可达域 | 1e58df2 |
| plan_ladder_steps | B9 | wired 10-12 | 36 passed；GB 口径+红线截断 | 2139a4f |
| run_power_ladder | B9 | wired 10-12 | 56 passed；失效即停+异常先停发射 | 577c21d |
| compute_pathloss | B9 | wired 10-12 | 60 passed；公式(3)+per-call 抽样 | deeadd0 |
| map_distance_to_loss | B9 | wired 10-12 | 40 passed；不可达点如实标注 | 6c20b6f |
| enforce_bandwidth_limit | B10 | wired 10-12 | 34 passed；分段无缝+能力域拒 | 8fb1eb4 |
| capture_monitor_spectrum | B10 | wired 10-12 | 16 passed；块级谱+分段+自漏扣除 | 14d3296 |
| estimate_snr | B10 | wired 10-12 | 31 passed；公式(4)+guard 防泄漏 | 4c105d7 |
| check_flatness | B10 | wired 10-12 | 26 passed；≤4dB 判据（EN 300 328） | 5484d1a |
| compute_spectrum_stats | B10 | wired 10-12 | 16 新用例（目录 73）；full/power_only/JSR 双口径 | c08f46d |
| parse_esp32_frame | B11 | wired 10-12 | 34 passed；校验和+域校验 | 88023ce |
| drive_esp32_link | B11 | wired 10-12 | 17 passed；坏帧超阈先停发射 | 41aa996 |
| parse_nrf24_frame | B11 | wired 10-12 | 13 passed；无 rssi 口径 | 47482fc |
| drive_nrf24_link | B11 | wired 10-12 | 15 passed；口径分歧 Ruling⑰ | 4430fa5 |
| apply_cliff_model | B11 | wired 10-12 | 23 passed；sigmoid 悬崖+夹紧 | 2325a9c |
| simulate_link_degradation | B11 | wired 10-12 | 13 passed；JSR 三级推导 | a83b562 |
| compute_per | B11 | wired 10-12 | 17 passed；样本量警告口径 | 88d76f6 |
| normalize_kpi | B11 | wired 10-12 | 20 passed；异源冲突拒+BER 口径声明 | 7198a3e |
| compute_alignment_error | B12 | wired 10-12 | 28 passed；配对时延 p50/p95 | 48417e1 |
| record_run_streams | B12 | wired 10-12 | 15 passed 含真后端 E2E；三路合流总编 | 8ee48b6 |
| run_baseline_check | B12 | wired 10-12 | 16 passed；保守拒+advice | 204e78c |
| annotate_truth_labels | B12 | wired 10-12 | 21 passed；SigMF v1.2+jam 命名空间 | 39faa47 |
| write_sigmf_recording | B12 | wired 10-12 | 13 新用例（-k 34）；流式 cf32+完整性校验 | dc5f59d |
| check_failure | B13 | wired 10-12 | 18 passed；≥口径+样本不足保守 | 045c456 |
| record_failure_level | B13 | wired 10-12 | 11 passed；电平回退+missing 如实 | 8802c25 |
| execute_gb42590_protocol | B13 | stub 10-11 | pytest -k gb42590_executor | — |
| compare_failure_boundaries | B13 | wired 10-12 | 12 passed；中位数聚合+平手规则 | pending |
| build_curve_frames | B13 | stub 10-11 | 上游覆盖: plot_triple_curves | — |
| plot_triple_curves | B13 | stub 10-11 | pytest -k triple_curves | — |
| dispatch_remote_training | B14 | stub 10-11 | 上游覆盖: train_classifier | — |
| train_classifier | B14 | stub 10-11 | pytest -k train_classifier | — |
| make_group_splits | B14 | stub 10-11 | 上游覆盖: grouped_cv_evaluate | — |
| grouped_cv_evaluate | B14 | stub 10-11 | pytest -k grouped_cv | — |
| predict_style | B14 | stub 10-11 | pytest -k infer_service | — |
| open_sim_siggen | B15 | stub 10-11 | pytest -k sim_1433d | — |
| open_sim_analyzer | B15 | stub 10-11 | pytest -k sim_rsa513a | — |
| upconvert_with_image_rejection | B15 | stub 10-11 | 上游覆盖: open_sim_mixer | — |
| open_sim_mixer | B15 | stub 10-11 | pytest -k sim_mixer13g | — |
| open_sim_emi_receiver | B15 | stub 10-11 | pytest -k sim_emi_receiver | — |
| open_sim_attenuator | B15 | stub 10-11 | pytest -k sim_attenuator | — |
| make_disclaimer_block | B16 | stub 10-11 | 上游覆盖: run_emc_conduction_sim | — |
| run_emc_conduction_sim | B16 | stub 10-11 | pytest -k emc_conduction | — |
| run_emc_radiation_sim | B16 | stub 10-11 | pytest -k emc_radiation | — |
| plan_frequency_sweep | B16 | stub 10-11 | 上游覆盖: run_emc_sweep | — |
| run_emc_sweep | B16 | stub 10-11 | pytest -k emc_sweep | — |
| locate_ledger_row | B17 | stub 10-11 | 上游覆盖: update_ledger | — |
| update_ledger | B17 | stub 10-11 | pytest -k ledger_update | — |
| count_comment_ratio | B17 | stub 10-11 | 上游覆盖: audit_ledger | — |
| audit_ledger | B17 | stub 10-11 | pytest -k ledger_audit | — |
| validate_scenario_schema | B17 | stub 10-11 | 上游覆盖: load_scenario | — |
| normalize_scenario | B17 | stub 10-11 | 上游覆盖: load_scenario | — |
| load_scenario | B17 | stub 10-11 | pytest -k scenario_validate | — |
| render_disclaimer_sections | B18 | stub 10-11 | 上游覆盖: build_report | — |
| assemble_frequency_plots | B18 | stub 10-11 | 上游覆盖: build_report | — |
| build_report | B18 | stub 10-11 | pytest -k report_builder | — |
| extract_report_numbers | B18 | stub 10-11 | 上游覆盖: verify_report_traceability | — |
| verify_report_traceability | B18 | stub 10-11 | pytest -k report_traceability | — |
| create_console_app | B19 | stub 10-11 | 上游覆盖: serve_console | — |
| serve_console | B19 | stub 10-11 | pytest -k console_api | — |
| build_scenario_cards | B19 | stub 10-11 | 上游覆盖: render_console_pages | — |
| render_console_pages | B19 | stub 10-11 | pytest -k console_ui | — |
| measure_refresh_latency | B19 | stub 10-11 | 上游覆盖: push_realtime_kpi | — |
| trigger_emergency_stop | B19 | stub 10-11 | 上游覆盖: push_realtime_kpi | — |
| push_realtime_kpi | B19 | stub 10-11 | pytest -k realtime_console | — |
| map_per_to_injection | B20 | stub 10-11 | 上游覆盖: bridge_to_sitl | — |
| bridge_to_sitl | B20 | stub 10-11 | pytest -k sitl_bridge | — |
| fallback_fixed_strategy | B20 | stub 10-11 | 上游覆盖: run_rl_policy | — |
| run_rl_policy | B20 | stub 10-11 | pytest -k rl_policy | — |
| run_rff_pipeline | B20 | stub 10-11 | pytest -k rff_pipeline | — |
| execute_scenario | B21 | stub 10-11 | 上游覆盖: run_demo | — |
| run_demo | B21 | stub 10-11 | pytest -k demo_pipeline | — |
