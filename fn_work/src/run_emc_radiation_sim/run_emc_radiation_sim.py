"""EMC 辐射摸底模拟（R34）：宽带天线+屏蔽环境谱→增益补偿→洁净度核验→声明——重写规约与签名意图详见 fn_docs/responsibility.md。

编排职责（谱读数归 SimRsa513a、增益补偿归 compensate_link_power、声明文案归
make_disclaimer_block、本函数只做编排）：

- 宽带天线+屏蔽环境模拟：scenario['center_hz']/'span_hz']（均必需）→SimRsa513a
  （ctx['spectrum_analyzer'] 注入或内部 open_sim_analyzer 新建）set_center/set_span
  →measure(scenario['iq'])——iq 缺省 None 走后端内置自校准测试音路径
  （单音 −30 dBm 恰落 center）。
- 增益补偿：谱 bin 功率（dB，dBm 满刻度口径）经 compensate_link_power——
  tables=scenario['compensation_tables'] **直传**（缺省 None→不补并在
  compensation_note 标注），逐 bin (freq/1e6 MHz, power) 代数和
  p_actual = p_measured + L_link + C_ant（公式(6)，缺表项不计入）；个别 bin
  p_actual=None（非法点）回落原始值，不让演示流程中断。
- 洁净度核验（简单阈值判据，演示口径）：bin 功率 ≥ max − peak_drop_db（缺省
  6 dB，scenario['peak_drop_db'] 可覆盖）计峰候选，相邻 bin 归并为一峰——
  'in_band_peaks'=峰簇数；'out_of_band_ratio_db'=主峰簇（含最大 bin 的簇）外
  全部 bin 线性功率和与主峰簇功率之比（dB，带外杂散比）。
- 全程模拟口径（R34 同 R33 语义）：输出恒带 simulated=True 与
  make_disclaimer_block('emc') 声明块；ctx/scenario 形状错 ValueError；
  仪器（注入或内部）观测域错（set_center/set_span、iq 非法）原样透传；
  演示数据「假」不构成抛错理由。

调用方：build_report（EMC 段）；run_demo。
"""
from __future__ import annotations

import math
from numbers import Real

from src.compensate_link_power.compensate_link_power import compensate_link_power
from src.open_sim_analyzer.open_sim_analyzer import SimRsa513a, open_sim_analyzer
from src.shared.make_disclaimer_block import make_disclaimer_block

__all__ = ["DEFAULT_PEAK_DROP_DB", "run_emc_radiation_sim"]

#: 洁净度判据缺省：bin 功率 ≥ max − 6 dB 计入峰候选（简单阈值判据，演示口径）。
DEFAULT_PEAK_DROP_DB = 6.0

#: 未提供补偿表时的注记（谱值为未补偿原始口径——演示标注）。
_NO_TABLES_NOTE = (
    "scenario 未提供 compensation_tables：谱值为未做增益补偿的原始口径（演示标注）"
)

#: 提供补偿表时的注记。
_TABLES_NOTE = "谱值已经 compensate_link_power 增益补偿（compensation_tables 直传口径）"


def _require_dict(name: str, value: object) -> dict:
    """形状守卫：ctx/scenario 非 dict → ValueError（消息附类型与原值）。"""
    if not isinstance(value, dict):
        raise ValueError(
            f"{name} 必须为 dict，实际为 {type(value).__name__}: {value!r}"
        )
    return value


def _positive_finite(name: str, raw: object) -> float:
    """数值守卫：拒 bool/非实数/NaN/±inf/非正，返回 float。"""
    if isinstance(raw, bool) or not isinstance(raw, Real):
        raise ValueError(f"{name} 必须为实数（bool 与其他类型一律拒绝）: {raw!r}")
    val = float(raw)
    if not math.isfinite(val):
        raise ValueError(f"{name} 必须为有限数（拒 NaN/±inf）: {raw!r}")
    if val <= 0.0:
        raise ValueError(f"{name} 必须为正数，实际为 {val!r}")
    return val


def _resolve_analyzer(ctx: dict) -> tuple[SimRsa513a, bool]:
    """频谱仪解析：ctx['spectrum_analyzer'] 注入优先，否则内部 open_sim_analyzer() 新建。"""
    injected = ctx.get("spectrum_analyzer")
    if injected is not None:
        return injected, True
    return open_sim_analyzer(), False


