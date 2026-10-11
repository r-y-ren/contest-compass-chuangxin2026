"""功率上限校验（≤0dBm 量级+豁免审计）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

from datetime import datetime, timezone

DEFAULT_CAP_DBM = 0.0
_WAIVER_REQUIRED_KEYS = ("id", "reason", "approved_by")


def _waiver_invalid_reason(waiver: object) -> str | None:
    """返回豁免凭证无效的原因；有效则返回 None。id/reason/approved_by 三键齐全且非空才算有效。"""
    if not isinstance(waiver, dict):
        return f"豁免凭证应为 dict，实际为 {type(waiver).__name__}"
    missing = [key for key in _WAIVER_REQUIRED_KEYS if not waiver.get(key)]
    if missing:
        return f"豁免凭证缺失或为空键: {missing}"
    return None


def _build_waiver_audit(waiver: dict) -> dict:
    """生成可审计豁免条目：豁免编号/原因/批准人/UTC ISO 时间戳。"""
    return {
        "id": waiver["id"],
        "reason": waiver["reason"],
        "approved_by": waiver["approved_by"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def check_power_cap(power_config: dict, waiver: dict | None = None) -> dict:
    """功率上限纯校验：power_dbm 不得超过 cap_dbm（默认 0.0，合规红线）。

    - 超限即违例；持有完整豁免凭证（id/reason/approved_by 三键齐全）时返回
      waived，并生成含时间戳的审计条目（豁免必须可审计），超限事实仍留在
      violations 中供追溯。
    - cap_dbm 覆盖仅允许收紧（不得高于默认 0.0）；非法覆盖（数值更高或非数值）
      一律回退默认 0.0 判定，并记违例说明——红线不允许借覆盖参数放松。
    - 不抛异常：一切结果（含输入形状错）走返回值，由上层总闸转拒。
    """
    cap_dbm = DEFAULT_CAP_DBM
    violations: list[str] = []

    if not isinstance(power_config, dict):
        return {
            "status": "violation",
            "cap_dbm": cap_dbm,
            "power_dbm": None,
            "violations": [
                f"输入形状错: power_config 应为 dict，实际为 {type(power_config).__name__}"
            ],
            "waiver_audit": None,
        }

    override = power_config.get("cap_dbm")
    if override is not None:
        if isinstance(override, bool) or not isinstance(override, (int, float)):
            violations.append(
                f"cap_dbm 覆盖非法（非数值: {override!r}），按默认 {DEFAULT_CAP_DBM} dBm 判定"
            )
        elif override > DEFAULT_CAP_DBM:
            violations.append(
                f"cap_dbm 覆盖 {override} dBm 不得高于默认红线 {DEFAULT_CAP_DBM} dBm，"
                f"视为非法，按默认 {DEFAULT_CAP_DBM} dBm 判定"
            )
        else:
            cap_dbm = float(override)

    power = power_config.get("power_dbm")
    if isinstance(power, bool) or not isinstance(power, (int, float)):
        violations.append(
            f"输入形状错: 缺少或非法的 power_dbm（{power!r}），无法判定功率上限"
        )
        return {
            "status": "violation",
            "cap_dbm": cap_dbm,
            "power_dbm": power,
            "violations": violations,
            "waiver_audit": None,
        }

    over_limit = power > cap_dbm
    if over_limit:
        violations.append(
            f"功率超限: power_dbm={power} dBm 超过上限 {cap_dbm} dBm"
            f"（合规红线 ≤{DEFAULT_CAP_DBM} dBm）"
        )
        invalid_reason = _waiver_invalid_reason(waiver)
        if waiver is not None and invalid_reason is None:
            return {
                "status": "waived",
                "cap_dbm": cap_dbm,
                "power_dbm": power,
                "violations": violations,
                "waiver_audit": _build_waiver_audit(waiver),
            }
        if waiver is not None:
            violations.append(f"豁免凭证无效，不予豁免: {invalid_reason}")

    return {
        "status": "violation" if violations else "pass",
        "cap_dbm": cap_dbm,
        "power_dbm": power,
        "violations": violations,
        "waiver_audit": None,
    }
