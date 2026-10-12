"""程控衰减器模拟后端（量程 0–75dB/0.25dB 档/纳秒级标称切换）——重写规约与签名意图详见 fn_docs/responsibility.md。

职责口径（B15 顶层 [P1]，R43）:
- 类 SimAttenuator（本文件定义）：纯软件程控衰减器仿真——
  ①量程 [0, 75] dB（≥60dB 器件规格+裕量），档位粒度 0.25dB；
  ②切换时延仿真：每次档位变化记录实测 perf_counter_ns 差（'switch_delay_ns'，
    真时延是程序级——通常数百 ns 至 µs 级，仅如实记录）；器件规格以标称口径
    附 'nominal_switch_ns': 500 声明，不做任何等待/注入延迟（仿真不睡眠）；
  ③get_attenuation() 返回当前量化档位值；档间过渡的零交叉损耗（约 0.1dB 暂态）
    不建模——pass_through 直接按新档位生效，文档注明，勿当暂态仿真用；
  ④pass_through(iq)：IQ × 10^(−att/20) 真衰减数学（线性幅度缩放，供链路演示）；
  ⑤capabilities() 能力元数据；⑥import 时自注册 name='sim_attenuator'。
- 鸭子口径兼容 set_channel_attenuation：实例暴露 callable set_attenuation(db)
  （承载粗+细全量实达值），可直接作为其 ctx['backend'] 替换粗档插件。
- 衰减器非后端主体：注册为插件（caps 自由，tx/rx 为假），method_names 缺省省略
  ——衰减器方法不在 tx/rx 契约方法集内，契约检查交由注册表延迟口径处理。

量化舍入口径: 四舍五入（half-up）到 0.25dB 网格——db/0.25 的小数部分 ≥0.5 上取
（如 30.1→30.0、30.15→30.25、恰在半界 30.125 亦上取 30.25）；0.25 为二进制精确
值，网格点浮点表示精确无漂移。域检查在量化前：db ∉ [0, 75] 拒绝并附域（ValueError）。
"""
from __future__ import annotations

import math
import numbers
from time import perf_counter_ns

from src.manage_backend_registry.register_backend import register_backend

__all__ = ["SimAttenuator", "open_sim_attenuator"]

# 量程域：0–75 dB（≥60dB 器件规格 + 裕量）；档位粒度 0.25 dB；标称切换时延 500 ns。
_ATT_MIN_DB: float = 0.0
_ATT_MAX_DB: float = 75.0
_STEP_DB: float = 0.25
_NOMINAL_SWITCH_NS: int = 500

# 注册名（插件口径：衰减器非后端主体，作为具名插件登记供 lookup）。
_BACKEND_NAME = "sim_attenuator"


def _as_real(key: str, raw: object) -> float:
    """数值参数统一校验：bool 拒收（布尔衰减几乎必为配置笔误），非实数/非有限→ValueError。"""
    if isinstance(raw, bool) or not isinstance(raw, numbers.Real):
        raise ValueError(f"{key} 必须为实数，实际为 {type(raw).__name__}: {raw!r}")
    val = float(raw)
    if not math.isfinite(val):
        raise ValueError(f"{key} 必须为有限数，实际为 {val!r}")
    return val


def _quantize_attenuation(key: str, db: object) -> float:
    """校验+量化：域检查（[0, 75]，超域 ValueError 附域）先于 half-up 量化到 0.25 网格。

    域内输入量化结果必落在 [0, 75] 网格上（上界 75 本就在网格，floor(x+0.5) 不会越顶）；
    网格值均为 0.25 的整数倍，浮点表示精确。
    """
    val = _as_real(key, db)
    if not _ATT_MIN_DB <= val <= _ATT_MAX_DB:
        raise ValueError(
            f"{key} {val!r} dB 超出衰减量程 [{_ATT_MIN_DB}, {_ATT_MAX_DB}] dB"
            f"（{_BACKEND_NAME} 档位粒度 {_STEP_DB} dB）"
        )
    steps = math.floor(val / _STEP_DB + 0.5)  # half-up 四舍五入到网格步数
    return steps * _STEP_DB


