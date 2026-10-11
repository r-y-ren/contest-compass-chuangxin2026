"""TX→RX 环回（延迟/衰减/加噪，时间戳因果）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
import numbers
import random
from collections.abc import Iterable, Iterator, Sequence

# 仿真域夹紧边界：增益上限 40dB——纯软件仿真里更高增益只会把幅值指数放大成非物理量，
# 与负延迟同属"越仿真域"：不硬报错（保持流可用），夹紧到边界并附 clamped 标注供审计。
_GAIN_DB_MAX = 40.0

# effects 支持的键；未知键忽略（为上游 open_sim_backend 的参数演进留前向兼容）。
_K_DELAY = "delay_blocks"
_K_GAIN = "gain_db"
_K_NOISE = "noise_dbm"
_K_LEAK = "lo_leak_db"


def _as_real(key: str, raw: object) -> float:
    """effects 数值键统一校验：bool 拒收（布尔增益/噪底几乎必为配置笔误），非实数/非有限→ValueError。"""
    if isinstance(raw, bool) or not isinstance(raw, numbers.Real):
        raise ValueError(f"effects[{key!r}] 必须为实数，实际为 {type(raw).__name__}")
    val = float(raw)
    if not math.isfinite(val):
        raise ValueError(f"effects[{key!r}] 必须为有限数，实际为 {val!r}")
    return val


def _parse_effects(effects: object) -> dict:
    """校验+解析信道效应参数：非法类型在此 ValueError；越仿真域值在此夹紧并记录 clamped。"""
    if not isinstance(effects, dict):
        raise ValueError(f"effects 必须为 dict，实际为 {type(effects).__name__}")
    clamped: dict = {}

    raw_delay = effects.get(_K_DELAY, 0)
    if isinstance(raw_delay, bool) or not isinstance(raw_delay, numbers.Integral):
        raise ValueError(f"effects[{_K_DELAY!r}] 必须为 int，实际为 {type(raw_delay).__name__}")
    delay = int(raw_delay)
    if delay < 0:  # 负延迟破坏因果性 → 夹紧为 0
        clamped[_K_DELAY] = {"from": delay, "to": 0}
        delay = 0

    gain_db = _as_real(_K_GAIN, effects.get(_K_GAIN, 0.0))
    if gain_db > _GAIN_DB_MAX:
        clamped[_K_GAIN] = {"from": gain_db, "to": _GAIN_DB_MAX}
        gain_db = _GAIN_DB_MAX

    raw_noise = effects.get(_K_NOISE)
    noise_dbm = None if raw_noise is None else _as_real(_K_NOISE, raw_noise)
    raw_leak = effects.get(_K_LEAK)
    lo_leak_db = None if raw_leak is None else _as_real(_K_LEAK, raw_leak)

    return {
        "delay_blocks": delay,
        "gain_db": gain_db,
        # 预推导线性量：块变换热路径不再重复做 dB 换算
        "gain_lin": 10.0 ** (gain_db / 20.0),
        # dBm→瓦特功率，I/Q 两维各担一半功率 → 每维高斯 sigma=sqrt(P/2)
        "noise_sigma": None
        if noise_dbm is None
        else math.sqrt(10.0 ** ((noise_dbm - 30.0) / 10.0) / 2.0),
        "leak_ratio": None if lo_leak_db is None else 10.0 ** (lo_leak_db / 20.0),
        "clamped": clamped,
    }


def loopback_sim_stream(
    tx_blocks: Iterable[Sequence[complex]],
    effects: dict,
    seed: int | None = None,
) -> Iterator[tuple[list[complex], dict]]:
    """TX→RX 环回（延迟/衰减/加噪，时间戳因果）。

    sim 内部环回通道：消费 TX IQ 块迭代器，按信道效应变换后作为 RX 流逐块产出
    (rx_block: list[complex], meta: dict)。纯 Python 实现（math/numbers/random，零第三方
    依赖）；TX 块为 numpy 数组时同样按逐元素迭代兼容处理（不在本模块 import numpy）。

    effects 键（缺省=不施加该效应；未知键忽略）:
      - delay_blocks: int ≥ 0，先产出该数量空占位块再吐真实块（因果保持，rx_ts 连续）；
        负值夹紧为 0 并在每块 meta['clamped'] 标注。
      - gain_db: float，幅度乘 10**(gain_db/20)（负值即衰减）；> 40dB 夹紧为 40dB 并标注。
      - noise_dbm: float|None，叠加复高斯噪声（功率按 dBm→W 换算，I/Q 各半），None 不加。
      - lo_leak_db: float|None，加 DC 泄漏单音（模拟发射本振自漏）：幅度 = 本块有效样本
        RMS × 10**(lo_leak_db/20)；空块无 RMS 参考，不加。

    meta 每块必有: {'rx_ts': 单调块序号（从 0）, 'n_samples': 样本数, 'src_index': 来源
    TX 块号（延迟占位块为 None）}；条件字段: 'placeholder'=True（延迟占位块）、'clamped'
    （越域夹紧记录，每块都带——中途接入的消费者也能审计）、'invalid_samples'（本块
    非复数元素计数）。

    每块变换顺序: 非法样本清零 → 幅度增益 → LO 泄漏 → 噪声（噪声最后落，对应 RX 前端底噪）。

    错误: effects 非 dict、数值键非实数/为布尔/非有限、delay_blocks 非整数 → ValueError
    （调用点即抛，无需消费流）；块内非复数元素 → 该元素按 0+0j 处理并在该块 meta 计数
    标注（流不中断）。

    seed: 传入则噪声可复现（同 seed 同输入两轮输出逐位一致）；None 每轮随机。
    """
    params = _parse_effects(effects)  # 急切校验：非法配置在调用点抛出，而非首次 next()
    rng = random.Random(seed)  # 每次调用独立实例：同 seed 复现，且不污染进程全局随机态
    return _stream(tx_blocks, params, rng)


def _stream(
    tx_blocks: Iterable[Sequence[complex]], params: dict, rng: random.Random
) -> Iterator[tuple[list[complex], dict]]:
    """实际生成器：延迟占位块 → 逐 TX 块变换，rx_ts 从 0 连续编号。"""
    delay: int = params["delay_blocks"]
    gain_lin: float = params["gain_lin"]
    noise_sigma = params["noise_sigma"]
    leak_ratio = params["leak_ratio"]
    clamped: dict = params["clamped"]
    rx_ts = 0

    def _meta(n_samples: int, src_index: int | None, placeholder: bool = False, invalid: int = 0) -> dict:
        meta = {"rx_ts": rx_ts, "n_samples": n_samples, "src_index": src_index}
        if placeholder:
            meta["placeholder"] = True
        if clamped:
            meta["clamped"] = dict(clamped)  # 每块独立副本：消费者改单块 meta 不影响他块
        if invalid:
            meta["invalid_samples"] = invalid
        return meta

    for _ in range(delay):
        # 占位块先于消费 TX 产出：即便 TX 流为空，延迟期占位块也照常吐出（RX 时钟先行）
        yield [], _meta(0, None, placeholder=True)
        rx_ts += 1

    for src_index, block in enumerate(tx_blocks):
        base: list[complex] = []
        power_sum = 0.0
        invalid = 0
        for sample in block:
            if isinstance(sample, numbers.Complex):  # int/float/complex（numpy 标量亦注册为 Complex）
                c = complex(sample)
            else:  # 非复数元素：按 0+0j 处理并计数（流不中断），其零值自然不抬泄漏 RMS 参考
                c = 0j
                invalid += 1
            base.append(c)
            power_sum += c.real * c.real + c.imag * c.imag
        n = len(base)
        if n == 0:
            # 空块：增益/噪声/泄漏均无作用对象（泄漏更无 RMS 参考），透传空块保持块结构
            yield [], _meta(0, src_index)
            rx_ts += 1
            continue
        rx = [c * gain_lin for c in base]  # ① 幅度增益
        if leak_ratio is not None:
            # ② LO 自漏：以本块 RMS 为参考的 DC 单音；在增益之后注入，不随通道增益缩放
            dc = math.sqrt(power_sum / n) * leak_ratio
            rx = [c + dc for c in rx]
        if noise_sigma is not None:
            # ③ 复高斯噪声：I/Q 各半功率，最后注入（RX 前端底噪叠加在一切之上）
            rx = [
                c + complex(rng.gauss(0.0, noise_sigma), rng.gauss(0.0, noise_sigma))
                for c in rx
            ]
        yield rx, _meta(n, src_index, invalid=invalid)
        rx_ts += 1
