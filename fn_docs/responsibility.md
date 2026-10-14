# 责任文档：无人机链路抗干扰测试平台（重做版）

> 由 fn-divide 产出与独占更新；fn-implement 只读。进度与状态见 implementation.md。
> 职责字段是**重写规约**：凭职责详述 + 签名意图（输入/输出），必须能完美复现该函数功能。
> **实现期发现结构性变化（函数增/删/拆/并/职责或调用关系变化）必须回到 fn-divide 改本文档**（快速确认通道），不得只在代码里改。
> 需求依据：`fn_docs/requirements.md`（55 条 R，2026-10-11 细化版）；全部函数 `[新增]`（旧实现已删，无存量改造）。
> **演进轮（2026-10-13）**：域二十 R56–R75 新增块见文末（P1 块随 R 号标注）；旧块不动。涉及旧函数的接线改造以各块引言内「改造点·快速通道」变更说明登记（R56/R58/R59/R64/R68/R75 共 6 处），均在用户裁决"管线允许顺手改但逐条登记"授权内。
> **演进轮②（2026-10-14）**：域二十一 R76–R87 新增块见文末（R82 演示批、R87 延后为 P1）；旧块不动、无旧函数改造。**承载方式例外**：R77–R83 为手册章节文档交付物、R87 为真机复查过程交付物——矩阵注明"无代码单元"（规格=需求条目，结构自检经 check_demo_manual 承载、命令走查按批执行）；代码单元=prepare_demo_assets / check_demo_manual / 固件两工程（esp32_wifi_firmware、nrf24_link_firmware）及 Python 帧参考实现两叶。

## 结构概览（纯结构，不带职责）

- load_scenario ← R1
  - validate_scenario_schema
  - normalize_scenario
- manage_run ← R2
  - create_run_workspace
  - append_run_log
  - finalize_run
- manage_backend_registry ← R3
  - register_backend
  - lookup_backend
- open_b210_backend ← R4
  - configure_b210_channels
  - write_b210_tx_stream
  - read_b210_rx_stream
- open_sim_backend ← R5
  - loopback_sim_stream
- open_replay_backend ← R6
  - read_sigmf_timeline
- autodetect_backend ← R7
  - probe_uhd_devices
- create_visa_driver ← R8
  - exchange_scpi
- synthesize_style ← R9
  - check_style_params
  - gen_tone
  - gen_sweep
  - gen_chirp
  - gen_bandlimited_noise
  - gen_partial_band
  - gen_pulse
  - compose_jamming
- switch_style ← R10
  - lookup_style_recipe
- run_power_ladder ← R11
  - plan_ladder_steps
- set_channel_attenuation ← R12
  - plan_attenuator_combo
- map_distance_to_loss ← R13
  - compute_pathloss
- lookup_jsr ← R14
- resolve_clock_reference ← R15
  - probe_gpsdo_status
- capture_monitor_spectrum ← R16
  - enforce_bandwidth_limit
- compute_spectrum_stats ← R17
  - estimate_snr
  - check_flatness
- drive_esp32_link ← R18
  - parse_esp32_frame
- drive_nrf24_link ← R19
  - parse_nrf24_frame
- simulate_link_degradation ← R20
  - apply_cliff_model
- normalize_kpi ← R21
  - compute_per
- record_run_streams ← R22
  - compute_alignment_error
- execute_gb42590_protocol ← R23
  - check_failure
  - record_failure_level
- run_baseline_check ← R24
- plot_triple_curves ← R25
  - build_curve_frames
- compare_failure_boundaries ← R26
- write_sigmf_recording ← R27
  - annotate_truth_labels
- index_dataset ← R28
  - query_dataset
- make_spectrogram ← R29
- train_classifier ← R30
  - dispatch_remote_training
- grouped_cv_evaluate ← R31
  - make_group_splits
- predict_style ← R32
- run_emc_conduction_sim ← R33
- run_emc_radiation_sim ← R34
- run_emc_sweep ← R35
  - plan_frequency_sweep
- build_gain_calibration ← R36
  - check_monotonicity
- calibrate_leakage ← R37
- compensate_link_power ← R38
- open_sim_siggen ← R39
- open_sim_analyzer ← R40
- open_sim_mixer ← R41
  - upconvert_with_image_rejection
- open_sim_emi_receiver ← R42
- open_sim_attenuator ← R43
- run_demo ← R44
  - execute_scenario
- build_report ← R45
  - render_disclaimer_sections
  - assemble_frequency_plots
- verify_report_traceability ← R46
  - extract_report_numbers
- serve_console ← R47
  - create_console_app
- render_console_pages ← R48
  - build_scenario_cards
- push_realtime_kpi ← R49
  - measure_refresh_latency
  - trigger_emergency_stop
- update_ledger ← R50
  - locate_ledger_row
- audit_ledger ← R51
  - count_comment_ratio
- guard_compliance ← R52
  - check_power_cap
  - check_band_whitelist
  - check_env_declarations
- bridge_to_sitl ← R53
  - map_per_to_injection
- run_rl_policy ← R54
  - fallback_fixed_strategy
- run_rff_pipeline ← R55
- localize_console_assets ← R56
  - render_console_navigation
  - mount_console_extensions
- edit_scenario_ui ← R57
- stream_realtime_console ← R58
  - render_triple_stream_charts
- harden_emergency_stop ← R59
- serve_run_artifacts ← R60
  - render_report_html
- list_run_summaries ← R61
- view_failure_comparison ← R62
- browse_dataset_library ← R63
- launch_replay_run ← R64
  - build_replay_scenario
- launch_classifier_training ← R65
- view_cv_evaluation ← R66
- infer_style_entry ← R67
- demo_emc_flows ← R68 [P1]
- demo_instrument_panels ← R69 [P1]
- view_calibration_status ← R70 [P1]
- view_ledger_audit ← R71 [P1]
- demo_sitl_bridge ← R72 [P1]
- demo_rl_policy ← R73 [P1]
- demo_rff_pipeline ← R74 [P1]
- audit_responsibility_alignment ← R75
- prepare_demo_assets ← R76
  - seed_preset_scenarios
  - prewarm_demo_runs
- check_demo_manual ← R84（承载 R76–R84 各批手册结构自检）
- esp32_wifi_firmware ← R85
  - encode_esp32_frame
  - udp_stream_task
  - kpi_report_task
  - compose_esp32_frame
- nrf24_link_firmware ← R86
  - encode_nrf24_frame
  - esb_traffic_task
  - counter_report_task
  - compose_nrf24_frame
（域二十一另含无代码单元的交付物：手册各批章节文档 ← R76–R84、真机复查记录 ← R87——承载方式见矩阵）

## 需求覆盖矩阵（P1 在 R 号后标注；非功能约束不进矩阵，fn-close 终检对照 requirements 非功能节）

| 需求 | 顶层函数 |
|---|---|
| R1 | load_scenario |
| R2 | manage_run |
| R3 | manage_backend_registry |
| R4 | open_b210_backend |
| R5 | open_sim_backend |
| R6 | open_replay_backend |
| R7 | autodetect_backend |
| R8 [P1] | create_visa_driver |
| R9 | synthesize_style |
| R10 | switch_style |
| R11 | run_power_ladder |
| R12 | set_channel_attenuation |
| R13 | map_distance_to_loss |
| R14 | lookup_jsr |
| R15 [P1] | resolve_clock_reference |
| R16 | capture_monitor_spectrum |
| R17 | compute_spectrum_stats |
| R18 | drive_esp32_link |
| R19 | drive_nrf24_link |
| R20 | simulate_link_degradation |
| R21 | normalize_kpi |
| R22 | record_run_streams |
| R23 | execute_gb42590_protocol |
| R24 | run_baseline_check |
| R25 | plot_triple_curves |
| R26 | compare_failure_boundaries |
| R27 | write_sigmf_recording |
| R28 | index_dataset |
| R29 | make_spectrogram |
| R30 | train_classifier |
| R31 | grouped_cv_evaluate |
| R32 | predict_style |
| R33 [P1] | run_emc_conduction_sim |
| R34 [P1] | run_emc_radiation_sim |
| R35 [P1] | run_emc_sweep |
| R36 | build_gain_calibration |
| R37 | calibrate_leakage |
| R38 | compensate_link_power |
| R39 [P1] | open_sim_siggen |
| R40 [P1] | open_sim_analyzer |
| R41 [P1] | open_sim_mixer |
| R42 [P1] | open_sim_emi_receiver |
| R43 [P1] | open_sim_attenuator |
| R44 | run_demo |
| R45 | build_report |
| R46 | verify_report_traceability |
| R47 | serve_console |
| R48 | render_console_pages |
| R49 | push_realtime_kpi |
| R50 | update_ledger |
| R51 | audit_ledger |
| R52 | guard_compliance |
| R53 [P1] | bridge_to_sitl |
| R54 [P1] | run_rl_policy |
| R55 [P1] | run_rff_pipeline |
| R56 | localize_console_assets |
| R57 | edit_scenario_ui |
| R58 | stream_realtime_console |
| R59 | harden_emergency_stop |
| R60 | serve_run_artifacts |
| R61 | list_run_summaries |
| R62 | view_failure_comparison |
| R63 | browse_dataset_library |
| R64 | launch_replay_run |
| R65 | launch_classifier_training |
| R66 | view_cv_evaluation |
| R67 | infer_style_entry |
| R68 [P1] | demo_emc_flows |
| R69 [P1] | demo_instrument_panels |
| R70 [P1] | view_calibration_status |
| R71 [P1] | view_ledger_audit |
| R72 [P1] | demo_sitl_bridge |
| R73 [P1] | demo_rl_policy |
| R74 [P1] | demo_rff_pipeline |
| R75 | audit_responsibility_alignment |
| R76 | prepare_demo_assets（手册总章文档交付物另见需求条目） |
| R77 | （文档交付物：测评核心五章；无代码单元——结构自检 check_demo_manual、命令走查按批） |
| R78 | （文档交付物：记录与报告四章；无代码单元——同上） |
| R79 | （文档交付物：AI 识别章；无代码单元——同上） |
| R80 | （文档交付物：模拟与扩展三章；无代码单元——同上） |
| R81 | （文档交付物：安全与台账二章；无代码单元——同上） |
| R82 [P1] | （文档交付物：二期进阶三章；无代码单元——同上） |
| R83 | （文档交付物：操控台七页章；无代码单元——同上） |
| R84 | check_demo_manual（附录与总装文档交付物另见需求条目） |
| R85 | esp32_wifi_firmware（+Python 叶 compose_esp32_frame） |
| R86 | nrf24_link_firmware（+Python 叶 compose_nrf24_frame） |
| R87 [P1·延后] | （过程交付物：真机复查记录——设备在位后按用户命令触发；无代码单元） |

## 共享函数（shared/：多顶层共用；矩阵挂全部受益需求）

- **stop_transmit_safely**（调用方：manage_run, run_power_ladder, drive_esp32_link, record_run_streams, execute_gb42590_protocol, trigger_emergency_stop）
  - 职责：安全停发射的唯一出口——幂等地令当前发射通道进入静默（后端 stop+增益归零+事件记录），供所有异常/急停/正常收尾路径复用；保证"先停发射再退出"铁律单点实现。
  - 签名意图：输入: 后端实例（可空）/ 输出: 停发射结果（已停/原本未发射/失败原因）/ 错误: 后端已失联→尽力而为并返回失败原因，不抛出（安全路径不允许被异常打断）。
  - tested 策略：上游覆盖: manage_run（R2 三路径用例）+ push_realtime_kpi（R49 急停用例）
  - 核验命令：上游覆盖: manage_run
- **append_event**（调用方：run_power_ladder, set_channel_attenuation, execute_gb42590_protocol, run_demo）
  - 职责：向当前运行 events.jsonl 追加一条带主机单调钟时间戳的注入事件（类型/档位/电平/附加字段），行级 JSON 落盘保证崩溃后已写事件不丢。
  - 签名意图：输入: 运行目录+事件字典 / 输出: 已写入的事件行 / 错误: 目录不存在或磁盘写失败→抛出（由调用方走停发射路径）。
  - tested 策略：上游覆盖: run_power_ladder（事件时间线断言）
  - 核验命令：上游覆盖: run_power_ladder
- **load_calibration_table**（调用方：lookup_jsr, compensate_link_power, set_channel_attenuation）
  - 职责：按名称加载标定表文件（增益标定/链路损耗/天线系数），校验结构（频点/档位覆盖、无 NaN）后返回只读表；表缺失或损坏按调用方语义抛出或返回带【待实测】标注的占位表。
  - 签名意图：输入: 表名+运行配置 / 输出: 标定表对象（含来源与占位标记）/ 错误: 文件损坏→抛出；缺失→按参数决定占位或抛出。
  - tested 策略：上游覆盖: lookup_jsr（缺表拒绝用例）+ compensate_link_power（无表标注用例）
  - 核验命令：上游覆盖: lookup_jsr
- **make_disclaimer_block**（调用方：run_emc_conduction_sim, run_emc_radiation_sim, run_emc_sweep, build_report）
  - 职责：生成统一的口径声明块（模拟后端/非 CISPR 16-1-1 接收机/屏蔽盒环境/仅自建链路/GB 42590 方法学预研定位，按场景类型取舍），供 EMC 段与报告脚注复用，保证四处声明文字一致。
  - 签名意图：输入: 声明场景枚举（emc/报告全局/急停页）/ 输出: 声明文本块 / 错误: 未知枚举→抛出。
  - tested 策略：上游覆盖: build_report（口径声明字段断言）
  - 核验命令：上游覆盖: build_report

## 功能块 load_scenario ← R1

（R1：场景 YAML 加载与校验——字段完整性、取值域、频段白名单（经 guard_compliance）、功率上限；非法即退出码 2 并指错。）

> 演进补注（2026-10-14，R75）：validate_scenario_schema 场景白名单键域实测 **63 键**（_KNOWN_KEYS——演进期净增 41 键入册放行不校验取值的口径：执行信封键与可选字段在册即放行，取值红线仍归 guard_compliance/下游）；键数以代码 _KNOWN_KEYS len 为动态锚（serve_console._MERGEABLE_KEYS 同源消费，audit_responsibility_alignment 对账校验——键数漂移即漏登）。

- **load_scenario** [L0|新增]
  - 职责：读取场景 YAML 文件并产出规范化场景对象：依次完成文件读取（YAML 解析失败→指错行）、validate_scenario_schema 字段校验、guard_compliance 红线校验（拒则退出码 2 语义异常）、normalize_scenario 规范化（默认值填充、单位统一）；是场景进入系统的唯一入口。
  - 签名意图：输入: 场景文件路径 / 输出: 规范化场景对象（样式/频段/梯度/判据/后端）/ 错误: ScenarioError（含字段名与原因，供退出码 2）。
  - 调用方：run_demo；serve_console（场景 API）
  - tested 策略：自有单测
  - 核验命令：测试: scenario_validate
  - **validate_scenario_schema** [L1|新增]
    - 职责：校验场景字段完整性与取值域（样式名在册、频段/带宽/采样率数值域、梯度参数非负、判据阈值域）；只判"形状与数值"，不判红线（红线归 guard_compliance）。
    - 签名意图：输入: 原始解析后的 dict / 输出: 通过（None）或逐字段错误列表 / 错误: 不抛出，返回错误列表由上层汇总。
    - 调用方：load_scenario
    - tested 策略：上游覆盖: load_scenario
    - 核验命令：上游覆盖: load_scenario
  - **normalize_scenario** [L1|新增]
    - 职责：把通过校验的场景填充默认值并规范化（频率单位统一 Hz、时间统一 ms、后端缺省 auto、判据缺省 PER>10%），产出下游唯一依赖的场景对象形状。
    - 签名意图：输入: 校验通过 dict / 输出: 规范化场景对象 / 错误: 默认值与显式值类型冲突→ScenarioError。
    - 调用方：load_scenario
    - tested 策略：上游覆盖: load_scenario
    - 核验命令：上游覆盖: load_scenario

