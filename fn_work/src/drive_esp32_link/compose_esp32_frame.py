"""ESP32 KPI 帧生成（R85 Python 参考实现，与固件 encode_esp32_frame 同规格）：五指标→合法帧文本——固件与 parse_esp32_frame 协议漂移的单点防线；重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

__all__ = ["compose_esp32_frame"]


def compose_esp32_frame(
    seq: int, sent: int, err: int, retries: int, rssi: float | None, *, checksum: bool = True
) -> str:
    """按协议规格生成 ESP 帧文本行（不含换行）。

    输入: 五指标值（rssi=None→NA）；checksum=True 附加 *<hex> 校验和后缀（帧体 sum&0xFF）。
    输出: `ESP,<seq>,<sent>,<err>,<retries>,<rssi>[*<hex>]`。
    错误: 非法值域（负数/非整数/非有限 rssi）→ValueError。
    """
    raise NotImplementedError("unimplemented:fn:compose_esp32_frame")
