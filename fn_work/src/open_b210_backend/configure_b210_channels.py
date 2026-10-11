"""双通道参数下发与回读校验（频率/增益/采样率/时钟源）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math

# BackendError 单一事实源在注册表包：回读不符属后端错误，与注册/查询侧同一异常族。
from src.manage_backend_registry.register_backend import BackendError

__all__ = ["BackendError", "configure_b210_channels"]

# 通道名 -> 句柄方法前缀：ch1_tx -> set_tx_<suffix>/get_tx_<suffix>，ch2_rx -> set_rx_*。
_CHANNELS: dict[str, str] = {"ch1_tx": "tx", "ch2_rx": "rx"}

# 参数键 -> 方法名后缀 + 容差（abs_tol 绝对容差 / rel_tol 相对容差 / antenna 精确串匹配）。
_PARAM_SPEC: dict[str, dict] = {
    "freq_hz": {"suffix": "freq", "abs_tol": 1.0, "tol_desc": "1Hz"},
    "gain_db": {"suffix": "gain", "abs_tol": 0.5, "tol_desc": "0.5dB"},
    "sample_rate": {"suffix": "rate", "abs_tol": 1.0, "tol_desc": "1Hz"},
    "bandwidth_hz": {"suffix": "bandwidth", "rel_tol": 0.01, "tol_desc": "1%"},
    "antenna": {"suffix": "antenna", "exact": True, "tol_desc": "精确匹配"},
}

_ANTENNA_WHITELIST = frozenset({"TX/RX", "RX2", "RX1", "TX"})
_CLOCK_REFS = frozenset({"internal", "external", "gpsdo"})
_FREQ_MIN_HZ, _FREQ_MAX_HZ = 70e6, 6e9
_GAIN_MIN_DB, _GAIN_MAX_DB = 0.0, 89.75


def _require_finite_number(channel: str, key: str, value: object) -> float:
    """数值形式校验：须为非 bool 的 int/float 且有限（NaN/inf 域校验期即拒）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"参数 {channel}.{key} 须为数值（int/float），"
            f"得到 {type(value).__name__}: {value!r}"
        )
    if not math.isfinite(value):
        raise ValueError(f"参数 {channel}.{key} 须为有限数，得到 {value!r}")
    return float(value)


def _validate_channel(channel: str, cfg: object) -> None:
    """单通道参数域校验（不触碰设备）：子键可缺，缺省不在此报错（下发期记 skipped）。"""
    if not isinstance(cfg, dict):
        raise ValueError(
            f"通道 {channel!r} 须为 dict（参数键: freq_hz/gain_db/sample_rate/"
            f"bandwidth_hz/antenna），得到 {type(cfg).__name__}: {cfg!r}"
        )
    for key in _PARAM_SPEC:
        if key not in cfg:
            continue
        value = cfg[key]
        if key == "antenna":
            # 先判 isinstance 再查白名单：非 str（含不可哈希对象）统一 ValueError 而非 TypeError。
            if not isinstance(value, str) or value not in _ANTENNA_WHITELIST:
                raise ValueError(
                    f"参数 {channel}.antenna 非法: {value!r}"
                    f"（白名单: {sorted(_ANTENNA_WHITELIST)}）"
                )
            continue
        number = _require_finite_number(channel, key, value)
        if key == "freq_hz" and not (_FREQ_MIN_HZ <= number <= _FREQ_MAX_HZ):
            raise ValueError(
                f"参数 {channel}.freq_hz 超出 B210 频率域 "
                f"[{_FREQ_MIN_HZ:g}, {_FREQ_MAX_HZ:g}] Hz: {number!r}"
            )
        if key == "gain_db" and not (_GAIN_MIN_DB <= number <= _GAIN_MAX_DB):
            raise ValueError(
                f"参数 {channel}.gain_db 超出增益域 "
                f"[{_GAIN_MIN_DB:g}, {_GAIN_MAX_DB:g}] dB: {number!r}"
            )
        if key in ("sample_rate", "bandwidth_hz") and number <= 0:
            raise ValueError(f"参数 {channel}.{key} 须为正数，得到 {number!r}")


def _verify_readback(channel: str, key: str, want, got, spec: dict) -> None:
    """回读校验：偏差超容差 -> BackendError（消息含参数名与下发/回读两值）。"""
    where = f"{channel}.{key}"
    if spec.get("exact"):  # antenna：字符串精确匹配，无容差
        if got != want:
            raise BackendError(
                f"{where} 回读不符: 下发 {want!r} vs 回读 {got!r}"
                f"（容差 {spec['tol_desc']}）"
            )
        return
    # 先判 isfinite：NaN 与任何容差比较恒为 False（abs(nan-x) > tol 也是 False），
    # 若直接比容差会让 nan 静默混入 applied——非有限回读在此即拒。
    if (
        isinstance(got, bool)
        or not isinstance(got, (int, float))
        or not math.isfinite(got)
    ):
        raise BackendError(
            f"{where} 回读值非法（须为有限数值）: 下发 {want!r} vs 回读 {got!r}"
        )
    want_f = float(want)
    if "abs_tol" in spec:
        within = abs(got - want_f) <= spec["abs_tol"]
    else:  # 相对容差（bw: 1%，以下发值为基准）
        within = abs(got - want_f) <= spec["rel_tol"] * abs(want_f)
    if not within:
        raise BackendError(
            f"{where} 回读不符: 下发 {want!r} vs 回读 {got!r}"
            f"（容差 {spec['tol_desc']}）"
        )


