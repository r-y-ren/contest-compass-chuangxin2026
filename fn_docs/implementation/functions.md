# functions.md —— 函数级实现清单（唯一状态真值）
> fn-implement 独占更新。**代码是真值，本表只是导航。**
> **改任何状态前必须先跑核验命令、在对话中贴出输出，绿了才许改。**
> **改后读回贴出改后行（读回断言）：脚本/命令打印成功不算写入证据，落盘的字节才算。**

| 函数 | 批次 | 状态(日期) | 核验命令+摘要 | commit |
|---|---|---|---|---|
| check_power_cap | B1 | stub 10-11 | 上游覆盖: guard_compliance | — |
| check_band_whitelist | B1 | stub 10-11 | 上游覆盖: guard_compliance | — |
| check_env_declarations | B1 | stub 10-11 | 上游覆盖: guard_compliance | — |
| guard_compliance | B1 | stub 10-11 | pytest -k guard_compliance | — |
| load_calibration_table | B2 | stub 10-11 | 上游覆盖: lookup_jsr | — |
| lookup_jsr | B2 | stub 10-11 | pytest -k lookup_jsr | — |
| check_monotonicity | B2 | stub 10-11 | 上游覆盖: build_gain_calibration | — |
| build_gain_calibration | B2 | stub 10-11 | pytest -k build_gain_calibration | — |
| calibrate_leakage | B2 | stub 10-11 | pytest -k calibrate_leakage | — |
| compensate_link_power | B2 | stub 10-11 | pytest -k compensate_link_power | — |
| stop_transmit_safely | B3 | stub 10-11 | 上游覆盖: manage_run | — |
| create_run_workspace | B3 | stub 10-11 | 上游覆盖: manage_run | — |
| append_run_log | B3 | stub 10-11 | 上游覆盖: manage_run | — |
| finalize_run | B3 | stub 10-11 | 上游覆盖: manage_run | — |
| manage_run | B3 | stub 10-11 | pytest -k manage_run | — |
| register_backend | B4 | stub 10-11 | 上游覆盖: manage_backend_registry | — |
| lookup_backend | B4 | stub 10-11 | 上游覆盖: manage_backend_registry | — |
| manage_backend_registry | B4 | stub 10-11 | pytest -k manage_backend_registry | — |
| loopback_sim_stream | B4 | stub 10-11 | 上游覆盖: open_sim_backend | — |
| open_sim_backend | B4 | stub 10-11 | pytest -k open_sim_backend | — |
| read_sigmf_timeline | B4 | stub 10-11 | 上游覆盖: open_replay_backend | — |
| open_replay_backend | B4 | stub 10-11 | pytest -k open_replay_backend | — |
| configure_b210_channels | B5 | stub 10-11 | 上游覆盖: open_b210_backend | — |
| write_b210_tx_stream | B5 | stub 10-11 | 上游覆盖: open_b210_backend | — |
| read_b210_rx_stream | B5 | stub 10-11 | 上游覆盖: open_b210_backend | — |
| open_b210_backend | B5 | stub 10-11 | pytest -k open_b210_backend | — |
| exchange_scpi | B5 | stub 10-11 | 上游覆盖: create_visa_driver | — |
| create_visa_driver | B5 | stub 10-11 | pytest -k create_visa_driver | — |
| probe_uhd_devices | B6 | stub 10-11 | 上游覆盖: autodetect_backend | — |
| autodetect_backend | B6 | stub 10-11 | pytest -k autodetect_backend | — |
| probe_gpsdo_status | B6 | stub 10-11 | 上游覆盖: resolve_clock_reference | — |
| resolve_clock_reference | B6 | stub 10-11 | pytest -k resolve_clock_reference | — |
| make_spectrogram | B6 | stub 10-11 | pytest -k make_spectrogram | — |
| query_dataset | B6 | stub 10-11 | 上游覆盖: index_dataset | — |
| index_dataset | B6 | stub 10-11 | pytest -k index_dataset | — |
| check_style_params | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_tone | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_sweep | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_chirp | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_bandlimited_noise | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_partial_band | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| gen_pulse | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| compose_jamming | B7 | stub 10-11 | 上游覆盖: synthesize_style | — |
| append_event | B8 | stub 10-11 | 上游覆盖: set_channel_attenuation | — |
| synthesize_style | B8 | stub 10-11 | pytest -k synthesize_style | — |
| lookup_style_recipe | B8 | stub 10-11 | 上游覆盖: switch_style | — |
| switch_style | B8 | stub 10-11 | pytest -k switch_style | — |
| plan_attenuator_combo | B8 | stub 10-11 | 上游覆盖: set_channel_attenuation | — |
| set_channel_attenuation | B8 | stub 10-11 | pytest -k set_channel_attenuation | — |
| plan_ladder_steps | B9 | stub 10-11 | 上游覆盖: run_power_ladder | — |
| run_power_ladder | B9 | stub 10-11 | pytest -k run_power_ladder | — |
| compute_pathloss | B9 | stub 10-11 | 上游覆盖: map_distance_to_loss | — |
| map_distance_to_loss | B9 | stub 10-11 | pytest -k map_distance_to_loss | — |
| enforce_bandwidth_limit | B10 | stub 10-11 | 上游覆盖: capture_monitor_spectrum | — |
| capture_monitor_spectrum | B10 | stub 10-11 | pytest -k capture_monitor_spectrum | — |
| estimate_snr | B10 | stub 10-11 | 上游覆盖: compute_spectrum_stats | — |
| check_flatness | B10 | stub 10-11 | 上游覆盖: compute_spectrum_stats | — |
| compute_spectrum_stats | B10 | stub 10-11 | pytest -k compute_spectrum_stats | — |
| parse_esp32_frame | B11 | stub 10-11 | 上游覆盖: drive_esp32_link | — |
| drive_esp32_link | B11 | stub 10-11 | pytest -k drive_esp32_link | — |
| parse_nrf24_frame | B11 | stub 10-11 | 上游覆盖: drive_nrf24_link | — |
| drive_nrf24_link | B11 | stub 10-11 | pytest -k drive_nrf24_link | — |
| apply_cliff_model | B11 | stub 10-11 | 上游覆盖: simulate_link_degradation | — |
| simulate_link_degradation | B11 | stub 10-11 | pytest -k simulate_link_degradation | — |
| compute_per | B11 | stub 10-11 | 上游覆盖: normalize_kpi | — |
| normalize_kpi | B11 | stub 10-11 | pytest -k normalize_kpi | — |
| compute_alignment_error | B12 | stub 10-11 | 上游覆盖: record_run_streams | — |
| record_run_streams | B12 | stub 10-11 | pytest -k record_run_streams | — |
| run_baseline_check | B12 | stub 10-11 | pytest -k run_baseline_check | — |
| annotate_truth_labels | B12 | stub 10-11 | 上游覆盖: write_sigmf_recording | — |
| write_sigmf_recording | B12 | stub 10-11 | pytest -k write_sigmf_recording | — |
| check_failure | B13 | stub 10-11 | 上游覆盖: execute_gb42590_protocol | — |
| record_failure_level | B13 | stub 10-11 | 上游覆盖: execute_gb42590_protocol | — |
| execute_gb42590_protocol | B13 | stub 10-11 | pytest -k execute_gb42590_protocol | — |
| compare_failure_boundaries | B13 | stub 10-11 | pytest -k compare_failure_boundaries | — |
| build_curve_frames | B13 | stub 10-11 | 上游覆盖: plot_triple_curves | — |
| plot_triple_curves | B13 | stub 10-11 | pytest -k plot_triple_curves | — |
| dispatch_remote_training | B14 | stub 10-11 | 上游覆盖: train_classifier | — |
| train_classifier | B14 | stub 10-11 | pytest -k train_classifier | — |
| make_group_splits | B14 | stub 10-11 | 上游覆盖: grouped_cv_evaluate | — |
| grouped_cv_evaluate | B14 | stub 10-11 | pytest -k grouped_cv_evaluate | — |
| predict_style | B14 | stub 10-11 | pytest -k predict_style | — |
| open_sim_siggen | B15 | stub 10-11 | pytest -k open_sim_siggen | — |
| open_sim_analyzer | B15 | stub 10-11 | pytest -k open_sim_analyzer | — |
| upconvert_with_image_rejection | B15 | stub 10-11 | 上游覆盖: open_sim_mixer | — |
| open_sim_mixer | B15 | stub 10-11 | pytest -k open_sim_mixer | — |
| open_sim_emi_receiver | B15 | stub 10-11 | pytest -k open_sim_emi_receiver | — |
| open_sim_attenuator | B15 | stub 10-11 | pytest -k open_sim_attenuator | — |
| make_disclaimer_block | B16 | stub 10-11 | 上游覆盖: run_emc_conduction_sim | — |
| run_emc_conduction_sim | B16 | stub 10-11 | pytest -k run_emc_conduction_sim | — |
| run_emc_radiation_sim | B16 | stub 10-11 | pytest -k run_emc_radiation_sim | — |
| plan_frequency_sweep | B16 | stub 10-11 | 上游覆盖: run_emc_sweep | — |
| run_emc_sweep | B16 | stub 10-11 | pytest -k run_emc_sweep | — |
| locate_ledger_row | B17 | stub 10-11 | 上游覆盖: update_ledger | — |
| update_ledger | B17 | stub 10-11 | pytest -k update_ledger | — |
| count_comment_ratio | B17 | stub 10-11 | 上游覆盖: audit_ledger | — |
| audit_ledger | B17 | stub 10-11 | pytest -k audit_ledger | — |
| validate_scenario_schema | B17 | stub 10-11 | 上游覆盖: load_scenario | — |
| normalize_scenario | B17 | stub 10-11 | 上游覆盖: load_scenario | — |
| load_scenario | B17 | stub 10-11 | pytest -k load_scenario | — |
| render_disclaimer_sections | B18 | stub 10-11 | 上游覆盖: build_report | — |
| assemble_frequency_plots | B18 | stub 10-11 | 上游覆盖: build_report | — |
| build_report | B18 | stub 10-11 | pytest -k build_report | — |
| extract_report_numbers | B18 | stub 10-11 | 上游覆盖: verify_report_traceability | — |
| verify_report_traceability | B18 | stub 10-11 | pytest -k verify_report_traceability | — |
| create_console_app | B19 | stub 10-11 | 上游覆盖: serve_console | — |
| serve_console | B19 | stub 10-11 | pytest -k serve_console | — |
| build_scenario_cards | B19 | stub 10-11 | 上游覆盖: render_console_pages | — |
| render_console_pages | B19 | stub 10-11 | pytest -k render_console_pages | — |
| measure_refresh_latency | B19 | stub 10-11 | 上游覆盖: push_realtime_kpi | — |
| trigger_emergency_stop | B19 | stub 10-11 | 上游覆盖: push_realtime_kpi | — |
| push_realtime_kpi | B19 | stub 10-11 | pytest -k push_realtime_kpi | — |
| map_per_to_injection | B20 | stub 10-11 | 上游覆盖: bridge_to_sitl | — |
| bridge_to_sitl | B20 | stub 10-11 | pytest -k bridge_to_sitl | — |
| fallback_fixed_strategy | B20 | stub 10-11 | 上游覆盖: run_rl_policy | — |
| run_rl_policy | B20 | stub 10-11 | pytest -k run_rl_policy | — |
| run_rff_pipeline | B20 | stub 10-11 | pytest -k run_rff_pipeline | — |
| execute_scenario | B21 | stub 10-11 | 上游覆盖: run_demo | — |
| run_demo | B21 | stub 10-11 | pytest -k run_demo | — |
