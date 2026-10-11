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

# 天线白名单按收/发分设（对齐 B210 真机端口）：CH1 发端口仅 TX/RX；CH2 收端口 TX/RX 或 RX2。
# 'RX1'/'TX' 非真机端口名，自白名单移除（真机 UHD 会以 LookupError 拒绝——域校验期即拒更早更明确）。
_ANTENNA_WHITELIST: dict[str, frozenset[str]] = {
    "tx": frozenset({"TX/RX"}),
    "rx": frozenset({"TX/RX", "RX2"}),
}
# 增益域按通道分设（对齐 B210 真机 dB 上限）：TX 0–89.75，RX 0–76。
_GAIN_RANGE_DB: dict[str, tuple[float, float]] = {
    "tx": (0.0, 89.75),
    "rx": (0.0, 76.0),
}
_CLOCK_REFS = frozenset({"internal", "external", "gpsdo"})
_FREQ_MIN_HZ, _FREQ_MAX_HZ = 70e6, 6e9


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
    """单通道参数域校验（不触碰设备）：子键可缺，缺省不在此报错（下发期记 skipped）。

    天线白名单与增益上界按通道收/发分设（真机口径）：tx 天线仅 {'TX/RX'}、增益 0–89.75；
    rx 天线 {'TX/RX','RX2'}、增益 0–76。未知子键不在此处理（前向兼容，主流程记 skipped）。
    """
    if not isinstance(cfg, dict):
        raise ValueError(
            f"通道 {channel!r} 须为 dict（参数键: freq_hz/gain_db/sample_rate/"
            f"bandwidth_hz/antenna），得到 {type(cfg).__name__}: {cfg!r}"
        )
    prefix = _CHANNELS[channel]
    antennas = _ANTENNA_WHITELIST[prefix]
    gain_min, gain_max = _GAIN_RANGE_DB[prefix]
    for key in _PARAM_SPEC:
        if key not in cfg:
            continue
        value = cfg[key]
        if key == "antenna":
            # 先判 isinstance 再查白名单：非 str（含不可哈希对象）统一 ValueError 而非 TypeError。
            if not isinstance(value, str) or value not in antennas:
                raise ValueError(
                    f"参数 {channel}.antenna 非法: {value!r}"
                    f"（{prefix} 白名单: {sorted(antennas)}）"
                )
            continue
        number = _require_finite_number(channel, key, value)
        if key == "freq_hz" and not (_FREQ_MIN_HZ <= number <= _FREQ_MAX_HZ):
            raise ValueError(
                f"参数 {channel}.freq_hz 超出 B210 频率域 "
                f"[{_FREQ_MIN_HZ:g}, {_FREQ_MAX_HZ:g}] Hz: {number!r}"
            )
        if key == "gain_db" and not (gain_min <= number <= gain_max):
            raise ValueError(
                f"参数 {channel}.gain_db 超出增益域 "
                f"[{gain_min:g}, {gain_max:g}] dB（{prefix} 通道上界）: {number!r}"
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


def _dispatch(action: str, call):
    """设备调用统一异常契约：底层异常（UHD RuntimeError/LookupError 等原文并入）→ BackendError。

    __cause__ 保留原异常——调用方既拿到统一异常族，又不丢失 UHD 原文定位。
    """
    try:
        return call()
    except Exception as exc:
        raise BackendError(f"{action}: {type(exc).__name__}: {exc}") from exc


def _apply_channel(
    device, channel: str, cfg: dict, applied: dict, skipped: list, unverified: list
) -> None:
    """单通道下发+回读校验：未下发（方法缺）记 skipped；已下发未回读确认（getter 缺）记 unverified。"""
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
        _dispatch(f"{channel}.{key} 下发失败（{setter_name}）", lambda s=setter, v=value: s(v))
        getter_name = f"get_{prefix}_{spec['suffix']}"
        getter = getattr(device, getter_name, None)
        if not callable(getter):
            # 已下发未回读确认：记 unverified（非 skipped），applied 记下发值+标注。
            unverified.append(f"{channel}.{key}:{getter_name}")
            channel_applied[key] = value
            continue
        readback = _dispatch(f"{channel}.{key} 回读失败（{getter_name}）", getter)
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
          skipped），通道内参数子键亦可缺（该项跳过并记 skipped）；未知子键/顶层
          未知键不炸：各记 skipped（'{channel}.{key}:unknown_key' / '{key}:
          unknown_key'）后忽略（前向兼容，多给的键不阻断既有下发）。
    输出: {'applied': {channel: {参数键: 实际回读值（getter 缺时记下发值）}},
          'skipped': [未下发项字符串（子键缺/setter 缺/未知键）],
          'unverified': [已下发未回读确认项（getter 缺，'{channel}.{key}:{getter_name}'；
          对应 applied 记下发值+此标注）], 'clock_ref': str|None}（clock_ref 为成功
          下发的时钟参考，未给出/句柄缺 set_clock_source 时为 None）。
    错误: ValueError——params 非 dict / 参数域校验不过（freq 70e6–6e9 Hz、gain 按通道
          tx 0–89.75 / rx 0–76 dB、rate>0、bw>0、antenna 白名单按通道 tx {'TX/RX'} /
          rx {'TX/RX','RX2'}、clock_ref 非 internal|external|gpsdo），域校验先于任何
          设备调用（失败路径零设备副作用）；BackendError——任一 set_*/get_* 设备调用
          抛异常（含 UHD 原文，__cause__ 保留）、回读偏差超容差（freq 1Hz / gain
          0.5dB / rate 1Hz / bw 1%、antenna 精确匹配）或回读非有限（NaN/inf），消息含
          参数名与下发/回读两值。
    """
    if not isinstance(params, dict):
        raise ValueError(
            f"params 须为 dict（ch1_tx/ch2_rx/clock_ref 结构），"
            f"得到 {type(params).__name__}: {params!r}"
        )

    applied: dict = {}
    skipped: list[str] = []
    unverified: list[str] = []

    # 1) 参数域校验先行：任何 ValueError 在触碰设备之前抛出；未知子键/顶层未知键
    #    不在此炸——记 skipped 后忽略（前向兼容口径）。
    for channel in _CHANNELS:
        if channel in params:
            _validate_channel(channel, params[channel])
            for key in params[channel]:
                if key not in _PARAM_SPEC:
                    skipped.append(f"{channel}.{key}:unknown_key")
    for key in params:
        if key not in _CHANNELS and key != "clock_ref":
            skipped.append(f"{key}:unknown_key")
    clock_ref = params.get("clock_ref")
    if clock_ref is not None and (
        not isinstance(clock_ref, str) or clock_ref not in _CLOCK_REFS
    ):
        raise ValueError(
            f"clock_ref 非法: {clock_ref!r}（合法值: {sorted(_CLOCK_REFS)}）"
        )

    # 2) 双通道参数下发 + 回读校验（通道键缺 -> 整通道跳过并记 skipped）。
    for channel in _CHANNELS:
        if channel not in params:
            skipped.append(channel)
            continue
        _apply_channel(device, channel, params[channel], applied, skipped, unverified)

    # 3) 时钟参考：set_clock_source / set_time_source 各自缺方法则各自跳过并记 skipped；
    #    在则下发（异常统一入 _dispatch 的 BackendError 契约）。
    resolved_clock: str | None = None
    if clock_ref is not None:
        set_clock = getattr(device, "set_clock_source", None)
        if callable(set_clock):
            _dispatch("clock_ref 下发失败（set_clock_source）", lambda: set_clock(clock_ref))
            resolved_clock = clock_ref
        else:
            skipped.append("clock_ref:set_clock_source")
        set_time = getattr(device, "set_time_source", None)
        if callable(set_time):
            _dispatch("clock_ref 下发失败（set_time_source）", lambda: set_time(clock_ref))
        else:
            skipped.append("clock_ref:set_time_source")

    return {
        "applied": applied,
        "skipped": skipped,
        "unverified": unverified,
        "clock_ref": resolved_clock,
    }
