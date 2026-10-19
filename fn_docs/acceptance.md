# 验收报告：无人机链路抗干扰测试平台（R87 真机复查轮 · c8）

> fn-close 独占产出。核验输出原样粘贴，禁止转述、禁止"概括为通过"。
> 本报告不宣布"验收通过"——终审归用户。

**本轮口径（用户裁决 2026-10-19）**：R87 只走查不改码。代码自 c7（6c46c3d）以来零 diff；R98–R102 五项修复方案已定稿但**全部延后未启动**。用户走查环单轮即返回 2 Critical/7 Important；按用户裁决"只登记不修"记录在案，**不以清零状态出门**。

## 终检一览

| 终检 | 命令 | 结果 | 证据 |
|---|---|---|---|
| ① 桩+全量测试+镜像 | scripts/fn-check.sh | 桩 0、3782 passed、镜像警告级、汇总"全部通过" | §1 |
| ② 接线与实跑 | git diff + 入口实跑 | 代码自 c7 零 diff；`--demo` 实跑有可观察输出 | §2 |
| ③ 矩阵双向 | scripts/fn-doc-lint.py | 433 错/57 警——与 c7 在册假阳基线逐字一致；人工复核见下 | §3 |
| ④ 非功能对照 | 定向 pytest | 75/34/121/42 全绿（与 c7 同读数） | §4 |
| ⑤ 报告完整性 | 本报告自查 | 无自封结论；末行固定句在；未过项如实列于 §7 | — |
| ⑥ 目录清点 | ls/test/git ls-files | scratch 无、vendor 无（不适用）、参考资料在位（含已删件历史标注）、venv 在位、依赖清单入库 | §5 |
| ⑦ 外发终检 | — | 非交付型本轮不适用 | — |

## 1 桩检查与全量测试（原样输出）

```
== ① 残留桩 ==
PASS 残留桩 0 处
================= 3782 passed, 2 warnings in 224.77s (0:03:44) =================
== ③ tests 镜像结构（警告级） ==
...（WARN 341 条，均为"源文件无同名测试"镜像提示，c6/c7 在册假阳族）
== 汇总 ==
全部通过
```

桩标记独立复核：`grep -rn 'STUB_MARKER' fn_work/src --include='*.py' | wc -l` → `0`；tracker 未勾行 `grep -c '^- \[ \]'` → `0`。

## 2 接线与实跑

**代码零 diff 证明**（门 2 的核心，本轮无新函数/无改造）：

```
$ git diff --stat 6c46c3d..HEAD -- fn_work/src fn_work/tests
（无输出，rc=0）
$ git log --oneline 6c46c3d..HEAD | head -5
a95a64e fn(全量线:grill): R87 口径回撤...
d99ed57 fn(全量线:grill): R87 启动轮立项...
df6713c fn(全量线:grill): 诊断报告删除的指针处置...
7570ce6 fn(全量线:grill): R87 扩容+2...
2792feb fn(轻量线): 手册两缺陷修复...
```

**顶层入口实跑**（本会话，原文）：

```
run_demo: run_dir=.../runs/20261019-195437 status=failed failure_levels=1 report=... traceability=passed ledger=skipped(no_entry)
EXIT=1
```

接线沿用 c7 事实（116 函数全 wired，c7 §3 在案）；本轮零代码改动，无新增接线面。**未过项**：无（本条只证明"未改动"）。

## 3 需求→函数对照（矩阵双向）

**机械轴原文尾行**：`== 433 错误, 57 警告 ==`。与 c7 在册读数逐字一致（c7：433/57；c6 基线 416/53）。错误族分诊（脚本原文分类计数）：

| 族 | 条数 | 定性 |
|---|---|---|
| 函数无调用链连到入口（死代码） | 179 | 在册假阳（c2/c6 两轮证伪：解析器不识别入口装配/鸭子调用） |
| 矩阵引用不存在的需求 | 96 | 在册假阳（演进格式/括注解析） |
| 矩阵顶层函数不在函数树 | 21 | 在册假阳（改造承载括注） |
| functions 状态词非法 | 14 | 在册假阳（"wired 10-17（改造点…）"人工注记） |
| 批次表引用未知函数 | 11 | 在册假阳（Ruling/处置行被当函数名） |
| "<函数> 的调用方不存在" | 约 95 | 在册假阳（调用方字段括注/共享函数不入概览树） |
| tracker 豁免模板行/格式 | 5 | 在册假阳（模板占位行） |
| `_dispatch_backend` tracker wired 行缺失 ×2 | 2 | 记账格式（改造函数用"语义applied/tested/commit"行，R91/R92 同款先例） |

