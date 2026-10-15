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
| execute_gb42590_protocol | B13 | wired 10-12 | 13 passed；五阶段编排+带宽校验+判据接线 | 1c77700 |
| compare_failure_boundaries | B13 | wired 10-12 | 12 passed；中位数聚合+平手规则 | c2b6a96 |
| build_curve_frames | B13 | wired 10-12 | 24 passed；三帧纯计算+开窗 | 5044bd0 |
| plot_triple_curves | B13 | wired 10-12 | 12 passed；三 PNG+curves_data.json+字体回退 | 49e4665 |
| dispatch_remote_training | B14 | wired 10-12 | 19 passed；探活+dry_run+形状稳定 | 5a65d34 |
| train_classifier | B14 | wired 10-12 | 15 新用例；取数→谱→样本量→remote/local | b2fca5e |
| make_group_splits | B14 | wired 10-12 | 20 passed；组粒度贪心均衡 | ba54c94 |
| grouped_cv_evaluate | B14 | wired 10-12 | 20 新用例；混淆+F1+泄漏自检 | f08eb2a |
| predict_style | B14 | wired 10-12 | 17 passed；cnn_dummy+全状态机不抛 | 61716a4 |
| open_sim_siggen | B15 | wired 10-12 | 15 passed；0.5dB 量化+1ppm+SCPI 复用 | da76f24 |
| open_sim_analyzer | B15 | wired 10-12 | 13 passed；DPX+±1.5dB 确定性偏差 | e40bed3 |
| upconvert_with_image_rejection | B15 | wired 10-12 | 59 passed；公式(2)+镜像+杂散 | 2069ccf |
| open_sim_mixer | B15 | wired 10-12 | 14 passed；13G 链+beyond_model+IQ 搬移 | 44b6d49 |
| open_sim_emi_receiver | B15 | wired 10-12 | 13 passed；三检波+CISPR 声明 | f7a5302 |
| open_sim_attenuator | B15 | wired 10-12 | 20 passed；0.25 网格+真衰减数学 | 0579c65 |
| make_disclaimer_block | B16 | wired 10-12 | 12 passed；三场景统一声明源 | ca121ba |
| run_emc_conduction_sim | B16 | wired 10-12 | 10 passed；LISN 模拟+dbuv+margin | eba4e8b |
| run_emc_radiation_sim | B16 | wired 10-12 | 8 passed；谱+补偿+洁净度 | f969249 |
| plan_frequency_sweep | B16 | wired 10-12 | 27 passed；双刻度+CISPR 频段 | 897ec62 |
| run_emc_sweep | B16 | wired 10-12 | 9 passed；点表编排+spurious 标记 | 002e308 |
| locate_ledger_row | B17 | wired 10-12 | 19 passed；边界正则+状态列解析 | 5963f4e |
| update_ledger | B17 | wired 10-12 | 17 passed；原子写+覆盖守卫 | da40f7d |
| count_comment_ratio | B17 | wired 10-12 | 14 passed；tokenize 注释+docstring | 629df88 |
| audit_ledger | B17 | wired 10-12 | 12 passed；死锚核验+注释率 | 1841af8 |
| validate_scenario_schema | B17 | wired 10-12 | 21 passed；七类白名单+域 | 957d0f2 |
| normalize_scenario | B17 | wired 10-12 | 9 passed；默认填充+归一+深拷贝 | 227b1a6 |
| load_scenario | B17 | wired 10-12 | 16 passed；校验→红线→规范化 | 3775208 |
| render_disclaimer_sections | B18 | wired 10-12 | 33 passed；基座+上下文+模拟段 | f4ac207 |
| assemble_frequency_plots | B18 | wired 10-12 | 15 passed；≥5 位+缺额如实 | d92fac9 |
| build_report | B18 | wired 10-12 | 17 passed；总装+缺项+PNG 复用 | e8b6f31 |
| extract_report_numbers | B18 | wired 10-12 | 24 passed；单位家族+科学计数 | 1b0cdb4 |
| verify_report_traceability | B18 | wired 10-12 | 17 passed；候选串+口径白名单 | 6672e9a |
| create_console_app | B19 | wired 10-12 | 25 实跑；五路由+WS+400 指错 | 5c55ef3 |
| serve_console | B19 | wired 10-12 | 25 passed；dry_run+延迟 uvicorn | 24c66e8 |
| build_scenario_cards | B19 | wired 10-12 | 12 passed；损坏跳过+error 卡 | 2e01e28 |
| render_console_pages | B19 | wired 10-12 | 15 passed；单文件 HTML+CDN | 6915fd7 |
| measure_refresh_latency | B19 | wired 10-12 | 8 passed；配对分位+pending | d6d4c07 |
| trigger_emergency_stop | B19 | wired 10-12 | 7 passed；先停发射+永不抛 | 315fd8f |
| push_realtime_kpi | B19 | wired 10-12 | 14 passed；广播+环形+降频 | 1344453 |
| map_per_to_injection | B20 | wired 10-12 | 16 组；饱和+分段线性 | ff9881c |
| bridge_to_sitl | B20 | wired 10-12 | 16 组；dry_run+缺库不抛 | 970c125 |
| fallback_fixed_strategy | B20 | wired 10-12 | 13 组；GB 计划联动 | 27ee377 |
| run_rl_policy | B20 | wired 10-12 | 13 组；Q-learning+回退 | 91bba33 |
| run_rff_pipeline | B20 | wired 10-12 | 7 组；端到端 F1 1.0 | 2b3917e |
| execute_scenario | B21 | wired 10-12 | 18 passed；四类型分派 | 471e6bb |
| run_demo | B21 | wired 10-12 | 23 passed；CLI 总装（--demo 口径后经 1478365 改为中段失效触发 exit 1=核心产出演示，终检道②-B 实测锚定） | 857f436 |

