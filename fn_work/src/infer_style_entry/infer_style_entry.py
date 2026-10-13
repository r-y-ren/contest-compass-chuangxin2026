"""主动推理入口：选历史运行/录音→predict_style→样式+置信度+对照标准答案；模型缺失提示不阻塞——重写规约与签名意图详见 fn_docs/responsibility.md。

本文件为 fn-scaffold 骨架桩：签名已定，实现由 fn-implement 对应批次填充。
"""


def infer_style_entry(source: dict) -> dict:
    """主动推理入口：选历史运行/录音→predict_style→样式+置信度+对照标准答案；模型缺失提示不阻塞（详见 fn_docs/responsibility.md 功能块）。"""
    raise NotImplementedError("unimplemented:fn:infer_style_entry")
