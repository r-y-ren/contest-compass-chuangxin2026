"""NRF24 链路驱动：计数帧流（丢包/重传，无 RSSI 口径）——重写规约与签名意图详见 fn_docs/responsibility.md。

编排口径（单帧解析归 parse_nrf24_frame、安全停发射归 stop_transmit_safely，本函数
只做流驱动）：串口行流 → 逐帧解析 → 增量 KPI 样本生成器。与 drive_esp32_link 同构
（serial_config 同形：port/baud/source 行流），差异仅在样本口径——link='nrf24'、
无 rssi 字段（NRF24 无 RSSI 读数，指标口径固定丢包/重传）、多 rpd 1bit 门限位：
- 增量口径：帧内 sent/lost/retries 为固件累计计数寄存器读数（PLOS_CNT/ARC_CNT），
  驱动逐帧求窗增量——per_raw = lost 增量 / sent 增量、retries 为窗重传增量、
  rpd 为当帧门限位（bool 透传）；流首基线取 0（首帧增量即其绝对读数）。
- 损坏处置：坏帧（FrameError，含空行/前缀错/字段错/非文本行）只跳过不产出；
  **连续**坏帧计数达 max_bad_streak（缺省 5）视为损坏超阈——先 stop_transmit_safely
  再抛 LinkError；好帧将连续计数清零，零星坏帧永不触发。
- 断开处置：source 迭代自身抛异常（串口断开等 Exception 族）——先停发射再抛
  LinkError（链上原始异常）；行流耗尽与消费方提前弃流（GeneratorExit 透传）均
  自然结束：不产错、不停发射（收尾停发射归编排方 record_run_streams）。
- 校验时点：serial_config/ctx 全部校验在调用时即刻抛 ValueError、不消费 source
  （同 capture_monitor_spectrum 口径，错误不推迟到首 next）。
"""
from __future__ import annotations

import os
import time
from typing import Iterator
from uuid import uuid4

from .parse_nrf24_frame import FrameError, parse_nrf24_frame
from src.shared.stop_transmit_safely import stop_transmit_safely

#: 错误契约随本函数透传不捕获，FrameError 重导出供调用方就地导入。
__all__ = ["FrameError", "LinkError", "drive_nrf24_link"]

_LINK_NAME = "nrf24"
_DEFAULT_BAUD = 115200
_DEFAULT_MAX_BAD_STREAK = 5

#: 自生成 run_token 前缀（同 run_power_ladder）：ctx 未提供 token 时自生成并写回
#: ctx——同 backend 跨调用各配独立 token，停发射按 (backend, token) 运行级幂等，
#: 每次错误路径均实停（缺省 None 退化为进程级幂等会漏停）；ctx 跨调用复用时
#: '_auto:' 前缀旧 token 一律换新防误继承，外部 token（无前缀）不覆盖。
_AUTO_TOKEN_PREFIX = "_auto:"


class LinkError(RuntimeError):
    """NRF24 链路错误（帧损坏超阈/串口源中断）——抛出前已先走 stop_transmit_safely。

    属性: reason=原因文案; stop_result=停发射结果 dict（status/steps/ts/context）。
    """

    def __init__(self, reason: str, stop_result: dict | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.stop_result = stop_result


def _valid_port(raw: object) -> str:
    """port 校验：非空 str（容忍 os.PathLike），其他类型/空白一律 ValueError。"""
    if isinstance(raw, os.PathLike):
        raw = str(raw)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"serial_config['port'] 必须为非空字符串（串口名），收到: {raw!r}")
    return raw


def _positive_int(raw: object, name: str, default: int) -> int:
    """正整数校验（bool 是 int 子类一并排除；None=取缺省），非法抛 ValueError。"""
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ValueError(
            f"serial_config[{name!r}] 必须为正整数（bool/非 int/小于 1 一律拒绝），收到: {raw!r}"
        )
    return raw


