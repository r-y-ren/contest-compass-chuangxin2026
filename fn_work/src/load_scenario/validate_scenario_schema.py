"""字段完整性与取值域校验（形状层面，不判红线）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
import re
from numbers import Integral

__all__ = [
    "BANDWIDTH_HZ_MAX",
    "BANDWIDTH_REQUIRED_STYLES",
    "ENVELOPE_KEY_WHITELIST",
    "SCENARIO_STYLE_WHITELIST",
    "SCENARIO_TYPE_WHITELIST",
    "ScenarioError",
    "validate_scenario_schema",
]


class ScenarioError(Exception):
    """场景装载失败（字段缺失/类型冲突/取值域非法），消息含字段名与原因。

    供 load_scenario 捕获后映射退出码 2 语义异常；本异常由本功能块两文件
    共用——定义于本文件，normalize_scenario 导入。
    """


# 七类样式白名单 = 六类在册样式 + 合成模式 'composite'（switch_style/
# synthesize_style 口径；大小写不敏感——strip().lower() 后比对）。
SCENARIO_STYLE_WHITELIST = frozenset(
    {"tone", "sweep", "chirp", "bandlimited_noise", "partial_band", "pulse", "composite"}
)

# 带限类样式（bandwidth_hz 必填）：bandlimited_noise / partial_band
# （场景装载口径；pulse 的带宽语义在 synthesize 侧由 check_style_params 另行把关）。
BANDWIDTH_REQUIRED_STYLES = frozenset({"bandlimited_noise", "partial_band"})

# 带宽取值上限 56 MHz（等号通过）。带宽越限属取值域错误由本校验把关；
# 功率/频段红线才归 guard_compliance。
BANDWIDTH_HZ_MAX = 56e6

# 在册场景类型（execute_scenario 分派白名单；strip().lower() 归一后比对）。
SCENARIO_TYPE_WHITELIST = frozenset({"gb42590", "distance", "custom", "emc"})

# 台账条目号形状（update_ledger 在册条目 'A1'..'L99'）。
_LEDGER_ENTRY_RE = re.compile(r"^[A-L]\d{1,2}$")

# 执行信封键（B21 高#1）：run_demo/execute_scenario 消费的编排参数随场景文件
# 进出——此前一律按未知键拒掉，场景文件路线整条死路。此处只做形状级检查
# （值域宽松归下游：distances 逐元素正数之外不重复 map 的深度校验、
# model_params/ladder 只查 dict 容器、sim_events 只查 list 容器）。
_ENVELOPE_KEYS = frozenset(
    {
        "scenario_type",
        "judge_min_samples",
        "dwell_s",
        "baseline_samples",
        "ledger_entry",
        "distances",
        "model_params",
        "ladder",
        "ladder_params",
        "record",
        "sim_events",
    }
)

# 场景在册键：'style'/'fs' 必填，其余可选。backend/judge_per_threshold 由
# normalize_scenario 消费（归一/缺省填充），故此处在册，但仅做形状级检查
# （backend 只查 str——'SIM' 等大小写变体须先通过本层再由 normalize 归一）。
_KNOWN_KEYS = frozenset(
    {
        "style",
        "fs",
        "freq_hz",
        "bandwidth_hz",
        "power_dbm",
        "duration_s",
        "duty_cycle",
        "repeats",
        "components",
        "backend",
        "judge_per_threshold",
    }
) | _ENVELOPE_KEYS

#: 兼容别名：执行信封键集合（测试/文档引用）。
ENVELOPE_KEY_WHITELIST = frozenset(_ENVELOPE_KEYS)


def _is_finite_real(value: object) -> bool:
    """有限实数判定：int/float 且非 bool；float 还须有限（NaN/±inf 一律非法）。

    bool 是 int 的子类但语义是开关而非量值，故显式排除（与
    check_style_params 同口径）；接受任意 numbers.Integral（np.int64 过）。
    """
    if isinstance(value, bool) or not isinstance(value, (Integral, float)):
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _number_field(raw: dict, key: str, errors: list) -> float | None:
    """取数值键：缺失返回 None 不报错；非法记一条含键名与值的 error 并返回
    None（后续域判定跳过，避免重复报错）。

    数值形状宽容（B17 中#4）：数字 str（可 float 且有限）同样通过——PyYAML
    1.1 口径不认 '1e6' 这类无点科学计数为 float 而给 str；通过后由
    normalize_scenario 数值化。不可解析 str/NaN/inf/bool/非数值才拒（消息
    注明数字 str 将被规范化）。
    """
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            parsed = None
        if parsed is None or not math.isfinite(parsed):
            errors.append(
                f"{key} 数值非法（NaN/inf/非数字 str），实际值 {value!r}"
                f"（数字 str 如 '1e6' 可通过并将被规范化为数值）"
            )
            return None
        return parsed
    if not _is_finite_real(value):
        errors.append(
            f"{key} 数值非法（NaN/inf/bool/非数值），实际值 {value!r}"
            f"（数字 str 如 '1e6' 可通过并将被规范化为数值）"
        )
        return None
    try:
        return float(value)
    except OverflowError:
        errors.append(f"{key} 数值非法（超出 float 可表示范围），实际值 {value!r}")
        return None


def _int_field(raw: dict, key: str, errors: list) -> None:
    """正 int 键形状检查：bool/float/非正一律拒（整数 str 如 '3' 宽容，同 repeats 口径）。

    执行信封键专用（judge_min_samples/baseline_samples）；只判形状，深度域
    （如每档窗口上限）归下游编排。
    """
    value = raw[key]
    if isinstance(value, str):
        try:
            candidate = float(value.strip())
        except ValueError:
            candidate = float("nan")
        if math.isfinite(candidate) and candidate.is_integer():
            value = int(candidate)
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        errors.append(
            f"{key} 须为正 int（拒 bool/float；整数 str 如 '3' 可宽容），实际值 {raw[key]!r}"
        )


def _envelope_number(value: object) -> float | None:
    """信封数值元素宽容解析：有限实数（拒 bool）或数字 str → float；其余 None。

    与 _number_field 同口径（B17 中#4：PyYAML 1.1 把 '1e6' 解析为 str），
    供 distances 逐元素检查复用；解析结果仅做形状判定，不写回场景。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (Integral, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _check_envelope_keys(raw: dict, errors: list) -> None:
    """执行信封键形状检查（B21 高#1）：在册即查形状，值域宽松归下游。

    - scenario_type: str 且 strip().lower() 落 {'gb42590','distance','custom',
      'emc'}（大小写不敏感，分派归一归 execute_scenario）；
    - judge_min_samples/baseline_samples: 正 int（bool/float 拒，整数 str 宽容）；
    - dwell_s: 数值 ≥0（正 float 或 0；数字 str 宽容）；
    - ledger_entry: str 匹配 ^[A-L]\\d{1,2}$（台账条目号形状）；
    - distances: list 且逐元素数值>0（深度域如非空/map 参数形状归
      map_distance_to_loss）；
    - model_params/ladder/ladder_params: dict（内部键形状归各消费方）；
    - record: bool；sim_events: list（元素形状归 simulate_link_degradation）。
    """
    if "scenario_type" in raw:
        raw_type = raw["scenario_type"]
        if not isinstance(raw_type, str) or raw_type.strip().lower() not in SCENARIO_TYPE_WHITELIST:
            errors.append(
                f"scenario_type 应为 str 四值 {sorted(SCENARIO_TYPE_WHITELIST)} 之一"
                f"（大小写不敏感），实际值 {raw_type!r}"
            )
    if "judge_min_samples" in raw:
        _int_field(raw, "judge_min_samples", errors)
    if "baseline_samples" in raw:
        _int_field(raw, "baseline_samples", errors)
    if "dwell_s" in raw:
        dwell = _number_field(raw, "dwell_s", errors)
        if dwell is not None and dwell < 0:
            errors.append(f"dwell_s 须为非负（正秒数或 0），实际值 {dwell!r}")
    if "ledger_entry" in raw:
        entry = raw["ledger_entry"]
        if not isinstance(entry, str) or not _LEDGER_ENTRY_RE.match(entry.strip()):
            errors.append(
                f"ledger_entry 应为 str 且匹配 ^[A-L]\\d{{1,2}}$（如 'B1'），"
                f"实际值 {entry!r}"
            )
    if "distances" in raw:
        raw_distances = raw["distances"]
        if not isinstance(raw_distances, list):
            errors.append(
                f"distances 应为 list（距离序列，米），"
                f"实际为 {type(raw_distances).__name__}: {raw_distances!r}"
            )
        else:
            for index, item in enumerate(raw_distances):
                number = _envelope_number(item)
                if number is None or number <= 0:
                    errors.append(
                        f"distances[{index}] 须为正数值（米，bool/NaN/inf/非数字拒），"
                        f"实际值 {item!r}"
                    )
    for dict_key in ("model_params", "ladder", "ladder_params"):
        if dict_key in raw and not isinstance(raw[dict_key], dict):
            errors.append(
                f"{dict_key} 应为 dict，"
                f"实际为 {type(raw[dict_key]).__name__}: {raw[dict_key]!r}"
            )
    if "record" in raw and not isinstance(raw["record"], bool):
        errors.append(
            f"record 应为 bool（录制开关），实际为 {type(raw['record']).__name__}: {raw['record']!r}"
        )
    if "sim_events" in raw and not isinstance(raw["sim_events"], list):
        errors.append(
            f"sim_events 应为 list（sim 注入事件序列），"
            f"实际为 {type(raw['sim_events']).__name__}: {raw['sim_events']!r}"
        )


def validate_scenario_schema(raw: dict) -> list:
    """字段完整性与取值域校验（形状层面，不判红线）。

    输入: raw: dict，场景 YAML 解析后的原始 dict，支持键与规则——
      - style: str，七类白名单 {'tone','sweep','chirp','bandlimited_noise',
        'partial_band','pulse','composite'}（switch_style/synthesize_style
        口径，大小写不敏感）；必填，缺失/非 str/白名单外 → 各一条 error；
      - fs: 必填，数值>0（采样率 Hz；数字 str 如 '1e6' 亦收——将被
        normalize_scenario 规范化为 float，B17 中#4，其余数值键同口径）；
      - freq_hz: 可选数值（允许负值——基带频偏，域归 synthesize 侧）；
      - bandwidth_hz: 可选，>0 且 ≤56e6（等号通过）；带限类
        （bandlimited_noise/partial_band）必填，缺失即 error；
      - power_dbm: 可选数值——只判数值形状，[-100,0] 功率红线归
        guard_compliance（check_power_cap），本校验绝不重复判红线；
      - duration_s: 可选，>0；
      - duty_cycle: 可选，严格落于开区间 (0,1)（pulse 占空比）；
      - repeats: 可选，正 int（拒 bool 与 float；整数 str 如 '3' 可宽容）；
      - judge_per_threshold: 可选数值，严格落于 (0,1)（PER 判据阈值域）；
      - backend: 可选，仅查 str 形状（白名单与小写归一归 normalize_scenario）；
      - 执行信封键（B21 高#1，可选，仅形状检查——值域宽松归下游，详见
        _check_envelope_keys）：scenario_type（str 四值 {'gb42590','distance',
        'custom','emc'}，大小写不敏感归一）、judge_min_samples/baseline_samples
        （正 int）、dwell_s（数值 ≥0）、ledger_entry（^[A-L]\\d{1,2}$）、
        distances（list 逐元素数值>0）、model_params/ladder/ladder_params
        （dict）、record（bool）、sim_events（list）；
      - components: composite 必填且为非空 list，元素须为 dict 并递归按
        同口径校验（错误前缀 'components[i]: '）；
      - 未知键 → 每键一条 error，消息形如「未知键: k」。
    输出: list[str] 错误清单（空列表 = 通过），逐字段汇总不抛出。
    错误: 不抛出；raw 非 dict → 返回单条错误的列表。
    """
    if not isinstance(raw, dict):
        return [
            f"输入形状错: 场景应为 dict（YAML 解析后的映射），"
            f"实际为 {type(raw).__name__}: {raw!r}"
        ]

    errors: list = []

    # ---- style：必填，七类白名单（大小写不敏感） ----
    style = raw.get("style")
    style_key = style.strip().lower() if isinstance(style, str) else None
    if "style" not in raw:
        errors.append(f"style 缺失（七类白名单 {sorted(SCENARIO_STYLE_WHITELIST)}）")
    elif not isinstance(style, str):
        errors.append(
            f"style 应为 str（七类白名单 {sorted(SCENARIO_STYLE_WHITELIST)}），"
            f"实际为 {type(style).__name__}: {style!r}"
        )
    elif style_key not in SCENARIO_STYLE_WHITELIST:
        errors.append(
            f"style 未知样式 {style!r}（七类白名单 "
            f"{sorted(SCENARIO_STYLE_WHITELIST)}，大小写不敏感）"
        )

    # ---- fs：必填，数值>0 ----
    if "fs" not in raw:
        errors.append("fs 缺失（采样率，数值>0 Hz）")
    else:
        fs = _number_field(raw, "fs", errors)
        if fs is not None and fs <= 0:
            errors.append(f"fs 须为正（采样率 Hz），实际值 {fs!r}")

    # ---- 可选数值键域检查（只判形状与数值，不判红线） ----
    # freq_hz：仅数值形状（负值=基带频偏合法；|freq|≤fs/2 提示归 synthesize 侧）。
    _number_field(raw, "freq_hz", errors)

    bandwidth_hz = _number_field(raw, "bandwidth_hz", errors)
    if bandwidth_hz is not None and not 0 < bandwidth_hz <= BANDWIDTH_HZ_MAX:
        errors.append(
            f"bandwidth_hz 须为正且 ≤{BANDWIDTH_HZ_MAX} Hz（56 MHz 上限，"
            f"等号通过），实际值 {bandwidth_hz!r}"
        )
    # 带限类样式 bandwidth_hz 必填（缺失即拒；已存在但非法时上面已报，不重复）。
    if (
        style_key in BANDWIDTH_REQUIRED_STYLES
        and "bandwidth_hz" not in raw
    ):
        errors.append(
            f"bandwidth_hz 必填（{style_key} 为带限类样式），当前缺失"
        )

    # power_dbm 只查数值形状；[-100,0] 功率红线归 guard_compliance。
    _number_field(raw, "power_dbm", errors)

    duration_s = _number_field(raw, "duration_s", errors)
    if duration_s is not None and duration_s <= 0:
        errors.append(f"duration_s 须为正（秒），实际值 {duration_s!r}")

    duty_cycle = _number_field(raw, "duty_cycle", errors)
    if duty_cycle is not None and not 0.0 < duty_cycle < 1.0:
        errors.append(f"duty_cycle 须严格落于开区间 (0, 1)，实际值 {duty_cycle!r}")

    if "repeats" in raw:
        repeats = raw["repeats"]
        if isinstance(repeats, str):
            # 整数 str 宽容（'3'/'3.0'——与 normalize_scenario 的 _to_positive_int
            # 同口径；小数 str 不宽容，落下方正 int 校验拒绝）。
            try:
                candidate = float(repeats.strip())
            except ValueError:
                candidate = float("nan")
            if math.isfinite(candidate) and candidate.is_integer():
                repeats = int(candidate)
        if (
            isinstance(repeats, bool)
            or not isinstance(repeats, Integral)
            or repeats <= 0
        ):
            errors.append(
                f"repeats 须为正 int（拒 bool；整数 str 如 '3' 可宽容），实际值 {raw['repeats']!r}"
            )

    judge = _number_field(raw, "judge_per_threshold", errors)
    if judge is not None and not 0.0 < judge < 1.0:
        errors.append(
            f"judge_per_threshold 须严格落于开区间 (0, 1)（PER 判据阈值），"
            f"实际值 {judge!r}"
        )

    # backend：仅形状检查（白名单域与小写归一归 normalize_scenario）。
    if "backend" in raw and not isinstance(raw["backend"], str):
        errors.append(
            f"backend 应为 str（白名单归一归 normalize），"
            f"实际为 {type(raw['backend']).__name__}: {raw['backend']!r}"
        )

    # ---- 执行信封键（B21 高#1）：形状级检查，值域宽松归下游 ----
    _check_envelope_keys(raw, errors)

    # ---- components：list 形状 + composite 必填非空 + 递归同口径 ----
    if "components" in raw:
        components = raw["components"]
        if not isinstance(components, list):
            errors.append(
                f"components 应为 list（composite 分量清单），"
                f"实际为 {type(components).__name__}: {components!r}"
            )
        else:
            for index, item in enumerate(components):
                if not isinstance(item, dict):
                    errors.append(
                        f"components[{index}] 应为 dict（分量场景），"
                        f"实际为 {type(item).__name__}: {item!r}"
                    )
            # 分量递归按同口径校验（嵌套字段缺失/域错逐条汇总，加前缀定位）。
            for index, item in enumerate(components):
                if isinstance(item, dict):
                    errors.extend(
                        f"components[{index}]: {sub}"
                        for sub in validate_scenario_schema(item)
                    )
    if style_key == "composite":
        if "components" not in raw:
            errors.append(
                "components 必填（style='composite' 合成模式），当前缺失"
            )
        elif isinstance(raw["components"], list) and not raw["components"]:
            errors.append("components 须为非空 list（style='composite'），当前为空")

    # ---- 未知键：每键一条 error（消息含「未知键: k」） ----
    for key in raw:
        if key not in _KNOWN_KEYS:
            errors.append(f"未知键: {key}")

    return errors
