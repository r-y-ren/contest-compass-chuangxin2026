"""公式(3) 单点路径损耗（含 X_σ 抽样，种子可控）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def compute_pathloss(d: float, d0: float, l0_db: float, n: float, x_sigma: dict | None = None, seed: int | None = None) -> float:
    """公式(3) 单点路径损耗（含 X_σ 抽样，种子可控）。"""
    raise NotImplementedError("unimplemented:fn:compute_pathloss")
