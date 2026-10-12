"""RSA513A 频谱仪模拟后端（DPX/13.6GHz/±1.5dB 口径）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
import numbers
import struct
import zlib

import numpy as np

# register_backend 供本模块 import 期自注册（与 open_sim_backend 同模式）；
# BackendError 为发射请求报错单源（同 replay 先例：start_tx 即抛）。
from src.manage_backend_registry.register_backend import BackendError, register_backend

__all__ = ["SimRsa513a", "open_sim_analyzer"]

# ---- 观测参数域（RSA513A 仿真口径，capabilities 与校验共用单一事实源）----
_CENTER_RANGE_HZ: tuple[float, float] = (1e6, 13.6e9)  # 中心频率域 1MHz–13.6GHz
_SPAN_RANGE_HZ: tuple[float, float] = (1e3, 110e6)  # DPX 口径 span 域 1kHz–110MHz
_RBW_RANGE_HZ: tuple[float, float] = (1.0, 1e6)  # RBW 域 1Hz–1MHz

# ---- 工厂缺省观测面 ----
_DEFAULT_CENTER_HZ = 1e9
_DEFAULT_SPAN_HZ = 10e6  # DPX 口径缺省 span
_DEFAULT_RBW_HZ = 10e3
_DEFAULT_TRACE_MODE = "clearwrite"

# ---- 仿真谱口径 ----
_NFFT = 1024  # FFT 点数（复用 numpy，口径固定）
_FLOOR_DB = -120.0  # 仿真底噪钳位 dBm（空谱 log(0)→-inf 防呆）
_UNCERTAINTY_DB = 1.5  # 幅度不确定度仿真口径 ±1.5 dB
_TONE_DBM = -30.0  # 内置自校准测试音：单音 -30 dBm @ center
_TONE_AMP = 10.0 ** (_TONE_DBM / 20.0)

# ---- DPX 帧合成口径：8 帧 min/max 包络（简化密度）----
_DPX_FRAMES = 8
_DPX_NOTE = "dpx_sim"

_TRACE_MODES = ("maxhold", "clearwrite")

# 无发射能力：事件文案（stop_tx/set_tx_gain 记录）与 start_tx 报错文案
_NO_TX_EVENT = "sim_rsa513a 无发射能力"
_NO_TX_MESSAGE = "sim_rsa513a 后端无发射能力"

# 注册名与契约方法清单（caps 声明 rx 为真 → 契约要求 read_samples；tx=False 无要求）。
_BACKEND_NAME = "sim_rsa513a"
_METHOD_NAMES = ["read_samples"]


def _as_real(key: str, raw: object) -> float:
    """数值参数统一校验：bool 拒收（布尔频率/带宽几乎必为配置笔误），非实数/非有限→ValueError。"""
    if isinstance(raw, bool) or not isinstance(raw, numbers.Real):
        raise ValueError(f"{key} 必须为实数，实际为 {type(raw).__name__}: {raw!r}")
    val = float(raw)
    if not math.isfinite(val):
        raise ValueError(f"{key} 必须为有限数，实际为 {val!r}")
    return val


def _check_in_range(key: str, val: float, bounds: tuple[float, float]) -> float:
    """域校验：越域（含边界外一丝一毫）→ValueError；通过则原值返回。"""
    lo, hi = bounds
    if not lo <= val <= hi:
        raise ValueError(f"{key} 超出仿真域 [{lo!r}, {hi!r}]，实际为 {val!r}")
    return val


def _deviation_seed(center_hz: float, span_hz: float, salt: int) -> int:
    """不确定度偏差种子：crc32(center+span 打包位模式+salt)——确定性、跨运行可复现
    （不依赖 Python 内建 hash 的随机化盐值；salt 区分 measure 单谱与 DPX 多帧）。"""
    return zlib.crc32(struct.pack("<ddq", float(center_hz), float(span_hz), int(salt)))


class SimRsa513a:
    """RSA513A 频谱仪仿真后端实例（注册名 sim_rsa513a）：观测参数面 + 仿真谱读数。

    谱模型（全程确定性，无真随机）:
      - 内置测试音（measure(iq=None)）：单音 -30 dBm 恰落 center（自校准口径）；
      - 给 IQ：取前 nfft=1024 样本（不足零填），复 FFT→fftshift→功率谱 dB
        （10·log10(|X|²/nfft²)，幅度 1.0 ≡ 0 dBm 满刻度；空谱钳位底噪 -120 dBm）；
        bin i 频率 = center + (i - nfft/2)·span/nfft（升频轴，覆盖 center±span/2）；
      - 幅度不确定度仿真：每 bin 功率叠加 ±1.5 dB 内均匀伪随机偏差，种子为
        center+span 位模式的 crc32（DPX 帧以 salt=0..7 派生 8 个不同偏差帧）——
        同参数同 salt 逐位可复现；
      - trace：clearwrite（缺省）当前谱即显；maxhold 逐 bin 取历史最大
        （set_center/set_span 改轴即清保持谱，rbw 不改谱值故保持谱有效）。

    与 B210 分析仪模式的区别（接口口径）: 本后端为纯频谱分析仪仿真，无 IQ 采样流
    ——read_samples 恒返回 []（B210 分析仪模式有真实 IQ 流可读）；谱读数一律走
    measure()/dpx_frame()。无发射能力：stop_tx/set_tx_gain 记录事件返回
    {'status': 'no_tx'}（不抛），start_tx 调用即 BackendError（同 replay 先例）。
    """

    def __init__(
        self, center_hz: float, span_hz: float, rbw_hz: float, trace_mode: str
    ) -> None:
        self.center_hz = center_hz
        self.span_hz = span_hz
        self.rbw_hz = rbw_hz
        self.trace_mode = trace_mode
        self._maxhold: list[float] | None = None  # maxhold 保持谱（轴变即失效清空）
        self.events: list[str] = []  # no_tx 调用记录（同 replay 先例）

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<SimRsa513a center_hz={self.center_hz!r} span_hz={self.span_hz!r} "
            f"rbw_hz={self.rbw_hz!r} trace_mode={self.trace_mode!r}>"
        )

    # ---- ① 观测参数面 ----

    def set_center(self, freq_hz: float) -> float:
        """设置中心频率（域 1e6–13.6e9 Hz）。

        输入: freq_hz 实数（非 bool/非有限/越域 → ValueError，先校验后写、拒绝不改状态）。
        输出: 实际生效中心频率 Hz。行为: 改轴即清 maxhold 保持谱（旧 bin 轴失效）。
        """
        val = _check_in_range("center_hz", _as_real("center_hz", freq_hz), _CENTER_RANGE_HZ)
        self.center_hz = val
        self._maxhold = None
        return val

    def set_span(self, span_hz: float) -> float:
        """设置观测 span（RSA DPX 口径域 1e3–110e6 Hz）。

        输入: span_hz 实数（越域/非有限/bool → ValueError，先校验后写）。输出: 生效 span Hz。
        行为: 改轴即清 maxhold 保持谱；span 同时改变不确定度偏差种子（center+span 哈希）。
        """
        val = _check_in_range("span_hz", _as_real("span_hz", span_hz), _SPAN_RANGE_HZ)
        self.span_hz = val
        self._maxhold = None
        return val

    def set_rbw(self, rbw_hz: float) -> float:
        """设置 RBW（域 1–1e6 Hz）。

        输入: rbw_hz 实数（越域/非有限/bool → ValueError）。输出: 生效 RBW Hz。
        行为: 本仿真谱 bin 宽由 span/nfft 决定，RBW 仅作参数面状态（不改谱值、不清保持谱）。
        """
        val = _check_in_range("rbw_hz", _as_real("rbw_hz", rbw_hz), _RBW_RANGE_HZ)
        self.rbw_hz = val
        return val

    def trace(self, mode: str = _DEFAULT_TRACE_MODE) -> str:
        """切换迹线模式：'clearwrite'（当前谱即显）| 'maxhold'（逐 bin 历史最大保持）。

        输入: mode 两模式之一（其他值 → ValueError）。输出: 生效模式名。
        行为: 切到 clearwrite 即清保持谱；maxhold 的累积在后续 measure 中逐次生效。
        """
        if mode not in _TRACE_MODES:
            raise ValueError(f"trace mode 须为 {_TRACE_MODES} 之一，实际为 {mode!r}")
        self.trace_mode = mode
        if mode == "clearwrite":
            self._maxhold = None
        return mode

    # ---- ② 模拟谱生成 ----

    def _freq_axis(self) -> np.ndarray:
        """升频轴：bin i → center + (i - nfft/2)·span/nfft，覆盖 center±span/2（半开）。"""
        return self.center_hz + (np.arange(_NFFT) - _NFFT / 2) * (self.span_hz / _NFFT)

    def _to_iq_array(self, iq: object) -> np.ndarray:
        """IQ 输入整形：一维数值序列→复数数组，截前 nfft 或零填至 nfft；非一维/非数值→ValueError。"""
        try:
            arr = np.asarray(iq, dtype=complex)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"iq 必须为一维复数/实数样本序列，无法解析: {iq!r}") from exc
        if arr.ndim != 1:
            raise ValueError(f"iq 必须为一维样本序列，实际维度为 {arr.ndim}")
        if arr.size >= _NFFT:
            return arr[:_NFFT]
        out = np.zeros(_NFFT, dtype=complex)  # 不足 nfft：零填（空输入→全零→底噪谱）
        out[: arr.size] = arr
        return out

    def _power_spectrum(self, iq: object, salt: int) -> np.ndarray:
        """功率谱 dB（含 ±1.5 dB 确定性不确定度偏差；salt 派生同参数下的不同偏差帧）。"""
        if iq is None:
            samples = np.full(_NFFT, _TONE_AMP, dtype=complex)  # 内置测试音：单音恰在 center
        else:
            samples = self._to_iq_array(iq)
        spec = np.fft.fftshift(np.fft.fft(samples, n=_NFFT))
        with np.errstate(divide="ignore"):  # 空谱 |X|=0 → log10(0)=-inf，先钳位底噪再叠加偏差
            power = 10.0 * np.log10(np.abs(spec) ** 2 / float(_NFFT) ** 2)
        power = np.maximum(power, _FLOOR_DB)
        rng = np.random.default_rng(
            _deviation_seed(self.center_hz, self.span_hz, salt)
        )
        return power + rng.uniform(-_UNCERTAINTY_DB, _UNCERTAINTY_DB, _NFFT)

    def measure(self, iq: object = None) -> dict:
        """测量一帧谱（确定性：同参数逐位可复现）。

        输入: iq 复/实样本序列；None=内置测试音（单音 -30 dBm @ center，自校准口径）。
        输出: {'freqs': [1024 floats], 'power_db': [1024 floats],
        'uncertainty_db': 1.5, 'trace_mode': 当前模式, 'simulated': True}——
        power_db 已含 ±1.5 dB 仿真不确定度偏差（种子 center+span 哈希），maxhold 模式
        下为逐 bin 历史最大保持谱。
        错误: iq 非一维/非数值序列 → ValueError（观测参数域错由各 setter 抛）。
        """
        power = self._power_spectrum(iq, salt=0)
        if self.trace_mode == "maxhold":
            if self._maxhold is None:
                self._maxhold = power.tolist()
            else:
                self._maxhold = [
                    max(held, cur) for held, cur in zip(self._maxhold, power.tolist())
                ]
            shown = self._maxhold
        else:  # clearwrite：当前谱即显（顺带清旧保持谱）
            shown = power.tolist()
            self._maxhold = list(shown)
        return {
            "freqs": [float(f) for f in self._freq_axis()],
            "power_db": list(shown),
            "uncertainty_db": _UNCERTAINTY_DB,
            "trace_mode": self.trace_mode,
            "simulated": True,
        }

    # ---- ③ DPX 口径 ----

    def dpx_frame(self, iq: object = None) -> dict:
        """DPX 帧合成（简化）：同一谱模型以 salt=0..7 派生 8 个不同偏差帧，逐 bin 取 min/max 包络。

        输入: iq 同 measure（None=内置测试音）。输出: {'density': [[min_db, max_db]·1024]
        （每 bin 两元素的 2D 密度包络）， 'frames': 8, 'note': 'dpx_sim'}。
        不触碰 maxhold 状态（密度合成独立于迹线模式）。
        """
        frames = [self._power_spectrum(iq, salt=k) for k in range(_DPX_FRAMES)]
        stack = np.stack(frames)
        density = [
            [float(lo), float(hi)]
            for lo, hi in zip(stack.min(axis=0).tolist(), stack.max(axis=0).tolist())
        ]
        return {"density": density, "frames": _DPX_FRAMES, "note": _DPX_NOTE}

    # ---- ④ 规格对标 ----

    def capabilities(self) -> dict:
        """规格对标（表1 口径，每次返回新 dict，调用方篡改不回写实例与注册表）。"""
        return {
            "model": "RSA513A-sim",
            "max_freq_hz": _CENTER_RANGE_HZ[1],
            "span_range_hz": tuple(_SPAN_RANGE_HZ),
            "rbw_range_hz": tuple(_RBW_RANGE_HZ),
            "uncertainty_db": _UNCERTAINTY_DB,
            "simulated": True,
        }

    # ---- ⑤ 统一后端接口（rx 只读谱面 / 无发射能力）----

    def read_samples(self, *args, **kwargs) -> list:
        """纯频谱分析仪无 IQ 流：恒返回 []。

        与 B210 分析仪模式的区别: B210 是 SDR，分析仪模式下仍有真实 IQ 采样流可经
        read_samples 读取；本 RSA513A 仿真后端只产谱读数（measure/dpx_frame），
        不提供 IQ 流——保留本方法仅为满足注册表 rx=True 契约，恒 []。
        """
        return []

    def stop_tx(self, *args, **kwargs) -> dict:
        """无发射能力：记录事件并返回 {'status': 'no_tx'}（不抛，同 replay 先例）。"""
        self.events.append(_NO_TX_EVENT)
        return {"status": "no_tx"}

    def set_tx_gain(self, *args, **kwargs) -> dict:
        """无发射能力：记录事件并返回 {'status': 'no_tx'}（不抛，同 replay 先例）。"""
        self.events.append(_NO_TX_EVENT)
        return {"status": "no_tx"}

    def start_tx(self, *args, **kwargs) -> dict:
        """sim_rsa513a 后端无 TX：任何发射请求调用即明确报错，绝不静默假装成功。"""
        raise BackendError(_NO_TX_MESSAGE)


def open_sim_analyzer(params: dict | None = None) -> SimRsa513a:
    """RSA513A 频谱仪模拟后端（注册名 sim_rsa513a）：观测参数面 + 仿真谱读数。

    输入: params: dict | None，键均可缺省——
      - center_hz: 中心频率 Hz（默认 1e9，域 1e6–13.6e9，越域 ValueError）；
      - span_hz: 观测 span Hz（DPX 口径默认 10e6，域 1e3–110e6，越域 ValueError）；
      - rbw_hz: RBW Hz（默认 10e3，域 1–1e6，越域 ValueError）；
      - trace: 迹线模式 'clearwrite'（默认）| 'maxhold'（其他值 ValueError）。
    输出: SimRsa513a 实例（确定性仿真：同参数 measure 逐位可复现）。
    错误: params 非 dict 且非 None / 数值键非实数/为布尔/非有限/越域 / trace 模式
    非法 → ValueError（校验先于实例构造，失败不产生半初始化对象）。
    """
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(
            f"params 必须为 dict | None，实际为 {type(params).__name__}: {params!r}"
        )
    center_hz = _check_in_range(
        "center_hz", _as_real("center_hz", params.get("center_hz", _DEFAULT_CENTER_HZ)),
        _CENTER_RANGE_HZ,
    )
    span_hz = _check_in_range(
        "span_hz", _as_real("span_hz", params.get("span_hz", _DEFAULT_SPAN_HZ)),
        _SPAN_RANGE_HZ,
    )
    rbw_hz = _check_in_range(
        "rbw_hz", _as_real("rbw_hz", params.get("rbw_hz", _DEFAULT_RBW_HZ)),
        _RBW_RANGE_HZ,
    )
    trace_mode = params.get("trace", _DEFAULT_TRACE_MODE)
    if trace_mode not in _TRACE_MODES:
        raise ValueError(
            f"trace 须为 {_TRACE_MODES} 之一，实际为 {trace_mode!r}"
        )
    return SimRsa513a(center_hz, span_hz, rbw_hz, trace_mode)


# import 时自注册（override=True：重复 import / importlib.reload 幂等不炸；
# method_names 供注册表 import 期契约形式检查——caps 声明 rx 为真须有 read_samples）。
register_backend(
    _BACKEND_NAME,
    open_sim_analyzer,
    {
        "kind": _BACKEND_NAME,
        "caps": {"tx": False, "rx": True, "freq_range_mhz": (1, 13600)},
    },
    override=True,
    method_names=list(_METHOD_NAMES),
)