**人工复核**：
- **漏实现拦截**：R1–R97 均有函数承载且 wired（c7 在案，本轮代码零 diff）；**R98–R102 无函数承载属用户裁决延后**（不作为漏实现）。
- **死代码拦截**：本轮无新增函数；c7 在案 116 函数全 wired。
- **静默漂移拦截**：桩 0、全量套件绿；functions.md 与代码一致（无新增行）。
- **tracker 核对**：未勾行 0；批次表无待办行；与 functions.md/git log 三方一致（c7 事实承继）。

## 4 非功能约束逐条（定向实跑原文）

```
== guard ==      75 passed in 0.04s
== stop ==       34 passed, 1 warning in 1.86s
== offline ==    121 passed, 1 warning in 2.39s
== sim ==        42 passed in 0.04s
```

与 c7 同读数（75/34/121/42），本轮代码零 diff。其余非功能（实时性/样式切换/可扩展性/采集不扰发射/防失控/识别确定性）用例在 3782 内，c6 实跑记录承继；本轮未新增测量。**未过项**：无（本道只证明未回退）。

## 5 目录清点

```
== scratch ==   .scratch 不存在
== vendor ==    fn_docs/vendor 不存在（本轮无外来件，不适用）
== refs ==      docs/设备清单.txt OK；全功能实现清单 OK；平台说明 OK；USRP_B210说明.pdf OK
                诊断-TX发射无效-20261017.md：用户修复后自行删除，requirements 已标"历史参考·已删除"+取回路径
== env ==       fn_work/.venv/bin/python 在位；fn_work/requirements.txt 已入库
== calibrations == fn_work/calibrations 不存在（标定三表【待实测】占位，R100 延后）
```

## 6 R87 真机走查记录

### 6.1 总章 0.1–0.4

| 项 | 实测 | 判定 |
|---|---|---|
| 0.3 环境自检 | `import fastapi, sigmf` 无输出；`/dev/ttyUSB0/1` 在；B210 serial 31B92DD | 通过 |
| 0.4 一键物料 | `conflicts=7`（七场景已在）、`prewarm_runs` 混合 exit 0/1、`env.uhd_probe=在位`、PlatformIO 6.2.0 | 通过 |

### 6.2 演示手册第 1–18 章（CLI，真机串行）

