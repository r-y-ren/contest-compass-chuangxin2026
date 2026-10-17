"""B210 正增益映射的"零衰减"基准增益解析——重写规约与签名意图详见 fn_docs/responsibility.md（域二十四/R95）。

缺省保守常量 60dB（三相对照 C 相位实测锚：60dB≈-20dBm@TRX1、串 30dB 衰减器后天线口≈-50dBm）；
标定钩子：标定三件实测后经钩子替换（在册 'gain' 表方向=档位→power_dbm、lookup_jsr 消费——功率→
增益须反向查表或另立子表，钩子形状实现期前维持常量）；80dB 硬上限：解析结果>80dB、≤0 或非有限
实数→ValueError 拒绝（越界即拒——纵深防御点：按 C 相位单点线性外推 TRX1≈0dBm，30dB 衰减器意外
不在链也不破 0dBm 口径；非合规证明——合规保证=固定串接 30dB 无源衰减器+屏蔽实验室环境+R52 豁免审计）。
"""
from __future__ import annotations

__all__ = ["resolve_base_tx_gain"]


def resolve_base_tx_gain() -> float:
    """解析 B210 正增益映射的基准增益（dB，∈(0, 80]）；越界拒绝。

    输入: 无（常量+标定钩子占位；标定后可扩表参数）/ 输出: float（基准增益 dB）/
    错误: 钩子/配置越界（>80、≤0、非有限实数）→ValueError。
    """
    raise NotImplementedError("unimplemented:fn:resolve_base_tx_gain")
