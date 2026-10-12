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
