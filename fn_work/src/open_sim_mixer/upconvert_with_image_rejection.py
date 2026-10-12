"""单次上变频纯计算（公式(2) f_RF=f_LO+f_IF，镜像按抑制比残留）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
from numbers import Real

__all__ = ["upconvert_with_image_rejection"]

#: IF 参数必填键（键缺 → ValueError 附缺键名；额外键不参与校验）
_IF_REQUIRED_KEYS: tuple[str, ...] = ("if_freq_hz", "if_power_dbm")
#: LO 参数必填键（phase_noise_dbc_hz 键必须在，值可为 None=理想 LO）
_LO_REQUIRED_KEYS: tuple[str, ...] = ("lo_freq_hz", "lo_power_dbm", "phase_noise_dbc_hz")

#: IF+LO 功率合成【简化口径】：LO 仅作搬移能量近似，按等功率双音合成取 IF 功率 +3 dB，
#: 不逐项依赖 lo_power_dbm 数值（文档化简化，不做逐项功率合成）
_RF_POWER_COMBINE_DB = 3.0
#: 二次本振杂散（2·f_LO±f_IF）相对 IF 功率的经验压制量（dB）
_SPURIOUS_SUPPRESSION_DB = 60.0


def _require_dict_with_keys(params: object, keys: tuple[str, ...], name: str) -> dict:
    """形状校验：入参必须是 dict 且必填键齐全；否则 ValueError（缺键附缺键名）。"""
    if not isinstance(params, dict):
        raise ValueError(f"{name} 必须为 dict（形状拒绝）：{type(params).__name__}")
    for key in keys:
        if key not in params:
            raise ValueError(f"{name} 缺少必填键 {key!r}（缺键拒绝，附键名）")
    return params


def _to_finite_float(label: str, value: object) -> float:
    """数值域公共校验：拒 bool/非实数/超 float 域/NaN/±inf，归一返回 float。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} 必须为实数（bool/非数值一律拒绝）：{value!r}")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} 超出 float 可表示域：{value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} 必须为有限数（拒 NaN/±inf）：{value!r}")
    return number


def _validate_freq(name: str, key: str, value: object) -> float:
    """频率域校验：有限正实数（Hz）；拒 bool/非数值/NaN/±inf/≤0。"""
    number = _to_finite_float(f"{name}[{key!r}]", value)
    if number <= 0.0:
        raise ValueError(f"{name}[{key!r}] 必须为正频率（Hz）：{number!r}")
    return number


def _validate_rejection(value: object) -> float:
    """镜像抑制比域校验：有限非负实数（dB）；拒 bool/非数值/NaN/±inf/负值。"""
    number = _to_finite_float("rejection_db", value)
    if number < 0.0:
        raise ValueError(f"rejection_db 必须为非负镜像抑制比（dB）：{number!r}")
    return number


def _validate_phase_noise(value: object) -> float | None:
    """LO 相噪口径校验：None=理想 LO；否则有限非 bool 实数（dBc/Hz）。"""
    if value is None:
        return None
    return _to_finite_float("lo_params['phase_noise_dbc_hz']", value)


