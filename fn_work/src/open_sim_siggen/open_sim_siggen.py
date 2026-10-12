"""1433D 信号源模拟后端（1MHz–20GHz/0.5dB/1ppm 口径）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
import numbers

from src.create_visa_driver.create_visa_driver import MODELS
from src.manage_backend_registry.register_backend import register_backend

__all__ = ["SimSiggen1433D", "open_sim_siggen"]

# 1433D 仿真口径常量（capabilities()/域校验/量化/回读偏差共用同一事实源）。
_FREQ_MIN_HZ = 1e6
_FREQ_MAX_HZ = 2e10
_POWER_MIN_DBM = -140.0
_POWER_MAX_DBM = 10.0
_POWER_RESOLUTION_DB = 0.5
_FREQ_ACCURACY_PPM = 1.0
_FREQ_READBACK_FACTOR = 1.000001  # 1ppm 口径：回读 = 固定 1.000001×设定（+1ppm 正偏差）
_DEFAULT_FREQ_HZ = 1e9
_DEFAULT_POWER_DBM = 0.0
# 相噪口径（B15三轴中②）：10kHz 偏移典型值仿真声明（静态口径键——不做 IQ 相噪注入）。
_PHASE_NOISE_DBC_HZ_10K = -100.0

# 注册名与自登记方法清单（caps 声明 tx=True → 契约要求 tx 三方法齐备；read_samples
# 为统一接口兼容保留（恒 []，信号源无 RX），亦在契约约定方法全集内——一并声明受检）。
_BACKEND_NAME = "sim_siggen_1433d"
_METHOD_NAMES = ["start_tx", "stop_tx", "set_tx_gain", "read_samples"]


def _as_real(key: str, raw: object) -> float:
    """数值参数统一校验：bool 拒收（布尔频率/功率几乎必为配置笔误），非实数/非有限 → ValueError。"""
    if isinstance(raw, bool) or not isinstance(raw, numbers.Real):
        raise ValueError(f"{key} 必须为实数，实际为 {type(raw).__name__}: {raw!r}")
    val = float(raw)
    if not math.isfinite(val):
        raise ValueError(f"{key} 必须为有限数，实际为 {val!r}")
    return val


def _check_freq_hz(freq_hz: float) -> float:
    """频率域校验：[1e6, 20e9] Hz 含端点；越域 ValueError（消息附域）。"""
    if not _FREQ_MIN_HZ <= freq_hz <= _FREQ_MAX_HZ:
        raise ValueError(
            f"freq_hz {freq_hz!r} Hz 超出 1433D 仿真频率域 [1e6, 20e9] Hz（1MHz–20GHz，含端点）"
        )
    return freq_hz


def _check_power_dbm(power_dbm: float) -> float:
    """功率域校验：[-140, +10] dBm 含端点（按原始请求值判域，先于 0.5dB 量化）；越域 ValueError（消息附域）。"""
    if not _POWER_MIN_DBM <= power_dbm <= _POWER_MAX_DBM:
        raise ValueError(
            f"power_dbm {power_dbm!r} dBm 超出 1433D 仿真功率域 [-140, +10] dBm（含端点）"
        )
    return power_dbm


def _quantize_power_db(power_dbm: float) -> float:
    """0.5dB 分辨率量化：就近取整到 0.5dB 格点，半格值（*.25/*.75）一律向 +∞ 方向进位。

    口径（自定并文档化，本函数为唯一实现点）: floor(p/0.5 + 0.5) * 0.5——
    例 -7.3 → -7.5（就近）、-7.0 → -7.0（恰在格点）、+2.25 → +2.5（半格向上）。
    0.5 的整数倍可被二进制浮点精确表示，量化结果无舍入噪声。
    """
    return math.floor(power_dbm / _POWER_RESOLUTION_DB + 0.5) * _POWER_RESOLUTION_DB


def _materialize_iq(iq: object) -> list[list]:
    """IQ 物化+逐样本校验：块迭代器 → list[list]；扁平复数序列视作单块；不可迭代的
    标量块包为单元素块。

    逐个样本校验（B15低#5）：bool/非数值样本（str/None/dict 等）一律 ValueError，
    消息含块/样本位置（iq 块 {bi} 样本 {si}）；iq 本身为不可迭代标量（如 int）时
    整体拒绝（无块/样本位置可言）。校验先于 start_tx 任何状态变更（原子拒绝）。
    """
    if iq is None:
        return []
    try:
        items = list(iq)
    except TypeError as exc:
        raise ValueError(
            f"iq 须为可迭代的 IQ 块/复数样本序列，实际为 {type(iq).__name__}: {iq!r}"
        ) from exc
    if items and all(isinstance(s, numbers.Complex) for s in items):
        blocks = [list(items)]  # 扁平 IQ 序列（[1+0j, 2+0j]）视作单块登记
    else:
        blocks = []
        for block in items:
            try:
                blocks.append(list(block))
            except TypeError:
                blocks.append([block])  # 不可迭代的标量块包为单元素块
    for bi, block in enumerate(blocks):
        for si, sample in enumerate(block):
            if isinstance(sample, bool) or not isinstance(sample, numbers.Complex):
                raise ValueError(
                    f"iq 块 {bi} 样本 {si} 须为实数/复数样本，实际为 "
                    f"{type(sample).__name__}: {sample!r}"
                )
    return blocks


class SimSiggen1433D:
    """1433D 信号源仿真后端实例（SCPI 等价参数面 + 统一后端鸭子接口）。

    SCPI 命令映射复用 create_visa_driver.MODELS['1433d']（文档注明复用：真仪表与
    sim 仪表同槽可换的同一张表——本模块只读引用，实例持拷贝，绝不回写全局表；
    每次参数设置同步留档 last_scpi 等价 SCPI 原句，供链路核查）。

    仿真口径（与 capabilities() 键一一对应，文档即规约）:
      - 频率域 [1e6, 20e9] Hz 含端点，越域 ValueError（消息附域）；
      - 功率域 [-140, +10] dBm 含端点（按原始请求判域，如 10.2 虽可量化落 10.0 仍拒），
        生效值量化到 0.5dB 格点（就近、半格向 +∞ 进位，例 -7.3 → -7.5），
        get_power 返回量化生效值 + 量化标注；
      - 回读口径: get_freq = 固定 1.000001×设定（+1ppm 相对偏差——freq_accuracy_ppm=1.0
        口径的非随机仿真，每次回读同一偏差，文档注明）；get_power = 量化后生效值；
      - 相噪口径（B15三轴中②）: 静态声明面——capabilities 'phase_noise_dbc_hz_10k'
        缺省 -100 dBc/Hz（10kHz 偏移典型值仿真声明），set_phase_noise(≤0)/get_phase_noise
        参数化，不做 IQ 相噪注入（start_tx 登记的 IQ 原样保留）；
      - start_tx 只登记不真发（记录 IQ + 当前参数并返回统计）；
        read_samples 恒 []（信号源无 RX 通道，方法仅为统一接口兼容保留，文档注明）。
    """

    def __init__(
        self,
        freq_hz: float = _DEFAULT_FREQ_HZ,
        power_dbm: float = _DEFAULT_POWER_DBM,
    ) -> None:
        self._commands = dict(MODELS["1433d"])  # 复用真仪表命令映射（只读拷贝）
        self._freq_hz = _check_freq_hz(_as_real("freq_hz", freq_hz))
        self._requested_power_dbm = _check_power_dbm(_as_real("power_dbm", power_dbm))
        self._power_dbm = _quantize_power_db(self._requested_power_dbm)
        self._phase_noise_dbc_hz = _PHASE_NOISE_DBC_HZ_10K
        self._output = False
        self._tx_active = False
        self._tx_iq_blocks: list[list] = []
        self._tx_params: dict = {}
        self._last_scpi: str | None = None

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<SimSiggen1433D freq_hz={self._freq_hz!r} power_dbm={self._power_dbm!r} "
            f"output={self._output!r} tx_active={self._tx_active!r}>"
        )

    # ---- 只读状态面 ----

    @property
    def freq_hz(self) -> float:
        """频率设定点（无偏差的设定值；带 1ppm 仿真偏差的回读走 get_freq）。"""
        return self._freq_hz

    @property
    def output(self) -> bool:
        """射频输出开关状态（出厂默认关）。"""
        return self._output

    @property
    def tx_active(self) -> bool:
        """是否处于发射登记态（start_tx 置位 / stop_tx 复位；纯仿真标记，不真发）。"""
        return self._tx_active

    @property
    def last_scpi(self) -> str | None:
        """最近一次参数设置对应的等价 SCPI 原句（按 MODELS['1433d'] 模板展开）。"""
        return self._last_scpi

    @property
    def scpi_commands(self) -> dict:
        """实例持有的 1433d 命令映射拷贝（改它不影响全局 MODELS 表）。"""
        return dict(self._commands)

    @property
    def tx_iq_blocks(self) -> list[list]:
        """最近一次 start_tx 登记的 IQ 块（拷贝；未登记为 []）。"""
        return [list(block) for block in self._tx_iq_blocks]

    @property
    def tx_params(self) -> dict:
        """最近一次 start_tx 登记时刻的参数快照 {'freq_hz', 'power_dbm', 'output'}（拷贝）。"""
        return dict(self._tx_params)

    # ---- 内部：SCPI 等价原句留档 ----

    def _scpi(self, command_key: str, **args) -> str:
        """按 MODELS['1433d'] 模板格式化等价 SCPI 原句（只读复用；未知键 KeyError 视为编程错）。"""
        return self._commands[command_key].format(**args)

    # ---- SCPI 等价参数面 ----

    def set_freq(self, freq_hz) -> float:
        """设置频率：[1e6, 20e9] Hz 含端点。

        输入: freq_hz 实数（bool/非实数/非有限 → ValueError）。
        输出: 生效设定点（float，无偏差原值）。
        错误: 越域 → ValueError（消息附频率域）。
        """
        val = _check_freq_hz(_as_real("freq_hz", freq_hz))
        self._freq_hz = val
        self._last_scpi = self._scpi("set_freq", mhz=val / 1e6)
        return val

    def set_power(self, power_dbm) -> float:
        """设置输出功率：[-140, +10] dBm 含端点，生效值按 0.5dB 分辨率量化。

        输入: power_dbm 实数（按原始请求判域；bool/非实数/非有限 → ValueError）。
        输出: 量化后生效值（float，0.5dB 格点；就近取整、半格向 +∞ 进位——例
          -7.3 → -7.5、+2.25 → +2.5；get_power 另附量化标注）。
        错误: 越域 → ValueError（消息附功率域；如 10.2 虽可量化落 10.0 仍拒）。
        """
        raw = _check_power_dbm(_as_real("power_dbm", power_dbm))
        quantized = _quantize_power_db(raw)
        self._requested_power_dbm = raw
        self._power_dbm = quantized
        self._last_scpi = self._scpi("set_power", dbm=quantized)
        return quantized

    def output_on(self) -> bool:
        """打开射频输出（幂等）；返回最新状态 True。"""
        self._output = True
        self._last_scpi = self._scpi("output_on")
        return True

    def output_off(self) -> bool:
        """关闭射频输出（幂等）；返回最新状态 False。"""
        self._output = False
        self._last_scpi = self._scpi("output_off")
        return False

    def get_freq(self) -> float:
        """频率回读（仿真口径）：固定 1.000001×设定 = +1ppm 相对正偏差。

        非随机模型——每次回读同一偏差（freq_accuracy_ppm=1.0 口径的确定性仿真，
        文档注明）；无偏差设定点走 freq_hz 属性。
        """
        return self._freq_hz * _FREQ_READBACK_FACTOR

    def get_power(self) -> dict:
        """功率回读（仿真口径）= 量化后生效值 + 量化标注。

        返回（每次新 dict）: {'power_dbm': 量化生效值（0.5dB 格点）,
        'requested_dbm': 原始请求值, 'resolution_db': 0.5,
        'quantized': 本次请求是否被网格舍入（恰在格点为 False）}。
        """
        return {
            "power_dbm": self._power_dbm,
            "requested_dbm": self._requested_power_dbm,
            "resolution_db": _POWER_RESOLUTION_DB,
            "quantized": self._requested_power_dbm != self._power_dbm,
        }

    def set_phase_noise(self, db) -> float:
        """设置相噪口径（静态声明面，B15三轴中②）：dBc/Hz @ 10kHz 偏移，须 ≤0。

        输入: db 实数（bool/非实数/非有限 → ValueError；>0 → ValueError——dBc/Hz 相噪
        为非正值）。输出: 生效声明值。
        行为: 纯静态口径（capabilities 'phase_noise_dbc_hz_10k' 回显当前值）；
        不做 IQ 相噪注入——start_tx 登记的 IQ 样本原样保留，文档注明。
        """
        val = _as_real("phase_noise_db", db)
        if val > 0:
            raise ValueError(
                f"phase_noise_dbc_hz_10k 须为 ≤0 的 dBc/Hz 值（10kHz 偏移口径），实际为 {val!r}"
            )
        self._phase_noise_dbc_hz = val
        return val

    def get_phase_noise(self) -> float:
        """相噪口径回读：当前生效的 dBc/Hz @ 10kHz 偏移声明值（静态口径，无读数偏差）。"""
        return self._phase_noise_dbc_hz

    def capabilities(self) -> dict:
        """能力元数据（每次返回新 dict，调用方篡改不回写实例与注册表）。"""
        return {
            "model": "1433D-sim",
            "freq_range_hz": (_FREQ_MIN_HZ, _FREQ_MAX_HZ),
            "power_range_dbm": (_POWER_MIN_DBM, _POWER_MAX_DBM),
            "power_resolution_db": _POWER_RESOLUTION_DB,
            "freq_accuracy_ppm": _FREQ_ACCURACY_PPM,
            "phase_noise_dbc_hz_10k": self._phase_noise_dbc_hz,
            "simulated": True,
        }

    # ---- 统一后端鸭子接口 ----

    def start_tx(self, iq, effects: dict | None = None) -> dict:
        """登记一次模拟发射：记录 IQ + 当前参数并返回统计——不真发（纯仿真，无射频输出）。

        输入: iq IQ 块迭代器（或扁平复数序列，视作单块；None 视作空）；effects
          信道效应 dict（原样随统计返回，None 记 {}；本后端不施加任何效应）。
        输出: 统计 dict {'simulated': True（仅登记标注）, 'blocks', 'samples',
          'freq_hz'（设定点）, 'power_dbm'（量化生效值）, 'output'（登记时刻开关态）,
          'effects'}；IQ 与参数快照另经 tx_iq_blocks / tx_params 属性核查。
        错误: iq 不可迭代（标量 int 等）或块内/扁平序列内样本非数值（str/bool/None
          等）→ ValueError（消息含块/样本位置；校验先于登记，失败不留半截状态）。
        """
        blocks = _materialize_iq(iq)
        self._tx_iq_blocks = blocks
        self._tx_params = {
            "freq_hz": self._freq_hz,
            "power_dbm": self._power_dbm,
            "output": self._output,
        }
        self._tx_active = True
        return {
            "simulated": True,
            "blocks": len(blocks),
            "samples": sum(len(block) for block in blocks),
            "freq_hz": self._freq_hz,
            "power_dbm": self._power_dbm,
            "output": self._output,
            "effects": effects if effects is not None else {},
        }

    def stop_tx(self) -> None:
        """结束模拟发射：清除发射登记态（幂等）；IQ 记录与参数快照留存供核查。"""
        self._tx_active = False
        return None

    def set_tx_gain(self, db) -> float:
        """发射增益设置：信号源以输出功率为唯一电平控制面——直接映射 set_power。

        输入/输出/错误: 同 set_power（返回量化后生效功率 dBm）。
        """
        return self.set_power(db)

    def read_samples(self, max_blocks: int = 1) -> list:
        """信号源无 RX 通道：恒返回 []（caps 声明 rx=False；方法仅为统一接口兼容保留）。"""
        return []


def open_sim_siggen(params: dict | None = None) -> SimSiggen1433D:
    """创建 1433D 信号源仿真后端实例（注册名 sim_siggen_1433d）。

    输入: params: dict | None，键均可缺省——
      - freq_hz: 初始频率 Hz（默认 1e9），须落入 [1e6, 20e9]（越域 → ValueError）；
      - power_dbm: 初始功率 dBm（默认 0.0），须落入 [-140, +10]（按原始请求判域，
        越域 → ValueError；生效值按 0.5dB 分辨率量化，例 -7.3 → -7.5）。
    输出: SimSiggen1433D 实例（出厂输出关、发射登记态关）。
    错误: params 非 dict / 数值键非实数/为布尔/非有限 / 频率或功率越域 → ValueError
    （校验先于实例构造，失败不产生半初始化对象）。
    """
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(
            f"params 必须为 dict | None，实际为 {type(params).__name__}: {params!r}"
        )
    freq_hz = _check_freq_hz(_as_real("freq_hz", params.get("freq_hz", _DEFAULT_FREQ_HZ)))
    power_dbm = _check_power_dbm(
        _as_real("power_dbm", params.get("power_dbm", _DEFAULT_POWER_DBM))
    )
    return SimSiggen1433D(freq_hz=freq_hz, power_dbm=power_dbm)


# import 时自注册（override=True：重复 import / importlib.reload 幂等不炸；
# method_names 供注册表 import 期契约形式检查——caps 声明 tx=True 须 tx 三方法齐备）。
register_backend(
    _BACKEND_NAME,
    open_sim_siggen,
    {
        "kind": _BACKEND_NAME,
        "model": "1433D-sim",
        "caps": {"tx": True, "rx": False, "freq_range_mhz": (1, 20000)},
    },
    override=True,
    method_names=list(_METHOD_NAMES),
)
