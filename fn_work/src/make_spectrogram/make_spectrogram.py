"""IQ 段→谱图：纯 numpy STFT（hann 窗 + rfft 功率谱 + dBFS 压缩），训练推理共用、短段跳过计数——重写规约与签名意图详见 fn_docs/responsibility.md（B6 顶层/R29；调用方 train_classifier/grouped_cv_evaluate/predict_style）。"""
from __future__ import annotations

from typing import Any

import numpy as np

__all__ = ["make_spectrogram"]

_MIN_NFFT = 8
_MAX_NFFT = 2 ** 16
_DB_FLOOR = 1e-12
# 帧规模上限（B6 中#3）：frames*nfft（约 6700 万元素）——超限拒收而非巨型分配。
_MAX_SPEC_ELEMENTS = 2 ** 26


def _hann(n: int) -> np.ndarray:
    """周期口径 hann 窗（纯 numpy 实现，禁 scipy）。"""
    if n <= 1:
        return np.ones(max(n, 0), dtype=np.float64)
    k = np.arange(n, dtype=np.float64)
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * k / float(n))


def _to_complex_scalar(v: Any) -> complex:
    """单元素规整：实数按 +0j；(I, Q) 浮点二元组 → complex(I, Q)。"""
    if isinstance(v, (tuple, list)):
        if len(v) == 2:
            return complex(float(v[0]), float(v[1]))
        raise ValueError(f"IQ 元素应为标量或 (I,Q) 二元组: {v!r}")
    if isinstance(v, complex):
        return complex(v)
    if isinstance(v, (bool, np.bool_, int, float, np.integer, np.floating)):
        return complex(float(v), 0.0)
    return complex(v)


def _iter_complex(nested: Any):
    """递归展平嵌套序列 → complex 流（保留 (I,Q) 二元组语义）。"""
    for v in nested:
        if isinstance(v, (tuple, list)):
            if len(v) == 2 and not any(isinstance(s, (tuple, list)) for s in v):
                yield _to_complex_scalar(v)
            else:
                yield from _iter_complex(v)
        else:
            yield _to_complex_scalar(v)


def _coerce_iq(iq: Any) -> np.ndarray:
    """输入规整为 complex128 一维数组：list/tuple/ndarray 通用；空输入→空数组不抛。"""
    if iq is None:
        return np.zeros(0, dtype=np.complex128)
    arr = np.asarray(iq)
    if arr.ndim == 0:
        arr = arr.reshape(1)
    if arr.size == 0:
        return np.zeros(0, dtype=np.complex128)
    if arr.ndim == 2 and arr.shape[1] == 2:
        try:  # (N,2) 实矩阵按 I/Q 两列规整
            re = arr[:, 0].astype(np.float64)
            im = arr[:, 1].astype(np.float64)
            return (re + 1j * im).astype(np.complex128)
        except (TypeError, ValueError):
            pass  # 落入通用逐元素路径
    if arr.dtype == object:
        return np.fromiter(_iter_complex(np.asarray(iq).tolist()), dtype=np.complex128)
    try:
        return arr.reshape(-1).astype(np.complex128)
    except (TypeError, ValueError):
        return np.fromiter(_iter_complex(np.asarray(iq).tolist()), dtype=np.complex128)


