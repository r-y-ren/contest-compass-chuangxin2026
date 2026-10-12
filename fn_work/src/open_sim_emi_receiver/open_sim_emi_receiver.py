"""EMI 接收机模拟后端（1kHz–3GHz/CISPR 检波/底噪口径）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
import numbers

# BackendError 单一事实源在注册表包；register_backend 供本模块 import 期自注册
# （与 open_sim_backend / open_replay_backend 同模式）。
from src.manage_backend_registry.register_backend import BackendError, register_backend

__all__ = ["SimEmiReceiver", "open_sim_emi_receiver"]

# CISPR A+B 频段口径（任务口径）：1kHz–3GHz 闭区间（恰在边界合法，域外 ValueError）。
FREQ_MIN_HZ = 1e3
FREQ_MAX_HZ = 3e9

# 仿真底噪口径：−150 dBm/Hz；RBW 内积分噪声功率 = −150 + 10·log10(rbw) dBm。
NOISE_FLOOR_DBM_HZ = -150.0

# 检波器全集（顺序即 capabilities()['detectors'] 的呈现顺序，大小写敏感）。
DETECTORS: tuple[str, ...] = ("peak", "quasi_peak", "average")

# CISPR 频段缺省 RBW：中心频率 <30MHz → 9kHz，≥30MHz → 120kHz（30MHz 归上带）。
_BAND_SPLIT_HZ = 30e6
_RBW_BELOW_SPLIT_HZ = 9e3
_RBW_ABOVE_SPLIT_HZ = 120e3

# 工厂缺省：中心频率 10MHz（<30MHz → 缺省 RBW 9kHz）；频域分析采样率 1Msps；
# 准峰值简化曲线缺省脉冲重复率 100Hz。
_DEFAULT_FREQ_HZ = 10e6
_DEFAULT_SAMPLE_RATE = 1e6
_DEFAULT_REP_HZ = 100.0

# 频域分析帧长上限（超长帧截断，仿真口径）：控制纯 Python FFT 的计算规模。
_MAX_FRAME_SAMPLES = 8192
# 检波统计跨 4 个等长连续帧（简化帧数，规约口径）。
_N_FRAMES = 4

# 所有读数统一携带的模拟标记与免责文案（R42 规约：仿真读数绝不冒充实测）。
_CISPR_NOTE = "模拟读数——非 CISPR 16-1-1 测量接收机"

# 注册名与契约方法清单（caps 声明 rx 为真 → 契约要求 read_samples；tx=False 无要求，
# start_tx/stop_tx/set_tx_gain 仅承载 no_tx 语义，不入契约清单——与 replay 同模式）。
_BACKEND_NAME = "sim_emi_receiver"
_METHOD_NAMES = ["read_samples"]

# 无发射能力：事件文案（stop_tx/set_tx_gain 记录）与 start_tx 报错文案。
_NO_TX_EVENT = "sim_emi_receiver 无发射能力"
_NO_TX_MESSAGE = "sim_emi_receiver 后端无发射能力（纯测量后端）"


def _as_real(key: str, raw: object) -> float:
    """数值参数统一校验：bool 拒收（布尔频率/带宽几乎必为配置笔误），非实数/非有限→ValueError。"""
    if isinstance(raw, bool) or not isinstance(raw, numbers.Real):
        raise ValueError(f"{key} 必须为实数，实际为 {type(raw).__name__}: {raw!r}")
    val = float(raw)
    if not math.isfinite(val):
        raise ValueError(f"{key} 必须为有限数，实际为 {val!r}")
    return val


def _validate_detector(raw: object) -> str:
    """检波器校验：须为 {'peak', 'quasi_peak', 'average'} 之一的 str（大小写敏感），否则 ValueError。"""
    if not isinstance(raw, str) or raw not in DETECTORS:
        raise ValueError(
            f"detector 须为 {DETECTORS} 之一（大小写敏感），实际为 {type(raw).__name__}: {raw!r}"
        )
    return raw


def _auto_rbw(freq_hz: float) -> float:
    """CISPR 频段缺省 RBW：<30MHz → 9kHz；≥30MHz → 120kHz。"""
    if freq_hz < _BAND_SPLIT_HZ:
        return _RBW_BELOW_SPLIT_HZ
    return _RBW_ABOVE_SPLIT_HZ


def _noise_floor_dbm(rbw_hz: float) -> float:
    """RBW 内仿真底噪功率：−150 dBm/Hz + 10·log10(rbw)（噪声功率随带宽积分）。"""
    return NOISE_FLOOR_DBM_HZ + 10.0 * math.log10(rbw_hz)


def _qp_offset_db(rep_hz: float) -> float:
    """准峰值相对峰值的简化 CISPR 衰减（dB）。

    简化曲线（规约口径，非 CISPR 16-1-1 规范 QP 充放电模型）：
    qp = peak − (10·log10(1 + 1000/rep_hz))·0.5——脉冲重复率 rep_hz 越低衰减越多
    （rep→∞ 时衰减→0 逼近 peak；rep=10Hz 衰减约 10dB）。
    """
    return 5.0 * math.log10(1.0 + 1000.0 / rep_hz)


def _next_pow2(n: int) -> int:
    """不小于 n 的最小 2 的幂（n>=1）。"""
    p = 1
    while p < n:
        p <<= 1
    return p


def _fft_pow2(samples: list[complex]) -> list[complex]:
    """迭代基-2 Cooley-Tukey FFT（输入长度须为 2 的幂）：位反转置换 + 逐级蝶形。

    纯 stdlib 实现（后端家族不引 numpy）：X_k = Σ_n x_n·e^{−2πikn/N}。
    """
    n = len(samples)
    if n < 1 or n & (n - 1):
        raise ValueError(f"内部错误: FFT 长度须为 2 的幂，得到 {n}")  # pragma: no cover - 防御性
    out = list(samples)
    # 位反转置换
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            out[i], out[j] = out[j], out[i]
    # 逐级蝶形
    length = 2
    while length <= n:
        ang = -2.0 * math.pi / length
        w_step = complex(math.cos(ang), math.sin(ang))
        half = length >> 1
        for start in range(0, n, length):
            w = 1.0 + 0.0j
            for idx in range(start, start + half):
                u = out[idx]
                v = out[idx + half] * w
                out[idx] = u + v
                out[idx + half] = u - v
                w *= w_step
        length <<= 1
    return out


class SimEmiReceiver:
    """EMI 接收机仿真后端实例（注册名 sim_emi_receiver）：CISPR 口径读数，无发射能力。

    读数口径（全部仿真，所有输出恒带 simulated=True 与 cispr_note 免责文案）:
      - measure(None)：无输入信号 → 仿真底噪读数，power_dbm = −150 + 10·log10(rbw)；
      - measure(iq)：IQ 序列按"简化 4 帧"切分，逐帧 FFT 取功率谱（幅度口径：单音复幅度
        1.0 → 0 dBm；逐 bin 以 RBW 内底噪钳底，杜绝 −inf），再跨帧按检波器合并——
        peak=各帧逐 bin 最大；average=各帧逐 bin 线性功率均值；quasi_peak=peak 减
        简化 CISPR 衰减曲线 _qp_offset_db(rep_hz)（低重频衰减多，文档注明简化）。

    频域 bin 频率 = 中心频率 ± k·(sample_rate/N_fft)，输出以 MHz 列出（负频率按
    环绕映射到中心频率以下）。RBW 经 set_rbw 参数化（None=恢复频段缺省 9k/120k）。
    """

    def __init__(
        self,
        freq_hz: float,
        detector: str,
        rbw_hz: float,
        rep_hz: float,
        sample_rate: float,
    ) -> None:
        self.freq_hz = freq_hz
        self.sample_rate = sample_rate
        self.rep_hz = rep_hz
        self._detector = detector
        self._rbw_hz = rbw_hz
        self.events: list[str] = []

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<SimEmiReceiver freq_hz={self.freq_hz!r} detector={self._detector!r} "
            f"rbw_hz={self._rbw_hz!r} rep_hz={self.rep_hz!r}>"
        )

    def set_detector(self, detector) -> str:
        """设置检波器：{'peak', 'quasi_peak', 'average'} 之一（大小写敏感）。

        输入: detector 检波器名；输出: 实际生效值；非法名（含大小写变体/非 str）→ ValueError。
        """
        self._detector = _validate_detector(detector)
        return self._detector

    def set_rbw(self, rbw_hz=None) -> float:
        """设置分辨率带宽 RBW：正有限实数；None=恢复 CISPR 频段缺省（<30MHz→9kHz，≥30MHz→120kHz）。

        输入: rbw_hz Hz（或 None）；输出: 实际生效值；非正/非实数/bool/非有限 → ValueError。
        """
        if rbw_hz is None:
            self._rbw_hz = _auto_rbw(self.freq_hz)
            return self._rbw_hz
        val = _as_real("rbw_hz", rbw_hz)
        if val <= 0:
            raise ValueError(f"rbw_hz 必须为正，实际为 {val!r}")
        self._rbw_hz = val
        return self._rbw_hz

    def measure(self, iq=None) -> dict:
        """一次 CISPR 口径读数（所有读数恒带 simulated=True 与 cispr_note——R42 规约）。

        输入: iq 复数样本序列（int/float 视作实 IQ 亦收）或 None。
        输出: dict——
          iq=None → 底噪口径读数（标量）: {'freq_mhz': 中心频率 MHz, 'power_dbm':
            −150+10·log10(rbw), 'detector': 当前检波器, 'rbw_hz', 'noise_floor_dbm_hz': -150,
            'simulated': True, 'cispr_note': ...}；
          给 iq → 频域检波读数（列表）: 'freq_mhz'/'power_dbm' 为逐 bin 列表
            （长度 N_fft，检波后口径），其余键同上。
        错误: iq 非 str/bytes 的可迭代复数序列、样本数 <4（4 帧口径）、样本非复数 → ValueError。
        """
        base = {
            "detector": self._detector,
            "rbw_hz": self._rbw_hz,
            "noise_floor_dbm_hz": NOISE_FLOOR_DBM_HZ,
            "simulated": True,
            "cispr_note": _CISPR_NOTE,
        }
        if iq is None:
            return {
                "freq_mhz": self.freq_hz / 1e6,
                "power_dbm": _noise_floor_dbm(self._rbw_hz),
                **base,
            }
        frames = self._split_frames(iq)
        # 逐帧功率谱（线性 mW 口径），逐 bin 以 RBW 内底噪钳底（仿真接收机自有噪声）
        floor_lin = 10.0 ** (_noise_floor_dbm(self._rbw_hz) / 10.0)
        spectra = [self._frame_spectrum(frame, floor_lin) for frame in frames]
        n_bins = len(spectra[0])
        if self._detector == "peak":
            power_dbm = [
                10.0 * math.log10(max(spec[k] for spec in spectra)) for k in range(n_bins)
            ]
        elif self._detector == "average":
            power_dbm = [
                10.0 * math.log10(sum(spec[k] for spec in spectra) / _N_FRAMES)
                for k in range(n_bins)
            ]
        else:  # quasi_peak：peak 读数减简化 CISPR 衰减（dB 域减法 = 线性域乘衰减曲线）
            offset = _qp_offset_db(self.rep_hz)
            power_dbm = [
                10.0 * math.log10(max(spec[k] for spec in spectra)) - offset
                for k in range(n_bins)
            ]
        bin_hz = self.sample_rate / n_bins
        freq_mhz = [
            (self.freq_hz + (k if k < n_bins / 2 else k - n_bins) * bin_hz) / 1e6
            for k in range(n_bins)
        ]
        return {"freq_mhz": freq_mhz, "power_dbm": power_dbm, **base}

    def read_samples(self) -> dict:
        """注册表 rx 契约适配（method_names=['read_samples']）：等价 measure(None) 底噪读数。"""
        return self.measure(None)

    def start_tx(self, *args, **kwargs) -> None:
        """纯测量后端无 TX：任何发射请求调用即明确报错，绝不静默假装成功。"""
        raise BackendError(_NO_TX_MESSAGE)

    def stop_tx(self) -> dict:
        """无发射能力：记录事件并返回 {'status': 'no_tx'}（不抛）。"""
        self.events.append(_NO_TX_EVENT)
        return {"status": "no_tx"}

    def set_tx_gain(self, *args, **kwargs) -> dict:
        """无发射能力：记录事件并返回 {'status': 'no_tx'}（不抛）。"""
        self.events.append(_NO_TX_EVENT)
        return {"status": "no_tx"}

    def capabilities(self) -> dict:
        """能力元数据（每次返回新 dict，调用方篡改不回写实例与注册表）。"""
        return {
            "freq_range_hz": (FREQ_MIN_HZ, FREQ_MAX_HZ),
            "detectors": list(DETECTORS),
            "noise_floor_dbm_hz": NOISE_FLOOR_DBM_HZ,
            "simulated": True,
        }

    def _split_frames(self, iq) -> list[list[complex]]:
        """IQ 强制转换 + 简化 4 帧等长切分（尾部长度 %=4 的余数样本不计，规约口径）。"""
        if isinstance(iq, (str, bytes)):
            raise ValueError(f"iq 须为复数样本序列，实际为 {type(iq).__name__}: {iq!r}")
        try:
            items = list(iq)
        except TypeError as exc:
            raise ValueError(
                f"iq 须为复数样本可迭代序列，实际为 {type(iq).__name__}: {iq!r}"
            ) from exc
        for idx, s in enumerate(items):
            if isinstance(s, bool) or not isinstance(s, numbers.Complex):
                raise ValueError(f"iq[{idx}] 须为复数样本，实际为 {type(s).__name__}: {s!r}")
        frame_len = len(items) // _N_FRAMES
        if frame_len < 1:
            raise ValueError(
                f"iq 至少 {_N_FRAMES} 个样本（简化 {_N_FRAMES} 帧检波口径），实际 {len(items)}"
            )
        return [items[i * frame_len : (i + 1) * frame_len] for i in range(_N_FRAMES)]

    def _frame_spectrum(self, frame: list[complex], floor_lin: float) -> list[float]:
        """单帧功率谱：截断至帧长上限→补零到 2 的幂→FFT→逐 bin |X|²/L²（单音幅度 1.0→0dBm）。

        归一化按截断后帧长 L（补零不改变单音 bin 幅度 |X|=A·L，故 |X|²/L²=A² 与补零无关）；
        逐 bin 以 floor_lin（RBW 内底噪线性功率）钳底。
        """
        length = min(len(frame), _MAX_FRAME_SAMPLES)
        work = [complex(s) for s in frame[:length]]
        work.extend([0j] * (_next_pow2(length) - length))
        transformed = _fft_pow2(work)
        denom = float(length * length)
        return [max((abs(x) ** 2) / denom, floor_lin) for x in transformed]


def open_sim_emi_receiver(params: dict | None = None) -> SimEmiReceiver:
    """创建 EMI 接收机仿真后端实例（注册名 sim_emi_receiver）：CISPR 口径读数仿真。

    输入: params: dict | None，键均可缺省——
      - freq_hz: 中心频率 Hz（默认 10e6），须落入 CISPR A+B 频段闭区间 [1e3, 3e9]
        （域外/非有限/bool → ValueError）；
      - detector: 检波器（默认 'peak'），须为 {'peak', 'quasi_peak', 'average'} 之一；
      - rbw_hz: 分辨率带宽 Hz（默认 None=按频段自动：<30MHz→9kHz，≥30MHz→120kHz），
        给定时须为正；
      - rep_hz: 准峰值简化曲线的脉冲重复率 Hz（默认 100），须为正；
      - sample_rate: IQ 频域分析采样率 Hz（默认 1e6），须为正。
    输出: SimEmiReceiver 实例（measure/set_detector/set_rbw/read_samples/capabilities，
      start_tx 一律 BackendError、stop_tx/set_tx_gain 记录 no_tx 事件）。
    错误: params 非 dict|None / 数值键非实数/bool/非有限 / freq 频段外 / rbw_hz·rep_hz·
      sample_rate 非正 / detector 非法 → ValueError（校验先于实例构造，无半初始化对象）。
    """
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(
            f"params 必须为 dict | None，实际为 {type(params).__name__}: {params!r}"
        )

    freq_hz = _as_real("freq_hz", params.get("freq_hz", _DEFAULT_FREQ_HZ))
    if not FREQ_MIN_HZ <= freq_hz <= FREQ_MAX_HZ:
        raise ValueError(
            f"freq_hz {freq_hz!r} 超出 CISPR A+B 频段 [{FREQ_MIN_HZ!r}, {FREQ_MAX_HZ!r}] Hz"
        )

    detector = _validate_detector(params.get("detector", "peak"))

    rbw_raw = params.get("rbw_hz")
    if rbw_raw is None:
        rbw_hz = _auto_rbw(freq_hz)
    else:
        rbw_hz = _as_real("rbw_hz", rbw_raw)
        if rbw_hz <= 0:
            raise ValueError(f"rbw_hz 必须为正，实际为 {rbw_hz!r}")

    rep_hz = _as_real("rep_hz", params.get("rep_hz", _DEFAULT_REP_HZ))
    if rep_hz <= 0:
        raise ValueError(f"rep_hz 必须为正（脉冲重复率），实际为 {rep_hz!r}")

    sample_rate = _as_real("sample_rate", params.get("sample_rate", _DEFAULT_SAMPLE_RATE))
    if sample_rate <= 0:
        raise ValueError(f"sample_rate 必须为正，实际为 {sample_rate!r}")

    return SimEmiReceiver(freq_hz, detector, rbw_hz, rep_hz, sample_rate)


# import 时自注册（override=True：重复 import / importlib.reload 幂等不炸；
# method_names 供注册表 import 期契约形式检查——caps 声明 rx 为真须具备 read_samples）。
register_backend(
    _BACKEND_NAME,
    open_sim_emi_receiver,
    {
        "kind": _BACKEND_NAME,
        "caps": {"tx": False, "rx": True, "freq_range_mhz": (1.0, 3000.0)},
        "params": {
            "freq_hz": "float，缺省 10e6——中心频率 Hz，须落入闭区间 [1e3, 3e9]（CISPR A+B 口径）",
            "detector": "str，缺省 'peak'——检波器，须为 {'peak', 'quasi_peak', 'average'} 之一",
            "rbw_hz": "float，缺省 None——None 按频段自动（<30MHz→9kHz，≥30MHz→120kHz）；给则须为正",
            "rep_hz": "float，缺省 100——准峰值简化曲线的脉冲重复率 Hz，须为正",
            "sample_rate": "float，缺省 1e6——IQ 频域分析采样率 Hz，须为正",
        },
    },
    override=True,
    method_names=list(_METHOD_NAMES),
)
