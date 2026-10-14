# batches.md —— 批次表（待办导航）
> fn-implement 独占更新。▶ = 下一批要完成的任务；未经批间门批准不得增删批次内容。

| 批次 | 函数/任务清单 | 验收点 | 注 |
|---|---|---|---|
| ▶ B34 | compose_nrf24_frame, encode_nrf24_frame, esb_traffic_task, counter_report_task, nrf24_link_firmware | pio run reporter/peer SUCCESS + dut_nrf24 往返族全绿 + tests/firmware_nrf24 镜像自证 | R86；同上 |
| B35 | 手册·测评核心五章（一键测评/六类样式/国标测法/距离模拟/链路健康测量） | 每章四件套+两档设备标注；章内命令 sim 侧逐条走查绿；check_demo_manual 期望集 +5 | R77 文档批 |
| B36 | 手册·记录与报告四章（三路同步/自动报告/溯源校验/录音库） | 同 B35 口径；期望集 +4 | R78 文档批 |
| B37 | 手册·AI 识别章（攒数据→训练→评测→当场识别） | 同上（训练走 dry_run/本地轻量演示路径）；期望集 +1 | R79 文档批 |
| B38 | 手册·模拟与扩展三章（EMC 摸底/远期仪表/三后端切换） | 同上；期望集 +3 | R80 文档批 |
| B39 | 手册·安全与台账二章（安全红线/清单台账） | 同上（台账演示走 --ledger 副本清单）；期望集 +2 | R81 文档批 |
| B40 | 手册·二期进阶三章（SITL 联动/RL 策略/RFF 指纹） | 同上（dry_run/冒烟演示口径）；期望集 +3 | R82 文档批 [P1] |
| B41 | 手册·操控台七页章（总览/运行/报告/数据/AI/仪表/台账+标定） | 页面操作实起服务/playwright 走查绿；期望集 +8 | R83 文档批 |
| B42 | 手册附录（应急速查表+总目录+出发检查单）+全手册总装 | check_demo_manual 全集绿：26 条目四件套齐+两档标注齐+FAQ 覆盖零遗漏+零占位 | R84 收口 |

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
| 10-12 | Ruling⑲B12 集成 | read_samples 三方契约归一层+真后端 E2E；空读上限；esp err 回退对齐 |
| 10-12 | Ruling⑳B12 双审 | 中3低3 全修+13 回归；sim ts 主机域/fsum 恰等阈/sample_rate 域；R27 必填口径回写 |
| 10-12 | Ruling㉑B13 双审 | 中1低5 全修+10 回归；params 嵌套合并/ctx 回落/aborted 事件 |
| 10-12 | Ruling㉒B14 申报 | predict_style 本批 cnn_dummy 规则判据（真 CNN 远期 unsupported_model 如实）；grouped_cv 泄漏自检对照固定内置 dummy 口径（自定义回调不重复调用——docstring 裁决）；train local=cnn_dummy 类均值模型 |
| 10-12 | Ruling㉓B14 双审 | 中3低3（修 5 申报 1）+18 回归；泄漏自检饥饿排除/pulse 重标定/序列化预检 |
| 10-12 | Ruling㉔B14 复核 | 饥饿/泄漏并存三态文案；sweep 验收措辞如实 |
| 10-12 | Ruling㉕B15 申报 | 混频 +3dB 简化/QP 简化曲线/500ns 标称/beyond_model/simulated 标记 |
| 10-12 | Ruling㉖B15 双审 | 三轴中2+对抗中2低4 全修+8 回归；ValueError 统一口径回写；qp 保序 |
| 10-12 | Ruling㉗B16 申报 | 对数 step=每步增量比（1+r 规范）；EMC 演示态限值缺省不判 |
| 10-12 | Ruling㉘B16 双审 | 高1中2低3+观察 全修+19 回归；点数上限/NaN 家族对齐/补偿 confidence |
| 10-12 | Ruling㉙B17 申报 | 统计节人工滚动/回退解析局限/死锚 token 口径 |
| 10-12 | Ruling㉚B17 双审 | 高1中4低2 修7申报2+24 回归；真清单 append 列方案（状态列结构守卫）；转义管道/CRLF/数值统一/done 同源 |
| 10-12 | Ruling㉛B18 双审 | 高2中8低6 修13申报3+28 回归；溯源假阴性三路堵死（词界/白名单收缩/舍入去）；探针断言随口径更新 |
| 10-12 | Ruling㉜B18 复核 | 13/13 生效；尾零/U+2212 等值盲区申报留观（现产不触发） |
| 10-12 | Ruling㉝B19 申报 | 装库后 skip 转实跑暴露 6 真缺陷（annotations 注解解析）已修；延迟 import 口径 |
| 10-12 | Ruling㉞B19 双审 | 三轴中2（slug/CRUD）+对抗中2低4 全修+25 回归；stop 复位/run 可查/降频不稀释 |
| 10-12 | Ruling㉟B20 申报 | RL=numpy Q-learning 轻量替身；SITL 简化 mock MAVLink 层 |
| 10-12 | Ruling㊱B20 双审 | 三轴 3 低+对抗 中1低3 全修+5 回归；rff hp 透传/PolicyError 统一/时延申报 |
| 10-12 | Ruling㊲B21 终批 | 高1中1低1+TX 真机 bug 全修+74 回归；场景文件路线复活（信封键白名单）；119/119 wired 收官 |
| 10-13 | 演进周期初建 9 批（B23–B31） | 域二十 25 函数+6 改造点，垂直切片：地基→实时安全→报告→数据回放→AI→EMC 仪表→标定台账→二期→对账收尾 |
| 10-13 | Ruling：serve_console 缺省装配七页产出（R56 第 3 触点） | 七页托管是 R56 验收硬件；tracker Ruling 行互指；存量用例 way3 期望同步（CDN 单页→七页 vendor） |
| 10-13 | Ruling：B23 实现口径校正两处 | starlette 1.8 无 route 属性→get+routes 探测；AppError 延迟 import 防循环互导；批间评审复核 |
| 10-13 | 对抗审查 I2 修复：edit_scenario_ui 补排 B24 | 切批遗漏（24≠25，B31 桩归零门会撞）；批间门裁决前置修正 |
| 10-13 | 对抗审查 I3 修复：E3 证据文本校正 | fn-step-done 落盘剥反斜杠致命令不可复现；已按实跑口径改写并留 Ruling |
| 10-13 | B24 申报三则 | ①sim 管线 monitor.csv 恒空（实证）——频谱路集成尾随+WS 链双覆盖；②create_console_app 极小改两处（deps 可选 hub/run_ctx）；③叶子 JS 加 window 计数钩（断言用，渲染零变化） |
| 10-14 | 对抗 C1 修复三申报 | ①run_scenario 增可选 stop 参数（签名微调：容器形状 docstring 登记，backend 由管线写回，status=stopped/exit 1 归一）；②render_console_pages 急停按钮 JS 真实化（白名单授权面，16 行：真值优先于硬编码文案）；③emergency_stopped 广播帧发送方补齐（对齐 push_realtime_kpi 既有形状） |
| 10-14 | R58 验收口径注记 | sim 管线 monitor.csv 恒空（实证）——频谱路验收=集成尾随真文件+WS 链双覆盖，真运行 spectrum 帧恒 0 属平台既有行为非本批缺口 |
| 10-14 | B25 资产件补注（快速通道） | 页区资产函数 report_view_area/run_list_area/comparison_area（B25）与 build_realtime_charts（B24）为各 R 块实现细节件（调用方=serve_console 装配/mount 注册），responsibility 块引言由 B31 旧块回登记统一补注 |
| 10-14 | B25 档案勘误 Ruling（评审 C1/I1/对抗 I-2） | ad9eb38 声称的端点注册+页区实际落 8148d85（per-fn add 范围执行差），95cfe63 wired 证据前指 7b4854f——两处提交级归属失真以本 Ruling 收口，不重写历史；计数 14/12 假数已正（13/13+通道 8） |
| 10-14 | B25 XSS 修复申报 | 渲染层自证安全三件：源转义（> 引用标记还原）+URL 方案守卫（javascript:/data:/vbscript:→#、srcdoc 剥离）+零外链断言保持；全链双向探针在案（旧渲染器污染对照）；report_view_area 注释改如实 |
| 10-14 | B26 申报 | replay 场景 scenario_type=custom（replay 无发射能力，gb42590 start_tx 不可用——监测路按录制时间轴回放）；launch_replay_run import 副作用注册 replay 后端；_backend_params 按类型透传（向后兼容） |
| 10-14 | B26 勘误 Ruling（评审中1，B25 C1 复发） | 3885ed3 提交级证据前指 9dc39e3（端点/页区/e2e 随最后函数落盘）——根因=多函数单子代理的 per-fn 拆提交惯例；此后该形态一律整批单提交或证据锚定末提交；低1：run_demo _normalize_scenario_object 第二触点并入 R64 改造点登记 |
| 10-14 | B26 对抗中2 转 B27 随批 | ①e2e 录制场景 num_samples>0（空录音使回放空转也绿）；②索引入口 runs_root 路径围栏+register 透传收缩 |
| 10-14 | B27 申报 | 整批单提交（惯例修正首发）；sim record:true 结构性空录音实证→e2e 改合成预置 SigMF（8192 样本，判别力封死空对回放）；source_scenario 白名单收缩落点=操控台索引入口消费边界 |
| 10-14 | B27 对抗中1/低1 转 B28 随批 | ①replay 围栏补 .sigmf-data 路径 realpath 校验（软链出界 202 放行）；②local+dry_run 复选框失联（train_classifier dry_run 仅 remote 分支消费） |
| 10-14 | B28 申报（中断续做） | 首子代理额度中断留 src 半成品（测试全缺）——续做子代理核实+补测 27 例；emc_area SVG 命名空间字面量踩零外链断言→canvas 改造；B27 随批 a/b 首代理已写、续做补测 3 例 |
| 10-14 | B28 对抗低2转B29随批 | ①/api/emc/{flow} params 展开序收紧（端点保留字 scenario_type/emc_flow 后置防覆写）；②serve_console:393/emc_area:19 SVG 注释改 canvas 口径；观察：硬链出界属 realpath 围栏固有限（威胁模型=本地 fs 写权限，不追） |
| 10-14 | B29 申报 | 随批 a 展开序现场在 demo_emc_flows.py:182（白名单外单文件，登记项落地处）；calibration_area/audit_area 两资产件（先例） |
| 10-14 | B29 对抗中1低2转B30随批 | ①/api/ledger/audit 的 ledger_path/code_root 加仓库根围栏（realpath 对齐 replay 口径——/etc/passwd→200 与 code_root=/ 全盘扫 DoS 面收口）；②400 field 错标修正（空白 ledger_path→field=ledger_path）；③勘误：随批 a 锚点 :178→:182（docstring 增行漂移） |
| 10-14 | B30 申报（网络中断续做） | 首派连接中断仍留半成品（同 B28 模式）——续做核实收全；sitl/rl/rff_area 三资产件（先例）；审计围栏 _r71_fence 对齐 replay 口径 |
| 10-14 | B30 对抗中1低3转B31随批 | ①/api/demo/sitl run_id 加 report_root 围栏（绝对路径被 os.path.join 丢弃→界外读，对齐 R60/R71 口径）——**B31 已落地**（demo_sitl_bridge realpath+commonpath 围栏，ValueError→端点 400 field='run_id'，+2 测）；②calibration demo field 分流库层已正（HTTP 层 FastAPI 先 coerce，不追）；③围栏 TOCTOU 理论窗（演示台威胁模型不追）；④RL converged 判据弱（已如实标注，不追）。另 B24 三观察（tracker 注记）同批顺修：/api/run 启动复位清 stop_flag['backend'] 旧句柄（+1 测）、编辑器模式切换/YAML 重贴清 #editor-errors 陈旧警示（+1 测）、急停四分支文案字符串级测试（+1 测） |
| 10-14 | B31 收尾申报 | fn-review 四 Important 就此闭环（R75 承接兑现）；资产件 14+build_realtime_charts 补注入域二十引言；域二十 25/25 wired 桩归零 |
| 10-14 | B31 对抗中1低2处置 | ①fn-check venv 架空修复：.venv/bin/pytest 控制台脚本重建（force-reinstall），fn-check②现走 venv 口径 3411+5 全部通过（环境域修复，gitignore 域登记）；②低 2（R72 run_id="." 过栏、audit 伪块头同号顶替）记为已知限界交 fn-close 终检呈报 |
| 10-14 | 走查环修复申报（F2/F3 根因）：**B26 申报的「sim 管线 monitor.csv 恒空」口径作废**——SimBackend.read_samples 静默态产低功率底噪块（每实例 64 块预算，meta synthetic=noise_floor；open_sim_backend docstring 在册）后，record:true sim 运行实证 monitor.csv 数据行 56320、SigMF data 112640 字节/num_samples 14080（tests/run_demo/test_sim_delivery_record_true.py 硬判据族）；同根修复：sim 源 kpi 行主机单调钟盖戳+gb 判据窗样本重追加（三元曲线各档开窗有样本，报告无缺帧）、--demo dwell 0→2ms（int 毫秒事件戳可分辨） | 走查环 F2/F3/F4（/tmp/walkthrough_report.md）：采集窗与发射窗不交致监测/录制/曲线/SITL 数据面恒空 |
| 10-14 | 周期②初建 11 批（B32–B42） | 域二十一：R76 物料+总章→R85/R86 固件（编译级）→R77–R83 手册七批（26 章节四件套+两档标注）→R84 附录总装；批序循 grill 裁决 |
| 10-14 | scaffold 基线提交 2e89dbf | 对账子代理建议采纳（B1/B4 型零代码提交先例）：14 桩+域二十一文档+platformio 先行入库，wired 提交不再收编脚手架 |
| 10-14 | check_demo_manual 前置 B32（偏离 R84 批序） | 检查器随首批实现、期望集随批增长——使每个手册批的验收命令 pytest -k demo_manual_check 可执行；B42 只收口附录+全集（原因：批批可用；代价：无；落点：本行+tracker B32 注） |
| 10-14 | 档位裁决=子代理逐函数（用户批表门口选择） | B32–B34 函数批：子代理实现+主会话调度/记账/串行提交（subagent 不动 git）；B35–B42 文档批主会话撰写、走查证据贴主会话 |
| 10-14 | B32 prewarm 两申报 | ①签名微调：增仅关键字 scenario_dir=None（场景名目录上下文，预授权项）；②落点口径：预跑走 run_scenario 无头等价入口非 run_demo CLI——后者 runs_root 硬编码 cwd 相对且台账缺省开启会污染清单；台账缺省不动=预跑不写清单（子代理申报，主会话核实采纳） |
| 10-14 | B32 对抗处置（Critical 0/Important 2/Minor 4） | I1 验收命令期望集零落点→修复子代理落地 expected_entries.txt 机制+smoke 硬门；I2 手册 0.5 补数据集索引重建步骤；M1 responsibility seed L1 措辞对齐（快速通道在块内登记）；M2 备件包补 USB 集线器+12/14 聚合口径注；M3 检查器三洞（围栏内两档词/FAQ 散文单行/首匹配歧义）**转 B33 随批**（全词优先 B42 收口前）；M4 总章走查证据补强注记入 tracker |
| 10-14 | 勘误：B32 行「demo_manual_check 绿（总章期望集）」措辞失实 | 总章非功能条目、B32 期望集实为空——机制经 I1 修复后落地（expected_entries.txt 随批追加）；history 行不回改（只追加原则），本行即为勘误真值 |
| 10-14 | B33 随批 a：M3 三洞加固完成 | 围栏剥离（族三）/FAQ 表格行（族五）/全命中章遍历（_find_chapters）；旧实现三洞伪过实证、新 3 用例检出；11 用例全绿随批提交 9243754 |
| 10-14 | B33 对抗处置（Critical 0/Important 3/Minor 1） | F1 编码器大有限 rssi 静默截断→语义域 [-1000,1000]dBm 双侧收口（C++ 域外钳 NA+缓冲断言=修复子代理；Python 域外 ValueError+边界用例=主会话；responsibility 措辞快速通道在块内登记）；F2 应急区围栏内伪表格行/F3 缩进围栏绕过→检查器围栏剥离补漏（修复子代理）；F4 回绕盲区（≥5000 万连续丢包才触发，真机不可达）=已知限界登记不修，README 口径与代码一致 |
| 10-14 | B33 门放行: X1 | 预授权连做生效——三轴过+对抗 Critical 0，F1–F3 修复随批（修复面并行落地），自动续 B34 |
