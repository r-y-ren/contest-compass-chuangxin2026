"""J(t) 多源干扰合成（公式1）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
from numbers import Real

import numpy as np

__all__ = ["compose_jamming"]


def _finite_real(name: str, value: object) -> float:
    """域自校验：有限实数（拒 bool/NaN/inf/复数/字符串等），返回 float。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} 必须为有限实数（拒 bool/NaN/inf），got {value!r}")
    as_float = float(value)
    if not math.isfinite(as_float):
        raise ValueError(f"{name} 必须为有限实数（拒 NaN/inf），got {value!r}")
    return as_float


def _parse_iq(idx: int, raw: object) -> np.ndarray:
    """分量基带波形 → complex128 一维数组（拒 bool/字符串/非数值/非一维/空）。"""
    if isinstance(raw, (bool, str, bytes)):
        raise ValueError(
            f"components[{idx}]['iq'] 必须为数值序列（实/复），got {type(raw).__name__}"
        )
    try:
        arr = np.asarray(raw)
    except Exception as exc:  # ragged 等无法成阵的输入
        raise ValueError(
            f"components[{idx}]['iq'] 必须为数值序列（实/复），无法解析: {exc}"
        ) from exc
    numeric = (
        np.issubdtype(arr.dtype, np.floating)
        or np.issubdtype(arr.dtype, np.integer)
        or np.issubdtype(arr.dtype, np.complexfloating)
    )
    if not numeric:
        raise ValueError(
            f"components[{idx}]['iq'] 必须为数值序列（实/复），got dtype={arr.dtype}"
        )
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError(
            f"components[{idx}]['iq'] 必须为非空一维序列，got ndim={arr.ndim}, size={arr.size}"
        )
    return arr.astype(np.complex128)


def _parse_envelope(idx: int, spec: object, n: int, comp: dict) -> np.ndarray:
    """A_k(t) → float64 一维数组：'constant'（值取 amplitude 键，缺省 1.0）或等长实数数组。"""
    if isinstance(spec, str):
        if spec != "constant":
            raise ValueError(
                f"components[{idx}]['envelope'] 字符串仅支持 'constant'，got {spec!r}"
            )
        amp = _finite_real(f"components[{idx}]['amplitude']", comp.get("amplitude", 1.0))
        return np.full(n, amp, dtype=np.float64)
    try:
        arr = np.asarray(spec)
    except Exception as exc:
        raise ValueError(
            f"components[{idx}]['envelope'] 必须为 'constant' 或与 iq 等长的一维实数数组，"
            f"无法解析: {exc}"
        ) from exc
    real_numeric = (
        np.issubdtype(arr.dtype, np.floating) or np.issubdtype(arr.dtype, np.integer)
    )
    if not real_numeric:
        raise ValueError(
            f"components[{idx}]['envelope'] 必须为实数数组（拒 bool/复数/非数值），"
            f"got dtype={arr.dtype}（标量常数请用 amplitude 键）"
        )
    if arr.ndim != 1:
        raise ValueError(
            f"components[{idx}]['envelope'] 必须为一维数组，got ndim={arr.ndim}"
        )
    env = arr.astype(np.float64)
    if env.size != n:
        raise ValueError(
            f"components[{idx}]['envelope'] 长度 {env.size} 须与该分量 iq 长度 {n} 等长"
        )
    if not np.all(np.isfinite(env)):
        raise ValueError(f"components[{idx}]['envelope'] 含非有限值（NaN/inf）")
    return env


def compose_jamming(components: list, fs: float = 1.0) -> tuple:
    """J(t) 多源合成（公式1）：J(t) = Σ_k A_k(t)·iq_k(t)·exp(j[2πΔf_k·t + θ_k])。

    - 分量 dict 键：'iq'（必填，该分量基带波形，ndarray|Sequence[complex]）；
      'envelope'（'constant' 时 A_k 取 'amplitude' 键数值、缺省 1.0；或与 iq 等长的
      一维实数数组 A_k(t)，须有限）；'freq_offset_hz'（Δf_k，缺省 0.0）；
      'phase_rad'（θ_k，缺省 0.0）。
    - 等长校验（严格）：各分量 iq 长度必须一致（envelope 数组还须与自身 iq 等长），
      不一致 → ValueError 并列出各长度；不做零填充归整。
    - 输出：(iq: complex64 合成波形, meta: {'n_components', 'length',
      'power_share'}）；power_share 按合成前各分量平均功率 / 分量总功率，
      总功率为 0 时占空口径 = 全 0.0 列表。
    - 域自校验（防御纵深）：components 须非空 list 且元素为 dict；freq_offset_hz/
      phase_rad/amplitude/fs 须有限实数（拒 bool/NaN/inf）；envelope 数组须有限。
      域错统一抛 ValueError（含参数名/分量下标）。
    """
    if not isinstance(components, list):
        raise ValueError(
            f"components 必须为非空 list[dict]（拒 {type(components).__name__}）"
        )
    if not components:
        raise ValueError("components 必须为非空 list[dict]，got 空列表")

    fs_hz = _finite_real("fs", fs)
    if fs_hz <= 0.0:
        raise ValueError(f"fs 必须为有限正数（>0），got {fs!r}")

    iqs: list[np.ndarray] = []
    envs: list[np.ndarray] = []
    freqs: list[float] = []
    phases: list[float] = []
    lengths: list[int] = []
    for idx, comp in enumerate(components):
        if not isinstance(comp, dict):
            raise ValueError(
                f"components[{idx}] 必须为 dict，got {type(comp).__name__}"
            )
        if "iq" not in comp:
            raise ValueError(f"components[{idx}] 缺必填键 'iq'")
        iq = _parse_iq(idx, comp["iq"])
        n = int(iq.size)
        freq = _finite_real(
            f"components[{idx}]['freq_offset_hz']", comp.get("freq_offset_hz", 0.0)
        )
        phase = _finite_real(
            f"components[{idx}]['phase_rad']", comp.get("phase_rad", 0.0)
        )
        env = _parse_envelope(idx, comp.get("envelope", "constant"), n, comp)
        iqs.append(iq)
        envs.append(env)
        freqs.append(freq)
        phases.append(phase)
        lengths.append(n)

    if len(set(lengths)) > 1:
        raise ValueError(f"各分量 iq 长度不一致（须等长，不零填充）: {lengths}")

    n = lengths[0]
    t = np.arange(n, dtype=np.float64) / fs_hz
    total = np.zeros(n, dtype=np.complex128)
    powers: list[float] = []
    for iq, env, freq, phase in zip(iqs, envs, freqs, phases):
        contrib = env * (iq * np.exp(1j * (2.0 * math.pi * freq * t + phase)))
        total += contrib
        powers.append(float(np.mean(np.abs(contrib) ** 2)))

    total_power = float(np.sum(powers))
    if total_power > 0.0:
        power_share = [p / total_power for p in powers]
    else:  # 全零分量：总功率 0 → 占空口径如实列 0.0
        power_share = [0.0] * len(powers)

    meta = {
        "n_components": len(components),
        "length": n,
        "power_share": power_share,
    }
    return total.astype(np.complex64), meta