## 功能块 manage_run ← R2

（R2：运行目录与生命周期——八件套、状态机 starting→armed→running→stopping→done/failed、任何退出路径先停发射（经 stop_transmit_safely）、日志落盘、结果 JSON。）

- **manage_run** [L0|新增]
  - 职责：一次运行的全生命周期管理：创建工作区（create_run_workspace 八件套骨架）、驱动状态机（starting/armed/running/stopping/done/failed，非法迁移拒绝）、收尾时保证 stop_transmit_safely 已执行、写出结果 JSON（退出码/耗时/后端/时钟口径/对齐误差）；所有顶层执行路径（run_demo、console 启动）都必须在本管理器内运行。
  - 签名意图：输入: 规范化场景对象+执行回调 / 输出: 运行目录路径+结果 JSON / 错误: 执行回调异常→转 failed 状态再抛出（先停发射）；目录创建失败→RunDirError（退出码 1）。
  - 调用方：run_demo；serve_console
  - tested 策略：自有单测
  - 核验命令：测试: run_lifecycle
  - **create_run_workspace** [L1|新增]
    - 职责：创建 runs/<YYYYMMDD-HHMMSS>/ 目录与八件套占位（场景副本、kpi.csv 表头、events.jsonl、monitor.csv 表头、SigMF 目录、report.md 占位、图目录、run.log），冲突时后缀去重。
    - 签名意图：输入: 基础 runs 目录+场景 / 输出: 运行目录 / 错误: 磁盘不可写/空间预检不足→RunDirError。
    - 调用方：manage_run
    - tested 策略：上游覆盖: manage_run
    - 核验命令：上游覆盖: manage_run
  - **append_run_log** [L1|新增]
    - 职责：向 run.log 追加结构化日志行（时间戳+级别+模块+消息+上下文字段），运行结束后只读封存；所有模块经它落日志（无 print 直写）。
    - 签名意图：输入: 运行目录+级别+消息+上下文 dict / 输出: 无（副作用写文件）/ 错误: 写失败→静默降级内存缓冲并在结果 JSON 标注日志不完整。
    - 调用方：manage_run 及各模块（经运行上下文）
    - tested 策略：上游覆盖: manage_run
    - 核验命令：上游覆盖: manage_run
  - **finalize_run** [L1|新增]
    - 职责：收尾：确认停发射结果、封存三路数据文件（flush+fsync）、写结果 JSON（退出码语义/耗时/后端/时钟/对齐误差/缺项清单）、状态机迁移至 done/failed。
    - 签名意图：输入: 运行上下文+退出语义 / 输出: 结果 JSON 路径 / 错误: 收尾自身失败→结果 JSON 记"收尾异常"并保留已写数据。
    - 调用方：manage_run
    - tested 策略：上游覆盖: manage_run
    - 核验命令：上游覆盖: manage_run

## 功能块 manage_backend_registry ← R3

（R3：仪表插槽接口与注册机制——统一接口（IQ 收发/参数/能力声明）、注册表、三类插槽对称、新增=文件+注册。）

- **manage_backend_registry** [L0|新增]
  - 职责：仪表后端注册与获取的总入口：定义后端统一接口契约（能力声明+参数下发+IQ 收发+启停），维护全局注册表；获取时按名解析，未注册名明确报错；保证"新后端=新文件+register_backend 调用"即可接入。
  - 签名意图：输入: 后端名（或注册请求：名+工厂）/ 输出: 后端实例或注册确认 / 错误: 未注册名→BackendError（列出可用名）；重复注册→拒绝（除非显式覆盖参数）。
  - 调用方：autodetect_backend；run_demo；各 sim 远期后端
  - tested 策略：自有单测
  - 核验命令：测试: slot_registry
  - **register_backend** [L1|新增]
    - 职责：把后端工厂函数按名登记入注册表（含能力元数据：频段/带宽/增益域/是否模拟），登记时做接口契约形式检查（必需方法齐全）。
    - 签名意图：输入: 名+工厂+能力元数据 / 输出: 登记确认 / 错误: 契约缺失方法或重名→BackendError。
    - 调用方：manage_backend_registry；各后端模块（import 时自注册）
    - tested 策略：上游覆盖: manage_backend_registry
    - 核验命令：上游覆盖: manage_backend_registry
  - **lookup_backend** [L1|新增]
    - 职责：按名（含别名解析：b210/sim/replay/auto）返回后端工厂与能力元数据，供 autodetect_backend 与场景后端选择使用。
    - 签名意图：输入: 后端名 / 输出: 工厂+能力元数据 / 错误: 未知名→BackendError（附可用名列表）。
    - 调用方：manage_backend_registry；autodetect_backend
    - tested 策略：上游覆盖: manage_backend_registry
    - 核验命令：上游覆盖: manage_backend_registry

## 功能块 open_b210_backend ← R4

（R4：B210 真硬件后端——UHD 双通道 CH1 注入/CH2 监测、参数下发回读、70MHz–6GHz；初始化失败上抛由 R7 决定降级。）

- **open_b210_backend** [L0|新增]
  - 职责：创建并初始化 B210 硬件后端：UHD 设备打开、双子通道（CH1 TX/CH2 RX）分配、configure_b210_channels 参数下发、提供 IQ 读写流句柄与硬件状态（时钟源/GPS 锁定）；注册名 b210。
  - 签名意图：输入: 后端参数（频率/增益/采样率/天线）/ 输出: 后端实例（实现统一接口）/ 错误: 设备打不开/参数下发失败→BackendError（含 UHD 错误原文）。
  - 调用方：manage_backend_registry（工厂）；autodetect_backend
  - tested 策略：自有单测（在位实测；不在位 skip 并标注）
  - 核验命令：测试: backend_b210
  - **configure_b210_channels** [L1|新增]
    - 职责：向 UHD 下发双通道参数（中心频率/增益/采样率/带宽/天线选择）并回读校验（回读偏差超容差报错），含 GPSDO/PPS 时钟源配置。
    - 签名意图：输入: 设备句柄+参数集 / 输出: 回读确认的参数集 / 错误: 参数越域→ValueError（域校验先行零副作用）；下发异常或回读不符→BackendError（含 UHD 原文）。
    - 调用方：open_b210_backend
    - tested 策略：上游覆盖: open_b210_backend
    - 核验命令：上游覆盖: open_b210_backend
  - **write_b210_tx_stream** [L1|新增]
    - 职责：把基带 IQ 流送入 CH1 发射（分块下发、欠载检测、发送字节计数），支持运行中增益/频率参数热更新。
    - 签名意图：输入: 后端实例+IQ 块迭代器 / 输出: 发送统计 / 错误: 欠载超阈/设备失联→BackendError（上层走停发射）。
    - 调用方：open_b210_backend（流接口）
    - tested 策略：上游覆盖: open_b210_backend
    - 核验命令：上游覆盖: open_b210_backend
  - **read_b210_rx_stream** [L1|新增]
    - 职责：从 CH2 连续读取监测 IQ 流（溢出检测、时间戳标记），供 capture_monitor_spectrum 消费。
    - 签名意图：输入: 后端实例+读取参数 / 输出: IQ 块迭代器（含时间戳与溢出标志）/ 错误: 溢出超阈→告警事件，失联→BackendError。
    - 调用方：open_b210_backend（流接口）；capture_monitor_spectrum
    - tested 策略：上游覆盖: open_b210_backend
    - 核验命令：上游覆盖: open_b210_backend

## 功能块 open_sim_backend ← R5

（R5：sim 模拟后端——全参数软件仿真、注入 IQ 环回、无硬件全流程。）

- **open_sim_backend** [L0|新增]
  - 职责：创建纯软件仿真仪表后端（注册名 sim）：参数域与 B210 同构（可配置扩展频段/带宽/增益）、注入 IQ 经 loopback_sim_stream 环回给监测与链路退化模型消费、可控注入仿真噪声与信道效应；无任何硬件依赖。
  - 签名意图：输入: 后端参数（同 b210 形状，域可放宽）/ 输出: 后端实例 / 错误: 参数域校验同形拒绝。
  - 调用方：manage_backend_registry（工厂）；autodetect_backend（降级目标）
  - tested 策略：自有单测
  - 核验命令：测试: backend_sim
  - **loopback_sim_stream** [L1|新增]
    - 职责：sim 内部环回通道：把 TX IQ 按配置的延迟/衰减/加噪变换后作为 RX 流返回（供监测与退化模型得到与注入一致的信号），保持时间戳因果。
    - 签名意图：输入: TX IQ 块+信道效应参数 / 输出: 变换后 RX IQ 块 / 错误: 参数越仿真域→夹紧并标注。
    - 调用方：open_sim_backend
    - tested 策略：上游覆盖: open_sim_backend
    - 核验命令：上游覆盖: open_sim_backend

## 功能块 open_replay_backend ← R6

（R6：replay 回放后端——SigMF 真值对按时间轴回放，复现与测试。）

- **open_replay_backend** [L0|新增]
  - 职责：创建回放后端（注册名 replay）：打开 SigMF 录制对，read_sigmf_timeline 按录制时间轴（可倍速）产出 RX 流；无 TX 能力（发发射请求即明确报错），用于复现既有数据流。
  - 签名意图：输入: SigMF 路径+倍速 / 输出: 后端实例 / 错误: 文件损坏/时间轴断裂→BackendError。
  - 调用方：manage_backend_registry（工厂）
  - tested 策略：自有单测
  - 核验命令：测试: backend_replay
  - **read_sigmf_timeline** [L1|新增]
    - 职责：解析 SigMF 元数据与数据文件，按样本时间戳切块产出（保序），暴露标注（样式/功率档）供回放场景对齐。
    - 签名意图：输入: SigMF 对路径 / 输出: 时间戳 IQ 块迭代器+标注 / 错误: 元数据缺字段/数据截断→BackendError。
    - 调用方：open_replay_backend
    - tested 策略：上游覆盖: open_replay_backend
    - 核验命令：上游覆盖: open_replay_backend

## 功能块 autodetect_backend ← R7

（R7：后端自动探测与降级——uhd_find_devices 探测、在位 b210/不在位 sim、标识贯通日志与 UI、初始化失败显式报错不静默。）

- **autodetect_backend** [L0|新增]
  - 职责：启动时决定当前后端：probe_uhd_devices 探测→在位尝试 open_b210_backend→成功用 b210；不在位降级 sim；在位但初始化失败→显式报错并提示"显式指定 --backend sim 可降级"，**绝不静默 sim**；把最终后端名+探测依据写入运行上下文（日志/UI/报告贯通）。
  - 签名意图：输入: 显式后端名（可空=auto）/ 输出: 后端实例+选择记录（探测输出/决策原因）/ 错误: 显式名失败→BackendError；auto 且初始化失败→BackendError（附降级建议）。
  - 调用方：run_demo；serve_console
  - tested 策略：自有单测（三态注入测试）
  - 核验命令：测试: backend_autodetect
  - **probe_uhd_devices** [L1|新增]
    - 职责：调用 uhd_find_devices（或 UHD API）枚举在位 USRP，返回设备清单与原始输出；工具缺失/执行失败返回空清单+原因（按无设备处理，不抛出）。
    - 签名意图：输入: 无 / 输出: 设备列表+探测原始输出+失败原因 / 错误: 不抛出（失败信息进返回值）。
    - 调用方：autodetect_backend
    - tested 策略：上游覆盖: autodetect_backend
    - 核验命令：上游覆盖: autodetect_backend

## 功能块 create_visa_driver ← R8 [P1]

（R8：PyVISA SCPI 仪表槽位——远期真仪表接入层，与插槽同构；sim 仪表可注入同槽演示。）

- **create_visa_driver** [L0|新增]
  - 职责：创建 PyVISA(+PyVISA-Py) 驱动槽位：按仪表型号加载 SCPI 命令映射（1433D/EMI 接收机等），exchange_scpi 完成查询/设置；实现统一仪表接口（能力声明=型号规格），远期真仪表与 sim 仪表同槽可换。
  - 签名意图：输入: VISA 地址（或资源名）+型号 / 输出: 驱动实例（统一接口）/ 错误: 资源打不开/应答超时→DriverError（含仪器原文）。
  - 调用方：manage_backend_registry（注册为 visa 槽）；open_sim_siggen 等远期后端复用其命令映射
  - tested 策略：自有单测（模拟仪器应答往返）
  - 核验命令：测试: visa_slot
  - **exchange_scpi** [L1|新增]
    - 职责：单次 SCPI 交互：发送命令、可选读回应答、超时与重试策略、原始应答解析为类型化值。
    - 签名意图：输入: 驱动实例+命令+期望应答类型 / 输出: 类型化应答 / 错误: 超时/语法错→DriverError。
    - 调用方：create_visa_driver
    - tested 策略：上游覆盖: create_visa_driver
    - 核验命令：上游覆盖: create_visa_driver

## 功能块 synthesize_style ← R9

（R9：六类样式合成引擎——J(t) 分量程序化（A_k/Δf_k/θ_k）、参数校验内建（频率/带宽≤56MHz/功率域）、越界即拒。）

- **synthesize_style** [L0|新增]
  - 职责：样式合成总入口：check_style_params 参数校验后按样式名分派到六个生成器（gen_tone/gen_sweep/gen_chirp/gen_bandlimited_noise/gen_partial_band/gen_pulse）产出基带 IQ；多样式叠加经 compose_jamming 完成（J(t) 多源合成）；输出可直接进后端 TX 流。
  - 签名意图：输入: 样式名+参数（频率/带宽/功率/时域形状）+样本预算 / 输出: 复数 IQ 数组（含元数据：实际带宽/功率归一）/ 错误: 参数越界（频率/带宽/功率域）→StyleError（指明参数名与界限）。
  - 调用方：switch_style；run_power_ladder（各档重合成）；execute_gb42590_protocol
  - tested 策略：自有单测
  - 核验命令：测试: styles_synth
  - **check_style_params** [L1|新增]
    - 职责：样式参数取值域校验：频率∈后端能力域、带宽≤56MHz（带限类）、功率∈[下限,0dBm 红线内]、时域参数非负；只判域不合成。
    - 签名意图：输入: 样式参数 dict / 输出: 通过/逐参数错误列表 / 错误: 不抛出，返回列表由上层转 StyleError。
    - 调用方：synthesize_style
    - tested 策略：上游覆盖: synthesize_style
    - 核验命令：上游覆盖: synthesize_style
  - **gen_tone** [L1|新增]
    - 职责：生成单音（CW）复指数 IQ：给定频偏与长度，恒包络。
    - 签名意图：输入: 频偏+样本数 / 输出: IQ 数组 / 错误: 域已由上游保证，不另抛。
    - 调用方：synthesize_style
    - tested 策略：上游覆盖: synthesize_style
    - 核验命令：上游覆盖: synthesize_style
  - **gen_sweep** [L1|新增]
    - 职责：生成线性扫频 IQ（起止频率/时长/重复），相位连续累积。
    - 签名意图：输入: f0/f1/时长/重复次数 / 输出: IQ 数组 / 错误: 同上不另抛。
    - 调用方：synthesize_style
    - tested 策略：上游覆盖: synthesize_style
    - 核验命令：上游覆盖: synthesize_style
  - **gen_chirp** [L1|新增]
    - 职责：生成 chirp（线性调频，锯齿/三角）IQ，换频周期参数化。
    - 签名意图：输入: 带宽/周期/形状 / 输出: IQ 数组 / 错误: 同上。
    - 调用方：synthesize_style
    - tested 策略：上游覆盖: synthesize_style
    - 核验命令：上游覆盖: synthesize_style
  - **gen_bandlimited_noise** [L1|新增]
    - 职责：生成带限高斯噪声 IQ（滤波成型，99% 功率带宽参数化、平坦度≤4dB 设计目标）。
    - 签名意图：输入: 带宽+样本数+随机种子 / 输出: IQ 数组（实测带宽/平坦度入元数据）/ 错误: 带宽>56MHz→StyleError。
    - 调用方：synthesize_style
    - tested 策略：上游覆盖: synthesize_style
    - 核验命令：上游覆盖: synthesize_style
  - **gen_partial_band** [L1|新增]
    - 职责：生成部分频带干扰 IQ（占被测带宽的比例参数化，中心可偏置）。
    - 签名意图：输入: 占比+中心偏置+样本数 / 输出: IQ 数组 / 错误: 同上。
    - 调用方：synthesize_style
    - tested 策略：上游覆盖: synthesize_style
    - 核验命令：上游覆盖: synthesize_style
  - **gen_pulse** [L1|新增]
    - 职责：生成脉冲干扰 IQ（占空比/脉宽/重复频率参数化，载波可选）。
    - 签名意图：输入: 占空比+脉宽+重复频率 / 输出: IQ 数组 / 错误: 同上。
    - 调用方：synthesize_style
    - tested 策略：上游覆盖: synthesize_style
    - 核验命令：上游覆盖: synthesize_style
  - **compose_jamming** [L1|新增]
    - 职责：J(t) 多源合成：把 K 个分量 IQ 按各自 A_k 包络、Δf_k 频偏、θ_k 相位叠加为单一干扰波形（公式(1) 程序化），输出总功率归一信息。
    - 签名意图：输入: 分量列表（IQ+包络+频偏+相位）/ 输出: 合成 IQ+各分量功率占比 / 错误: 分量长度不一致→StyleError。
    - 调用方：synthesize_style
    - tested 策略：上游覆盖: synthesize_style
    - 核验命令：上游覆盖: synthesize_style