| 章 | exit | 关键读数 | 判定 | 发现 |
|---|---|---|---|---|
| 1 | 1 / 0 | ①`status=failed failure_levels=1 traceability=passed`；②`completed`、`backend=B210Backend`、八件套齐 | 通过 | — |
| 2 | 0×6 / 2 | 六样式均 completed；B210 每轮 77–78 s（sim 2–6 s）；超带宽 exit 2 指名 `bandwidth_hz` | 部分 | I8 |
| 3 | 1 | `failure_levels=1`；报告失效电平 `-15.0 dB`；events 阶梯 `-25/-20/-15`、step2 触发 `per=0.1>=0.1` | 通过 | — |
| 4 | 0 / 0 | 1/3/7 米事件在；100 米 skip 正确；**7 米 `n_samples=0` 静默** | 部分 | I7 |
| 5 | 0/1 | kpi 八列逐字；失效轮 per 悬崖 `0→0.1→0.5→0.9→1.0`；NRF 清缓冲后 6 帧/3 s、seq 101→226 | 部分 | I9、M8 |
| 6 | 0 | 三路齐；kpi 首值 16872557.46 ms、events ts 16853081；monitor 首列 `0/1/2/3`（0=802816，78.4%）与手册真机限界句一致 | 通过 | — |
| 7 | 1 | 报告七节标题逐字、plots 三图齐 | 通过 | — |
| 8 | 1 / 0 | 原句 `sorted(glob.glob('runs/*/'))[-1]` 选中 `runs/models/` → `ValueError`；修正目录后 `2049/2048/1 passed=True`；频点篡改检出；**中位数 -15.0→-99.0 仍 passed=True** | 部分 | C3、C4 |
| 9 | 0 | SigMF 对在；rebuild `196/2`；query/register 通；**meta `core:sample_rate=1.0`、`annotations=[]`、`jam:backend=sim` 与 B210 实况不符** | 部分 | I1、M10 |
| 10 | 0 | dry_run `n_samples=57`、`skipped=139`；无模型态精确；有模型把 sweep 判 partial_band@0.9726（手册已承认近邻误判） | 部分 | M3 |
| 11 | 0 | EMC 步进扫频节 + `simulated` 声明 | 通过 | — |
| 12 | 0 | `SimSiggen1433D output=False`；`SimAttenuator attenuation_db=30.0 switches=0` | 通过 | — |
| 13 | 0 / 0 | 报告/result 两处后端标注；replay completed（ReplayBackend）；stderr 决策行未观察到 | 部分 | M12 |
| 14 | 0 / 2 | 两条 `rejected` 原文逐字；场景超功率 exit 2 | 通过 | — |
| 15 | 0 | `updated=True line_no=30`；`done/total=100/100`；注释率 0.368988 | 通过 | — |
| 16 | 0 | `ok=True read_only=True n_steps=3` | 通过 | — |
| 17 | 0 | rounds=1 fallback；rounds=2 动作序列非空但仍 fallback、converged=False | 通过（限界） | M9 |
| 18 | 0 | 数据够 4/4、Macro-F1 0.9741；空索引诚实拒跑（文案走 0 匹配分支） | 通过 | M11 |

### 6.3 演示手册第 19–26 章（网页，复用用户走查环页面实测 + 逐章对照）

| 章 | 实测要点 | 判定 | 发现 |
|---|---|---|---|
| 19 总览 | 四块空占位；演示手册已如实写"骨架页" | 通过（对演示手册） | C2（对 user-guide/README） |
| 20 运行 | 启动真跑、WS 三帧、急停 `stop_tx` 先行通过；编辑器覆盖、新建不刷新、衰减滑杆死控件 | 部分 | C1、I4、I5 |
| 21 报告 | 列表/详情/三图/下载/EMC/对比可用；溯源徽标假绿、报告模型路径错 | 部分 | C4、I3 |
| 22 数据 | 索引/过滤/回放/红线通；178 卡中 120 不可回放、125 个空录音目录被列出 | 部分 | I2 |
| 23 AI | 训练/评测/识别端点通；训练产物与评测/报告默认路径不一致 | 部分 | I3 |
| 24 仪表 | 五台 open/read/close 200；EMC 三流程 done；标定演示 `wrote_real_table=false` | 通过 | — |
| 25 台账 | 100/100、clean=true、注释率 0.3689；只读 | 通过 | — |
| 26 标定 | 三表【待实测】如实；演示仅覆盖 gain 三分支，手册"三件演示"失实 | 部分 | I10 |

## 7 缺陷清单（用户裁决：只登记不修）

### Critical（4）

| ID | 缺陷 | 证据锚点 | 出处 |
|---|---|---|---|
| C1 | 场景编辑器选中目标后不加载原 YAML，表单保存静默覆盖多频段场景并丢字段 | `edit_scenario_ui.py:153`（无 change 监听）、`:356-359`（守卫读空 textarea）；实跑覆盖后只剩单频段 | 用户走查环 / 手册 ch20 |
| C2 | 总览页仅四个空 `block-mount`，user-guide/README 宣称"七页全能力" | `curl /pages/overview` 原文；`docs/功能演示手册.md:545` 自认骨架 | 用户走查环 |
| C3 | 手册第 8 章溯源命令 `sorted(glob.glob('runs/*/'))[-1]` 选中 `runs/models/`，照抄即报 `ValueError` | 实跑原文 `ValueError: 报告文件不存在: 'runs/models//report.md'` | 手册 1–18 章走查 |
| C4 | 核心失效电平中位数被篡改（-15.0→-99.0 dB）仍 `passed=True`、0 差异——溯源徽标假绿 | 本会话复核：`TRACE_PASSED=True MISMATCHES=0 CONTEXTUAL=1` | 两轮走查共同发现 |

