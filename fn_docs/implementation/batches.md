# batches.md —— 批次表（待办导航）
> fn-implement 独占更新。▶ = 下一批要完成的任务；未经批间门批准不得增删批次内容。

| 批次 | 函数/任务清单 | 验收点 | 注 |
|---|---|---|---|

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
| 10-14 | B34 三申报 | ①lib_deps ^1.4.10 registry 解析为 1.6.2（^ 语义，README 如实）；②ARC_CNT 按 datasheet 按包复位语义=发送完成逐包直读累计（任务书"差分累计"括号提示作废，README 声明）、PLOS_CNT 差分累计+RF_CH 重写清零（饱和钳窗已声明）；③测试文件名 test_nrf24_* 前缀（与 esp32 批 basename 冲突，仓库惯例全局唯一）；.gitignore .pio 锚点缺陷（firmware/** 不匹配 fn_work/firmware/）主会话顺手修为 **/.pio/（scaffold 失误随 F1-F3 修复提交 ea14f48） |
| 10-15 | 勘误：B34 行「d430d65 整批单提交」失实（评审 M1） | 实况=B34 全部实现被 fix(B33) ea14f48 的 git add -A 收编（并行子代理文件当时在树、提交消息零申报），d430d65 仅含进位文档——functions.md 五行哈希已更正为「ea14f48(实现随批)+d430d65(进位)」；history 行不回改（只追加原则），本行即为勘误真值；根因=并行批收尾时 add -A + commit 证据行只取 HEAD 弱证据（B31-B33 惯例未兜住）。流程加固：自 B35 起 commit 证据=git show --stat 白名单核对式；并行批在途时禁用 add -A |
| 10-15 | B34 对抗处置（Critical 0/Important 3/Minor 8） | I1 档案归属/I2 证据空转=评审 M1 同源已收口（adb55e6：哈希更正+勘误行+证据升级条款）；I3+M1 责任块三处措辞快速通道对齐（rpd 归一/ESB 无掉线态/饱和回绕口径）；M2 注释/M3 置位源/M4 死分支/M6 版本钉死 1.6.2+测试断言/M7 host64 位限界声明/M8 RPD settle 窗=修复子代理；M5 申报行"任务书差分累计"出处勘误=派发词括号提示（不入库文档），B34 申报行②以本行补锚 |
| 10-15 | B35 三轴处置（0C/2 Medium/2 Minor） | A-M1 进位 5 行随本行落库（时序=先 commit 后记账所致）；A-M2 进位证据回退弱证据形态=违背 10-15 加固条款，事实登记——自 B36 起进位证据一律 git show --stat 白名单核对式（本行即回退记录）；S-Min1 ch1 退出码 1 补"或运行中断"、S-Min2 ch5 列清单补 per_note、"六线"计数改七线=随批顺改（对抗回报后一并提交） |
| 10-15 | B35 对抗处置（Critical 0/Important 3/Minor 5） | F1 ch2 谱形差异句失实（sim 监测窗全在停发射后+固定种子底噪，对抗 6 轮 56321 行逐字节同证）→句改写（sim 看丢包曲线/识别节，谱形差=真机表现）；F2 kpi 列补 per_note（八列）；F3 检查器子串拼接伪覆盖→docstring 限界登记+全等匹配加固留 B42；F4 耗时口径改实测（demo 2–3s/样式轮 5–6s）；F5 六线→七线（含总章 0.3）；F6 ESP 帧补 [*<校验和>] 尾（ch5+0.3）；F7 期望集头注章形改正；F8 导语标注分批交付中 |
| 10-15 | B36 三轴处置（0C/1Medium/2Minor） | Medium-1 ch9 register 必抛 IndexConflictError（rebuild 先登记同 run_id）→补 update=True+拒绝行为转演示点；Minor-1 进位证据 grep BRE 竖线永不命中（事实属实、证据形态坏）→自 B37 起证据 grep 一律 -qE；Minor-2 README 功能 6"对齐误差统计入报告"与实现差距（手册如实未写）→登记留痕，R84 附录前修订 README 或补呈现面 |
| 10-15 | B36 对抗处置（Critical 1 已清/Important 2/Minor 5） | A1 register 冲突=三轴 Medium-1 同源已修（ebf9b96，对抗独立复现确认 HEAD 清零）；C1 四行 BRE 坏证据→tracker 勘误注记+随本行落库；C2 走查覆盖缺口（register 逃逸面=Critical 根因）留痕+条款：后续批走查证据避免 /tmp 脚本唯一载体（手册命令本身=持久证据）；A2 sed 靶改全数字/A3 ts 键措辞=已修；A4+C4 README:85「八节结构」失实句并入 README 修订清单（R84 附录前）；B2 合并章限界=B42 既定加固 |
| 10-15 | B37 门处置（三轴全过/0C/1I/4M） | I1 sim 录音 IQ 与样式无关（对抗 10+11 轮 md5 同证）→ch10 补限界如实句；M1 no_model 三键投影补全；M4 类别覆盖不足拒训分支预告；M2 证据时间敏感/M3 两态未留痕=登记（对抗已补复现） |
| 10-15 | B39 门处置（fix-then-pass：H1 已修/M1/L1/L2） | H1 ch14 声明键嵌套 declarations+违例逐字引文（各恰 1 违例实证）随 B42 提交；M1 急停可跑演示顺延至第 20 章（R83 范围）——本行即顺延 Ruling；L1 安全红线走查 token 错贴=注记勘误；L2 注释率 36.1% 已改 |
| 10-15 | B38 门处置（通过/0C/1M/2L/2Info） | A1 ch13 backend 句按实跑三处标注改写（CLI 摘要行无 backend 字段）；A2 EMC 节裕量"未判定"口径+limit_line_dbmv 差异如实；A3 引号改报告原句；A4 dict 通道 conduction/radiation 报告无 EMC 节（仅 sweep 形状适配 result['emc']）=登记已知限界，第 24 章网页三流程图谱段来自流程响应不受影响；Info 证据易失性=已立条款 |
| 10-15 | B40 门处置（fix-then-pass：H1/M1/L1） | H1 ch17 打印切片藏三可观测量→rounds=2+关键键选择打印；M1「六样式」→「六档功率阶梯（JSR 电平，样式固定噪声）」；L1 ch18 补第 9 章索引前置指引；I1 风格差异登记不追 |
| 10-15 | B41+B42 终门处置（不放行→修复→复验四件全绿） | H1 ch19 总览页如实化（骨架页+四预留区块现状+两处取数指引）；M1/L1 按钮名对齐真机（启动运行/编辑器区下拉+YAML 模式/运行审计（只读）/对比选中运行/回放此条）；L2 章号勘误；M2 检查器回退通道同权全等（无序号/无空格序号拼接章检出）+序号剥除兼容 N. 形态；M3 两档小节体切片跳标题行（删空检出）；L3 头注释对齐；fixture 标题对齐编号契约——复验：四变异全检出+真实手册 ok=True passed=26+全套件 3544 绿 |
| 10-15 | 裁决：六门合并双审作废重走（B37–B42） | 用户裁决"双审查不能合并，重走一遍"——文档批起单子代理合并三轴+对抗违背分离独立原则；既有合并报告的修复成果保留（真发现已处置），门结论作废重走：分离双审×6 门；tracker 注记在册 |
| 10-15 | B39 重走三轴 Info 处置 | ①README:102 注释率 35.9% 滞后（实测 36.1%）并入既有 README 修订清单；②进位证据形态宽（B36 C1 同类）注记供条款参考——重走对抗结论待其子代理回报 |
| 10-15 | B40 重走对抗处置（0C/2I/7M） | F5 ch18 拒跑归因改写（rebuild 无样式全跳段+文案偏差如实）+F6 四阶段取数配方（≥2 类样式×≥3 run_id register）；F1 ch16 选 failure 轮指引/F3 六档电平=常量真值（登记）/A2 ch24 补三演示区/A3 pymavlink 已预装措辞/F7 前置回指；B4 期望集单向盲区（期望→手册单向，反向无检测）=检查器设计限界登记；代码侧两文案（run_rff 全跳段提示/demo_rl"末轮"实为倒数第二轮）=树外改动登记待裁决，不随手册批 |
| 10-15 | B38 重走对抗处置（0C/2I/3M） | I1 ch13 命令注释残留旧句（与 A1 修复后预期矛盾）→三处标注口径对齐；I2 ch11 限值数字句不可兑现→限界披露（sweep 文件路线不消费 limit_line_dbmv；margin/passed 仅 dict 通道 result.json；dict 通道报告无 EMC 节；换算列 None）；M2 ch11/13 补 0.5 前置指引；M3 stderr 流标注；M1 期望集自声明盲区=B40 B4 同源已登记 |
| 10-15 | B42 重走对抗处置（0C/4I/5M） | I1 混合围栏走私→_strip_fenced 同型闭合（```/~~~ 各闭各型）；I2 HTML 注释档词走私→注释块剥离（与围栏同法）；I3 M3 锚回退盲→补 B7 形态锚（标题含档词+空体检出）；I4 docstring=飞行修复确认；M5 行 5 补「No module 'src'」变体/M7 第二部分标签辖 6–10 章/M6 共缩+M8 键承载=口径固有限界登记/M9 并发漂移随收口提交消解——加固锚后 check 套件 20 绿、全集 ok=True passed=26 |
| 10-15 | B41 重走对抗处置（0C/3I/4M） | I1 ch20 两处「开始」残句=三轴（重走）同源已修（随收口提交入账）；I2 原门证据（console_pages_e2e 结构级）不构成"预期现象一致"内容级证据=作废重走同源教训归档，本轮内容级比对（八章 10 个 UI 名逐一命中+全流程 API 实走）补上；I3 门证据时间敏感→条款：门行证据一律附 commit 锚；M1 ch21"点一行"→行内「查看报告」/M2 ch19 功能说明加骨架限定=已修；M3 matched 字段语义（索引侧命中数）=登记；M4 结构门不管页面元素名=登记+建议 UI 名比对脚本化（后续项） |
| 10-15 | 演进轮③批次计划（B44/B45）+批号协调 | 并行 R90 修订周期（手册 v2）并单批 B43（原子切换）并指示缺陷批自 B44 起；两周期文件面互不触碰（R90=手册+check_demo_manual+prepare_demo_assets；本批=run_demo/build_report/record_run_streams/run_power_ladder/新两模块+sim_delivery/report_builder 测试族；共享面仅 implementation 四文档，各节独立追加） |
| 10-15 | 基线 4 失败归因在案（对账子代理实证） | 全量 3552P+4F：①audit_responsibility_alignment 元测试 _FAST_TRACK_MIN=6 与 R90 未提交文档（第 7 处快速通道标记）阈值耦合→已由并行 R90 B43 认领（阈值动态化），本周期不触碰其文件面；②③④B210 真机不在位（探测缓存与运行时探测两路径不一致已知缝）→环境限界标注，实证归 R87，非回归 |
| 10-15 | B43 对抗处置（Critical 1/Important 6/Minor 5——全修复+复验） | C1 0.4 网页重建索引毒化 runs/ 致 ch7/8/11"取最新运行"必炸（顺序依赖假绿）→三处选取改目录过滤（ls -dt runs/*/ / glob 尾斜杠），毒化条件下 scoped 复验三处全 OK；I1 章节命令 12 处 sim→auto 对齐"默认全硬件"（ch13 平台能力/0.4 物料预跑/附录兜底保留 sim 口径）；I2 README 27/28 加固段加"随 B44 落地后生效"时态限定；I3 附录 B 节号 0.4→0.3；I4 requirements 三行 v1 漏改（环境表/术语/非功能）同步；I5 总章完整性弱契约 docstring 限界登记（DEMO_CHECKLIST 联动=后续加固项）；M1 节号/M2 重复句/M3 awk 取列/M4 ch22 括注/M5 cp 防嵌套=全修 |
| 10-15 | B43 门随批：R88 手册真值同步（并行会话终审移交 4 处） | ch2/ch6/ch10/ch20 四处 sim 底噪/样式无关旧口径按 R88 新真值改写（发射窗内=注入谱本体、谱形随样式可辨、识别语义可用 sim 录音攒样）；README 27/28 时态限定已被并行终审重写消解（核 grep 零残留）；sim_delivery 8 绿+八键 ok=True passed=26——用户裁决"本轮收口"（2026-10-15），随 B43 门闭 |
