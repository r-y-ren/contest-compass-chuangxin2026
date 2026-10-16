# 验收报告：识别准确率协同改造（演进轮④：R91–R93，周期 c6·走查环后重写版）
> fn-close 独占产出（2026-10-16）。核验输出原样粘贴，禁止转述、禁止"概括为通过"。
> 本报告不宣布"验收通过"——终审归用户。上周期报告（R94 周期 c5）归档于 acceptance-c5.md；归档链 c1–c5 在案。
> **版本说明**：走查环 C1 修复（efbdf9e）动过代码，本版为六道全部重跑后的同周期重写（旧版作废、git 留痕）。

## 终检一览
| 终检 | 命令 | 结果 | 证据 |
|---|---|---|---|
| ① 桩+全量测试+镜像 | scripts/fn-check.sh | exit 0（残留桩 0；全量 3707 passed, 5 skipped；镜像 WARN=固有噪音） | §1/§2 |
| ② 接线与实跑 | — | 181 函数行非 wired=0；本批三顶层实跑过 | §3 |
| ③ 矩阵双向 | scripts/fn-doc-lint.py | 错误全为在册假阳族（c2 先例独立核对替代） | §4 |
| ④ 非功能对照 | — | 逐条过（含演进轮④新增 2 条） | §5 |
| ⑤ 报告完整性 | — | 无自封结论、末行固定句在 | — |
| ⑥ 目录清点 | — | .scratch 无主件=0；vendor 无件；requirements.txt 在位可复建 | §6 |

## 1 桩检查（fn-check ①段原文）
```
PASS 残留桩 0 处
```

## 2 全量测试（fn-check ②段原文，走查修复后重跑）
```
=========== 3707 passed, 5 skipped, 2 warnings in 190.37s (0:03:10) ============
```
（5 skipped=3 例 B210 探测瞬态[c4 在册缝]+2 参数化跳过；2 warnings=fastapi 既有弃用告警。3707=走查修复前 3704+修复新增 3 用例。）

## 3 接线与实跑（本批三顶层；全库 181 函数行 grep 非 wired=0）
```
predict_style 规则路: tone 0.967 gated键在
grouped_cv 对齐: aligned_template macro_f1= 1.0
```
- `predict_style`（R91/R92）：阶梯门控 tone 合成 IQ 实跑（旧实现判 pulse@0.79 同型输入）；sim 六样式识别器级硬判全对（B47 验收族）；
- `grouped_cv_evaluate`（R93）：对齐回调注入+aligned_template 实跑 macro_f1=1.0；六样式特征向量级全对角用例在册；
- `view_cv_evaluation`（R93）：默认注入+query protocol 透传（15 用例含端点实调）。

## 4 矩阵双向+lint 分诊
fn-doc-lint.py 错误输出逐族分诊均为在册假阳（c2 证伪先例同族）：状态词带括注/变更记录 Ruling 行误切/tracker 模板示例文字/c4-c5 在册资产件与文档交付物/R94 周期行。**独立核对替代**（同前版：divide 三自检留证+门双审档案轴+fn-check ①0 桩+十一函数 wired 逐一 grep+functions 哈希核对）。

## 5 非功能约束逐条（演进轮④相关；既有 15 条沿 c4 结论——R88 用例在 3707 内全绿）
| 约束 | 判据 | 验证 |
|---|---|---|
| 识别确定性（演进轮④） | 同 IQ+同模型→同标签同置信度 | 复走查 A 链确定性断言（两次运行全 dict 相等）+平手排序最小类用例 |
| 置信度如实披露（演进轮④） | 未校准标注附、禁预写 | confidence_note 恒带；RMS 归一后近距 conf≈0.70（旧 0.9999 饱和已治）、真悬殊仍 1.0 如实；手册措辞回真（复走查 A10 推翻假设） |
| 演示零出错（演进轮②） | 手册/页面承诺兑现 | 走查环 24 轮真实用户路径实跑；手册五处措辞回真+M 级登记第 12 条 |

## 6 目录清点
- `.scratch/`：不存在（无主暂存 0）；`fn_docs/vendor/`：不存在；
- 环境可复建：fn_work/requirements.txt 在库（scipy 启用注记在 requirements.md）；fn_work/.venv 在位；
- **杂散文件披露**：仓库根有 4 个未跟踪文件（`os`/`re`/`subprocess`/`sys`，各约 13.6MB，ImageMagick 渲染残留，时间戳 2026-10-16T02:28Z）——非本周期产物（疑并行会话截图链残留），未擅删，移交用户处置。

## 未完成项
无（R91–R93 十一函数全 wired；R87 真机实证为在册延后项）。

## 用户走查环记录（单环：走查→修复→复走查清零）
- **首轮走查**（对抗子代理，24 轮平台测试真跑+训练真做+25 条录音识别实测）：**Critical 1 / Important 6 / Minor 3**。C1=训练模板取全段谱 vs 部署识别切 on 段谱——谱分布错位，平台录音模板路 13/25（tone/chirp/partial_band 12 条全错→sweep、conf 恒 1.0 饱和）；I1-I6=手册措辞与承诺面缺口（无模型提示态/评测等号限定/两口径同构/置信度饱和/切片口径/protocol API 层）。
- **修复**（efbdf9e）：train_classifier/view_cv_evaluation 增 `_scoped_profile`（门控感知特征提取——与部署 scope 判定同型同源 import，复走查 AST 级+8 边界差分证逐句一致）；spectral_template_match 距离按维度归一（RMS 口径）防 softmax 饱和；手册五处措辞回真+M 级登记。**修复实证**：合成阶梯 IQ 六样式模板路 6/6（旧口径对照 4/6 错位复现）。
- **复走查**（scoped，独立几何/种子）：11 条对抗假设全推翻（同型性 0 分叉/独立几何 6/6+3 hold-out 种子全对/手册措辞属实/四套件 143 passed 零回归）——**C/I 清零**；唯一新发现 M1"首行"措辞一字级已改。
- 走查环结论：Critical/Important 清零（M1 处置+M 级留档 user-guide 已知限制第 12 条）。

## 本周期变更摘要（B47/B48 十一函数+走查修复，供终审索引）
- R91 门控感知两级分类：_classify_dummy 改造+三叶提出（连续分流 duty_on≥0.9/段内分类=最长单段≥3×nfft/两层门控兜底/features 扩键）——sim 六样式识别器级硬判全对（tone 0.943/sweep 0.700/chirp 0.750/noise 0.837/partial 0.550/pulse 0.901），「sim 恒 pulse@0.76」缺陷已修；
- R92 推理消费训练产出：_predict_one 模板/规则分流+_template_classify+shared spectral_template_match（softmax over negative distances·RMS 归一·未校准）+_load_model 顶层模板规整（快速通道）——真链用例（rebuild→local 训练→模型文件→识别 6/6）；
- R93 评测口径对齐：make_predict_style_callbacks（predict_fn 与部署同一实现）+grouped_cv_evaluate eval_protocol 白名单（intrinsic_dummy/aligned_template/custom）+view_cv_evaluation 默认注入+query 透传——六样式对齐口径用例全对角 macro_f1==1.0；
- 走查环 C1 修复（efbdf9e）：训练/评测特征门控 scope 与部署统一（_scoped_profile）——平台录音整块口径六样式 6/6（复走查独立复算）；置信度饱和已治（近距 0.70）；
- 批间双审两门全处置（Critical 清零；I/M 全修复或登记：0368f0b/697aa49）；Ruling/勘误/快速通道行在册。

以上为终检事实，验收与否由用户判定。
