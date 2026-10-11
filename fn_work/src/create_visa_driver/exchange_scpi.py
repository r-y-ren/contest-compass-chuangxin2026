"""单次 SCPI 交互：发送/应答/超时重试/类型化解析——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def exchange_scpi(driver, command: str, expect: str | None = None) -> object:
    """单次 SCPI 交互：发送/应答/超时重试/类型化解析。"""
    raise NotImplementedError("unimplemented:fn:exchange_scpi")
