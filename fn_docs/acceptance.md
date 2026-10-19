# 验收报告：无人机链路抗干扰测试平台（演进轮⑤——真机发射功率→增益映射修复 R95–R97）
> fn-close 独占产出。核验输出原样粘贴，禁止转述、禁止"概括为通过"。
> 本报告不宣布"验收通过"——终审归用户。前版报告已归档 acceptance-c6.md。

## 终检一览
| 终检 | 命令 | 结果 | 证据 |
|---|---|---|---|
| ① 桩+全量测试+镜像 | scripts/fn-check.sh | 桩 0／3782 passed 0 skip／镜像 WARN=固有噪音族 | §1/§2 |
| ② 接线与实跑 | — | 本轮 6 单元调用点在+真机轮实跑记录在案；存量函数由全量套件覆盖 | §3 |
| ③ 矩阵双向 | scripts/fn-doc-lint.py | 433 错/57 警=在册假阳族基线+8 错全落族（分诊独立核对替代，c6 先例）；人工复核：R95–R97 三行在、tracker 0 未勾、批表空 | §4 |
| ④ 非功能对照 | — | 逐条过（定向族实跑） | §5 |
| ⑤ 报告完整性 | — | 无自封结论、末行固定句在 | — |
| ⑥ 目录清点 | — | 无 .scratch／无 vendor／dataset/ 在册观察项／依赖清单入库／参考资料五件对得上 | §6 |
| 走查环 | 用户走查子代理 | 0C/3I/3M→3I+2M 修复（手册 4 处+本报告就位）→复走查清零 | §7 |

## 1 桩检查（fn-check ① 原文）
```
== ① 残留桩 ==
PASS 残留桩 0 处
```

## 2 全量测试（fn-check ② 原文；走查子代理独立复跑同数）
```
================= 3782 passed, 2 warnings in 223.84s (0:03:43) =================
PASS 全量测试
```
走查环独立复跑：`3782 passed, 2 warnings in 219.26s`（0 skip）。计数口径：c6 基线 3708+5skip（B210 不在位）→本轮在位 3713→B50 +8→B51 +54→B52 +6→B53 +1=3782。

## 3 接线与实跑
**本轮六单元**（调用点 grep 实据+实跑记录）：
| 单元 | 调用点 | 实跑 |
|---|---|---|
| get_tx_gain | set_channel_attenuation._dispatch_backend getattr 探测（8 处含测试） | 真机 M-4 对拍 set==get（30/45/60）；mock UHD 8 用例 |
| resolve_base_tx_gain | run_demo.py（6 处）+set_channel_attenuation.py（8 处） | 真机轮基准注入 60.0 生效（events 双列）；10 用例 |
| _dispatch_backend[改造] | set_channel_attenuation 编排 | 真机轮 runs/20261019-142850 六档 30/40/45/50/55/60 全 applied=True via=tx_gain；b210_gain_mapping 10+attenuation_truthful 5 用例 |
| validate_scenario_schema[改造] | load_scenario 链 | _KNOWN_KEYS 64 键；tests/load_scenario 135 绿 |
| run_demo._backend_params[改造]+_ensure_b210_tx_gain | _execute_pipeline :823 接线 | 真机轮=场景 sim+auto 探测命中路径（C1 修复实证）：B210 以 60dB 打开；tests/run_demo 108 绿 |
| build_report[改造] | 阶梯节条件脚注 | 真机轮 report.md:15 脚注在；sim 轮零出现；tests/build_report 63 绿 |

**存量 116 函数**：全量套件 3782 覆盖其测试；接线/实跑记录承 c6 验收（26 章走查环全实跑）+本轮零回退（sim 零扰动三证：open_sim_backend 零 diff+42 绿+sim 实跑事件口径保持）。

