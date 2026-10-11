"""带内平坦度核验（≤4dB 判据）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def check_flatness(power_bins, band: tuple, limit_db: float = 4.0) -> dict:
    """带内平坦度核验（≤4dB 判据）。"""
    raise NotImplementedError("unimplemented:fn:check_flatness")
