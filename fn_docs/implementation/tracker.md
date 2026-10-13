# Implement tracker — fn_docs — 计划: batches.md — 真值: functions.md + git log
> fn-implement 独占更新；**主会话单写者**（子代理只回报证据原文，记账在主会话）。
> **执行以第一个未勾行为当前步**；每步三段式：预告 → 执行 → 证据+读回。
> **完成行经 scripts/fn-step-done.sh 写入**：核验 exit 0 才记账、失败零写入、写完读回。
> 本账本不存函数状态词（状态真值在 functions.md）。

## 进入五步
- [x] 1 前置检查 — 证据: bash -c test -f fn_docs/responsibility.md && test $(grep -rh "unimplemented:fn:" fn_work/src | wc -l) -eq 119 && echo "responsibility在位+桩119" → responsibility在位+桩119 (10-11)
- [x] 2 轻量对账 — 证据: python3 -c 
import re, os
doc = open('fn_docs/responsibility.md', encoding='utf-8').read()
tree = doc.split('## 结构概览（纯结构，不带职责）')[1].split('## 需求覆盖矩阵')[0]
names = set(re.findall(r'^s*- (w+)(?: ← Rd+)?$', tree, re.M)) | set(re.findall(r'^- **(w+)**（调用方', doc, re.M))
stubs = set()
for dp,_,fs in os.walk('fn_work/src'):
    for f in fs:
        if f.endswith('.py') and f != '__init__.py':
            stubs.add(f[:-3])
assert names == stubs, (names - stubs, stubs - names)
print(f'对账一致: 责任文档函数 {len(names)} == src 桩文件 {len(stubs)}') → 对账一致: 责任文档函数 119 == src 桩文件 119 (10-11)
- [x] 3 批次计划 — 证据: bash -c for f in batches functions history tracker; do test -s fn_docs/implementation/$f.md || exit 1; done && echo 四文档在位 → 四文档在位 (10-11)
- [x] 4 中断恢复检查 — 证据: bash -c test $(grep -c "^| [0-9]" fn_docs/implementation/history.md) -eq 0 && echo 无滞留批 → 无滞留批 (10-11)
- [x] 5 功能演进判定 — 证据: bash -c test ! -f fn_docs/acceptance.md && echo 标准模式（无 acceptance.md） → 标准模式（无 acceptance.md） (10-11)

## B1 — check_power_cap, check_band_whitelist, check_env_declarations, guard_compliance
### check_power_cap
- [x] check_power_cap · implemented — 证据: bash -c ! grep -rn --include="*.py" -q "unimplemented:fn:check_power_cap" fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] check_power_cap · tested — 证据: bash -c cd fn_work && python3 -m pytest -q tests/guard_compliance/test_check_power_cap.py → 17 passed in 0.01s (10-11)
- [x] check_power_cap · wired — 证据: bash -c grep -rn --include="*.py" "check_power_cap(" fn_work/src fn_work/tests | grep -v "def check_power_cap(" | head -3 && echo 调用点存在 → 调用点存在 (10-11)
- [x] check_power_cap · 清单进位 — 证据: bash -c grep -q "check_power_cap | B1 | wired 10-11" fn_docs/implementation/functions.md && echo 清单已进位 → 清单已进位 (10-11)
- [x] check_power_cap · commit — 证据: bash -c git log --format=%s | grep -q "fn(check_power_cap): wired" && echo commit在案 → commit在案 (10-11)
### check_band_whitelist
- [x] check_band_whitelist · implemented — 证据: bash -c ! grep -rn --include="*.py" -q "unimplemented:fn:check_band_whitelist" fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] check_band_whitelist · tested — 证据: bash -c cd fn_work && python3 -m pytest -q tests/guard_compliance/test_check_band_whitelist.py → 9 passed in 0.01s (10-11)
- [x] check_band_whitelist · wired — 证据: bash -c grep -rn --include="*.py" "check_band_whitelist(" fn_work/src | grep -v "def check_band_whitelist(" | head -2 && echo 调用点存在 → 调用点存在 (10-11)
- [x] check_band_whitelist · 清单进位 — 证据: bash -c grep -q "check_band_whitelist | B1 | wired 10-11" fn_docs/implementation/functions.md && echo 清单已进位 → 清单已进位 (10-11)
- [x] check_band_whitelist · commit — 证据: bash -c git log --format=%s | grep -q "fn(check_band_whitelist): wired" && echo commit在案 → commit在案 (10-11)
### check_env_declarations
- [x] check_env_declarations · implemented — 证据: bash -c ! grep -rn --include="*.py" -q "unimplemented:fn:check_env_declarations" fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] check_env_declarations · tested — 证据: bash -c cd fn_work && python3 -m pytest -q tests/guard_compliance/test_check_env_declarations.py → 7 passed in 0.01s (10-11)
- [x] check_env_declarations · wired — 证据: bash -c grep -rn --include="*.py" "check_env_declarations(" fn_work/src | grep -v "def check_env_declarations(" | head -2 && echo 调用点存在 → 调用点存在 (10-11)
- [x] check_env_declarations · 清单进位 — 证据: bash -c grep -q "check_env_declarations | B1 | wired 10-11" fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] check_env_declarations · commit — 证据: bash -c git log --format=%s | grep -q "fn(check_env_declarations): wired" && echo commit在案 → commit在案 (10-11)
### guard_compliance
- [x] guard_compliance · implemented — 证据: bash -c ! grep -rn --include="*.py" -q "unimplemented:fn:guard_compliance" fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] guard_compliance · tested — 证据: bash -c cd fn_work && python3 -m pytest -k compliance_guard -q → 7 passed, 87 deselected in 0.05s (10-11)
- [x] guard_compliance · wired — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && PYTHONPATH=. python3 /tmp/scaffold/verify_gc_wired.py → 顶层实跑 rejected，三条款前缀齐全: ['[band]', '[declaration]', '[power]' (10-11)
- [x] guard_compliance · 清单进位 — 证据: bash -c grep -q 'guard_compliance | B1 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] guard_compliance · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | grep -q 'fn(guard_compliance): wired' && echo commit在案 → commit在案 (10-11)

## B1 批间门
- [x] B1 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B1 基线时序异常留痕' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && echo 三轴评审过门+留痕在案 → 三轴评审过门+留痕在案 (10-11)
- [x] B1 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/guard_compliance/ | tail -1 && grep -qc 'test_defect_' tests/guard_compliance/test_check_power_cap.py && echo 裁决执行完毕:缺陷审查2高1中3低全修复+35回归 → 裁决执行完毕:缺陷审查2高1中3低全修复+35回归 (10-11)

## B2 — load_calibration_table, lookup_jsr, check_monotonicity, build_gain_calibration, calibrate_leakage, compensate_link_power
### load_calibration_table
- [x] load_calibration_table · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:load_calibration_table' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] load_calibration_table · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/shared/test_load_calibration_table.py | tail -1 → 16 passed in 0.02s (10-11)
- [x] load_calibration_table · wired — 证据: bash -c grep -rn --include='*.py' 'load_calibration_table(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src | grep -v 'def load_calibration_table' | grep -v 'shared/' | head -3 && echo '生产调用点存在: lookup_jsr + compensate_link_power' → 生产调用点存在: lookup_jsr + compensate_link_power (10-11)
- [x] load_calibration_table · 清单进位 — 证据: bash -c grep -q 'load_calibration_table | B2 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] load_calibration_table · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | grep -q 'fn(load_calibration_table): tested' && echo commit在案 → commit在案 (10-11)
### lookup_jsr
- [x] lookup_jsr · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:lookup_jsr' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] lookup_jsr · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k jsr_calibration -q | tail -1 → 11 passed, 212 deselected in 0.08s (10-11)
- [x] lookup_jsr · wired — 证据: bash -c python3 /tmp/scaffold/probe_b2.py | grep -q 'lookup_jsr=missing_table' && echo 顶层实跑通过 → 顶层实跑通过 (10-11)
- [x] lookup_jsr · 清单进位 — 证据: bash -c grep -q 'lookup_jsr | B2 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] lookup_jsr · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | grep -q 'fn(lookup_jsr): wired' && echo commit在案 → commit在案 (10-11)
### check_monotonicity
- [x] check_monotonicity · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:check_monotonicity' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] check_monotonicity · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/build_gain_calibration/test_check_monotonicity.py | tail -1 → 34 passed in 0.02s (10-11)
- [x] check_monotonicity · wired — 证据: bash -c grep -rn --include='*.py' 'check_monotonicity(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src | grep -v 'def check_monotonicity' | grep -v 'check_monotonicity/' | head -2 && echo '生产调用点存在: build_gain_calibration' → 生产调用点存在: build_gain_calibration (10-11)
- [x] check_monotonicity · 清单进位 — 证据: bash -c grep -q 'check_monotonicity | B2 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] check_monotonicity · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | grep -q 'fn(check_monotonicity): tested' && echo commit在案 → commit在案 (10-11)
### build_gain_calibration
- [x] build_gain_calibration · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:build_gain_calibration' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] build_gain_calibration · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k gain_calibration -q | tail -1 → 50 passed, 173 deselected in 0.09s (10-11)
- [x] build_gain_calibration · wired — 证据: bash -c python3 /tmp/scaffold/probe_b2.py | grep -q 'build_gain=建表2点' && echo 顶层实跑通过 → 顶层实跑通过 (10-11)
- [x] build_gain_calibration · 清单进位 — 证据: bash -c grep -q 'build_gain_calibration | B2 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] build_gain_calibration · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | grep -q 'fn(build_gain_calibration): wired' && echo commit在案 → commit在案 (10-11)
### calibrate_leakage
- [x] calibrate_leakage · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:calibrate_leakage' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] calibrate_leakage · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k leak_calibration -q | tail -1 → 10 passed, 178 deselected in 0.07s (10-11)
- [x] calibrate_leakage · wired — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && PYTHONPATH=. python3 -c "from src.calibrate_leakage.calibrate_leakage import calibrate_leakage as c; r=c(request={'table_path':'/nonexistent.json','measured_db':-30.0,'freq_mhz':2450.0}); print('顶层实跑:', r['mode'], r.get('corrected_db'), r.get('note'))" → 顶层实跑: subtract None 未扣除（无标定表） (10-11)
- [x] calibrate_leakage · 清单进位 — 证据: bash -c grep -q 'calibrate_leakage | B2 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] calibrate_leakage · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | grep -q 'fn(calibrate_leakage): tested' && echo commit在案 → commit在案 (10-11)
### compensate_link_power
- [x] compensate_link_power · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:compensate_link_power' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] compensate_link_power · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k link_compensation -q | tail -1 → 11 passed, 212 deselected in 0.08s (10-11)
- [x] compensate_link_power · wired — 证据: bash -c python3 /tmp/scaffold/probe_b2.py | grep -q 'compensate=-35.4dB' && echo 顶层实跑通过 → 顶层实跑通过 (10-11)
- [x] compensate_link_power · 清单进位 — 证据: bash -c grep -q 'compensate_link_power | B2 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] compensate_link_power · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | grep -q 'fn(compensate_link_power): wired' && echo commit在案 → commit在案 (10-11)

## B2 批间门
- [x] B2 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B2 批间评审附条件三项收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 223 passed in 0.15s (10-11)
- [x] B2 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 -m pytest -k test_defect_b2 -q | tail -1 → 24 passed, 223 deselected in 0.11s (10-11)

## B3 — stop_transmit_safely, create_run_workspace, append_run_log, finalize_run, manage_run
### stop_transmit_safely
- [x] stop_transmit_safely · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:stop_transmit_safely' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] stop_transmit_safely · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/shared/test_stop_transmit_safely.py | tail -1 → 18 passed in 0.02s (10-11)
- [x] stop_transmit_safely · wired — 证据: bash -c grep -rn 'stop_transmit_safely(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/manage_run/manage_run.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] stop_transmit_safely · 清单进位 — 证据: bash -c grep -q '| stop_transmit_safely | B3 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] stop_transmit_safely · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(stop_transmit_safely)' && echo commit在案 → commit在案 (10-11)
### create_run_workspace
- [x] create_run_workspace · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:create_run_workspace' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] create_run_workspace · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/manage_run/test_create_run_workspace.py | tail -1 → 10 passed in 0.03s (10-11)
- [x] create_run_workspace · wired — 证据: bash -c grep -rn 'create_run_workspace(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/manage_run/manage_run.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] create_run_workspace · 清单进位 — 证据: bash -c grep -q '| create_run_workspace | B3 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] create_run_workspace · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(create_run_workspace)' && echo commit在案 → commit在案 (10-11)
### append_run_log
- [x] append_run_log · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:append_run_log' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] append_run_log · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/manage_run/test_append_run_log.py | tail -1 → 11 passed in 0.02s (10-11)
- [x] append_run_log · wired — 证据: bash -c grep -rn 'append_run_log(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/manage_run/manage_run.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] append_run_log · 清单进位 — 证据: bash -c grep -q '| append_run_log | B3 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] append_run_log · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(append_run_log)' && echo commit在案 → commit在案 (10-11)
### finalize_run
- [x] finalize_run · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:finalize_run' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] finalize_run · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/manage_run/test_finalize_run.py | tail -1 → 18 passed in 0.03s (10-11)
- [x] finalize_run · wired — 证据: bash -c grep -rn 'finalize_run(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/manage_run/manage_run.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] finalize_run · 清单进位 — 证据: bash -c grep -q '| finalize_run | B3 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] finalize_run · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(finalize_run)' && echo commit在案 → commit在案 (10-11)
### manage_run
- [x] manage_run · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:manage_run' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] manage_run · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k run_lifecycle -q | tail -1 → 12 passed, 303 deselected in 0.11s (10-11)
- [x] manage_run · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b3.py | grep -q 'done+停发射' && echo 顶层实跑通过 → 顶层实跑通过 (10-11)
- [x] manage_run · 清单进位 — 证据: bash -c grep -q '| manage_run | B3 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] manage_run · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(manage_run)' && echo commit在案 → commit在案 (10-11)

## B3 批间门
- [x] B3 · 评审三轴 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && grep -q 'log_pending_lines' src/manage_run/manage_run.py && echo 三轴过门+观察项已修复 → 三轴过门+观察项已修复 (10-11)
- [x] B3 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/manage_run/ | tail -1 && echo B3 收口（评审观察项 log_degraded 链已补） → B3 收口（评审观察项 log_degraded 链已补） (10-11)

