"""急停路径：直调停发射→停场景→广播→记录——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def trigger_emergency_stop(ctx: dict, origin: str) -> dict:
    """急停路径：直调停发射→停场景→广播→记录。"""
    raise NotImplementedError("unimplemented:fn:trigger_emergency_stop")
