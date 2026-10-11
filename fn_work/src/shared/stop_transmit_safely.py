"""安全停发射唯一出口：幂等静默+事件记录，安全路径不抛出——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def stop_transmit_safely(backend=None) -> dict:
    """安全停发射唯一出口：幂等静默+事件记录，安全路径不抛出。"""
    raise NotImplementedError("unimplemented:fn:stop_transmit_safely")
