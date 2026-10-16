# 验收报告：识别准确率协同改造+演示手册走查（演进轮④：R91–R93，周期 c6·演示手册走查环后重写版）
> fn-close 独占产出（2026-10-16）。核验输出原样粘贴，禁止转述、禁止"概括为通过"。
> 本报告不宣布"验收通过"——终审归用户。上周期报告（R94 周期 c5）归档于 acceptance-c5.md；归档链 c1–c5 在案。
> **版本说明**：本版为 c6 同周期第二次重写——第一次=走查环 C1 修复（efbdf9e）后六道重跑；第二次=用户指令对 docs/功能演示手册.md 走 fn-close 走查环，修复动过代码（B49：0e77e83/daaf089），六道再次全部重跑（本版；旧版作废、git 留痕）。

## 终检一览
| 终检 | 命令 | 结果 | 证据 |
|---|---|---|---|
| ① 桩+全量测试+镜像 | scripts/fn-check.sh | exit 0（残留桩 0；全量 3708 passed, 5 skipped；镜像 WARN=固有噪音） | §1/§2 |
| ② 接线与实跑 | — | functions.md 数据行 181 全 wired（非 wired=0）；B49 变更函数调用链+双口径顶层实跑在案；26 章顶层入口经走查环全实跑 | §3 |
| ③ 矩阵双向 | scripts/fn-doc-lint.py | 416 错/53 警全为在册假阳族（较前版 +36=B49 新增行同族；独立核对替代） | §4 |
| ④ 非功能对照 | — | 逐条过（17 条；本走查环新增载体标注） | §5 |
| ⑤ 报告完整性 | — | 无自封结论、末行固定句在 | — |
| ⑥ 目录清点 | — | .scratch 无主件=0；vendor 无件；杂散 4 件本周期已删（纯缓存口径）；requirements.txt 在位可复建 | §6 |
| ⑦ 外发终检 | — | 不适用（本周期无外发物） | — |

## 1 桩检查（fn-check ①段原文）
```
== ① 残留桩 ==
PASS 残留桩 0 处
```

## 2 全量测试（fn-check ②段原文，演示手册走查环修复后重跑）
```
=========== 3708 passed, 5 skipped, 2 warnings in 229.93s (0:03:49) ============
PASS 全量测试
```
（3708=前版 3707+B49 新增 1 用例；5 skipped=B210 真机门控 3+参数化 2——本日 `uhd_find_devices` 未枚举设备；2 warnings=fastapi 既有弃用告警。）

## 3 接线与实跑
**全库静态（原文）**：
```
$ grep "^| " fn_docs/implementation/functions.md | wc -l
182
$ grep "^| " fn_docs/implementation/functions.md | grep -v "| wired"
| 函数 | 批次 | 状态(日期) | 核验命令+摘要 | commit |
```
（182 行=表头 1+数据 181，非 wired 数据行=0。）

**本周期变更函数 prepare_demo_assets（B49）**：
- 调用链：`prepare_demo_assets.py:108` 实调 `prewarm_demo_runs`（L21 `PREWARM_SCENARIOS`、L13 import 在案）；顶层入口=手册总章 0.4 演示者命令（entry 类）；
- 顶层实跑双口径（复走查独立实证）：仓内交付形态 `written=[]/conflicts=7/prewarm_runs 9 轮（退出码 [0,0,0,0,0,0,1,1,1]）/七场景字节不变/报告无 refused_conflicts 键`；/tmp 全新目录形态 `written=7/conflicts=[]/prewarm 照跑`。

**走查环（演示手册）顶层入口实跑**：26 章命令/页面/API 三轮全实跑留证——run_demo（六样式/失效/距离/录音/EMC/replay）、verify_report_traceability（2049/2048/1+篡改 888.888 当场点名）、index_dataset（rebuild 108 条全带 style、query 命中、register 拒登）、train_classifier（query={} n_samples=47、单样式"类别覆盖不足拒训"）、predict_style（六样式 6/6、no_model 降级原句）、guard_compliance（双违例逐字、文件路线 exit 2）、update_ledger（副本 L30）/audit_ledger（100/100、注释率 36.7%）、demo_sitl_bridge（台阶映射/单档 n_steps=1）、demo_rl_policy（rounds=1/2 两分支）、demo_rff_pipeline（纯 rebuild 4/4、macro_f1 0.9732）、open_sim_siggen/open_sim_attenuator（读数对象串）、serve_console（七页 HTTP 200+run/stop/replay/compare/dataset/ai/instruments/emc×3/calibration/ledger 全 API）——逐字输出在三轮走查报告（对话留痕）。