def _apply_channel(device, channel: str, cfg: dict, applied: dict, skipped: list) -> None:
    """单通道下发+回读校验：子键缺/句柄缺方法 -> 各自跳过并记 skipped。"""
    prefix = _CHANNELS[channel]
    channel_applied: dict = {}
    for key, spec in _PARAM_SPEC.items():
        if key not in cfg:
            skipped.append(f"{channel}.{key}")
            continue
        value = cfg[key]
        setter_name = f"set_{prefix}_{spec['suffix']}"
        setter = getattr(device, setter_name, None)
        if not callable(setter):
            skipped.append(f"{channel}.{key}:{setter_name}")
            continue
        setter(value)
        getter_name = f"get_{prefix}_{spec['suffix']}"
        getter = getattr(device, getter_name, None)
        if not callable(getter):
            skipped.append(f"{channel}.{key}:{getter_name}")
            continue
        readback = getter()
        _verify_readback(channel, key, value, readback, spec)
        channel_applied[key] = readback
    applied[channel] = channel_applied


def configure_b210_channels(device, params: dict) -> dict:
    """向 B210 设备句柄下发双通道参数并回读校验（CH1 TX / CH2 RX / 时钟参考）。

    输入: device 鸭子句柄（方法名按后缀映射: ch1_tx -> set_tx_freq/set_tx_gain/
          set_tx_rate/set_tx_bandwidth/set_tx_antenna，ch2_rx -> set_rx_* 同构；
          句柄缺某方法 -> 该项跳过并记 skipped，不炸）；params {'ch1_tx': {freq_hz,
          gain_db, sample_rate, bandwidth_hz, antenna}, 'ch2_rx': {...}, 'clock_ref':
          'internal'|'external'|'gpsdo'}——通道键可缺（缺则该通道整段跳过并记
          skipped），通道内参数子键亦可缺（该项跳过并记 skipped）。
    输出: {'applied': {channel: {参数键: 实际回读值}}, 'skipped': [跳过项字符串],
          'clock_ref': str|None}（clock_ref 为成功下发的时钟参考，未给出/句柄缺
          set_clock_source 时为 None）。
    错误: ValueError——params 非 dict / 参数域校验不过（freq 70e6–6e9 Hz、gain
          0–89.75 dB、rate>0、bw>0、antenna 白名单 {'TX/RX','RX2','RX1','TX'}、
          clock_ref 非 internal|external|gpsdo），域校验先于任何设备调用（失败路径
          零设备副作用）；BackendError——回读偏差超容差（freq 1Hz / gain 0.5dB /
          rate 1Hz / bw 1%、antenna 精确匹配）或回读非有限（NaN/inf），消息含参数名
          与下发/回读两值。
    """
    if not isinstance(params, dict):
        raise ValueError(
            f"params 须为 dict（ch1_tx/ch2_rx/clock_ref 结构），"
            f"得到 {type(params).__name__}: {params!r}"
        )

    # 1) 参数域校验先行：任何 ValueError 在触碰设备之前抛出。
    for channel in _CHANNELS:
        if channel in params:
            _validate_channel(channel, params[channel])
    clock_ref = params.get("clock_ref")
    if clock_ref is not None and (
        not isinstance(clock_ref, str) or clock_ref not in _CLOCK_REFS
    ):
        raise ValueError(
            f"clock_ref 非法: {clock_ref!r}（合法值: {sorted(_CLOCK_REFS)}）"
        )

    applied: dict = {}
    skipped: list[str] = []

    # 2) 双通道参数下发 + 回读校验（通道键缺 -> 整通道跳过并记 skipped）。
    for channel in _CHANNELS:
        if channel not in params:
            skipped.append(channel)
            continue
        _apply_channel(device, channel, params[channel], applied, skipped)

    # 3) 时钟参考：set_clock_source / set_time_source 各自缺方法则各自跳过并记 skipped。
    resolved_clock: str | None = None
    if clock_ref is not None:
        set_clock = getattr(device, "set_clock_source", None)
        if callable(set_clock):
            set_clock(clock_ref)
            resolved_clock = clock_ref
        else:
            skipped.append("clock_ref:set_clock_source")
        set_time = getattr(device, "set_time_source", None)
        if callable(set_time):
            set_time(clock_ref)
        else:
            skipped.append("clock_ref:set_time_source")

    return {"applied": applied, "skipped": skipped, "clock_ref": resolved_clock}