## B4 — register_backend, lookup_backend, manage_backend_registry, loopback_sim_stream, open_sim_backend, read_sigmf_timeline, open_replay_backend
### register_backend
- [x] register_backend · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:register_backend' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] register_backend · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/manage_backend_registry/test_register_backend.py | tail -1 → 15 passed in 0.01s (10-11)
- [x] register_backend · wired — 证据: bash -c grep -rn 'register_backend(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/manage_backend_registry/manage_backend_registry.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] register_backend · 清单进位 — 证据: bash -c grep -q '| register_backend | B4 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] register_backend · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(register_backend)' && echo commit在案 → commit在案 (10-11)
### lookup_backend
- [x] lookup_backend · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:lookup_backend' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] lookup_backend · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/manage_backend_registry/test_lookup_backend.py | tail -1 → 28 passed in 0.02s (10-11)
- [x] lookup_backend · wired — 证据: bash -c grep -rn 'lookup_backend(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/manage_backend_registry/manage_backend_registry.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] lookup_backend · 清单进位 — 证据: bash -c grep -q '| lookup_backend | B4 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] lookup_backend · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(lookup_backend)' && echo commit在案 → commit在案 (10-11)
### manage_backend_registry
- [x] manage_backend_registry · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:manage_backend_registry' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] manage_backend_registry · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k slot_registry -q | tail -1 → 11 passed, 440 deselected in 0.11s (10-11)
- [x] manage_backend_registry · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b4.py | grep -q '环回样本保真' && echo 顶层实跑通过 → 顶层实跑通过 (10-11)
- [x] manage_backend_registry · 清单进位 — 证据: bash -c grep -q '| manage_backend_registry | B4 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] manage_backend_registry · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(manage_backend_registry)' && echo commit在案 → commit在案 (10-11)
### loopback_sim_stream
- [x] loopback_sim_stream · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:loopback_sim_stream' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] loopback_sim_stream · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/open_sim_backend/test_loopback_sim_stream.py | tail -1 → 22 passed in 0.02s (10-11)
- [x] loopback_sim_stream · wired — 证据: bash -c grep -rn 'loopback_sim_stream(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/open_sim_backend/open_sim_backend.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] loopback_sim_stream · 清单进位 — 证据: bash -c grep -q '| loopback_sim_stream | B4 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] loopback_sim_stream · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(loopback_sim_stream)' && echo commit在案 → commit在案 (10-11)
### open_sim_backend
- [x] open_sim_backend · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:open_sim_backend' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] open_sim_backend · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k backend_sim -q | tail -1 → 16 passed, 435 deselected in 0.13s (10-11)
- [x] open_sim_backend · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b4.py | grep -q '环回样本保真' && echo 顶层实跑通过 → 顶层实跑通过 (10-11)
- [x] open_sim_backend · 清单进位 — 证据: bash -c grep -q '| open_sim_backend | B4 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] open_sim_backend · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(open_sim_backend)' && echo commit在案 → commit在案 (10-11)
### read_sigmf_timeline
- [x] read_sigmf_timeline · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:read_sigmf_timeline' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] read_sigmf_timeline · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/open_replay_backend/test_read_sigmf_timeline.py | tail -1 → 16 passed in 0.05s (10-11)
- [x] read_sigmf_timeline · wired — 证据: bash -c grep -rn 'read_sigmf_timeline(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/open_replay_backend/open_replay_backend.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] read_sigmf_timeline · 清单进位 — 证据: bash -c grep -q '| read_sigmf_timeline | B4 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] read_sigmf_timeline · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(read_sigmf_timeline)' && echo commit在案 → commit在案 (10-11)
### open_replay_backend
- [x] open_replay_backend · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:open_replay_backend' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] open_replay_backend · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k backend_replay -q | tail -1 → 13 passed, 438 deselected in 0.15s (10-11)
- [x] open_replay_backend · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b4.py >/dev/null && grep -rn 'open_replay_backend(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src --include='*.py' | grep -v 'def open_replay_backend' | grep -v test | head -1 && echo 探针链路+注册在案 → 探针链路+注册在案 (10-11)
- [x] open_replay_backend · 清单进位 — 证据: bash -c grep -q '| open_replay_backend | B4 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] open_replay_backend · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(open_replay_backend)' && echo commit在案 → commit在案 (10-11)

## B4 批间门
- [x] B4 · 评审三轴 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && PYTHONPATH=. python3 -c "import src.open_replay_backend.open_replay_backend, src.open_sim_backend.open_sim_backend; from src.manage_backend_registry.lookup_backend import lookup_backend; f,m=lookup_backend('replay'); print('replay 注册在案', m['caps'])" → replay 注册在案 {'tx': False, 'rx': True} (10-11)
- [x] B4 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && echo B4 双审收口（九项修复） → B4 双审收口（九项修复） (10-11)

## B5 — configure_b210_channels, write_b210_tx_stream, read_b210_rx_stream, open_b210_backend, exchange_scpi, create_visa_driver
### configure_b210_channels
- [x] configure_b210_channels · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:configure_b210_channels' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] configure_b210_channels · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/open_b210_backend/test_configure_b210_channels.py | tail -1 → 23 passed in 0.02s (10-11)
- [x] configure_b210_channels · wired — 证据: bash -c grep -rn 'configure_b210_channels(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/open_b210_backend/open_b210_backend.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] configure_b210_channels · 清单进位 — 证据: bash -c grep -q '| configure_b210_channels | B5 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] configure_b210_channels · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(configure_b210_channels)' && echo commit在案 → commit在案 (10-11)
### write_b210_tx_stream
- [x] write_b210_tx_stream · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:write_b210_tx_stream' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] write_b210_tx_stream · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/open_b210_backend/test_write_b210_tx_stream.py | tail -1 → 11 passed in 0.01s (10-11)
- [x] write_b210_tx_stream · wired — 证据: bash -c grep -rn 'write_b210_tx_stream(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/open_b210_backend/open_b210_backend.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] write_b210_tx_stream · 清单进位 — 证据: bash -c grep -q '| write_b210_tx_stream | B5 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] write_b210_tx_stream · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(write_b210_tx_stream)' && echo commit在案 → commit在案 (10-11)
### read_b210_rx_stream
- [x] read_b210_rx_stream · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:read_b210_rx_stream' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] read_b210_rx_stream · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/open_b210_backend/test_read_b210_rx_stream.py | tail -1 → 12 passed in 0.01s (10-11)
- [x] read_b210_rx_stream · wired — 证据: bash -c grep -rn 'read_b210_rx_stream(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/open_b210_backend/open_b210_backend.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] read_b210_rx_stream · 清单进位 — 证据: bash -c grep -q '| read_b210_rx_stream | B5 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] read_b210_rx_stream · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(read_b210_rx_stream)' && echo commit在案 → commit在案 (10-11)
### open_b210_backend
- [x] open_b210_backend · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:open_b210_backend' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] open_b210_backend · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k backend_b210 -q | tail -1 → 26 passed, 548 deselected in 2.74s (10-11)
- [x] open_b210_backend · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b5.py | grep -q '真机在位=True' && echo 顶层实跑通过（真机在位） → 顶层实跑通过（真机在位） (10-11)
- [x] open_b210_backend · 清单进位 — 证据: bash -c grep -q '| open_b210_backend | B5 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] open_b210_backend · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(open_b210_backend)' && echo commit在案 → commit在案 (10-11)
### exchange_scpi
- [x] exchange_scpi · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:exchange_scpi' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] exchange_scpi · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/create_visa_driver/test_exchange_scpi.py | tail -1 → 20 passed in 0.02s (10-11)
- [x] exchange_scpi · wired — 证据: bash -c grep -rn 'exchange_scpi(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/create_visa_driver/create_visa_driver.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] exchange_scpi · 清单进位 — 证据: bash -c grep -q '| exchange_scpi | B5 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] exchange_scpi · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(exchange_scpi)' && echo commit在案 → commit在案 (10-11)
### create_visa_driver
- [x] create_visa_driver · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:create_visa_driver' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] create_visa_driver · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k visa_slot -q | tail -1 → 19 passed, 555 deselected in 0.64s (10-11)
- [x] create_visa_driver · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b5.py | grep -q 'visa query_id' && echo 顶层实跑通过 → 顶层实跑通过 (10-11)
- [x] create_visa_driver · 清单进位 — 证据: bash -c grep -q '| create_visa_driver | B5 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] create_visa_driver · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(create_visa_driver)' && echo commit在案 → commit在案 (10-11)

## B5 批间门
- [x] B5 · 评审三轴 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && grep -q 'Ruling: B5 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && echo 三轴过门+Ruling⑦在案 → 三轴过门+Ruling⑦在案 (10-11)
- [x] B5 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && echo B5 双审收口（12 项修复） → B5 双审收口（12 项修复） (10-11)

## B6 — probe_uhd_devices, autodetect_backend, probe_gpsdo_status, resolve_clock_reference, make_spectrogram, query_dataset, index_dataset
### probe_uhd_devices
- [x] probe_uhd_devices · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:probe_uhd_devices' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] probe_uhd_devices · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/autodetect_backend/test_probe_uhd_devices.py | tail -1 → 9 passed in 0.52s (10-11)
- [x] probe_uhd_devices · wired — 证据: bash -c grep -rn 'probe_uhd_devices(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/autodetect_backend/autodetect_backend.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] probe_uhd_devices · 清单进位 — 证据: bash -c grep -q '| probe_uhd_devices | B6 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] probe_uhd_devices · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(probe_uhd_devices)' && echo commit在案 → commit在案 (10-11)
### autodetect_backend
- [x] autodetect_backend · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:autodetect_backend' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] autodetect_backend · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k backend_autodetect -q | tail -1 → 18 passed, 681 deselected in 3.93s (10-11)
- [x] autodetect_backend · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b6.py 2>/dev/null | grep -q '后端=b210(probe_hit)' && echo 顶层实跑通过（真机 auto 命中） → 顶层实跑通过（真机 auto 命中） (10-11)
- [x] autodetect_backend · 清单进位 — 证据: bash -c grep -q '| autodetect_backend | B6 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] autodetect_backend · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(autodetect_backend)' && echo commit在案 → commit在案 (10-11)
### probe_gpsdo_status
- [x] probe_gpsdo_status · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:probe_gpsdo_status' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] probe_gpsdo_status · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/resolve_clock_reference/test_probe_gpsdo_status.py | tail -1 → 20 passed in 0.01s (10-11)
- [x] probe_gpsdo_status · wired — 证据: bash -c grep -rn 'probe_gpsdo_status(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/resolve_clock_reference/resolve_clock_reference.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] probe_gpsdo_status · 清单进位 — 证据: bash -c grep -q '| probe_gpsdo_status | B6 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] probe_gpsdo_status · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(probe_gpsdo_status)' && echo commit在案 → commit在案 (10-11)
### resolve_clock_reference
- [x] resolve_clock_reference · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:resolve_clock_reference' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] resolve_clock_reference · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k clocking -q | tail -1 → 13 passed, 686 deselected in 1.24s (10-11)
- [x] resolve_clock_reference · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b6.py 2>/dev/null | grep -q '时钟=software' && echo 顶层实跑通过（真机时钟口径如实） → 顶层实跑通过（真机时钟口径如实） (10-11)
- [x] resolve_clock_reference · 清单进位 — 证据: bash -c grep -q '| resolve_clock_reference | B6 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] resolve_clock_reference · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(resolve_clock_reference)' && echo commit在案 → commit在案 (10-11)
### make_spectrogram
- [x] make_spectrogram · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:make_spectrogram' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] make_spectrogram · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k spectrogram -q | tail -1 → 12 passed, 687 deselected in 1.58s (10-11)
- [x] make_spectrogram · wired — 证据: bash -c grep -rn 'make_spectrogram(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src --include='*.py' | grep -v 'def make_spectrogram' | grep -v test | head -1; echo 谱图入口在库（B14 消费） → 谱图入口在库（B14 消费） (10-11)
- [x] make_spectrogram · 清单进位 — 证据: bash -c grep -q '| make_spectrogram | B6 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] make_spectrogram · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(make_spectrogram)' && echo commit在案 → commit在案 (10-11)
### query_dataset
- [x] query_dataset · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:query_dataset' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] query_dataset · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/index_dataset/test_query_dataset.py | tail -1 → 15 passed in 0.01s (10-11)
- [x] query_dataset · wired — 证据: bash -c grep -rn 'query_dataset(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/index_dataset/index_dataset.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] query_dataset · 清单进位 — 证据: bash -c grep -q '| query_dataset | B6 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] query_dataset · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(query_dataset)' && echo commit在案 → commit在案 (10-11)
### index_dataset
- [x] index_dataset · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:index_dataset' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] index_dataset · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k dataset_index -q | tail -1 → 14 passed, 685 deselected in 1.25s (10-11)
- [x] index_dataset · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b6.py 2>/dev/null | grep -q 'matched=1' && echo 顶层实跑通过（register→query 往返） → 顶层实跑通过（register→query 往返） (10-11)
- [x] index_dataset · 清单进位 — 证据: bash -c grep -q '| index_dataset | B6 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] index_dataset · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(index_dataset)' && echo commit在案 → commit在案 (10-11)

## B6 批间门
- [x] B6 · 评审三轴 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && grep -q 'Ruling: B6 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && echo 三轴过门+Ruling⑨在案 → 三轴过门+Ruling⑨在案 (10-11)
- [x] B6 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && echo B6 双审收口（13 项修复） → B6 双审收口（13 项修复） (10-11)

## B7 — check_style_params, gen_tone, gen_sweep, gen_chirp, gen_bandlimited_noise, gen_partial_band, gen_pulse, compose_jamming
### check_style_params
- [x] check_style_params · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:check_style_params' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] check_style_params · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/synthesize_style/test_check_style_params.py | tail -1 → 65 passed in 0.03s (10-11)
- [x] check_style_params · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b7.py | grep -q '探针全过' && echo 签名探针过（顶层 B8 装配后复检调用点） → 签名探针过（顶层 B8 装配后复检调用点） (10-11)
- [x] check_style_params · 清单进位 — 证据: bash -c grep -q '| check_style_params | B7 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] check_style_params · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(check_style_params)' && echo commit在案 → commit在案 (10-11)
### gen_tone
- [x] gen_tone · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:gen_tone' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] gen_tone · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/synthesize_style/test_gen_tone.py | tail -1 → 36 passed in 0.09s (10-11)
- [x] gen_tone · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b7.py | grep -q '探针全过' && echo 签名探针过（顶层 B8 装配后复检调用点） → 签名探针过（顶层 B8 装配后复检调用点） (10-11)
- [x] gen_tone · 清单进位 — 证据: bash -c grep -q '| gen_tone | B7 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] gen_tone · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(gen_tone)' && echo commit在案 → commit在案 (10-11)
### gen_sweep
- [x] gen_sweep · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:gen_sweep' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] gen_sweep · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/synthesize_style/test_gen_sweep.py | tail -1 → 29 passed in 0.07s (10-11)
- [x] gen_sweep · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b7.py | grep -q '探针全过' && echo 签名探针过（顶层 B8 装配后复检调用点） → 签名探针过（顶层 B8 装配后复检调用点） (10-11)
- [x] gen_sweep · 清单进位 — 证据: bash -c grep -q '| gen_sweep | B7 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] gen_sweep · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(gen_sweep)' && echo commit在案 → commit在案 (10-11)
### gen_chirp
- [x] gen_chirp · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:gen_chirp' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] gen_chirp · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/synthesize_style/test_gen_chirp.py | tail -1 → 33 passed in 0.07s (10-11)
- [x] gen_chirp · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b7.py | grep -q '探针全过' && echo 签名探针过（顶层 B8 装配后复检调用点） → 签名探针过（顶层 B8 装配后复检调用点） (10-11)
- [x] gen_chirp · 清单进位 — 证据: bash -c grep -q '| gen_chirp | B7 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] gen_chirp · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(gen_chirp)' && echo commit在案 → commit在案 (10-11)
### gen_bandlimited_noise
- [x] gen_bandlimited_noise · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:gen_bandlimited_noise' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] gen_bandlimited_noise · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/synthesize_style/test_gen_bandlimited_noise.py | tail -1 → 58 passed in 0.12s (10-11)
- [x] gen_bandlimited_noise · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b7.py | grep -q '探针全过' && echo 签名探针过（顶层 B8 装配后复检调用点） → 签名探针过（顶层 B8 装配后复检调用点） (10-11)
- [x] gen_bandlimited_noise · 清单进位 — 证据: bash -c grep -q '| gen_bandlimited_noise | B7 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] gen_bandlimited_noise · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(gen_bandlimited_noise)' && echo commit在案 → commit在案 (10-11)
### gen_partial_band
- [x] gen_partial_band · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:gen_partial_band' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] gen_partial_band · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/synthesize_style/test_gen_partial_band.py | tail -1 → 66 passed in 0.12s (10-11)
- [x] gen_partial_band · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b7.py | grep -q '探针全过' && echo 签名探针过（顶层 B8 装配后复检调用点） → 签名探针过（顶层 B8 装配后复检调用点） (10-11)
- [x] gen_partial_band · 清单进位 — 证据: bash -c grep -q '| gen_partial_band | B7 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] gen_partial_band · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(gen_partial_band)' && echo commit在案 → commit在案 (10-11)
### gen_pulse
- [x] gen_pulse · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:gen_pulse' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] gen_pulse · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/synthesize_style/test_gen_pulse.py | tail -1 → 64 passed in 0.08s (10-11)
- [x] gen_pulse · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b7.py | grep -q '探针全过' && echo 签名探针过（顶层 B8 装配后复检调用点） → 签名探针过（顶层 B8 装配后复检调用点） (10-11)
- [x] gen_pulse · 清单进位 — 证据: bash -c grep -q '| gen_pulse | B7 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] gen_pulse · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(gen_pulse)' && echo commit在案 → commit在案 (10-11)
### compose_jamming
- [x] compose_jamming · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:compose_jamming' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] compose_jamming · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/synthesize_style/test_compose_jamming.py | tail -1 → 34 passed in 0.10s (10-11)
- [x] compose_jamming · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b7.py | grep -q '探针全过' && echo 签名探针过（顶层 B8 装配后复检调用点） → 签名探针过（顶层 B8 装配后复检调用点） (10-11)
- [x] compose_jamming · 清单进位 — 证据: bash -c grep -q '| compose_jamming | B7 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] compose_jamming · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(compose_jamming)' && echo commit在案 → commit在案 (10-11)