## 功能块 switch_style ← R10

（R10：样式注册表与快速切换——新增样式=注册不动核心、切换 <2s 软件操作。）

- **switch_style** [L0|新增]
  - 职责：运行前/间隙切换当前样式：lookup_style_recipe 取配方→预合成就绪实例→原子替换当前样式句柄；切换耗时测量入结果（<2s 判据）；切换期间不发发射（安全闸）。
  - 签名意图：输入: 当前运行上下文+新样式名+参数 / 输出: 就绪样式实例+切换耗时 / 错误: 未注册样式→StyleError；合成失败→保持旧样式并报错。
  - 调用方：run_demo；serve_console（场景卡切换）
  - tested 策略：自有单测
  - 核验命令：测试: styles_switch
  - **lookup_style_recipe** [L1|新增]
    - 职责：样式配方注册表查询（样式名→生成器绑定+默认参数+能力元数据），新样式注册=登记配方。
    - 签名意图：输入: 样式名 / 输出: 配方 / 错误: 未注册→StyleError（附在册列表）。
    - 调用方：switch_style；synthesize_style（分派）
    - tested 策略：上游覆盖: switch_style
    - 核验命令：上游覆盖: switch_style

## 功能块 run_power_ladder ← R11

（R11：功率步进执行器——GB 口径 −5dB 起 5dB 档递增、失效即停、事件流 events.jsonl。）

- **run_power_ladder** [L0|新增]
  - 职责：执行功率阶梯：plan_ladder_steps 生成档位计划→逐档下发（后端增益+衰减组合）→每档经 append_event 记录（时间戳/档号/电平/JSR 估计）→监听失效判据回调，触发即 stop_transmit_safely 并终止；档位不可达先停发射再报错。
  - 签名意图：输入: 运行上下文+梯度参数+失效判据回调 / 输出: 档位执行记录列表 / 错误: 后端增益不可达→LadderError（已停发射）；判据回调异常→同停发射语义。
  - 调用方：execute_gb42590_protocol；run_demo（非国标自定义梯度）
  - tested 策略：自有单测
  - 核验命令：测试: power_ladder
  - **plan_ladder_steps** [L1|新增]
    - 职责：把梯度参数展开为有序档位计划（起始=链路发射功率−5dB、步长 5dB、上限参数化；支持自定义起止/步长场景），每档标注预期电平与档号。
    - 签名意图：输入: 链路参考功率+梯度参数 / 输出: 档位计划（电平/档号/说明）/ 错误: 起点高于红线→PlanError。
    - 调用方：run_power_ladder
    - tested 策略：上游覆盖: run_power_ladder
    - 核验命令：上游覆盖: run_power_ladder

## 功能块 set_channel_attenuation ← R12

（R12：粗细档信道拼接——30dB 衰减器两态+软件增益细档、请求→组合映射、越界给出可达域。）

- **set_channel_attenuation** [L0|新增]
  - 职责：把目标衰减量翻译为档位组合：plan_attenuator_combo 计算（30dB 粗档接入/旁路 × 软件增益细档，档位标定表由调用方直传或 ctx['attenuator_cal']（文件标定表无档位语义，不走 load_calibration_table））→下发后端→append_event 记录；请求超出可达范围时拒绝并返回可达域。
  - 签名意图：输入: 目标衰减 dB+运行上下文 / 输出: 实达衰减+档位组合 / 错误: 超可达域→AttenuationError（附可达范围）。
  - 调用方：run_power_ladder；map_distance_to_loss（间接经计划）
  - tested 策略：自有单测
  - 核验命令：测试: channel_ladder
  - **plan_attenuator_combo** [L1|新增]
    - 职责：纯计算：目标衰减→（粗档二态，软件增益档）组合与残差，输出组合序列；不含副作用。
    - 签名意图：输入: 目标 dB+档位域+标定表 / 输出: 组合+实达值+残差 / 错误: 不抛出（不可达返回 None 由上层转 AttenuationError）。
    - 调用方：set_channel_attenuation
    - tested 策略：上游覆盖: set_channel_attenuation
    - 核验命令：上游覆盖: set_channel_attenuation

## 功能块 map_distance_to_loss ← R13

（R13：距离-损耗映射——L(d) 公式(3) 功率台阶等效、n/X_σ 参数化、远场→近场演变序列。）

- **map_distance_to_loss** [L0|新增]
  - 职责：把距离序列映射为损耗计划：compute_pathloss 逐点算 L(d)（含 X_σ 阴影抽样，随机种子可控复现）→损耗值序列交给 set_channel_attenuation 语义生成档位计划；超可模拟距离域时给出可达距离范围。
  - 签名意图：输入: 距离序列/参考距离 d₀/n/X_σ 参数 / 输出: 距离-损耗-档位计划 / 错误: 距离超可达衰减域→DistanceError（附可达范围）。
  - 调用方：run_demo（距离演变场景）；run_power_ladder（演变模式）
  - tested 策略：自有单测
  - 核验命令：测试: pathloss_map
  - **compute_pathloss** [L1|新增]
    - 职责：公式(3) 单点计算：L(d)=L(d₀)+10n·log₁₀(d/d₀)+X_σ（X_σ=零均值高斯 σ 抽样，种子可控）；纯函数。
    - 签名意图：输入: d/d₀/L(d₀)/n/X_σ 参数+种子 / 输出: 损耗 dB / 错误: d≤0 或 d<d₀→ValueError。
    - 调用方：map_distance_to_loss
    - tested 策略：上游覆盖: map_distance_to_loss
    - 核验命令：上游覆盖: map_distance_to_loss

## 功能块 lookup_jsr ← R14

（R14：JSR 标定与换算——增益→注入功率标定表查询、JSR 换算、缺表拒绝。）

- **lookup_jsr** [L0|新增]
  - 职责：由当前增益档/频率查标定表得估计注入功率（load_calibration_table，含【待实测】占位语义），结合链路信号功率换算 JSR；标定表缺失时拒绝 JSR 场景并提示先标定。
  - 签名意图：输入: 增益档+频率+链路信号功率 / 输出: 估计注入功率+JSR dB / 错误: 表缺失→CalibrationError（提示 build_gain_calibration）；插值域外→返回值带外推标注。
  - 调用方：run_power_ladder（事件附 JSR）；compute_spectrum_stats（反演交叉校验）
  - tested 策略：自有单测
  - 核验命令：测试: jsr_calibration

## 功能块 resolve_clock_reference ← R15 [P1]

（R15：时钟参考探测——GPS/10MHz/PPS 可用性、驯服启用或主机钟降级、口径贯通日志与报告脚注。）

- **resolve_clock_reference** [L0|新增]
  - 职责：初始化时决定时基：probe_gpsdo_status 探测（GPS 锁定/外接 10MHz/PPS）→可用则配置后端时钟驯服、不可用降级主机单调钟；输出时钟口径（枚举+依据）写入运行上下文（报告脚注消费）；探测失败不阻塞。
  - 签名意图：输入: 后端实例（可空）/ 输出: ClockReference（枚举/依据/驯服状态）/ 错误: 不抛出（任何失败→软件钟+标注）。
  - 调用方：run_demo（初始化阶段）；manage_run（结果 JSON 记录）
  - tested 策略：自有单测
  - 核验命令：测试: clocking
  - **probe_gpsdo_status** [L1|新增]
    - 职责：读取后端/GPSDO 状态（锁定卫星数/参考源/PPS 可用），返回原始状态与可用性判定；无硬件返回不可用+原因。
    - 签名意图：输入: 后端实例 / 输出: 状态 dict+可用布尔 / 错误: 不抛出。
    - 调用方：resolve_clock_reference
    - tested 策略：上游覆盖: resolve_clock_reference
    - 核验命令：上游覆盖: resolve_clock_reference

## 功能块 capture_monitor_spectrum ← R16

（R16：监测谱采集——CH2 流→monitor.csv、56MHz 边界内建（限带/分段）、超带宽自动限带记录口径。）

- **capture_monitor_spectrum** [L0|新增]
  - 职责：消费监测 IQ 流产出 monitor.csv：按窗口做功率谱统计（频率 bin+功率+时间戳）逐行落盘；enforce_bandwidth_limit 在采集参数处实施 56MHz 边界（2.4G 整段自动限带或分段计划、5.8G 单信道段）；带宽口径写入运行上下文。
  - 签名意图：输入: 监测流+采集参数 / 输出: monitor.csv 行流+分段口径 / 错误: 流中断→MonitorError（走停发射路径）。
  - 调用方：record_run_streams（三路之一）
  - tested 策略：自有单测
  - 核验命令：测试: monitor_capture
  - **enforce_bandwidth_limit** [L1|新增]
    - 职责：给定目标观测频段与设备 56MHz 实时带宽，产出合法采集计划（单段限带或多段拼接），并生成口径说明（哪些频段受限）。
    - 签名意图：输入: 目标频段+设备带宽 / 输出: 采集段计划+受限说明 / 错误: 目标频段全超设备域→MonitorError。
    - 调用方：capture_monitor_spectrum
    - tested 策略：上游覆盖: capture_monitor_spectrum
    - 核验命令：上游覆盖: capture_monitor_spectrum

## 功能块 compute_spectrum_stats ← R17

（R17：频谱统计与核验——SNR 公式(4)、JSR 反演、平坦度≤4dB、杂散可观测口径。）

- **compute_spectrum_stats** [L0|新增]
  - 职责：对 monitor 数据窗口出统计行：estimate_snr（公式(4)，参考信号参数在位时）、JSR 反演（与 lookup_jsr 交叉）、check_flatness（带限噪声段）、监测底噪口径（无参考时只出功率统计并标注）；统计行供报告与判据使用。
  - 签名意图：输入: monitor 窗口+参考参数（可空）/ 输出: 统计行（SNR/JSR/平坦度/底噪，含可用性标记）/ 错误: 窗口数据不足→跳窗计数，不抛出。
  - 调用方：record_run_streams（随采随算）；build_report（图谱数据）
  - tested 策略：自有单测
  - 核验命令：测试: spectrum_stats
  - **estimate_snr** [L1|新增]
    - 职责：公式(4) 单窗口计算：SNR=P_signal/(P_noise+P_interference)，信号/噪声/干扰功率划分策略参数化（bin 归属法）。
    - 签名意图：输入: 功率谱 bin+划分参数 / 输出: SNR dB+各功率分量 / 错误: 划分空带→返回不可用标记。
    - 调用方：compute_spectrum_stats
    - tested 策略：上游覆盖: compute_spectrum_stats
    - 核验命令：上游覆盖: compute_spectrum_stats
  - **check_flatness** [L1|新增]
    - 职责：对指定频带计算平坦度（最大/最小功率差）并与 ≤4dB 判据比对，越限报警事件。
    - 签名意图：输入: 功率谱 bin+目标频带 / 输出: 平坦度 dB+越限布尔 / 错误: 带内 bin 不足→不可用标记。
    - 调用方：compute_spectrum_stats
    - tested 策略：上游覆盖: compute_spectrum_stats
    - 核验命令：上游覆盖: compute_spectrum_stats

## 功能块 drive_esp32_link ← R18

（R18：ESP32 WiFi 链路驱动——UDP 定长流+RSSI 上报固件、串口解析、PER/重传/RSSI、断开先停发射。）

- **drive_esp32_link** [L0|新增]
  - 职责：ESP32 被测链路驱动：维护串口连接、parse_esp32_frame 持续解析 KPI 帧（PER/重传/RSSI）打时间戳产出样本流；串口断开/帧损坏率超阈→stop_transmit_safely 后抛 LinkError；固件（PlatformIO 工程）随库交付。
  - 签名意图：输入: 串口配置 / 输出: KPI 样本流（时间戳+指标）/ 错误: 断开/损坏超阈→LinkError（已停发射）。
  - 调用方：record_run_streams（三路之一）
  - tested 策略：自有单测（样本帧解析+断开处置）
  - 核验命令：测试: dut_esp32
  - **parse_esp32_frame** [L1|新增]
    - 职责：单帧解析：串口行/帧→（seq/期望包/错包/重传/RSSI）类型化样本，校验和与乱序检测。
    - 签名意图：输入: 原始帧字节 / 输出: KPI 样本 / 错误: 坏帧→FrameError（计入损坏率）。
    - 调用方：drive_esp32_link
    - tested 策略：上游覆盖: drive_esp32_link
    - 核验命令：上游覆盖: drive_esp32_link

## 功能块 drive_nrf24_link ← R19

（R19：NRF24 链路驱动——RPD+ARC_CNT/PLOS_CNT 计数上报、无 RSSI 口径、断开处置同 R18。）

- **drive_nrf24_link** [L0|新增]
  - 职责：NRF24 被测链路驱动：串口解析计数帧（丢包/重传 RPD 1bit 门限），样本口径固定"丢包/重传"（不产 RSSI 字段）；断开处置同 drive_esp32_link（先停发射）；固件随库交付。
  - 签名意图：输入: 串口配置 / 输出: KPI 样本流 / 错误: 断开→LinkError（已停发射）。
  - 调用方：record_run_streams（三路之一）
  - tested 策略：自有单测
  - 核验命令：测试: dut_nrf24
  - **parse_nrf24_frame** [L1|新增]
    - 职责：单帧解析：计数寄存器读数→（发送/丢包/重传/RPD）类型化样本。
    - 签名意图：输入: 原始帧 / 输出: KPI 样本 / 错误: 坏帧→FrameError。
    - 调用方：drive_nrf24_link
    - tested 策略：上游覆盖: drive_nrf24_link
    - 核验命令：上游覆盖: drive_nrf24_link

## 功能块 simulate_link_degradation ← R20

（R20：sim 链路退化模型——注入参数驱动的 PER 退化（含悬崖）、模型参数【待实测】校准位、域外夹紧标注。）

- **simulate_link_degradation** [L0|新增]
  - 职责：无硬件 KPI 发生器：订阅注入事件流（样式/功率/频偏），按退化模型（S 形悬崖：低电平近基线 PER、临界档位陡升、参数【待实测】占位可校准）产出与真链路同构的 KPI 样本流；模型域外输入夹紧并标注。
  - 签名意图：输入: 注入事件流+模型参数 / 输出: KPI 样本流（同 normalize_kpi 形状）/ 错误: 不抛出（域外夹紧+标注）。
  - 调用方：record_run_streams（sim 模式 DUT 路）
  - tested 策略：自有单测（单调性+悬崖档位）
  - 核验命令：测试: dut_sim
  - **apply_cliff_model** [L1|新增]
    - 职责：单点退化计算：给定（样式,JSR/电平,频偏）→PER（sigmoid 悬崖），纯函数、参数可注入。
    - 签名意图：输入: 注入状态+模型参数 / 输出: PER / 错误: 域外输入→夹紧值+标记。
    - 调用方：simulate_link_degradation
    - tested 策略：上游覆盖: simulate_link_degradation
    - 核验命令：上游覆盖: simulate_link_degradation

