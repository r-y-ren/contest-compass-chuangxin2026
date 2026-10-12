"""ESP32 KPI 单帧解析（B11 叶子，上游 drive_esp32_link）。

帧格式（自定义文本行协议，\\n 结尾）::

    ESP,<seq>,<sent>,<err>,<retries>,<rssi>[*<hex>]

- 逗号分隔 6 字段：seq/sent/err/retries 为非负整数，rssi 为 dBm 浮点数或 'NA'（→ None）。
- 可选校验和后缀 ``*<hex>``：存在时对帧体（ESP 起、``*`` 前）做简单 ``sum & 0xFF`` 校验，
  不符抛 FrameError；hex 大小写均可。
- 多余空白容忍（仅限整行首尾，\\r\\n 结尾亦可）；多行输入拒绝。

解析失败（字段非整数/负数/字段数不足/前缀非 ESP 等）统一抛本文件定义的
:class:`FrameError`，其消息含原因与截短后的原行。
"""
from __future__ import annotations

_PREFIX = "ESP"
_FIELD_COUNT = 6
_SUM_MASK = 0xFF
_SNIPPET_LIMIT = 40


class FrameError(ValueError):
    """ESP32 帧解析失败；消息含原因与截短后的原行。"""

    def __init__(self, reason: str, raw: object = "") -> None:
        if isinstance(raw, (bytes, bytearray)):
            text = bytes(raw).decode("utf-8", "replace")
        else:
            text = str(raw)
        snippet = text if len(text) <= _SNIPPET_LIMIT else text[:_SNIPPET_LIMIT] + "..."
        super().__init__(f"{reason} (raw={snippet!r})")
        self.reason = reason
        self.raw = text


def _parse_int_field(text: str, name: str, raw: str) -> int:
    """把字段解析为非负十进制整数，否则抛 FrameError。"""
    try:
        value = int(text, 10)
    except ValueError:
        raise FrameError(f"field {name!r} is not an integer: {text!r}", raw) from None
    if value < 0:
        raise FrameError(f"field {name!r} must be >= 0, got {value}", raw)
    return value


def parse_esp32_frame(frame: bytes | str) -> dict:
    """解析单个 ESP32 KPI 帧并返回指标字典。

    Args:
        frame: 单帧文本（``bytes`` 按 utf-8 解码；容忍首尾空白与 ``\\r\\n``）。

    Returns:
        ``{'seq': int, 'sent': int, 'err': int, 'retries': int,
        'rssi_dbm': float | None, 'checksum_ok': bool | None, 'raw': str}``；
        无校验和后缀时 ``checksum_ok`` 为 ``None``，``raw`` 为 strip 后原行。

    Raises:
        FrameError: 多行/空输入、前缀非 ESP、字段数不为 6、整数字段非数字或为负、
            rssi 非 'NA' 且非数字、校验和格式非法或不符。
    """
    if isinstance(frame, (bytes, bytearray)):
        try:
            text = bytes(frame).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FrameError(f"utf-8 decode failed: {exc}", bytes(frame)) from None
    elif isinstance(frame, str):
        text = frame
    else:
        raise FrameError(f"frame must be bytes or str, got {type(frame).__name__}", frame)

    line = text.strip()
    if not line:
        raise FrameError("empty frame", text)
    if "\n" in line:
        raise FrameError("multiline input is not a single frame", line)

    checksum_ok: bool | None = None
    body = line
    if "*" in line:
        body, _, suffix = line.rpartition("*")
        suffix = suffix.strip()
        if not suffix:
            raise FrameError("empty checksum suffix", line)
        try:
            expected = int(suffix, 16)
        except ValueError:
            raise FrameError(f"invalid checksum hex: {suffix!r}", line) from None
        actual = sum(body.encode("utf-8")) & _SUM_MASK
        if actual != expected:
            raise FrameError(
                f"checksum mismatch: body sum 0x{actual:02X} != 0x{expected:02X}", line
            )
        checksum_ok = True

    fields = [part.strip() for part in body.split(",")]
    if len(fields) != _FIELD_COUNT:
        raise FrameError(f"expected {_FIELD_COUNT} comma fields, got {len(fields)}", line)
    if fields[0] != _PREFIX:
        raise FrameError(f"bad prefix: {fields[0]!r} != {_PREFIX!r}", line)

    rssi_text = fields[5]
    rssi_dbm: float | None = None
    if rssi_text.upper() != "NA":
        try:
            rssi_dbm = float(rssi_text)
        except ValueError:
            raise FrameError(
                f"field 'rssi' is not a number or 'NA': {rssi_text!r}", line
            ) from None

    return {
        "seq": _parse_int_field(fields[1], "seq", line),
        "sent": _parse_int_field(fields[2], "sent", line),
        "err": _parse_int_field(fields[3], "err", line),
        "retries": _parse_int_field(fields[4], "retries", line),
        "rssi_dbm": rssi_dbm,
        "checksum_ok": checksum_ok,
        "raw": line,
    }