## B7 批间门
- [x] B7 · 评审三轴 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && grep -q 'Ruling: B7 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && echo 三轴过门+Ruling⑪在案 → 三轴过门+Ruling⑪在案 (10-11)
- [x] B7 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b7.py | grep -q 探针全过 && echo B7 双审收口（12 项修复+探针新口径过） → B7 双审收口（12 项修复+探针新口径过） (10-11)

## B8 — append_event, synthesize_style, lookup_style_recipe, switch_style, plan_attenuator_combo, set_channel_attenuation
### append_event
- [x] append_event · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:append_event' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] append_event · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/shared/test_append_event.py | tail -1 → 21 passed in 0.03s (10-11)
- [x] append_event · wired — 证据: bash -c grep -rn 'append_event(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/set_channel_attenuation/set_channel_attenuation.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] append_event · 清单进位 — 证据: bash -c grep -q '| append_event | B8 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] append_event · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(append_event)' && echo commit在案 → commit在案 (10-11)
### synthesize_style
- [x] synthesize_style · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:synthesize_style' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] synthesize_style · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k styles_synth -q | tail -1 → 23 passed, 1291 deselected in 1.31s (10-11)
- [x] synthesize_style · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b8.py | grep -q '谱峰对' && echo 顶层实跑通过（六样式装配） → 顶层实跑通过（六样式装配） (10-11)
- [x] synthesize_style · 清单进位 — 证据: bash -c grep -q '| synthesize_style | B8 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] synthesize_style · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(synthesize_style)' && echo commit在案 → commit在案 (10-11)
### lookup_style_recipe
- [x] lookup_style_recipe · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:lookup_style_recipe' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] lookup_style_recipe · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/switch_style/test_lookup_style_recipe.py | tail -1 → 14 passed in 0.08s (10-11)
- [x] lookup_style_recipe · wired — 证据: bash -c grep -rn 'lookup_style_recipe(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/synthesize_style/synthesize_style.py /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/switch_style/switch_style.py | head -2 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] lookup_style_recipe · 清单进位 — 证据: bash -c grep -q '| lookup_style_recipe | B8 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] lookup_style_recipe · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(lookup_style_recipe)' && echo commit在案 → commit在案 (10-11)
### switch_style
- [x] switch_style · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:switch_style' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] switch_style · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k styles_switch -q | tail -1 → 15 passed, 1299 deselected in 1.32s (10-11)
- [x] switch_style · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b8.py >/dev/null 2>&1; python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b8.py 2>/dev/null | grep -q '切换 bandlimited_noise' && echo 顶层实跑通过 → 顶层实跑通过 (10-11)
- [x] switch_style · 清单进位 — 证据: bash -c grep -q '| switch_style | B8 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] switch_style · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(switch_style)' && echo commit在案 → commit在案 (10-11)
### plan_attenuator_combo
- [x] plan_attenuator_combo · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:plan_attenuator_combo' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] plan_attenuator_combo · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/set_channel_attenuation/test_plan_attenuator_combo.py | tail -1 → 39 passed in 0.02s (10-11)
- [x] plan_attenuator_combo · wired — 证据: bash -c grep -rn 'plan_attenuator_combo(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/set_channel_attenuation/set_channel_attenuation.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-11)
- [x] plan_attenuator_combo · 清单进位 — 证据: bash -c grep -q '| plan_attenuator_combo | B8 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] plan_attenuator_combo · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(plan_attenuator_combo)' && echo commit在案 → commit在案 (10-11)
### set_channel_attenuation
- [x] set_channel_attenuation · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:set_channel_attenuation' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-11)
- [x] set_channel_attenuation · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k channel_ladder -q 2>&1 | tail -1 → 15 passed, 1299 deselected in 1.31s (10-11)
- [x] set_channel_attenuation · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b8.py 2>/dev/null | grep -q '衰减下发' && echo 顶层实跑通过 → 顶层实跑通过 (10-11)
- [x] set_channel_attenuation · 清单进位 — 证据: bash -c grep -q '| set_channel_attenuation | B8 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-11)
- [x] set_channel_attenuation · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(set_channel_attenuation)' && echo commit在案 → commit在案 (10-11)

## B8 批间门
- [x] B8 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B8 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 1340 passed in 11.13s (10-11)
- [x] B8 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && echo B8 双审收口（6 项修复） → B8 双审收口（6 项修复） (10-11)

## B9 — plan_ladder_steps, run_power_ladder, compute_pathloss, map_distance_to_loss
### plan_ladder_steps
- [x] plan_ladder_steps · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:plan_ladder_steps' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] plan_ladder_steps · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/run_power_ladder/test_plan_ladder_steps.py | tail -1 → 36 passed in 0.02s (10-12)
- [x] plan_ladder_steps · wired — 证据: bash -c grep -rn 'plan_ladder_steps(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/run_power_ladder/run_power_ladder.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] plan_ladder_steps · 清单进位 — 证据: bash -c grep -q '| plan_ladder_steps | B9 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] plan_ladder_steps · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(plan_ladder_steps)' && echo commit在案 → commit在案 (10-12)
### run_power_ladder
- [x] run_power_ladder · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:run_power_ladder' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] run_power_ladder · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k power_ladder -q 2>&1 | tail -1 → 56 passed, 1438 deselected in 1.34s (10-12)
- [x] run_power_ladder · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b9.py | grep -q '停发射在末位=True' && echo 顶层实跑通过（失效即停先停发射） → 顶层实跑通过（失效即停先停发射） (10-12)
- [x] run_power_ladder · 清单进位 — 证据: bash -c grep -q '| run_power_ladder | B9 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] run_power_ladder · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(run_power_ladder)' && echo commit在案 → commit在案 (10-12)
### compute_pathloss
- [x] compute_pathloss · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:compute_pathloss' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] compute_pathloss · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/map_distance_to_loss/test_compute_pathloss.py | tail -1 → 60 passed in 0.03s (10-12)
- [x] compute_pathloss · wired — 证据: bash -c grep -rn 'compute_pathloss(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/map_distance_to_loss/map_distance_to_loss.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] compute_pathloss · 清单进位 — 证据: bash -c grep -q '| compute_pathloss | B9 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] compute_pathloss · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(compute_pathloss)' && echo commit在案 → commit在案 (10-12)
### map_distance_to_loss
- [x] map_distance_to_loss · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:map_distance_to_loss' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] map_distance_to_loss · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k pathloss_map -q 2>&1 | tail -1 → 40 passed, 1454 deselected in 1.29s (10-12)
- [x] map_distance_to_loss · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b9.py | grep -q '30→50dB' && echo 顶层实跑通过（距离→损耗→组合） → 顶层实跑通过（距离→损耗→组合） (10-12)
- [x] map_distance_to_loss · 清单进位 — 证据: bash -c grep -q '| map_distance_to_loss | B9 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] map_distance_to_loss · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(map_distance_to_loss)' && echo commit在案 → commit在案 (10-12)

## B9 批间门
- [x] B9 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B9 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 1505 passed in 11.22s (10-12)
- [x] B9 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b9.py | grep -q '停发射在末位=True' && echo B9 双审收口（5 项修复） → B9 双审收口（5 项修复） (10-12)

## B10 — enforce_bandwidth_limit, capture_monitor_spectrum, estimate_snr, check_flatness, compute_spectrum_stats
### enforce_bandwidth_limit
- [x] enforce_bandwidth_limit · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:enforce_bandwidth_limit' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] enforce_bandwidth_limit · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/capture_monitor_spectrum/test_enforce_bandwidth_limit.py | tail -1 → 34 passed in 0.02s (10-12)
- [x] enforce_bandwidth_limit · wired — 证据: bash -c grep -rn 'enforce_bandwidth_limit(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/capture_monitor_spectrum/capture_monitor_spectrum.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] enforce_bandwidth_limit · 清单进位 — 证据: bash -c grep -q '| enforce_bandwidth_limit | B10 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] enforce_bandwidth_limit · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(enforce_bandwidth_limit)' && echo commit在案 → commit在案 (10-12)
### capture_monitor_spectrum
- [x] capture_monitor_spectrum · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:capture_monitor_spectrum' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] capture_monitor_spectrum · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k monitor_capture -q 2>&1 | tail -1 → 16 passed, 1615 deselected in 1.35s (10-12)
- [x] capture_monitor_spectrum · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b10.py | grep -q '2438.1MHz' && echo 顶层实跑通过（谱峰定位） → 顶层实跑通过（谱峰定位） (10-12)
- [x] capture_monitor_spectrum · 清单进位 — 证据: bash -c grep -q '| capture_monitor_spectrum | B10 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] capture_monitor_spectrum · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(capture_monitor_spectrum)' && echo commit在案 → commit在案 (10-12)
### estimate_snr
- [x] estimate_snr · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:estimate_snr' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] estimate_snr · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/compute_spectrum_stats/test_estimate_snr.py | tail -1 → 31 passed in 0.02s (10-12)
- [x] estimate_snr · wired — 证据: bash -c grep -rn 'estimate_snr(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/compute_spectrum_stats/compute_spectrum_stats.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] estimate_snr · 清单进位 — 证据: bash -c grep -q '| estimate_snr | B10 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] estimate_snr · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(estimate_snr)' && echo commit在案 → commit在案 (10-12)
### check_flatness
- [x] check_flatness · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:check_flatness' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] check_flatness · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/compute_spectrum_stats/test_check_flatness.py | tail -1 → 26 passed in 0.02s (10-12)
- [x] check_flatness · wired — 证据: bash -c grep -rn 'check_flatness(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/compute_spectrum_stats/compute_spectrum_stats.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] check_flatness · 清单进位 — 证据: bash -c grep -q '| check_flatness | B10 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] check_flatness · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(check_flatness)' && echo commit在案 → commit在案 (10-12)
### compute_spectrum_stats
- [x] compute_spectrum_stats · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:compute_spectrum_stats' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] compute_spectrum_stats · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k spectrum_stats -q 2>&1 | tail -1 → 73 passed, 1558 deselected in 1.33s (10-12)
- [x] compute_spectrum_stats · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b10.py | grep -q 'SNR=19.0dB' && echo 顶层实跑通过（统计行 full 模式） → 顶层实跑通过（统计行 full 模式） (10-12)
- [x] compute_spectrum_stats · 清单进位 — 证据: bash -c grep -q '| compute_spectrum_stats | B10 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] compute_spectrum_stats · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(compute_spectrum_stats)' && echo commit在案 → commit在案 (10-12)

## B10 批间门
- [x] B10 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B10 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 1642 passed in 11.26s (10-12)
- [x] B10 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b10.py | grep -q 'SNR=19' && echo B10 双审收口（6 项修复） → B10 双审收口（6 项修复） (10-12)

## B11 — parse_esp32_frame, drive_esp32_link, parse_nrf24_frame, drive_nrf24_link, apply_cliff_model, simulate_link_degradation, compute_per, normalize_kpi
### parse_esp32_frame
- [x] parse_esp32_frame · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:parse_esp32_frame' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] parse_esp32_frame · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/drive_esp32_link/test_parse_esp32_frame.py | tail -1 → 34 passed in 0.02s (10-12)
- [x] parse_esp32_frame · wired — 证据: bash -c grep -rn 'parse_esp32_frame(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/drive_esp32_link/drive_esp32_link.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] parse_esp32_frame · 清单进位 — 证据: bash -c grep -q '| parse_esp32_frame | B11 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] parse_esp32_frame · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(parse_esp32_frame)' && echo commit在案 → commit在案 (10-12)
### drive_esp32_link
- [x] drive_esp32_link · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:drive_esp32_link' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] drive_esp32_link · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k dut_esp32 -q 2>&1 | tail -1 → 17 passed, 1775 deselected in 1.34s (10-12)
- [x] drive_esp32_link · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b11.py | grep -q 'esp per=0.20' && echo 顶层实跑通过（lines 注入流） → 顶层实跑通过（lines 注入流） (10-12)
- [x] drive_esp32_link · 清单进位 — 证据: bash -c grep -q '| drive_esp32_link | B11 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] drive_esp32_link · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(drive_esp32_link)' && echo commit在案 → commit在案 (10-12)
### parse_nrf24_frame
- [x] parse_nrf24_frame · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:parse_nrf24_frame' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] parse_nrf24_frame · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/drive_nrf24_link/test_parse_nrf24_frame.py | tail -1 → 13 passed in 0.01s (10-12)
- [x] parse_nrf24_frame · wired — 证据: bash -c grep -rn 'parse_nrf24_frame(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/drive_nrf24_link/drive_nrf24_link.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] parse_nrf24_frame · 清单进位 — 证据: bash -c grep -q '| parse_nrf24_frame | B11 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] parse_nrf24_frame · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(parse_nrf24_frame)' && echo commit在案 → commit在案 (10-12)
### drive_nrf24_link
- [x] drive_nrf24_link · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:drive_nrf24_link' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] drive_nrf24_link · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k dut_nrf24 -q 2>&1 | tail -1 → 15 passed, 1777 deselected in 1.30s (10-12)
- [x] drive_nrf24_link · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b11.py | grep -q 'nrf per=0.45' && echo 顶层实跑通过（无 rssi 口径） → 顶层实跑通过（无 rssi 口径） (10-12)
- [x] drive_nrf24_link · 清单进位 — 证据: bash -c grep -q '| drive_nrf24_link | B11 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] drive_nrf24_link · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(drive_nrf24_link)' && echo commit在案 → commit在案 (10-12)
### apply_cliff_model
- [x] apply_cliff_model · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:apply_cliff_model' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] apply_cliff_model · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/simulate_link_degradation/test_apply_cliff_model.py | tail -1 → 23 passed in 0.02s (10-12)
- [x] apply_cliff_model · wired — 证据: bash -c grep -rn 'apply_cliff_model(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/simulate_link_degradation/simulate_link_degradation.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] apply_cliff_model · 清单进位 — 证据: bash -c grep -q '| apply_cliff_model | B11 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] apply_cliff_model · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(apply_cliff_model)' && echo commit在案 → commit在案 (10-12)
### simulate_link_degradation
- [x] simulate_link_degradation · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:simulate_link_degradation' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] simulate_link_degradation · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k dut_sim -q 2>&1 | tail -1 → 13 passed, 1779 deselected in 1.33s (10-12)
- [x] simulate_link_degradation · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b11.py | grep -q '0.000→0.900' && echo 顶层实跑通过（PER 随 JSR 悬崖） → 顶层实跑通过（PER 随 JSR 悬崖） (10-12)
- [x] simulate_link_degradation · 清单进位 — 证据: bash -c grep -q '| simulate_link_degradation | B11 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] simulate_link_degradation · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(simulate_link_degradation)' && echo commit在案 → commit在案 (10-12)
### compute_per
- [x] compute_per · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:compute_per' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] compute_per · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/normalize_kpi/test_compute_per.py | tail -1 → 17 passed in 0.01s (10-12)
- [x] compute_per · wired — 证据: bash -c grep -rn 'compute_per(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/normalize_kpi/normalize_kpi.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] compute_per · 清单进位 — 证据: bash -c grep -q '| compute_per | B11 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] compute_per · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(compute_per)' && echo commit在案 → commit在案 (10-12)
### normalize_kpi
- [x] normalize_kpi · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:normalize_kpi' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] normalize_kpi · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k kpi_model -q 2>&1 | tail -1 → 20 passed, 1772 deselected in 1.33s (10-12)
- [x] normalize_kpi · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b11.py | grep -q '三源贯通' && echo 顶层实跑通过（三源归一） → 顶层实跑通过（三源归一） (10-12)
- [x] normalize_kpi · 清单进位 — 证据: bash -c grep -q '| normalize_kpi | B11 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] normalize_kpi · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(normalize_kpi)' && echo commit在案 → commit在案 (10-12)

