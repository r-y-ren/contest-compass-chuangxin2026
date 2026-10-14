"""ESP32 KPI 帧生成（R85 Python 参考实现，与固件 encode_esp32_frame 同规格）：五指标→合法帧文本——固件与 parse_esp32_frame 协议漂移的单点防线；重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math

__all__ = ["compose_esp32_frame"]

_PREFIX = "ESP"
_SUM_MASK = 0xFF


def _counter_field(value: object, name: str) -> int:
    """计数字段校验：严格非负 int（拒负数/bool/float/字符串等），返回原值。

    与 parse 侧 ``[0-9]+`` 口径对称——本函数拒掉的输入恰恰是解析器不可能吐出的值。
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"field {name!r} must be a non-negative integer, got {value!r}")
    if value < 0:
        raise ValueError(f"field {name!r} must be a non-negative integer, got {value!r}")
    return value


def _rssi_field(rssi: float | None) -> str:
    """rssi→帧文本：None→'NA'；非有限（NaN/inf/-inf）→ValueError；数值定 1 位小数。

    1 位小数与固件侧 ``%.1f`` 逐字节一致（RSSI 为 dBm 量级，整数位已足够；
    跨语言格式锁定是 host 等价测试的口径基础）。
    """
    if rssi is None:
        return "NA"
    if isinstance(rssi, bool) or not isinstance(rssi, (int, float)):
        raise ValueError(f"field 'rssi' must be a finite number or None, got {rssi!r}")
    value = float(rssi)
    if not math.isfinite(value):
        raise ValueError(f"field 'rssi' must be a finite number or None, got {rssi!r}")
    return f"{value:.1f}"


def compose_esp32_frame(
    seq: int, sent: int, err: int, retries: int, rssi: float | None, *, checksum: bool = True
) -> str:
    """按协议规格生成 ESP 帧文本行（不含换行）。

    输入: 五指标值（rssi=None→NA）；checksum=True 附加 *<hex> 校验和后缀（帧体 sum&0xFF）。
    输出: `ESP,<seq>,<sent>,<err>,<retries>,<rssi>[*<hex>]`。
    错误: 非法值域（负数/非整数/非有限 rssi）→ValueError。
    """
    body = ",".join(
        (
            _PREFIX,
            str(_counter_field(seq, "seq")),
            str(_counter_field(sent, "sent")),
            str(_counter_field(err, "err")),
            str(_counter_field(retries, "retries")),
            _rssi_field(rssi),
        )
    )
    if not checksum:
        return body
    return f"{body}*{sum(body.encode('utf-8')) & _SUM_MASK:02x}"
