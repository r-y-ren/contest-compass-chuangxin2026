# history.md —— 历史表（已完成批次队列，只追加不删改）
> fn-implement 独占更新。每批次完成后尾部追加留痕。

| 完成日期 | 批次 | 任务/函数清单（含操作与来源说明） | 验收摘要 |
|---|---|---|---|
| 10-11 | B1 | check_power_cap, check_band_whitelist, check_env_declarations, guard_compliance（3 叶并行子代理+顶层 1 子代理；Ruling×2 见 tracker） | 40 用例全绿；compliance_guard 7 用例；顶层实跑三条款拒；4 函数 commit+哈希补记 d5f0299 |
| 10-11 | B1+ | 批间用户裁决=缺陷审查后继续：对抗审查发现 2 高（NaN 功率/NaN cap 绕过红线）1 中（空白豁免）3 低 + 4 类盲区 → 修复+35 回归，75 用例全绿（fix commit 见 git） | 红线绕过全堵死；端到端 NaN/inf 拒绝 |
| 10-11 | B2 | load_calibration_table, check_monotonicity, calibrate_leakage（波1 并行）, lookup_jsr, build_gain_calibration, compensate_link_power（波2 并行）；Ruling④ flat JSON | 全库 223 用例绿；三顶层实跑探针过；6 函数 wired |
| 10-11 | B2+ | 批间用户裁决=漏洞审查后继续：对抗审查高7（异常逃逸家族：OverflowError/RecursionError/IsADirectoryError）中1（数值等价档摆动）低1（负容差）→ 全修复+24 回归；审查中子代理误删 fn_work 已 git 恢复（完整性复核 176 文件/223→247 绿） | 不抛出契约全恢复；同档数值等价去重 |