def upconvert_with_image_rejection(
    if_params: dict, lo_params: dict, rejection_db: float = 40.0
) -> dict:
    """单次上变频纯计算：IF+LO→RF（公式(2) f_RF=f_LO+f_IF），镜像按抑制比残留。

    只做一次混频的频谱标注计算（无时间波形、无仪器操作、无随机性——同输入同输出，
    不改入参）。

    输入口径（if_params/lo_params 非 dict、必填键缺（附缺键名）、域非法一律 ValueError）：
    - ``if_params``: ``{'if_freq_hz': f_IF（Hz，正有限实数，bool 拒）,
      'if_power_dbm': IF 功率（dBm，任意有限实数，bool/NaN 拒）}``（额外键忽略）
    - ``lo_params``: ``{'lo_freq_hz': f_LO（Hz，正有限实数，bool 拒）,
      'lo_power_dbm': LO 驱动功率（dBm，任意有限实数，bool/NaN 拒——仅作域校验记录，
      不进输出键集）, 'phase_noise_dbc_hz': LO 相噪口径（dBc/Hz；None=理想 LO；
      bool/NaN/非数值拒）}``
    - ``rejection_db``: 镜像抑制比（dB，缺省 40；负值/NaN/bool/非数值拒；
      0 合法——镜像全残留）

    输出口径（键集固定 7 键，功率均为 dBm 标量）：
    - ``rf_freq_hz``: 公式(2) ``f_RF = f_LO + f_IF``
    - ``rf_power_dbm``: 【简化口径】IF+LO 功率合成取 IF 功率 +3 dB（等功率双音合成
      近似——LO 仅作搬移能量，不逐项依赖 lo_power_dbm 数值）
    - ``image_freq_hz``: ``f_LO − f_IF``（镜像边带；按字面公式输出，f_IF > f_LO 时
      为负、不做折叠/取绝对值整形）
    - ``image_power_dbm``: ``IF 功率 − rejection_db``（镜像残留）
    - ``image_rejection_db``: ``rejection_db`` 归一透传（float）
    - ``phase_noise_note``: LO 相噪口径透传（float，dBc/Hz）或 ``'ideal_lo'``
      （``phase_noise_dbc_hz=None`` 理想本振标记）
    - ``spurious``: 两条二次本振杂散 ``[{'freq_hz': 2·f_LO−f_IF, 'power_dbm': IF−60},
      {'freq_hz': 2·f_LO+f_IF, 'power_dbm': IF−60}]``（−60 dB 为经验压制量口径；
      顺序固定先低后高）

    :param if_params: IF 参数 dict（形状/域见上）
    :param lo_params: LO 参数 dict（形状/域见上）
    :param rejection_db: 镜像抑制比（dB，非负，缺省 40.0）
    :return: 上变频频谱标注 dict（键集见上）
    :raises ValueError: 入参非 dict / 必填键缺（附键名）/ 频率非正或非数值或 NaN 或
        bool / 功率与相噪非数值或 NaN 或 bool / ``rejection_db`` 负值或非数值。
    """
    if_req = _require_dict_with_keys(if_params, _IF_REQUIRED_KEYS, "if_params")
    lo_req = _require_dict_with_keys(lo_params, _LO_REQUIRED_KEYS, "lo_params")

    if_freq_hz = _validate_freq("if_params", "if_freq_hz", if_req["if_freq_hz"])
    if_power_dbm = _to_finite_float("if_params['if_power_dbm']", if_req["if_power_dbm"])
    lo_freq_hz = _validate_freq("lo_params", "lo_freq_hz", lo_req["lo_freq_hz"])
    # lo_power_dbm 仅域校验（记录口径不进输出键集；+3dB 简化式不逐项依赖其数值）
    _to_finite_float("lo_params['lo_power_dbm']", lo_req["lo_power_dbm"])
    phase_noise_dbc_hz = _validate_phase_noise(lo_req["phase_noise_dbc_hz"])
    rejection = _validate_rejection(rejection_db)

    return {
        # 公式(2)：上边带 f_RF = f_LO + f_IF
        "rf_freq_hz": lo_freq_hz + if_freq_hz,
        # IF+LO 合成简化口径：IF 功率 +3 dB（LO 仅作搬移能量近似）
        "rf_power_dbm": if_power_dbm + _RF_POWER_COMBINE_DB,
        # 镜像边带：f_LO − f_IF（字面公式，不折叠）
        "image_freq_hz": lo_freq_hz - if_freq_hz,
        # 镜像残留：IF 功率 − 抑制比
        "image_power_dbm": if_power_dbm - rejection,
        "image_rejection_db": rejection,
        # LO 相噪口径透传；None → 理想本振标记
        "phase_noise_note": "ideal_lo" if phase_noise_dbc_hz is None else phase_noise_dbc_hz,
        # 二次本振杂散（2·f_LO±f_IF，各压 IF−60 dB；先低后高）
        "spurious": [
            {
                "freq_hz": 2.0 * lo_freq_hz - if_freq_hz,
                "power_dbm": if_power_dbm - _SPURIOUS_SUPPRESSION_DB,
            },
            {
                "freq_hz": 2.0 * lo_freq_hz + if_freq_hz,
                "power_dbm": if_power_dbm - _SPURIOUS_SUPPRESSION_DB,
            },
        ],
    }