## 功能块 normalize_kpi ← R21

（R21：KPI 数据模型与 PER 口径——两链路+sim 统一模型、PER≤10% 判据、BER→PER 口径声明、异源冲突拒。）

- **normalize_kpi** [L0|新增]
  - 职责：统一 KPI 模型出口：把 ESP32/NRF24/sim 三源样本归一为统一行（时间戳/链路名/PER/重传/RSSI?/来源标记），compute_per 统一计算口径（EN 300 328 判据字段），附口径元数据（BER→PER 声明、F13 数字空缺标注）；异源字段冲突拒绝并指源。
  - 签名意图：输入: 任一源原始样本 / 输出: 统一 KPI 行+口径元数据 / 错误: 字段冲突/类型不符→KpiError（指明源与字段）。
  - 调用方：record_run_streams（DUT 路出口）；execute_gb42590_protocol（判据输入）
  - tested 策略：自有单测
  - 核验命令：测试: kpi_model
  - **compute_per** [L1|新增]
    - 职责：PER 计算纯函数：错误包/总包（窗口参数化），附样本量与置信区间口径；样本量不足返回不可用标记。
    - 签名意图：输入: 错包数/总包数+窗口 / 输出: PER+样本量标记 / 错误: 总包为 0→不可用标记（不抛出）。
    - 调用方：normalize_kpi；check_failure
    - tested 策略：上游覆盖: normalize_kpi
    - 核验命令：上游覆盖: normalize_kpi

## 功能块 record_run_streams ← R22

（R22：三路对齐采集——DUT-KPI∥监测谱∥注入事件统一单调钟、对齐误差统计、单路超时策略。）

- **record_run_streams** [L0|新增]
  - 职责：三路采集编排：并行驱动 DUT 路（真链路或 simulate_link_degradation）、监测路（capture_monitor_spectrum+compute_spectrum_stats）、事件路（append_event 汇聚），统一主机单调钟盖戳；compute_alignment_error 统计对齐误差入结果 JSON；单路超时按策略（记录继续/停止，发射安全优先）处置。
  - 签名意图：输入: 运行上下文+三路源配置 / 输出: kpi.csv+monitor.csv+events.jsonl+对齐统计 / 错误: 关键路（事件/DUT）丢失→停发射+StreamError；监测路丢失→记录降级继续。
  - 调用方：execute_gb42590_protocol；run_demo（采集阶段）
  - tested 策略：自有单测
  - 核验命令：测试: align_streams
  - **compute_alignment_error** [L1|新增]
    - 职责：对齐误差统计：对三路事件按时间邻近配对（如档位变化↔KPI 跳变↔谱变化），产出配对时延分布（P50/P95）。
    - 签名意图：输入: 三路时间序列 / 输出: 对齐误差统计 / 错误: 可配对事件不足→返回样本不足标记。
    - 调用方：record_run_streams
    - tested 策略：上游覆盖: record_run_streams
    - 核验命令：上游覆盖: record_run_streams

## 功能块 execute_gb42590_protocol ← R23

（R23：GB 42590 §5.11 步进协议执行器——噪声/单音/多音、带宽≥链路带宽、−5dB 起 5dB 递增、失效即停记 P_crit、达上限标"未失效"。）

- **execute_gb42590_protocol** [L0|新增]
  - 职责：国标测法编排：按样式（噪声/单音/多音）合成干扰（带宽≥链路带宽校验）→run_baseline_check 放行→run_power_ladder 执行步进（判据=check_failure）→失效时 record_failure_level 记 P_crit→汇总失效电平表；判据永不触发时达上限即停并标注"未失效"。
  - 签名意图：输入: 规范化场景+链路参考功率 / 输出: 协议化结果（失效电平表+各档 KPI 摘要+未失效标注）/ 错误: 步进/采集异常→沿停发射语义上抛 ProtocolError。
  - 调用方：run_demo；serve_console（国标场景卡）
  - tested 策略：自有单测
  - 核验命令：测试: gb42590_executor
  - **check_failure** [L1|新增]
    - 职责：失效判据评估：给定窗口 KPI（compute_per 口径）与阈值（默认 PER>10%），返回失效/未失效+依据；纯函数。
    - 签名意图：输入: PER+样本量+阈值 / 输出: 判定（bool+依据）/ 错误: 样本不足→未失效+样本量标记。
    - 调用方：execute_gb42590_protocol；run_power_ladder（判据回调）
    - tested 策略：上游覆盖: execute_gb42590_protocol
    - 核验命令：上游覆盖: execute_gb42590_protocol
  - **record_failure_level** [L1|新增]
    - 职责：失效电平登记：捕获失效瞬间的档位/电平/JSR/KPI 快照/时间戳，写入运行结果与失效电平表条目（多样式可累积）。
    - 签名意图：输入: 失效上下文 / 输出: 失效电平表条目 / 错误: 上下文字段缺失→补"未知"并标注。
    - 调用方：execute_gb42590_protocol
    - tested 策略：上游覆盖: execute_gb42590_protocol
    - 核验命令：上游覆盖: execute_gb42590_protocol

## 功能块 run_baseline_check ← R24

（R24：无干扰对照段——每轮先跑无干扰基线，异常即中止防误报。）

- **run_baseline_check** [L0|新增]
  - 职责：正式注入前的对照段：不发射干扰采集基线 KPI 窗口，基线 PER 超阈（链路自身故障/环境噪声）→中止运行（独立退出码语义）并给出排查提示；健康则输出基线统计供报告对照。
  - 签名意图：输入: 运行上下文+基线阈值 / 输出: 基线报告（放行/中止+统计）/ 错误: 采集异常→沿停发射语义上抛。
  - 调用方：execute_gb42590_protocol（前置）；run_demo
  - tested 策略：自有单测
  - 核验命令：测试: baseline_guard

## 功能块 plot_triple_curves ← R25

（R25：三元曲线——PER–电平/吞吐–误码/事件时间线三图+中文字体无缺字、数据不足出部分图。）

- **plot_triple_curves** [L0|新增]
  - 职责：由对齐三路数据组装并绘制三张 PNG：build_curve_frames 出数据帧→matplotlib 绘制（内置中文字体注册，全中文标签零缺字）；数据不足时输出已得部分并在结果标注缺项。
  - 签名意图：输入: 运行目录三路数据 / 输出: 三张 PNG+图数据表 / 错误: 全部数据缺失→CurveError；部分缺失→降级出图。
  - 调用方：build_report（图谱来源）
  - tested 策略：自有单测
  - 核验命令：测试: triple_curves
  - **build_curve_frames** [L1|新增]
    - 职责：把三路原始数据规整为三张图的数据帧（x/y 序列+标注点：失效档、档位变化线），纯计算。
    - 签名意图：输入: kpi/events/monitor 数据 / 输出: 三个数据帧 / 错误: 数据空→空帧标记。
    - 调用方：plot_triple_curves
    - tested 策略：上游覆盖: plot_triple_curves
    - 核验命令：上游覆盖: plot_triple_curves

## 功能块 compare_failure_boundaries ← R26

（R26：边界对比与薄弱定位——多样式失效电平对比表+薄弱样式/频点结论。）

- **compare_failure_boundaries** [L0|新增]
  - 职责：跨轮聚合失效电平：多样式/多频点对比表（失效电平升序），定位最薄弱样式/频点（失效电平最低者）并生成结论段（供跳频/纠错改进引用）；样本不足降级单样式报告。
  - 签名意图：输入: 多轮失效电平条目 / 输出: 对比表+定位结论 / 错误: 仅一轮可用→降级标注输出。
  - 调用方：build_report（结论段）；run_demo（多场景汇总）
  - tested 策略：自有单测
  - 核验命令：测试: boundary_compare

## 功能块 write_sigmf_recording ← R27

（R27：SigMF 录制与自动标注——IQ 归档+样式/功率档/时间窗/后端标注、磁盘预检、写失败停发射。）

- **write_sigmf_recording** [L0|新增]
  - 职责：把监测/发射 IQ 按 SigMF v1.2 归档：磁盘空间预检（不足→停发射路径）→数据分块写+元数据（annotate_truth_labels 自动标注）落盘→完成后校验对完整性。
  - 签名意图：输入: IQ 流+运行上下文 / 输出: SigMF 对路径 / 错误: 写失败/磁盘不足→StorageError（已停发射）。
  - 调用方：record_run_streams（录制路）
  - tested 策略：自有单测
  - 核验命令：测试: sigmf_record
  - **annotate_truth_labels** [L1|新增]
    - 职责：把运行事实（样式/参数/功率档序列/时间窗/后端/时钟口径）写入 SigMF 全局与捕获元数据标注段（标准字段+自定义命名空间）。
    - 签名意图：输入: 运行事实 / 输出: SigMF 元数据标注 dict / 错误: 事实字段缺失→该字段标"未知"。
    - 调用方：write_sigmf_recording
    - tested 策略：上游覆盖: write_sigmf_recording
    - 核验命令：上游覆盖: write_sigmf_recording

## 功能块 index_dataset ← R28

（R28：数据集索引与检索——按样式/频段/日期/后端检索、索引损坏重建。）

- **index_dataset** [L0|新增]
  - 职责：跨运行数据集索引：登记每次 SigMF 对与关键标注（样式/频段/日期/后端/失效电平）到索引文件，query_dataset 检索；索引损坏时从 runs 目录重建并告警。
  - 签名意图：输入: 运行记录（登记）或查询条件 / 输出: 索引条目/查询结果 / 错误: 索引损坏→IndexWarn+自动重建。
  - 调用方：train_classifier（取数）；build_report（数据引用）
  - tested 策略：自有单测
  - 核验命令：测试: dataset_index
  - **query_dataset** [L1|新增]
    - 职责：条件检索（样式/频段/日期区间/后端/标签组合），返回 SigMF 路径+标注分组（供训练按批次分组）。
    - 签名意图：输入: 查询条件 / 输出: 条目列表（含批次分组键）/ 错误: 条件字段未知→QueryError。
    - 调用方：index_dataset；train_classifier；grouped_cv_evaluate
    - tested 策略：上游覆盖: index_dataset
    - 核验命令：上游覆盖: index_dataset

## 功能块 make_spectrogram ← R29

（R29：谱图生成——IQ→谱图变换参数化、训练推理共用、短段跳过计数。）

- **make_spectrogram** [L0|新增]
  - 职责：IQ 段→谱图数组（STFT，窗长/重叠/频率轴参数化），训练与推理共用同一实现保证分布一致；段长不足跳过并计数；可输出 PNG 预览。
  - 签名意图：输入: IQ 数组+参数 / 输出: 谱图数组（dB）+跳段计数 / 错误: 参数域错（nfft/hop）→ValueError；IQ 含非有限值→ValueError（含位置计数）；输入空→空谱(0,0)+skipped=1（不抛）。
  - 调用方：train_classifier；grouped_cv_evaluate；predict_style
  - tested 策略：自有单测
  - 核验命令：测试: spectrogram

## 功能块 train_classifier ← R30

（R30：七分类训练——谱图 CNN、remote-compute 派发/本地降级、样本不足拒训、Dry-run。）

- **train_classifier** [L0|新增]
  - 职责：训练入口：query_dataset 取数→make_spectrogram 出特征→样本量检查（不足拒训）→dispatch_remote_training 派发远程 GPU（显式参数才本地 CPU 降级）→回收模型文件+训练日志（指标入 metrics 记录，禁止预写）。
  - 签名意图：输入: 数据查询条件+训练超参+执行地（remote/local）/ 输出: 模型文件+训练报告 / 错误: 样本不足→TrainError；远程不可达且未显式降级→TrainError。
  - 调用方：run_demo（训练场景）；CLI 入口
  - tested 策略：自有单测（小样本 sanity+拒训）；远程 Dry-run
  - 核验命令：测试: train_classifier
  - **dispatch_remote_training** [L1|新增]
    - 职责：把训练任务打包派发到 remote-compute 远程算力（同步数据/拉起任务/回收产物/记录算力选项），失败返回原因供上层决定降级。
    - 签名意图：输入: 训练包（代码路径+数据+超参）/ 输出: 远程产物（模型+日志）/ 错误: 派发/回收失败→RemoteError（含原因）。
    - 调用方：train_classifier
    - tested 策略：上游覆盖: train_classifier
    - 核验命令：上游覆盖: train_classifier

## 功能块 grouped_cv_evaluate ← R31

（R31：分组 CV 评测——按录制批次分组防泄漏、混淆矩阵+Macro-F1、目标 0.85 如实记录。）

- **grouped_cv_evaluate** [L0|新增]
  - 职责：评测协议：make_group_splits 按录制批次（run id）划分 K 折（同批次不跨组）→逐折训练/推理（小模型或已训模型微调口径）→汇总混淆矩阵+Macro-F1+分组泄漏自检（构造段级划分对比实验证明无泄漏高估）；内部目标 0.85 不达标如实记录。
  - 签名意图：输入: 数据集索引+模型工厂+K / 输出: 评测报告（矩阵/F1/泄漏自检）/ 错误: 批次信息缺失→EvaluateError（拒绝评测）。
  - 调用方：train_classifier（训练后评测）；build_report（识别段）
  - tested 策略：自有单测
  - 核验命令：测试: grouped_cv
  - **make_group_splits** [L1|新增]
    - 职责：分组划分纯函数：按批次键把样本分组后划 K 折（组粒度，防段级泄漏），返回折索引；组数<K→降级折数并标注。
    - 签名意图：输入: 样本批次键列表+K / 输出: 折划分 / 错误: 组数不足→降级标注（不抛出）。
    - 调用方：grouped_cv_evaluate；run_rff_pipeline
    - tested 策略：上游覆盖: grouped_cv_evaluate
    - 核验命令：上游覆盖: grouped_cv_evaluate

## 功能块 predict_style ← R32

（R32：识别推理服务——单 run/单段 IQ 出样式+置信度入报告、模型缺失标注不阻塞。）

- **predict_style** [L0|新增]
  - 职责：推理入口：加载模型（缺失→返回"未识别"标注不阻塞主流程）→make_spectrogram→七分类前向→输出（标签+置信度+模型版本）供报告识别段；支持批量段聚合投票。
  - 签名意图：输入: IQ/SigMF 路径+模型（可空）/ 输出: 识别结果行 / 错误: 模型缺失→带标注的未识别结果（不抛出）。
  - 调用方：build_report；serve_console（在线识别）
  - tested 策略：自有单测
  - 核验命令：测试: infer_service

## 功能块 run_emc_conduction_sim ← R33 [P1]

（R33：EMC 传导摸底模拟——模拟 LISN+供电线传导电平流程、图谱段+模拟口径声明。）

- **run_emc_conduction_sim** [L0|新增]
  - 职责：传导摸底模拟流程：以模拟 LISN（sim 仪表）读取供电线传导发射电平（仿真读数模型），按限值线比较出余量图谱段；输出附 make_disclaimer_block 模拟口径声明；真仪表要求经 visa 槽时读数来源标注切换。
  - 签名意图：输入: EMC 场景（频段/限值线）/ 输出: 传导摸底图谱段+声明 / 错误: 场景频段超模拟域→裁剪+标注。
  - 调用方：build_report（EMC 段）；run_demo（EMC 场景）
  - tested 策略：自有单测
  - 核验命令：测试: emc_conduction

## 功能块 run_emc_radiation_sim ← R34 [P1]

（R34：EMC 辐射摸底模拟——屏蔽环境+标准增益补偿模型、辐射图谱+洁净度结论、模拟声明。）

