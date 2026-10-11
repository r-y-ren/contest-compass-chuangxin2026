"""红线总闸：功率/频段/声明三查，任一失败即拒（不可跳过）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

from .check_band_whitelist import check_band_whitelist
from .check_env_declarations import check_env_declarations
from .check_power_cap import check_power_cap

# 条款前缀：合并后的拒绝原因清单必须逐条指明违反哪一条红线
_CLAUSE_PREFIX = {
    "power": "[power]",
    "band": "[band]",
    "declarations": "[declaration]",
}


def _merge_violations(clause: str, sub_violations: list) -> list[str]:
    """把子检查违例统一转为带条款前缀的字符串清单（band 子检查的 dict 违例取其 reason）。"""
    prefix = _CLAUSE_PREFIX[clause]
    merged: list[str] = []
    for item in sub_violations:
        reason = item.get("reason") if isinstance(item, dict) else item
        merged.append(f"{prefix} {reason}")
    return merged


def guard_compliance(config: dict) -> dict:
    """红线总闸：功率→频段→声明依次三查，任一违例即整体拒绝（不可跳过、不抛出）。

    输入约定（缺节按该节违例处理，任何形状问题转为对应条款违例，不抛出）:
      config: {
        "power": {"power_dbm": float, 可选 "cap_dbm"/"waiver"},
        "bands": [(start, stop), ...]（MHz，也兼容已成形 dict 的频段配置）,
        "declarations": {"shielded_box": True, "dut_scope": "self_built"},
      }

    输出: {
        "status": "pass" | "rejected",
        "checks": {"power": ..., "band": ..., "declarations": ...}（各子检查原结果）,
        "violations": ["[power] ...", "[band] ...", "[declaration] ..."]（拒绝原因清单）,
        "waiver_audits": [审计条目]（有效豁免不构成拒绝，但审计条目必须透传）,
        "declarations_echo": [配置显式携带的必填声明名清单],
      }

    无跳过路径：函数只收 config 一个参数，三查无条件全部执行。
    """
    # config 本身形状错（非 dict）→ 视为三节全缺，三条款全违例转拒，不抛出
    sections = config if isinstance(config, dict) else {}

    # ① 功率红线：豁免凭证随 power 节携带，有效性判定与审计条目生成归叶子检查
    power_section = sections.get("power")
    waiver = power_section.get("waiver") if isinstance(power_section, dict) else None
    power_check = check_power_cap(power_section, waiver=waiver)

    # ② 频段白名单：约定 bands 直接为二元组列表；兼容 {"bands": [...]} 形状的频段配置
    bands_section = sections.get("bands")
    band_check = (
        check_band_whitelist(bands_section)
        if isinstance(bands_section, dict)
        else check_band_whitelist({"bands": bands_section})
    )

    # ③ 环境与对象声明
    declarations_section = sections.get("declarations")
    declarations_check = check_env_declarations(declarations_section)

    checks = {
        "power": power_check,
        "band": band_check,
        "declarations": declarations_check,
    }

    # 任一子检查 violation 即整体拒绝；waived 不构成拒绝，但审计条目必须透传到结果
    violations: list[str] = []
    for clause, sub in checks.items():
        if sub["status"] == "violation":
            violations.extend(_merge_violations(clause, sub.get("violations", [])))
    waiver_audits = [
        sub["waiver_audit"] for sub in checks.values() if sub.get("waiver_audit") is not None
    ]

    declared = declarations_section if isinstance(declarations_section, dict) else {}
    declarations_echo = [
        name for name in declarations_check["required"] if name in declared
    ]

    return {
        "status": "rejected" if violations else "pass",
        "checks": checks,
        "violations": violations,
        "waiver_audits": waiver_audits,
        "declarations_echo": declarations_echo,
    }
