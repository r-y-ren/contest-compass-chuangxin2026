"""NRF24 单帧解析（发送/丢包/重传/RPD 门限位，无 RSSI 口径）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import re

__all__ = ["FrameError", "parse_nrf24_frame"]

_PREFIX = "NRF"
_FIELD_COUNT = 6  # NRF,<seq>,<sent>,<lost>,<retries>,<rpd>
_FIELD_NAMES = ("seq", "sent", "lost", "retries", "rpd")
_DIGITS = re.compile(r"^[0-9]+$")  # 显式 [0-9]：拒 Unicode 数字/正负号/小数点/空白


class FrameError(ValueError):
    """坏帧（类型/解码/空/多行/字段数/前缀/数值口径/rpd 取值不合法），消息附具体原因。"""


def _decode(frame: bytes | str) -> str:
    """入参归一为 str：str 原样；bytes 按 ASCII 严格解码（失败→FrameError）；
    其他类型拒收（签名口径仅 bytes | str）。"""
    if isinstance(frame, str):
        return frame
    if isinstance(frame, bytes):
        try:
            return frame.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise FrameError(f"帧字节非 ASCII 文本: {frame!r}（{exc}）") from exc
    raise FrameError(f"frame 必须为 bytes 或 str，得到 {type(frame).__name__}")


def parse_nrf24_frame(frame: bytes | str) -> dict:
    """NRF24 单帧解析：计数寄存器读数 → 类型化 KPI 样本（纯函数）。

    帧格式（CSV 单行，字段数恰为 6）：
        NRF,<seq>,<sent>,<lost>,<retries>,<rpd>
    - seq: 帧序号（非负整数）；sent: 已发送计数（非负整数）；
    - lost: 丢包计数（PLOS_CNT 口径，非负整数）；
    - retries: 重传计数（ARC_CNT 口径，非负整数）；
    - rpd: 1bit 接收功率门限标志，仅允许 0/1（其他值拒收）。

    输入口径：bytes（按 ASCII 解码）或 str；容忍首尾空白与行尾 \\r\\n；
    内嵌换行/回车（多行拼帧）拒收。校验规则同 esp32 风格：
    字段数 6 → 前缀 'NRF' → 数值字段全为非负整数 → rpd∈{0,1}。

    输出样本（键集恰为以下 6 个）：
        {'seq': int, 'sent': int, 'lost': int, 'retries': int,
         'rpd': bool, 'raw': str（去除首尾空白后的解码行）}
    口径注意：NRF24 无 RSSI——产出不含 'rssi' 键（指标口径只丢包/重传）。

    错误（只抛 FrameError，消息附原因）：frame 非 bytes/str、字节非 ASCII、
    空帧、多行、字段数≠6、前缀≠'NRF'、数值字段非非负整数、rpd∉{0,1}。
    """
    line = _decode(frame).strip()  # 容忍行尾 \r\n 及首尾空白
    if not line:
        raise FrameError("空帧：去除首尾空白后无内容")
    if "\r" in line or "\n" in line:
        raise FrameError(f"多行输入拒收（单帧解析只接受一行）: {line!r}")

    fields = line.split(",")
    if len(fields) != _FIELD_COUNT:
        raise FrameError(
            f"字段数错误: 期望 {_FIELD_COUNT}（{_PREFIX},<seq>,<sent>,<lost>,<retries>,<rpd>），"
            f"得到 {len(fields)}: {line!r}"
        )
    if fields[0] != _PREFIX:
        raise FrameError(f"帧前缀错误: 期望 {_PREFIX!r}，得到 {fields[0]!r}")

    values: list[int] = []
    for name, raw_value in zip(_FIELD_NAMES, fields[1:]):
        if not _DIGITS.match(raw_value):
            raise FrameError(f"字段 {name} 必须为非负整数，得到 {raw_value!r}")
        values.append(int(raw_value))

    seq, sent, lost, retries, rpd = values
    if rpd not in (0, 1):
        raise FrameError(f"rpd 为 1bit 门限标志，仅允许 0/1，得到 {rpd}")

    return {
        "seq": seq,
        "sent": sent,
        "lost": lost,  # PLOS_CNT 丢包计数
        "retries": retries,  # ARC_CNT 重传计数
        "rpd": bool(rpd),  # 1bit 门限标志 → bool
        "raw": line,
    }