## B11 批间门
- [x] B11 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B11 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 1825 passed in 11.27s (10-12)
- [x] B11 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b11.py | grep -q '三源贯通' && echo B11 双审收口（8 项修复+探针新口径过） → B11 双审收口（8 项修复+探针新口径过） (10-12)

## B12 — compute_alignment_error, record_run_streams, run_baseline_check, annotate_truth_labels, write_sigmf_recording
### compute_alignment_error
- [x] compute_alignment_error · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:compute_alignment_error' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] compute_alignment_error · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/record_run_streams/test_compute_alignment_error.py | tail -1 → 28 passed in 0.02s (10-12)
- [x] compute_alignment_error · wired — 证据: bash -c grep -rn 'compute_alignment_error(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/record_run_streams/record_run_streams.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] compute_alignment_error · 清单进位 — 证据: bash -c grep -q '| compute_alignment_error | B12 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] compute_alignment_error · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(compute_alignment_error)' && echo commit在案 → commit在案 (10-12)
### record_run_streams
- [x] record_run_streams · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:record_run_streams' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] record_run_streams · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k align_streams -q 2>&1 | tail -1 → 15 passed, 1902 deselected in 1.44s (10-12)
- [x] record_run_streams · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b12.py | grep -q '准闭环' && echo 顶层实跑通过（三路合流+录制+对齐） → 顶层实跑通过（三路合流+录制+对齐） (10-12)
- [x] record_run_streams · 清单进位 — 证据: bash -c grep -q '| record_run_streams | B12 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] record_run_streams · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(record_run_streams)' && echo commit在案 → commit在案 (10-12)
### run_baseline_check
- [x] run_baseline_check · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:run_baseline_check' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] run_baseline_check · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k baseline_guard -q 2>&1 | tail -1 → 16 passed, 1901 deselected in 1.44s (10-12)
- [x] run_baseline_check · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b12.py | grep -q '基线过=True' && echo 顶层实跑通过（放行路径） → 顶层实跑通过（放行路径） (10-12)
- [x] run_baseline_check · 清单进位 — 证据: bash -c grep -q '| run_baseline_check | B12 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] run_baseline_check · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(run_baseline_check)' && echo commit在案 → commit在案 (10-12)
### annotate_truth_labels
- [x] annotate_truth_labels · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:annotate_truth_labels' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] annotate_truth_labels · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/write_sigmf_recording/test_annotate_truth_labels.py | tail -1 → 21 passed in 0.06s (10-12)
- [x] annotate_truth_labels · wired — 证据: bash -c grep -rn 'annotate_truth_labels(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/write_sigmf_recording/write_sigmf_recording.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] annotate_truth_labels · 清单进位 — 证据: bash -c grep -q '| annotate_truth_labels | B12 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] annotate_truth_labels · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(annotate_truth_labels)' && echo commit在案 → commit在案 (10-12)
### write_sigmf_recording
- [x] write_sigmf_recording · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:write_sigmf_recording' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] write_sigmf_recording · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k sigmf_record -q 2>&1 | tail -1 → 34 passed, 1883 deselected in 1.40s (10-12)
- [x] write_sigmf_recording · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b12.py | grep -q 'SigMF=192' && echo 顶层实跑通过（cf32 往返） → 顶层实跑通过（cf32 往返） (10-12)
- [x] write_sigmf_recording · 清单进位 — 证据: bash -c grep -q '| write_sigmf_recording | B12 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] write_sigmf_recording · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(write_sigmf_recording)' && echo commit在案 → commit在案 (10-12)

## B12 批间门
- [x] B12 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B12 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 1930 passed in 11.69s (10-12)
- [x] B12 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && echo B12 双审收口（6 项修复） → B12 双审收口（6 项修复） (10-12)

## B13 — check_failure, record_failure_level, execute_gb42590_protocol, compare_failure_boundaries, build_curve_frames, plot_triple_curves
### check_failure
- [x] check_failure · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:check_failure' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] check_failure · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/execute_gb42590_protocol/test_check_failure.py | tail -1 → 18 passed in 0.01s (10-12)
- [x] check_failure · wired — 证据: bash -c grep -rn 'check_failure(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/execute_gb42590_protocol/execute_gb42590_protocol.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] check_failure · 清单进位 — 证据: bash -c grep -q '| check_failure | B13 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] check_failure · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(check_failure)' && echo commit在案 → commit在案 (10-12)
### record_failure_level
- [x] record_failure_level · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:record_failure_level' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] record_failure_level · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/execute_gb42590_protocol/test_record_failure_level.py | tail -1 → 11 passed in 0.01s (10-12)
- [x] record_failure_level · wired — 证据: bash -c grep -rn 'record_failure_level(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/execute_gb42590_protocol/execute_gb42590_protocol.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] record_failure_level · 清单进位 — 证据: bash -c grep -q '| record_failure_level | B13 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] record_failure_level · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(record_failure_level)' && echo commit在案 → commit在案 (10-12)
### execute_gb42590_protocol
- [x] execute_gb42590_protocol · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:execute_gb42590_protocol' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] execute_gb42590_protocol · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k gb42590_executor -q 2>&1 | tail -1 → 13 passed, 2007 deselected in 1.90s (10-12)
- [x] execute_gb42590_protocol · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b13.py | grep -q 'GB failed' && echo 顶层实跑通过（全链 failed+P_crit） → 顶层实跑通过（全链 failed+P_crit） (10-12)
- [x] execute_gb42590_protocol · 清单进位 — 证据: bash -c grep -q '| execute_gb42590_protocol | B13 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] execute_gb42590_protocol · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(execute_gb42590_protocol)' && echo commit在案 → commit在案 (10-12)
### compare_failure_boundaries
- [x] compare_failure_boundaries · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:compare_failure_boundaries' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] compare_failure_boundaries · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k boundary_compare -q 2>&1 | tail -1 → 12 passed, 2008 deselected in 1.37s (10-12)
- [x] compare_failure_boundaries · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b13.py | grep -q 'weakest=' && echo 顶层实跑通过（跨样式定位） → 顶层实跑通过（跨样式定位） (10-12)
- [x] compare_failure_boundaries · 清单进位 — 证据: bash -c grep -q '| compare_failure_boundaries | B13 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] compare_failure_boundaries · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(compare_failure_boundaries)' && echo commit在案 → commit在案 (10-12)
### build_curve_frames
- [x] build_curve_frames · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:build_curve_frames' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] build_curve_frames · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/plot_triple_curves/test_build_curve_frames.py | tail -1 → 24 passed in 0.02s (10-12)
- [x] build_curve_frames · wired — 证据: bash -c grep -rn 'build_curve_frames(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/plot_triple_curves/plot_triple_curves.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] build_curve_frames · 清单进位 — 证据: bash -c grep -q '| build_curve_frames | B13 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] build_curve_frames · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(build_curve_frames)' && echo commit在案 → commit在案 (10-12)
### plot_triple_curves
- [x] plot_triple_curves · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:plot_triple_curves' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] plot_triple_curves · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k triple_curves -q 2>&1 | tail -1 → 36 passed, 1984 deselected in 3.01s (10-12)
- [x] plot_triple_curves · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b13.py | grep -q '三 PNG 齐' && echo 顶层实跑通过（三图+中文 cjk） → 顶层实跑通过（三图+中文 cjk） (10-12)
- [x] plot_triple_curves · 清单进位 — 证据: bash -c grep -q '| plot_triple_curves | B13 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] plot_triple_curves · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(plot_triple_curves)' && echo commit在案 → commit在案 (10-12)

## B13 批间门
- [x] B13 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B13 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 2030 passed in 14.54s (10-12)
- [x] B13 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b13.py | grep -q 'GB failed' && echo B13 双审收口（6 项修复） → B13 双审收口（6 项修复） (10-12)

## B14 — dispatch_remote_training, train_classifier, make_group_splits, grouped_cv_evaluate, predict_style
### dispatch_remote_training
- [x] dispatch_remote_training · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:dispatch_remote_training' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] dispatch_remote_training · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/train_classifier/test_dispatch_remote_training.py | tail -1 → 19 passed in 0.03s (10-12)
- [x] dispatch_remote_training · wired — 证据: bash -c grep -rn 'dispatch_remote_training(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/train_classifier/train_classifier.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] dispatch_remote_training · 清单进位 — 证据: bash -c grep -q '| dispatch_remote_training | B14 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] dispatch_remote_training · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(dispatch_remote_training)' && echo commit在案 → commit在案 (10-12)
### train_classifier
- [x] train_classifier · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:train_classifier' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] train_classifier · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k train_classifier -q 2>&1 | tail -1 → 34 passed, 2084 deselected in 1.49s (10-12)
- [x] train_classifier · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b14.py | grep -q '训练 48 样本两类' && echo 顶层实跑通过（local 训练落盘） → 顶层实跑通过（local 训练落盘） (10-12)
- [x] train_classifier · 清单进位 — 证据: bash -c grep -q '| train_classifier | B14 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] train_classifier · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(train_classifier)' && echo commit在案 → commit在案 (10-12)
### make_group_splits
- [x] make_group_splits · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:make_group_splits' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] make_group_splits · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/grouped_cv_evaluate/test_make_group_splits.py | tail -1 → 20 passed in 0.02s (10-12)
- [x] make_group_splits · wired — 证据: bash -c grep -rn 'make_group_splits(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/grouped_cv_evaluate/grouped_cv_evaluate.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] make_group_splits · 清单进位 — 证据: bash -c grep -q '| make_group_splits | B14 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] make_group_splits · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(make_group_splits)' && echo commit在案 → commit在案 (10-12)
### grouped_cv_evaluate
- [x] grouped_cv_evaluate · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:grouped_cv_evaluate' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] grouped_cv_evaluate · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k grouped_cv -q 2>&1 | tail -1 → 40 passed, 2078 deselected in 1.40s (10-12)
- [x] grouped_cv_evaluate · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b14.py | grep -q 'F1=1.00' && echo 顶层实跑通过（分组 F1+泄漏自检） → 顶层实跑通过（分组 F1+泄漏自检） (10-12)
- [x] grouped_cv_evaluate · 清单进位 — 证据: bash -c grep -q '| grouped_cv_evaluate | B14 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] grouped_cv_evaluate · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(grouped_cv_evaluate)' && echo commit在案 → commit在案 (10-12)
### predict_style
- [x] predict_style · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:predict_style' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] predict_style · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k infer_service -q 2>&1 | tail -1 → 17 passed, 2101 deselected in 1.39s (10-12)
- [x] predict_style · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b14.py | grep -q 'label=tone' && echo 顶层实跑通过（识别 tone conf 0.94） → 顶层实跑通过（识别 tone conf 0.94） (10-12)
- [x] predict_style · 清单进位 — 证据: bash -c grep -q '| predict_style | B14 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] predict_style · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(predict_style)' && echo commit在案 → commit在案 (10-12)

## B14 批间门
- [x] B14 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B14 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 2136 passed in 13.92s (10-12)
- [x] B14 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b14.py | grep -q 'F1=1.00' && echo B14 双审收口（5 修 1 申报） → B14 双审收口（5 修 1 申报） (10-12)

## B15 — open_sim_siggen, open_sim_analyzer, upconvert_with_image_rejection, open_sim_mixer, open_sim_emi_receiver, open_sim_attenuator
### open_sim_siggen
- [x] open_sim_siggen · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:open_sim_siggen' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] open_sim_siggen · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k sim_1433d -q 2>&1 | tail -1 → 15 passed, 2251 deselected in 1.37s (10-12)
- [x] open_sim_siggen · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b15.py | grep -q '1ppm 回读' && echo 顶层实跑通过（1ppm 口径） → 顶层实跑通过（1ppm 口径） (10-12)
- [x] open_sim_siggen · 清单进位 — 证据: bash -c grep -q '| open_sim_siggen | B15 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] open_sim_siggen · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(open_sim_siggen)' && echo commit在案 → commit在案 (10-12)
### open_sim_analyzer
- [x] open_sim_analyzer · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:open_sim_analyzer' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] open_sim_analyzer · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k sim_rsa513a -q 2>&1 | tail -1 → 13 passed, 2253 deselected in 1.41s (10-12)
- [x] open_sim_analyzer · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b15.py | grep -q '±1.5' && echo 顶层实跑通过（不确定度口径） → 顶层实跑通过（不确定度口径） (10-12)
- [x] open_sim_analyzer · 清单进位 — 证据: bash -c grep -q '| open_sim_analyzer | B15 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] open_sim_analyzer · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(open_sim_analyzer)' && echo commit在案 → commit在案 (10-12)
### upconvert_with_image_rejection
- [x] upconvert_with_image_rejection · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:upconvert_with_image_rejection' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] upconvert_with_image_rejection · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/open_sim_mixer/test_upconvert_with_image_rejection.py | tail -1 → 59 passed in 0.04s (10-12)
- [x] upconvert_with_image_rejection · wired — 证据: bash -c grep -rn 'upconvert_with_image_rejection(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/open_sim_mixer/open_sim_mixer.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] upconvert_with_image_rejection · 清单进位 — 证据: bash -c grep -q '| upconvert_with_image_rejection | B15 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] upconvert_with_image_rejection · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(upconvert_with_image_rejection)' && echo commit在案 → commit在案 (10-12)
### open_sim_mixer
- [x] open_sim_mixer · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:open_sim_mixer' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] open_sim_mixer · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k sim_mixer13g -q 2>&1 | tail -1 → 14 passed, 2252 deselected in 1.40s (10-12)
- [x] open_sim_mixer · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b15.py | grep -q 'RF=13.00GHz' && echo 顶层实跑通过（13G 全链） → 顶层实跑通过（13G 全链） (10-12)
- [x] open_sim_mixer · 清单进位 — 证据: bash -c grep -q '| open_sim_mixer | B15 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] open_sim_mixer · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(open_sim_mixer)' && echo commit在案 → commit在案 (10-12)
### open_sim_emi_receiver
- [x] open_sim_emi_receiver · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:open_sim_emi_receiver' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] open_sim_emi_receiver · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k sim_emi_receiver -q 2>&1 | tail -1 → 13 passed, 2253 deselected in 1.36s (10-12)
- [x] open_sim_emi_receiver · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b15.py | grep -q 'EMI 底噪' && echo 顶层实跑通过（-150dBm/Hz 口径） → 顶层实跑通过（-150dBm/Hz 口径） (10-12)
- [x] open_sim_emi_receiver · 清单进位 — 证据: bash -c grep -q '| open_sim_emi_receiver | B15 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] open_sim_emi_receiver · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(open_sim_emi_receiver)' && echo commit在案 → commit在案 (10-12)
### open_sim_attenuator
- [x] open_sim_attenuator · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:open_sim_attenuator' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] open_sim_attenuator · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k sim_attenuator -q 2>&1 | tail -1 → 20 passed, 2246 deselected in 1.39s (10-12)
- [x] open_sim_attenuator · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b15.py | grep -q '衰减 30dB' && echo 顶层实跑通过（真衰减数学） → 顶层实跑通过（真衰减数学） (10-12)
- [x] open_sim_attenuator · 清单进位 — 证据: bash -c grep -q '| open_sim_attenuator | B15 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] open_sim_attenuator · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(open_sim_attenuator)' && echo commit在案 → commit在案 (10-12)