- **run_emc_radiation_sim** [L0|新增]
  - 职责：辐射摸底模拟流程：模拟屏蔽环境天线测量（增益补偿模型经 compensate_link_power 口径），产出辐射发射图谱+频谱洁净度核验结论段；附模拟口径声明。
  - 签名意图：输入: EMC 场景 / 输出: 辐射图谱段+洁净度结论 / 错误: 同 R33 语义。
  - 调用方：build_report；run_demo
  - tested 策略：自有单测
  - 核验命令：测试: emc_radiation

## 功能块 run_emc_sweep ← R35 [P1]

（R35：EMC 步进扫频与杂散/敏感度流程——扫描编排、1kHz–3GHz 模拟口径、越界裁剪。）

- **run_emc_sweep** [L0|新增]
  - 职责：EMC 扫描编排：plan_frequency_sweep 生成步进扫描计划（模拟 EMI 接收机执行，1kHz–3GHz 口径）→逐点采集（杂散发射搜索/敏感度监测流程）→汇总扫描图谱与结论段；频率域越界裁剪并标注。
  - 签名意图：输入: 扫描场景（起止/步进/检波方式）/ 输出: 扫描图谱+结论段 / 错误: 计划空（起止颠倒）→SweepError。
  - 调用方：build_report；run_demo
  - tested 策略：自有单测
  - 核验命令：测试: emc_sweep
  - **plan_frequency_sweep** [L1|新增]
    - 职责：扫描计划纯函数：起止/步进/驻留→有序扫描点表（含检波方式与带宽标注），支持对数/线性两种刻度。
    - 签名意图：输入: 起止频率+步进+刻度 / 输出: 扫描点表 / 错误: 起止非法→SweepError。
    - 调用方：run_emc_sweep
    - tested 策略：上游覆盖: run_emc_sweep
    - 核验命令：上游覆盖: run_emc_sweep

## 功能块 build_gain_calibration ← R36

（R36：发射端增益标定表——标定流程+存储、单调性检查、非单调拒用、【待实测】占位。）

- **build_gain_calibration** [L0|新增]
  - 职责：标定流程编排：逐增益档注入已知信号→读实际功率（仪表/监测通道）→check_monotonicity 校验→存储标定表文件（频率点×增益档→功率）；实测数据缺失时生成【待实测】占位表（禁止预写数字）。
  - 签名意图：输入: 标定测量序列（或占位请求）/ 输出: 标定表文件 / 错误: 样本不足/非单调→CalibrationError（拒用）。
  - 调用方：lookup_jsr（表来源）；set_channel_attenuation（表来源）；CLI 标定入口
  - tested 策略：自有单测
  - 核验命令：测试: gain_calibration
  - **check_monotonicity** [L1|新增]
    - 职责：单调性纯函数：增益档→功率序列非降校验（容差参数化），返回逐点违例列表。
    - 签名意图：输入: (档,功率) 序列+容差 / 输出: 违例列表 / 错误: 不抛出（结果由上层转拒用）。
    - 调用方：build_gain_calibration
    - tested 策略：上游覆盖: build_gain_calibration
    - 核验命令：上游覆盖: build_gain_calibration

## 功能块 calibrate_leakage ← R37

（R37：监测通道回校与自漏扣除——固定几何一次标定、扣除后监测统计、未扣除标注。）

- **calibrate_leakage** [L0|新增]
  - 职责：自漏标定与扣除：固定几何下测 CH1→CH2 耦合系数（频点→耦合 dB 表）存档；监测统计应用扣除（无标定表时标注"未扣除"继续）；回校监测通道增益漂移。
  - 签名意图：输入: 标定会话数据（或扣除请求+监测值）/ 输出: 耦合表/扣除后统计 / 错误: 标定数据不足→CalibrationWarn+未扣除标注。
  - 调用方：compute_spectrum_stats（扣除出口）；capture_monitor_spectrum
  - tested 策略：自有单测
  - 核验命令：测试: leak_calibration

## 功能块 compensate_link_power ← R38

（R38：全链路补偿计算器——公式(6) P_actual=P_measured+L_link+C_ant、无表频点标注。）

- **compensate_link_power** [L0|新增]
  - 职责：公式(6) 补偿：对频点 f 取测量功率+load_calibration_table（L_link 线损表+C_ant 天线系数表）代数和得真实功率；频点无表→结果标"不可信（无补偿表）"；一期覆盖 2.4G/5.8G，全频段表随远期标定扩展。
  - 签名意图：输入: (f, P_measured) 序列+补偿表 / 输出: P_actual 序列+可信度标记 / 错误: 不抛出——表损坏/缺失/占位统一该表贡献 None 且 confidence='no_table'（未知项不计入 p_actual）。
  - 调用方：run_emc_radiation_sim；compute_spectrum_stats；build_report（功率口径）
  - tested 策略：自有单测
  - 核验命令：测试: link_compensation

## 功能块 open_sim_siggen ← R39 [P1]

（R39：1433D 信号源模拟后端——1MHz–20GHz、0.5dB 分辨率/1ppm 仿真口径、插槽接入。）

- **open_sim_siggen** [L0|新增]
  - 职责：1433D 仿真后端（注册名 sim_siggen_1433d）：SCPI 等价参数面（频率 1MHz–20GHz/功率/调制样式），仿真读数口径（0.5dB 分辨率/1ppm/相噪指标仿真相位噪声模型）；超仿真模型域返回标注。
  - 签名意图：输入: SCPI 等价参数 / 输出: 仿真波形/读数 / 错误: 超域→ValueError（消息附模型有效域）。
  - 调用方：manage_backend_registry（注册）；create_visa_driver（命令映射共用）
  - tested 策略：自有单测
  - 核验命令：测试: sim_1433d

## 功能块 open_sim_analyzer ← R40 [P1]

（R40：RSA513A 频谱仪模拟后端——DPX 级监测、≥13.6GHz、±1.5dB 仿真口径、对标表1 规格。）

- **open_sim_analyzer** [L0|新增]
  - 职责：RSA513A 仿真后端（注册名 sim_rsa513a）：观测参数面（频率上限 13.6GHz/RBW/VBW/DPX 帧），仿真谱读数（幅度不确定度 ±1.5dB 仿真模型），规格对标表1 声明；与真实监测流接口兼容。
  - 签名意图：输入: 观测参数 / 输出: 仿真谱数据 / 错误: 超域→ValueError（消息附域）。
  - 调用方：manage_backend_registry（注册）；run_emc_sweep（可配执行仪表）
  - tested 策略：自有单测
  - 核验命令：测试: sim_rsa513a

## 功能块 open_sim_mixer ← R41 [P1]

（R41：13GHz 混频扩展模拟——f_RF=f_LO+f_IF 变换+镜像抑制+本振稳定度→相噪口径。）

- **open_sim_mixer** [L0|新增]
  - 职责：13GHz 混频扩展仿真后端：upconvert_with_image_rejection 执行上变频（f_RF=f_LO+f_IF）与镜像抑制（腔体滤波等效模型），本振稳定度参数→输出相噪口径；串接 sim 信号源/分析仪演示 13GHz 全链。
  - 签名意图：输入: IF/LO 参数 / 输出: RF 仿真流+相噪口径 / 错误: 镜像抑制超域→ValueError（消息附非负域，标注）。
  - 调用方：manage_backend_registry（注册）；open_sim_siggen/open_sim_analyzer（串接）
  - tested 策略：自有单测
  - 核验命令：测试: sim_mixer13g
  - **upconvert_with_image_rejection** [L1|新增]
    - 职责：单次上变频纯函数：IF+LO→RF（含镜像分量幅度按抑制比残留），输出频谱标注。
    - 签名意图：输入: IF 频率/功率+LO+抑制比 / 输出: RF 频率/功率+镜像残留 / 错误: 参数非正→ValueError。
    - 调用方：open_sim_mixer
    - tested 策略：上游覆盖: open_sim_mixer
    - 核验命令：上游覆盖: open_sim_mixer

## 功能块 open_sim_emi_receiver ← R42 [P1]

（R42：EMI 接收机模拟后端——1kHz–3GHz、CISPR 口径读数、-150dBm/Hz 底噪仿真。）

- **open_sim_emi_receiver** [L0|新增]
  - 职责：EMI 接收机仿真后端（注册名 sim_emi_receiver）：CISPR 式读数（峰值/准峰值/平均值检波），频段 1kHz–3GHz、底噪 -150dBm/Hz 仿真口径；供 R33–R35 与独立 EMC 支路演示；所有读数带"模拟"标记。
  - 签名意图：输入: 测量参数（频率/检波/带宽）/ 输出: CISPR 式读数 / 错误: 超域→ValueError（消息附频段域）。
  - 调用方：manage_backend_registry（注册）；run_emc_conduction_sim/run_emc_sweep
  - tested 策略：自有单测
  - 核验命令：测试: sim_emi_receiver

## 功能块 open_sim_attenuator ← R43 [P1]

（R43：程控衰减器模拟后端——≥60dB 量程/纳秒级档仿真、与 R12 同接口可替换。）

- **open_sim_attenuator** [L0|新增]
  - 职责：程控衰减器仿真后端：≥60dB 量程、档位粒度与切换时延仿真（纳秒级口径），实现与 set_channel_attenuation 相同的接口（粗档插件可替换），支撑 0–10km 全量程距离模拟演示。
  - 签名意图：输入: 衰减请求（dB/档位）/ 输出: 实达衰减+切换时延 / 错误: 超量程→ValueError（消息附量程域）。
    （B15 Ruling：五仿真后端统一 ValueError 器件域口径——attenuator 不复用
    set_channel_attenuation 的 AttenuationError，该异常保留给编排层的档位可达域判断，
    器件域校验与编排可达域异常分层。）
  - 调用方：set_channel_attenuation（可替换粗档）；manage_backend_registry
  - tested 策略：自有单测
  - 核验命令：测试: sim_attenuator

## 功能块 run_demo ← R44

（R44：一键命令编排器——单命令串联主链、参数化后端/场景、分阶段退出码、异常先停发射。）

> 演进补注（2026-10-14，R75）：本块新增公共入口 **run_scenario**（`__all__` 导出；无头单场景运行——网页操控台/程序化复用通道，不打印不退出、一切入返回值 dict；与 CLI run_demo 同构编排链，共享 _execute_pipeline/_execute_stage；scenario 完整 dict 直装载为第二通道——网页侧薄载荷的名解析与文件合并在 serve_console 缺省 runner 完成；可选 stop 急停协作容器（B24 C1：{'flag'} 编排旗+'backend' 后端句柄写回通道）；返回 status/exit_code/failure_levels 同 CLI 三态口径，stopped=1 未完成口径）。

- **run_demo** [L0|新增]
  - 职责：CLI 总入口（`demo` 命令）：load_scenario→guard_compliance→autodetect_backend→resolve_clock_reference→manage_run 内 execute_scenario（基线→步进→采集→失效→出结果）→build_report→verify_report_traceability→update_ledger（可选）；退出码 0/1/2 语义贯通；任何异常经 stop_transmit_safely 收尾。
  - 签名意图：输入: CLI 参数（场景路径/后端/选项）/ 输出: 运行目录+摘要行+退出码 / 错误: 校验失败=2；运行失败=1（均已停发射）。
  - 调用方：CLI 入口；CI（sim 全流程验收）
  - tested 策略：自有单测
  - 核验命令：测试: demo_pipeline
  - **execute_scenario** [L1|新增]
    - 职责：单场景执行阶段函数：在 manage_run 上下文内按场景类型分派（gb42590/自定义梯度/距离演变/EMC）编排各功能块，产出统一运行结果对象供报告与台账消费。
    - 签名意图：输入: 运行上下文+场景 / 输出: 运行结果对象 / 错误: 各阶段异常透传（上下文保证停发射）。
    - 调用方：run_demo；serve_console（启动运行）
    - tested 策略：上游覆盖: run_demo
    - 核验命令：上游覆盖: run_demo

## 功能块 build_report ← R45

（R45：报告生成器——三元曲线/失效电平表/监测谱/识别/EMC 段+口径脚注+≥5 频点图谱位、缺项标"缺"。）

- **build_report** [L0|新增]
  - 职责：报告总装：由运行目录组装 report.md+网页视图——plot_triple_curves 图谱、失效电平表、compare_failure_boundaries 结论、监测谱图、predict_style 识别段、EMC 段（如启用）、render_disclaimer_sections 口径脚注、assemble_frequency_plots 频点图谱位（≥5 位，一期按实有频点如实标注）；数字全部来自本 run 数据（R46 校验对象）。
  - 签名意图：输入: 运行目录+结果对象 / 输出: report.md+图集+网页段 / 错误: 产物缺失→该段标"缺项"不虚构。
  - 调用方：run_demo；serve_console（报告中心）
  - tested 策略：自有单测
  - 核验命令：测试: report_builder
  - **render_disclaimer_sections** [L1|新增]
    - 职责：脚注组装：调用 make_disclaimer_block 按报告上下文（后端/时钟/口径选择）拼装完整声明区（PER 口径/非 CISPR/屏蔽盒/仅自建链路/GB 42590 预研定位/数字纪律说明）。
    - 签名意图：输入: 报告上下文 / 输出: 声明区 markdown / 错误: 上下文字段缺失→补"未记录"。
    - 调用方：build_report
    - tested 策略：上游覆盖: build_report
    - 核验命令：上游覆盖: build_report
  - **assemble_frequency_plots** [L1|新增]
    - 职责：频点图谱位组装：收集多频点（2.4G 各信道/5.8G 监测段）图谱，保证报告含 ≥5 个图谱位（不足如实标注缺哪些频点）。
    - 签名意图：输入: 多频点图谱数据 / 输出: 图谱区段+计数 / 错误: 无任何频点→空段标注。
    - 调用方：build_report
    - tested 策略：上游覆盖: build_report
    - 核验命令：上游覆盖: build_report

## 功能块 verify_report_traceability ← R46

（R46：报告数字溯源校验——每个关键数字回溯数据文件行级引用、不一致即失败。）

- **verify_report_traceability** [L0|新增]
  - 职责：溯源校验：extract_report_numbers 抽取报告关键数字→逐个回查 runs 数据文件（kpi/events/monitor）同值存在→不一致列差异并失败；通过则报告页盖"数字可溯源"标记。
  - 签名意图：输入: report.md+运行目录 / 输出: 校验报告（通过/差异清单）/ 错误: 数字无出处→TraceError（列出数字与位置）。
  - 调用方：run_demo（报告后置步骤）
  - tested 策略：自有单测
  - 核验命令：测试: report_traceability
  - **extract_report_numbers** [L1|新增]
    - 职责：从 markdown 报告抽取带上下文的关键数字（电平/PER/JSR/F1 等）与所在行号，供回查。
    - 签名意图：输入: report.md 文本 / 输出: 数字条目列表（值/类型/行号）/ 错误: 不抛出。
    - 调用方：verify_report_traceability
    - tested 策略：上游覆盖: verify_report_traceability
    - 核验命令：上游覆盖: verify_report_traceability

## 功能块 serve_console ← R47

（R47：Web 服务与 API——FastAPI+WS、场景 CRUD/启动急停/状态流/报告列表、非法请求 400 指错。）

> 演进补注（2026-10-14，R75）：场景启动 **双载荷合并契约**——POST /api/run body {'scenario': dict}：全载荷（含 'style'）直行；薄载荷（缺 'style'）须携 'name'，经 scenario_dir/<name>.yaml 全口径装载后在册键覆盖合并（可合并键域 _MERGEABLE_KEYS = 场景在册键 ∪ 执行信封键）。**_KNOWN_KEYS 跨模块耦合**：_MERGEABLE_KEYS 直接取自 src.load_scenario.validate_scenario_schema._KNOWN_KEYS（场景白名单键数单一事实源——键域变动两处同振，audit_responsibility_alignment 以代码实测键数为动态锚校验本契约登记在册）。

