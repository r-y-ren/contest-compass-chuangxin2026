# 验收报告：无人机链路抗干扰测试平台·R94 设备接口真值同步周期（c5）
> fn-close 独占产出（2026-10-15）。核验输出原样粘贴，禁止转述、禁止"概括为通过"。
> 本报告不宣布"验收通过"——终审归用户。上周期报告（R90 修订周期）归档于 acceptance-c4.md。
> 终检时点：R94 B46 全链（c7e4369→b5263f2→e6898d7）+双审全闭后。
> **双会话共存声明**：并行演进轮④（R91-R93 识别器改造）正在实施——其桩与档案中间态在库（①段 6 桩归属其批，git log 77afff5/447ed3a 滚动落地）——本报告双口径记账（R94 自身面/并行在途面），先例=R90 进入对账。

## 终检一览

| 终检 | 命令 | 结果 | 证据 |
|---|---|---|---|
| ① 桩+全量测试+镜像 | scripts/fn-check.sh | ①FAIL 6 桩=**全部并行在途**（R94 自身 0）②PASS 3640+1skip ③WARN 既档噪声 | §1/§2 |
| ② 接线与实跑 | — | prepare 实跑 19 项（9a/9b 在位）；demo_manual_check 绿 | §3 |
| ③ 矩阵双向 | fn-doc-lint.py+独立核对 | lint 427 错=假阳族+并行中间态（view_cv_evaluation stub 行=其 B48 批）；独立双向 94 R 行/169 wired | §4 |
| ④ 非功能对照 | — | 11 条逐条过（231+1skip 约束族） | §5 |
| ⑤ 报告完整性 | — | 无自封结论、末行固定句在 | — |
| ⑥ 目录清点 | — | scratch 无/vendor 无/requirements 16 包+venv 在位/PDF 登记 | §6 |

## 1 桩检查（fn-check.sh ①段原文）
```
== ① 残留桩 ==
FAIL 残留桩 6 处：
```
（6 桩=并行演进轮④在途批 B47/B48：`_rule_decision`/`_template_classify`/`make_predict_style_callbacks` 等——`git grep unimplemented:fn: HEAD` 3 名+工作树同源；R94 自身桩面=0（B46 改造点为存量真实现修订）。**判据归因**：①段 FAIL 属并行批中间态非 R94 缺口，如实报告不掩盖；其批 fn-close 由彼会话自理。）

## 2 全量测试（fn-check.sh ②段原文）
```
=========== 3640 passed, 1 skipped, 2 warnings in 168.24s (0:02:48) ============
PASS 全量测试
```
（3640=c4 基线 3631+R94 净增 9（⑦ 同步锚+并行其批 8）；1 skip=B210 真机条件守卫；走查环独立复跑一致。）

## 3 接线与实跑
- **prepare_demo_assets（R94 改造点：第 9 行细分）**：实跑（临时目录 rounds=1）`written=7 checklist=19 项（9a/9b 在位=True）`；调用点=演示者命令（手册 0.4）。
- **check_demo_manual（R94 间接）**：`pytest -k demo_manual_check -q` → `1 passed`；八键 ok=True passed=26。
- **手册 v2.1（R94 交付物）**：旧接法 grep -qE 零命中（B46 验收在案）；端口名桥接注在 0.2；FPGA 三使用面说明在 0.3。

## 4 需求→函数对照（R94；R1–R93 沿 c2–c4 各报告不变）
| R | 函数/单元 | 核验命令 | 结果 |
|---|---|---|---|
| R94 | 设备接口真值同步（文档交付物）+改造点 prepare_demo_assets | pytest tests/prepare_demo_assets/ -q；grep -qE 旧接法；八键直跑 | 20 passed（含⑦ 同步锚）；零命中；ok=True passed=26 |
- 独立双向：responsibility 94 R 行各有承载；functions.md 169 行 wired（168+并行 B48 stub 行中间态）；lint 427 错=四族假阳（c1 既档）+并行中间态（view_cv_evaluation stub 与 tracker wired 漂移=其批五步进行中）——独立双向替代核对（c1 先例）。

## 5 非功能约束逐条（11/11）
合规红线/实时/切换/插槽/先停发射/溯源/平台/数字纪律/离线/登记/**演示零出错**——约束族聚合 231+1skip 绿；演示零出错=手册 v2.1 八键+走查环清零（本周期走查环：0C/1I/3M+3 观察——I(README 卡片口径)+C(sitl 自曝过时)+D(dB 口径)+E(台账注记) 全修，B(acceptance 断链)=本报告写入自愈）。

## 6 目录清点
.scratch/ 无｜fn_docs/vendor/ 无｜requirements.txt 16 包+.venv 在位｜**docs/USRP_B210说明.pdf 登记 references 参考资料节（3 处提及）**｜设备清单.txt 更新在库（MMCX 细分行）｜并行在途文件（predict_style 等）未入本批提交。

## 走查环留痕
单环闭环（零喂料子代理，user-guide+功能手册+PDF 四方核对）：H1-H20 主线承诺全不成立（宣称为真）——**R94 设备真值四方一致实证**（PDF↔user-guide↔功能手册↔antenna 白名单）；A(README 卡片口径矛盾)已修（分层口径）；C(sitl 自曝已失效)改写；D(dB/dBm 换算口径)补注；E(添置件台账待回写)新条 11；B(acceptance 指针)随本报告复存自愈；F/G/H'(openapi 500/EMC params 踩坑形态/过时注释)=观察登记。

## 已知限制（如实，终审参考）
并行演进轮④在途（其桩/档案中间态在库，终态由彼会话 fn-close）｜识别器轻量替身限界沿 c4｜设备台账回写待办（NRF24×2/屏蔽盒/备件包三件）｜真机频率域保守口径（代码 70M–6G vs 实测 42M–6.008G）｜R87 真机复查延后（含 GPS 天线 MMCX 接法实核）。

以上为终检事实，验收与否由用户判定。
