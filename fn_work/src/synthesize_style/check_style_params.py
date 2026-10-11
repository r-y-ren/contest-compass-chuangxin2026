"""样式参数取值域校验（频率/带宽≤56MHz/功率红线内）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math

# 六类样式白名单；带限类（bandwidth_hz 必填）样式集合。
STYLE_WHITELIST = frozenset(
    {"tone", "sweep", "chirp", "bandlimited_noise", "partial_band", "pulse"}
)
BANDWIDTH_REQUIRED_STYLES = frozenset({"bandlimited_noise", "partial_band", "pulse"})

# 取值域常量：带宽上限 56MHz；功率域 [-100, 0] dBm（0 dBm 为红线，等号通过）。
BANDWIDTH_HZ_MAX = 56e6
POWER_DBM_MIN = -100.0
POWER_DBM_MAX = 0.0

# 已知数值键（sample_rate_hz 供 |freq|≤fs/2 提示级判定）；其余键按未知键提示不拒。
_NUMERIC_KEYS = (
    "freq_hz",
    "bandwidth_hz",
    "power_dbm",
    "duration_s",
    "duty_cycle",
    "repeats",
    "sample_rate_hz",
)
_KNOWN_KEYS = frozenset({"style", *_NUMERIC_KEYS})


def _is_finite_real(value: object) -> bool:
    """有限实数判定：int/float 且非 bool；float 还须有限（NaN/±inf 一律非法）。

    bool 是 int 的子类但语义上是开关而非量值，故显式排除；
    int 天然有限（不经 float 转换，天文数字也不抛 OverflowError）。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _real_field(params: dict, key: str, errors: list[str]) -> float | None:
    """取数值键：缺失返回 None 不报错；非法（NaN/inf/bool/非数值/超 float 范围）
    记一条含键名与值的 error 并返回 None（后续域判定跳过，避免重复报错）。"""
    if key not in params:
        return None
    value = params[key]
    if not _is_finite_real(value):
        errors.append(f"{key} 数值非法（NaN/inf/bool/非数值），实际值 {value!r}")
        return None
    try:
        return float(value)
    except OverflowError:
        errors.append(f"{key} 数值非法（超出 float 可表示范围），实际值 {value!r}")
        return None


def check_style_params(params: dict) -> dict:
    """样式参数取值域校验纯函数（只判域不合成，永不抛出）。

    输入: params: dict，支持键与规则——
      - style: str，六类白名单 {'tone','sweep','chirp','bandlimited_noise',
        'partial_band','pulse'}；缺失/非 str/白名单外（含大小写不符）→ 一条 error；
      - freq_hz: 频率偏移或中心 Hz，允许负值（基带偏移）；|freq|>sample_rate_hz/2
        仅记 warning 不入 errors（复信号可超 Nyquist，提示级不拒）；
      - bandwidth_hz: >0 且 ≤56e6 Hz；带限类（bandlimited_noise/partial_band/
        pulse 载波类）必填，缺失即 error；
      - power_dbm: 须满足 -100 ≤ power_dbm ≤ 0.0 dBm（0 dBm 为合规红线，等号通过）；
      - duration_s: >0；duty_cycle: 严格落于开区间 (0,1)（pulse 占空比）；
      - repeats: 正 int（拒 bool 与 float）；
      - sample_rate_hz: >0（供 |freq|≤fs/2 提示级判定）；
      - 任意数值键 NaN/±inf/bool/非数值 → 该键一条 error（含键名与值）；
        未知键 → 一条 warning（不拒）。
    输出: {'errors': [str]（非空=整体拒），'warnings': [str]}。
    错误: params 非 dict → errors 单条（不抛）。
    """
    if not isinstance(params, dict):
        return {
            "errors": [
                f"输入形状错: params 应为 dict，实际为 {type(params).__name__}: {params!r}"
            ],
            "warnings": [],
        }

    errors: list[str] = []
    warnings: list[str] = []

    style = params.get("style")
    if "style" not in params:
        errors.append(f"style 缺失（白名单 {sorted(STYLE_WHITELIST)}）")
    elif not isinstance(style, str):
        errors.append(
            f"style 应为 str（白名单 {sorted(STYLE_WHITELIST)}），"
            f"实际为 {type(style).__name__}: {style!r}"
        )
    elif style not in STYLE_WHITELIST:
        errors.append(f"style 未知样式 {style!r}（白名单 {sorted(STYLE_WHITELIST)}）")

    freq_hz = _real_field(params, "freq_hz", errors)

    bandwidth_hz = _real_field(params, "bandwidth_hz", errors)
    if bandwidth_hz is not None and not 0 < bandwidth_hz <= BANDWIDTH_HZ_MAX:
        errors.append(
            f"bandwidth_hz 须为正且 ≤{BANDWIDTH_HZ_MAX} Hz，实际值 {bandwidth_hz!r}"
        )

    power_dbm = _real_field(params, "power_dbm", errors)
    if power_dbm is not None and not POWER_DBM_MIN <= power_dbm <= POWER_DBM_MAX:
        errors.append(
            f"power_dbm 须满足 {POWER_DBM_MIN} ≤ power_dbm ≤ {POWER_DBM_MAX} dBm"
            f"（0 dBm 为合规红线，等号通过），实际值 {power_dbm!r}"
        )

    duration_s = _real_field(params, "duration_s", errors)
    if duration_s is not None and duration_s <= 0:
        errors.append(f"duration_s 须为正（秒），实际值 {duration_s!r}")

    duty_cycle = _real_field(params, "duty_cycle", errors)
    if duty_cycle is not None and not 0.0 < duty_cycle < 1.0:
        errors.append(f"duty_cycle 须严格落于开区间 (0, 1)，实际值 {duty_cycle!r}")

    if "repeats" in params:
        repeats = params["repeats"]
        if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats <= 0:
            errors.append(f"repeats 须为正 int（拒 bool），实际值 {repeats!r}")

    sample_rate_hz = _real_field(params, "sample_rate_hz", errors)
    if sample_rate_hz is not None and sample_rate_hz <= 0:
        errors.append(f"sample_rate_hz 须为正，实际值 {sample_rate_hz!r}")
        sample_rate_hz = None

    # 带限类样式 bandwidth_hz 必填（缺失即拒；已存在但非法时上面已报数值/域错，不重复）。
    if style in BANDWIDTH_REQUIRED_STYLES and "bandwidth_hz" not in params:
        errors.append(f"bandwidth_hz 必填（{style} 为带限类样式），当前缺失")

    # |freq|>fs/2：提示级——复信号可超 Nyquist，记 warning 不入 errors。
    if (
        freq_hz is not None
        and sample_rate_hz is not None
        and abs(freq_hz) > sample_rate_hz / 2
    ):
        warnings.append(
            f"freq_hz {freq_hz!r} Hz 超出采样率/2（sample_rate_hz/2 = "
            f"{(sample_rate_hz / 2)!r} Hz）——复信号可超，提示级不拒"
        )

    for key, value in params.items():
        if key not in _KNOWN_KEYS:
            warnings.append(f"未知参数键 {key!r}（值 {value!r}）——不拒，仅提示")

    return {"errors": errors, "warnings": warnings}
