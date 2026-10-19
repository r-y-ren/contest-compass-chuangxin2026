# JOURNAL —— 过程流水（fn-commit 追加；任何执行者可写，与结构化文档互补）

| 日期时间 | 阶段 | 摘要 | 核验 |
|---|---|---|---|
| 2026-10-14 23:32 | 全量线:implement | X1 豁免记账——预授权连做（剩余全部，B34–B42 批间门不停人；评审+对抗照跑、Critical 清零自动续、证据纪律不豁免） | 用户字面授权在案；tracker X1 行已读回 |
| 2026-10-15 01:28 | 全量线:implement | 周期②收口——B32–B42 全批完成（14 函数 wired+26 章手册+附录+固件双工程），X1 额度用尽 consumed | 全套件 3544+5skip 绿；全集硬门 ok=True passed=26 零遗漏零占位；批表清空 |
| 2026-10-15 10:06 | 全量线:implement | 双审重走收口——用户裁决合并双审作废，六门分离重走全闭（0C 残留），重走修复全入库 | check 套件 20 绿+demo_manual_check 1 绿+全集 ok=True passed=26+全套件 3551+5skip |
| 2026-10-15 19:14 | 全量线:implement | R90 修订周期收口——B43 手册 v2 原子切换+双审全处置+R88 移交同步 | 八键 ok=True passed=26；契约 24+物料 19+audit 6+sim_delivery 8 绿；全套件 3603 时点/并行终态 3631 |
| 2026-10-15 20:42 | 全量线:close | R90 终检收口——c4 报告+走查环清零+user-guide R90 增量 | 六道全过（桩0/3631 绿/独立双向/231 约束族/完整性/目录）；上周期归档 c3 |

## 演示手册走查环（2026-10-16，c6 第二环——用户指令"按 fn-close 走一遍 docs/功能演示手册.md"）
- 首轮走查（对抗子代理，26 章+总章+附录零未走、156 工具调用）：C0/I6/M3。失真主源=口径注记层系统性漂移（f44b6e9/R89 根治后手册未回写），命令层 26 章无一例跑不起来、全量 3707 绿非假绿（skip 全硬件门控）。
- F1 实现类（交付仓形态 0.4 预跑恒空）→显式派 /fn-implement 子代理：B49（0e77e83 预跑与种子冲突解耦+refused_conflicts 删除+交付形态字节级用例；daaf089 四文档收口；定向 21 绿+全量 3708）；F2–F9 手册直改 12 处+契约检查器 FAQ 锚随真值同步（24/24）。
- 复走查（独立子代理）9 修复面全过，总核新抓 1I（22 章预期行旧口径残留）+2M（18 章空目录归因/10 章静默成功）；修补后第 3 轮最小复核零发现——C/I 清零。
- 六道全部重跑（fn-check 桩 0/3708 绿/lint 416 假阳族+独立核对/17 约束逐条/目录清点含杂散 4 件 IM 纯缓存已删）；acceptance.md c6 同周期第二次重写在案。
- 流程坑增量：**口径注记层是走查新靶面**（命令全对≠手册真——代码根治后必须回写手册口径句，本轮 6 条 Important 全属此族）；fn-check 输出禁止接 tail 管道（截断桩段/测试计数，须整落文件）；契约检查器 FAQ 锚与手册行文案联动（改附录 B 症状行须保 12 字符归一键）。

## B210 监测端口映射勘误（2026-10-17，用户真机发现→文档面修复）
- 现象：用户按手册接好两天线（TRX1/RX2）+GPS 真机运行，RX1 灯亮。定位：监测链实际绑 UHD **信道 0**——tx/rx 流句柄 StreamArgs 未传 channels（open_b210_backend.py:181/:218）、set_rx_* 未传信道号（configure_b210_channels.py:150）均缺省 chan 0；UHD 天线名 'RX2' 是**按信道相对命名**（活体探测两信道各列 'TX/RX'/'RX2'），信道 0 的 'RX2' 物理对应**丝印 RX1 口**——即现行代码监测物理口=RX1，手册"监测接 RX2"与实际错位（R94 当时"端口=按代码缺省"的核对混淆了逻辑名与丝印口）。
- 用户裁决：监测天线改接丝印 RX1、代码零改动。文档面同步：手册 6 处（设备边界表/0.1 两行/0.2 总图+接线表+桥接注重写含 LED 预期注记）、user-guide 已知限制 8、README 演示段、requirements R94 行勘误注+变更记录新行、responsibility R94 块勘误注；契约检查器 24/24 复绿。
- 遗留：真机监测谱实证（天线在 RX1 上实际监测到注入谱）随 R87；若日后要改回丝印 RX2 口为监测口=代码改动（channels=[1]+set_rx_*(…,1)），须立 R 条目走 fn-implement。