def _stft_power(x: np.ndarray, nfft: int, hop: int) -> tuple[np.ndarray, int]:
    """分帧→加 hann 窗→FFT 幅度平方取正频率半轴，返回 (freq_bins, frames) float32 功率谱与帧数。

    IQ 为复基带信号，numpy 2.x 的 rfft 不接受复数输入，等价口径为全 fft 取
    前 nfft//2+1 个正频率 bin（freq_bins = nfft//2+1 与 rfft 一致）。

    帧数口径 frames = 1 + ceil((N-nfft)/hop)：末尾不足整窗的帧补零计入
    （1000 样本 / nfft=256 / hop=128 → 6 个完整帧 + 1 个补零尾帧 = 7）。
    """
    n = int(x.size)
    frames = 1 + int(np.ceil((n - nfft) / hop))
    win = _hann(nfft)
    starts = np.arange(frames, dtype=np.int64) * hop
    idx = starts[:, None] + np.arange(nfft, dtype=np.int64)[None, :]
    span = int(starts[-1]) + nfft
    buf = np.zeros(span, dtype=np.complex128)
    buf[:n] = x  # 越界样本（仅末帧可能存在）补零
    spec = np.fft.fft(buf[idx] * win[None, :], n=nfft, axis=1)[:, : nfft // 2 + 1]
    power = np.abs(spec) ** 2.0
    return power.T.astype(np.float32), frames


def _render_preview(spec: np.ndarray, out_path: str) -> str | None:
    """渲染 PNG 预览：matplotlib 延迟 import，库缺/空谱图/失败返回 None 不抛。"""
    if spec.size == 0:
        return None  # 空谱图无可视内容
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    try:
        fig, ax = plt.subplots(figsize=(6, 4), dpi=120)
        im = ax.imshow(spec, origin="lower", aspect="auto", cmap="viridis")
        ax.set_xlabel("time frame")
        ax.set_ylabel("freq bin")
        ax.set_title("IQ spectrogram")
        fig.colorbar(im, ax=ax, label="power (dBFS)")
        fig.tight_layout()
        fig.savefig(out_path)
        plt.close(fig)
        return out_path
    except Exception:
        return None


def make_spectrogram(
    iq,
    nfft: int = 256,
    hop: int | None = None,
    *,
    to_db: bool = True,
    normalize: bool = True,
    preview_png: str | None = None,
) -> dict:
    """IQ 段→谱图（B6 顶层/R29：STFT 参数化，训练推理共用同一实现保证分布一致）。

    纯 numpy 实现链路：hann 分帧（窗长 ``nfft``、步进 ``hop`` 缺省 ``nfft//2``）→
    FFT 幅度平方取正频率半轴（复基带 IQ 的单边功率谱，freq_bins=nfft//2+1）→
    dB 压缩 ``10*log10(p+1e-12)``；``normalize=True`` 时按
    最大值归一（dBFS 口径，谱峰 0 dB；线性口径则峰值归一为 1）。

    输出 dict：``spec`` (freq_bins, frames) float32、``freq_bins``=nfft//2+1、
    ``frames``、``skipped``、``params``={'nfft','hop','window'}；请求 ``preview_png``
    时额外附 ``preview`` 键（成功为路径，库缺/失败为 None）。

    - 段长（含空输入）不足一个窗长：``spec`` 为 (0,0) 空数组、frames=0、skipped=1；
    - 元素规整：接受 list/tuple/ndarray，实数按 +0j，(I,Q) 浮点二元组转 complex。

    :raises ValueError: nfft<8 或 nfft>2**16；hop<1 或 hop>=nfft；
        IQ 含 NaN/inf（消息含首个坏样本位置与计数）；
        frames*nfft > 2**26 帧规模超上限（提示减小样本数或加大 hop）。
    """
    nfft_i = int(nfft)
    if nfft_i < _MIN_NFFT or nfft_i > _MAX_NFFT:
        raise ValueError(f"nfft={nfft_i} 越界（要求 {_MIN_NFFT} ≤ nfft ≤ {_MAX_NFFT}）")
    hop_i = nfft_i // 2 if hop is None else int(hop)
    if hop_i < 1 or hop_i >= nfft_i:
        raise ValueError(f"hop={hop_i} 非法（要求 1 ≤ hop < nfft={nfft_i}）")

    x = _coerce_iq(iq)
    n = int(x.size)
    freq_bins = nfft_i // 2 + 1

    # B6 中#2：脏 IQ 显式拒收（NaN/inf 污染整谱且 dB 压缩后不可辨）——与库内
    # isfinite 先例同口径（configure_b210_channels/_validate_record 均非有限即拒）。
    if not np.isfinite(x).all():
        bad = ~np.isfinite(x)
        raise ValueError(
            f"IQ 含非有限值（NaN/inf）: 首个坏样本位置 {int(bad.argmax())}，"
            f"共 {int(bad.sum())}/{n} 个样本非有限"
        )

    if n < nfft_i:
        spec = np.zeros((0, 0), dtype=np.float32)
        frames = 0
        skipped = 1
    else:
        # B6 中#3：帧规模上限先行（frames 口径与 _stft_power 同式）——超限拒收，
        # 防止 frames*nfft 巨型索引矩阵/谱矩阵一击撑爆内存。
        frames = 1 + int(np.ceil((n - nfft_i) / hop_i))
        if frames * nfft_i > _MAX_SPEC_ELEMENTS:
            raise ValueError(
                f"谱图帧规模超上限: frames={frames} × nfft={nfft_i} = "
                f"{frames * nfft_i} > {_MAX_SPEC_ELEMENTS}（2**26）——"
                "请减小样本数或加大 hop（或分块处理）"
            )
        spec, frames = _stft_power(x, nfft_i, hop_i)
        skipped = 0
        if to_db:
            spec = (10.0 * np.log10(spec.astype(np.float64) + _DB_FLOOR)).astype(np.float32)
        if normalize:
            ref = float(spec.max())
            spec = spec - ref if to_db else (spec / ref if ref > 0.0 else spec)
            spec = np.asarray(spec, dtype=np.float32)

    result = {
        "spec": spec,
        "freq_bins": int(freq_bins),
        "frames": int(frames),
        "skipped": int(skipped),
        "params": {"nfft": int(nfft_i), "hop": int(hop_i), "window": "hann"},
    }
    if preview_png is not None:
        result["preview"] = _render_preview(spec, preview_png)
    return result