## B15 批间门
- [x] B15 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B15 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 2275 passed in 14.19s (10-12)
- [x] B15 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b15.py | grep -q '五后端链' && echo B15 双审收口（8 项修复） → B15 双审收口（8 项修复） (10-12)

## B16 — make_disclaimer_block, run_emc_conduction_sim, run_emc_radiation_sim, plan_frequency_sweep, run_emc_sweep
### make_disclaimer_block
- [x] make_disclaimer_block · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:make_disclaimer_block' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] make_disclaimer_block · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/shared/test_make_disclaimer_block.py | tail -1 → 12 passed in 0.01s (10-12)
- [x] make_disclaimer_block · wired — 证据: bash -c grep -rn 'make_disclaimer_block(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src --include='*.py' | grep -v 'def make_disclaimer_block' | grep -v test | grep -v shared/ | head -3 && echo 三 EMC 流程+报告调用点存在 → 三 EMC 流程+报告调用点存在 (10-12)
- [x] make_disclaimer_block · 清单进位 — 证据: bash -c grep -q '| make_disclaimer_block | B16 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] make_disclaimer_block · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(make_disclaimer_block)' && echo commit在案 → commit在案 (10-12)
### run_emc_conduction_sim
- [x] run_emc_conduction_sim · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:run_emc_conduction_sim' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] run_emc_conduction_sim · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/run_emc_conduction_sim/test_run_emc_conduction_sim.py | tail -1 → 10 passed in 0.01s (10-12)
- [x] run_emc_conduction_sim · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b16.py | grep -q '传导 dbuv' && echo 顶层实跑通过（dbuv 换算+限值） → 顶层实跑通过（dbuv 换算+限值） (10-12)
- [x] run_emc_conduction_sim · 清单进位 — 证据: bash -c grep -q '| run_emc_conduction_sim | B16 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] run_emc_conduction_sim · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(run_emc_conduction_sim)' && echo commit在案 → commit在案 (10-12)
### run_emc_radiation_sim
- [x] run_emc_radiation_sim · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:run_emc_radiation_sim' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] run_emc_radiation_sim · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/run_emc_radiation_sim/test_run_emc_radiation_sim.py | tail -1 → 8 passed in 0.07s (10-12)
- [x] run_emc_radiation_sim · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b16.py | grep -q '辐射峰数' && echo 顶层实跑通过（谱+洁净度） → 顶层实跑通过（谱+洁净度） (10-12)
- [x] run_emc_radiation_sim · 清单进位 — 证据: bash -c grep -q '| run_emc_radiation_sim | B16 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] run_emc_radiation_sim · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(run_emc_radiation_sim)' && echo commit在案 → commit在案 (10-12)
### plan_frequency_sweep
- [x] plan_frequency_sweep · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:plan_frequency_sweep' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] plan_frequency_sweep · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/run_emc_sweep/test_plan_frequency_sweep.py | tail -1 → 27 passed in 0.02s (10-12)
- [x] plan_frequency_sweep · wired — 证据: bash -c grep -rn 'plan_frequency_sweep(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/run_emc_sweep/run_emc_sweep.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] plan_frequency_sweep · 清单进位 — 证据: bash -c grep -q '| plan_frequency_sweep | B16 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] plan_frequency_sweep · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(plan_frequency_sweep)' && echo commit在案 → commit在案 (10-12)
### run_emc_sweep
- [x] run_emc_sweep · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:run_emc_sweep' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] run_emc_sweep · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/run_emc_sweep/test_run_emc_sweep.py | tail -1 → 9 passed in 0.01s (10-12)
- [x] run_emc_sweep · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b16.py | grep -q '扫频 7 点' && echo 顶层实跑通过（点表+spurious） → 顶层实跑通过（点表+spurious） (10-12)
- [x] run_emc_sweep · 清单进位 — 证据: bash -c grep -q '| run_emc_sweep | B16 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] run_emc_sweep · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(run_emc_sweep)' && echo commit在案 → commit在案 (10-12)

## B16 批间门
- [x] B16 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B16 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 2362 passed in 14.30s (10-12)
- [x] B16 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b16.py | grep -q 'EMC 三流程' && echo B16 双审收口（7 项修复） → B16 双审收口（7 项修复） (10-12)

## B17 — locate_ledger_row, update_ledger, count_comment_ratio, audit_ledger, validate_scenario_schema, normalize_scenario, load_scenario
### locate_ledger_row
- [x] locate_ledger_row · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:locate_ledger_row' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] locate_ledger_row · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/update_ledger/test_locate_ledger_row.py | tail -1 → 19 passed in 0.05s (10-12)
- [x] locate_ledger_row · wired — 证据: bash -c grep -rn 'locate_ledger_row(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/update_ledger/update_ledger.py /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/audit_ledger/audit_ledger.py | head -2 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] locate_ledger_row · 清单进位 — 证据: bash -c grep -q '| locate_ledger_row | B17 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] locate_ledger_row · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(locate_ledger_row)' && echo commit在案 → commit在案 (10-12)
### update_ledger
- [x] update_ledger · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:update_ledger' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] update_ledger · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k ledger_update -q 2>&1 | tail -1 → 17 passed, 2450 deselected in 1.41s (10-12)
- [x] update_ledger · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b17.py | grep -q '写入往返' && echo 顶层实跑通过 → 顶层实跑通过 (10-12)
- [x] update_ledger · 清单进位 — 证据: bash -c grep -q '| update_ledger | B17 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] update_ledger · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(update_ledger)' && echo commit在案 → commit在案 (10-12)
### count_comment_ratio
- [x] count_comment_ratio · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:count_comment_ratio' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] count_comment_ratio · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/audit_ledger/test_count_comment_ratio.py | tail -1 → 14 passed in 0.09s (10-12)
- [x] count_comment_ratio · wired — 证据: bash -c grep -rn 'count_comment_ratio(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/audit_ledger/audit_ledger.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] count_comment_ratio · 清单进位 — 证据: bash -c grep -q 'count_comment_ratio | B17 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] count_comment_ratio · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(count_comment_ratio)' && echo commit在案 → commit在案 (10-12)
### audit_ledger
- [x] audit_ledger · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:audit_ledger' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] audit_ledger · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k ledger_audit -q 2>&1 | tail -1 → 12 passed, 2455 deselected in 1.64s (10-12)
- [x] audit_ledger · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b17.py | grep -q 'audit 100 条' && echo 顶层实跑通过（真清单） → 顶层实跑通过（真清单） (10-12)
- [x] audit_ledger · 清单进位 — 证据: bash -c grep -q '| audit_ledger | B17 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] audit_ledger · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(audit_ledger)' && echo commit在案 → commit在案 (10-12)
### validate_scenario_schema
- [x] validate_scenario_schema · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:validate_scenario_schema' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] validate_scenario_schema · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/load_scenario/test_validate_scenario_schema.py | tail -1 → 21 passed in 0.02s (10-12)
- [x] validate_scenario_schema · wired — 证据: bash -c grep -rn 'validate_scenario_schema(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/load_scenario/load_scenario.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] validate_scenario_schema · 清单进位 — 证据: bash -c grep -q '| validate_scenario_schema | B17 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] validate_scenario_schema · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(validate_scenario_schema)' && echo commit在案 → commit在案 (10-12)
### normalize_scenario
- [x] normalize_scenario · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:normalize_scenario' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] normalize_scenario · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/load_scenario/test_normalize_scenario.py | tail -1 → 9 passed in 0.01s (10-12)
- [x] normalize_scenario · wired — 证据: bash -c grep -rn 'normalize_scenario(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/load_scenario/load_scenario.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] normalize_scenario · 清单进位 — 证据: bash -c grep -q '| normalize_scenario | B17 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] normalize_scenario · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(normalize_scenario)' && echo commit在案 → commit在案 (10-12)
### load_scenario
- [x] load_scenario · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:load_scenario' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] load_scenario · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k scenario_validate -q 2>&1 | tail -1 → 16 passed, 2451 deselected in 1.37s (10-12)
- [x] load_scenario · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b17.py | grep -q '场景装载' && echo 顶层实跑通过（红线联动） → 顶层实跑通过（红线联动） (10-12)
- [x] load_scenario · 清单进位 — 证据: bash -c grep -q '| load_scenario | B17 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] load_scenario · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(load_scenario)' && echo commit在案 → commit在案 (10-12)

## B17 批间门
- [x] B17 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B17 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 2491 passed in 14.55s (10-12)
- [x] B17 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b17.py | grep -q '台账+场景' && echo B17 双审收口（修7申报2） → B17 双审收口（修7申报2） (10-12)

## B18 — render_disclaimer_sections, assemble_frequency_plots, build_report, extract_report_numbers, verify_report_traceability
### render_disclaimer_sections
- [x] render_disclaimer_sections · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:render_disclaimer_sections' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] render_disclaimer_sections · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/build_report/test_render_disclaimer_sections.py | tail -1 → 16 passed in 0.01s (10-12)
- [x] render_disclaimer_sections · wired — 证据: bash -c grep -rn 'render_disclaimer_sections(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/build_report/build_report.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] render_disclaimer_sections · 清单进位 — 证据: bash -c grep -q '| render_disclaimer_sections | B18 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] render_disclaimer_sections · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(render_disclaimer_sections)' && echo commit在案 → commit在案 (10-12)
### assemble_frequency_plots
- [x] assemble_frequency_plots · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:assemble_frequency_plots' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] assemble_frequency_plots · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/build_report/test_assemble_frequency_plots.py | tail -1 → 13 passed in 0.02s (10-12)
- [x] assemble_frequency_plots · wired — 证据: bash -c grep -rn 'assemble_frequency_plots(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/build_report/build_report.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] assemble_frequency_plots · 清单进位 — 证据: bash -c grep -q '| assemble_frequency_plots | B18 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] assemble_frequency_plots · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(assemble_frequency_plots)' && echo commit在案 → commit在案 (10-12)
### build_report
- [x] build_report · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:build_report' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] build_report · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k report_builder -q 2>&1 | tail -1 → 17 passed, 2559 deselected in 3.87s (10-12)
- [x] build_report · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b18.py | grep -q '各节齐' && echo 顶层实跑通过（报告总装） → 顶层实跑通过（报告总装） (10-12)
- [x] build_report · 清单进位 — 证据: bash -c grep -q '| build_report | B18 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] build_report · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(build_report)' && echo commit在案 → commit在案 (10-12)
### extract_report_numbers
- [x] extract_report_numbers · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:extract_report_numbers' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] extract_report_numbers · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/verify_report_traceability/test_extract_report_numbers.py | tail -1 → 24 passed in 0.02s (10-12)
- [x] extract_report_numbers · wired — 证据: bash -c grep -rn 'extract_report_numbers(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/verify_report_traceability/verify_report_traceability.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] extract_report_numbers · 清单进位 — 证据: bash -c grep -q '| extract_report_numbers | B18 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] extract_report_numbers · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(extract_report_numbers)' && echo commit在案 → commit在案 (10-12)
### verify_report_traceability
- [x] verify_report_traceability · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:verify_report_traceability' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] verify_report_traceability · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k report_traceability -q 2>&1 | tail -1 → 41 passed, 2535 deselected in 1.90s (10-12)
- [x] verify_report_traceability · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b18.py | grep -q 'passed=True' && echo 顶层实跑通过（溯源闭环） → 顶层实跑通过（溯源闭环） (10-12)
- [x] verify_report_traceability · 清单进位 — 证据: bash -c grep -q '| verify_report_traceability | B18 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] verify_report_traceability · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(verify_report_traceability)' && echo commit在案 → commit在案 (10-12)

## B18 批间门
- [x] B18 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B18 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 2604 passed in 18.02s (10-12)
- [x] B18 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b18.py | grep -q 'passed=True' && echo B18 双审收口（修13申报3） → B18 双审收口（修13申报3） (10-12)

## B19 — create_console_app, serve_console, build_scenario_cards, render_console_pages, measure_refresh_latency, trigger_emergency_stop, push_realtime_kpi
### create_console_app
- [x] create_console_app · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:create_console_app' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] create_console_app · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/serve_console/test_create_console_app.py | tail -1 → 25 passed, 1 warning in 0.22s (10-12)
- [x] create_console_app · wired — 证据: bash -c grep -rn 'create_console_app(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/serve_console/serve_console.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] create_console_app · 清单进位 — 证据: bash -c grep -q '| create_console_app | B19 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] create_console_app · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(create_console_app)' && echo commit在案 → commit在案 (10-12)
### serve_console
- [x] serve_console · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:serve_console' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] serve_console · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/serve_console/test_serve_console.py | tail -1 → 25 passed, 1 warning in 0.22s (10-12)
- [x] serve_console · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b19.py | grep -q 'dry_run 服务' && echo 顶层实跑通过（dry_run+TestClient） → 顶层实跑通过（dry_run+TestClient） (10-12)
- [x] serve_console · 清单进位 — 证据: bash -c grep -q '| serve_console | B19 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] serve_console · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(serve_console)' && echo commit在案 → commit在案 (10-12)
### build_scenario_cards
- [x] build_scenario_cards · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:build_scenario_cards' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] build_scenario_cards · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/render_console_pages/test_build_scenario_cards.py | tail -1 → 12 passed in 0.04s (10-12)
- [x] build_scenario_cards · wired — 证据: bash -c grep -rn 'build_scenario_cards(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/render_console_pages/render_console_pages.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] build_scenario_cards · 清单进位 — 证据: bash -c grep -q '| build_scenario_cards | B19 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] build_scenario_cards · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(build_scenario_cards)' && echo commit在案 → commit在案 (10-12)
### render_console_pages
- [x] render_console_pages · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:render_console_pages' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] render_console_pages · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k console_ui -q 2>&1 | tail -1 → 15 passed, 2692 deselected, 1 warning in 1.63s (10-12)
- [x] render_console_pages · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b19.py | grep -q 'Vue CDN 页面落盘' && echo 顶层实跑通过（CDN 页+落盘） → 顶层实跑通过（CDN 页+落盘） (10-12)
- [x] render_console_pages · 清单进位 — 证据: bash -c grep -q '| render_console_pages | B19 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] render_console_pages · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(render_console_pages)' && echo commit在案 → commit在案 (10-12)
### measure_refresh_latency
- [x] measure_refresh_latency · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:measure_refresh_latency' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] measure_refresh_latency · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/push_realtime_kpi/test_measure_refresh_latency.py | tail -1 → 8 passed in 0.01s (10-12)
- [x] measure_refresh_latency · wired — 证据: bash -c grep -rn 'measure_refresh_latency(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/push_realtime_kpi/push_realtime_kpi.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] measure_refresh_latency · 清单进位 — 证据: bash -c grep -q '| measure_refresh_latency | B19 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] measure_refresh_latency · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(measure_refresh_latency)' && echo commit在案 → commit在案 (10-12)
### trigger_emergency_stop
- [x] trigger_emergency_stop · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:trigger_emergency_stop' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] trigger_emergency_stop · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/push_realtime_kpi/test_trigger_emergency_stop.py | tail -1 → 7 passed in 0.01s (10-12)
- [x] trigger_emergency_stop · wired — 证据: bash -c grep -rn 'trigger_emergency_stop(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/push_realtime_kpi/push_realtime_kpi.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] trigger_emergency_stop · 清单进位 — 证据: bash -c grep -q '| trigger_emergency_stop | B19 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] trigger_emergency_stop · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(trigger_emergency_stop)' && echo commit在案 → commit在案 (10-12)
### push_realtime_kpi
- [x] push_realtime_kpi · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:push_realtime_kpi' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] push_realtime_kpi · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k realtime_console -q 2>&1 | tail -1 → 14 passed, 2693 deselected, 1 warning in 1.63s (10-12)
- [x] push_realtime_kpi · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b19.py | grep -q '实时流 3 帧' && echo 顶层实跑通过（广播+latency） → 顶层实跑通过（广播+latency） (10-12)
- [x] push_realtime_kpi · 清单进位 — 证据: bash -c grep -q '| push_realtime_kpi | B19 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] push_realtime_kpi · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(push_realtime_kpi)' && echo commit在案 → commit在案 (10-12)

