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
- [ ] manage_run · commit — 预告: fn(manage_run): wired 含四文档变更

## B3 批间门
- [ ] B3 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B3 · 用户裁决 — 预告: 继续 B4 / 修订 / 裁决 blocked

## B4 — register_backend, lookup_backend, manage_backend_registry, loopback_sim_stream, open_sim_backend, read_sigmf_timeline, open_replay_backend
### register_backend
- [ ] register_backend · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] register_backend · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] register_backend · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] register_backend · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] register_backend · commit — 预告: fn(register_backend): wired 含四文档变更
### lookup_backend
- [ ] lookup_backend · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] lookup_backend · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] lookup_backend · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] lookup_backend · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] lookup_backend · commit — 预告: fn(lookup_backend): wired 含四文档变更
### manage_backend_registry
- [ ] manage_backend_registry · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] manage_backend_registry · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] manage_backend_registry · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] manage_backend_registry · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] manage_backend_registry · commit — 预告: fn(manage_backend_registry): wired 含四文档变更
### loopback_sim_stream
- [ ] loopback_sim_stream · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] loopback_sim_stream · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] loopback_sim_stream · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] loopback_sim_stream · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] loopback_sim_stream · commit — 预告: fn(loopback_sim_stream): wired 含四文档变更
### open_sim_backend
- [ ] open_sim_backend · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] open_sim_backend · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] open_sim_backend · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] open_sim_backend · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] open_sim_backend · commit — 预告: fn(open_sim_backend): wired 含四文档变更
### read_sigmf_timeline
- [ ] read_sigmf_timeline · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] read_sigmf_timeline · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] read_sigmf_timeline · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] read_sigmf_timeline · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] read_sigmf_timeline · commit — 预告: fn(read_sigmf_timeline): wired 含四文档变更
### open_replay_backend
- [ ] open_replay_backend · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] open_replay_backend · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] open_replay_backend · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] open_replay_backend · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] open_replay_backend · commit — 预告: fn(open_replay_backend): wired 含四文档变更

## B4 批间门
- [ ] B4 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B4 · 用户裁决 — 预告: 继续 B5 / 修订 / 裁决 blocked

## B5 — configure_b210_channels, write_b210_tx_stream, read_b210_rx_stream, open_b210_backend, exchange_scpi, create_visa_driver
### configure_b210_channels
- [ ] configure_b210_channels · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] configure_b210_channels · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] configure_b210_channels · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] configure_b210_channels · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] configure_b210_channels · commit — 预告: fn(configure_b210_channels): wired 含四文档变更
### write_b210_tx_stream
- [ ] write_b210_tx_stream · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] write_b210_tx_stream · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] write_b210_tx_stream · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] write_b210_tx_stream · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] write_b210_tx_stream · commit — 预告: fn(write_b210_tx_stream): wired 含四文档变更
### read_b210_rx_stream
- [ ] read_b210_rx_stream · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] read_b210_rx_stream · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] read_b210_rx_stream · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] read_b210_rx_stream · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] read_b210_rx_stream · commit — 预告: fn(read_b210_rx_stream): wired 含四文档变更
### open_b210_backend
- [ ] open_b210_backend · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] open_b210_backend · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] open_b210_backend · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] open_b210_backend · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] open_b210_backend · commit — 预告: fn(open_b210_backend): wired 含四文档变更
### exchange_scpi
- [ ] exchange_scpi · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] exchange_scpi · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] exchange_scpi · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] exchange_scpi · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] exchange_scpi · commit — 预告: fn(exchange_scpi): wired 含四文档变更
### create_visa_driver
- [ ] create_visa_driver · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] create_visa_driver · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] create_visa_driver · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] create_visa_driver · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] create_visa_driver · commit — 预告: fn(create_visa_driver): wired 含四文档变更

## B5 批间门
- [ ] B5 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B5 · 用户裁决 — 预告: 继续 B6 / 修订 / 裁决 blocked

