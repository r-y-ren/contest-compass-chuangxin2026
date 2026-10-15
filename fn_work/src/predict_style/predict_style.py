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
from src.shared.spectral_template_match import spectral_template_match

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
#: 门控感知两级分类连续判据（R91）：duty_on ≥ 此值视为无显著通断（连续录音），
#: 全段决策直出——连续合成信号零漂移。底噪尾巴实测 duty_on 58.5–77.5%，故含
#: 真实通断结构的阶梯驻留录音（duty_on≈0.23–0.42）恒入门控路。
_GATED_CONTINUOUS_MIN = 0.9
#: 段内谱分析所需最少窗数（R91）：最长单段 ≥ _ON_SEGMENT_KFFT×nfft 才做段内
#: 分类——判据取最长单段而非拼接累计：两层门控（阶梯×pulse）下 on 段=脉内碎片，
#: 碎片累计可超 3×nfft 而拼接谱=连续载波会误判 tone；最长单段短于此（真脉冲串/
#: 脉内碎片/短驻留段）维持全段规则一判定不重判。
_ON_SEGMENT_KFFT = 3
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

    规范 dict：{'kind': str, 'labels': list[str]（七类缺省兜底）, 'weights': 原样，
    但 weights 非 dict 而 raw 顶层 'class_mean_spectra' 为非空 dict
    （train_classifier(local) 产物形态）时顶层模板保留进 weights——train_meta
    等其余顶层键不入 weights 不入哈希}。
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
    # weights 规整（B47 伴生修复）：weights 缺/非 dict 而 raw 顶层
    # 'class_mean_spectra' 为非空 dict（train_classifier(local) 产物形态——顶层
    # 模板原被丢弃致模板路不可达）→ 顶层模板保留进 weights（model_version 哈希
    # 自然带指纹）；train_meta 等其余顶层键不入 weights 不入哈希（训练元数据
    # 不影响识别行为）。内联 dict 与 json 文件两路径同规整（return 前一处）。
    weights = raw.get("weights")
    if not isinstance(weights, dict):
        top_templates = raw.get("class_mean_spectra")
        if isinstance(top_templates, dict) and top_templates:
            weights = {"class_mean_spectra": top_templates}
    return (
        {
            "kind": kind,
            "labels": _normalize_labels(raw.get("labels")),
            "weights": weights,
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
    """规则路分类编排（R91 门控感知两级）：全段特征→通断分流→全段/段内决策。

    纯编排——特征计算（_signal_features）、on 段提取（_extract_gate_segments）、
    决策序（_rule_decision）、段内谱（make_spectrogram）全部调用已落地三叶与共用
    谱图，本函数不自算特征。决策序：

    ① feats = _signal_features(iq, 全段谱) → 分流判据 duty_on：
    - duty_on ≥ _GATED_CONTINUOUS_MIN（0.9，无显著通断——连续录音/合成信号）→
      _rule_decision(feats) 全段决策直出，外发 centroid_hz/bandwidth_3db 取全段
      值——与门控感知改造前行为完全一致（连续合成信号零漂移）；
    - duty_on < 0.9（显著通断结构，如平台阶梯驻留录音：占空入脉冲窗+驻留周期峰
      曾劫持规则一恒判 pulse）→ 门控感知两级：_extract_gate_segments(feats["gate"])
      取段长 ≥ nfft（spec_res["params"]["nfft"]）的 on 段（段间直连——无底噪
      间隙故段内包络连续）——
      · 最长单段 ≥ _ON_SEGMENT_KFFT×nfft（3 窗，段可谱分析；判据取最长单段
        而非拼接累计——两层门控（阶梯×pulse）下全段 gate 的 on 段=脉内碎片，
        碎片累计可超 3×nfft 而拼接谱=连续载波会误判 tone，最长单段判据下碎片
        场景自然回兜底）→ 段长 ≥nfft 的长段集拼接 iq_on 做段内
        make_spectrogram(iq_on)+_signal_features+_rule_decision 出标签与置信度，
        外发 centroid_hz/bandwidth_3db 取段内值（样式信息在 on 段谱形——这是
        R91 的核心修正：阶梯 tone 录音不再被劫持为 pulse）；
      · 最长单段 < 3×nfft（真脉冲串/脉内碎片/短驻留段）→ 维持全段规则一判定
        （duty_gated&gate_periodic→pulse 置信公式不变，短脉冲不重判）。两层
        门控的 pulse 即由此兜底承载：拼接谱无脉间结构，段内再判 pulse 在拼接
        口径下不可达（iq_on 样本包络恒 > 全段阈值 ≥ 段内阈值 ⟹ 段内 gate 恒
        全开、duty_on≡1.0）——如实描述。
      门控路 features 恒扩三键：gated=True / on_ratio=全段 duty_on / on_segments=
      段长 ≥nfft 的段数——如实披露看到了门控。

    ② 零能量退化钳（B14 低#4 口径不变）：全段 spec_span 与 pwr_sum 双低 →
    confidence 钳 ≤0.1 + features['degenerate']='zero_energy'；confidence 终钳
    [0,1]。nfft 已上游干跑校验（段内 make_spectrogram 无 ValueError 路径），
    段内 frames==0 理论不达（最长单段 ≥3×nfft ⟹ 拼接样本 ≥3×nfft ⟹ ≥5 帧），
    仍按短段兜底不重判。
    """
    feats = _signal_features(iq, spec_res["spec"].astype(np.float64))
    label, confidence = _rule_decision(feats)
    features = {
        "centroid_hz": feats["centroid"],
        "bandwidth_3db": min(feats["bandwidth_3db"], 1.0),
    }

    if feats["duty_on"] < _GATED_CONTINUOUS_MIN:  # 显著通断 → 门控感知两级
        nfft = int(spec_res["params"]["nfft"])
        segments = [
            (start, end)
            for start, end in _extract_gate_segments(feats["gate"])
            if end - start >= nfft
        ]
        features["gated"] = True
        features["on_ratio"] = float(feats["duty_on"])
        features["on_segments"] = len(segments)
        # 段内判据=最长单段（非拼接累计）：碎片累计可超 3×nfft 但拼接谱=连续
        # 载波会误判 tone——最长单段不足（碎片/短脉冲/短驻留）自然回规则一兜底。
        longest = max((end - start for start, end in segments), default=0)
        if longest >= _ON_SEGMENT_KFFT * nfft:  # 最长单段可谱分析 → 段内分类
            iq_on = iq[np.r_[tuple(slice(start, end) for start, end in segments)]]
            spec_on = make_spectrogram(iq_on, nfft=nfft)
            if int(spec_on["frames"]) > 0:  # 理论不达（≥3×nfft ⟹ ≥5 帧）兜底
                feats_on = _signal_features(
                    iq_on, spec_on["spec"].astype(np.float64)
                )
                label, confidence = _rule_decision(feats_on)
                features["centroid_hz"] = feats_on["centroid"]
                features["bandwidth_3db"] = min(feats_on["bandwidth_3db"], 1.0)

    # 零能量退化（B14 低#4）：谱全平坦且总能量<1e-12（全零 IQ）→ conf 钳 0.1+
    # features 附 'degenerate': 'zero_energy'（不冒充高置信分类）。
    if (
        feats["spec_span"] < _DEGENERATE_SPEC_SPAN
        and feats["pwr_sum"] < _DEGENERATE_ENERGY
    ):
        confidence = min(confidence, 0.1)
        features["degenerate"] = "zero_energy"
    return label, float(min(max(confidence, 0.0), 1.0)), features


def _predict_one(
    iq_source: Any, loaded: dict | None, model_err: dict | None, nfft: int
) -> dict:
    """单源推理：模型①② → IQ 取数③ → 谱图④ → 分类⑤⑥ 分流（一切失败转 status 不抛）。

    ⑤⑥ 分类分流（R92）：模型 weights 含非空 dict 'class_mean_spectra' → 模板路
    ——门控感知骨架与 _classify_dummy 规则路同型（docstring 互指）：全段
    _signal_features → duty_on < _GATED_CONTINUOUS_MIN 时 _extract_gate_segments
    取段长 ≥nfft 的 on 段、最长单段 ≥ _ON_SEGMENT_KFFT×nfft 才拼接长段重算
    make_spectrogram 为 scope（否则全段兜底不切换），scope 谱的 dB 时间平均谱
    profile（与 class_mean_spectra 训练口径一致）→ _template_classify（经
    shared/spectral_template_match）出标签与置信度；features = centroid_hz/
    bandwidth_3db（scope 特征，外发口径与规则路一致）+ confidence_note/
    template_path，门控切换时另扩 gated/on_ratio/on_segments 三键；零能量退化钳
    同规则路。模板形状非法（维度不一致等 ValueError）→ 回退规则路 _classify_dummy
    且 features 附 'note': '模板路形状异常回退规则路: …'（不新增错误类型）；
    weights 为非空 dict 但 class_mean_spectra 不合规（缺键/非 dict/空 dict）
    → 同口径回退规则路+note '模板路缺合规 class_mean_spectra，回退规则路'
    （B47 双审 I-2：原静默走规则路，现如实标注）。裸模型（weights 缺/None/
    非 dict/空 dict——无模板承诺）→ 规则路 _classify_dummy 无 note（现状不变）。
    model_version 恒 kind-sha256(weights)（有模板自然带指纹）；结果行结构不变。
    """
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

    # ⑤⑥ 分类分流（R92）+ 结果行：weights 含非空 dict 'class_mean_spectra' →
    # 模板路（门控感知骨架与 _classify_dummy 规则路同型）；weights 为非空 dict
    # 但 class_mean_spectra 不合规（缺键/非 dict/空 dict——B47 双审 I-2：原静默
    # 走规则路，现归回退路径带 note，与 ValueError 回退同口径）；裸模型
    # （weights 缺/None/非 dict/空 dict——无模板承诺）规则路无 note 现状不变。
    weights = loaded.get("weights")
    templates = weights.get("class_mean_spectra") if isinstance(weights, dict) else None
    if isinstance(templates, dict) and templates:
        spec = spec_res["spec"].astype(np.float64)
        nfft_seg = int(spec_res["params"]["nfft"])
        feats = _signal_features(iq, spec)
        iq_scope, spec_scope, gated = iq, spec, False
        segments = []
        if feats["duty_on"] < _GATED_CONTINUOUS_MIN:  # 显著通断 → 门控感知
            segments = [
                (start, end)
                for start, end in _extract_gate_segments(feats["gate"])
                if end - start >= nfft_seg
            ]
            # 段内判据=最长单段（非拼接累计），与规则路同口径：两层门控的脉内
            # 碎片累计可超 3×nfft 而拼接谱=连续载波会误判 tone——最长单段不足则
            # 维持全段 scope 兜底（模板匹配脉冲串全段谱形）。
            longest = max((end - start for start, end in segments), default=0)
            if longest >= _ON_SEGMENT_KFFT * nfft_seg:  # 最长单段可谱分析
                iq_on = iq[np.r_[tuple(slice(start, end) for start, end in segments)]]
                spec_on = make_spectrogram(iq_on, nfft=nfft_seg)
                if int(spec_on["frames"]) > 0:  # 理论不达（≥3×nfft ⟹ ≥5 帧）兜底
                    spec_scope = spec_on["spec"].astype(np.float64)
                    gated = True
        feats_scope = _signal_features(iq_scope, spec_scope)  # scope 特征
        profile = spec_scope.mean(axis=1)  # dB 时间平均谱（训练口径一致）
        try:
            label, confidence, extras = _template_classify(
                profile, weights, loaded["labels"]
            )
        except ValueError as exc:
            # 形状非法（维度不一致等）→ 回退规则路+note（R92 口径：不新增错误类型）
            label, confidence, features = _classify_dummy(iq, spec_res)
            features["note"] = f"模板路形状异常回退规则路: {exc}"
        else:
            features = {
                "centroid_hz": feats_scope["centroid"],
                "bandwidth_3db": min(feats_scope["bandwidth_3db"], 1.0),
                **extras,
            }
            if gated:  # 门控披露三键（on_ratio/on_segments 与规则路同口径）
                features["gated"] = True
                features["on_ratio"] = float(feats["duty_on"])
                features["on_segments"] = len(segments)
            # 零能量退化钳（同规则路：scope 谱全平坦+总能量双低不冒充高置信）。
            if (
                feats_scope["spec_span"] < _DEGENERATE_SPEC_SPAN
                and feats_scope["pwr_sum"] < _DEGENERATE_ENERGY
            ):
                confidence = min(confidence, 0.1)
                features["degenerate"] = "zero_energy"
            confidence = float(min(max(confidence, 0.0), 1.0))
    elif isinstance(weights, dict) and weights:
        # B47 双审 I-2：非空 dict weights 但 class_mean_spectra 不合规（缺键/
        # 非 dict/空 dict）→ 回退规则路+note（原静默走规则路，现如实标注——
        # 与上方 ValueError 回退同口径）。
        label, confidence, features = _classify_dummy(iq, spec_res)
        features["note"] = "模板路缺合规 class_mean_spectra，回退规则路"
    else:
        label, confidence, features = _classify_dummy(iq, spec_res)  # 规则路（现状不变）
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
    """识别推理入口（B14 顶层/R32；B47 R91 门控感知/R92 模板路）：IQ 段 →
    样式标签+置信度+模型版本结果行。

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
            双路分类（R92 分流）：weights 含非空 dict 'class_mean_spectra'
            （train_classifier(local) 产物的顶层 class_mean_spectra 形态经
            _load_model 规整入 weights 同达）→ 模板路；否则规则路（谱质心/带宽
            特征与七类标签阈值匹配）。kind='cnn' 真网络归远期 →
            {'status':'unsupported_model'}（not_implemented_yet 如实返回）。
        nfft: make_spectrogram 窗长（参数化，缺省 256）。

    输出:
        单源 dict / 批量 list[dict]。成功行：{'status':'ok', 'recognized':True,
        'label': 七类名 str, 'confidence': 0–1 float, 'model_version':
        kind+'-'+sha256(weights)[:8]（无 weights → kind+'-dummy'）, 'features':
        dict（键集随分类路扩键，见下）, 'iq_source': 来源摘要}。失败行：no_model/
        unsupported_model/no_iq/bad_iq/short_iq + recognized=False + note。

        features 基础两键恒在：'centroid_hz'（谱质心，相对量纲 0=DC/1=Nyquist）/
        'bandwidth_3db'（-3dB 带宽，正频率轴份额 0–1）；按分类路扩键——

        · 规则路（模型无模板；R91 门控感知两级防劫持/防退化）：全段占空
          duty_on ≥0.9（无显著通断——连续合成信号）→ 全段规则决策直出，
          features 恰基础两键（连续路零扩键）；duty_on <0.9（显著通断，如平台
          阶梯驻留录音）→ 提取段长 ≥nfft 的 on 段、最长单段 ≥3×nfft 才拼接
          长段做段内谱重判（防驻留录音被门控占空+驻留周期峰劫持恒判 pulse——
          样式信息在 on 段谱形，外发 centroid/bandwidth 取段内值）；最长单段
          不足（真脉冲串/脉内碎片/两层门控阶梯×pulse）→ 维持全段规则一判定
          不重判（防退化：短 on 段不可谱分析不冒充连续载波，两层门控的
          pulse 由该兜底如实承载）。门控路（无论段内重判与否）features 恒扩
          三键：'gated': True / 'on_ratio': 全段占空 / 'on_segments': 段长
          ≥nfft 的段数——如实披露看到了门控。
        · 模板路（R92；模型含非空 class_mean_spectra）：门控感知骨架与规则路
          同型（scope=全段谱或长 on 段拼接谱，切换判据同为最长单段 ≥3×nfft），
          scope 的 dB 时间平均谱（与 class_mean_spectra 训练口径一致）→
          spectral_template_match 最近质心出标签；confidence 为 softmax over
          negative distances 的**未校准**分数（校准需独立校准集，留远期）——
          features 扩 'confidence_note'（未校准标注）与 'template_path': True
          两键；门控三键（gated/on_ratio/on_segments）两路口径**有意不同**——
          模板路仅 scope 实际切换（gated）时扩三键，规则路 duty_on<0.9 恒扩
          三键（模板路 note 键承载回退信息）；模板形状非法（维度不一致等
          ValueError）→ 回退规则路判定且 features 附 'note':
          '模板路形状异常回退规则路: …'（不新增错误类型）；weights 为非空
          dict 但 class_mean_spectra 不合规（缺键/非 dict/空 dict）→ 同口径
          回退规则路+note '模板路缺合规 class_mean_spectra，回退规则路'
          （B47 双审 I-2）。
        · 零能量退化段（谱全平坦且总能量<1e-12，如全零 IQ，双路同钳）：
          confidence 钳 ≤0.1 且 features 追加 'degenerate': 'zero_energy'
          （B14 低#4，不冒充高置信分类）。

    错误:
        不抛（一切失败转 status 行）；唯一例外：nfft 非法 → ValueError 由
        make_spectrogram 透传（空段干跑先行触发，先于任何数据计算）。
    """
    if _is_batch(iq_source):
        loaded, model_err = _load_model(model)  # 批量：模型只载入一次共享
        return [_predict_one(item, loaded, model_err, nfft) for item in iq_source]
    loaded, model_err = _load_model(model)
    return _predict_one(iq_source, loaded, model_err, nfft)


# ── 演进轮④（R91/R92）新叶——重写规约与签名意图详见 fn_docs/responsibility.md
#    域二十三功能块；宿主 _classify_dummy/_predict_one 改造体已落地（B47）。


def _signal_features(iq: np.ndarray, spec: np.ndarray) -> dict:
    """特征计算纯函数（R91；现 _classify_dummy 前半计算段 :249–292 原样提出，全段/
    段内两处同源复用——提取不重写，改造接线归后续 _classify_dummy 改造步）：IQ+谱
    → 13 键特征 dict（键名与 _rule_decision 共用契约，不得增删改）。

    键：'centroid'（0–1 折合质心）/'bandwidth_3db'（-3dB bin 份额 0–1）/'ripple20'/
    'env_cv'/'duty_on'/'duty_off'/'duty_gated'/'gate_periodic'/'gate'（bool ndarray，
    供 on 段提取）/'sweep_range'/'reversals'（int）/'spec_span'（prof.max−prof.min，
    零能量退化判据用）/'pwr_sum'（包络平方和）。spec 为 dB 谱矩阵（行=频率 bin）。

    错误：空输入由上游 short_iq 先拒（_predict_one ④——frames==0 即返回不进
    本层）；本层空数组 ValueError（zero-size reduction——空谱 prof.max() 抛）
    ——主链不可达，如实注明（本层对空输入形态不承诺，直测须自担）。
    """
    spec = spec.astype(np.float64)
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

    spec_span = float(prof.max() - prof.min())
    pwr_sum = float(pwr.sum())
    return {
        "centroid": centroid,
        "bandwidth_3db": bw3db,
        "ripple20": ripple20,
        "env_cv": env_cv,
        "duty_on": duty_on,
        "duty_off": duty_off,
        "duty_gated": duty_gated,
        "gate_periodic": gate_periodic,
        "gate": gate,
        "sweep_range": sweep_range,
        "reversals": reversals,
        "spec_span": spec_span,
        "pwr_sum": pwr_sum,
    }


def _extract_gate_segments(gate: np.ndarray) -> list[tuple[int, int]]:
    """二值门控序列 → 连通 on 段表 [(start, end_exclusive), ...]（R91；空输入→空表，
    段序确定=按出现顺序）。规则路（_classify_dummy）与模板路（_predict_one）门控
    感知共用。

    向量化口径：前后各补一个 False 后差分（布尔异或）找沿——flatnonzero 出的沿
    位置天然上升/下降交替，两两成对即 (start, end_exclusive)。输入宽进防御
    （上游 _signal_features 恒给一维 bool，非 bool/非一维不承诺）：list 转
    ndarray、非 bool 数组按真值性（!=0）转、多维摊平。
    """
    arr = np.asarray(gate)
    if arr.dtype != np.bool_:  # 宽进：非 bool 数值数组按真值性转
        arr = arr != 0
    arr = arr.reshape(-1)  # 上游恒一维；多维防御性摊平
    padded = np.concatenate((np.zeros(1, dtype=bool), arr, np.zeros(1, dtype=bool)))
    edges = np.flatnonzero(padded[1:] != padded[:-1])  # 上升/下降沿交替位置
    return [(int(edges[i]), int(edges[i + 1])) for i in range(0, edges.size, 2)]


def _rule_decision(feats: dict) -> tuple[str, float]:
    """六规则决策序纯函数（R91；现 _classify_dummy 后半 if-elif 链 :294–308 原样
    提出，判据与置信度公式逐句不变）：门控脉冲→扫频轨迹（chirp/sweep）→tone→
    partial_band→bandlimited_noise→composite 兜底。段内特征命中门控脉冲=两层
    门控判 pulse（判据本身不区分全段/段内，天然语义）。

    键契约（与 _signal_features 13 键一致，只从 feats 取键不自算）：'centroid'/
    'bandwidth_3db'/'ripple20'/'env_cv'/'duty_on'/'duty_off'/'duty_gated'/
    'gate_periodic'/'gate'/'sweep_range'/'reversals'/'spec_span'/'pwr_sum'——本
    函数消费其中八键（duty_off/duty_gated/gate_periodic/env_cv/sweep_range/
    reversals/bandwidth_3db/ripple20）；缺键 → KeyError 自然抛（层内契约输入，
    防御不承诺）。零能量退化钳不在本层（B14 低#4 口径留 _classify_dummy 编排层）。
    """
    duty_off = feats["duty_off"]
    duty_gated = feats["duty_gated"]
    gate_periodic = feats["gate_periodic"]
    env_cv = feats["env_cv"]
    sweep_range = feats["sweep_range"]
    reversals = feats["reversals"]
    bw3db = feats["bandwidth_3db"]
    ripple20 = feats["ripple20"]

    if duty_gated and gate_periodic:  # 门控+占空带宽+周期性 → 脉冲（全段/段内同判据）
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
    return label, float(confidence)


def _template_classify(
    profile: np.ndarray, weights: dict, labels: list[str]
) -> tuple[str, float, dict]:
    """模板路分类组装（R92）：待测时间平均谱向量（全段或 on 段，与
    class_mean_spectra 训练口径一致）→ shared/spectral_template_match 出
    (label, confidence)；未校准标注与模板路特征键随第三项 dict 返回（口径见
    requirements R92）。形状非法不在本层拒（交 _predict_one 回退规则路）。

    - profile：dB 时间平均谱一维向量（调用方算好谱并均值化——本函数不重新算谱；
      与模板向量维度一致性由 spectral_template_match 校验，ValueError 原样透传）；
    - weights：模型 dict，取 weights['class_mean_spectra']（{label: 模板向量}，
      键存在性由调用方 _predict_one 分流保证——缺键 KeyError 自然抛，层内契约）；
    - labels：七类名序列锚（透传 spectral_template_match 的 labels 参数，结果
      label 限该域）；
    - 第三项 dict 恒两键：'confidence_note'（未校准标注）与 'template_path':
      True（模板路标识——规则路结果无此键）。
    """
    # 约束：labels 锚域/模板维度/非数值校验全由 spectral_template_match 承载，
    # ValueError 不吞不改地透传（回退编排是 _predict_one 改造步职责）。
    label, confidence = spectral_template_match(
        profile, weights["class_mean_spectra"], labels
    )
    return label, confidence, {
        # 约束：置信度为 softmax over negative distances 未校准分数——校准需
        # 独立校准集，留远期。
        "confidence_note": (
            "未校准分数（softmax over negative distances；校准需独立校准集，留远期）"
        ),
        "template_path": True,
    }
