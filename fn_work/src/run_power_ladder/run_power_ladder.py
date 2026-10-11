"""功率阶梯执行：−5dB 起 5dB 档递增，失效即停，事件流落盘——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def run_power_ladder(ctx: dict, ladder_params: dict, failure_cb) -> list:
    """功率阶梯执行：−5dB 起 5dB 档递增，失效即停，事件流落盘。"""
    raise NotImplementedError("unimplemented:fn:run_power_ladder")
