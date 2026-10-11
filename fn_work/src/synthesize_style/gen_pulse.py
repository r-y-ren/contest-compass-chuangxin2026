"""脉冲干扰 IQ（周期脉冲串，载波可选）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
from numbers import Integral, Real

import numpy as np

__all__ = ["gen_pulse"]


def _finite_real(name: str, value: object) -> float:
    """域自校验：有限实数（拒 bool/NaN/inf/复数/字符串等），返回 float。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} 必须为有限实数（拒 bool/NaN/inf），got {value!r}")
    as_float = float(value)
    if not math.isfinite(as_float):
        raise ValueError(f"{name} 必须为有限实数（拒 NaN/inf），got {value!r}")
    return as_float


def gen_pulse(
    pulse_width_s: float,
    repeat_hz: float,
    n_samples: int,
    carrier_hz: float = 0.0,
    with_carrier: bool = True,
    fs: float = 1.0,
    amplitude: float = 1.0,
) -> tuple[np.ndarray, dict]:
    """周期脉冲串干扰 IQ：门控包络 × 连续相位载波。

    - 包络门控：样本 t=n/fs，脉内判定 ``t mod (1/repeat_hz) < pulse_width_s``；
      脉间段恰为零（IQ 精确 0+0j）。
    - 载波相位按全局 t 连续累积（跨脉冲连续，脉冲仅作包络门控）：
      with_carrier=True 脉内为 ``amplitude*exp(j*2π*carrier_hz*t)``；
      with_carrier=False 脉内恒幅 ``amplitude``（实数 +0j 归一形态）。
    - 占空比由二者推导：duty = pulse_width_s*repeat_hz，须 ∈(0,1)；
      duty≥1（脉宽≥周期）物理不可能 → ValueError。
    - 采样欠定区（B7低#9）：repeat_hz ≥ fs/2 → ValueError（每周期不足 2 样本，
      脉位不可分辨，含两值）；duty 极小（如 1e-9）仍为合法路径。
    - 输出长度恰为 n_samples，dtype complex64；
      meta = {'duty_cycle','pulse_width_s','repeat_hz','carrier_hz'}；
      with_carrier=False 时 carrier_hz 不参与合成 → meta['carrier_hz']=None
      并增 'carrier_ignored': True（B7低#10，如实标注载波被忽略）。
    - 域自校验（防御纵深）：pulse_width_s/repeat_hz/carrier_hz/fs/amplitude
      有限实数（pulse_width_s、repeat_hz、fs、amplitude 还须 >0；amplitude 还须
      ∈[1e-30, 1e30]——输出 complex64 表示域，B7中#4）；
      n_samples 正 int；with_carrier 必须 bool 型——域错抛 ValueError（含参数名）。
    """
    width = _finite_real("pulse_width_s", pulse_width_s)
    if width <= 0.0:
        raise ValueError(f"pulse_width_s 必须为有限正数（>0），got {pulse_width_s!r}")
    repeat = _finite_real("repeat_hz", repeat_hz)
    if repeat <= 0.0:
        raise ValueError(f"repeat_hz 必须为有限正数（>0），got {repeat_hz!r}")
    duty = width * repeat
    if duty >= 1.0:
        raise ValueError(
            f"duty 占空比 pulse_width_s*repeat_hz={duty!r} ≥1 物理不可能"
            f"（脉宽≥重复周期），got duty={duty!r}"
        )
    carrier = _finite_real("carrier_hz", carrier_hz)
    if not isinstance(with_carrier, bool):
        raise ValueError(f"with_carrier 必须为 bool 型（拒 int/str/None 等），got {with_carrier!r}")
    if isinstance(n_samples, bool) or not isinstance(n_samples, Integral):
        raise ValueError(f"n_samples 必须为正整数（拒 bool/非整型），got {n_samples!r}")
    n = int(n_samples)
    if n <= 0:
        raise ValueError(f"n_samples 必须为正整数（>0），got {n_samples!r}")
    fs_hz = _finite_real("fs", fs)
    if fs_hz <= 0.0:
        raise ValueError(f"fs 必须为有限正数（>0），got {fs!r}")
    # 采样欠定区（B7低#9）：repeat ≥ fs/2 → 每周期不足 2 样本，脉位不可分辨。
    if repeat >= fs_hz / 2.0:
        raise ValueError(
            f"repeat_hz 须 < fs/2（采样欠定区拒：每周期至少 2 样本），"
            f"got repeat_hz={repeat} ≥ fs/2={fs_hz / 2.0}"
        )
    amp = _finite_real("amplitude", amplitude)
    if amp <= 0.0:
        raise ValueError(f"amplitude 必须为有限正数（>0），got {amplitude!r}")
    if not 1e-30 <= amp <= 1e30:
        raise ValueError(
            f"amplitude 数值超界：须 1e-30 ≤ amplitude ≤ 1e30"
            f"（输出 complex64 表示域：float32 上溢≈3.4e38/下溢≈1.2e-38，留裕量），"
            f"got {amplitude!r}"
        )

    # 全局时间轴 → 门控包络（脉内 1 / 脉间 0）→ 乘载波（相位按全局 t 连续累积）
    t = np.arange(n, dtype=np.float64) / fs_hz
    period = 1.0 / repeat
    r = np.mod(t, period)
    # 周期回绕防护（双侧）：非整比率 fs/repeat 下 fmod 余数在整数边界处可携带
    # 1ulp 噪声——贴 period 的余数实为下一脉冲起点（归零判通），贴 width 的
    # 余数实为脉间下边界（判断）。相对 1e-9 阈值仅覆盖浮点噪声量级。
    env = ((r < width * (1.0 - 1e-9)) | (r > period * (1.0 - 1e-9))).astype(np.float64)
    if with_carrier:
        iq = amp * env * np.exp(1j * (2.0 * math.pi * carrier * t))
        iq[0] = amp + 0.0j  # t=0 必在脉内，相位 0 精确锚点
    else:
        iq = amp * env  # 实数包络（+0j 归一形态），浮点零段保持精确 0
        iq[0] = amp
    meta = {
        "duty_cycle": duty,
        "pulse_width_s": width,
        "repeat_hz": repeat,
        # B7低#10：with_carrier=False 时载波不参与合成——如实置 None 并标注忽略。
        "carrier_hz": carrier if with_carrier else None,
    }
    if not with_carrier:
        meta["carrier_ignored"] = True
    return iq.astype(np.complex64), meta
