"""CH1 发射 IQ 流（分块/欠载检测/热更新）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import Any, Callable

# BackendError 单一事实源在注册表包（与 open_replay_backend / read_sigmf_timeline 同源同类）。
from src.manage_backend_registry.register_backend import BackendError

_LOGGER = logging.getLogger(__name__)


def _is_real_number(value: object) -> bool:
    """int/float 判定（bool 显式拒收——True/False 出现在 IQ 分量位几乎必为错位）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_iq(element: object) -> tuple[complex, bool]:
    """单元素 IQ 规整：complex 原样；(int/float, int/float) 二元组转 complex(I,Q)。

    其余非复数元素（裸实数/字符串/None/非二元组/含 bool 或非数分量的元组）→ 0j，
    并返回 invalid=True 供调用方累计 invalid_zeroed。
    """
    if isinstance(element, complex):
        return element, False
    if isinstance(element, (tuple, list)) and len(element) == 2:
        i, q = element
        if _is_real_number(i) and _is_real_number(q):
            return complex(i, q), False
    return 0j, True


def write_b210_tx_stream(
    stream_handle: Any,
    iq_blocks: Iterable[Sequence[Any]],
    chunk_size: int = 4096,
    *,
    underrun_limit: int = 3,
    on_progress: Callable[[int], Any] | None = None,
) -> dict:
    """CH1 发射 IQ 流：把基带 IQ 块迭代器分块送入鸭子发射流句柄。

    输入: stream_handle 鸭子流句柄——send(iq_chunk)→{'sent': n} 必备；start()/end()
          可选，缺方法跳过：start() 发送前调用，end() 结束后调用且异常吞掉记录
          （含欠载熔断/send 失败路径，finally 兜底）；iq_blocks IQ 块迭代器（每块
          为 Sequence，元素 complex / (I,Q) 二元组直接规整，裸实数与其他垃圾元素
          置 0j 并计数）；chunk_size 分块大小（默认 4096）；underrun_limit 欠载
          累计阈值（默认 3，某块 sent < len(chunk) 记一次欠载，累计超过阈值即
          BackendError）；on_progress 热更新回调，每块下发后以累计已发样本数调用
          （回调异常吞掉记录，不影响发送）。
    输出: {'samples_sent': 累计已发样本数, 'blocks': 已下发分块数（send 调用次数）,
          'underruns': 欠载次数, 'invalid_zeroed': 规整为 0j 的元素数}。
    错误: chunk_size<=0→ValueError（先于 start()，不触碰句柄）；send 抛异常→
          BackendError 包装透传（原异常挂 __cause__）；欠载累计超过 underrun_limit
          →BackendError。
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size 必须为正整数，收到: {chunk_size!r}")

    samples_sent = 0
    blocks = 0
    underruns = 0
    invalid_zeroed = 0

    start = getattr(stream_handle, "start", None)
    if callable(start):
        start()
    try:
        for block in iq_blocks:
            for offset in range(0, len(block), chunk_size):
                chunk: list[complex] = []
                for element in block[offset : offset + chunk_size]:
                    sample, invalid = _normalize_iq(element)
                    if invalid:
                        invalid_zeroed += 1
                    chunk.append(sample)
                try:
                    result = stream_handle.send(chunk)
                except Exception as exc:
                    raise BackendError(
                        f"B210 TX 流 send 失败（第 {blocks + 1} 块，"
                        f"已发 {samples_sent} 样本）: {exc}"
                    ) from exc
                # 契约为 {'sent': n}；非 dict 返回视为 0（走欠载口径暴露坏契约）。
                sent = result.get("sent", 0) if isinstance(result, dict) else 0
                samples_sent += sent
                blocks += 1
                if sent < len(chunk):
                    underruns += 1
                    if underruns > underrun_limit:
                        raise BackendError(
                            f"B210 TX 流欠载超限: 累计 {underruns} 次超过 "
                            f"underrun_limit={underrun_limit}（已发 {samples_sent} 样本）"
                        )
                if on_progress is not None:
                    try:
                        on_progress(samples_sent)
                    except Exception as exc:
                        _LOGGER.warning(
                            "on_progress 回调异常（吞掉，发送继续）: %s: %s",
                            type(exc).__name__,
                            exc,
                        )
    finally:
        end = getattr(stream_handle, "end", None)
        if callable(end):
            try:
                end()
            except Exception as exc:
                _LOGGER.warning(
                    "end() 异常（吞掉，不影响返回）: %s: %s", type(exc).__name__, exc
                )

    return {
        "samples_sent": samples_sent,
        "blocks": blocks,
        "underruns": underruns,
        "invalid_zeroed": invalid_zeroed,
    }