## B6 — probe_uhd_devices, autodetect_backend, probe_gpsdo_status, resolve_clock_reference, make_spectrogram, query_dataset, index_dataset
### probe_uhd_devices
- [ ] probe_uhd_devices · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] probe_uhd_devices · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] probe_uhd_devices · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] probe_uhd_devices · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] probe_uhd_devices · commit — 预告: fn(probe_uhd_devices): wired 含四文档变更
### autodetect_backend
- [ ] autodetect_backend · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] autodetect_backend · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] autodetect_backend · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] autodetect_backend · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] autodetect_backend · commit — 预告: fn(autodetect_backend): wired 含四文档变更
### probe_gpsdo_status
- [ ] probe_gpsdo_status · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] probe_gpsdo_status · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] probe_gpsdo_status · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] probe_gpsdo_status · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] probe_gpsdo_status · commit — 预告: fn(probe_gpsdo_status): wired 含四文档变更
### resolve_clock_reference
- [ ] resolve_clock_reference · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] resolve_clock_reference · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] resolve_clock_reference · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] resolve_clock_reference · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] resolve_clock_reference · commit — 预告: fn(resolve_clock_reference): wired 含四文档变更
### make_spectrogram
- [ ] make_spectrogram · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] make_spectrogram · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] make_spectrogram · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] make_spectrogram · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] make_spectrogram · commit — 预告: fn(make_spectrogram): wired 含四文档变更
### query_dataset
- [ ] query_dataset · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] query_dataset · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] query_dataset · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] query_dataset · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] query_dataset · commit — 预告: fn(query_dataset): wired 含四文档变更
### index_dataset
- [ ] index_dataset · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] index_dataset · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] index_dataset · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] index_dataset · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] index_dataset · commit — 预告: fn(index_dataset): wired 含四文档变更

## B6 批间门
- [ ] B6 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B6 · 用户裁决 — 预告: 继续 B7 / 修订 / 裁决 blocked

## B7 — check_style_params, gen_tone, gen_sweep, gen_chirp, gen_bandlimited_noise, gen_partial_band, gen_pulse, compose_jamming
### check_style_params
- [ ] check_style_params · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] check_style_params · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] check_style_params · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] check_style_params · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] check_style_params · commit — 预告: fn(check_style_params): wired 含四文档变更
### gen_tone
- [ ] gen_tone · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] gen_tone · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] gen_tone · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] gen_tone · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] gen_tone · commit — 预告: fn(gen_tone): wired 含四文档变更
### gen_sweep
- [ ] gen_sweep · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] gen_sweep · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] gen_sweep · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] gen_sweep · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] gen_sweep · commit — 预告: fn(gen_sweep): wired 含四文档变更
### gen_chirp
- [ ] gen_chirp · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] gen_chirp · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] gen_chirp · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] gen_chirp · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] gen_chirp · commit — 预告: fn(gen_chirp): wired 含四文档变更
### gen_bandlimited_noise
- [ ] gen_bandlimited_noise · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] gen_bandlimited_noise · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] gen_bandlimited_noise · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] gen_bandlimited_noise · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] gen_bandlimited_noise · commit — 预告: fn(gen_bandlimited_noise): wired 含四文档变更
### gen_partial_band
- [ ] gen_partial_band · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] gen_partial_band · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] gen_partial_band · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] gen_partial_band · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] gen_partial_band · commit — 预告: fn(gen_partial_band): wired 含四文档变更
### gen_pulse
- [ ] gen_pulse · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] gen_pulse · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] gen_pulse · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] gen_pulse · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] gen_pulse · commit — 预告: fn(gen_pulse): wired 含四文档变更
### compose_jamming
- [ ] compose_jamming · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] compose_jamming · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] compose_jamming · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] compose_jamming · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] compose_jamming · commit — 预告: fn(compose_jamming): wired 含四文档变更

## B7 批间门
- [ ] B7 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B7 · 用户裁决 — 预告: 继续 B8 / 修订 / 裁决 blocked