def _cleanliness(power_db: list[float], peak_drop_db: float) -> dict:
    """洁净度核验（简单阈值判据）：峰簇计数 + 主峰簇外带外杂散比（dB）。

    判据（演示口径，文档注明非 CISPR 判据）：
    - 峰候选 = bin 功率 ≥ max(power) − peak_drop_db；相邻 bin 归并为同一峰簇；
    - in_band_peaks = 峰簇数；主峰簇 = 含全局最大 bin 的簇；
    - out_of_band_ratio_db = 10·log10(主峰簇外全部 bin 线性功率和 / 主峰簇线性功率)
      （杂散功率为零时记 −inf）；线性功率以 math.fsum 聚合（精确舍入）。
    """
    max_power = max(power_db)
    threshold = max_power - peak_drop_db
    clusters: list[list[int]] = []
    for idx, power in enumerate(power_db):
        if power < threshold:
            continue
        if clusters and idx == clusters[-1][-1] + 1:
            clusters[-1].append(idx)
        else:
            clusters.append([idx])
    peak_bin = power_db.index(max_power)
    main_cluster = next((c for c in clusters if peak_bin in c), [peak_bin])
    main_set = set(main_cluster)
    linear = [10.0 ** (p / 10.0) for p in power_db]
    main_power = math.fsum(linear[i] for i in main_set)
    spurious_power = math.fsum(
        linear[i] for i in range(len(linear)) if i not in main_set
    )
    if spurious_power > 0.0 and main_power > 0.0:
        ratio_db = 10.0 * math.log10(spurious_power / main_power)
    else:
        ratio_db = float("-inf")
    return {
        "in_band_peaks": len(clusters),
        "out_of_band_ratio_db": ratio_db,
        "peak_threshold_db": threshold,
        "criterion": (
            f"简单阈值判据（演示口径）：bin 功率 ≥ max − {peak_drop_db} dB 计峰候选，"
            "相邻 bin 归并为一峰；主峰簇（含最大 bin）外全部 bin 线性功率和与主峰簇"
            "功率之比（dB）记为带外杂散比"
        ),
    }


def run_emc_radiation_sim(ctx: dict, scenario: dict) -> dict:
    """EMC 辐射摸底模拟：屏蔽环境模拟谱 → 增益补偿 → 洁净度核验 → 模拟口径声明（R34）。

    :param ctx: 运行上下文 dict——'spectrum_analyzer' 可注入 SimRsa513a 实例
        （注入实例 set_center/set_span 域错原样透传）；'calibration_config' 可给
        compensate_link_power 的 config（补偿表缺键时文件加载口径，缺省 {}）；
        缺省内部 open_sim_analyzer() 新建
    :param scenario: EMC 辐射摸底场景 dict——
        - 'center_hz'（必需）：观测中心频率 Hz（数值域由仪器 setter 校验）；
        - 'span_hz'（必需）：观测跨度 Hz（同上）；
        - 'iq'（可选）：宽带天线模拟 IQ；缺省 None=后端内置测试音路径；
        - 'compensation_tables'（可选）：{'link_loss': {freq_mhz: dB}, 'antenna':
          {freq_mhz: dB}} 直传 compensate_link_power（缺省 None→不补+标注）；
        - 'peak_drop_db'（可选）：洁净度峰判定跌落阈（缺省 6.0，须为正）。
    :return: ``{'spectrum': {'freqs': [Hz…], 'power_db': [dB…]}, 'compensated': bool,
        'cleanliness': {'in_band_peaks', 'out_of_band_ratio_db', 'peak_threshold_db',
        'criterion'}, 'disclaimer': make_disclaimer_block('emc'), 'simulated': True,
        'compensation_note': str, 'uncertainty_db': 谱不确定度透传, 'warnings': []}``。
    :raises ValueError: ctx/scenario 非 dict；缺 'center_hz'/'span_hz'；
        peak_drop_db 非法；仪器观测域错（set_center/set_span）或 iq 非法
        原样透传（注入与内部新建同口径）。
    """
    _require_dict("ctx", ctx)
    _require_dict("scenario", scenario)
    if scenario.get("center_hz") is None:
        raise ValueError("scenario 缺 'center_hz'（辐射摸底观测中心频率 Hz）")
    if scenario.get("span_hz") is None:
        raise ValueError("scenario 缺 'span_hz'（辐射摸底观测跨度 Hz）")
    peak_drop_db = _positive_finite(
        "peak_drop_db", scenario.get("peak_drop_db", DEFAULT_PEAK_DROP_DB)
    )

    analyzer, _injected = _resolve_analyzer(ctx)
    analyzer.set_center(scenario["center_hz"])  # 域错透传（注入/内部同口径）
    analyzer.set_span(scenario["span_hz"])
    spectrum = analyzer.measure(scenario.get("iq"))  # iq=None → 内置测试音路径
    freqs = [float(f) for f in spectrum["freqs"]]
    powers = [float(p) for p in spectrum["power_db"]]

    # ② 增益补偿：tables 直传缺省 None → 不补+标注；补后个别非法 bin 回落原值
    tables = scenario.get("compensation_tables")
    compensated = False
    compensation_note = _NO_TABLES_NOTE
    if tables is not None:
        config = ctx.get("calibration_config")
        if not isinstance(config, dict):
            config = {}
        measurements = [(f / 1e6, p) for f, p in zip(freqs, powers)]
        comp = compensate_link_power(measurements, config, tables=tables)
        powers = [
            point["p_actual"] if point["p_actual"] is not None else raw
            for point, raw in zip(comp, powers)
        ]
        compensated = True
        compensation_note = _TABLES_NOTE

    # ③ 洁净度核验（对最终图谱口径——补偿后的谱）＋ ④ 输出
    return {
        "spectrum": {"freqs": freqs, "power_db": powers},
        "compensated": compensated,
        "cleanliness": _cleanliness(powers, peak_drop_db),
        "disclaimer": make_disclaimer_block("emc"),
        "simulated": True,
        "compensation_note": compensation_note,
        "uncertainty_db": spectrum.get("uncertainty_db"),
        "warnings": [],
    }