## 4 需求→函数对照（矩阵双向）
- 机械轴原文尾行：`== 433 错误, 57 警告 ==`。基线分诊：c6 在册假阳族 416/53（死代码误报/矩阵演进格式/括注/批次表 Ruling 行等，c2/c6 两轮证伪）+本轮增量 8 错全落同族（R95–R97 矩阵行演进格式×3、改造承载括注×3、functions↔tracker 记账格式×2——R91/R92 行同款先例）；长职责 WARN×2 已人工定性（_dispatch_backend 919 字=四形态纯下发编排不拆；resolve_base_tx_gain 333 字=单一解析转变不拆）。
- 人工复核：矩阵 R95/R96/R97 三行在盘且各自顶层承载（set_channel_attenuation/open_b210_backend 改造承载式——R91 先例）；覆盖对账 97 条在 requirements；**漏实现拦截**——本轮三条需求全 wired（functions.md 六行含双哈希）；**死代码拦截**——本轮单元调用链闭合（§3）；**静默漂移拦截**——functions.md 状态与代码一致（桩 0+套件绿）；**tracker 核对**——B50–B53 全行勾（0 未勾）、与 functions.md/git log 三方一致（B51 I2 哈希勘误在案）、批表空=周期全批完成。

## 5 非功能约束逐条（定向实跑原文）
| 约束 | 验证 |
|---|---|
| 合规红线 | `tests/guard_compliance/ → 75 passed`（超功率/频段/声明拒+豁免审计）；本轮增益≤60 实证+80 上限映射层拒+专家键工厂域 |
| 实时性/样式切换/可扩展性/可溯源 | 用例在 3782 内（c6 §5 实跑记录承继，本轮零回退） |
| 安全（异常先停发射） | `tests/shared/test_stop_transmit_safely.py + tests/harden_emergency_stop/ → 34 passed`；本轮新增 _ensure_b210_tx_gain 失败先 stop_tx 仓内钉住（B51 假账抓获后补） |
| 数字纪律/离线可用 | `tests/localize_console_assets/ → 121 passed`；【待实测】标注保持（标定三件未动）；名义/物理双列+未标定脚注=本轮如实口径兑现 |
| sim 零改变（演进轮⑤新增语义） | `tests/open_sim_backend/ → 42 passed`+全量绿+sim 实跑事件 unknown_gain 口径保持（走查 F2 反证后手册如实分列） |
| 其余（采集不扰发射/录音可复现/防失控/识别确定性/置信度披露） | 用例在 3782 内（R88/R91–R93 族，c6 承继零回退） |

## 6 目录清点
- `.scratch/`：不存在（无主暂存=零）；`fn_docs/vendor/`：不存在（无 vendor 件）。
- `fn_work/dataset/`：未跟踪**在册观察项**（用户数据落盘，长期记忆+批表登记；不入库不清理——用户处置面）。
- 依赖清单：`git ls-files fn_work/requirements.txt` 命中（16 包，走查环核）——环境可由清单+系统 uhd 复建（走查 F13 链路实证）。
- 参考资料登记 vs 实际：五件全对上（设备清单.txt／全功能实现清单／平台说明／USRP_B210说明.pdf／诊断-TX发射无效-20261017.md——末者含 §5.6 勘误注）。无"历史参考"待标件。

## 7 走查环（user-guide 全文；单环清零）
首轮走查（对抗子代理，真机单轮实跑）：**0 Critical / 3 Important / 3 Minor**——F1"80dB 硬拒"缺主语（专家键域实为工厂 0–89.75 拒，85 实证通过/90 拒）、F2"unknown_gain 已成历史"缺 sim 限定（sim 轮 12 事件实证仍在=有意保留）、F3 手册尾指针断链（acceptance.md 归档空窗）→修复：手册"真机发射与功率阶梯"段改写（80 硬拒主语+分层域、真机/sim 分列、+67dB 出处标注六档扫/四相位 66.5）；F4 末条编号 12→14；F3 随本报告就位闭环。F6（环回/底噪两节锚点单位口径）=Minor 留档（两处均有单位对冲句）。复走查（scoped）：四修复面逐条核真清零。

## 未完成项
无（R95–R97 全员 wired；B50–B53 四批全部完成入史）。**移交后续**（登记非缺口）：R87 真机复查（monitor 交窗窗口重设计/power_step 键集钉住/标定三件实测/26 章真机走查）、设备台账回写（已知限制 11）、M-C power_step 键集。

以上为终检事实，验收与否由用户判定。
