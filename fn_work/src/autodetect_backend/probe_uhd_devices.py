"""枚举在位 USRP（uhd_find_devices），失败不抛出——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations


def probe_uhd_devices() -> dict:
    """枚举在位 USRP 设备清单与原始输出，工具缺失/失败返回空清单+原因。"""
    raise NotImplementedError("unimplemented:fn:probe_uhd_devices")