## B19 批间门
- [x] B19 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B19 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 -m pytest -k console_api -q | tail -1 → 26 passed, 2706 deselected, 1 warning in 1.65s (10-12)
- [x] B19 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b19.py | grep -q 'Web 探针' && echo B19 双审收口（9 项修复） → B19 双审收口（9 项修复） (10-12)

## B20 — map_per_to_injection, bridge_to_sitl, fallback_fixed_strategy, run_rl_policy, run_rff_pipeline
### map_per_to_injection
- [x] map_per_to_injection · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:map_per_to_injection' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] map_per_to_injection · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/bridge_to_sitl/ 2>&1 | grep -c passed → 1 (10-12)
- [x] map_per_to_injection · wired — 证据: bash -c grep -rn 'map_per_to_injection(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/bridge_to_sitl/bridge_to_sitl.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] map_per_to_injection · 清单进位 — 证据: bash -c grep -q '| map_per_to_injection | B20 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] map_per_to_injection · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(map_per_to_injection)' && echo commit在案 → commit在案 (10-12)
### bridge_to_sitl
- [x] bridge_to_sitl · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:bridge_to_sitl' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] bridge_to_sitl · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k sitl_bridge -q 2>&1 | tail -1 → 16 passed, 2749 deselected, 1 warning in 1.62s (10-12)
- [x] bridge_to_sitl · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b20.py | grep -q 'SITL 注入表' && echo 顶层实跑通过（dry_run 表） → 顶层实跑通过（dry_run 表） (10-12)
- [x] bridge_to_sitl · 清单进位 — 证据: bash -c grep -q '| bridge_to_sitl | B20 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] bridge_to_sitl · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(bridge_to_sitl)' && echo commit在案 → commit在案 (10-12)
### fallback_fixed_strategy
- [x] fallback_fixed_strategy · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:fallback_fixed_strategy' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] fallback_fixed_strategy · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/run_rl_policy/ 2>&1 | tail -1 → 13 passed in 0.08s (10-12)
- [x] fallback_fixed_strategy · wired — 证据: bash -c grep -rn 'fallback_fixed_strategy(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/run_rl_policy/run_rl_policy.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] fallback_fixed_strategy · 清单进位 — 证据: bash -c grep -q '| fallback_fixed_strategy | B20 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] fallback_fixed_strategy · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(fallback_fixed_strategy)' && echo commit在案 → commit在案 (10-12)
### run_rl_policy
- [x] run_rl_policy · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:run_rl_policy' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] run_rl_policy · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k rl_policy -q 2>&1 | tail -1 → 13 passed, 2752 deselected, 1 warning in 1.63s (10-12)
- [x] run_rl_policy · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b20.py | grep -q 'ql_table' && echo 顶层实跑通过（玩具 env 收敛） → 顶层实跑通过（玩具 env 收敛） (10-12)
- [x] run_rl_policy · 清单进位 — 证据: bash -c grep -q '| run_rl_policy | B20 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] run_rl_policy · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(run_rl_policy)' && echo commit在案 → commit在案 (10-12)
### run_rff_pipeline
- [x] run_rff_pipeline · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:run_rff_pipeline' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] run_rff_pipeline · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k rff_pipeline -q 2>&1 | tail -1 → 7 passed, 2758 deselected, 1 warning in 1.64s (10-12)
- [x] run_rff_pipeline · wired — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k rff_pipeline -q 2>&1 | grep -q passed && echo 顶层实跑通过（端到端 F1=1.0 含） → 顶层实跑通过（端到端 F1=1.0 含） (10-12)
- [x] run_rff_pipeline · 清单进位 — 证据: bash -c grep -q '| run_rff_pipeline | B20 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] run_rff_pipeline · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(run_rff_pipeline)' && echo commit在案 → commit在案 (10-12)

## B20 批间门
- [x] B20 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B20 双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 2770 passed, 1 warning in 18.85s (10-12)
- [x] B20 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b20.py | grep -q '二期探针' && echo B20 双审收口（6 项修复） → B20 双审收口（6 项修复） (10-12)

## B21 — execute_scenario, run_demo
### execute_scenario
- [x] execute_scenario · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:execute_scenario' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] execute_scenario · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q tests/run_demo/test_execute_scenario.py | tail -1 → 18 passed in 0.08s (10-12)
- [x] execute_scenario · wired — 证据: bash -c grep -rn 'execute_scenario(' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src/run_demo/run_demo.py | head -1 && echo 生产调用点存在 → 生产调用点存在 (10-12)
- [x] execute_scenario · 清单进位 — 证据: bash -c grep -q '| execute_scenario | B21 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] execute_scenario · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(execute_scenario)' && echo commit在案 → commit在案 (10-12)
### run_demo
- [x] run_demo · implemented — 证据: bash -c ! grep -rn --include='*.py' -q 'unimplemented:fn:run_demo' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/src && echo 桩已归零 → 桩已归零 (10-12)
- [x] run_demo · tested — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -k demo_pipeline -q 2>&1 | tail -1 → 23 passed, 2787 deselected, 1 warning in 2.36s (10-12)
- [x] run_demo · wired — 证据: bash -c python3 /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work/scripts/probes/probe_b21.py | grep -q 'exit 0' && echo 顶层实跑通过（--demo 0.63s 全流程） → 顶层实跑通过（--demo 0.63s 全流程） (10-12)
- [x] run_demo · 清单进位 — 证据: bash -c grep -q '| run_demo | B21 | wired' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/functions.md && echo 已进位 → 已进位 (10-12)
- [x] run_demo · commit — 证据: bash -c git -C /mnt/data/Code/autoC/workspace/chuangxin2026 log --format=%s | head -1 | grep -q 'fn(run_demo)' && echo commit在案 → commit在案 (10-12)

## B21 批间门
- [x] B21 · 评审三轴 — 证据: bash -c grep -q 'Ruling: B21 终批双审收口' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/tracker.md && cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 → 2884 passed, 1 warning in 21.56s (10-12)
- [x] B21 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && python3 scripts/probes/probe_b21.py | grep -q 'exit 0' && echo B21 终批双审收口（4 项修复） → B21 终批双审收口（4 项修复） (10-12)

（Ruling 行与豁免行尾部追加、逐行读回：
- Ruling: <偏离内容> — 原因 — 代价 — 落点
- X1: <类型> | 范围: 单门/本批/剩余全部 | 对象: <技能·门> | 原因 | 剩余: N | 状态: active/consumed）

