"""PyVISA SCPI 仪表驱动槽位（远期真仪表接入层）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def create_visa_driver(resource: str, model: str) -> object:
    """PyVISA SCPI 仪表驱动槽位（远期真仪表接入层）。"""
    raise NotImplementedError("unimplemented:fn:create_visa_driver")
