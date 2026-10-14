"""sim 仿真后端：全参数软件仿真，无硬件全流程——重写规约与签名意图详见 fn_docs/responsibility.md。

走查环修复（2026-10-14，F2/F3 根因）：read_samples 在**非发射登记态**也产块
——静默态合成低功率底噪块（环回语义补全：发射态回注入流、静默态回底噪），
每实例底噪块预算 _IDLE_NOISE_BUDGET 块（预算尽后回落空读=源耗尽），meta 附
'synthetic': 'noise_floor' 标注（监测路采集窗落在发射窗外时 monitor.csv/
SigMF 录音不再恒空——docstring 在册，tests/open_sim_backend 同步新真值）。
"""
from __future__ import annotations

import math
import numbers
import random
from collections import deque
from collections.abc import Iterable, Sequence

from src.manage_backend_registry.register_backend import register_backend

from .loopback_sim_stream import loopback_sim_stream

__all__ = ["SimBackend", "open_sim_backend"]

# 默认参数域（与 B210 同构的仿真投影）：频率 70MHz–6GHz；增益域 0–90dB 越界夹紧不报错
# （仿真域放宽：freq 域可经 params['caps']['freq_range_mhz'] 扩展）。
_DEFAULT_FREQ_RANGE_MHZ: tuple[float, float] = (70.0, 6000.0)
_GAIN_DB_MIN = 0.0
_GAIN_DB_MAX = 90.0
_DEFAULT_FREQ_HZ = 2.4e9
_DEFAULT_SAMPLE_RATE = 1e6

# 每次 read_samples 的最小泵块数：读 1 块也预变换 _PUMP_CHUNK 块进 RX 缓冲——
# ① set_tx_gain 热更新仍保持"块"粒度生效（不整流定格）；② stop_tx 后缓冲留有界残余可续读。
_PUMP_CHUNK = 4

# ---- 静默态底噪块参数（走查环 F2/F3 修复：非发射登记态也产块） ----
#: 底噪块样本数（复样本/块——短块由 capture 侧零填至 nfft，谱分辨率不受影响）。
_IDLE_NOISE_SAMPLES = 256
#: 底噪总功率（dBm）：低功率底噪口径（远低于任何合法发射电平，不冒充信号）。
_IDLE_NOISE_DBM = -110.0
#: 每实例底噪块预算：预算内静默读每调产块，预算尽后回落 []（源耗尽语义，
#: 监测路连续空读熔断/两路皆尽自然收尾——防失控上限归采集侧 max_monitor_blocks 双保险）。
_IDLE_NOISE_BUDGET = 64
#: 底噪块 meta 标注值（'synthetic' 键——审计可辨"合成底噪"与"发射环回"两来源）。
_IDLE_SYNTHETIC_TAG = "noise_floor"

# 注册名与自登记方法清单（caps 声明 tx/rx 为真 → 契约要求四方法齐备，import 期即受形式检查）。
_BACKEND_NAME = "sim"
_METHOD_NAMES = ["start_tx", "stop_tx", "set_tx_gain", "read_samples"]


def _as_real(key: str, raw: object) -> float:
    """数值参数统一校验：bool 拒收（布尔频率/增益几乎必为配置笔误），非实数/非有限→ValueError。"""
    if isinstance(raw, bool) or not isinstance(raw, numbers.Real):
        raise ValueError(f"{key} 必须为实数，实际为 {type(raw).__name__}: {raw!r}")
    val = float(raw)
    if not math.isfinite(val):
        raise ValueError(f"{key} 必须为有限数，实际为 {val!r}")
    return val


def _parse_freq_range_mhz(raw: object) -> tuple[float, float]:
    """频率域解析：须为 (lo, hi) 两实数（MHz），0 ≤ lo < hi，否则 ValueError。"""
    if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
        raise ValueError(
            f"caps['freq_range_mhz'] 必须为 (lo, hi) 二元组，实际为 {type(raw).__name__}: {raw!r}"
        )
    if len(raw) != 2:
        raise ValueError(f"caps['freq_range_mhz'] 必须恰含 2 个元素，实际为 {len(raw)}")
    lo = _as_real("caps['freq_range_mhz'][0]", raw[0])
    hi = _as_real("caps['freq_range_mhz'][1]", raw[1])
    if lo < 0 or hi <= lo:
        raise ValueError(f"caps['freq_range_mhz'] 须满足 0 ≤ lo < hi，实际为 ({lo}, {hi})")
    return (lo, hi)