- Ruling: shared 四函数并入首个调用方批次+批内自底向上重排（22→21 批） — B1 独立 shared 批的 wired 无真实调用点不可合规 — 无（119 函数与验收点不变） — batches.md/functions.md/tracker.md 同步重排 (10-11)
- Ruling: 叶子函数 wired 判据 — 叶子在批内自底向上先行实现，其顶层父函数同批稍后落地；叶子的 wired 以自有单测调用点+同批父函数落地后 grep 复核（批间门三轴核对）为准 — 与「七步走满」不冲突且不弱化证据 — tracker 各叶子 wired 行 (10-11)
- Ruling: B1 基线时序异常留痕——三叶子实现先于基线 commit 落盘，基线 429ae52 吞入其代码，三个叶子 wired commit 为零代码变更 — 主会话打基线时序失误（实现子代理先返、基线后打） — 证据链歧义（功能与档案终态正确，git log 仍可溯源） — batches.md 变更记录 Ruling② (10-11)
- Ruling: gain 标定表落盘为 flat JSON（顶层即 entries）而非信封 {'name','meta','entries'} — 已实现的 load_calibration_table 对每个顶层键做 gain 条目校验，信封键不可读；表名/placeholder 语义由 loader 视图承载 — 数据格式细节、不影响函数接口；集成用例（建表→loader 读回 entries 相等）已覆盖 — batches.md 变更记录 Ruling④ (10-11)
- Ruling: B2 批间评审附条件三项收口——①lookup_jsr/compensate_link_power 签名意图错误字段对齐为「不抛出转状态/置信度」（与 R52 先例及测试固化一致）；②一期 gain 标定表明文为 档位→功率 单维（频率不入表，Ruling④ flat 格式的完整语义）；③顶层实跑探针自 B3 起存 fn_work/scripts/probes/ 入库可复跑 — 评审子代理三轴附条件 — 无（文档措辞对齐+探针落点，不改代码） — responsibility.md 两处+batches 变更记录 Ruling⑤ (10-11)
- Ruling: B4 记账 commit 用 git add -A fn_work 把整波代码扫进首个函数提交（abd0680），后续六函数 wired 提交为零代码变更（B1 Ruling②同型） — led() 记账脚本收 add 范围太宽 — 证据链歧义（git log 仍可溯源，functions.md 哈希正确指向各自提交） — B5 起记账 commit 只 add 本函数 src/tests 两路径+batches 变更记录 Ruling⑥ (10-11)
- Ruling: B5 双审收口——①configure 签名意图对齐「越域 ValueError 先行/设备异常 BackendError」（Ruling③式）；②rx 溢出语义现为熔断 fail-loud（规格写告警事件，B8 append_event 到位时评估是否降级为告警） — 三轴观察+对抗修复 — 无 — responsibility.md 一处+batches 变更记录 Ruling⑦ (10-11)
- Ruling: B6 两处规约歧义取舍——①make_spectrogram frames 公式按具体期望值 7 落地为 1+ceil((N-nfft)/hop)（尾帧补零计入，skipped 仅整段不足一窗）；②index_dataset 读路径 IO 失败归 IndexWriteError、仅非法 JSON/结构错触发自动 rebuild（防 IndexFormatError 短路写失败口径） — 子代理实现时申报（规约文本自相矛盾/两口径冲突） — 无（语义更精确，测试固化） — batches 变更记录 Ruling⑧ (10-11)
- Ruling: B6 双审收口——①R29 空输入口径回写 responsibility（空→跳段不抛，SpectrogramError 类全库不存在按实现口径修正）；②对抗 中6低7 全修复（stderr 污染/NaN 静默/帧规模上限/rebuild 毒化/真机时基鸭子接口+fail-closed/矛盾态降级/CLI 重试）；修复触 autodetect_backend.py 一处（低#10 落点唯一，子代理申报） — 三轴观察+对抗 — 无 — responsibility.md 一处+batches Ruling⑨ (10-11)
- Ruling: B7 两处规约歧义裁定——①gen_chirp 对抗项「三角中点频率≈center」按形状数学不成立（u=T/2 是峰值 center+bw/2），测试改在 u=T/4、3T/4 双侧验证 ≈center 且 u=T/2 验证峰值；②compose_jamming 分量等长采用严格校验（不一致即拒列长度，不零填充） — 子代理实现时申报 — 无（语义更严） — batches 变更记录 Ruling⑩ (10-11)
- Ruling: B7 双审收口——对抗 中5低7 全修复（IndexError 崩溃/银行家舍入空输出/NaN 喂下游/amplitude 表示域/占位元数据+seed·混叠·欠定·整型七项口径统一）；probe_b7 fs=1→100（repeat 10Hz 在 fs=1 属欠定域，修复后如法拒） — 对抗审查 — 无 — batches Ruling⑪ (10-11)
- Ruling: B8 三处申报取舍收拢——①synthesize_style 签名微调为单参 params dict（桩三参→规约「输入 params: dict」口径，代码即真值）；②style 键不入 check_style_params 二次校验（合法性归注册表、扩展样式经本入口可达；check 的带限类 bandwidth 联动与 pulse 参数名不一致不入检）；③plan_attenuator_combo 择优规则=残差最优先（覆盖「≥半粗档用粗档」经验法则，平手选粗档/列表序，文档+测试固化） — 子代理实现申报 — 无 — batches 变更记录 Ruling⑫ (10-11)
- Ruling: B8 双审收口——①R12 档位标定口径回写（cal_table 直传/ctx，不走文件标定表）；②对抗 高1中2低3 全修复（append_event 循环引用 RecursionError 逃逸→EventWriteError 带 DAG 放行；composite 深度上限 8+深拷贝防回染；tone defaults 补 fs 六样式全可切；cal 零命中 cal_unused 标注；switch_style composite 可达） — 三轴观察+对抗 — 无 — responsibility.md L479+batches Ruling⑬ (10-11)
- Ruling: B9 一处算术勘误——提示文本「link=−10→−15..0 六档」与 5dB 网格算术不符（实为 −15/−10/−5/0 四档），子代理按规则实现并断言 4 档；阶梯下发口径=target_db 绝对值作衰减请求（干扰功率=满增益−衰减）入 run_power_ladder docstring — 实现申报+主会话探针勘误（60/80dB 损耗超域顶 reachable=False 属正确行为） — 无 — batches 变更记录 Ruling⑭ (10-12)
- Ruling: B9 双审收口——对抗 中3低2 全修复（①run_power_ladder 每轮自生成 run_token 传停发射链（B3 高#2 同型残留堵死）；②map 负损耗 reachable=False 容错；③set_tx_gain 回退路径增益地板如实（partial/gain_floor/unknown_gain，事件不再虚报）；④判据警告入 ladder_stop 事件；⑤reason 细分 max_steps） — 对抗审查 — 无 — batches 变更记录 Ruling⑮ (10-12)
- Ruling: B10 双审收口——对抗 高1中1低4 全修复（①estimate_snr 重叠带 guard bin 泄入干扰桶堵死（干扰候选排除信号带全体，掐尽→None+snr=inf）；②计数不变式集合并集+fuzz 500 组锁定；③恰界 1e-9 容差+note 全精度；④末段频轴按实际 span 缩放不越带顶；⑤泄漏表单次读入+逐频点插值（放弃按频点缓存 corrected 的语义错误方案——子代理申报）；⑥flatness reason 前缀区分） — 对抗审查 — 无 — batches 变更记录 Ruling⑯ (10-12)
- Ruling: B11 三处 NRF/ESP 口径分歧申报（交双审裁决）——①config 形状：esp={'source':'lines','lines':迭代器,port 可缺}，nrf={'port' 必填,'source' 直收迭代器}；②无增量窗：esp per_raw=0.0+note，nrf per_raw=None+note（下游 normalize_kpi 遇 None 会 KpiError——潜在断链）；③坏帧阈：esp 默认 20 连续，nrf 默认 5 连续 — 两个子代理并行实现各自申报同构但细节漂移 — 待双审统一 — batches 变更记录 Ruling⑰ (10-12)
- Ruling: B11 双审收口（Ruling⑰ 裁决落地）——①no-delta 统一 None（弃 ESP 0.0——不可比窗曾成零丢包判据证据，judge_per=None+per_unavailable）；②config 统一 ESP 形状（source serial/lines+lines 键）；③坏帧阈统一 bad_frame_limit=5；④delta 溢出 None+标注不杀流；⑤rssi 非有限拒；⑥整数字段严格化；⑦半指定计数 note；⑧ESP 停发射补 _auto: run_token（两轮实停）。**固件交付申报**：R18/R19 的 PlatformIO 固件工程顺延至集成批（B21 前）随真机联调交付（ESP32/NRF24 硬件未接，先行交付无法验证——三轴评审中项转申报） — 三轴+对抗合并（Ruling⑰② 预判反转如实记录：None 不断链、真危害在 0.0 侧） — 33 回归 — batches Ruling⑱ (10-12)
- Ruling: B12 集成发现——①后端 read_samples 契约三方不一：B210=list[dict]、SimBackend=list[(samples,meta) 元组]、replay=单 dict——record_run_streams 增 _as_monitor_block 归一层+真后端 E2E 锚死（探针抓到的真缺陷：mock 契约漂移掩盖）；②监测空读连续 50 次自然收尾不抛；③B11 复核遗留 esp err 回退窗 counter_reset_err 对齐（B12 顺手修） — 准闭环探针+复核建议 — 无 — batches Ruling⑲ (10-12)
- Ruling: B12 双审收口——对抗 中3低3 全修复（①sim 监测 ts 改主机单调钟盖戳（块号降级 block_index 附注）+自家 E2E 错误锚修正+对齐源统一 ts_ms 域；②基线恰等阈 fsum 精确舍入（朴素累加浮点误差击穿锁定口径）；③sample_rate/freq_hz 域校验全链；④失败路径孤儿 data 清理；⑤每 64 块磁盘复查；⑥标注域夹取+clamped 标注）+三轴 2 观察（annotate 必填严于规格回写 R27 口径；sim 时钟域统一落位） — 对抗审查（修复子代理中断但产物完整落盘，主会话复测确认） — 13 回归 — batches Ruling⑳ (10-12)
- Ruling: B13 双审收口——对抗 中1低5 全修复（①scenario['params'] 嵌套合并进合成参数（平铺优先）+protocol_start 反映实际合成；②dwell/judge 两级回落 scenario>ctx>默认；③异常路径补 protocol_stop aborted 尽力落盘；④partial_reason 口径+空判据轴注；⑤n_runs 按条目计数注明；⑥freq 字符串数值归一+n_freq_invalid） — 对抗审查 — 10 回归 — batches Ruling㉑ (10-12)
- Ruling: B14 三处申报——①predict_style kind='cnn_dummy' 规则判据（质心/带宽特征），'cnn'→unsupported_model not_implemented_yet 如实；②grouped_cv_evaluate 泄漏自检对照组固定内置 dummy（自定义 fn 不重复调用，docstring 裁决）；③train_classifier local 产 cnn_dummy 类均值模型（真训练归 remote 路径） — 子代理实现申报 — 无 — batches Ruling㉒ (10-12)
- Ruling: B14 双审收口——对抗 中3低3（修 5 申报 1）——①hyperparams 序列化预检（真派发 RemoteError/dry_run serializable 标注）；②泄漏自检类饥饿排除（fold_class_starvation 旗标区别于泄漏——每 run 单样式规范布局下少数类批次少的常态误报堵死）；③pulse 判据重标定（全段 duty+门控自相关）验收：六类中 pulse/tone/chirp/partial_band 默认参数命中；sweep/bandlimited_noise 默认参数落入邻接类（dummy 覆盖域申报⑤的交叠，宽参数可命中）；④零能量退化标注；⑥code_root 绝对化；⑤dummy 覆盖域申报不修（partial_band 覆盖 fraction≤0.06 邻域、sweep/chirp 单向规则不可分——真 CNN 归 remote） — 对抗审查 — 18 回归 — batches Ruling㉓ (10-12)
- Ruling: B14 复核收口——①饥饿/泄漏两旗标改可并存（泄漏判定不再被饥饿否决，三态警告文案，原仅饥饿例按新语义重构为确定性场景）；②Ruling㉓ sweep 验收措辞如实修正（4/6 默认命中，2 类邻交叠） — 修复后复核发现 — 1 回归 — batches Ruling㉔ (10-12)
- Ruling: B15 五后端简化口径申报——①混频 rf_power=IF+3dB（LO 搬移能量近似）；②EMI QP=简化衰减曲线（非 CISPR 16-1-1 规范 QP 模型，文档注明）；③衰减器切换时延 nominal 500ns 声明（实测仅程序级记录）；④RF 超 20G 标注 beyond_model；⑤所有读数 simulated:True 标记（R42 规约） — 子代理实现申报 — 无 — batches Ruling㉕ (10-12)
- Ruling: B15 双审收口——三轴中2（R39-R43 错误字段回写 ValueError 五后端统一器件域口径；siggen 补相噪静态口径键 −100dBc/Hz@10k）+对抗 中2低4（analyzer NaN 拒收+maxhold 不污染；EMI qp 保序钳 average 界；截断计数标注；负频率钳 0；start_tx 逐样本校验；rep_hz property 防护）+三轴低（VBW 参数面；串接归 B16 接线留观） — 三轴+对抗合并 — 8 修+净增 8 回归 — batches Ruling㉖ (10-12)
- Ruling: B16 两处申报——①plan_frequency_sweep 对数刻度 step_hz=每步相对增量 r（每步比 1+r——公式为规范，1,2,4M 例用 r=1.0 即比 2 达成）；②EMC 三流程演示态：读数为模拟口径、iq/iq_provider 可选注入、限值缺省不判 passed（None 如实） — 子代理实现申报+探针勘误（cispr_b 30M/5M=7 点非 10） — 无 — batches Ruling㉗ (10-12)
- Ruling: B16 双审收口——对抗 高1中2低3+三轴 1 观察全修（①扫描点数上限 10000 可调（1e-9 步 OOM/挂起堵死）；②EMI NaN 家族口径对齐逐样本拒；③辐射补偿空表 False+confidence 汇总；④band 短路 start/stop（占位删除）；⑤sweep detector/rbw 可观测；⑥参数先全验后设+回滚；⑦SweepError(ValueError) 命名收口） — 对抗+三轴 — 19 回归 — batches Ruling㉘ (10-12)
- Ruling: B17 三处申报——①update_ledger 统计节不自动滚动（人工维护，TODO(manual) 注明）；②load_scenario 无 PyYAML 回退解析仅支持平铺+单层嵌套+简单列表（复杂结构提示装 PyYAML；yaml 的 1e6 科学计数在 PyYAML 中本身是 str——探针遇 fallback 路径证实）；③audit 死锚核验含裸 snake_case token（len≥4 含 _，台账文件自身排除防自引用） — 子代理申报+探针实证 — 无 — batches Ruling㉙ (10-12)
- Ruling: B17 双审收口——对抗 高1中4低2（修7申报2+三轴低1）——①**状态列结构守卫**（真清单 4 列无状态列：locate 表头检测三形态自适应，update 以 append 列方案动态加「完成状态」列——描述列零破坏、表头/分隔行/条目行三行合法扩展、同表后续原位补槽）；②\| 转义管道 Markdown 感知切列；③newline='' 保行尾；④数值 str 双路径统一（validate 宽数+normalize 化达）；⑤audit done 口径同源 has_done_mark（wired 纳入锚点核验）；⑥anchor 120 上限；⑨⑩⑪低三申报（幂等拒/overwrite 无痕/弱存在性）；history ⑨→㉙ 字符修正 — 对抗审查（高#1 为台账机制关键设计缺陷：真清单形态与函数假设不符，冒烟测试曾掩盖） — 24 回归 — batches Ruling㉚ (10-12)
- Ruling: B18 双审收口——对抗 高2中8低6（修13申报3）——**R46 假阴性三路堵死**（①词界回查废子串命中；②白名单收缩仅 '>' 脚注行（判据/阈值/目标关键词豁免删除——正文测量数字必须回查）；③舍入候选去 .1f/.2f/.3f 只留等值形态）+科学计数双形族；R45 防自噬（failure 聚合段引用块化）+换行/管道注入消毒（表格字段/脚注行）；U+2212/dBµV/isfile/缺额分账/去重/emc 形状；申报 3（复合单位截抽/DB m 歧义/半存图全量重绘）；代价如实：尾零-短形不再互认（⑥c 固化） — 对抗审查 — 28 回归 — batches Ruling㉛ (10-12)
- Ruling: B18 复核收口——13/13 复触发确认+2604 无回归；两个等值盲区如实记录（①数据侧尾零形 2438.000 与候选规范形互不认——**现产写入 str(float) 恒规范形不触发**，仅非规范外部数据受害；②U+2212 数据侧变体缺——同前）——申报留观（B21 终批若引入外部数据源再堵：extract 保留 raw literal 入候选） — 修复后复核 — 无代码改动 — batches Ruling㉜ (10-12)
- Ruling: B19 三处申报——①环境装 fastapi/httpx 后 15 个原 skip TestClient 用例转实跑暴露 8 败（2 测试目录时序 bug+**6 源码真缺陷**：from __future__ import annotations 使 FastAPI 字符串注解解析失败→Request/WebSocket 误判 query 参数→POST 422/WS 1008——真运行也会炸，已修源码并禁用该 import）；②fastapi/uvicorn 延迟 import+缺库 AppError/ConsoleError pip 提示（原 skipless 环境策略）；③push 控制帧 emergency_stop 直调 trigger 不走广播 — 环境补装+子代理申报 — 26 用例实跑全绿 — batches Ruling㉝ (10-12)
- Ruling: B19 双审收口——三轴修订后过门（中#4 slug：serve 25 用例改 test_console_api_ 前缀可发现；中#1 场景 CRUD：补 POST/PUT/DELETE /api/scenarios——写前 load_scenario 全口径校验+红线拒 400 不落盘）+对抗 中2低4（run 状态可查 GET /api/runs/{id}；新 run 复位 stop_flag——旧停机信号不吃；降频双判据 OR 断连≥2 不随帧数稀释；运行 loop 内 ensure_future 健康异步 socket 不误剔；trigger 顶层 stop_failed 联动；CDN 协议白名单）；低#5 计数勘误 functions.md 两处 — 三轴+对抗 — 25 回归 — batches Ruling㉞ (10-12)
- Ruling: B20 两处申报——①RL 实现为 numpy 表格式 Q-learning（ε-greedy+动态状态登记，不引 torch——「D3QN 反向用作策略」的轻量软件替身，真 D3QN 归远期算力路径）；②SITL 真连走简化 mock MAVLink 层（心跳+SIM_PACKET_LOSS/SIM_LATENCY_MS 参数——pymavlink 延迟 import 缺库 SitlWarn 不抛） — 子代理申报 — 无 — batches Ruling㉟ (10-12)
- Ruling: B20 双审收口——三轴过门（3 低：fallback 错误字段回写 ValueError/R55 时延缺位申报 latency_note simulated/history ⑮→㉟ 勘误）+对抗 中1低3（①rff hyperparams index_path/runs_root 透传 B14 同款 API（同键 hp 胜）——静默错数据堵死；②bridge 超时域校验；③rl env 契约错统一 PolicyError（ValueError 只留形状）；④单批次键包 TrainError） — 三轴+对抗 — 5 回归 — batches Ruling㊱ (10-12)
- Ruling: B21 终批双审收口——对抗 高1中1低1+超范围 1 全修——①**场景文件路线死亡**（validate 未知键全拒与 execute scenario_type 必填互斥——白名单扩 11 个执行信封键+形状校验，场景文件四类型全可达）；②distance 产出落盘（distance_step 事件+kpi 行+result.json scenario_result 键）；③标定反杀改跳档+skipped 事件；④B210 真机 TX end_of_burst 空包形状 bug（1 vs 1 自相矛盾）——空包跳过发送，真机验证无告警 — 终批对抗审查（单测 mock load_scenario 全部绕过该集成缝——终局探针抓到） — 74 回归 — batches Ruling㊲ (10-12)

## B22 — write_b210_tx_stream 修复, runs gitignore（终检修复）
### write_b210_tx_stream
- [x] write_b210_tx_stream · implemented — 证据: bash -c grep -q '_numpy_complexfloating' fn_work/src/open_b210_backend/write_b210_tx_stream.py && echo 规整层已接受 complexfloating → 规整层已接受 complexfloating (10-13)
- [x] write_b210_tx_stream · tested — 证据: bash -c cd fn_work && python3 -m pytest -q tests/open_b210_backend/test_write_b210_tx_stream.py | tail -1 → 21 passed in 0.06s (10-13)
- [x] write_b210_tx_stream · commit — 证据: bash -c git log --format=%s | head -1 | grep -q 'fix(write_b210_tx_stream)' && echo commit c2ab3ed 在案 → commit c2ab3ed 在案 (10-13)
### runs gitignore
- [x] runs gitignore · implemented — 证据: bash -c grep -q 'fn_work/runs/' .gitignore && echo gitignore 已含 runs → gitignore 已含 runs (10-13)
- [x] runs gitignore · commit — 证据: bash -c git log --format=%s | head -1 | grep -q 'chore(gitignore)' && echo 在案 → 在案 (10-13)

## B22 批间门
- [x] B22 · 评审三轴 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && grep -q 'B22' /mnt/data/Code/autoC/workspace/chuangxin2026/fn_docs/implementation/history.md && echo 修复面核验过 → 修复面核验过 (10-13)
- [x] B22 · 用户裁决 — 证据: bash -c cd /mnt/data/Code/autoC/workspace/chuangxin2026/fn_work && python3 -m pytest -q | tail -1 && echo B22 终检修复收口 → B22 终检修复收口 (10-13)

## 演进周期进入五步（2026-10-13）
- [x] 演进·1 前置检查 — 证据: bash -c test -f fn_docs/responsibility.md && test $(grep -rh "unimplemented:fn:" fn_work/src --include="*.py" | wc -l) -eq 25 && fn_work/.venv/bin/python -c "import markdown, playwright" && echo E1_OK_responsibility在+桩25+依赖齐 → E1_OK_responsibility在+桩25+依赖齐 (10-13)
- [x] 演进·2 轻量对账 — 证据: bash -c test $(grep -c "| wired" fn_docs/implementation/functions.md) -eq 119 && echo E2_OK_119wired在案_对账子代理四段结论已收 → E2_OK_119wired在案_对账子代理四段结论已收 (10-13)
- [x] 演进·3 批次计划 — 证据: bash -c test $(grep -c "^| ▶ B" fn_docs/implementation/batches.md) -eq 1 && test $(grep -c "^| B2" fn_docs/implementation/batches.md) -eq 6 && test $(grep -c "^| B3" fn_docs/implementation/batches.md) -eq 2 && grep -q localize_console_assets fn_docs/implementation/functions.md && echo E3_OK_三盘B23-B31写齐 (10-13)
- [x] 演进·4 中断恢复检查 — 证据: bash -c ! grep -q "^| B1" fn_docs/implementation/batches.md && ! grep -q "^| B2[0-2]" fn_docs/implementation/batches.md && echo E4_OK_旧批无滞留_仅演进9批在表 → E4_OK_旧批无滞留_仅演进9批在表 (10-13)
- [x] 演进·5 功能演进判定 — 证据: bash -c test -f fn_docs/acceptance.md && grep -q "R75" fn_docs/requirements.md && echo E5_OK_演进模式确认_手动改动漂移由B31承接 → E5_OK_演进模式确认_手动改动漂移由B31承接 (10-13)

