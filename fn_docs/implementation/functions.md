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
| check_style_params | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_tone | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_sweep | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_chirp | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_bandlimited_noise | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_partial_band | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_pulse | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| compose_jamming | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| append_event | B8 | stub 10-11 | 上游覆盖: set_channel_attenuation | — |
| synthesize_style | B8 | stub 10-11 | pytest -k styles_synth | — |
| lookup_style_recipe | B8 | stub 10-11 | 上游覆盖: switch_style | — |
| switch_style | B8 | stub 10-11 | pytest -k styles_switch | — |
| plan_attenuator_combo | B8 | stub 10-11 | 上游覆盖: set_channel_attenuation | — |
| set_channel_attenuation | B8 | stub 10-11 | pytest -k channel_ladder | — |
| plan_ladder_steps | B9 | stub 10-11 | 上游覆盖: run_power_ladder | — |
| run_power_ladder | B9 | stub 10-11 | pytest -k power_ladder | — |
| compute_pathloss | B9 | stub 10-11 | 上游覆盖: map_distance_to_loss | — |
| map_distance_to_loss | B9 | stub 10-11 | pytest -k pathloss_map | — |
| enforce_bandwidth_limit | B10 | stub 10-11 | 上游覆盖: capture_monitor_spectrum | — |
| capture_monitor_spectrum | B10 | stub 10-11 | pytest -k monitor_capture | — |
| estimate_snr | B10 | stub 10-11 | 上游覆盖: compute_spectrum_stats | — |
| check_flatness | B10 | stub 10-11 | 上游覆盖: compute_spectrum_stats | — |
| compute_spectrum_stats | B10 | stub 10-11 | pytest -k spectrum_stats | — |
| parse_esp32_frame | B11 | stub 10-11 | 上游覆盖: drive_esp32_link | — |
| drive_esp32_link | B11 | stub 10-11 | pytest -k dut_esp32 | — |
| parse_nrf24_frame | B11 | stub 10-11 | 上游覆盖: drive_nrf24_link | — |
| drive_nrf24_link | B11 | stub 10-11 | pytest -k dut_nrf24 | — |
| apply_cliff_model | B11 | stub 10-11 | 上游覆盖: simulate_link_degradation | — |
| simulate_link_degradation | B11 | stub 10-11 | pytest -k dut_sim | — |
| compute_per | B11 | stub 10-11 | 上游覆盖: normalize_kpi | — |
| normalize_kpi | B11 | stub 10-11 | pytest -k kpi_model | — |
| compute_alignment_error | B12 | stub 10-11 | 上游覆盖: record_run_streams | — |
| record_run_streams | B12 | stub 10-11 | pytest -k align_streams | — |
| run_baseline_check | B12 | stub 10-11 | pytest -k baseline_guard | — |
| annotate_truth_labels | B12 | stub 10-11 | 上游覆盖: write_sigmf_recording | — |
| write_sigmf_recording | B12 | stub 10-11 | pytest -k sigmf_record | — |
| check_failure | B13 | stub 10-11 | 上游覆盖: execute_gb42590_protocol | — |
| record_failure_level | B13 | stub 10-11 | 上游覆盖: execute_gb42590_protocol | — |
| execute_gb42590_protocol | B13 | stub 10-11 | pytest -k gb42590_executor | — |
| compare_failure_boundaries | B13 | stub 10-11 | pytest -k boundary_compare | — |
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