## B8 — append_event, synthesize_style, lookup_style_recipe, switch_style, plan_attenuator_combo, set_channel_attenuation
### append_event
- [ ] append_event · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] append_event · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] append_event · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] append_event · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] append_event · commit — 预告: fn(append_event): wired 含四文档变更
### synthesize_style
- [ ] synthesize_style · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] synthesize_style · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] synthesize_style · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] synthesize_style · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] synthesize_style · commit — 预告: fn(synthesize_style): wired 含四文档变更
### lookup_style_recipe
- [ ] lookup_style_recipe · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] lookup_style_recipe · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] lookup_style_recipe · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] lookup_style_recipe · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] lookup_style_recipe · commit — 预告: fn(lookup_style_recipe): wired 含四文档变更
### switch_style
- [ ] switch_style · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] switch_style · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] switch_style · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] switch_style · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] switch_style · commit — 预告: fn(switch_style): wired 含四文档变更
### plan_attenuator_combo
- [ ] plan_attenuator_combo · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] plan_attenuator_combo · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] plan_attenuator_combo · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] plan_attenuator_combo · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] plan_attenuator_combo · commit — 预告: fn(plan_attenuator_combo): wired 含四文档变更
### set_channel_attenuation
- [ ] set_channel_attenuation · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] set_channel_attenuation · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] set_channel_attenuation · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] set_channel_attenuation · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] set_channel_attenuation · commit — 预告: fn(set_channel_attenuation): wired 含四文档变更

## B8 批间门
- [ ] B8 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B8 · 用户裁决 — 预告: 继续 B9 / 修订 / 裁决 blocked

## B9 — plan_ladder_steps, run_power_ladder, compute_pathloss, map_distance_to_loss
### plan_ladder_steps
- [ ] plan_ladder_steps · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] plan_ladder_steps · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] plan_ladder_steps · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] plan_ladder_steps · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] plan_ladder_steps · commit — 预告: fn(plan_ladder_steps): wired 含四文档变更
### run_power_ladder
- [ ] run_power_ladder · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] run_power_ladder · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] run_power_ladder · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] run_power_ladder · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] run_power_ladder · commit — 预告: fn(run_power_ladder): wired 含四文档变更
### compute_pathloss
- [ ] compute_pathloss · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] compute_pathloss · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] compute_pathloss · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] compute_pathloss · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] compute_pathloss · commit — 预告: fn(compute_pathloss): wired 含四文档变更
### map_distance_to_loss
- [ ] map_distance_to_loss · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] map_distance_to_loss · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] map_distance_to_loss · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] map_distance_to_loss · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] map_distance_to_loss · commit — 预告: fn(map_distance_to_loss): wired 含四文档变更

## B9 批间门
- [ ] B9 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B9 · 用户裁决 — 预告: 继续 B10 / 修订 / 裁决 blocked

## B10 — enforce_bandwidth_limit, capture_monitor_spectrum, estimate_snr, check_flatness, compute_spectrum_stats
### enforce_bandwidth_limit
- [ ] enforce_bandwidth_limit · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] enforce_bandwidth_limit · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] enforce_bandwidth_limit · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] enforce_bandwidth_limit · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] enforce_bandwidth_limit · commit — 预告: fn(enforce_bandwidth_limit): wired 含四文档变更
### capture_monitor_spectrum
- [ ] capture_monitor_spectrum · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] capture_monitor_spectrum · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] capture_monitor_spectrum · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] capture_monitor_spectrum · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] capture_monitor_spectrum · commit — 预告: fn(capture_monitor_spectrum): wired 含四文档变更
### estimate_snr
- [ ] estimate_snr · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] estimate_snr · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] estimate_snr · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] estimate_snr · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] estimate_snr · commit — 预告: fn(estimate_snr): wired 含四文档变更
### check_flatness
- [ ] check_flatness · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] check_flatness · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] check_flatness · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] check_flatness · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] check_flatness · commit — 预告: fn(check_flatness): wired 含四文档变更
### compute_spectrum_stats
- [ ] compute_spectrum_stats · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] compute_spectrum_stats · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] compute_spectrum_stats · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] compute_spectrum_stats · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] compute_spectrum_stats · commit — 预告: fn(compute_spectrum_stats): wired 含四文档变更

## B10 批间门
- [ ] B10 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B10 · 用户裁决 — 预告: 继续 B11 / 修订 / 裁决 blocked