- **serve_console** [L0|新增]
  - 职责：Web 服务入口：create_console_app 构建 FastAPI 应用（场景 CRUD、run 启动/急停、状态与实时流端点、报告列表、清单完成度代理端点）+静态页面托管+WS 连接管理；uvicorn 拉起；非法请求 400 带字段级指错。
  - 签名意图：输入: 服务配置（端口/运行根目录）/ 输出: 运行中的服务 / 错误: 端口占用→ServiceError。
  - 调用方：CLI 入口（start 脚本）
  - tested 策略：自有单测（API 合约+急停端点）
  - 核验命令：测试: console_api
  - **create_console_app** [L1|新增]
    - 职责：纯工厂：组装路由/WS hub/静态资源/异常处理为 ASGI 应用（可测试性：不绑端口）。
    - 签名意图：输入: 依赖注入（运行器/实时流源）/ 输出: FastAPI 实例 / 错误: 依赖缺失→AppError。
    - 调用方：serve_console
    - tested 策略：上游覆盖: serve_console
    - 核验命令：上游覆盖: serve_console

## 功能块 render_console_pages ← R48

（R48：操控台前端——Vue3 CDN+Canvas 页面、场景卡/状态/报告中心/清单入口、断线提示重连。）

> 演进补注（2026-10-14，R75）：页面元素枚举更新（演进期实测全集）——急停按钮（#emergency-stop，四分支文案按 /api/stop 响应真值优先：stop_failed 异常/stopped 已停/no_backend 旗置/兜底）；运行结果轮询回显（202→GET /api/runs/{id} 至终态，120s 超时提示转报告中心）；清单完成度内联（/api/ledger 直读 done/total）；场景编辑器区块（#scenario-editor，R57 表单/YAML 双模式）；三路图区（Canvas 实时 KPI/监测/控制帧渲染，R58，急停红标含 emergency_stopped 帧）等；页面骨架经 localize_console_assets 七页化（R56，Vue3 vendor 本地化）。

- **render_console_pages** [L0|新增]
  - 职责：前端页面产出：单文件 HTML+Vue3(CDN)+Canvas 页面（无 Node 构建）——场景卡片、滑杆调参、后端/链路/时钟状态区、报告中心列表、清单完成度入口；build_scenario_cards 由场景目录渲染卡片数据；WS 断线横幅+自动重连。
  - 签名意图：输入: 场景目录+配置 / 输出: 静态页面资产 / 错误: 场景目录空→空态页面（不报错）。
  - 调用方：serve_console（静态托管）
  - tested 策略：自有单测（关键元素 smoke）
  - 核验命令：测试: console_ui
  - **build_scenario_cards** [L1|新增]
    - 职责：把场景文件目录转为卡片数据（名称/描述/样式标签/风险级/推荐后端），供前端渲染。
    - 签名意图：输入: 场景文件列表 / 输出: 卡片数据列表 / 错误: 单个场景损坏→跳过并在卡片列表标注。
    - 调用方：render_console_pages
    - tested 策略：上游覆盖: render_console_pages
    - 核验命令：上游覆盖: render_console_pages

## 功能块 push_realtime_kpi ← R49

（R49：实时 KPI 曲线与急停——WS 推送端到端 <500ms 目标、急停本地直达先停发射、积压降频。）

- **push_realtime_kpi** [L0|新增]
  - 职责：实时流枢纽：订阅三路数据→WS 广播 KPI/监测曲线帧；measure_refresh_latency 测端到端延迟（事件→页面可达戳）入结果 JSON（<500ms 判据）；推送积压自动降频+标注。
  - 签名意图：输入: 实时流源+WS hub / 输出: 广播统计+延迟统计 / 错误: 无订阅者→丢弃帧计数（不报错）。
  - 调用方：serve_console；execute_scenario（运行时挂载）
  - tested 策略：自有单测
  - 核验命令：测试: realtime_console
  - **measure_refresh_latency** [L1|新增]
    - 职责：延迟测量：给事件帧盖发送戳，收到页面回执（或模拟订阅者回执）算端到端延迟分布。
    - 签名意图：输入: 帧戳流 / 输出: 延迟统计（P50/P95/超阈率）/ 错误: 无回执→样本不足标记。
    - 调用方：push_realtime_kpi
    - tested 策略：上游覆盖: push_realtime_kpi
    - 核验命令：上游覆盖: push_realtime_kpi
  - **trigger_emergency_stop** [L1|新增]
    - 职责：急停路径：先 stop_transmit_safely（不经任何队列直调）→再停场景执行→UI 广播急停事件→记录急停事件（操作来源/时刻）。
    - 签名意图：输入: 运行上下文+来源标识 / 输出: 急停结果 / 错误: 停发射本身失败→结果标注（不再抛出，安全路径）。
    - 调用方：serve_console（急停端点）；push_realtime_kpi
    - tested 策略：上游覆盖: push_realtime_kpi（急停断言）+ serve_console
    - 核验命令：上游覆盖: push_realtime_kpi

## 功能块 update_ledger ← R50

（R50：清单台账更新器——✅+日期+锚点写入技术支持版清单、统计节滚动、条目不存在拒、覆盖需显式。）

- **update_ledger** [L0|新增]
  - 职责：台账更新：定位清单条目（locate_ledger_row）→追加/更新「✅ 日期+实现锚点（函数/文件）」状态标注→滚动统计节计数；读测试结果自动或手动指定锚点均可；条目号不存在拒绝、已 ✅ 覆盖需显式参数。
  - 签名意图：输入: 清单条目号+锚点（+覆盖标志）/ 输出: 更新后清单 diff 摘要 / 错误: 条目不存在→LedgerError；冲突覆盖未授权→LedgerError。
  - 调用方：run_demo（验收后可选）；开发流程（每功能完成时）；CI（测试绿自动）
  - tested 策略：自有单测
  - 核验命令：测试: ledger_update
  - **locate_ledger_row** [L1|新增]
    - 职责：在《docs/全功能实现清单-技术支持版.md》中按编号精确定位条目行与状态列位置（结构感知：表格行匹配），返回行号与现状标注。
    - 签名意图：输入: 条目编号+清单路径 / 输出: 行定位+现状 / 错误: 找不到→LedgerError（附相近条目提示）。
    - 调用方：update_ledger；audit_ledger
    - tested 策略：上游覆盖: update_ledger
    - 核验命令：上游覆盖: update_ledger

## 功能块 audit_ledger ← R51

（R51：台账自检与注释率统计——✅ 锚点存在性核对、未完成无 ✅、注释率 ≥20% 结题轮口径。）

- **audit_ledger** [L0|新增]
  - 职责：自检：扫描清单全部条目——✅ 条目的锚点代码/测试在库中真实存在、未完成条目无 ✅、统计节与实际一致；输出差异清单；退出码语义（干净=0）。
  - 签名意图：输入: 清单路径+代码树根 / 输出: 自检报告 / 错误: 锚点失效→列差异（退出码 1）。
  - 调用方：CI；结题轮
  - tested 策略：自有单测
  - 核验命令：测试: ledger_audit
  - **count_comment_ratio** [L1|新增]
    - 职责：代码注释率统计：扫源码树（排除生成物/第三方）计注释行占比，输出分模块明细与总率（≥20% 目标口径）。
    - 签名意图：输入: 代码树根 / 输出: 注释率报告 / 错误: 无可统计文件→空报告标注。
    - 调用方：audit_ledger；结题轮
    - tested 策略：上游覆盖: audit_ledger
    - 核验命令：上游覆盖: audit_ledger

## 功能块 guard_compliance ← R52

（R52：合规红线校验器——功率上限 ≤0dBm 量级+可审计豁免、频段白名单、屏蔽盒提示、仅自建链路声明、不可跳过。）

- **guard_compliance** [L0|新增]
  - 职责：红线总闸：对任意场景/配置依次 check_power_cap（功率上限+豁免审计记录）、check_band_whitelist（2.4G/5.8G 法定频段）、环境与对象声明检查（屏蔽盒提示标志、仅自建链路声明）；任何一关失败即拒（无跳过路径）；load_scenario 前置调用，console 场景保存亦调用。
  - 签名意图：输入: 场景/配置对象 / 输出: 通过（含声明清单）/ 错误: 不抛出——超限→status='rejected' 携带条款清单（功率/频段/声明，不可跳过）。
  - 调用方：load_scenario；serve_console；run_demo
  - tested 策略：自有单测
  - 核验命令：测试: compliance_guard
  - **check_power_cap** [L1|新增]
    - 职责：功率上限纯校验：配置功率 ≤0dBm 量级上限（默认值+显式豁免记录审计条目），返回违例或豁免审计号。
    - 签名意图：输入: 功率配置+豁免凭证（可空）/ 输出: 通过/违例/豁免审计 / 错误: 不抛出（结果由总闸转拒）。
    - 调用方：guard_compliance
    - tested 策略：上游覆盖: guard_compliance
    - 核验命令：上游覆盖: guard_compliance
  - **check_band_whitelist** [L1|新增]
    - 职责：频段白名单纯校验：目标频段 ⊆ 2.4G/5.8G 无人机法定频段（2400–2483.5/5725–5829MHz），返回违例频段。
    - 签名意图：输入: 频段配置 / 输出: 通过/违例清单 / 错误: 不抛出。
    - 调用方：guard_compliance；load_scenario（经总闸）
    - tested 策略：上游覆盖: guard_compliance
    - 核验命令：上游覆盖: guard_compliance

  - **check_env_declarations** [L1|新增]
    - 职责：环境与对象声明纯校验：场景必须含屏蔽盒环境确认标志与仅自建链路声明两个必填字段，缺失即违例清单。
    - 签名意图：输入: 场景声明字段 / 输出: 通过/违例清单 / 错误: 不抛出（结果由总闸转拒）。
    - 调用方：guard_compliance
    - tested 策略：上游覆盖: guard_compliance
    - 核验命令：上游覆盖: guard_compliance

## 功能块 bridge_to_sitl ← R53 [P1]

（R53：SITL 链路退化注入桥——PER 台阶→ArduPilot SITL 丢包/时延注入、无 SITL 跳过不阻塞。）

- **bridge_to_sitl** [L0|新增]
  - 职责：把实测结果桥接 SITL：读运行结果 PER–电平台阶→map_per_to_injection 生成注入计划→经 pymavlink/SITL 参数通道实施链路丢包/时延注入；SITL 不在位/失联→跳过+标注（安全断开），不阻塞主流程。
  - 签名意图：输入: 运行结果+SITL 连接配置 / 输出: 注入会话报告 / 错误: SITL 失联→SitlWarn+安全断开（不抛出）。
  - 调用方：run_demo（可选拓展步）；CLI 独立入口
  - tested 策略：自有单测
  - 核验命令：测试: sitl_bridge
  - **map_per_to_injection** [L1|新增]
    - 职责：映射纯函数：PER–电平台阶→SITL 链路丢包率/时延参数表（分段线性+饱和）。
    - 签名意图：输入: 台阶数据+映射参数 / 输出: 注入参数表 / 错误: 台阶空→空表标注。
    - 调用方：bridge_to_sitl
    - tested 策略：上游覆盖: bridge_to_sitl
    - 核验命令：上游覆盖: bridge_to_sitl

## 功能块 run_rl_policy ← R54 [P1]

（R54：RL 干扰策略器——D3QN 反向用作调度策略、sim 在环小闭环、不收敛回退固定策略。）

- **run_rl_policy** [L0|新增]
  - 职责：RL 策略闭环：在 sim 环境（open_sim_backend+simulate_link_degradation）内以 D3QN 学习样式/功率调度（状态=链路 KPI+监测谱摘要，动作=样式/档位），训练与执行分离；不收敛→fallback_fixed_strategy 回退（如实记录训练曲线）；仅 sim 在环，不做开放辐射。
  - 签名意图：输入: 训练配置+环境工厂 / 输出: 策略模型+训练曲线+回退标记 / 错误: 环境异常→PolicyError（终止训练）。
  - 调用方：CLI 入口；run_demo（策略场景，可选）
  - tested 策略：自有单测（一轮冒烟+回退路径）
  - 核验命令：测试: rl_policy
  - **fallback_fixed_strategy** [L1|新增]
    - 职责：固定策略回退：按场景给定的样式/梯度序列执行（不学习），保证策略场景永有可执行路径。
    - 签名意图：输入: 场景 / 输出: 动作序列 / 错误: 场景非法→ValueError（B20+ Ruling 回写：实测落地为 ValueError——场景形状错口径；PolicyError 属 run_rl_policy 环境异常族，叶子不越权使用）。
    - 调用方：run_rl_policy
    - tested 策略：上游覆盖: run_rl_policy
    - 核验命令：上游覆盖: run_rl_policy

## 功能块 run_rff_pipeline ← R55 [P1]

（R55：RFF 指纹识别管道——自采+公开集子集、轻量模型训练、部署模拟、分组 CV 同口径。）

- **run_rff_pipeline** [L0|新增]
  - 职责：RFF 全管道：数据准备（自采 SigMF+公开集子集适配）→特征/轻量模型训练（蒸馏口径：参数量入报告；时延按元数据口径申报——endpoint 附 latency_note='simulated'，时延缺位申报非实测，B20+ Ruling 回写）→grouped_cv_evaluate 同口径评测→部署模拟（本地推理端点）；数据不足拒训。
  - 签名意图：输入: 数据集配置+训练超参 / 输出: 模型+评测报告+实测数字 / 错误: 数据不足→TrainError。
  - 调用方：CLI 入口；二期交付演示
  - tested 策略：自有单测（管道 smoke+无泄漏断言）
  - 核验命令：测试: rff_pipeline

<!-- ══ 域二十：展示层全能力演进（2026-10-13 fn-divide 演进轮追加；旧块不动） ══ -->

> 资产件清单注（2026-10-14，R75）：report_view_area/run_list_area/comparison_area/dataset_area/train_area/eval_area/infer_area/emc_area/panels_area/calibration_area/audit_area/sitl_area/rl_area/rff_area+build_realtime_charts=装配资产件（页区/图表 HTML 产出函数，调用方=serve_console 缺省装配与 mount_console_extensions 注册），B24–B30 各批申报在案（B25 资产件补注先例：细节件不单列功能块，归各 R 块实现）。

## 功能块 localize_console_assets ← R56

（R56：操控台依赖本地化与多页骨架——Vue3 生产版 vendor 入仓零 CDN、断网全可用；七区导航页骨架。改造点·快速通道：①`render_console_pages` [改造] index 运行页并入导航体系（加导航条+页标识，页面区块职责不变）；②`create_console_app` [改造] 增加一处 `mount_console_extensions` 接线（其余演进端点全部经该挂载点注册，旧函数不再逐个改）。）

- **localize_console_assets** [L0|新增]
  - 职责：操控台资产本地化与骨架产出：把 Vue3 生产版单文件落盘为仓内 vendor 资产并经 mount_console_extensions 注册的 /assets/vendor 路由托管；产出七区页面骨架（总览/运行/报告/数据/AI/仪表/台账），每页零外链（断言无 http(s) 外部资源引用，断网全可用）。
  - 签名意图：输入: 资产目标目录+页面配置 / 输出: vendor 文件+七页骨架资产字典 / 错误: vendor 源缺失→ConsoleAssetError（禁止静默回退 CDN）。
  - 调用方：serve_console（装配时产出）
  - tested 策略：自有单测（vendor 在位+零外链断言）
  - 核验命令：测试: console_offline
  - **render_console_navigation** [L1|新增]
    - 职责：七页骨架与导航条 HTML 生成：统一顶部导航（当前页高亮）+各页容器与区块挂载点（运行页复用既有 index 页区块），不含各功能区块内容（内容归 R57–R74 各自块）。
    - 签名意图：输入: 页名+区块挂载点清单 / 输出: 页面骨架 HTML / 错误: 未知页名→抛出。
    - 调用方：localize_console_assets
    - tested 策略：上游覆盖: localize_console_assets
    - 核验命令：上游覆盖: localize_console_assets
  - **mount_console_extensions** [L1|新增]
    - 职责：演进端点集中挂载点：把 R57–R74 各功能块的服务端点按序注册到 ASGI 应用（单点接线，旧函数 create_console_app 仅调用本函数一次）。
    - 签名意图：输入: FastAPI 应用+依赖注入 / 输出: 已注册扩展的应用 / 错误: 依赖缺失→AppError。
    - 调用方：create_console_app（R56 快速通道接线）
    - tested 策略：上游覆盖: localize_console_assets
    - 核验命令：上游覆盖: localize_console_assets

