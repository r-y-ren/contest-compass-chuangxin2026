"""急停硬化序列：先 trigger_emergency_stop（先停发射+事件留痕）再置 stop_flag；停发射失败仍保证标志置位——重写规约与签名意图详见 fn_docs/responsibility.md。

本文件为 fn-scaffold 骨架桩：签名已定，实现由 fn-implement 对应批次填充。
"""


def harden_emergency_stop(source: str, run_ctx: dict, stop_flag: dict) -> dict:
    """急停硬化序列：先 trigger_emergency_stop（先停发射+事件留痕）再置 stop_flag；停发射失败仍保证标志置位（详见 fn_docs/responsibility.md 功能块）。"""
    raise NotImplementedError("unimplemented:fn:harden_emergency_stop")