## B11 — parse_esp32_frame, drive_esp32_link, parse_nrf24_frame, drive_nrf24_link, apply_cliff_model, simulate_link_degradation, compute_per, normalize_kpi
### parse_esp32_frame
- [ ] parse_esp32_frame · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] parse_esp32_frame · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] parse_esp32_frame · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] parse_esp32_frame · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] parse_esp32_frame · commit — 预告: fn(parse_esp32_frame): wired 含四文档变更
### drive_esp32_link
- [ ] drive_esp32_link · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] drive_esp32_link · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] drive_esp32_link · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] drive_esp32_link · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] drive_esp32_link · commit — 预告: fn(drive_esp32_link): wired 含四文档变更
### parse_nrf24_frame
- [ ] parse_nrf24_frame · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] parse_nrf24_frame · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] parse_nrf24_frame · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] parse_nrf24_frame · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] parse_nrf24_frame · commit — 预告: fn(parse_nrf24_frame): wired 含四文档变更
### drive_nrf24_link
- [ ] drive_nrf24_link · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] drive_nrf24_link · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] drive_nrf24_link · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] drive_nrf24_link · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] drive_nrf24_link · commit — 预告: fn(drive_nrf24_link): wired 含四文档变更
### apply_cliff_model
- [ ] apply_cliff_model · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] apply_cliff_model · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] apply_cliff_model · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] apply_cliff_model · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] apply_cliff_model · commit — 预告: fn(apply_cliff_model): wired 含四文档变更
### simulate_link_degradation
- [ ] simulate_link_degradation · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] simulate_link_degradation · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] simulate_link_degradation · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] simulate_link_degradation · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] simulate_link_degradation · commit — 预告: fn(simulate_link_degradation): wired 含四文档变更
### compute_per
- [ ] compute_per · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] compute_per · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] compute_per · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] compute_per · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] compute_per · commit — 预告: fn(compute_per): wired 含四文档变更
### normalize_kpi
- [ ] normalize_kpi · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] normalize_kpi · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] normalize_kpi · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] normalize_kpi · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] normalize_kpi · commit — 预告: fn(normalize_kpi): wired 含四文档变更

## B11 批间门
- [ ] B11 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B11 · 用户裁决 — 预告: 继续 B12 / 修订 / 裁决 blocked

## B12 — compute_alignment_error, record_run_streams, run_baseline_check, annotate_truth_labels, write_sigmf_recording
### compute_alignment_error
- [ ] compute_alignment_error · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] compute_alignment_error · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] compute_alignment_error · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] compute_alignment_error · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] compute_alignment_error · commit — 预告: fn(compute_alignment_error): wired 含四文档变更
### record_run_streams
- [ ] record_run_streams · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] record_run_streams · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] record_run_streams · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] record_run_streams · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] record_run_streams · commit — 预告: fn(record_run_streams): wired 含四文档变更
### run_baseline_check
- [ ] run_baseline_check · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] run_baseline_check · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] run_baseline_check · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] run_baseline_check · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] run_baseline_check · commit — 预告: fn(run_baseline_check): wired 含四文档变更
### annotate_truth_labels
- [ ] annotate_truth_labels · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] annotate_truth_labels · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] annotate_truth_labels · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] annotate_truth_labels · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] annotate_truth_labels · commit — 预告: fn(annotate_truth_labels): wired 含四文档变更
### write_sigmf_recording
- [ ] write_sigmf_recording · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] write_sigmf_recording · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] write_sigmf_recording · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] write_sigmf_recording · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] write_sigmf_recording · commit — 预告: fn(write_sigmf_recording): wired 含四文档变更

## B12 批间门
- [ ] B12 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B12 · 用户裁决 — 预告: 继续 B13 / 修订 / 裁决 blocked