### Important（10）

| ID | 缺陷 | 证据锚点 |
|---|---|---|
| I1 | SigMF 录音无真值标注：`core:sample_rate=1.0`、`annotations=[]`、`jam:backend=sim`（实际 B210） | 实测 `runs/20261019-200420/*.sigmf-meta` |
| I2 | 数据页把 125 个空 `recordings/` 目录列为录音卡片（178 卡中 120 不可回放） | `/api/dataset` total 178/replayable 58/disabled 120 |
| I3 | 训练写 `runs/models/`、评测默认 `models/`、报告查 `run_dir/models/`——三方不一致，报告仍显示"未识别（无模型）" | `build_report.py:16`；实跑 evaluate `model_exists=False` |
| I4 | 编辑器新建场景后运行页卡片不刷新，必须重启操控台 | 实跑编辑器卡片有、运行页卡片无 |
| I5 | 运行页"链路衰减"滑杆不生效（`atten_db` 被剔除）、"应用参数"只改文案；功率滑杆默认值覆盖场景文件 | `render_console_pages.py:160/194`；运行副本 `power_dbm=-10.0` |
| I6 | 3782 测试全绿但关键承诺无行为级断言（"绿而不护"） | 六处测试只断言占位/字符串/文件大小（详见用户走查环 E-I7） |
| I7 | 距离 7 米档静默 `n_samples=0`、`judge_per_mean=null`，无 skip/错误 | 两轮距离实测一致 |
| I8 | B210 单轮 77–78 s，手册"约 7 秒"仅 sim 口径；2450 MHz 注入谱可辨性弱（环境峰 -47.2 dB） | 六样式轮实测；tone max/mean -56.53/-77.35 dB |
| I9 | 第 5 章叙述"模拟链路"，但 `--backend auto` 实开 B210；要 sim 须显式 `--backend sim` | 实跑 result `B210Backend` vs `SimBackend` |
| I10 | 手册第 26 章"三件演示走一遍"实为仅 gain 三分支，leakage/compensation 仅状态读取 | `view_calibration_status.py:220-262` |

### Minor（13，留档）

M1 手册"500 帧/~36ms"过时（实测 1000 帧/ts 0–3）；M2 README 3713 vs 3782；M3 旧 noise-only sweep 录音被判 partial_band@0.9455；M4 裸模型无回退 note；M5 demo_smoke 首轮报告 kpi 0 行/frame_a·b 缺（如实标注）；M6 Ctrl+C 后立即同端口重启误报占用；M7 +67dB 本次复测峰均比 57.6dB（≥15dB 判据仍成立，跨实验不可通约注记在案）；M8 NRF 首次直读有缓冲/复位伪影（清缓冲后正常）；M9 rounds=2 仍回退；M10 手册 register 示例值会覆盖自动标注；M11 RFF 空索引走"0 匹配"分支而非 min_samples=4 文案；M12 auto 降级 sim 决策行未观察到（B210 在位）；M13 标定三表仍【待实测】。

## 8 未过项与处置（本报告不宣布完成）

1. **用户走查环未清零**：2 Critical（C1/C2）+ 7 Important（I1–I6 及路径问题）——按用户裁决"只登记不修"，未修复、未复走查。
2. **演示手册 1–18 章新增 2 Critical**：C3（第 8 章命令照抄必败）、C4（溯源假绿）与 3 Important（I7/I8/I9）。
3. **fn-close 出口规则冲突**：规程要求 Critical/Important 清零才出门；用户明确"本批只走查不改码"，故本报告**以未过项清单交付**，不以"验收完成"口径呈现。
4. **移交**：C1–C4 建议优先；其余 I/M 项按用户裁决另行排期；R98–R102（monitor 交窗/键集/标定/测试补强）仍延后未启动。

## 9 结论

- 六道中①–⑥均已执行并留原样证据；其中③的机械错误为在册假阳基线，人工复核未发现新增漏实现/死代码/静默漂移。
- R87 的 26 章走查已完成可执行部分（1–18 章真机 CLI + 19–26 章网页实测），产出 4 Critical / 10 Important / 13 Minor。
- 按用户裁决 B，本批**不修复**；验收与否由用户判定。

以上为终检事实，验收与否由用户判定。
