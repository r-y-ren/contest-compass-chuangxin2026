"""识别推理：标签+置信度+模型版本（缺模型不阻塞）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def predict_style(iq_source: str, model=None) -> dict:
    """识别推理：标签+置信度+模型版本（缺模型不阻塞）。"""
    raise NotImplementedError("unimplemented:fn:predict_style")
