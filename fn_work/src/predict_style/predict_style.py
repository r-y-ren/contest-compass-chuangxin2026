"""识别推理入口：模型加载（缺失→未识别标注不阻塞）→IQ 取数→make_spectrogram→七类 dummy 规则分类——重写规约与签名意图详见 fn_docs/responsibility.md（B14 顶层/R32；调用方 build_report/serve_console）。"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import numpy as np

from src.index_dataset.index_dataset import index_dataset
from src.make_spectrogram.make_spectrogram import make_spectrogram
from src.open_replay_backend.read_sigmf_timeline import read_sigmf_timeline

__all__ = ["SEVEN_STYLE_LABELS", "predict_style"]

#: 七类样式标签域：六生成样式（配方注册表同名）+ composite 合成模式——dummy 分类
#: 器的阈值匹配只在这七个规范名上进行（模型 labels 字段须含七类名，缺失/非法
#: 回退本缺省）。
SEVEN_STYLE_LABELS = (
    "tone",
    "sweep",
    "chirp",
    "bandlimited_noise",
    "partial_band",
    "pulse",
    "composite",
)

#: 本批已实现的分类器 kind（'cnn' 真网络前向归远期 → not_implemented_yet）
_SUPPORTED_KINDS = ("cnn_dummy",)

_NO_MODEL_NOTE = "未识别（无模型）——不阻塞主流程"

#: nfft 域干跑预检用空段（长度 0 < 任何合法 nfft → 只走参数校验分支）
_EMPTY_IQ = np.zeros(0, dtype=np.complex128)

#: 脉冲门控包络二值化阈值（B14 中#3）：包络低于峰值 -20dB（比值 1/10）判关断——
#: 全段样本口径量化，不再按块聚合（短周期脉冲周期 < 块长时块均值永不下探）。
_GATE_FLOOR_RATIO = 10.0
#: 脉冲占空比带宽（on 段占全段比例的闭区间）与门控周期性自相关峰阈值——
#: duty∈[0.05,0.5] 且二值门控自相关出现显著周期峰才判 pulse（噪声门控占空比
#: ≈0.9+、恒包络≈1.0，均落在窗外）。带宽两侧留采样量化容差 _PULSE_DUTY_EPS
#: （duty_on 是样本计数近似，边界 duty=0.05/0.5 的实测分数可偏入窗内 ±1 个
#: 周期样本数——200/8192≈0.024 的相位极值由容差 0.01+周期性要求共同兜住）。
_PULSE_DUTY_MIN = 0.05
_PULSE_DUTY_MAX = 0.5
_PULSE_DUTY_EPS = 0.01
_PULSE_AC_PEAK = 0.3
#: 零能量退化判定（B14 低#4）：全段总能量（包络平方和）与谱平坦度（dB 峰谷差）阈值。
_DEGENERATE_ENERGY = 1e-12
_DEGENERATE_SPEC_SPAN = 1e-9


def _fail(status: str, note: str, summary: str) -> dict:
    """失败结果行：status+recognized=False+note+来源摘要（不抛出口径的统一形状）。"""
    return {"status": status, "recognized": False, "note": note, "iq_source": summary}


def _normalize_labels(labels: Any) -> list[str]:
    """labels 规整：非空 str 序列原样列表化；缺失/非法 → 七类缺省。"""
    if isinstance(labels, (list, tuple)) and labels:
        if all(isinstance(x, str) and x for x in labels):
            return list(labels)
    return list(SEVEN_STYLE_LABELS)


def _load_model(model: Any) -> tuple[dict | None, dict | None]:
    """模型规整：None/路径不可读/缺 kind → (None, no_model 结果)；其余 → (规范 dict, None)。

    规范 dict：{'kind': str, 'labels': list[str]（七类缺省兜底）, 'weights': 原样}。
    model 为 dict → 直用；为 str → json 读 {'kind','labels','weights'}；其他类型 →
    unsupported_model（模型存在但形态不受支持）。
    """
    if model is None:
        return None, {"status": "no_model", "recognized": False, "note": _NO_MODEL_NOTE}

    if isinstance(model, dict):
        raw = model
        origin = "内联 dict 模型"
    elif isinstance(model, str):
        try:
            with open(model, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError) as exc:  # 文件缺失/IO 错/非法 JSON
            return None, {
                "status": "no_model",
                "recognized": False,
                "note": f"模型文件不可读: {model}: {exc}",
            }
        if not isinstance(raw, dict):
            return None, {
                "status": "no_model",
                "recognized": False,
                "note": f"模型文件不可读（根须为 JSON 对象）: {model}",
            }
        origin = f"模型文件 {model}"
    else:
        return None, {
            "status": "unsupported_model",
            "recognized": False,
            "note": (
                f"model 类型不受支持（dict | str 路径 | None），"
                f"得到 {type(model).__name__}"
            ),
        }

    kind = raw.get("kind")
    if not isinstance(kind, str) or not kind:
        return None, {
            "status": "no_model",
            "recognized": False,
            "note": f"模型缺有效 'kind' 字段（须为 str，如 cnn_dummy）: {origin}",
        }
    return (
        {
            "kind": kind,
            "labels": _normalize_labels(raw.get("labels")),
            "weights": raw.get("weights"),
        },
        None,
    )


def _model_version(kind: str, weights: Any) -> str:
    """模型版本串：kind-sha256(weights)[:8]；无 weights（None/缺键）→ kind-dummy。"""
    if weights is None:
        return f"{kind}-dummy"
    try:
        blob = json.dumps(weights, sort_keys=True, ensure_ascii=False, default=str)
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8]
    except (TypeError, ValueError):  # 不可序列化的极端 weights → 版本退 dummy
        digest = "dummy"
    return f"{kind}-{digest}"


def _to_complex128(iq: Any) -> np.ndarray:
    """ndarray/list IQ 规整为 complex128 一维（(N,2) 实矩阵按 I/Q 两列）。

    :raises ValueError/TypeError: 元素不可规整为复数（透传给调用方转 bad_iq）。
    """
    arr = np.asarray(iq)
    if arr.ndim == 2 and arr.shape[1] == 2:
        arr = arr[:, 0].astype(np.float64) + 1j * arr[:, 1].astype(np.float64)
    return arr.reshape(-1).astype(np.complex128)


def _from_sigmf(meta_path: str) -> tuple[np.ndarray, str, dict | None]:
    """SigMF meta 路径 → (首块 IQ, 摘要, 失败结果|None)。复用 read_sigmf_timeline
    的全套解析校验（datatype/num_samples/captures 时间轴等）；任何读错误 → bad_iq
    （不抛）；空录制 → no_iq。"""
    summary = f"sigmf:{meta_path}"
    try:
        blocks = read_sigmf_timeline(meta_path)
        first = next(iter(blocks), None)
    except Exception as exc:  # BackendError/ValueError/OSError 一律转 bad_iq 不抛
        return _EMPTY_IQ, summary, _fail("bad_iq", f"SigMF 读取失败: {exc}", summary)
    if first is None or not first.get("samples"):
        return _EMPTY_IQ, summary, _fail("no_iq", f"SigMF 录制无样本: {meta_path}", summary)
    iq = np.asarray(first["samples"], dtype=np.complex128)
    return iq, f"{summary}#blk0[{int(iq.size)}]", None


def _from_dataset_query(query: dict) -> tuple[np.ndarray, str, dict | None]:
    """dict 源 → 数据集条件检索（index_dataset 'query'，索引落点用其缺省相对路径）
    → 首条匹配的 recordings 目录内最早 .sigmf-meta → SigMF 路径复用。

    检索失败（QueryError/索引损坏不可重建等）→ bad_iq；无匹配/无可用录制 → no_iq。
    """
    summary = "dataset-query:" + json.dumps(query, sort_keys=True, ensure_ascii=False, default=str)
    try:
        found = index_dataset("query", query=query)
        entries = found.get("entries", [])
    except Exception as exc:  # QueryError/IndexFormatError/IndexWriteError → bad_iq 不抛
        return _EMPTY_IQ, summary, _fail("bad_iq", f"数据集检索失败: {exc}", summary)
    for entry in entries:
        rec_dir = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(rec_dir, str) or not os.path.isdir(rec_dir):
            continue
        metas = sorted(f for f in os.listdir(rec_dir) if f.endswith(".sigmf-meta"))
        if metas:
            return _from_sigmf(os.path.join(rec_dir, metas[0]))
    return (
        _EMPTY_IQ,
        summary,
        _fail("no_iq", "数据集查询无可用录制（无匹配条目或 recordings 缺 .sigmf-meta）", summary),
    )


def _acquire_iq(iq_source: Any) -> tuple[np.ndarray, str, dict | None]:
    """IQ 取数：None→no_iq；str→SigMF；dict→数据集检索；ndarray/list/tuple→直用。

    返回 (complex128 一维数组, 来源摘要, 失败结果|None)；失败时数组为空占位。
    """
    if iq_source is None:
        return _EMPTY_IQ, "None", _fail("no_iq", "iq_source 为 None（无输入段）", "None")
    if isinstance(iq_source, str):
        return _from_sigmf(iq_source)
    if isinstance(iq_source, dict):
        return _from_dataset_query(iq_source)
    try:
        iq = _to_complex128(iq_source)
    except (TypeError, ValueError) as exc:
        summary = f"{type(iq_source).__name__}（长度未知）"
        return _EMPTY_IQ, summary, _fail("bad_iq", f"IQ 规整失败: {exc}", summary)
    summary = (
        f"ndarray:{iq_source.dtype}[{int(iq.size)}]"
        if isinstance(iq_source, np.ndarray)
        else f"{type(iq_source).__name__}[{int(iq.size)}]"
    )
    return iq, summary, None


def _gate_autocorr_peak(gate: np.ndarray) -> bool:
    """二值门控序列的周期性自相关检验（B14 中#3）：去均值后 FFT 线性自相关归一，
    lag∈[4, n//3] 内出现 >_PULSE_AC_PEAK 的峰 → 周期脉冲串（理想周期门控在重复
    周期 lag 处归一值≈1-P/n；噪声门控自相关随 lag 即衰减到 0 附近，量级~1/√n）。"""
    n = int(gate.size)
    if n < 12:
        return False
    series = gate.astype(np.float64) - float(gate.mean())
    ac0 = float((series * series).sum())
    if ac0 <= 0.0:  # 恒定门控（全开/全关）无周期结构可言
        return False
    max_lag = n // 3
    size = 1 << int(2 * n - 1).bit_length()  # ≥2n-1 的 2 幂 → 循环相关退化为线性
    spectrum = np.fft.rfft(series, size)
    ac = np.fft.irfft(spectrum * np.conj(spectrum), size)[: max_lag + 1]
    return bool((ac[4:] / ac0 > _PULSE_AC_PEAK).any())  # lag≥4 排除主瓣零邻域


def _classify_dummy(iq: np.ndarray, spec_res: dict) -> tuple[str, float, dict]:
    """dummy 规则分类器：谱质心/带宽特征 + 阈值匹配，在七类规范名上出标签+置信度。

    特征（相对量纲，不依赖 fs）：
    - centroid_hz：时间平均功率谱的质心，折合正频率轴（0=DC，1=Nyquist）位置；
    - bandwidth_3db：时间平均谱峰 -3dB 以上的 bin 占正频率轴份额（0–1）；
    - 辅助（不外发）：包络起伏 env_cv（tone 恒包络≈0 / 噪声 Rayleigh≈0.52 /
      脉冲门控≫1）、时域占空 duty_on/duty_off（B14 中#3 全段样本口径：包络二值
      化后 on 段占比/关断占比，非块内量化）、门控周期性 gate_periodic（二值包络
      自相关周期峰）、逐帧峰位轨迹 sweep_range/reversals（chirp/sweep 判据）、
      带内平坦度 ripple20。

    决策序（deterministic）：门控脉冲（duty∈[0.05,0.5] 且门控自相关周期峰）→
    扫频轨迹（确定性包络才认，噪声抖动排除）→ 窄带+恒包络=tone → 窄带噪声=
    partial_band → 宽带平坦=bandlimited_noise → 兜底 composite。阈值为经验值
    （nfft 归一量纲，随窗宽不敏感）。
    """
    spec = spec_res["spec"].astype(np.float64)
    freq_bins = int(spec.shape[0])
    axis = max(freq_bins - 1, 1)  # bin i 折合位置 i/(freq_bins-1)：末 bin=Nyquist=1.0

    prof = spec.mean(axis=1)  # 时间平均功率谱（dBFS）
    lin = 10.0 ** (prof / 10.0)
    total = float(lin.sum())
    centroid = (
        float((np.arange(freq_bins, dtype=np.float64) * lin).sum() / total) / axis
        if total > 0.0
        else 0.0
    )
    peak = float(prof.max())
    bw3db = float((prof >= peak - 3.0).sum()) / max(freq_bins, 1)
    occ20 = prof >= peak - 20.0
    ripple20 = float(prof[occ20].std()) if occ20.any() else 0.0

    env = np.abs(iq)
    mean_env = float(env.mean())
    env_cv = float(env.std() / mean_env) if mean_env > 0.0 else 0.0
    pwr = env * env

    # 脉冲门控（B14 中#3 全段口径重标定）：包络二值化（峰值 -20dB 以下为关断）→
    # 占空 duty_on 与关断占比 duty_off；门控规律以二值序列 FFT 自相关周期峰验证。
    peak_env = float(env.max()) if env.size else 0.0
    if peak_env > 0.0:
        gate = env > (peak_env / _GATE_FLOOR_RATIO)
        duty_on = float(gate.mean())
    else:
        gate = np.zeros_like(env, dtype=bool)
        duty_on = 0.0  # 全零段无门控可言（零能量退化另行标注）
    duty_off = 1.0 - duty_on
    duty_gated = (
        _PULSE_DUTY_MIN - _PULSE_DUTY_EPS
        <= duty_on
        <= _PULSE_DUTY_MAX + _PULSE_DUTY_EPS
    )
    gate_periodic = duty_gated and _gate_autocorr_peak(gate)

    peak_bins = np.argmax(spec, axis=0).astype(np.float64)  # 逐帧谱峰 bin
    sweep_range = float(peak_bins.max() - peak_bins.min()) / axis
    diffs = np.diff(peak_bins)
    moving = diffs[np.abs(diffs) > 0.5]  # 滤除亚 bin 抖动
    reversals = int((np.diff(np.sign(moving)) != 0).sum()) if moving.size >= 2 else 0

    if duty_gated and gate_periodic:  # 全段口径门控+占空带宽+周期性 → 脉冲
        label, confidence = "pulse", min(0.95, 0.5 + 0.45 * duty_off)
    elif env_cv < 0.35 and (sweep_range > 0.02 or reversals >= 4):  # 确定性扫频轨迹
        if reversals >= 3:
            label, confidence = "chirp", 0.75
        else:
            label, confidence = "sweep", 0.70
    elif bw3db <= 0.03 and env_cv < 0.15:  # 极窄带+恒包络 → 单音
        label, confidence = "tone", min(0.99, 0.90 + 0.09 * (1.0 - bw3db / 0.03))
    elif bw3db <= 0.06:  # 窄带非恒包络 → 受害带宽的部分频带占用
        label, confidence = "partial_band", 0.55
    elif ripple20 <= 6.0:  # 宽带+带内平坦 → 带限噪声
        label, confidence = "bandlimited_noise", min(0.95, 0.55 + 0.06 * (6.0 - ripple20))
    else:  # 非平坦宽带/多成分混合 → 合成样式兜底
        label, confidence = "composite", 0.40

    features = {"centroid_hz": centroid, "bandwidth_3db": min(bw3db, 1.0)}
    # 零能量退化（B14 低#4）：谱全平坦且总能量<1e-12（全零 IQ）→ conf 钳 0.1+
    # features 附 'degenerate': 'zero_energy'（不冒充高置信分类）。
    if (
        float(prof.max() - prof.min()) < _DEGENERATE_SPEC_SPAN
        and float(pwr.sum()) < _DEGENERATE_ENERGY
    ):
        confidence = min(confidence, 0.1)
        features["degenerate"] = "zero_energy"
    return label, float(min(max(confidence, 0.0), 1.0)), features


def _predict_one(
    iq_source: Any, loaded: dict | None, model_err: dict | None, nfft: int
) -> dict:
    """单源推理：模型①② → IQ 取数③ → 谱图④ → 分类⑤⑥（一切失败转 status 不抛）。"""
    if model_err is not None:  # ①② 模型缺失/不可读/缺 kind —— 最高优先级不阻塞
        return dict(model_err)
    kind = loaded["kind"]
    if kind not in _SUPPORTED_KINDS:
        if kind == "cnn":
            note = "模型 kind='cnn' 真网络前向归远期（not_implemented_yet）：本批仅实现 cnn_dummy"
        else:
            note = f"模型 kind={kind!r} 不受支持（本批实现: {list(_SUPPORTED_KINDS)}）"
        return {"status": "unsupported_model", "recognized": False, "note": note}

    iq, summary, iq_err = _acquire_iq(iq_source)  # ③ IQ 获取
    if iq_err is not None:
        return iq_err

    # ④ 谱图：先空段干跑——只过 nfft 域校验（非法 → ValueError 透传给调用方），
    # 真数据段的 ValueError（NaN/inf 脏 IQ、帧规模超上限）则转 bad_iq 不抛。
    make_spectrogram(_EMPTY_IQ, nfft=nfft)
    try:
        spec_res = make_spectrogram(iq, nfft=nfft)
    except ValueError as exc:
        return _fail("bad_iq", f"谱图计算失败: {exc}", summary)
    if int(spec_res["frames"]) == 0 or int(spec_res["skipped"]):
        return _fail(
            "short_iq",
            f"段长不足一个窗长（samples={int(iq.size)} < nfft={spec_res['params']['nfft']}）",
            summary,
        )

    # ⑤⑥ dummy 分类 + 结果行
    label, confidence, features = _classify_dummy(iq, spec_res)
    return {
        "status": "ok",
        "recognized": True,
        "label": label,
        "confidence": confidence,
        "model_version": _model_version(kind, loaded.get("weights")),
        "features": features,
        "iq_source": summary,
    }


def _is_batch(iq_source: Any) -> bool:
    """批量判定：list 且每个元素均为合法单源形态（str/None/ndarray/dict）。

    IQ 样本 list（元素为数值/复数/(I,Q) 二元组/嵌套 list）不满足该形态 → 单段
    直用；空 list 亦视为（空）单段；tuple 一律单段（与 SigMF 块样本天然形态兼容）。
    """
    if not isinstance(iq_source, list) or not iq_source:
        return False
    return all(
        item is None or isinstance(item, (str, np.ndarray, dict)) for item in iq_source
    )


def predict_style(iq_source, model=None, nfft: int = 256) -> dict | list[dict]:
    """识别推理入口（B14 顶层/R32）：IQ 段 → 样式标签+置信度+模型版本结果行。

    输入:
        iq_source: 单源三形态——SigMF meta 路径 str（复用 read_sigmf_timeline 解析，
            取首块 samples；文件错→bad_iq 不抛）| IQ ndarray/list（直用，(N,2) 实
            矩阵按 I/Q 两列）| None（→no_iq）。另支持数据集取数可选路径：检索条件
            dict（index_dataset 'query' 口径，索引落点为其缺省相对路径）→ 首条匹配
            recordings 目录内最早 .sigmf-meta。批量：list[上述单源]（元素须均为
            str/None/ndarray/dict 形态，否则该 list 按 IQ 样本直用）→ 逐源结果 list。
        model: None → {'status':'no_model','recognized':False,'note':'未识别（无模型）
            ——不阻塞主流程'}（R32 规约，不抛）；dict {'kind':'cnn_dummy'|'cnn',
            'labels':[...七类名], 'weights':...}；或模型 json 文件路径 str（读失败
            → no_model 同语义+note '模型文件不可读'）。本批实现 kind='cnn_dummy'
            规则分类器（谱质心/带宽特征与七类标签阈值匹配）；kind='cnn' 真网络
            归远期 → {'status':'unsupported_model'}（not_implemented_yet 如实返回）。
        nfft: make_spectrogram 窗长（参数化，缺省 256）。

    输出:
        单源 dict / 批量 list[dict]。成功行：{'status':'ok', 'recognized':True,
        'label': 七类名 str, 'confidence': 0–1 float, 'model_version':
        kind+'-'+sha256(weights)[:8]（无 weights → kind+'-dummy'）, 'features':
        {'centroid_hz': 质心（相对量纲，0=DC/1=Nyquist）, 'bandwidth_3db': -3dB
        带宽（正频率轴份额 0–1）}, 'iq_source': 来源摘要}——零能量退化段（谱全平坦
        且总能量<1e-12，如全零 IQ）confidence 钳 ≤0.1 且 features 追加
        'degenerate': 'zero_energy'（B14 低#4）。失败行：no_model/
        unsupported_model/no_iq/bad_iq/short_iq + recognized=False + note。

    错误:
        不抛（一切失败转 status 行）；唯一例外：nfft 非法 → ValueError 由
        make_spectrogram 透传（空段干跑先行触发，先于任何数据计算）。
    """
    if _is_batch(iq_source):
        loaded, model_err = _load_model(model)  # 批量：模型只载入一次共享
        return [_predict_one(item, loaded, model_err, nfft) for item in iq_source]
    loaded, model_err = _load_model(model)
    return _predict_one(iq_source, loaded, model_err, nfft)