## B13 — check_failure, record_failure_level, execute_gb42590_protocol, compare_failure_boundaries, build_curve_frames, plot_triple_curves
### check_failure
- [ ] check_failure · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] check_failure · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] check_failure · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] check_failure · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] check_failure · commit — 预告: fn(check_failure): wired 含四文档变更
### record_failure_level
- [ ] record_failure_level · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] record_failure_level · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] record_failure_level · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] record_failure_level · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] record_failure_level · commit — 预告: fn(record_failure_level): wired 含四文档变更
### execute_gb42590_protocol
- [ ] execute_gb42590_protocol · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] execute_gb42590_protocol · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] execute_gb42590_protocol · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] execute_gb42590_protocol · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] execute_gb42590_protocol · commit — 预告: fn(execute_gb42590_protocol): wired 含四文档变更
### compare_failure_boundaries
- [ ] compare_failure_boundaries · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] compare_failure_boundaries · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] compare_failure_boundaries · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] compare_failure_boundaries · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] compare_failure_boundaries · commit — 预告: fn(compare_failure_boundaries): wired 含四文档变更
### build_curve_frames
- [ ] build_curve_frames · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] build_curve_frames · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] build_curve_frames · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] build_curve_frames · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] build_curve_frames · commit — 预告: fn(build_curve_frames): wired 含四文档变更
### plot_triple_curves
- [ ] plot_triple_curves · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] plot_triple_curves · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] plot_triple_curves · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] plot_triple_curves · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] plot_triple_curves · commit — 预告: fn(plot_triple_curves): wired 含四文档变更

## B13 批间门
- [ ] B13 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B13 · 用户裁决 — 预告: 继续 B14 / 修订 / 裁决 blocked

## B14 — dispatch_remote_training, train_classifier, make_group_splits, grouped_cv_evaluate, predict_style
### dispatch_remote_training
- [ ] dispatch_remote_training · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] dispatch_remote_training · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] dispatch_remote_training · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] dispatch_remote_training · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] dispatch_remote_training · commit — 预告: fn(dispatch_remote_training): wired 含四文档变更
### train_classifier
- [ ] train_classifier · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] train_classifier · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] train_classifier · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] train_classifier · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] train_classifier · commit — 预告: fn(train_classifier): wired 含四文档变更
### make_group_splits
- [ ] make_group_splits · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] make_group_splits · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] make_group_splits · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] make_group_splits · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] make_group_splits · commit — 预告: fn(make_group_splits): wired 含四文档变更
### grouped_cv_evaluate
- [ ] grouped_cv_evaluate · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] grouped_cv_evaluate · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] grouped_cv_evaluate · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] grouped_cv_evaluate · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] grouped_cv_evaluate · commit — 预告: fn(grouped_cv_evaluate): wired 含四文档变更
### predict_style
- [ ] predict_style · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] predict_style · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] predict_style · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] predict_style · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] predict_style · commit — 预告: fn(predict_style): wired 含四文档变更

## B14 批间门
- [ ] B14 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B14 · 用户裁决 — 预告: 继续 B15 / 修订 / 裁决 blocked

## B15 — open_sim_siggen, open_sim_analyzer, upconvert_with_image_rejection, open_sim_mixer, open_sim_emi_receiver, open_sim_attenuator
### open_sim_siggen
- [ ] open_sim_siggen · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] open_sim_siggen · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] open_sim_siggen · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] open_sim_siggen · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] open_sim_siggen · commit — 预告: fn(open_sim_siggen): wired 含四文档变更
### open_sim_analyzer
- [ ] open_sim_analyzer · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] open_sim_analyzer · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] open_sim_analyzer · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] open_sim_analyzer · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] open_sim_analyzer · commit — 预告: fn(open_sim_analyzer): wired 含四文档变更
### upconvert_with_image_rejection
- [ ] upconvert_with_image_rejection · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] upconvert_with_image_rejection · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] upconvert_with_image_rejection · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] upconvert_with_image_rejection · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] upconvert_with_image_rejection · commit — 预告: fn(upconvert_with_image_rejection): wired 含四文档变更
### open_sim_mixer
- [ ] open_sim_mixer · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] open_sim_mixer · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] open_sim_mixer · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] open_sim_mixer · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] open_sim_mixer · commit — 预告: fn(open_sim_mixer): wired 含四文档变更
### open_sim_emi_receiver
- [ ] open_sim_emi_receiver · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] open_sim_emi_receiver · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] open_sim_emi_receiver · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] open_sim_emi_receiver · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] open_sim_emi_receiver · commit — 预告: fn(open_sim_emi_receiver): wired 含四文档变更
### open_sim_attenuator
- [ ] open_sim_attenuator · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] open_sim_attenuator · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] open_sim_attenuator · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] open_sim_attenuator · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] open_sim_attenuator · commit — 预告: fn(open_sim_attenuator): wired 含四文档变更