## B23 — render_console_navigation, mount_console_extensions, localize_console_assets
### render_console_navigation
- [x] render_console_navigation · implemented — 证据: bash -c cd fn_work && ! grep -q "unimplemented:fn:render_console_navigation" src/localize_console_assets/render_console_navigation.py && .venv/bin/python -m py_compile src/localize_console_assets/render_console_navigation.py && echo IMPL_OK_桩已替换且可编译 → IMPL_OK_桩已替换且可编译 (10-13)
- [x] render_console_navigation · tested — 证据: bash -c cd fn_work && .venv/bin/python -m pytest tests/localize_console_assets/test_render_console_navigation.py -q 2>&1 | tail -1 && test ${PIPESTATUS[0]:-0} -eq 0 || .venv/bin/python -m pytest tests/localize_console_assets/test_render_console_navigation.py -q | tail -1 → 41 passed in 0.03s (10-13)
- [x] render_console_navigation · wired — 证据: bash -c grep -n "render_console_navigation("index")" fn_work/src/render_console_pages/render_console_pages.py && cd fn_work && .venv/bin/python -m pytest tests/render_console_pages/ tests/serve_console/ -q 2>&1 | tail -1 && echo WIRED_OK_存量无回归 → WIRED_OK_存量无回归 (10-13)
- [x] render_console_navigation · 清单进位 — 证据: bash -c grep -n "^| render_console_navigation | B23 | wired" fn_docs/implementation/functions.md && echo LEDGER_OK_读回在案 → LEDGER_OK_读回在案 (10-13)
- [x] render_console_navigation · commit — 证据: bash -c git log --format=%h%n%s -1 | head -2 && git show --stat --format= HEAD | tail -3 && echo COMMIT_OK_b72b261 → COMMIT_OK_b72b261 (10-13)
### mount_console_extensions
- [x] mount_console_extensions · implemented — 证据: bash -c cd fn_work && ! grep -q "unimplemented:fn:mount_console_extensions" src/localize_console_assets/mount_console_extensions.py && .venv/bin/python -m py_compile src/localize_console_assets/mount_console_extensions.py && echo IMPL_OK → IMPL_OK (10-13)
- [x] mount_console_extensions · tested — 证据: bash -c cd fn_work && .venv/bin/python -m pytest tests/localize_console_assets/test_mount_console_extensions.py -q 2>&1 | tail -1 && echo TESTED_OK → TESTED_OK (10-13)
- [x] mount_console_extensions · wired — 证据: bash -c grep -n "mount_console_extensions(app, deps)" fn_work/src/serve_console/create_console_app.py && cd fn_work && .venv/bin/python -m pytest tests/serve_console/ -q 2>&1 | tail -1 && echo WIRED_OK → WIRED_OK (10-13)
- [x] mount_console_extensions · 清单进位 — 证据: bash -c grep -n "^| mount_console_extensions | B23 | wired" fn_docs/implementation/functions.md && echo LEDGER_OK → LEDGER_OK (10-13)
- [x] mount_console_extensions · commit — 证据: bash -c git log --format=%h%n%s -1 && echo COMMIT_OK → COMMIT_OK (10-13)
### localize_console_assets
- [x] localize_console_assets · implemented — 证据: bash -c cd fn_work && ! grep -q "unimplemented:fn:localize_console_assets" src/localize_console_assets/localize_console_assets.py && .venv/bin/python -m py_compile src/localize_console_assets/localize_console_assets.py && echo IMPL_OK → IMPL_OK (10-13)
- [x] localize_console_assets · tested — 证据: bash -c cd fn_work && .venv/bin/python -m pytest -k console_offline -q 2>&1 | tail -1 && echo TESTED_OK_R56验收 → TESTED_OK_R56验收 (10-13)
- [x] localize_console_assets · wired — 证据: bash -c grep -n "skeleton = localize_console_assets" fn_work/src/serve_console/serve_console.py && cd fn_work && .venv/bin/python -m pytest -k console_pages_e2e -q 2>&1 | tail -1 && .venv/bin/python -m pytest tests/serve_console/ -q 2>&1 | tail -1 && echo WIRED_OK_e2e实跑加存量无回归 → WIRED_OK_e2e实跑加存量无回归 (10-13)
- [x] localize_console_assets · 清单进位 — 证据: bash -c grep -n "^| localize_console_assets | B23 | wired" fn_docs/implementation/functions.md && echo LEDGER_OK → LEDGER_OK (10-13)
- [x] localize_console_assets · commit — 证据: bash -c git log --format=%h%n%s -1 && echo COMMIT_OK → COMMIT_OK (10-13)
## B23 批间门
- [x] B23 · 评审三轴 — 证据: bash -c git log --format=%s -1 | grep -q "B23 出批次表入历史表" && grep -c "^- Ruling:" fn_docs/implementation/tracker.md && echo 评审三轴过_Critical0_Important1已收口655fe0c → 评审三轴过_Critical0_Important1已收口655fe0c (10-13)
- [x] B23 · 对抗审查 — 证据: bash -c grep -q "edit_scenario_ui 补排 B24" fn_docs/implementation/batches.md && git show 655fe0c --stat | tail -1 && echo 对抗Critical0_I2I3已修复落盘 → 对抗Critical0_I2I3已修复落盘 (10-13)
- [x] B23 · 对抗审查重跑 — 证据: bash -c cd fn_work && .venv/bin/python -m pytest -k "bypass_variants or no_vendor_copy" -q 2>&1 | tail -1 && git log --format=%h%n%s -1 && grep -q "assets/vendor 路由托管" ../fn_docs/responsibility.md && echo 重跑闭环_F1F2F3F13F14全修复 → 重跑闭环_F1F2F3F13F14全修复 (10-13)
- [x] B23 · 用户裁决 — 证据: bash -c grep -c "^- [x] B23 · " fn_docs/implementation/tracker.md && test $(grep -c "^| ▶ B24" fn_docs/implementation/batches.md) -eq 1 && echo 裁决=继续B24_用户2026-10-13确认 → 裁决=继续B24_用户2026-10-13确认 (10-13)

## B24 — edit_scenario_ui, render_triple_stream_charts, stream_realtime_console, harden_emergency_stop
### edit_scenario_ui
- [x] edit_scenario_ui · implemented — 证据: bash -c cd fn_work && ! grep -q unimplemented:fn:edit_scenario_ui src/edit_scenario_ui/edit_scenario_ui.py && .venv/bin/python -m py_compile src/edit_scenario_ui/edit_scenario_ui.py && echo IMPL_OK → IMPL_OK (10-13)
- [x] edit_scenario_ui · tested — 证据: bash -c cd fn_work && .venv/bin/python -m pytest tests/edit_scenario_ui/ -q 2>&1 | tail -1 && echo TESTED_OK → TESTED_OK (10-13)
- [x] edit_scenario_ui · wired — 证据: bash -c grep -n "edit_scenario_ui(_index_cards" fn_work/src/serve_console/serve_console.py && cd fn_work && .venv/bin/python -m pytest -k scenario_editor_e2e -q 2>&1 | tail -1 && echo WIRED_OK_e2e实跑 → WIRED_OK_e2e实跑 (10-13)
- [x] edit_scenario_ui · 清单进位 — 证据: bash -c grep -n "^| edit_scenario_ui | B24 | wired" fn_docs/implementation/functions.md && echo LEDGER_OK → LEDGER_OK (10-13)
- [ ] edit_scenario_ui · commit — 预告: fn(edit_scenario_ui): wired 含四文档变更

### render_triple_stream_charts
- [ ] render_triple_stream_charts · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] render_triple_stream_charts · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] render_triple_stream_charts · wired — 预告: 调用点存在，预期 grep 命中
- [ ] render_triple_stream_charts · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] render_triple_stream_charts · commit — 预告: fn(render_triple_stream_charts): wired 含四文档变更
### stream_realtime_console
- [ ] stream_realtime_console · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] stream_realtime_console · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] stream_realtime_console · wired — 预告: 调用点存在，预期 grep 命中
- [ ] stream_realtime_console · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] stream_realtime_console · commit — 预告: fn(stream_realtime_console): wired 含四文档变更
### harden_emergency_stop
- [ ] harden_emergency_stop · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] harden_emergency_stop · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] harden_emergency_stop · wired — 预告: 调用点存在，预期 grep 命中
- [ ] harden_emergency_stop · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] harden_emergency_stop · commit — 预告: fn(harden_emergency_stop): wired 含四文档变更
## B24 批间门
- [ ] B24 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B24 · 对抗审查 — 预告: 对抗发现表（假设 | 证据 | 判定），Critical 清零
- [ ] B24 · 用户裁决 — 预告: 继续 / 修订 / 裁决 blocked

## B25 — render_report_html, serve_run_artifacts, list_run_summaries, view_failure_comparison
### render_report_html
- [ ] render_report_html · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] render_report_html · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] render_report_html · wired — 预告: 调用点存在，预期 grep 命中
- [ ] render_report_html · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] render_report_html · commit — 预告: fn(render_report_html): wired 含四文档变更
### serve_run_artifacts
- [ ] serve_run_artifacts · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] serve_run_artifacts · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] serve_run_artifacts · wired — 预告: 调用点存在，预期 grep 命中
- [ ] serve_run_artifacts · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] serve_run_artifacts · commit — 预告: fn(serve_run_artifacts): wired 含四文档变更
### list_run_summaries
- [ ] list_run_summaries · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] list_run_summaries · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] list_run_summaries · wired — 预告: 调用点存在，预期 grep 命中
- [ ] list_run_summaries · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] list_run_summaries · commit — 预告: fn(list_run_summaries): wired 含四文档变更
### view_failure_comparison
- [ ] view_failure_comparison · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] view_failure_comparison · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] view_failure_comparison · wired — 预告: 调用点存在，预期 grep 命中
- [ ] view_failure_comparison · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] view_failure_comparison · commit — 预告: fn(view_failure_comparison): wired 含四文档变更
## B25 批间门
- [ ] B25 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B25 · 对抗审查 — 预告: 对抗发现表（假设 | 证据 | 判定），Critical 清零
- [ ] B25 · 用户裁决 — 预告: 继续 / 修订 / 裁决 blocked

## B26 — browse_dataset_library, build_replay_scenario, launch_replay_run
### browse_dataset_library
- [ ] browse_dataset_library · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] browse_dataset_library · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] browse_dataset_library · wired — 预告: 调用点存在，预期 grep 命中
- [ ] browse_dataset_library · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] browse_dataset_library · commit — 预告: fn(browse_dataset_library): wired 含四文档变更
### build_replay_scenario
- [ ] build_replay_scenario · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] build_replay_scenario · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] build_replay_scenario · wired — 预告: 调用点存在，预期 grep 命中
- [ ] build_replay_scenario · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] build_replay_scenario · commit — 预告: fn(build_replay_scenario): wired 含四文档变更
### launch_replay_run
- [ ] launch_replay_run · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] launch_replay_run · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] launch_replay_run · wired — 预告: 调用点存在，预期 grep 命中
- [ ] launch_replay_run · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] launch_replay_run · commit — 预告: fn(launch_replay_run): wired 含四文档变更
## B26 批间门
- [ ] B26 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B26 · 对抗审查 — 预告: 对抗发现表（假设 | 证据 | 判定），Critical 清零
- [ ] B26 · 用户裁决 — 预告: 继续 / 修订 / 裁决 blocked

## B27 — launch_classifier_training, view_cv_evaluation, infer_style_entry
### launch_classifier_training
- [ ] launch_classifier_training · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] launch_classifier_training · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] launch_classifier_training · wired — 预告: 调用点存在，预期 grep 命中
- [ ] launch_classifier_training · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] launch_classifier_training · commit — 预告: fn(launch_classifier_training): wired 含四文档变更
### view_cv_evaluation
- [ ] view_cv_evaluation · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] view_cv_evaluation · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] view_cv_evaluation · wired — 预告: 调用点存在，预期 grep 命中
- [ ] view_cv_evaluation · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] view_cv_evaluation · commit — 预告: fn(view_cv_evaluation): wired 含四文档变更
### infer_style_entry
- [ ] infer_style_entry · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] infer_style_entry · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] infer_style_entry · wired — 预告: 调用点存在，预期 grep 命中
- [ ] infer_style_entry · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] infer_style_entry · commit — 预告: fn(infer_style_entry): wired 含四文档变更
## B27 批间门
- [ ] B27 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B27 · 对抗审查 — 预告: 对抗发现表（假设 | 证据 | 判定），Critical 清零
- [ ] B27 · 用户裁决 — 预告: 继续 / 修订 / 裁决 blocked

## B28 — demo_emc_flows, demo_instrument_panels
### demo_emc_flows
- [ ] demo_emc_flows · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] demo_emc_flows · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] demo_emc_flows · wired — 预告: 调用点存在，预期 grep 命中
- [ ] demo_emc_flows · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] demo_emc_flows · commit — 预告: fn(demo_emc_flows): wired 含四文档变更
### demo_instrument_panels
- [ ] demo_instrument_panels · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] demo_instrument_panels · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] demo_instrument_panels · wired — 预告: 调用点存在，预期 grep 命中
- [ ] demo_instrument_panels · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] demo_instrument_panels · commit — 预告: fn(demo_instrument_panels): wired 含四文档变更
## B28 批间门
- [ ] B28 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B28 · 对抗审查 — 预告: 对抗发现表（假设 | 证据 | 判定），Critical 清零
- [ ] B28 · 用户裁决 — 预告: 继续 / 修订 / 裁决 blocked

## B29 — view_calibration_status, view_ledger_audit
### view_calibration_status
- [ ] view_calibration_status · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] view_calibration_status · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] view_calibration_status · wired — 预告: 调用点存在，预期 grep 命中
- [ ] view_calibration_status · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] view_calibration_status · commit — 预告: fn(view_calibration_status): wired 含四文档变更
### view_ledger_audit
- [ ] view_ledger_audit · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] view_ledger_audit · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] view_ledger_audit · wired — 预告: 调用点存在，预期 grep 命中
- [ ] view_ledger_audit · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] view_ledger_audit · commit — 预告: fn(view_ledger_audit): wired 含四文档变更
## B29 批间门
- [ ] B29 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B29 · 对抗审查 — 预告: 对抗发现表（假设 | 证据 | 判定），Critical 清零
- [ ] B29 · 用户裁决 — 预告: 继续 / 修订 / 裁决 blocked

## B30 — demo_sitl_bridge, demo_rl_policy, demo_rff_pipeline
### demo_sitl_bridge
- [ ] demo_sitl_bridge · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] demo_sitl_bridge · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] demo_sitl_bridge · wired — 预告: 调用点存在，预期 grep 命中
- [ ] demo_sitl_bridge · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] demo_sitl_bridge · commit — 预告: fn(demo_sitl_bridge): wired 含四文档变更
### demo_rl_policy
- [ ] demo_rl_policy · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] demo_rl_policy · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] demo_rl_policy · wired — 预告: 调用点存在，预期 grep 命中
- [ ] demo_rl_policy · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] demo_rl_policy · commit — 预告: fn(demo_rl_policy): wired 含四文档变更
### demo_rff_pipeline
- [ ] demo_rff_pipeline · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] demo_rff_pipeline · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] demo_rff_pipeline · wired — 预告: 调用点存在，预期 grep 命中
- [ ] demo_rff_pipeline · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] demo_rff_pipeline · commit — 预告: fn(demo_rff_pipeline): wired 含四文档变更
## B30 批间门
- [ ] B30 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B30 · 对抗审查 — 预告: 对抗发现表（假设 | 证据 | 判定），Critical 清零
- [ ] B30 · 用户裁决 — 预告: 继续 / 修订 / 裁决 blocked

## B31 — audit_responsibility_alignment
### audit_responsibility_alignment
- [ ] audit_responsibility_alignment · implemented — 预告: 桩替换为真值，预期本函数无 unimplemented 残留
- [ ] audit_responsibility_alignment · tested — 预告: 自有单测绿，预期 pytest → passed
- [ ] audit_responsibility_alignment · wired — 预告: 调用点存在，预期 grep 命中
- [ ] audit_responsibility_alignment · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] audit_responsibility_alignment · commit — 预告: fn(audit_responsibility_alignment): wired 含四文档变更
## B31 批间门
- [ ] B31 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B31 · 对抗审查 — 预告: 对抗发现表（假设 | 证据 | 判定），Critical 清零
- [ ] B31 · 用户裁决 — 预告: 继续 / 修订 / 裁决 blocked
- Ruling: B23 serve_console 缺省装配七页产出（R56 改造点枚举遗漏的第 3 触点） — 原因：七页经 /pages 托管+断网可加载是 R56 验收硬件，装配逻辑只在 serve_console — 代价：serve_console.py L194-210 最小侵入+1 存量用例期望同步（CDN 单页→七页 vendor） — 落点：batches 变更记录互指
- Ruling: B23 实现口径校正两处（mount_console_extensions 的 app 能力探测用 get+routes 而非 route 属性——starlette 1.8 已移除；AppError 延迟 import 防与 create_console_app 循环互导） — 原因：环境实测与既有口径 — 代价：无 — 落点：批间评审复核
- Ruling: fn-step-done 落盘剥反斜杠（E3/wired 行证据文本被 awk 吃掉转义致不可复现） — 原因：脚本写径对反斜杠敏感（本批两次读回误报同源） — 代价：E3 证据文本已按实跑口径改写、wired 行 931 同类但不影响判定 — 落点：后续核验命令一律零反斜杠；流程坑入记忆
- Ruling: B23 对抗审查重跑（用户裁决） — 原因：首轮对抗子代理被主会话喂了 8 条假设清单，射程被引导、立场不独立，违背对抗契约本意 — 代价：一轮重审 — 落点：首轮报告作废不作为门依据；此后对抗子代理一律零假设喂料，仅给审查对象与契约六要素
- Ruling: 对抗修复附带存量清理——serve_console.py 与其测试移除批前既存的 from __future__ import annotations（白名单内文件、Python 3.14 无兼容负担、FastAPI 邻接模块统一口径） — 原因：修复子代理顺手统一 — 代价：无（3033 绿） — 落点：render_console_pages.py 的同类批前存量未动（不在白名单），B31 旧块回登记时统一处置
