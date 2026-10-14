"""NRF24 KPI 帧生成（R86 Python 参考实现，与固件 encode_nrf24_frame 同规格）：五计数值→合法帧文本——固件与 parse_nrf24_frame 协议漂移的单点防线；重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

__all__ = ["compose_nrf24_frame"]


def compose_nrf24_frame(seq: int, sent: int, lost: int, retries: int, rpd: int) -> str:
    """按协议规格生成 NRF 帧文本行（不含换行）。

    输入: 五计数值（rpd∈{0,1}）。
    输出: `NRF,<seq>,<sent>,<lost>,<retries>,<rpd>`。
    错误: 非法值域（负数/非整数/rpd∉{0,1}）→ValueError。
    """
    raise NotImplementedError("unimplemented:fn:compose_nrf24_frame")