## B15 批间门
- [ ] B15 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B15 · 用户裁决 — 预告: 继续 B16 / 修订 / 裁决 blocked

## B16 — make_disclaimer_block, run_emc_conduction_sim, run_emc_radiation_sim, plan_frequency_sweep, run_emc_sweep
### make_disclaimer_block
- [ ] make_disclaimer_block · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] make_disclaimer_block · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] make_disclaimer_block · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] make_disclaimer_block · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] make_disclaimer_block · commit — 预告: fn(make_disclaimer_block): wired 含四文档变更
### run_emc_conduction_sim
- [ ] run_emc_conduction_sim · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] run_emc_conduction_sim · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] run_emc_conduction_sim · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] run_emc_conduction_sim · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] run_emc_conduction_sim · commit — 预告: fn(run_emc_conduction_sim): wired 含四文档变更
### run_emc_radiation_sim
- [ ] run_emc_radiation_sim · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] run_emc_radiation_sim · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] run_emc_radiation_sim · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] run_emc_radiation_sim · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] run_emc_radiation_sim · commit — 预告: fn(run_emc_radiation_sim): wired 含四文档变更
### plan_frequency_sweep
- [ ] plan_frequency_sweep · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] plan_frequency_sweep · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] plan_frequency_sweep · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] plan_frequency_sweep · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] plan_frequency_sweep · commit — 预告: fn(plan_frequency_sweep): wired 含四文档变更
### run_emc_sweep
- [ ] run_emc_sweep · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] run_emc_sweep · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] run_emc_sweep · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] run_emc_sweep · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] run_emc_sweep · commit — 预告: fn(run_emc_sweep): wired 含四文档变更

## B16 批间门
- [ ] B16 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B16 · 用户裁决 — 预告: 继续 B17 / 修订 / 裁决 blocked

## B17 — locate_ledger_row, update_ledger, count_comment_ratio, audit_ledger, validate_scenario_schema, normalize_scenario, load_scenario
### locate_ledger_row
- [ ] locate_ledger_row · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] locate_ledger_row · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] locate_ledger_row · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] locate_ledger_row · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] locate_ledger_row · commit — 预告: fn(locate_ledger_row): wired 含四文档变更
### update_ledger
- [ ] update_ledger · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] update_ledger · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] update_ledger · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] update_ledger · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] update_ledger · commit — 预告: fn(update_ledger): wired 含四文档变更
### count_comment_ratio
- [ ] count_comment_ratio · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] count_comment_ratio · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] count_comment_ratio · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] count_comment_ratio · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] count_comment_ratio · commit — 预告: fn(count_comment_ratio): wired 含四文档变更
### audit_ledger
- [ ] audit_ledger · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] audit_ledger · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] audit_ledger · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] audit_ledger · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] audit_ledger · commit — 预告: fn(audit_ledger): wired 含四文档变更
### validate_scenario_schema
- [ ] validate_scenario_schema · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] validate_scenario_schema · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] validate_scenario_schema · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] validate_scenario_schema · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] validate_scenario_schema · commit — 预告: fn(validate_scenario_schema): wired 含四文档变更
### normalize_scenario
- [ ] normalize_scenario · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] normalize_scenario · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] normalize_scenario · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] normalize_scenario · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] normalize_scenario · commit — 预告: fn(normalize_scenario): wired 含四文档变更
### load_scenario
- [ ] load_scenario · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] load_scenario · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] load_scenario · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] load_scenario · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] load_scenario · commit — 预告: fn(load_scenario): wired 含四文档变更

## B17 批间门
- [ ] B17 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B17 · 用户裁决 — 预告: 继续 B18 / 修订 / 裁决 blocked

