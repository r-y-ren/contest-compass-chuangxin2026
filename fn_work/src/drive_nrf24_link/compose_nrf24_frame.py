"""NRF24 KPI 帧生成（R86 Python 参考实现，与固件 encode_nrf24_frame 同规格）：五计数值→合法帧文本——固件与 parse_nrf24_frame 协议漂移的单点防线；重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

__all__ = ["compose_nrf24_frame"]

_PREFIX = "NRF"


def _counter_field(value: object, name: str) -> int:
    """计数字段校验：严格非负 int（拒负数/bool/float/字符串等），返回原值。

    与 parse 侧 ``[0-9]+`` 口径对称——本函数拒掉的输入恰恰是解析器不可能吐出的值。
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"field {name!r} must be a non-negative integer, got {value!r}")
    if value < 0:
        raise ValueError(f"field {name!r} must be a non-negative integer, got {value!r}")
    return value


def _rpd_field(rpd: object) -> int:
    """rpd 门限位校验：仅允许 int 0/1（bool 是 int 子类，显式拒——不是 1bit 数值）。"""
    if isinstance(rpd, bool) or not isinstance(rpd, int) or rpd not in (0, 1):
        raise ValueError(f"field 'rpd' must be 0 or 1, got {rpd!r}")
    return rpd


def compose_nrf24_frame(seq: int, sent: int, lost: int, retries: int, rpd: int) -> str:
    """按协议规格生成 NRF 帧文本行（不含换行）。

    输入: 五计数值（rpd∈{0,1}）。
    输出: `NRF,<seq>,<sent>,<lost>,<retries>,<rpd>`。
    错误: 非法值域（负数/非整数/rpd∉{0,1}）→ValueError。
    """
    return ",".join(
        (
            _PREFIX,
            str(_counter_field(seq, "seq")),
            str(_counter_field(sent, "sent")),
            str(_counter_field(lost, "lost")),
            str(_counter_field(retries, "retries")),
            str(_rpd_field(rpd)),
        )
    )