<!-- 演进周期追加（2026-10-13，域二十 25 函数） -->
| render_console_navigation | B23 | wired 10-13 | pytest tests/localize_console_assets/test_render_console_navigation.py → 41 passed；调用点 render_console_pages.py:345；存量 108 passed 无回归 | b72b261 |
| mount_console_extensions | B23 | wired 10-13 | pytest tests/localize_console_assets/test_mount_console_extensions.py → 14 passed；接线 create_console_app.py:471；vendor 路由 200/157924B；全套件 2972 绿 | d7000fc |
| localize_console_assets | B23 | wired 10-13 | pytest -k console_offline → 57 passed（含三旁路+N1 四形态拒收）；-k console_pages_e2e → 8 passed（断网真装载 window.Vue）；装配 serve_console.py:209；全套件 3028 零回归 | 401ccd8 |
| render_triple_stream_charts | B24 | wired 10-13 | pytest tests/stream_realtime_console/test_render_triple_stream_charts.py → 27 passed；调用点 stream_realtime_console.py:40/521（装配助手经手）；帧协议四型+断线横幅+skip 计数+window 计数钩 | a794e50 |
| stream_realtime_console | B24 | wired 10-13 | pytest tests/stream_realtime_console/test_stream_realtime_console.py → 22 passed；-k realtime_streams_e2e → 2 passed（真 sim 运行帧到达浏览器）；挂载 serve_console.py:167；全套件 3093；C1 修复后 stop 容器贯通 run_scenario(stop=)（backend 写回+档间协作检查）；I3 延迟方向铆 n_clock_skew==0 | 962e9f8 |
| harden_emergency_stop | B24 | wired 10-13 | -k emergency_stop → 26 passed（含真运行急停 e2e：4.53s 提前终止/3 档/帧冻结）；委托 create_console_app.py:446；顺序断言停发射先于旗置位；C1 修复后生产接线真停 | 6c90e2b |
| edit_scenario_ui | B24 | wired 10-13 | pytest tests/edit_scenario_ui/ → 8 passed；-k scenario_editor_e2e → 1 passed（表单/YAML 双模式+400 逐条上屏+卡片刷新）；注入 serve_console.py:311；存量 189 无回归；N2 多频段表单防护 | b125d10 |
| render_report_html | B25 | wired 10-14 | pytest tests/serve_run_artifacts/test_render_report_html.py → 52 passed（含 XSS 消毒 20 形态+全链回归，C-1 修复后）；调用点 serve_run_artifacts.py:191；plots 引用改端点+零外链三路断言 | 95cfe63 |
| serve_run_artifacts | B25 | wired 10-14 | pytest tests/serve_run_artifacts/test_serve_run_artifacts.py → 40 passed；-k report_view → 2 passed（真 sim 运行报告页可读+三图+徽标+下载）；注册 mount_console_extensions.py:131；全套件 3196 | 7b4854f |
| list_run_summaries | B25 | wired 10-14 | pytest tests/list_run_summaries/ → 13 passed（+e2e 3）；-k report_center_e2e → 3 passed（真跑两轮列表+钻取）；端点 mount_console_extensions R61 块+run-list 页区 | ad9eb38 |
| view_failure_comparison | B25 | wired 10-14 | pytest -k boundary_view → 8 passed（通道修复后；含对比表/降级/结论）；端点 mount_console_extensions R62 块+comparison 页区 | 8148d85 |
| browse_dataset_library | B26 | wired 10-14 | pytest tests/browse_dataset_library/ → 14 passed；-k dataset_view_e2e → 2 passed（录制→建库→过滤真链）；端点 mount R63 块+dataset 页区（端点/页区/e2e 实落 9dc39e3——证据锚点勘误见 batches 10-14 Ruling） | 3885ed3 |
| build_replay_scenario | B26 | wired 10-14 | pytest → 12 passed（组装契约/声明红线全查/损坏拒）；调用点 launch_replay_run | d755baa |
| launch_replay_run | B26 | wired 10-14 | pytest tests/launch_replay_run/ → 21 passed；-k replay_run → 21 passed（录制→回放 exit 0 端到端含浏览器链）；挂载 mount_console_extensions.py:428；全套件 3296 | 9dc39e3 |
| launch_classifier_training | B27 | wired 10-14 | -k ai_train_view → 11 passed（dry_run 端到端+拒训原文上屏+模型列表）；端点 mount R65 块+train 页区 | 6097ba7 |
| view_cv_evaluation | B27 | wired 10-14 | -k ai_eval_view → 10 passed（矩阵/Macro-F1/三旗标/警告回显/EvalError 400）；端点 mount R66 块+eval 页区 | 6097ba7 |
| infer_style_entry | B27 | wired 10-14 | -k ai_infer_view → 13 passed（tone 样本正确标签 hit=True+模型缺失提示态）；端点 mount R67 块+infer 页区 | 6097ba7 |
| demo_emc_flows | B28 | wired 10-14 | -k emc_view → 10 passed（三流程真跑+声明+越域标注+端点）；改造点 execute_scenario emc_flow 分派+4 回归 | 7c6eb8d |
| demo_instrument_panels | B28 | wired 10-14 | -k instruments_view → 10 passed（五仪表周期+超域+VISA+端点）；端点 mount R69 块 | 7c6eb8d |
| view_calibration_status | B29 | wired 10-14 | -k calibration_view → 8 passed（三件状态/占位如实/演示三分支/真实表零写）；端点 mount R70 块+calibration 页区 | af44c40 |
| view_ledger_audit | B29 | wired 10-14 | -k ledger_audit_view → 7 passed（明细/锚点清单/注释率/仓库根锚定/只读）；端点 mount R71 块+audit 页区 | af44c40 |
| demo_sitl_bridge | B30 | wired 10-14 | -k sitl_view → 6 passed（dry_run 映射+缺席标注+无台阶拒）；端点 mount R72 块+sitl 页区 | 106a19a |
| demo_rl_policy | B30 | wired 10-14 | -k rl_view → 7 passed（冒烟一轮+回退分支+rounds 域拒）；端点 mount R73 块+rl 页区 | 106a19a |
| demo_rff_pipeline | B30 | wired 10-14 | -k rff_view → 7 passed（四阶段+产物+拒跑）；端点 mount R74 块+rff 页区 | 106a19a |
| audit_responsibility_alignment | B31 | wired 10-14 | -k responsibility_alignment → 6 passed（七对账项+锚点交叉+漏登检出）；责任文档回登记×4+资产件注随批落地 | 146d04d |
| check_demo_manual | B32 | wired 10-14 | pytest tests/check_demo_manual/ → 7 passed+1 skipped（四断言族全绿+真手册冒烟 skip 待手册成型）；-k demo_manual_check → smoke 用例消费面在位 | 87623e4 |
| seed_preset_scenarios | B32 | wired 10-14 | pytest tests/prepare_demo_assets/test_seed_preset_scenarios.py → 7 passed（7 模板全过 load_scenario+冲突/覆盖/不可写）；调用点 prepare_demo_assets.py:88 | 433e43e |
| prewarm_demo_runs | B32 | wired 10-14 | pytest tests/prepare_demo_assets/test_prewarm_demo_runs.py → 5 passed（exit0/1 登记+exit2 中止不吞错+计数）；调用点 prepare_demo_assets.py:105 | e986122 |
| prepare_demo_assets | B32 | wired 10-14 | pytest tests/prepare_demo_assets/ → 19 passed；顶层实跑临时目录 written=7+prewarm[0,0,1]+checklist12/16+env 四键；幂等 refused=7 | d7ffabc |
| compose_esp32_frame | B33 | wired 10-14 | pytest tests/drive_esp32_link/test_compose_esp32_frame.py → 37 passed（往返/NA/非法族/golden 锁格式）；host 等价消费面 | 9243754 |
| encode_esp32_frame | B33 | wired 10-14 | tests/firmware_esp32/test_host_equivalence.py → 2 passed（g++ harness 与 Python compose 逐字节一致+NA 钳制）；调用点 tasks.cpp:185 | 9243754 |
| udp_stream_task | B33 | wired 10-14 | pio run -e tx → SUCCESS（编译级，规约口径；真机联调随 R87）；main.cpp 角色调用 | 9243754 |
| kpi_report_task | B33 | wired 10-14 | pio run -e rx → SUCCESS；缺口/重复/回绕口径在 README 声明；main.cpp 角色调用 | 9243754 |
| esp32_wifi_firmware | B33 | wired 10-14 | pio run → tx/rx 2 succeeded；tests/firmware_esp32/test_firmware_layout.py → 2 passed；README 构建/烧录在册 | 9243754 |
| compose_nrf24_frame | B34 | wired 10-14 | pytest tests/drive_nrf24_link/test_compose_nrf24_frame.py → 31 passed（往返/rpd 两态/非法族/golden/全可解析）；host 等价消费 | ea14f48(实现随批)+d430d65(进位) |
| encode_nrf24_frame | B34 | wired 10-14 | tests/firmware_nrf24/test_nrf24_host_equivalence.py → 2 passed（g++ harness 逐字节一致）；调用点 tasks.cpp:194 | ea14f48(实现随批)+d430d65(进位) |
| esb_traffic_task | B34 | wired 10-14 | pio run -e reporter → SUCCESS（编译级；真机联调随 R87）；main.cpp 角色调用 | ea14f48(实现随批)+d430d65(进位) |
| counter_report_task | B34 | wired 10-14 | pio run -e reporter → SUCCESS；ARC 按包直读/PLOS 差分累计口径 README 声明 | ea14f48(实现随批)+d430d65(进位) |
| nrf24_link_firmware | B34 | wired 10-14 | pio run → reporter/peer 2 succeeded（RF24 1.6.2）；test_nrf24_firmware_layout → 3 passed；README 引脚表/构建烧录在册 | ea14f48(实现随批)+d430d65(进位) |
| normalize_monitor_block | B44 | wired 10-15 | pytest tests/shared/test_normalize_monitor_block.py → 7 passed；tests/record_run_streams → 47 passed（薄壳调用点 record_run_streams.py:174+prewindow 4 用例） | dff5cfc+12de3be |
| _pull_tick | B44 | wired 10-15 | pytest tests/tap_tx_window_blocks → 20 passed（归一盖戳/空读/异常透传/max_blocks 透传/非list容错 5 例）；调用点 _make_tick_dwell_cb 闭包内 | 25e3388 收编 |
| check_demo_manual | B43 | wired 10-15（改造点 R90 契约 v2） | 契约 v2 24 用例（三件套/防回潮/总章完整性/围栏注释防误报迁移）；真实手册八键全绿 | d7b8d6f |
| prepare_demo_assets | B43 | wired 10-15（改造点 R90 单列化） | 19 passed；报告 checklist=18 项单列（序同手册 0.1）；全套件 3591 零失败时点实证 | d7b8d6f |
| _make_tick_dwell_cb | B44 | wired 10-15 | pytest tests/tap_tx_window_blocks → 25 passed（分片/停检/保底/域拒绝 15 例）；产出=tap 装配、消费=run_power_ladder dwell_cb | 25e3388 收编 |
| tap_tx_window_blocks | B44 | wired 10-15 | pytest tests/tap_tx_window_blocks → 25 passed（白名单/装配 6 例）+sim_delivery 交窗 3 例；调用点 execute_gb42590_protocol.py:741 | 25e3388 |
| _emc_conduction_md | B45 | wired 10-15 | pytest tests/render_emc_flow_section → 11 passed（全要素/缺项/三态/消毒 4 例）；分派=render_emc_flow_section | bafa338 收编 |
| _emc_radiation_md | B45 | wired 10-15 | 同上（谱表有界/洁净度/补偿 4 例） | bafa338 收编 |
| _emc_sweep_md | B45 | wired 10-15 | 同上（点表/spurious/超限 3 例） | bafa338 收编 |
| render_emc_flow_section | B45 | wired 10-15 | pytest tests/render_emc_flow_section → 11 passed+tests/build_report → 60 passed（四形状分支含缺项回归）；调用点 build_report.py:461 | bafa338 |
| spectral_template_match | B47 | tested 10-15 | pytest tests/shared/test_spectral_template_match.py → 8 passed（距离序/softmax 值域和一/平手确定性/labels 锚域/空模板/维度拒/非数值/ndarray 同构）；wired 进位随 Ruling⑪ 批内 _template_classify 落地补证 | — |
| _signal_features | B47 | tested 10-15 | pytest tests/predict_style → 32 passed（13 键契约集合断言/tone-noise-门控-恒包络特征值/gate 自洽/等价锚：门控 tone 全流程仍判 pulse）；wired 随 _classify_dummy 改造补证 | — |
| _extract_gate_segments | B47 | tested 10-15 | pytest tests/predict_style → 40 passed（多段/全开/全关/空/单样本/首尾边界/与 _signal_features gate 联动锚/宽进快照 9 例）；wired 随改造体补证 | — |
| _rule_decision | B47 | tested 10-15 | pytest tests/predict_style → 49 passed（六规则各例+精确置信度断言+段内两层门控锚+等价锚：提取链与全流程 label/confidence 完全相等）；wired 随改造体补证 | — |
| _template_classify | B47 | stub 10-15 | —（桩在位 predict_style.py:452） | — |
| _classify_dummy | B47 | stub 10-15 | —（改造承载 R91；改造体留 implement，既有体在跑） | — |
| _predict_one | B47 | stub 10-15 | —（改造承载 R92；同上） | — |
| predict_style | B47 | stub 10-15 | —（改造承载 R91/R92 顶层 docstring；签名不变） | — |
| make_predict_style_callbacks | B48 | stub 10-15 | —（桩在位 make_predict_style_callbacks.py:31） | — |
| grouped_cv_evaluate | B48 | stub 10-15 | —（改造承载 R93；同上） | — |
| view_cv_evaluation | B48 | stub 10-15 | —（改造承载 R93 默认注入；同上） | — |
| prepare_demo_assets | B46 | wired 10-15（改造点 R94 行细分） | 19 passed；报告 checklist=19 项（9a/9b 转接线细分）；下标锚位移同步 | c7e4369 |
