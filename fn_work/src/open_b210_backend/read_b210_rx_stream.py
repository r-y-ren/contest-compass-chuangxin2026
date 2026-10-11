"""CH2 监测 IQ 流读取（溢出检测/时间戳标记）——重写规约与签名意图详见 fn_docs/responsibility.md。

鸭子流句柄适配层：只依赖 recv(n) → {'samples', 'overflow', 'ts'} 协议，不 import UHD——
硬件接线归 open_b210_backend，本函数在无硬件环境可用 FakeRecv 全量对抗测试。
"""
from __future__ import annotations

from typing import Any, Iterator

# BackendError 单一事实源在注册表包（与 read_sigmf_timeline 同源同类）：本模块 re-export
# 同一类——调用方 `except BackendError` 跨后端统一接住，外部既有导入用法不破坏。
from src.manage_backend_registry.register_backend import BackendError

__all__ = ["BackendError", "read_b210_rx_stream"]

# 单次 recv 请求的样本数（UHD 典型 spb 量级）。读取粒度不参数化：块边界本就随硬件
# 就绪节奏波动，消费方需要精确块大小应自行重组缓冲，而非在此承诺假精确。
_RECV_NUM_SAMPS = 65536

# 连续空样本块熔断阈（缺省 200）：RX 空转往往是增益/天线/频率配错导致的"无输入"，
# 无限空转只会挂死消费方——超阈即 BackendError 快速失败。
_IDLE_LIMIT_DEFAULT = 200


def _is_uint(value: object) -> bool:
    """非负 int 校验（bool 是 int 子类，一并排除）。"""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def read_b210_rx_stream(
    stream_handle: Any,
    max_blocks: int | None = None,
    *,
    overflow_limit: int = 10,
    idle_limit: int = _IDLE_LIMIT_DEFAULT,
) -> Iterator[dict]:
    """从 CH2 监测通道连续读取 IQ 流（生成器：逐块产出时间戳与溢出标志）。

    输入: stream_handle=鸭子流句柄（须具备可调用 recv(n)，返回
          {'samples': list[complex], 'overflow': bool, 'ts': int}——'ts'/'overflow'
          缺失时取缺省（None/False）并在产出块标注 'partial_meta': True）、
          max_blocks=最多产出的数据块数（None=无限，由消费方 break 断流）、
          overflow_limit=允许的最大连续溢出块数、idle_limit=允许的最大连续空样本块数
          （缺省 200，超阈熔断防 RX 空转挂死）。
    输出: 生成器，逐数据块 dict：{'samples': list[complex]（浅拷贝防句柄侧缓冲复用，
          元素原样透传、规整归消费方）, 'ts': 产出块单调序号（起于 0，空块跳过不占号），
          'overflow': 本块溢出标志, 'device_ts': recv 返回的设备时间戳原值}；recv dict
          缺 'ts'/'overflow' 键时附 'partial_meta': True（缺省值兜底但不静默）。
    错误: 句柄缺/不可调用 recv、max_blocks 非 None-非负int、overflow_limit/idle_limit
          非非负int → ValueError（调用时即刻抛，首块前报错）；recv 抛异常/返回非 dict
          → BackendError（原因原文并入消息，__cause__ 保留）；连续溢出块数
          > overflow_limit → BackendError（第 overflow_limit+1 个连续溢出块不产出）；
          连续空样本块数 > idle_limit → BackendError（消息含空转计数与
          "RX 无数据（检查增益/天线/频率）"提示，检查增益/天线/频率后再重试）。
    热停止: 消费方不取即不读——生成器惰性，recv 只在 next() 触发时发生。
    """
    recv = getattr(stream_handle, "recv", None)
    if not callable(recv):
        raise ValueError(
            f"stream_handle 缺少可调用的 recv(n) 方法: {stream_handle!r}"
        )
    if max_blocks is not None and not _is_uint(max_blocks):
        raise ValueError(f"max_blocks 须为 None 或非负 int，收到: {max_blocks!r}")
    if not _is_uint(overflow_limit):
        raise ValueError(f"overflow_limit 须为非负 int，收到: {overflow_limit!r}")
    if not _is_uint(idle_limit):
        raise ValueError(f"idle_limit 须为非负 int，收到: {idle_limit!r}")

    # 校验即刻完成后才建生成器（调用即抛，不推迟到首块 next）——与 read_sigmf_timeline
    # 的"首块前报错"口径一致。
    return _iter_blocks(recv, max_blocks, overflow_limit, idle_limit)


def _iter_blocks(
    recv: Any,
    max_blocks: int | None,
    overflow_limit: int,
    idle_limit: int,
) -> Iterator[dict]:
    """实际读取循环：入口校验已完成，此处纯产出逻辑。"""
    block_seq = 0              # 产出块单调序号（空块跳过不占号）
    produced = 0               # 已产出数据块数（max_blocks 上限对齐"产出的块"，非 recv 次数）
    consecutive_overflows = 0  # 连续溢出块计数（任一非溢出 recv 即清零——含空净块）
    idle_blocks = 0            # 连续空样本块空转计数（任一携带样本的块清零；熔断阈值 idle_limit）

    while max_blocks is None or produced < max_blocks:
        try:
            chunk = recv(_RECV_NUM_SAMPS)
        except Exception as exc:  # 任何底层失联（UHD/传输层）统一转域错误，原因链保留
            raise BackendError(
                f"CH2 IQ 流读取失败（recv 异常）: {type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(chunk, dict):
            raise BackendError(
                f"recv 须返回 dict（samples/overflow/ts），"
                f"收到: {type(chunk).__name__}: {chunk!r}"
            )

        # 溢出先于空块判定：溢出是设备级状态，与该块是否携带样本无关；
        # 判阈在产出前——超限的那个连续溢出块本身不再产出。
        if chunk.get("overflow"):
            consecutive_overflows += 1
            if consecutive_overflows > overflow_limit:
                raise BackendError(
                    f"CH2 连续溢出超阈: 连续 {consecutive_overflows} 块 "
                    f"> overflow_limit={overflow_limit}，判定读取链失联"
                )
        else:
            consecutive_overflows = 0

        # 空块判定用 len()（numpy 数组 not 会因真值歧义直接 ValueError）：
        # None/长度 0 一律空转——跳过不产出、不占块序号，连续超阈即熔断。
        samples = chunk.get("samples")
        if samples is None or len(samples) == 0:
            idle_blocks += 1
            if idle_blocks > idle_limit:
                raise BackendError(
                    f"CH2 RX 空转熔断: 连续 {idle_blocks} 空块 > idle_limit={idle_limit}，"
                    f"RX 无数据（检查增益/天线/频率）"
                )
            continue
        idle_blocks = 0  # 携带样本：连续空转段清零

        # 'ts'/'overflow' 键缺失：缺省值兜底（device_ts=None / overflow=False），
        # 产出块附 'partial_meta': True——缺省不静默，消费方可据此降级信任。
        block: dict = {
            "samples": list(samples),
            "ts": block_seq,
            "overflow": bool(chunk.get("overflow", False)),
            "device_ts": chunk.get("ts"),
        }
        if "overflow" not in chunk or "ts" not in chunk:
            block["partial_meta"] = True
        yield block
        block_seq += 1
        produced += 1
