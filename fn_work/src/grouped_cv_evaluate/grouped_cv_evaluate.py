"""分组 CV 评测：批次分组防泄漏+混淆矩阵+Macro-F1——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def grouped_cv_evaluate(index_query: dict, model_factory, k: int = 5) -> dict:
    """分组 CV 评测：批次分组防泄漏+混淆矩阵+Macro-F1。"""
    raise NotImplementedError("unimplemented:fn:grouped_cv_evaluate")