def drive_nrf24_link(serial_config: dict, ctx: dict | None = None) -> Iterator[dict]:
    """NRF24 被测链路驱动：串口计数帧流 → 增量 KPI 样本生成器（无 RSSI 口径）。

    输入: serial_config（与 drive_esp32_link 同形）:
          'port'=串口名（非空 str，必填）、'baud'=波特率（正 int，缺省 115200）、
          'source'=串口行流迭代器（必填，逐行产出 bytes|str——测试经此注入行序列；
          整段文本 str/bytes/bytearray 拒收）、'max_bad_streak'=连续坏帧阈
          （正 int，缺省 5）；ctx=运行上下文 dict|None（'backend'=停发射后端、
          'run_token'=运行级幂等 token，未提供时自生成 '_auto:' 前缀写回 ctx）。
    输出: 生成器逐好帧产出 KPI 样本（键集恰为 5 项，永不携带 rssi 字段）:
          {'timestamp_ms': float（主机单调钟 ms，非降）、'link': 'nrf24'、
          'per_raw': float|None（=lost 增量/sent 增量；不可比窗为 None）、
          'retries': int（窗重传增量）、'rpd': bool（当帧 1bit 门限位透传）}；
          不可比窗另附 'per_note': 'no_delta'（sent 增量为 0——0/0 不可比，交下游
          按不可用样本处理）或 'counter_reset'（计数回退——设备复位/寄存器回绕，
          重定基线不硬算负增量，该窗重传按 0 计）。流首基线取 0（首帧增量即其
          绝对读数）；行流耗尽自然结束。
    错误: serial_config/ctx 非法（非 dict、port 缺/空/非 str、baud/max_bad_streak
          非正 int（bool 拒）、source 缺/None/整段文本/不可迭代）→ ValueError，
          调用时即刻抛出（不推迟到首 next，不消费 source）；连续坏帧达
          max_bad_streak 或 source 迭代自身抛异常（串口断开）→ 先
          stop_transmit_safely（ctx['backend']+运行级 run_token）再抛 LinkError
          （附 .stop_result；源中断链上原始异常）。
    口径: NRF24 无 RSSI 读数——样本永不携带 rssi/rssi_dbm 键（指标口径固定
          丢包/重传+RPD 门限位，此为与 drive_esp32_link 样本的口径差异点）。
    """
    if not isinstance(serial_config, dict):
        raise ValueError(
            f"serial_config 必须为 dict（port/baud/source），实际类型: {type(serial_config).__name__}"
        )
    if ctx is not None and not isinstance(ctx, dict):
        raise ValueError(f"ctx 必须为 dict 或 None，实际类型: {type(ctx).__name__}")

    port = _valid_port(serial_config.get("port"))
    _positive_int(serial_config.get("baud"), "baud", _DEFAULT_BAUD)  # 校验即契约（行流驱动不实开串口）
    max_bad_streak = _positive_int(
        serial_config.get("max_bad_streak"), "max_bad_streak", _DEFAULT_MAX_BAD_STREAK
    )

    source = serial_config.get("source")
    if source is None:
        raise ValueError("serial_config 缺少 'source'（串口行流迭代器——测试经此注入行序列）")
    if isinstance(source, (str, bytes, bytearray)):
        raise ValueError(
            "serial_config['source'] 必须为逐行迭代器而非整段文本（请按行拆分后传入），"
            f"收到整段: {source!r}"
        )
    try:
        lines = iter(source)
    except TypeError as exc:
        raise ValueError(f"serial_config['source'] 须为可迭代的串口行流: {source!r}") from exc

    # 停发射凭据（仅错误路径使用）：backend/run_token 取自 ctx；未提供 token 时
    # 自生成 '_auto:' 前缀 token 写回 ctx（口径见 _AUTO_TOKEN_PREFIX 注释）。
    ctx_fields = ctx if isinstance(ctx, dict) else {}
    backend = ctx_fields.get("backend")
    run_token = ctx_fields.get("run_token")
    if run_token is None or (
        isinstance(run_token, str) and run_token.startswith(_AUTO_TOKEN_PREFIX)
    ):
        run_token = f"{_AUTO_TOKEN_PREFIX}{uuid4().hex}"
        ctx_fields["run_token"] = run_token

    return _iter_nrf24_samples(lines, port, max_bad_streak, backend, run_token)


def _iter_nrf24_samples(
    lines: Iterator[object],
    port: str,
    max_bad_streak: int,
    backend: object,
    run_token: object,
) -> Iterator[dict]:
    """实际驱动循环：入口校验已就绪，此处纯流式解析+增量产出+错误处置。"""
    prev_sent = prev_lost = prev_retries = 0  # 流首基线取 0：首帧增量即绝对读数
    bad_streak = 0
    bad_total = 0
    good_total = 0

    def _stop(reason: str, error_text: str | None = None) -> dict:
        """错误路径停发射（安全路径不抛出，结果供 LinkError 附带）。"""
        context: dict = {"origin": "drive_nrf24_link", "reason": reason, "port": port}
        if error_text is not None:
            context["error"] = error_text
        return stop_transmit_safely(backend, context=context, run_token=run_token)

    try:
        for line in lines:
            try:
                frame = parse_nrf24_frame(line)
            except FrameError:
                bad_streak += 1
                bad_total += 1
                if bad_streak >= max_bad_streak:
                    # 损坏超阈：先停发射再抛（异常能传出即证明停发射已完成）。
                    stop_result = _stop("bad_frame_streak")
                    raise LinkError(
                        f"NRF24 链路帧损坏超阈: 连续坏帧 {bad_streak} >= {max_bad_streak}"
                        f"（port={port}，好帧 {good_total}，累计坏帧 {bad_total}）——已先停发射",
                        stop_result=stop_result,
                    )
                continue  # 阈下坏帧：跳过不产出（好帧将连续计数清零）
            bad_streak = 0
            good_total += 1

            sent_d = frame["sent"] - prev_sent
            lost_d = frame["lost"] - prev_lost
            retries_d = frame["retries"] - prev_retries

            per_note: str | None = None
            if sent_d < 0 or lost_d < 0 or retries_d < 0:
                # 计数回退（设备复位/寄存器回绕）：重定基线，本窗不硬算负增量。
                per_note = "counter_reset"
                per_raw = None
                retries_out = 0
            elif sent_d == 0:
                # 本窗无新包：0/0 不可比，交下游按不可用样本处理（retries 增量照实透出）。
                per_note = "no_delta"
                per_raw = None
                retries_out = retries_d
            else:
                per_raw = lost_d / sent_d
                retries_out = retries_d
            prev_sent, prev_lost, prev_retries = frame["sent"], frame["lost"], frame["retries"]

            sample: dict = {
                "timestamp_ms": time.monotonic_ns() / 1e6,
                "link": _LINK_NAME,
                "per_raw": per_raw,
                "retries": retries_out,
                "rpd": frame["rpd"],
            }
            if per_note is not None:
                sample["per_note"] = per_note
            yield sample
        # 行流耗尽：自然结束（不产错、不停发射——收尾停发射归编排方）。
    except LinkError:
        raise  # 已按"先停发射再抛"语义处置过，不再包装
    except Exception as exc:  # noqa: BLE001 - 串口断开等源异常：先停发射再转 LinkError
        stop_result = _stop("source_error", f"{type(exc).__name__}: {exc}")
        raise LinkError(
            f"NRF24 串口源中断（port={port}，好帧 {good_total}，累计坏帧 {bad_total}）: "
            f"{type(exc).__name__}: {exc}——已先停发射",
            stop_result=stop_result,
        ) from exc