## 真机 TX 发射无效诊断（2026-10-17，带练中用户发现→诊断报告在案，修复移交并行对话）
- 现象：真机轮（runs/20261017-124103，B210Backend）TX1 灯不亮；monitor 102 万行零本方信号（>-40dB 热行=环境 WiFi 宽带突发、逐 bin 最长连续串=1、无阶梯结构）；每档事件 applied=unknown_gain。
- 根因链：①open_b210_backend.py:50 缺省 TX 增益 0dB；②run_demo.py:328 _backend_params 只透传 freq_hz（场景无增益旋钮）；③set_channel_attenuation.py:99 B210 无 set_attenuation→回退 set_tx_gain(**负值**)被夹 0、粗档 30dB in/out 无执行器纯账面；④B210Backend 无 get_tx_gain（unknown_gain 分支必走）；⑤增益标定表【待实测】→ power_dbm 从未映射到增益。净效果：真机阶梯=常数 0dB 耳语（-110dBm@天线，低于底噪 50–70dB）。
- 三相对照实验（平台路径 start_tx/read_samples，2450.2MHz 音调）：A 基线期望 bin=底噪；B 缺省 0dB 发射期望 bin 仍=底噪（复现缺陷）；C set_tx_gain(60) 期望 bin +37.3dB 干净出峰——电台与发射链完好，缺陷唯一在映射层。
- 产物：fn_docs/诊断-TX发射无效-20261017.md（根因锚点/实验数据/影响面/修复方向面六节）；带练暂停于步骤 4 后（sim 口径不受影响）。修复由用户并行对话承接（立 R 条目走 fn-ladder）。
| 2026-10-19 19:19 | 轻量线 | 手册两缺陷修复：第10章③训练命令补 index_path/runs_root 取数两参（与②同源，照抄不再拒训）+第6章三路时间戳宣称补 B210 真机限界句（monitor 首列交窗索引非毫秒、仅 kpi/events 毫秒量纲、随 R87）；.gitignore 补 fn_work/dataset|models 运行时产物 | 修后③形态 dry_run n_samples=53/6labels 非拒训、旧形态 TrainError'查询匹配 0 条'逐字复现；对抗审查 2I（record 全 0/键名 ts）批内修复+scoped 复审 16-run 全量普查通过 |
| 2026-10-19 19:25 | 全量线:grill | R87 扩容+2（走查两 Minor 转入，用户裁决）：①train_classifier 零匹配测试补强（弱断言钉原文+缺省路径仓库根语义用例）②responsibility.md 取数措辞对齐；R87 行+变更记录 2026-10-19 行 | 读回证据：requirements.md L552（R87 扩容随批累计句）+L730（变更记录行）grep 命中；出处=2792feb 对抗审查 Minor 两则 |
| 2026-10-19 19:27 | 全量线:grill | 诊断报告删除的指针处置（用户告知修复完成后自行删除）：requirements 参考资料行标历史参考·已删除+取回路径（2792feb）、acceptance c7 核验结论加日期勘误注；JOURNAL 流水保持原样 | 读回证据：requirements.md L89（历史参考·已删除）/acceptance.md L60（勘误注 2026-10-19）grep 命中；git status 仅两文档 M 零夹带 |
| 2026-10-19 19:49 | 全量线:grill | R87 启动轮立项——新增 R98（真机监测并发采集+时间戳归一 P0）/R99（power_step 键集钉住）/R100（自漏标定入口与实测）/R101（标定口径如实化）/R102（训练取数测试补强）；R87 改进行中（26 章走查自动执行、带练暂停）；非功能+3/依赖零新增/范围外调整/对账 102 条/变更记录；README 增量（进行时态） | 读回证据：requirements.md L551（R87 进行中）/L628（域二十五）/L632-666（R98–R102）/L689（并发安全）/L742（102 条）/L777（变更记录）grep 命中；README.md L176（R87 段）命中；git status 仅两文档 M |
| 2026-10-19 19:53 | 全量线:grill | R87 口径回撤（用户裁决 B：本批只走查不改码）——R87 改只走查+缺陷清单，R98–R102 全部标延后未启动，非功能/依赖/范围外注明随 R98；README 改走查口径 | 读回：requirements.md L551（只走查不改码）/L632（R98 延后）/L777 后新行（回撤记录）/README L176（走查口径）grep 命中 |
| 2026-10-19 20:50 | 全量线:close | R87 真机复查轮验收（c8）：六道终检执行+26 章走查；按用户裁决 B 只登记不修——用户走查环 2C/7I + 手册 1–18 章新增 2C/3I 全列未过项；c7 归档 acceptance-c7.md；不宣布完成 | 证据：fn-check 3782 passed/桩 0；代码 c7 起零 diff；doc-lint 433/57=c7 基线；定向 75/34/121/42；缺陷清单 4C/10I/13M 带原文锚点；git status 仅验收文档 |
| 2026-10-19 21:07 | 全量线:grill | R87 走查缺陷修复轮立项——R98–R102 解冻+新增 R103–R115（18 条：P0 5/P1 13）；非功能+4（行为级正负用例/固定衰减 0–50/模型目录锚定/溯源可证伪）；依赖授权可新增、方案零新增；范围外调整；对账 115 条；README 转修复态；六轮裁决入变更记录 | 读回：requirements L551 R87 走查完成/L668–752 R103–R115/L837 115 条/L874 新变更行；README L176 修复段；git status 仅两文档 |
| 2026-10-19 21:09 | 全量线:divide | R87 修复轮责任划分——矩阵+R98–R115 十八行；新增/改造函数块 17+shared 承载 R107；4 个共享函数（normalize_monitor_block 改造/recompute_failure_aggregates/build_recording_facts/resolve_models_dir）；自检：矩阵 18/18、字段全齐、新名零重复、调用链全闭合 | 读回：responsibility.md 矩阵行 18、功能块 17、R107 共享承载、共享函数 4；自检脚本输出 matrix_missing=[] / blocks_missing_fields=[] / dups_in_new=[] |
| 2026-10-19 21:10 | 全量线:scaffold | R87 修复轮落桩——6 新顶层模块+3 shared 新模块+5 处既有文件追加私有桩，共 23 个 unimplemented:fn 桩；既有函数体零改动（numstat 全为新增行）；编译/导入/收集验证过 | 证据：py_compile COMPILE_OK；IMPORT_OK 14；pytest 新占位 9 skipped；grep unimplemented:fn =23；git diff --numstat 五处既有文件 15/7/15/7/7 增、0 删 |