class SimBackend:
    """纯软件仿真后端实例（鸭子接口：start_tx / stop_tx / set_tx_gain / read_samples / capabilities）。

    数据通路（全部惰性逐块拉取，无硬件、无线程）:
      TX 块 ×当前发射增益（逐块热读 → set_tx_gain 即时生效于后续变换块）
      → loopback_sim_stream(effects)（延迟/衰减/加噪/LO 泄漏，时间戳因果）
      → 内部 RX 缓冲（deque）→ read_samples 弹出。

    静默态底噪（走查环 F2/F3 修复，环回语义补全）：非发射登记态（未发射/
    已停/源耗尽）且缓冲弹尽时，read_samples 合成低功率底噪块（_IDLE_NOISE_*
    参数域，meta 附 'synthetic': 'noise_floor'）——发射态回注入流、静默态回
    底噪，采集窗落在发射窗外也有数据可采；每实例预算 _IDLE_NOISE_BUDGET 块，
    预算尽后回落 []（源耗尽），不无限产块。

    能力方法在正常使用下自身不抛（stop 幂等、增益越界夹紧、静默读产底噪块
    至预算尽）；start_tx 的 effects 校验委托 loopback_sim_stream 急切执行且
    先于任何状态变更（非法 effects 在调用点 ValueError，原子拒绝：旧流与
    残余原样保留）。
    """

    def __init__(
        self,
        freq_hz: float,
        sample_rate: float,
        tx_gain_db: float,
        tx_bandwidth_hz: float,
        freq_range_mhz: tuple[float, float],
    ) -> None:
        self.freq_hz = freq_hz
        self.sample_rate = sample_rate
        self.tx_gain_db = tx_gain_db
        self.tx_bandwidth_hz = tx_bandwidth_hz
        self._freq_range_mhz = freq_range_mhz
        self._rx_buffer: deque[tuple[list[complex], dict]] = deque()
        self._tx_source: Iterable[Sequence[complex]] | None = None
        self._loopback = None
        self._streaming = False
        # 静默态底噪块状态：预算余量+独立 RNG（固定种子→同参数实例可复现）+块序号。
        self._idle_budget = _IDLE_NOISE_BUDGET
        self._idle_rng = random.Random(0x51B4C0DE)
        self._idle_ts = 0

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<SimBackend freq_hz={self.freq_hz!r} sample_rate={self.sample_rate!r} "
            f"tx_gain_db={self.tx_gain_db!r} streaming={self._streaming!r}>"
        )

    @property
    def streaming(self) -> bool:
        """是否处于发射登记态（源耗尽后自动转 False，残余块仍可续读）。"""
        return self._streaming

    def _gain_scaled(self, blocks: Iterable[Sequence[complex]]):
        """发射增益热路径：逐块读取当前增益——热更新对后续拉取的块即时生效。"""
        for block in blocks:
            lin = 10.0 ** (self.tx_gain_db / 20.0)
            # 非复数样本原样透传，由 loopback_sim_stream 按 0+0j 容错并计数标注
            yield [complex(s) * lin if isinstance(s, numbers.Complex) else s for s in block]

    def start_tx(self, iq_blocks: Iterable[Sequence[complex]], effects: dict | None = None) -> None:
        """登记发射流：IQ 块经 当前增益×loopback_sim_stream(effects) 变换环回内部缓冲。

        输入: iq_blocks IQ 块迭代器；effects 信道效应 dict（delay_blocks/gain_db/
        noise_dbm/lo_leak_db，None=无效应）。输出: None。
        行为: 发射中重复 start_tx → 隐式停旧流并清空残余（不抛，新流从干净缓冲开始）；
        effects 非 dict/数值非法 → loopback_sim_stream 急切校验在此 ValueError——
        原子拒绝：校验先于 stop_tx/清缓冲等一切状态变更，发射中拒绝后旧流与残余
        原样保留（streaming 不变、旧源继续可读）。
        """
        eff = {} if effects is None else effects
        source = iter(iq_blocks)
        loopback = loopback_sim_stream(self._gain_scaled(source), eff)  # 非法 effects 在此抛（先于任何状态变更）
        if self._streaming:
            self.stop_tx()
        self._rx_buffer.clear()
        self._tx_source = source
        self._loopback = loopback
        self._streaming = True
        return None

    def stop_tx(self) -> None:
        """停止发射生产（关闭环回生成器），保留已变换入缓冲的残余块供 read_samples 续读；幂等。"""
        self._streaming = False
        if self._loopback is not None:
            self._loopback.close()
        self._loopback = None
        self._tx_source = None
        return None

    def set_tx_gain(self, db) -> float:
        """设置发射增益：[0, 90] dB 越界夹紧到边界（不抛），即时生效于后续变换块。

        输入: db 实数；输出: 实际生效值；db 非实数/非有限 → ValueError。
        """
        val = _as_real("tx_gain_db", db)
        self.tx_gain_db = min(_GAIN_DB_MAX, max(_GAIN_DB_MIN, val))
        return self.tx_gain_db

    def _idle_noise_block(self) -> "tuple[list[complex], dict]":
        """合成一块低功率底噪（静默态环回口径）：复高斯 I/Q 各半功率，meta 附
        'synthetic': 'noise_floor' 审计标注（与发射环回块可辨）。"""
        # dBm→瓦特功率，I/Q 两维各担一半功率 → 每维高斯 sigma=sqrt(P/2)
        # （与 loopback_sim_stream 噪声换算同式；远低于合法发射电平的底噪口径）。
        sigma = math.sqrt(10.0 ** ((_IDLE_NOISE_DBM - 30.0) / 10.0) / 2.0)
        rng = self._idle_rng
        block = [
            complex(rng.gauss(0.0, sigma), rng.gauss(0.0, sigma))
            for _ in range(_IDLE_NOISE_SAMPLES)
        ]
        meta = {
            "rx_ts": self._idle_ts,
            "n_samples": _IDLE_NOISE_SAMPLES,
            "src_index": None,
            "synthetic": _IDLE_SYNTHETIC_TAG,
        }
        self._idle_ts += 1
        return block, meta

    def read_samples(self, max_blocks: int = 1) -> list[tuple[list[complex], dict]]:
        """弹出环回 RX 块：默认每次 1 块，返回 [(rx_block, meta), ...]。

        惰性生产：发射登记态下按需从环回生成器泵块入缓冲（每次至少泵至
        max(max_blocks, 4) 块或源耗尽）——增益热更新因此对"后续块"生效而非定格整流；
        源耗尽自动结束生产（非错误），残余缓冲照常弹尽；源生成器中途异常则异常照抛、
        发射登记态即时撤销（streaming 即刻转 False 不虚报，已入缓冲残余仍可续读）。

        静默态底噪（走查环 F2/F3 修复）：非发射登记态且缓冲弹尽时合成低功率底噪块
        （meta 附 'synthetic': 'noise_floor'）——每实例预算 _IDLE_NOISE_BUDGET 块，
        预算尽后返回 []（源耗尽语义，与空闲空读兼容）。发射登记态优先弹缓冲残余
        （stop_tx 后残余块先于底噪块产出，溯源不混）。
        max_blocks 非正整数按 1 处理（不抛）。
        """
        if isinstance(max_blocks, bool) or not isinstance(max_blocks, numbers.Integral):
            max_blocks = 1
        max_blocks = max(1, int(max_blocks))
        if self._streaming:
            target = max(max_blocks, _PUMP_CHUNK)
            while len(self._rx_buffer) < target:
                try:
                    rx_block, meta = next(self._loopback)
                except StopIteration:
                    self._streaming = False  # 源耗尽：生产自然终止，残余仍可读
                    break
                except Exception:
                    # 源生成器异常：即时撤销发射登记态（不等下次 read 才自愈），
                    # 异常照常上抛，已变换入缓冲的残余块不受影响。
                    self._streaming = False
                    raise
                self._rx_buffer.append((rx_block, meta))
        if not self._streaming and not self._rx_buffer:
            # 静默态：残余弹尽后按预算补底噪块（残余先于底噪产出，溯源不混）。
            while len(self._rx_buffer) < max_blocks and self._idle_budget > 0:
                self._rx_buffer.append(self._idle_noise_block())
                self._idle_budget -= 1
        out: list[tuple[list[complex], dict]] = []
        while self._rx_buffer and len(out) < max_blocks:
            out.append(self._rx_buffer.popleft())
        return out

    def capabilities(self) -> dict:
        """能力元数据（每次返回新 dict，调用方篡改不回写实例与注册表）。"""
        return {
            "kind": _BACKEND_NAME,
            "tx": True,
            "rx": True,
            "freq_range_mhz": tuple(self._freq_range_mhz),
            "freq_hz": self.freq_hz,
            "sample_rate_hz": self.sample_rate,
            "tx_bandwidth_hz": self.tx_bandwidth_hz,
            "tx_gain_range_db": (_GAIN_DB_MIN, _GAIN_DB_MAX),
        }


