"""功率上限校验（≤0dBm 量级+豁免审计）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
from datetime import datetime, timezone

DEFAULT_CAP_DBM = 0.0
_WAIVER_REQUIRED_KEYS = ("id", "reason", "approved_by")


def _is_finite_real(value: object) -> bool:
    """有限实数判定：int/float 且非 bool；float 还须有限（NaN/±inf 一律非法）。

    int 天然有限（不经过 float 转换，天文数字也不抛 OverflowError），
    bool 是 int 的子类但语义上是开关而非量值，故显式排除。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _is_valid_waiver_value(value: object) -> bool:
    """豁免键值有效性：必须是 str 且 strip() 后非空。

    键缺失（get → None）、None、非字符串（数字/bool 等）、纯空白
    （空格/制表符/换行等）一律无效——豁免凭证必须携带可审计的实际内容。
    """
    return isinstance(value, str) and value.strip() != ""


def _waiver_invalid_reason(waiver: object) -> str | None:
    """返回豁免凭证无效的原因；有效则返回 None。

    id/reason/approved_by 三键齐全且值为非空白字符串才算有效：
    缺键、None、非字符串、纯空白均判无效。
    """
    if not isinstance(waiver, dict):
        return f"豁免凭证应为 dict，实际为 {type(waiver).__name__}"
    missing = [
        key for key in _WAIVER_REQUIRED_KEYS if not _is_valid_waiver_value(waiver.get(key))
    ]
    if missing:
        return f"豁免凭证缺失、为空、纯空白或非字符串: {missing}"
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

    - 超限即违例；持有完整豁免凭证（id/reason/approved_by 三键齐全且值
      为非空白字符串）时返回 waived，并生成含时间戳的审计条目（豁免必须
      可审计），超限事实仍留在 violations 中供追溯。
    - cap_dbm 覆盖仅允许收紧（有限数值且 ≤ 默认 0.0）；非法覆盖（NaN/inf/
      非数值/bool，或数值更高=试图放松红线）一律回退默认 0.0 判定，并记
      违例说明——红线不允许借覆盖参数放松，NaN 覆盖也不得被当成"合法收紧"。
    - power_dbm 必须是有限实数（非 bool）：NaN/±inf 与非数值一样属于输入
      形状错，先行判 violation 且不可豁免——NaN 比较恒 False 不得放行。
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
        if not _is_finite_real(override):
            violations.append(
                f"cap_dbm 非法覆盖值（NaN/inf/非数值/bool），实际值 {override!r}，"
                f"回退按默认红线 {DEFAULT_CAP_DBM} dBm 判定"
            )
        elif override > DEFAULT_CAP_DBM:
            violations.append(
                f"cap_dbm 覆盖 {override} dBm 试图放松红线（不得高于默认 {DEFAULT_CAP_DBM} dBm），"
                f"视为非法，按默认 {DEFAULT_CAP_DBM} dBm 判定"
            )
        else:
            try:
                cap_dbm = float(override)
            except OverflowError:
                # 超出 float 可表示范围的天文数字 int：无法作为有效上限，回退默认
                violations.append(
                    f"cap_dbm 非法覆盖值（超出可表示范围），实际值 {override!r}，"
                    f"回退按默认红线 {DEFAULT_CAP_DBM} dBm 判定"
                )

    power = power_config.get("power_dbm")
    if not _is_finite_real(power):
        violations.append(
            f"输入形状错: power_dbm 功率值非法（NaN/inf/非数值），实际值 {power!r}，"
            "无法判定功率上限（形状错不可豁免）"
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