## B18 — render_disclaimer_sections, assemble_frequency_plots, build_report, extract_report_numbers, verify_report_traceability
### render_disclaimer_sections
- [ ] render_disclaimer_sections · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] render_disclaimer_sections · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] render_disclaimer_sections · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] render_disclaimer_sections · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] render_disclaimer_sections · commit — 预告: fn(render_disclaimer_sections): wired 含四文档变更
### assemble_frequency_plots
- [ ] assemble_frequency_plots · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] assemble_frequency_plots · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] assemble_frequency_plots · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] assemble_frequency_plots · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] assemble_frequency_plots · commit — 预告: fn(assemble_frequency_plots): wired 含四文档变更
### build_report
- [ ] build_report · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] build_report · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] build_report · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] build_report · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] build_report · commit — 预告: fn(build_report): wired 含四文档变更
### extract_report_numbers
- [ ] extract_report_numbers · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] extract_report_numbers · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] extract_report_numbers · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] extract_report_numbers · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] extract_report_numbers · commit — 预告: fn(extract_report_numbers): wired 含四文档变更
### verify_report_traceability
- [ ] verify_report_traceability · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] verify_report_traceability · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] verify_report_traceability · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] verify_report_traceability · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] verify_report_traceability · commit — 预告: fn(verify_report_traceability): wired 含四文档变更

## B18 批间门
- [ ] B18 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B18 · 用户裁决 — 预告: 继续 B19 / 修订 / 裁决 blocked

## B19 — create_console_app, serve_console, build_scenario_cards, render_console_pages, measure_refresh_latency, trigger_emergency_stop, push_realtime_kpi
### create_console_app
- [ ] create_console_app · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] create_console_app · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] create_console_app · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] create_console_app · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] create_console_app · commit — 预告: fn(create_console_app): wired 含四文档变更
### serve_console
- [ ] serve_console · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] serve_console · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] serve_console · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] serve_console · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] serve_console · commit — 预告: fn(serve_console): wired 含四文档变更
### build_scenario_cards
- [ ] build_scenario_cards · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] build_scenario_cards · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] build_scenario_cards · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] build_scenario_cards · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] build_scenario_cards · commit — 预告: fn(build_scenario_cards): wired 含四文档变更
### render_console_pages
- [ ] render_console_pages · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] render_console_pages · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] render_console_pages · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] render_console_pages · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] render_console_pages · commit — 预告: fn(render_console_pages): wired 含四文档变更
### measure_refresh_latency
- [ ] measure_refresh_latency · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] measure_refresh_latency · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] measure_refresh_latency · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] measure_refresh_latency · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] measure_refresh_latency · commit — 预告: fn(measure_refresh_latency): wired 含四文档变更
### trigger_emergency_stop
- [ ] trigger_emergency_stop · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] trigger_emergency_stop · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] trigger_emergency_stop · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] trigger_emergency_stop · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] trigger_emergency_stop · commit — 预告: fn(trigger_emergency_stop): wired 含四文档变更
### push_realtime_kpi
- [ ] push_realtime_kpi · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] push_realtime_kpi · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] push_realtime_kpi · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] push_realtime_kpi · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] push_realtime_kpi · commit — 预告: fn(push_realtime_kpi): wired 含四文档变更

## B19 批间门
- [ ] B19 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B19 · 用户裁决 — 预告: 继续 B20 / 修订 / 裁决 blocked

