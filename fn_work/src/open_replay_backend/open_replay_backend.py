"""replay 回放后端：SigMF 真值对按时间轴回放——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def open_replay_backend(sigmf_path: str, speed: float = 1.0) -> object:
    """replay 回放后端：SigMF 真值对按时间轴回放。"""
    raise NotImplementedError("unimplemented:fn:open_replay_backend")