## 功能块 edit_scenario_ui ← R57

（R57：场景编辑器 UI——页面新建/编辑/删除场景，表单与 YAML 双模式，提交走既有场景 CRUD API，校验错误逐条回显。无旧函数改造：API 端点复用 POST/PUT/DELETE /api/scenarios。）

- **edit_scenario_ui** [L0|新增]
  - 职责：场景编辑器页面区块：表单模式（字段级控件+安全声明必选项）与 YAML 文本模式双切换；新建/编辑/删除三种操作分别接线既有场景 CRUD 端点；服务端校验失败（400 错误清单）逐条上屏指明条目，成功后刷新场景卡片。
  - 签名意图：输入: 场景目录现状（卡片数据）/ 输出: 编辑器区块资产（HTML/JS）/ 错误: 提交失败→错误清单回显（不吞错）。
  - 调用方：serve_console（运行页区块挂载）
  - tested 策略：自有单测（playwright：非法提交见逐条错误、合法提交卡片出现）
  - 核验命令：测试: scenario_editor_e2e

## 功能块 stream_realtime_console ← R58

（R58：实时三路曲线接通——push_realtime_kpi 三路推流接进操控台 /ws hub，Canvas 三图同屏，延迟统计入结果 JSON。改造点·快速通道：`serve_console` 缺省 runner [改造] 运行构造时把 hub 注入执行管线（挂实时流，runner 装载/合并语义不变）。）

- **stream_realtime_console** [L0|新增]
  - 职责：实时流接通：运行执行期间把 KPI/监测谱/注入事件三路帧经 push_realtime_kpi 推入操控台 /ws hub（替代现状空壳回声）；端到端延迟统计（measure_refresh_latency 口径）写入运行结果 JSON；推送积压降频并标注（沿用 R49 口径）。
  - 签名意图：输入: 运行上下文+WS hub / 输出: 广播帧流+延迟统计 / 错误: 无订阅者→丢帧计数不报错；hub 失联→降级离线落盘不中断运行。
  - 调用方：serve_console（runner 挂载，R58 快速通道）
  - tested 策略：自有单测（帧到达+延迟统计）
  - 核验命令：测试: realtime_streams_e2e
  - **render_triple_stream_charts** [L1|新增]
    - 职责：三路 Canvas 图区：KPI 曲线、频谱瀑布、事件时间线三图布局与 WS 帧消费渲染（断线横幅期间缓存重连后续画）。
    - 签名意图：输入: WS 帧流（三路类型标记）/ 输出: 图区渲染资产+消费统计 / 错误: 帧类型未知→跳过计数。
    - 调用方：stream_realtime_console
    - tested 策略：上游覆盖: stream_realtime_console
    - 核验命令：上游覆盖: stream_realtime_console

## 功能块 harden_emergency_stop ← R59

（R59：急停硬接线——/api/stop 从仅置 stop_flag 升级为先 trigger_emergency_stop（先停发射）再置标志。改造点·快速通道：`create_console_app` 停止路由 [改造] 委托本函数（路由形状不变）。）

- **harden_emergency_stop** [L0|新增]
  - 职责：急停硬化序列：收到急停请求→先调 trigger_emergency_stop（内部先 stop_transmit_safely 停发射并记录急停事件）→再置 stop_flag 终止编排→返回已执行反馈（页面按钮状态与广播帧）；停发射本身失败时仍保证标志置位并在结果中报错（安全顺序不可倒置）。
  - 签名意图：输入: 急停请求（来源标识）+运行上下文 / 输出: 急停结果（停发射状态/标志状态/事件引用）/ 错误: 停发射失败→结果标注失败原因，标志仍置位。
  - 调用方：create_console_app 停止路由（R59 快速通道）
  - tested 策略：自有单测（先停发射断言+失败仍置位）
  - 核验命令：测试: emergency_stop

## 功能块 serve_run_artifacts ← R60

（R60：报告站内可读——report.md 服务端渲染为 HTML、plots PNG、原始数据文件下载三端点+溯源结论回显。无旧函数改造：端点经 mount_console_extensions 注册。）

- **serve_run_artifacts** [L0|新增]
  - 职责：运行产物服务端点：GET /api/runs/{id}/report（report.md 经 render_report_html 渲染）、/api/runs/{id}/plots/{name}（PNG 曲线图）、/api/runs/{id}/files/{name}（kpi.csv/events.jsonl 等下载）；报告页回显 verify_report_traceability 的溯源校验结论。
  - 签名意图：输入: 运行 id+文件名 / 输出: HTML/PNG/文件流响应 / 错误: 运行或文件不存在→404；路径穿越（.. 等）→400 拒绝。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（三端点合约+渲染断言+穿越拒绝）
  - 核验命令：测试: report_view
  - **render_report_html** [L1|新增]
    - 职责：report.md→HTML 服务端渲染（markdown 库），产物零外链资源、图片引用改指本服务 plots 端点。
    - 签名意图：输入: report.md 路径+运行 id / 输出: 渲染 HTML / 错误: 文件损坏→渲染错误上抛由端点转 500 带指错。
    - 调用方：serve_run_artifacts
    - tested 策略：上游覆盖: serve_run_artifacts
    - 核验命令：上游覆盖: serve_run_artifacts

## 功能块 list_run_summaries ← R61

（R61：报告中心升级——运行列表从裸目录名升级为元数据行（读各 run 的 result.json），行可钻取进 R60 报告页。无旧函数改造。）

- **list_run_summaries** [L0|新增]
  - 职责：报告中心元数据行：扫描 report_root 下各运行目录，读取 result.json/场景副本提取元数据（时间/场景名/样式/后端/状态/失效电平/报告相对路径），输出列表页数据（新建在前）；result.json 缺失或损坏的行标注"无结果"不虚构、不剔除。
  - 签名意图：输入: report_root / 输出: 运行摘要行列表 / 错误: 单行提取失败→该行降级标注，列表不失败。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（正常行/缺 result 行/排序）
  - 核验命令：测试: report_center_e2e

## 功能块 view_failure_comparison ← R62

（R62：跨轮失效对比视图——compare_failure_boundaries 上页：选运行集→对比表+薄弱环节结论。无旧函数改造：编排函数复用。）

- **view_failure_comparison** [L0|新增]
  - 职责：跨轮对比页：接收运行 id 集→读取各轮失效电平数据→调 compare_failure_boundaries 出对比表与薄弱环节定位结论→表格化上屏；样本不足降级单样式并标注（沿用 R26 口径）。
  - 签名意图：输入: 运行 id 列表 / 输出: 对比表+结论段（页面资产/JSON）/ 错误: 运行无失效数据→标注"未失效"行；全缺→提示选其他运行。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（多轮→对比表断言）
  - 核验命令：测试: boundary_view

## 功能块 browse_dataset_library ← R63

（R63：录音库与数据集浏览——index_dataset list/query 上页：SigMF 真值对卡片+过滤+索引重建入口。无旧函数改造：索引函数复用。）

- **browse_dataset_library** [L0|新增]
  - 职责：录音库页：经 index_dataset 的 list/query 出 SigMF 真值对卡片（样式/功率/时长/批次/运行来源），按样式/日期过滤；索引未建时提示并提供 rebuild 触发（调 index_dataset 重建口径）。
  - 签名意图：输入: 过滤条件（样式/日期区间）/ 输出: 条目页数据+索引状态 / 错误: 索引缺失→状态提示+重建入口（不报错拦页）。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（建库→过滤→重建）
  - 核验命令：测试: dataset_view_e2e

## 功能块 launch_replay_run ← R64

（R64：replay 一键回放——从录音库选条目组装 replay 场景经操控台 runner 发起。改造点·快速通道：`run_demo._backend_params` [改造] 透传 sigmf_path/倍速等 replay 参数（当前仅透传 freq_hz，replay 后端实际不可用——通路补齐，登记项）。）

- **launch_replay_run** [L0|新增]
  - 职责：一键回放编排：从录音库选定条目→build_replay_scenario 组装场景→经操控台 /api/run 发起（复用缺省 runner 与运行态展示）；回放过程在实时曲线与报告中心可见。
  - 签名意图：输入: 录音条目标识（SigMF 路径/来源运行）/ 输出: 回放运行（run_id）/ 错误: 录音损坏或时间轴断裂→装载期报错上屏（退出码语义沿用 R44）。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（sim 侧端到端：录制→入库→回放 exit 0）
  - 核验命令：测试: replay_run
  - **build_replay_scenario** [L1|新增]
    - 职责：录音条目→replay 场景对象：backend='replay'+sigmf_path+倍速+沿用来源场景的频段/安全声明（声明缺失则拒——红线不因回放松动）。
    - 签名意图：输入: SigMF 条目元数据 / 输出: 规范化 replay 场景 / 错误: 声明缺失或文件不可读→ScenarioError 指明。
    - 调用方：launch_replay_run
    - tested 策略：上游覆盖: launch_replay_run
    - 核验命令：上游覆盖: launch_replay_run

## 功能块 launch_classifier_training ← R65

（R65：AI 训练任务页——train_classifier 网页触发（remote/local/dry_run）、后台任务+状态轮询、模型列表。无旧函数改造。）

- **launch_classifier_training** [L0|新增]
  - 职责：训练任务端点与页区：接收训练参数（where=remote/local、dry_run、数据筛选）→后台线程调 train_classifier→任务状态轮询（复用运行表模式）；列出 run_dir/models/ 下已有模型条目；样本不足拒训信息原样上屏。
  - 签名意图：输入: 训练参数 / 输出: 任务句柄+状态流+模型列表 / 错误: 拒训（TrainError）→状态置 failed 带原因；远程不可达→明确报错不静默本地降级（沿用 R30）。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（dry_run 端到端+拒训分支）
  - 核验命令：测试: ai_train_view

## 功能块 view_cv_evaluation ← R66

（R66：AI 评测可视化——grouped_cv_evaluate 网页触发+混淆矩阵/Macro-F1/泄漏警告结果页。无旧函数改造。）

- **view_cv_evaluation** [L0|新增]
  - 职责：评测端点与结果页：接收数据筛选+模型→调 grouped_cv_evaluate→混淆矩阵表格化+Macro-F1+分组泄漏检测警告如实回显；分组信息缺失拒绝信息上屏（沿用 R31）。
  - 签名意图：输入: 数据集筛选+模型标识 / 输出: 评测结果页数据（矩阵/指标/警告）/ 错误: 分组缺失→EvalError 上屏。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（合成数据→矩阵字段断言）
  - 核验命令：测试: ai_eval_view

## 功能块 infer_style_entry ← R67

（R67：AI 主动推理入口——选历史运行/录音→predict_style→样式+置信度+真值对照。无旧函数改造。）

- **infer_style_entry** [L0|新增]
  - 职责：主动推理端点与页区：选定历史运行或录音条目→调 predict_style→样式标签+置信度上屏，并对照该样本的"标准答案"（SigMF 标注/场景副本）显示是否命中；模型缺失提示先训练，不阻塞。
  - 签名意图：输入: IQ 源选择（运行 id/录音条目）/ 输出: 识别结果行（标签/置信度/对照）/ 错误: 模型缺失→提示态（非报错）；样本过短→跳段计数沿用 R32。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（已知样式样本→正确标签）
  - 核验命令：测试: ai_infer_view

## 功能块 demo_emc_flows ← R68 [P1]

（R68：EMC 三流程演示页——传导/辐射/扫频网页可达+图谱+强制模拟口径声明。改造点·快速通道：`execute_scenario` [改造] emc 类型增加子类型分派（conduction/radiation/sweep，缺省 sweep 保持现状行为）。）

- **demo_emc_flows** [L0|新增]
  - 职责：EMC 演示端点与页区：三流程（传导/辐射/扫频）各自参数表单→经 execute_scenario 发起→图谱段与 make_disclaimer_block 口径声明上屏；频率域越界裁剪并标注（沿用 R33–R35）。
  - 签名意图：输入: EMC 流程类型+参数 / 输出: 演示运行+图谱+声明 / 错误: 参数越域→裁剪标注不拒；场景非法→校验错误上屏。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（三流程可达+声明字段）
  - 核验命令：测试: emc_view

## 功能块 demo_instrument_panels ← R69 [P1]

（R69：仪表模拟演示面板——五台远期仪表 sim 面板+VISA 槽位状态。无旧函数改造：open_sim_* 与 create_visa_driver 直接复用。）

- **demo_instrument_panels** [L0|新增]
  - 职责：仪表面板端点与页区：五台模拟仪表（1433D/RSA513A/混频 13GHz/EMI 接收机/程控衰减器）各自面板状态机（打开/读数演示/关闭，经 open_sim_* 工厂）+VISA 槽位注册状态显示；读数超模型域如实标注（沿用 R39–R43 口径）。
  - 签名意图：输入: 面板操作（仪表名+动作+参数）/ 输出: 仿真读数/状态 / 错误: 未打开先读→IllegalStateError；超域→读数带标注不拒。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（五仪表开关+读数合约）
  - 核验命令：测试: instruments_view

## 功能块 view_calibration_status ← R70 [P1]

（R70：标定演示与看板——增益标定/自漏标定/全链路补偿的只读状态+合成数据演示流程。无旧函数改造。）

- **view_calibration_status** [L0|新增]
  - 职责：标定看板端点与页区：三类标定表当前状态（经 load_calibration_table：在位/缺失/【待实测】占位如实显示）+合成数据演示流程一键走（build_gain_calibration 建表→非单调拒用等分支结果上屏）；纯演示与只读，不改真实标定表。
  - 签名意图：输入: 看板查询/演示触发 / 输出: 状态页数据+演示分支结果 / 错误: 演示失败→结果如实上屏。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（看板字段+合成演示分支）
  - 核验命令：测试: calibration_view

## 功能块 view_ledger_audit ← R71 [P1]

（R71：台账审计页——audit_ledger 上页：明细+锚点失效清单+注释率；只读，网页运行仍 ledger=False。无旧函数改造。）

- **view_ledger_audit** [L0|新增]
  - 职责：台账审计端点与页区：调 audit_ledger 出 done/total 明细、锚点失效清单、注释率→表格化上屏；只读——不提供任何写清单入口（网页运行 ledger=False 现状不变，演示现场防误写）。
  - 签名意图：输入: 审计触发（可选清单路径，缺省仓库根锚定）/ 输出: 审计结果页数据 / 错误: 清单路径不存在→AuditError 上屏。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（审计结果字段断言）
  - 核验命令：测试: ledger_audit_view

## 功能块 demo_sitl_bridge ← R72 [P1]

（R72：SITL 桥演示入口——bridge_to_sitl dry_run 演示模式上页（映射预览）；SITL 不在位跳过标注。无旧函数改造。B30 对抗①转 B31 随批（2026-10-14）：run_id 加 report_root realpath 围栏——解析后须落 realpath(report_root) 内（绝对/穿越→ValueError，端点转 400 field='run_id'，对齐 R60/R71 口径）。）

- **demo_sitl_bridge** [L0|新增]
  - 职责：SITL 演示端点与页区：选历史运行→提取 PER-功率台阶→bridge_to_sitl(dry_run=True) 出注入映射预览（台阶→丢包/时延表）上屏；SITL 不在位显示跳过标注不报错（沿用 R53）。
  - 签名意图：输入: 运行 id / 输出: 映射预览+桥接状态 / 错误: 运行无 KPI 数据→提示选其他运行。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（dry_run 映射断言+缺席分支）
  - 核验命令：测试: sitl_view

