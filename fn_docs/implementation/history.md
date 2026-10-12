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
