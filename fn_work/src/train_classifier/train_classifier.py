"""七分类训练入口（远程派发/显式本地降级/不足拒训）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def train_classifier(query: dict, hyperparams: dict, where: str = 'remote') -> dict:
    """七分类训练入口（远程派发/显式本地降级/不足拒训）。"""
    raise NotImplementedError("unimplemented:fn:train_classifier")