## 功能块 demo_rl_policy ← R73 [P1]

（R73：RL 策略演示入口——run_rl_policy sim 冒烟演示上页；不收敛回退如实显示。无旧函数改造。）

- **demo_rl_policy** [L0|新增]
  - 职责：RL 演示端点与页区：触发 run_rl_policy sim 小闭环一轮冒烟（短轮次参数固定）→策略动作序列与回报上屏；训练不收敛自动回退固定策略时如实标注回退原因（沿用 R54）。
  - 签名意图：输入: 演示触发（无自由参数或仅轮次）/ 输出: 演示结果（动作序列/回报/是否回退）/ 错误: 演示异常→失败原因上屏（不静默）。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（冒烟一轮+回退分支）
  - 核验命令：测试: rl_view

## 功能块 demo_rff_pipeline ← R74 [P1]

（R74：RFF 管道演示入口——run_rff_pipeline smoke 演示上页：阶段进度+产物。无旧函数改造。）

- **demo_rff_pipeline** [L0|新增]
  - 职责：RFF 演示端点与页区：触发 run_rff_pipeline smoke（小样本固定参数）→取数/谱特征/分组 CV/部署模拟各阶段进度与产物列表上屏；数据不足拒跑提示（沿用 R55）。
  - 签名意图：输入: 演示触发 / 输出: 阶段进度+产物清单 / 错误: 数据不足→拒跑提示上屏。
  - 调用方：mount_console_extensions
  - tested 策略：自有单测（阶段字段+拒跑分支）
  - 核验命令：测试: rff_view

## 功能块 audit_responsibility_alignment ← R75

（R75：责任文档对账与手动改动纳入——responsibility.md 回登记演进期契约变更、fn-review 2026-10-13 四条 Important 闭环、6a417de 后 5 个手动提交裁决=纳入。改造点·快速通道：旧块回登记（run_scenario 公共入口与 dict 第二通道入 R44 块、serve_console 双载荷契约与 _KNOWN_KEYS 耦合入 R47 块、白名单 63 键域入 R1 块、页面元素枚举更新 R48 块）由本技能在实现期执行并留变更说明；本函数承载对账结果的防回归校验。）

- **audit_responsibility_alignment** [L0|新增]
  - 职责：责任文档对账校验：断言 responsibility.md 已含演进期契约登记（run_scenario 入口/双载荷合并契约/场景白名单 63 键域描述/R48 页面元素枚举/域二十新块与 6 处快速通道变更说明），与代码现状锚点交叉（如 _KNOWN_KEYS 键数、__all__ 导出）；漏登即列清单——防"改了代码不回文档"的再次漂移。
  - 签名意图：输入: 责任文档路径+代码根 / 输出: 对账报告（已登记项/漏登清单）/ 错误: 文档或锚点文件缺失→对账失败上抛。
  - 调用方：维护与验收命令（pytest）
  - tested 策略：自有单测（构造漏登→检出；全登→通过）
  - 核验命令：测试: responsibility_alignment

## 功能块 prepare_demo_assets ← R76

（R76：手册总章——两档设备清单与连接（便携/全量各自全量清单，补充小件直接并入不单列）+ASCII 连接图与接线表+主机环境启动+演示前准备。**文档交付物**：docs/功能演示手册.md 总章由实现批撰写（规格=需求 R76）；本函数承载总章中**可执行**的演示前准备物料——预置场景、预跑历史（操控台报告中心/录音库/AI 页有数据可翻）、出发检查单。批序首位：R76 → R85/R86 → R77…R84。）

- **prepare_demo_assets** [L0|新增]
  - 职责：演示物料准备编排：seed_preset_scenarios 把内置演示场景模板集写入 scenarios/（清单与手册总章一一对应：冒烟零失效/失效演示/距离演变/带录音攒数据/EMC/编辑器练手等）→ prewarm_demo_runs 预跑若干轮 sim 运行落 runs/（走 run_demo 既有入口；含 record:true 轮次以产出带标注 SigMF 录音供 AI 页与录音库演示）→ 汇总物料报告与出发前检查单数据（两档设备勾选表+环境自检命令结果）。幂等：目标已存在不覆盖，显式 overwrite 才覆盖。
  - 签名意图：输入: scenario_dir / runs_root / 预跑轮次配置（overwrite=False）/ 输出: 物料报告（写入场景清单+预跑运行目录列表+检查单数据）/ 错误: 目录冲突未授权覆盖→拒绝并列冲突项。
  - 调用方：演示者命令（手册总章；entry 类）
  - tested 策略：自有单测（临时目录：预置齐+预跑退出码语义正确+幂等拒覆盖）
  - 核验命令：测试: demo_assets
  - **seed_preset_scenarios** [L1|新增]
    - 职责：把内置演示场景模板集（与手册总章清单一致）写为 scenarios/ 下 YAML 文件；文件已存在即计为冲突项不覆盖（内容异同不区分——保守侧）。〔措辞对齐·快速通道 2026-10-14：原文「已存在且内容不同」与实现（已存在即冲突）分歧，B32 对抗 M1；行为取更保守侧，实现为真值〕
    - 签名意图：输入: 目标目录（+overwrite）/ 输出: 写入文件清单+冲突清单 / 错误: 目录不可写→上抛。
    - 调用方：prepare_demo_assets
    - tested 策略：上游覆盖: prepare_demo_assets
    - 核验命令：上游覆盖: prepare_demo_assets
  - **prewarm_demo_runs** [L1|新增]
    - 职责：按配置预跑若干轮 sim 运行（场景取预置集，逐轮走 run_demo 既有入口）落 runs/；校验各轮退出码语义（--demo 口径 exit 1=测到失效属预期产出，如实登记不算失败）；单轮意外失败即中止并列已跑清单（不吞错）。
    - 签名意图：输入: 场景清单+runs_root+轮次配置 / 输出: 运行目录列表+各轮退出码 / 错误: 意外退出码→中止并报告。
    - 调用方：prepare_demo_assets
    - tested 策略：上游覆盖: prepare_demo_assets
    - 核验命令：上游覆盖: prepare_demo_assets

## 功能块 check_demo_manual ← R84（承载 R76–R84 结构自检）

（R84：手册附录+总装——现场应急速查表（症状→处置，覆盖 README FAQ 全部条目）+总目录+出发前检查单；**全手册结构自检**是本块可执行核心，R77–R83 各批验收命令即本函数按批登记的期望章节集执行（期望集随批增长）。）

- **check_demo_manual** [L0|新增]
  - 职责：手册结构体检：解析 docs/功能演示手册.md——①断言期望功能条目集齐（期望集按已交付批登记，缺条目点名）；②每条目四件套小节齐（功能说明/两档所需设备及连线/操作步骤/预期现象）且两档（便携/全量）标注齐；③全文无"待定/TODO/占位"残留标记；④附录应急速查表覆盖 fn_docs/README.md「常见问题」全部条目（标题关键词映射，未覆盖点名）。汇总输出体检报告。
  - 签名意图：输入: 手册路径+README 路径+期望条目清单 / 输出: 体检报告（ok 布尔+缺失条目/缺件/占位/FAQ 未覆盖四清单+通过项计数）/ 错误: 手册或 README 文件缺失→上抛。
  - 调用方：验收命令（pytest；test+entry 类）
  - tested 策略：自有单测（构造缺件/占位/FAQ 缺覆盖手册→检出；完备手册→通过）
  - 核验命令：测试: demo_manual_check

## 功能块 esp32_wifi_firmware ← R85

（R85：ESP32 WiFi 链路固件工程——PlatformIO 工程 fn_work/firmware/esp32_wifi/（platformio 装进 .venv，不动全局）。**拓扑定桩=成对节点**：发送节点按固定节拍向接收节点发定长 UDP 载荷（payload 含递增 seq）；接收节点按 seq 缺口统计丢包 err、以重复 seq 计应用层重发 retries、累计期望包数 sent、周期读自身 WiFi RSSI，经 USB 串口吐 KPI 帧。**帧协议与 parse_esp32_frame 契约逐字对齐**：`ESP,<seq>,<sent>,<err>,<retries>,<rssi>[*<hex>]`，校验和=帧体 sum&0xFF 十六进制；计数口径在工程 README 声明，实测数字禁止预写。本期**编译级验证**（pio run+Python 帧参考实现往返）；烧录与射频联调随 R87。）

- **esp32_wifi_firmware** [L0|新增]（PlatformIO 工程交付物——C++；编排单元）
  - 职责：固件工程主体：节点角色配置（发送/接收二选一，构建参数区分）、WiFi 与串口初始化、主循环编排（发送角色→udp_stream_task；接收角色→kpi_report_task）；platformio.ini 与构建说明（两角色构建/烧录命令、波特率）随工程交付。
  - 签名意图：输入: 构建角色参数（NODE_ROLE=tx/rx）/ 输出: 可烧录固件映像（pio run 产物）/ 错误: 编译失败→构建非零退出。
  - 调用方：演示者烧录命令（手册链路健康测量条目；entry 类）
  - tested 策略：编译级（pio run）+上游覆盖: compose_esp32_frame 往返
  - 核验命令：测试: firmware_esp32
  - **encode_esp32_frame** [L1|新增]（C++）
    - 职责：KPI 帧编码：五指标→`ESP,<seq>,<sent>,<err>,<retries>,<rssi>` 文本行+可选校验和后缀（帧体 sum&0xFF 十六进制）+\n——与 parse_esp32_frame 严格口径互逆（整数字段非负十进制、rssi 浮点或 NA；rssi 语义域 [-1000,1000] dBm，域外/非有限→钳 NA 不吐数值帧——Python 参考实现同域拒绝 ValueError，两侧"域外不吐数值帧"契约一致）。〔措辞对齐·快速通道 2026-10-14：原文「值域非法→钳制并计数」之"计数"半未落地（计数参数类型层非负、数据路径不可达）且 B33 对抗 F1 实证大有限值截断破等价——改为语义域钳制口径，行为以实现为真值〕
    - 签名意图：输入: 五指标值（+校验和开关）/ 输出: 帧文本行 / 错误: 值域非法→固件侧钳制并计数（不吐非法帧）。
    - 调用方：kpi_report_task
    - tested 策略：上游覆盖: compose_esp32_frame（Python 同规格往返）
    - 核验命令：上游覆盖: firmware_esp32
  - **udp_stream_task** [L1|新增]（C++）
    - 职责：发送节点业务流：定长 UDP 载荷（含递增 seq）按固定节拍发往接收节点地址；发送失败与 WiFi 掉线计数并重连。
    - 签名意图：输入: 目标地址/节拍/载荷长 / 输出: 无线业务流 / 错误: WiFi 掉线→重连+计数（不中断主循环）。
    - 调用方：esp32_wifi_firmware（发送角色主循环）
    - tested 策略：编译级；真机联调随 R87
    - 核验命令：上游覆盖: firmware_esp32
  - **kpi_report_task** [L1|新增]（C++）
    - 职责：接收节点统计与上报：按 seq 缺口算 err、重复 seq 计 retries、累计 sent、周期读 RSSI（NA 化处理不可得值）；encode_esp32_frame 编码后吐串口。
    - 签名意图：输入: 收包回调流 / 输出: 串口 KPI 帧流 / 错误: 计数回绕→置标记位并继续（不断流）。
    - 调用方：esp32_wifi_firmware（接收角色主循环）
    - tested 策略：编译级；真机联调随 R87
    - 核验命令：上游覆盖: firmware_esp32
  - **compose_esp32_frame** [L1|新增]（Python——帧协议参考实现，落 drive_esp32_link 包）
    - 职责：Python 侧帧生成（与固件 encode_esp32_frame 同规格）：五指标→合法帧文本（含校验和后缀可选路径），供固件往返用例与解析器测试复用——固件与解析器协议漂移的单点防线。
    - 签名意图：输入: 五指标值（+checksum 开关）/ 输出: 帧文本 / 错误: 非法值域→ValueError。
    - 调用方：pytest 往返用例（test+entry 类）
    - tested 策略：自有单测（compose→parse 往返全字段一致；非法值拒）
    - 核验命令：测试: dut_esp32（往返用例族）

## 功能块 nrf24_link_firmware ← R86

（R86：NRF24 链路固件工程——PlatformIO 工程 fn_work/firmware/nrf24_link/。**拓扑定桩=一对 ESP32+RF24 节点**：ESB（自动应答）模式对发定长包；**发送节点为报告节点**——sent=已发累计、lost=PLOS_CNT、retries=ARC_CNT、seq 递增，rpd=报告节点发包间隙短暂进监听窗读 RPD 锁存位（0/1）。**帧协议与 parse_nrf24_frame 契约逐字对齐**：`NRF,<seq>,<sent>,<lost>,<retries>,<rpd>`（六字段严格非负整数）。编译级验证同 R85；烧录联调随 R87。）

- **nrf24_link_firmware** [L0|新增]（PlatformIO 工程交付物——C++；编排单元）
  - 职责：固件工程主体：SPI/RF24 初始化、ESB 通道参数（与手册演示频段一致）、主循环编排 esb_traffic_task+counter_report_task；platformio.ini 与构建说明随工程交付。
  - 签名意图：输入: 构建角色（发送报告节点/对端）/ 输出: 可烧录固件映像 / 错误: 编译失败→构建非零退出。
  - 调用方：演示者烧录命令（entry 类）
  - tested 策略：编译级（pio run）+上游覆盖: compose_nrf24_frame 往返
  - 核验命令：测试: firmware_nrf24
  - **encode_nrf24_frame** [L1|新增]（C++）
    - 职责：KPI 帧编码：五计数值→`NRF,<seq>,<sent>,<lost>,<retries>,<rpd>` 文本行+\n——与 parse_nrf24_frame 严格口径互逆（字段非负十进制整数、rpd∈{0,1}）。
    - 签名意图：输入: 五计数值 / 输出: 帧文本行 / 错误: 值域非法→固件侧钳制并计数。
    - 调用方：counter_report_task
    - tested 策略：上游覆盖: compose_nrf24_frame（Python 同规格往返）
    - 核验命令：上游覆盖: firmware_nrf24
  - **esb_traffic_task** [L1|新增]（C++）
    - 职责：ESB 业务流：定长载荷（含递增 seq）按固定节拍经 RF24 自动应答模式发送；发送失败与掉线计数。
    - 签名意图：输入: 通道参数/节拍/载荷长 / 输出: 无线业务流 / 错误: 发送失败→计数并继续。
    - 调用方：nrf24_link_firmware（发送角色主循环）
    - tested 策略：编译级；真机联调随 R87
    - 核验命令：上游覆盖: firmware_nrf24
  - **counter_report_task** [L1|新增]（C++）
    - 职责：计数与上报：周期读 NRF24 状态寄存器（PLOS_CNT/ARC_CNT）累计 lost/retries、维护 sent/seq、发包间隙短监听窗读 RPD；encode_nrf24_frame 编码后吐串口。
    - 签名意图：输入: 寄存器读数流 / 输出: 串口 KPI 帧流 / 错误: 计数回绕→置标记位并继续。
    - 调用方：nrf24_link_firmware（发送角色主循环）
    - tested 策略：编译级；真机联调随 R87
    - 核验命令：上游覆盖: firmware_nrf24
  - **compose_nrf24_frame** [L1|新增]（Python——帧协议参考实现，落 drive_nrf24_link 包）
    - 职责：Python 侧帧生成（与固件 encode_nrf24_frame 同规格）：五计数值→合法帧文本，供固件往返用例与解析器测试复用——协议漂移单点防线。
    - 签名意图：输入: 五计数值 / 输出: 帧文本 / 错误: 非法值域（含 rpd∉{0,1}）→ValueError。
    - 调用方：pytest 往返用例（test+entry 类）
    - tested 策略：自有单测（compose→parse 往返全字段一致；非法值拒）
    - 核验命令：测试: dut_nrf24（往返用例族）
