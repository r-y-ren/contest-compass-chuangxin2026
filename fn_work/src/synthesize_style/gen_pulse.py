"""脉冲干扰 IQ（占空比参数化）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def gen_pulse(duty_cycle: float, pulse_width_s: float, repeat_hz: float, with_carrier: bool = True, fs: float = 1.0) -> object:
    """脉冲干扰 IQ（占空比参数化）。"""
    raise NotImplementedError("unimplemented:fn:gen_pulse")
