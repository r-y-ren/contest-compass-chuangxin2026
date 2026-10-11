"""环境与对象声明纯校验（屏蔽盒标志+仅自建链路声明）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

REQUIRED_DECLARATIONS: list[str] = ["shielded_box", "dut_scope"]
_DUT_SCOPE_LEGAL_VALUE = "self_built"


def check_env_declarations(declarations: dict) -> dict:
    """环境与对象声明纯校验。

    场景必须显式携带两个必填声明：
      1. shielded_box=True —— 屏蔽盒环境确认；
      2. dut_scope='self_built' —— 仅测自建链路声明（真机为红线）。
    任一缺失或值不符即违例，违例清单逐项指明缺哪个声明/值是什么；不抛异常。

    输入: declarations: dict（期望含 shielded_box: bool、dut_scope: str；dut_scope 合法值仅 'self_built'）
    输出: dict {status: 'pass'|'violation', violations: list[str], required: list[str]}
    错误: 不抛出；declarations 为空 dict 或 None → 全部必填项违例。
    """
    violations: list[str] = []

    scene = declarations if isinstance(declarations, dict) else {}

    # ① shielded_box：必须显式为 True（严格布尔，真值数字不放行）
    if "shielded_box" not in scene:
        violations.append("缺少必填声明 'shielded_box'（屏蔽盒环境确认未显式携带）")
    elif scene["shielded_box"] is not True:
        violations.append(
            f"声明 'shielded_box' 必须为 True（屏蔽盒环境确认），实际为 {scene['shielded_box']!r}"
        )

    # ② dut_scope：合法值仅 'self_built'（真机声明红线）
    if "dut_scope" not in scene:
        violations.append("缺少必填声明 'dut_scope'（仅测自建链路声明未显式携带）")
    elif scene["dut_scope"] != _DUT_SCOPE_LEGAL_VALUE:
        violations.append(
            f"声明 'dut_scope' 仅允许 '{_DUT_SCOPE_LEGAL_VALUE}'（仅测自建链路），"
            f"实际为 {scene['dut_scope']!r}（真机声明红线）"
        )

    return {
        "status": "pass" if not violations else "violation",
        "violations": violations,
        "required": list(REQUIRED_DECLARATIONS),
    }