class SimAttenuator:
    """程控衰减器仿真实例（鸭子接口：set_attenuation / get_attenuation / pass_through / capabilities）。

    档位状态为量化后的网格值（0.25dB 步进）；set_attenuation 返回切换记录 dict
    （含实测 switch_delay_ns 与标称 nominal_switch_ns），仅真实档位变化追加进
    switch_log；构造时初值直接生效、不记切换（无"切换前状态"可言）。

    零交叉损耗（档间过渡约 0.1dB 暂态）不建模：档位变更即时全域生效，pass_through
    按当前档位一步到位，无暂态轨迹。
    """

    def __init__(self, attenuation_db: float = 0.0) -> None:
        self._attenuation_db = _quantize_attenuation("attenuation_db", attenuation_db)
        self.switch_log: list[dict] = []

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<SimAttenuator attenuation_db={self._attenuation_db!r} switches={len(self.switch_log)}>"

    def set_attenuation(self, db) -> dict:
        """设置衰减档位：量化到 0.25dB 网格并返回切换记录；超域 [0, 75] → ValueError（附域）。

        输入: db 实数衰减值 dB（bool/非实数/非有限拒绝；域内任意实数均可，量化口径
        half-up——30.1→30.0、30.15→30.25）。输出: 切换记录 dict（每次调用返回新
        dict，篡改不回写实例与日志）——
          requested_db: 校验后的原始请求值；applied_db: 量化后生效档位；
          previous_db: 切换前档位；switched: 是否真实变更（幂等重设为 False）；
          switch_delay_ns: 本次状态更新的实测 perf_counter_ns 差（程序级开销，
          真实器件纳秒级时延不仿真等待，仅如实测量记录）；
          nominal_switch_ns: 500（器件规格标称口径，声明性字段）。
        仅 switched=True 的记录追加进 self.switch_log；域错在计时与状态变更前抛出
        （原子拒绝：档位与日志原样保留）。
        """
        previous = self._attenuation_db
        requested = _as_real("db", db)  # 先过数值校验（失败即抛，未动状态）
        if not _ATT_MIN_DB <= requested <= _ATT_MAX_DB:
            raise ValueError(
                f"db {requested!r} dB 超出衰减量程 [{_ATT_MIN_DB}, {_ATT_MAX_DB}] dB"
                f"（{_BACKEND_NAME} 档位粒度 {_STEP_DB} dB）"
            )
        quantized = math.floor(requested / _STEP_DB + 0.5) * _STEP_DB
        start = perf_counter_ns()  # 切换窗口：量化后的状态更新段
        self._attenuation_db = quantized
        elapsed = perf_counter_ns() - start
        record: dict = {
            "requested_db": requested,
            "applied_db": quantized,
            "previous_db": previous,
            "switched": quantized != previous,
            "switch_delay_ns": float(elapsed),
            "nominal_switch_ns": _NOMINAL_SWITCH_NS,
        }
        if record["switched"]:
            self.switch_log.append(dict(record))
        return record

    def get_attenuation(self) -> float:
        """读取当前衰减档位（量化后的网格值，恒为 0.25dB 整数倍）。"""
        return self._attenuation_db

    def pass_through(self, iq) -> list[complex]:
        """IQ 通路仿真：样本 × 10^(−att/20)（真衰减数学：dB→线性幅度因子）。

        输入: iq 可迭代的 IQ 样本序列（元素为实数/复数，bool 拒收）；输出: 缩放后
        的 list[complex]（相位不变，幅度按当前档位衰减）。供链路演示——零交叉暂态
        不建模，档位切换对后续调用即时全域生效。
        """
        factor = 10.0 ** (-self._attenuation_db / 20.0)
        try:
            samples = list(iq)
        except TypeError as exc:
            raise ValueError(
                f"iq 必须为可迭代的 IQ 样本序列，实际为 {type(iq).__name__}: {iq!r}"
            ) from exc
        out: list[complex] = []
        for sample in samples:
            if isinstance(sample, bool) or not isinstance(sample, numbers.Complex):
                raise ValueError(
                    f"IQ 样本须为实数/复数，实际为 {type(sample).__name__}: {sample!r}"
                )
            out.append(complex(sample) * factor)
        return out

    def capabilities(self) -> dict:
        """能力元数据（每次返回新 dict，调用方篡改不回写实例与注册表）。"""
        return {
            "kind": _BACKEND_NAME,
            "attenuation_range_db": (_ATT_MIN_DB, _ATT_MAX_DB),
            "step_db": _STEP_DB,
            "nominal_switch_ns": _NOMINAL_SWITCH_NS,
            "simulated": True,
        }


def open_sim_attenuator(params: dict | None = None) -> SimAttenuator:
    """创建程控衰减器仿真实例（注册名 sim_attenuator，插件口径）。

    输入: params: dict | None，键均可缺省——
      - attenuation_db: 初始衰减 dB（默认 0），域 [0, 75] 内任意实数（构造时即按
        half-up 量化到 0.25 网格生效，不记切换日志）；
      - 其余键忽略（向前兼容）。
    输出: SimAttenuator 实例（鸭子兼容 set_channel_attenuation 的 ctx['backend']——
    callable set_attenuation 承载全量实达值，可替换粗档插件）。
    错误: params 非 dict / attenuation_db 非 bool 外实数/非有限/超域 [0, 75] →
    ValueError（校验先于实例构造，失败不产生半初始化对象）。
    """
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(f"params 必须为 dict | None，实际为 {type(params).__name__}: {params!r}")
    initial = _quantize_attenuation("attenuation_db", params.get("attenuation_db", 0.0))
    return SimAttenuator(initial)


# import 时自注册（override=True：重复 import / importlib.reload 幂等不炸）。
# 衰减器非后端主体：caps 自由（tx/rx 为假），method_names 省略——set_attenuation 等
# 方法不在 tx/rx 契约方法集内，注册表契约检查按缺省口径延迟，登记为可 lookup 插件。
register_backend(
    _BACKEND_NAME,
    open_sim_attenuator,
    {
        "kind": _BACKEND_NAME,
        "caps": {
            "tx": False,
            "rx": False,
            "attenuation_range_db": (_ATT_MIN_DB, _ATT_MAX_DB),
            "step_db": _STEP_DB,
            "nominal_switch_ns": _NOMINAL_SWITCH_NS,
            "simulated": True,
        },
    },
    override=True,
)