def open_sim_backend(params: dict) -> SimBackend:
    """创建纯软件仿真后端实例（注册名 sim）：全参数软件仿真，无硬件全流程。

    输入: params: dict，键均可缺省——
      - freq_hz: 中心频率 Hz（默认 2.4e9），须落入生效频率域（默认 70e6–6e9；
        域外/负值 → ValueError；域可经 caps 扩展）；
      - sample_rate: 采样率 Hz（默认 1e6），须为正（≤0 → ValueError）；
      - tx_gain_db: 发射增益 dB（默认 0），越 [0, 90] 夹紧到边界（不报错）；
      - tx_bandwidth_hz: 发射带宽 Hz（默认取 sample_rate），提供时须为正；
      - caps: 能力域扩展 dict，可含 freq_range_mhz=(lo, hi)（MHz，0 ≤ lo < hi）。
    输出: SimBackend 实例（鸭子接口，发射流经 loopback_sim_stream 变换环回内部缓冲，
      增益热更新即时生效于后续块，stop_tx 保留残余供续读）。
    错误: params 非 dict / 数值键非实数/为布尔/非有限 / freq 域外 / sample_rate 或
      带宽非正 / caps 形状非法 → ValueError（校验先于实例构造，失败不产生半初始化对象）。
    """
    if not isinstance(params, dict):
        raise ValueError(f"params 必须为 dict，实际为 {type(params).__name__}: {params!r}")
    caps = params.get("caps")
    if caps is None:
        caps = {}
    if not isinstance(caps, dict):
        raise ValueError(f"caps 必须为 dict，实际为 {type(caps).__name__}: {caps!r}")
    freq_range_mhz = _parse_freq_range_mhz(caps.get("freq_range_mhz", _DEFAULT_FREQ_RANGE_MHZ))

    freq_hz = _as_real("freq_hz", params.get("freq_hz", _DEFAULT_FREQ_HZ))
    lo_hz, hi_hz = freq_range_mhz[0] * 1e6, freq_range_mhz[1] * 1e6
    if not lo_hz <= freq_hz <= hi_hz:
        raise ValueError(
            f"freq_hz {freq_hz!r} 超出生效频率域 [{lo_hz!r}, {hi_hz!r}] Hz"
            f"（MHz 域 {freq_range_mhz}，可经 caps['freq_range_mhz'] 扩域）"
        )

    sample_rate = _as_real("sample_rate", params.get("sample_rate", _DEFAULT_SAMPLE_RATE))
    if sample_rate <= 0:
        raise ValueError(f"sample_rate 必须为正，实际为 {sample_rate!r}")

    tx_gain_db = _as_real("tx_gain_db", params.get("tx_gain_db", 0.0))
    tx_gain_db = min(_GAIN_DB_MAX, max(_GAIN_DB_MIN, tx_gain_db))

    tx_bandwidth_hz = _as_real("tx_bandwidth_hz", params.get("tx_bandwidth_hz", sample_rate))
    if tx_bandwidth_hz <= 0:
        raise ValueError(f"tx_bandwidth_hz 必须为正，实际为 {tx_bandwidth_hz!r}")

    return SimBackend(freq_hz, sample_rate, tx_gain_db, tx_bandwidth_hz, freq_range_mhz)


# import 时自注册（override=True：重复 import / importlib.reload 幂等不炸；
# method_names 供注册表 import 期契约形式检查——caps 声明 tx/rx 为真须四方法齐备）。
register_backend(
    _BACKEND_NAME,
    open_sim_backend,
    {
        "kind": _BACKEND_NAME,
        "caps": {"tx": True, "rx": True, "freq_range_mhz": tuple(_DEFAULT_FREQ_RANGE_MHZ)},
    },
    override=True,
    method_names=list(_METHOD_NAMES),
)