## 4 矩阵双向+lint 分诊
```
== 416 错误, 53 警告 ==
```
（前版 380，+36=B49 新增四文档行；族分布：死代码误报 176[entry 类/共享函数不入概览树]、矩阵引用不存在需求 93[R 系演进格式解析脱节]、矩阵顶层不在函数树 18[文档交付物行]、批次表引用未知函数 10、状态词带括注 9、tracker 豁免行模板示例文字 2、其余调用方括注切分族——c2/c6 两轮证伪同族。）
**独立核对替代**：B49 行真值核对——functions.md:190 B49 行+commit 0e77e83 在库（git cat-file 验）、batches.md:115 立批行在盘、tracker.md:1768-1790 进入五步 5 行+函数五行+批间门三行全勾（fn-step-done 核验绿读回）、调用链 prepare_demo_assets.py:108 实在；本周期无新增 R 条目（B49=R76 域内缺陷修复，需求矩阵无变动）；既有矩阵沿 c6 独立核对结论（divide 三自检+门双审档案轴+fn-check ①0 桩）。

## 5 非功能约束逐条（17 条；★=本走查环新增实跑载体）
| 约束 | 判据 | 验证 |
|---|---|---|
| 合规红线 | 超功率/超频段拒绝+四项口径声明 | ★走查 14 章双违例逐字命中（超功率/非白名单两串与手册逐字符一致）+场景文件路线 exit 2；R52 用例在 3708 内 |
| 实时性 | KPI 端到端 <500ms | 用例在 3708 内（sim 实测记录入 run JSON） |
| 样式切换 | <2s | R10 计时用例在 3708 内；★走查 2 章六样式连跑（切换=改一个字段，毫秒级） |
| 可扩展性 | 三插槽即插即换 | 用例在 3708 内；★走查 12/13 章 sim 仪表/三后端实测 |
| 安全 | 异常路径先停发射 | R2/R18/R22 用例在 3708 内；★走查 20 章 /api/stop 返回 steps 首位 stop_tx |
| 可溯源性 | 报告数字回查原始数据 | ★走查 8 章：2049 数字 2048 有出处+篡改值当场点名（行号+上下文） |
| 平台 | Linux；无外网除远程训练全可用 | 套件在 3708 内；★走查全程本地 |
| 数字纪律 | 只引实测、禁预写、【待实测】保留 | ★走查 26 章【待实测】标注/11 章 CISPR 模拟声明原句/10 章拒训原句三证 |
| 离线可用 | 七页断网可用 | console_offline 用例在 3708 内；★走查 19-26 章本地服务全页实测 |
| 管线顺手改登记 | 变更须入变更记录 | ★B49 即登记载体（batches.md 变更记录+tracker+functions 增量行） |
| 演示零出错 | 手册命令/页面承诺兑现 | ★本走查环=26 章全实跑+9 处失真修复+3 轮复核清零；真机侧随 R87 |
| 手册单文件契约 v2 | 章级三件套+防回潮+总章完整性 | ★tests/check_demo_manual/ 24 passed（走查环收尾复跑） |
| 采集提前不扰发射 | 阶梯节奏/判据窗语义不变 | R88 用例在 3708 内 |
| 录音可复现 | 同场景同种子同录音块序列 | R88 用例在 3708 内 |
| 防失控上限 | max_monitor_blocks/max_kpi_rows 不放大 | R88 用例在 3708 内 |
| 识别确定性 | 同 IQ+同模型同标签置信度 | R91–R93 用例在 3708 内；★走查 10 章模板路复算同 dict |
| 置信度如实披露 | 未校准标注附、禁预写 | ★走查 10 章 confidence_note 原句随每次识别返回；6/6 与近邻错判（sweep→partial_band 0.9455）两头如实 |

## 6 目录清点
- `.scratch/`：不存在（无主暂存 0）；`fn_docs/vendor/`：不存在（vue vendor 走 /assets/vendor 托管、provenance 在 requirements.md 外部依赖节登记）；
- 外部数据源登记：requirements.md 外部依赖节完备（scipy/vue.global.prod.js/markdown/playwright+chromium/platformio 均登记）；参考资料节 5 件与 docs/ 实存文件对账一致；
- 环境可复建：fn_work/requirements.txt 在库+fn_work/.venv 在位（fastapi/sigmf import 自检过）；
- 前版披露的仓库根 4 个 ImageMagick 残留（os/re/subprocess/sys，各 ~13.6MB）——本周期验明纯缓存（PostScript 头、Creator: ImageMagick、时间戳 2026-10-16T02:28Z）已按第⑥道"确认无价值的纯缓存可删"处置删除；
- 现存未跟踪仅 `fn_work/dataset/`（运行期数据集索引，运行产物非无主暂存——如实登记；与 runs/ 同性质，未擅改 .gitignore）。

## 未完成项
无（R91–R93 十一函数+B49 全 wired；R87 真机实证为在册延后项——本日设备未枚举，真机侧走查以手册附录 B 应急口径替代并记限界）。

