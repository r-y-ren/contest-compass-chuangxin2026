"""replay 回放后端：SigMF 真值对按时间轴回放——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
import numbers
from typing import Iterator

# BackendError 单一事实源在注册表包（与 read_sigmf_timeline 同源同类）；
# register_backend 供本模块 import 期自注册（与 open_sim_backend 同模式）。
from src.manage_backend_registry.register_backend import BackendError, register_backend

from .read_sigmf_timeline import read_sigmf_timeline

# speed 下限：低于此倍速视为非法（ValueError）
MIN_SPEED = 0.1
# 无发射能力：事件文案（stop_tx/set_tx_gain 记录）与 start_tx 报错文案
_NO_TX_EVENT = "replay 无发射能力"
_NO_TX_MESSAGE = "replay 后端无发射能力"

# 注册名与契约方法清单（caps 声明 rx 为真 → 契约要求 read_samples；tx=False 无要求）。
_BACKEND_NAME = "replay"
_METHOD_NAMES = ["read_samples"]


class ReplayBackend:
    """replay 回放后端实例（注册名 replay）：一次性 SigMF RX 回放流，无 TX 能力。

    read_samples() 逐块弹出 read_sigmf_timeline 的惰性切块——回放不做真实延时等待，
    块产出即出；倍速只体现在块 meta 的 wallclock 语义标注（wallclock_s = time_s / speed）
    与 capabilities 记录，不影响样本内容与产出节奏。块耗尽后恒返回 []（一次性流，不循环）。
    """

    def __init__(self, sigmf_path: str, speed: float, block_size: int):
        self._sigmf_path = sigmf_path
        self._speed = speed
        self._block_size = block_size
        self.events: list[str] = []
        # 急切打开：read_sigmf_timeline 的全部校验（文件缺失/字段缺/截断/时间轴断裂）
        # 在此刻执行，并预取首块——坏文件在 open 时即抛 BackendError，不推迟到首次读取。
        self._timeline: Iterator[dict] = read_sigmf_timeline(
            sigmf_path, block_size=block_size
        )
        self._pending = next(self._timeline, None)

    def read_samples(self) -> dict | list:
        """弹出下一时间戳 IQ 块（含 samples/sample_start/time_s/annotations+wallclock 标注）。

        块产出即出（不 sleep）；一次性流耗尽后恒返回 []。
        """
        if self._pending is None:
            return []
        block, self._pending = self._pending, next(self._timeline, None)
        out = dict(block)
        # 倍速仅作 wallclock 语义标注：回放墙钟时刻 = 录制时间 / speed
        out["wallclock_s"] = block["time_s"] / self._speed
        return out

    def stop_tx(self) -> dict:
        """无发射能力：记录事件并返回 {'status': 'no_tx'}（不抛）。"""
        self.events.append(_NO_TX_EVENT)
        return {"status": "no_tx"}

    def set_tx_gain(self, *args, **kwargs) -> dict:
        """无发射能力：记录事件并返回 {'status': 'no_tx'}（不抛）。"""
        self.events.append(_NO_TX_EVENT)
        return {"status": "no_tx"}

    def start_tx(self, *args, **kwargs) -> dict:
        """replay 后端无 TX：任何发射请求调用即明确报错，绝不静默假装成功。"""
        raise BackendError(_NO_TX_MESSAGE)

    def capabilities(self) -> dict:
        """能力元数据：注册名 replay、无 TX、倍速与切块参数（倍速记录于此）。"""
        return {
            "name": "replay",
            "tx": False,
            "speed": self._speed,
            "block_size": self._block_size,
            "sigmf_path": self._sigmf_path,
        }


def open_replay_backend(
    sigmf_path: str, speed: float = 1.0, block_size: int = 65536
) -> ReplayBackend:
    """replay 回放后端（注册名 replay）：打开 SigMF 真值对，按录制时间轴回放 RX 流。

    输入: sigmf_path=.sigmf-meta 路径（.sigmf-data 同名替换后缀）、speed=倍速（有限实数
          >=0.1，默认 1.0，非 bool；仅影响 wallclock 语义标注与 capabilities，不做真实延时）、
          block_size=每块样本数（透传 read_sigmf_timeline）。
    输出: ReplayBackend 实例（急切打开并预取校验首块）。
    错误: 文件缺失/损坏/时间轴断裂→BackendError（open 时即抛，不 defer）；
          speed<0.1 / 非有限（inf/NaN）/ bool / 非实数 →ValueError（校验先于文件打开）；
          发射请求→BackendError（start_tx 即抛）。
    """
    # 数值口径与 sim 侧一致：bool 拒收（True/False 几乎必为配置笔误）、
    # inf/NaN 等非有限拒收（not (NaN >= 0.1) 为 True → NaN 一并拒绝）。
    if (
        isinstance(speed, bool)
        or not isinstance(speed, numbers.Real)
        or not math.isfinite(float(speed))
        or not speed >= MIN_SPEED
    ):
        raise ValueError(f"speed 必须为有限实数且 >= {MIN_SPEED}，收到: {speed!r}")
    return ReplayBackend(sigmf_path, speed=speed, block_size=block_size)


# import 时自注册（与 open_sim_backend 同模式；override=True：重复 import /
# importlib.reload 幂等不炸）。工厂适配注册表惯例（单 params dict 入参）：
# 拆包 sigmf_path/speed/block_size 三键，参数形状见 meta['params'] 注明。
register_backend(
    _BACKEND_NAME,
    lambda params: open_replay_backend(
        params["sigmf_path"], params.get("speed", 1.0), params.get("block_size", 65536)
    ),
    {
        "kind": _BACKEND_NAME,
        "caps": {"tx": False, "rx": True},
        "params": {
            "sigmf_path": "str，必填——.sigmf-meta 路径（.sigmf-data 同名替换后缀）",
            "speed": "float，缺省 1.0——倍速，须为有限实数 >= 0.1 且非 bool",
            "block_size": "int，缺省 65536——每块样本数，须为正整数",
        },
    },
    override=True,
    method_names=list(_METHOD_NAMES),
)