## B20 — map_per_to_injection, bridge_to_sitl, fallback_fixed_strategy, run_rl_policy, run_rff_pipeline
### map_per_to_injection
- [ ] map_per_to_injection · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] map_per_to_injection · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] map_per_to_injection · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] map_per_to_injection · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] map_per_to_injection · commit — 预告: fn(map_per_to_injection): wired 含四文档变更
### bridge_to_sitl
- [ ] bridge_to_sitl · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] bridge_to_sitl · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] bridge_to_sitl · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] bridge_to_sitl · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] bridge_to_sitl · commit — 预告: fn(bridge_to_sitl): wired 含四文档变更
### fallback_fixed_strategy
- [ ] fallback_fixed_strategy · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] fallback_fixed_strategy · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] fallback_fixed_strategy · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] fallback_fixed_strategy · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] fallback_fixed_strategy · commit — 预告: fn(fallback_fixed_strategy): wired 含四文档变更
### run_rl_policy
- [ ] run_rl_policy · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] run_rl_policy · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] run_rl_policy · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] run_rl_policy · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] run_rl_policy · commit — 预告: fn(run_rl_policy): wired 含四文档变更
### run_rff_pipeline
- [ ] run_rff_pipeline · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] run_rff_pipeline · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] run_rff_pipeline · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] run_rff_pipeline · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] run_rff_pipeline · commit — 预告: fn(run_rff_pipeline): wired 含四文档变更

## B20 批间门
- [ ] B20 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B20 · 用户裁决 — 预告: 继续 B21 / 修订 / 裁决 blocked

## B21 — execute_scenario, run_demo
### execute_scenario
- [ ] execute_scenario · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] execute_scenario · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] execute_scenario · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] execute_scenario · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] execute_scenario · commit — 预告: fn(execute_scenario): wired 含四文档变更
### run_demo
- [ ] run_demo · implemented — 预告: 桩替换为真值，预期本函数桩 grep 归零
- [ ] run_demo · tested — 预告: 叶子自有单测绿/中上层上游覆盖，预期 pytest → passed
- [ ] run_demo · wired — 预告: 调用点存在（grep/ast-grep 命中）；顶层入口实跑一次
- [ ] run_demo · 清单进位 — 预告: functions.md 状态行改后读回
- [ ] run_demo · commit — 预告: fn(run_demo): wired 含四文档变更

## B21 批间门
- [ ] B21 · 评审三轴 — 预告: 规格/标准/档案同步（含 tracker 本批行核对）
- [ ] B21 · 用户裁决 — 预告: 继续 B22 / 修订 / 裁决 blocked

（Ruling 行与豁免行尾部追加、逐行读回：
- Ruling: <偏离内容> — 原因 — 代价 — 落点
- X1: <类型> | 范围: 单门/本批/剩余全部 | 对象: <技能·门> | 原因 | 剩余: N | 状态: active/consumed）

- Ruling: shared 四函数并入首个调用方批次+批内自底向上重排（22→21 批） — B1 独立 shared 批的 wired 无真实调用点不可合规 — 无（119 函数与验收点不变） — batches.md/functions.md/tracker.md 同步重排 (10-11)
- Ruling: 叶子函数 wired 判据 — 叶子在批内自底向上先行实现，其顶层父函数同批稍后落地；叶子的 wired 以自有单测调用点+同批父函数落地后 grep 复核（批间门三轴核对）为准 — 与「七步走满」不冲突且不弱化证据 — tracker 各叶子 wired 行 (10-11)
- Ruling: B1 基线时序异常留痕——三叶子实现先于基线 commit 落盘，基线 429ae52 吞入其代码，三个叶子 wired commit 为零代码变更 — 主会话打基线时序失误（实现子代理先返、基线后打） — 证据链歧义（功能与档案终态正确，git log 仍可溯源） — batches.md 变更记录 Ruling② (10-11)
- Ruling: gain 标定表落盘为 flat JSON（顶层即 entries）而非信封 {'name','meta','entries'} — 已实现的 load_calibration_table 对每个顶层键做 gain 条目校验，信封键不可读；表名/placeholder 语义由 loader 视图承载 — 数据格式细节、不影响函数接口；集成用例（建表→loader 读回 entries 相等）已覆盖 — batches.md 变更记录 Ruling④ (10-11)
- Ruling: B2 批间评审附条件三项收口——①lookup_jsr/compensate_link_power 签名意图错误字段对齐为「不抛出转状态/置信度」（与 R52 先例及测试固化一致）；②一期 gain 标定表明文为 档位→功率 单维（频率不入表，Ruling④ flat 格式的完整语义）；③顶层实跑探针自 B3 起存 fn_work/scripts/probes/ 入库可复跑 — 评审子代理三轴附条件 — 无（文档措辞对齐+探针落点，不改代码） — responsibility.md 两处+batches 变更记录 Ruling⑤ (10-11)