## 用户走查环记录（本周期第二环：docs/功能演示手册.md——用户指令"按 fn-close 走一遍"）
- **首轮走查**（对抗子代理，26 章+总章+附录全覆盖、零未走章、156 次工具调用逐字实跑）：**Critical 0 / Important 6 / Minor 3**。F1=交付仓形态 0.4 预跑恒空（scenarios 已入 git+runs 被忽略→冲突早退守卫拦死预跑，实现类）；F2=sim 监测谱频轴不随场景 freq_hz（2450/2412 两轮谱逐位相同，需披露）；F3/F4/F5=rebuild 自 f44b6e9 起自动带样式后，手册"须显式 register"三族口径反转（9/18/10 章：含"rebuild 不带样式""多攒不解锁""query 给样式条件"三处反向指引）；F6=EMC dict 通道 R89 后报告有节、传导裕量在正文（旧口径三子句失真）；F7=轮时长 3s/5–6s→实测 7.1–7.3s；F8="恒判 pulse"旧限界句未随 R91–R93 反转；F9=SITL"无台阶如实提示"实为如实计数。次级发现：口径注记层系统性漂移（f44b6e9/R89 根治后手册未回写）是失真主源，命令层 26 章无一例跑不起来。
- **修复**：F1 显式派 /fn-implement 子代理走满流程（B49：0e77e83 预跑与种子冲突解耦+refused_conflicts 键删除+交付形态新用例[conflicts=7+prewarm 非空+七场景 sha256 不变]；daaf089 四文档收口；定向 21 绿+全量 3708 绿；对抗探针：corrupt 场景→prewarm_error 诚实中止不静默混跑）；F2–F9 手册直改 12 处（0.4/2/6/9/10/11/16/18/22 章+附录 B）+契约检查器 FAQ 锚随真值同步（tests/check_demo_manual/ 24 passed）。
- **复走查**（scoped 独立子代理，97 次工具调用）：9 修复面全过——F1 双形字节级实证、F6 六假设全否证（传导正文三列+result.json 同记+无限值线"未判定"原句、辐射/扫频/文件路线均无裕量数字）、F8 现场 6/6（47 样本、conf 0.9994–1.0000）+近邻错判实测兑现限界句；**总核新抓 1 Important**：第 22 章预期现象行旧口径残留（同章两行互斥，修复面只改了步骤行漏了预期行）+2 Minor（18 章跳段归因"没有 recordings 目录"→实为"目录存在但空"；10 章命令②成功分支静默无输出）。
- **三处修补+第 3 轮最小复核**（独立子代理）：三处全过零发现——22 章三处口径一致+rebuild 108 条全带 style 对回场景副本逐条一致；18 章 61 跳段全部=空目录（create_run_workspace.py:183 无条件建目录代码背书+_resolve_data_file 空目录计跳段）；10 章 print 版 stdout 可见 dict、exit 0。
- 走查环结论：**Critical/Important 清零**（Minor 全修）。留档观察项：`fn_work/dataset/` 未跟踪（与 runs/ 同性质运行产物）；fn_docs/README.md FAQ"查询匹配 0 条"条目仍真但窄（查询样式零录音时可达，演示手册附录 B 已扩为双症状行）。

## 本周期变更摘要（供终审索引）
- R91 门控感知两级分类：_classify_dummy 改造+三叶提出（连续分流 duty_on≥0.9/段内分类=最长单段≥3×nfft/两层门控兜底/features 扩键）——sim 六样式识别器级硬判全对，「sim 恒 pulse@0.76」缺陷已修；
- R92 推理消费训练产出：_predict_one 模板/规则分流+_template_classify+shared spectral_template_match（softmax over negative distances·RMS 归一·未校准）+_load_model 顶层模板规整——真链用例（rebuild→local 训练→模型文件→识别 6/6）；
- R93 评测口径对齐：make_predict_style_callbacks+grouped_cv_evaluate eval_protocol 白名单+view_cv_evaluation 默认注入+query 透传——六样式对齐口径用例全对角 macro_f1==1.0；
- 走查环 C1 修复（efbdf9e）：训练/评测特征门控 scope 与部署统一（_scoped_profile）——平台录音整块口径六样式 6/6；置信度饱和已治（近距 0.70）；
- **演示手册走查环（本版增量）**：B49 prepare_demo_assets 预跑与种子冲突解耦（0e77e83/daaf089）+手册 12 处口径回真（0.4 双形/2·6 sim 频轴注记/9·22 rebuild 自动样式/10 训练配方 query={}与识别口径反转/11 限值数字限界/16 单档措辞/18 免 register 配方/附录 B 双症状行）+3 轮复核清零；六道全部重跑（3708 绿）。

以上为终检事实，验收与否由用户判定。
