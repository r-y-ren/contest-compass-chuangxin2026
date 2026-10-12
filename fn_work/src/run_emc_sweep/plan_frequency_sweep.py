"""扫描点表纯函数（线性/对数刻度）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math

#: CISPR 频段便捷值（band 参数给定时覆盖 start/stop）
CISPR_BANDS: dict[str, tuple[float, float]] = {
    'cispr_a': (9e3, 150e3),    # CISPR A 频段: 9 kHz – 150 kHz
    'cispr_b': (150e3, 30e6),   # CISPR B 频段: 150 kHz – 30 MHz
}

_LINEAR = 'linear'
_LOG = 'log'


def _as_finite_number(name: str, value: object) -> float:
    """数值参数守卫：拒 bool / 非数值类型 / NaN / Inf，返回 float。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{name} 必须为实数（int/float），bool 与其他类型一律拒绝: {value!r}"
        )
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} 必须为有限数值（拒绝 NaN/Inf）: {value!r}")
    return number


def plan_frequency_sweep(start_hz: float, stop_hz: float, step_hz: float = 1e6,
                         scale: str = 'linear', band: str | None = None) -> dict:
    """扫描点表纯函数（线性/对数刻度）。

    生成 EMC 步进扫描的有序频率点表。两种刻度下 ``step_hz`` 语义不同（务必注意）：

    - ``scale='linear'``（线性刻度）: ``step_hz`` 为固定绝对步长（Hz）。
      点数 = ``ceil((stop-start)/step) + 1``，逐点均匀；末点对齐到 ``stop``。
      当 ``step >= stop - start`` 时退化为单点，并在 ``warnings`` 标注
      ``'single_point'``。
    - ``scale='log'``（对数刻度）: ``step_hz`` 为每步相对增量 ``r``（无量纲，
      非 Hz），每步频率比 = ``1 + r``（如 ``step_hz=0.02`` → 每步 ×1.02）。
      点数 = ``ceil(log(stop/start)/log(1+r)) + 1``，逐点等比；末点对齐到
      ``stop``。

    便捷参数 ``band``: ``'cispr_a'``（9 kHz–150 kHz）或 ``'cispr_b'``
    （150 kHz–30 MHz）；给定时忽略 ``start_hz``/``stop_hz`` 而采用频段值。

    Args:
        start_hz: 起始频率（Hz），要求 > 0。
        stop_hz: 终止频率（Hz），要求 > start_hz。
        step_hz: 步进——线性刻度为绝对 Hz 步长，对数刻度为每步相对增量 r。
        scale: 刻度，``'linear'`` 或 ``'log'``。
        band: CISPR 频段便捷参数，缺省 None（用 start/stop）。

    Returns:
        dict: ``{'points_hz': list[float], 'n_points': int, 'scale': str,
        'step_note': str, 'warnings': list[str]}``；给 ``band`` 时附 ``'band'`` 键。

    Raises:
        ValueError: start_hz<=0 / stop_hz<=start_hz / step_hz<=0 / scale 非法 /
            band 非法 / 参数为 NaN、Inf 或 bool。
    """
    start_hz = _as_finite_number('start_hz', start_hz)
    stop_hz = _as_finite_number('stop_hz', stop_hz)
    step_hz = _as_finite_number('step_hz', step_hz)

    if not isinstance(scale, str) or scale not in (_LINEAR, _LOG):
        raise ValueError(f"scale 非法: {scale!r}（合法值: 'linear', 'log'）")

    if band is not None:
        if not isinstance(band, str) or band not in CISPR_BANDS:
            legal = ', '.join(repr(name) for name in CISPR_BANDS)
            raise ValueError(f"band 非法: {band!r}（合法值: {legal}）")
        start_hz, stop_hz = CISPR_BANDS[band]

    if step_hz <= 0:
        raise ValueError(f"step_hz 必须 > 0: {step_hz!r}")
    if start_hz <= 0:
        raise ValueError(f"start_hz 必须 > 0: {start_hz!r}")
    if stop_hz <= start_hz:
        raise ValueError(
            f"stop_hz 必须 > start_hz（得到 start={start_hz!r}, stop={stop_hz!r}）"
        )

    warnings: list[str] = []
    if scale == _LINEAR:
        step_note = 'linear: step_hz 为固定绝对步长（Hz）'
        span = stop_hz - start_hz
        if step_hz >= span:
            points = [start_hz]
            warnings.append('single_point')
            step_note += '；step ≥ 跨度 → 单点'
        else:
            n_points = math.ceil(span / step_hz) + 1
            points = [start_hz + k * step_hz for k in range(n_points - 1)]
            points.append(stop_hz)
    else:
        step_note = ('log: step_hz 为每步相对增量 r（每步频率比 = 1 + step_hz，'
                     '非 Hz）')
        ratio = 1.0 + step_hz
        n_points = math.ceil(
            math.log(stop_hz / start_hz) / math.log(ratio)
        ) + 1
        points = [start_hz * ratio ** k for k in range(n_points - 1)]
        points.append(stop_hz)

    # 浮点边缘：倒数第二个公式点已触及 stop 时不重复追加末点。
    if len(points) >= 2 and points[-2] >= stop_hz:
        points[-2:] = [stop_hz]

    result = {
        'points_hz': points,
        'n_points': len(points),
        'scale': scale,
        'step_note': step_note,
        'warnings': warnings,
    }
    if band is not None:
        result['band'] = band
    return result
