"""predict_style 对抗测试（slug=infer_service）：识别推理入口——模型缺失不阻塞、
SigMF/直给/批量 IQ 取数、dummy 规则分类、结果行契约（B14 顶层/R32）。"""
from __future__ import annotations

import json
import re

import numpy as np
import pytest

from src.index_dataset.index_dataset import index_dataset
from src.predict_style.predict_style import predict_style
from src.synthesize_style.gen_pulse import gen_pulse

#: 七类样式标签域（六生成样式 + composite）——dummy 分类器的匹配名集
_LABELS = [
    "tone",
    "sweep",
    "chirp",
    "bandlimited_noise",
    "partial_band",
    "pulse",
    "composite",
]


def _dummy_model(weights=None):
    """本批实现的规则分类器模型（可携带 weights 参与 model_version 摘要）。"""
    model = {"kind": "cnn_dummy", "labels": list(_LABELS)}
    if weights is not None:
        model["weights"] = weights
    return model


def _tone_iq():
    """0.1fs 单音（质心特征主导：正频率轴折合位置 0.2）。"""
    return np.exp(1j * 2.0 * np.pi * 0.1 * np.arange(4096)).astype(np.complex64)


def _wide_noise_iq():
    """宽带噪声（带宽特征主导：占 Nyquist 200k/500k=0.4）。"""
    rng = np.random.default_rng(7)
    n = 8192
    white = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    spec = np.fft.fft(white)
    freqs = np.fft.fftfreq(n, d=1.0 / 1e6)
    return np.fft.ifft(spec * (np.abs(freqs) < 100e3)).astype(np.complex64)


def _pulse_iq(duty, repeat_hz=5e3, carrier_hz=0.1e6, n=8192, fs=1e6):
    """周期脉冲串 IQ：给定占空比/重复率（载波 0.1fs），gen_pulse 物理口径合成。"""
    iq, _meta = gen_pulse(
        duty / repeat_hz, repeat_hz, n, carrier_hz=carrier_hz, fs=fs
    )
    return iq


def _write_sigmf_pair(directory, iq, fs=1e6):
    """tmp 下写 cf32 单音 SigMF 对（meta+data），返回 meta 路径。"""
    stem = directory / "rec"
    np.asarray(iq, dtype=np.complex64).tofile(str(stem) + ".sigmf-data")
    meta = {
        "global": {
            "core:sample_rate": fs,
            "core:datatype": "cf32_le",
            "core:num_samples": int(np.asarray(iq).size),
        },
        "captures": [{"core:sample_start": 0}],
        "annotations": [],
    }
    (directory / "rec.sigmf-meta").write_text(
        json.dumps(meta), encoding="utf-8"
    )
    return str(directory / "rec.sigmf-meta")


def test_infer_service_no_model_unrecognized_not_blocking():
    """① 无模型 → no_model 结果行（R32 规约原文 note），不抛异常。"""
    result = predict_style(_tone_iq(), model=None)
    assert result["status"] == "no_model"
    assert result["recognized"] is False
    assert "不阻塞" in result["note"]


def test_infer_service_unreadable_model_path_no_model(tmp_path):
    """② 模型路径坏（文件缺失 / 根非 JSON 对象）→ no_model 语义 + note 含'模型文件不可读'。"""
    missing = predict_style(_tone_iq(), model="/nonexistent/model.json")
    assert missing["status"] == "no_model"
    assert missing["recognized"] is False
    assert "模型文件不可读" in missing["note"]

    not_object = tmp_path / "list_model.json"
    not_object.write_text("[1, 2, 3]", encoding="utf-8")
    listed = predict_style(_tone_iq(), model=str(not_object))
    assert listed["status"] == "no_model"
    assert "模型文件不可读" in listed["note"]


def test_infer_service_corrupt_model_file_no_model(tmp_path):
    """②b 模型文件存在但损坏（非法 JSON）→ no_model + note。"""
    bad = tmp_path / "bad_model.json"
    bad.write_text("{not json", encoding="utf-8")
    result = predict_style(_tone_iq(), model=str(bad))
    assert result["status"] == "no_model"
    assert result["recognized"] is False
    assert "模型文件不可读" in result["note"]


def test_infer_service_single_tone_label_tone():
    """③ 0.1fs 单音 IQ → label='tone'（质心特征主导，折合位置≈0.2）。"""
    result = predict_style(_tone_iq(), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["recognized"] is True
    assert result["label"] == "tone"
    assert abs(result["features"]["centroid_hz"] - 0.2) < 0.05


def test_infer_service_wideband_noise_label_bandlimited_noise():
    """④ 宽带噪声 IQ → label='bandlimited_noise'（带宽特征宽，>0.1 正频率轴）。"""
    result = predict_style(_wide_noise_iq(), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "bandlimited_noise"
    assert result["features"]["bandwidth_3db"] > 0.1


def test_infer_service_none_iq_status_no_iq():
    """⑤ iq_source=None（模型有效）→ no_iq，不抛。"""
    result = predict_style(None, model=_dummy_model())
    assert result["status"] == "no_iq"
    assert result["recognized"] is False


def test_infer_service_sigmf_path_recognizes_tone(tmp_path):
    """⑥ SigMF meta 路径（tmp cf32 单音对）→ ok+tone，iq_source 摘要带 sigmf 前缀。"""
    meta_path = _write_sigmf_pair(tmp_path, _tone_iq())
    result = predict_style(meta_path, model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    assert result["iq_source"].startswith("sigmf:")


def test_infer_service_cnn_kind_unsupported():
    """⑦ kind='cnn'（真网络归远期）→ unsupported_model，recognized=False，不抛。"""
    inline = predict_style(_tone_iq(), model={"kind": "cnn", "labels": list(_LABELS)})
    assert inline["status"] == "unsupported_model"
    assert inline["recognized"] is False
    assert "not_implemented_yet" in inline["note"]

    unknown = predict_style(_tone_iq(), model={"kind": "svm"})
    assert unknown["status"] == "unsupported_model"


def test_infer_service_batch_list_per_item_results():
    """⑧ 批量 list[单源] → 结果 list 且逐源独立（ok/no_iq/ok）。"""
    results = predict_style(
        [_tone_iq(), None, _wide_noise_iq()], model=_dummy_model()
    )
    assert isinstance(results, list)
    assert len(results) == 3
    assert results[0]["status"] == "ok" and results[0]["label"] == "tone"
    assert results[1]["status"] == "no_iq"
    assert results[2]["status"] == "ok" and results[2]["label"] == "bandlimited_noise"


def test_infer_service_confidence_within_unit_range():
    """⑨ confidence ∈ [0,1]（tone 与宽带噪声两路）。"""
    for iq in (_tone_iq(), _wide_noise_iq()):
        result = predict_style(iq, model=_dummy_model())
        assert 0.0 <= result["confidence"] <= 1.0


def test_infer_service_features_key_set_and_range():
    """⑩ features 键集恰 {centroid_hz, bandwidth_3db}，相对量纲均在 [0,1]。"""
    result = predict_style(_tone_iq(), model=_dummy_model())
    assert set(result["features"]) == {"centroid_hz", "bandwidth_3db"}
    for value in result["features"].values():
        assert isinstance(value, float)
        assert 0.0 <= value <= 1.0


def test_infer_service_model_version_format():
    """⑪ model_version：有 weights → kind-8 位十六进制摘要且同 weights 稳定；
    无 weights → 'cnn_dummy-dummy'。"""
    with_weights = predict_style(_tone_iq(), model=_dummy_model({"rule": "v1"}))
    assert re.fullmatch(r"cnn_dummy-[0-9a-f]{8}", with_weights["model_version"])
    again = predict_style(_tone_iq(), model=_dummy_model({"rule": "v1"}))
    assert again["model_version"] == with_weights["model_version"]
    changed = predict_style(_tone_iq(), model=_dummy_model({"rule": "v2"}))
    assert changed["model_version"] != with_weights["model_version"]

    bare = predict_style(_tone_iq(), model=_dummy_model())
    assert bare["model_version"] == "cnn_dummy-dummy"


def test_infer_service_invalid_nfft_value_error():
    """⑫ nfft 非法（0 / <8）→ ValueError 透传（make_spectrogram 域校验）。"""
    with pytest.raises(ValueError):
        predict_style(_tone_iq(), model=_dummy_model(), nfft=0)
    with pytest.raises(ValueError):
        predict_style(_tone_iq(), model=_dummy_model(), nfft=4)


def test_infer_service_broken_sigmf_bad_iq(tmp_path):
    """⑬ 坏 SigMF（meta 在 data 缺 / 路径不存在）→ bad_iq，recognized=False，不抛。"""
    meta_only = tmp_path / "half.sigmf-meta"
    meta_only.write_text(
        json.dumps(
            {
                "global": {
                    "core:sample_rate": 1e6,
                    "core:datatype": "cf32_le",
                    "core:num_samples": 16,
                },
                "captures": [{"core:sample_start": 0}],
                "annotations": [],
            }
        ),
        encoding="utf-8",
    )
    truncated = predict_style(str(meta_only), model=_dummy_model())
    assert truncated["status"] == "bad_iq"
    assert truncated["recognized"] is False

    missing = predict_style(str(tmp_path / "nope.sigmf-meta"), model=_dummy_model())
    assert missing["status"] == "bad_iq"
    assert missing["recognized"] is False


def test_infer_service_short_iq_status():
    """⑭ 段长不足一个窗长（16 < nfft=256）→ short_iq，不参与分类。"""
    result = predict_style(np.zeros(16, dtype=np.complex64), model=_dummy_model())
    assert result["status"] == "short_iq"
    assert result["recognized"] is False


def test_infer_service_list_iq_direct():
    """⑮ list 形态 IQ（complex 样本 list）直用 → 单段 ok（非批量路径）。"""
    result = predict_style(_tone_iq().tolist(), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    assert result["iq_source"].startswith("list[")


def test_infer_service_dataset_query_optional_path(tmp_path, monkeypatch):
    """⑯ 可选数据集取数路径：dict 检索条件 → 索引命中 recordings 内 SigMF → tone。

    chdir 到 tmp 使 index_dataset 缺省相对索引落点（fn_work/dataset/index.json）
    解析在 tmp 下，不触碰真实目录（与 index_dataset 测试同口径）。
    """
    runs_root = tmp_path / "fn_work" / "dataset" / "runs"
    rec_dir = runs_root / "20260101-000000" / "recordings"
    rec_dir.mkdir(parents=True)
    _write_sigmf_pair(rec_dir, _tone_iq())
    (runs_root / "20260101-000000" / "result.json").write_text(
        json.dumps(
            {
                "status": "done",
                "style": "tone",
                "freq_mhz": 100.0,
                "backend": "sim",
                "date": "20260101",
            }
        ),
        encoding="utf-8",
    )
    index_dataset(
        "rebuild",
        index_path=str(tmp_path / "fn_work" / "dataset" / "index.json"),
        runs_root=str(runs_root),
    )
    monkeypatch.chdir(tmp_path)

    result = predict_style({"style": "tone"}, model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    assert result["iq_source"].startswith("sigmf:")


# --- B14 中#3 脉冲盲区：门控判据全段口径重标定（短周期/中占空比不再漏检） ---


@pytest.mark.parametrize("duty", [0.05, 0.3, 0.5])
def test_infer_service_pulse_duty_band_three_points(duty):
    """5kHz 重复率下 duty 0.05/0.3/0.5 三点全命中 pulse——旧 128 块量化口径在
    周期 200 样本时块均值永不下探 20dB 阈值（duty 0.5 关断段 100<128 必漏检）。"""
    result = predict_style(_pulse_iq(duty), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["recognized"] is True
    assert result["label"] == "pulse"
    assert result["confidence"] > 0.5


def test_infer_service_pulse_short_period_20khz():
    """短周期 20kHz（50 样本/周期，远小于旧 128 块粒度）→ 仍判 pulse。"""
    result = predict_style(_pulse_iq(0.1, repeat_hz=20e3), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "pulse"


def test_infer_service_pulse_recap_sweep_params_20us_5khz_carrier():
    """重标定验收例（审查 sweep 口径）：20µs 脉宽/5kHz 重复/0.1MHz 载波（duty=0.1）→
    pulse；且配方注册表 pulse 默认参数（100µs/1kHz/无载波）不回归。"""
    iq, _meta = gen_pulse(20e-6, 5e3, 8192, carrier_hz=0.1e6, fs=1e6)
    result = predict_style(iq, model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "pulse"


def test_infer_service_pulse_default_recipe_params_not_regressed():
    """六类默认参数 sweep 中 pulse 行：RECIPES['pulse'] 默认（100µs/1kHz/fs=1e6）→ pulse。"""
    from src.switch_style.lookup_style_recipe import RECIPES

    iq, _meta = RECIPES["pulse"]["generator"](
        **dict(RECIPES["pulse"]["defaults"])
    )
    result = predict_style(iq, model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "pulse"


def test_infer_service_constant_envelope_tone_not_stolen_by_pulse_gate():
    """反例护栏：恒包络 tone 占空比≈1.0 落在脉冲窗外 → 仍判 tone（重标定不抢道）。"""
    result = predict_style(_tone_iq(), model=_dummy_model())
    assert result["label"] == "tone"


# --- B14 低#4 零能量退化：全零 IQ 不冒充高置信分类 ---


def test_infer_service_zero_energy_iq_degenerate_annotation():
    """全零 IQ（谱全平坦且总能量<1e-12）→ conf 钳 0.1+features 附
    'degenerate': 'zero_energy'（status 仍 ok、recognized 仍 True 不阻塞）。"""
    result = predict_style(np.zeros(4096, dtype=np.complex64), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["recognized"] is True
    assert result["confidence"] <= 0.1
    assert result["features"]["degenerate"] == "zero_energy"


def test_infer_service_tiny_but_nonzero_signal_not_flagged_degenerate():
    """微幅 tone（总能量 4096·(1e-8)²≈4e-13 <1e-12 但谱不平坦：峰仍高出底噪约 4dB）
    → 不附 degenerate 标注（平坦+零能量双条件缺一不可）。"""
    result = predict_style(
        1e-8 * _tone_iq(), model=_dummy_model()
    )
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    assert "degenerate" not in result["features"]


# --- B47 _signal_features 特征纯函数（R91）：合成 IQ 直测特征值 + 等价性锚 ---

from src.make_spectrogram.make_spectrogram import make_spectrogram  # noqa: E402
from src.predict_style.predict_style import _signal_features  # noqa: E402

#: 13 键特征契约（与后续 _rule_decision 共用——键名定死，不得增删改）
_FEATURE_KEYS = {
    "centroid",
    "bandwidth_3db",
    "ripple20",
    "env_cv",
    "duty_on",
    "duty_off",
    "duty_gated",
    "gate_periodic",
    "gate",
    "sweep_range",
    "reversals",
    "spec_span",
    "pwr_sum",
}


def _feats_of(iq, nfft=256):
    """合成 IQ → make_spectrogram 谱 + _signal_features 特征 dict（complex128 直测口径，
    与 predict_style 全流程的 _to_complex128 规整一致）。"""
    x = np.asarray(iq, dtype=np.complex128)
    return _signal_features(x, make_spectrogram(x, nfft=nfft)["spec"])


def _gated_tone_iq(duty=0.25, period=200, n=8192, freq=0.1):
    """numpy 直构周期门控 tone：每 period 样本开 round(duty·period) 个（载波 freq·fs）。"""
    idx = np.arange(n)
    on = (idx % period) < int(round(duty * period))
    return (np.exp(1j * 2.0 * np.pi * freq * idx) * on).astype(np.complex64)


def test_signal_features_tone_narrow_band_constant_envelope():
    """① 单音合成 IQ（0.1fs tone）→ bandwidth_3db 极窄（≤0.03）且 env_cv 低（<0.15）。"""
    feats = _feats_of(_tone_iq())
    assert feats["bandwidth_3db"] <= 0.03
    assert feats["env_cv"] < 0.15


def test_signal_features_wideband_noise_rayleigh_env_cv():
    """② 宽带噪声 → env_cv∈[0.3,0.8]（包络 Rayleigh≈0.52）且 bandwidth_3db 宽（>0.1）。"""
    feats = _feats_of(_wide_noise_iq())
    assert 0.3 <= feats["env_cv"] <= 0.8
    assert feats["bandwidth_3db"] > 0.1


def test_signal_features_gated_tone_duty_periodic_and_key_contract():
    """③ 周期门控 tone（占空≈0.25）→ duty_on≈0.25、duty_gated/gate_periodic 均 True；
    特征 dict 键集恰为 13 键契约。"""
    feats = _feats_of(_gated_tone_iq(duty=0.25))
    assert set(feats) == _FEATURE_KEYS
    assert feats["duty_on"] == pytest.approx(0.25, abs=0.01)
    assert feats["duty_gated"] is True
    assert feats["gate_periodic"] is True


def test_signal_features_constant_envelope_full_duty_not_gated():
    """④ 连续恒包络 tone → duty_on≈1.0、duty_gated/gate_periodic 均 False（窗外）。"""
    feats = _feats_of(_tone_iq())
    assert feats["duty_on"] == pytest.approx(1.0, abs=1e-9)
    assert feats["duty_off"] == pytest.approx(0.0, abs=1e-9)
    assert feats["duty_gated"] is False
    assert feats["gate_periodic"] is False


def test_signal_features_gate_array_consistent_with_duty_on():
    """⑤ gate 数组与 duty_on 自洽：bool ndarray、shape 随 IQ、gate.mean()==duty_on（1e-9）。"""
    iq = _gated_tone_iq(duty=0.25)
    feats = _feats_of(iq)
    gate = feats["gate"]
    assert isinstance(gate, np.ndarray) and gate.dtype == np.bool_
    assert gate.shape == np.asarray(iq).shape
    assert float(gate.mean()) == pytest.approx(feats["duty_on"], abs=1e-9)


def test_signal_features_pulse_equivalence_anchor_full_pipeline():
    """⑥ 等价性核心锚：③的合成脉冲 IQ 经现 _classify_dummy 全流程（predict_style +
    裸 cnn_dummy 模型）仍判 pulse——特征计算段提出后口径未漂移的端到端证明。"""
    result = predict_style(_gated_tone_iq(duty=0.25), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "pulse"


# --- B47 _extract_gate_segments 门控 on 段提取（R91）：end_exclusive 口径+边界+联动锚 ---

from src.predict_style.predict_style import _extract_gate_segments  # noqa: E402


def test_extract_gate_segments_typical_multi_segments():
    """① 典型多段 [1,1,0,1,0,0,1,1,1] → [(0,2),(3,4),(6,9)]（end_exclusive 口径）。"""
    gate = np.array([1, 1, 0, 1, 0, 0, 1, 1, 1], dtype=bool)
    assert _extract_gate_segments(gate) == [(0, 2), (3, 4), (6, 9)]


def test_extract_gate_segments_all_on_single_segment():
    """② 全开 → 单段 [(0, n)]。"""
    assert _extract_gate_segments(np.ones(7, dtype=bool)) == [(0, 7)]


def test_extract_gate_segments_all_off_empty_table():
    """③ 全关 → 空表。"""
    assert _extract_gate_segments(np.zeros(10, dtype=bool)) == []


def test_extract_gate_segments_empty_input_empty_table():
    """④ 空数组 → 空表。"""
    assert _extract_gate_segments(np.zeros(0, dtype=bool)) == []


def test_extract_gate_segments_single_sample():
    """⑤ 单样本：True → [(0,1)]；False → []。"""
    assert _extract_gate_segments(np.array([True])) == [(0, 1)]
    assert _extract_gate_segments(np.array([False])) == []


def test_extract_gate_segments_leading_off_trailing_on_not_swallowed():
    """⑥ 首尾边界：首 False 尾 True 段不吞——[0,1,1,0,1] → [(1,3),(4,5)]。"""
    gate = np.array([0, 1, 1, 0, 1], dtype=bool)
    assert _extract_gate_segments(gate) == [(1, 3), (4, 5)]


def test_extract_gate_segments_anchor_with_signal_features_gate():
    """⑦ 联动锚：周期门控 tone 合成 IQ，feats=_signal_features(...) 的 feats['gate']
    提段——段数≥3、各段长>0、段序按出现顺序递增、段长和==gate.sum()（自洽）。"""
    period, duty = 200, 0.25
    feats = _feats_of(_gated_tone_iq(duty=duty, period=period))
    gate = feats["gate"]
    segs = _extract_gate_segments(gate)
    assert len(segs) >= 3
    assert all(end > start for start, end in segs)  # 各段长>0
    starts = [start for start, _end in segs]
    assert starts == sorted(starts)  # 段序确定=按出现顺序
    assert sum(end - start for start, end in segs) == int(gate.sum())  # 无样本丢失


def test_extract_gate_segments_lenient_input_forms():
    """⑧ 宽进防御（不承诺项的现行为快照）：list 输入与 0/1 数值数组与 bool ndarray
    同结果。"""
    expected = [(0, 2), (3, 4)]
    assert _extract_gate_segments([True, True, False, True]) == expected
    assert _extract_gate_segments(np.array([1, 1, 0, 1])) == expected


# --- B47 _rule_decision 六规则决策序纯函数（R91）：规则直测+段内语义锚+等价锚 ---

from src.predict_style.predict_style import _rule_decision  # noqa: E402


def _rule_feats(**overrides):
    """13 键特征 dict 直构（键契约齐全；缺省态=六规则全不命中的 composite 底态），
    各规则用例覆写判据键——决策函数只取不自算，直接喂决策序。"""
    feats = {
        "centroid": 0.5,
        "bandwidth_3db": 0.5,
        "ripple20": 8.0,
        "env_cv": 0.6,
        "duty_on": 1.0,
        "duty_off": 0.0,
        "duty_gated": False,
        "gate_periodic": False,
        "gate": np.ones(16, dtype=bool),
        "sweep_range": 0.0,
        "reversals": 0,
        "spec_span": 40.0,
        "pwr_sum": 100.0,
    }
    feats.update(overrides)
    return feats


def test_rule_decision_gated_pulse_first_priority():
    """① 门控脉冲（首序）：duty_on=0.25（duty_off=0.75）/gated/periodic → pulse，
    conf=0.5+0.45*0.75=0.8375 精确断言——扫频判据键同时似然仍不抢道（首序优先）。"""
    feats = _rule_feats(
        duty_on=0.25,
        duty_off=0.75,
        duty_gated=True,
        gate_periodic=True,
        env_cv=0.1,
        sweep_range=0.3,
        reversals=5,
    )
    label, confidence = _rule_decision(feats)
    assert label == "pulse"
    assert confidence == pytest.approx(0.8375, abs=1e-12)


def test_rule_decision_chirp_many_reversals():
    """② chirp：env_cv=0.1/sweep_range=0.3/reversals=5（≥3）→ ('chirp', 0.75)。"""
    assert _rule_decision(_rule_feats(env_cv=0.1, sweep_range=0.3, reversals=5)) == (
        "chirp",
        0.75,
    )


def test_rule_decision_sweep_monotonic_track():
    """③ sweep：sweep_range>0.02 但 reversals<3（2 与 0 两点）→ ('sweep', 0.70)。"""
    assert _rule_decision(_rule_feats(env_cv=0.1, sweep_range=0.3, reversals=2)) == (
        "sweep",
        0.70,
    )
    assert _rule_decision(_rule_feats(env_cv=0.1, sweep_range=0.05, reversals=0)) == (
        "sweep",
        0.70,
    )


def test_rule_decision_tone_narrow_band_constant_envelope():
    """④ tone：bw3db=0.01/env_cv=0.1 → ('tone', 0.90+0.09*(1-0.01/0.03)=0.96)。"""
    label, confidence = _rule_decision(_rule_feats(bandwidth_3db=0.01, env_cv=0.1))
    assert label == "tone"
    assert confidence == pytest.approx(0.96, abs=1e-9)


def test_rule_decision_partial_band_moderate_bandwidth():
    """⑤ partial_band：bw3db=0.05（0.03<·≤0.06）且 env_cv=0.6 →
    ('partial_band', 0.55)。"""
    assert _rule_decision(_rule_feats(bandwidth_3db=0.05, env_cv=0.6)) == (
        "partial_band",
        0.55,
    )


def test_rule_decision_bandlimited_noise_flat_ripple():
    """⑥ bandlimited_noise：bw3db=0.5/ripple20=3.0 → ('bandlimited_noise',
    0.55+0.06*(6.0-3.0)=0.73)。"""
    label, confidence = _rule_decision(
        _rule_feats(bandwidth_3db=0.5, ripple20=3.0, env_cv=0.6)
    )
    assert label == "bandlimited_noise"
    assert confidence == pytest.approx(0.73, abs=1e-9)


def test_rule_decision_composite_uneven_wideband_fallback():
    """⑦ composite 兜底：宽带非平坦（ripple20=8.0>6.0）→ ('composite', 0.40)。"""
    assert _rule_decision(_rule_feats(ripple20=8.0)) == ("composite", 0.40)


def test_rule_decision_intra_segment_gate_also_pulse():
    """⑧ 段内两层门控语义锚：段内特征（duty_on=0.3/gated/periodic）→ 同判 pulse
    （conf=0.5+0.45*0.7=0.815）——判据本身不区分全段/段内。"""
    label, confidence = _rule_decision(
        _rule_feats(duty_on=0.3, duty_off=0.7, duty_gated=True, gate_periodic=True)
    )
    assert label == "pulse"
    assert confidence == pytest.approx(0.815, abs=1e-12)


def test_rule_decision_equivalence_anchor_against_full_pipeline():
    """⑨ 等价锚（决策链提取零漂移证明）：周期门控 tone 合成 IQ，_signal_features →
    _rule_decision 的 (label, conf) 与现 _classify_dummy 全流程 predict_style 同输入
    的 (label, confidence) 完全相等。"""
    iq = _gated_tone_iq(duty=0.25)
    feats = _feats_of(iq)
    label, confidence = _rule_decision(feats)
    result = predict_style(iq, model=_dummy_model())
    assert result["status"] == "ok"
    assert label == "pulse"
    assert result["label"] == label
    assert result["confidence"] == confidence


# --- B47 _template_classify 模板路分类组装（R92）：合成模板直测+锚域+透传锚+等价锚 ---

from src.predict_style.predict_style import _template_classify  # noqa: E402
from src.shared.spectral_template_match import spectral_template_match  # noqa: E402


def _template_weights(n=32):
    """两类合成模板模型 weights（{class_mean_spectra: {label: 模板向量}}）：
    tone 单峰=[10,0,...,0]、bandlimited_noise 平铺=[1]*n/√n 量级。"""
    tone = np.zeros(n)
    tone[0] = 10.0
    noise = np.full(n, 1.0 / np.sqrt(n))
    return {"class_mean_spectra": {"tone": tone, "bandlimited_noise": noise}}


def test_template_classify_template_hit_tone():
    """① 模板命中：待测 profile 近 tone 模板（+0.01 均匀扰动）→ label='tone'
    且 conf>0.5（softmax over negative distances 近邻模板主导）。"""
    weights = _template_weights()
    profile = weights["class_mean_spectra"]["tone"] + 0.01
    label, confidence, _extras = _template_classify(profile, weights, list(_LABELS))
    assert label == "tone"
    assert confidence > 0.5


def test_template_classify_labels_anchor_restricts_to_seven():
    """② labels 锚域透传：锚外模板键（mystery_style 单峰 bin1，与待测 profile
    零距离=若入域必胜）不参与匹配——结果 label 仍限七类名内。"""
    weights = _template_weights()
    mystery = np.zeros(32)
    mystery[1] = 10.0
    weights["class_mean_spectra"]["mystery_style"] = mystery
    label, _confidence, _extras = _template_classify(mystery, weights, list(_LABELS))
    assert label != "mystery_style"
    assert label in _LABELS


def test_template_classify_extras_uncalibrated_note_and_template_path():
    """③ 第三项 dict 两键齐：confidence_note 含'未校准'、template_path is True。"""
    weights = _template_weights()
    _label, _confidence, extras = _template_classify(
        weights["class_mean_spectra"]["tone"], weights, list(_LABELS)
    )
    assert set(extras) == {"confidence_note", "template_path"}
    assert "未校准" in extras["confidence_note"]
    assert extras["template_path"] is True


def test_template_classify_dimension_mismatch_value_error_passthrough():
    """④ 底层形状异常透传锚：profile 维度与模板不一致（33 vs 32）→
    spectral_template_match 的 ValueError 原样透传（不吞不改）。"""
    weights = _template_weights()
    with pytest.raises(ValueError, match="维度不一致"):
        _template_classify(np.zeros(33), weights, list(_LABELS))


def test_template_classify_equivalence_anchor_with_shared_matcher():
    """⑤ 值等价锚：同输入下 (label, conf) 与直接调 spectral_template_match 完全
    相等（组装层纯转发+特征键追加，零口径漂移）。"""
    rng = np.random.default_rng(11)
    weights = _template_weights()
    for _ in range(5):
        profile = rng.uniform(0.0, 10.0, 32)
        label, confidence, _extras = _template_classify(
            profile, weights, list(_LABELS)
        )
        direct = spectral_template_match(
            profile, weights["class_mean_spectra"], list(_LABELS)
        )
        assert (label, confidence) == direct


# --- B47 _classify_dummy 门控感知两级分类（R91）：阶梯录音识别+两级门控+防退化锚 ---


def _ladder_tone_iq(on=770, off=1390, segments=4, freq=0.1):
    """阶梯录音型门控 tone（R91 核心输入）：segments 段连续 tone（各 on 样本，
    相位沿全局样本序）+ 段间 off 样本零底噪间隙——占空比 on/(on+off)（缺省
    770/2160≈0.356，落脉冲占空窗：旧实现全段规则一恒判 pulse）。缺省周期
    2160 使 0.1fs 载波每间隙恰整数周期（216）——段拼接（段间直连）后相位连续，
    段内谱形纯净不冒充扫频轨迹。不复用 _gated_tone_iq（那是短周期门控，on 段
    <nfft 恒走短段兜底路）。"""
    idx = np.arange(segments * (on + off))
    on_mask = (idx % (on + off)) < on
    return (np.exp(1j * 2.0 * np.pi * freq * idx) * on_mask).astype(np.complex64)


def _ladder_noise_iq(on=770, off=1390, segments=4, band=0.1, seed=7):
    """阶梯录音型门控带限噪声：同 ladder 口径但段内为 |f|<band 带限白噪声；
    包络钳 0.5×均值（Rayleigh 深衰落会打穿门控阈值 -20dB，把 on 段切碎——
    钳衰落保段完整，段内仍是噪声包络起伏）。"""
    rng = np.random.default_rng(seed)
    total = segments * (on + off)
    white = rng.standard_normal(total) + 1j * rng.standard_normal(total)
    freqs = np.fft.fftfreq(total)
    noise = np.fft.ifft(np.fft.fft(white) * (np.abs(freqs) < band))
    env = np.abs(noise)
    floored = np.maximum(env, 0.5 * env.mean())
    idx = np.arange(total)
    on_mask = (idx % (on + off)) < on
    return (noise * (floored / env) * on_mask).astype(np.complex64)


def _ladder_nested_pulse_iq(on=1024, off=1024, segments=2, freq=0.1,
                            inner_on=50, inner_period=200):
    """两层门控：外层阶梯驻留（on/off 段）×段内短周期门控 tone（脉内 inner_on
    样本、周期 inner_period）——两层相乘的通断包络（R88 平台录音×注入 pulse
    两层嵌套的最小复刻）。"""
    idx = np.arange(segments * (on + off))
    outer = (idx % (on + off)) < on
    inner = (idx % inner_period) < inner_on
    return (np.exp(1j * 2.0 * np.pi * freq * idx) * outer * inner).astype(
        np.complex64
    )


def test_classify_dummy_ladder_tone_recognized_as_tone():
    """① 阶梯录音型门控 tone（4 段×770 样本、占空≈0.356 落脉冲窗+驻留周期峰
    ——R91 现状断点复刻，旧实现全段规则一判 pulse@0.79）→ 门控感知两级改造后
    段内分类识别 tone；features 扩 gated/on_ratio/on_segments 三键、无
    confidence_note（规则路）。"""
    result = predict_style(_ladder_tone_iq(), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["recognized"] is True
    assert result["label"] == "tone"
    feats = result["features"]
    assert feats["gated"] is True
    assert "on_ratio" in feats
    assert "on_segments" in feats
    assert "confidence_note" not in feats


def test_classify_dummy_ladder_bandlimited_noise_segment_path():
    """② 同型阶梯录音但段内为带限噪声 → 段内分类 label='bandlimited_noise'
    （旧实现全段规则一判 pulse）；外发 centroid/bandwidth 为段内值（宽带）。"""
    result = predict_style(_ladder_noise_iq(), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "bandlimited_noise"
    feats = result["features"]
    assert feats["gated"] is True
    assert feats["bandwidth_3db"] > 0.06  # 段内宽带（非全段门控混叠谱）


def test_classify_dummy_two_layer_gating_still_pulse():
    """③ 两层门控：外层阶梯×段内短周期门控 tone（脉内 50 样本周期 200，on 段
    <nfft）→ label='pulse'（门控路如实披露；短 on 段不可谱分析，维持全段
    规则一判定）。"""
    result = predict_style(_ladder_nested_pulse_iq(), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "pulse"
    feats = result["features"]
    assert feats["gated"] is True
    assert feats["on_segments"] == 0  # 脉内 50 样本段全部 <nfft 不入段表


def test_classify_dummy_continuous_tone_no_gated_keys_regression():
    """④ 连续 tone 回归锚：连续 IQ（duty_on=1.0 ≥0.9 连续判据）→ tone 且
    features 键集恰 {centroid_hz, bandwidth_3db}（连续路零扩键——门控感知
    不污染连续合成信号，与既有键集合断言口径互为镜像）。"""
    result = predict_style(_tone_iq(), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    assert set(result["features"]) == {"centroid_hz", "bandwidth_3db"}


def test_classify_dummy_short_pulse_train_still_pulse_with_gated_keys():
    """⑤ 短脉冲串回归锚：周期门控 tone（on 段 50 样本 <nfft）→ 仍判 pulse
    （短段维持规则一，防退化边界）且 features 含门控三键（如实披露看到了
    门控）。"""
    result = predict_style(_gated_tone_iq(duty=0.25), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "pulse"
    feats = result["features"]
    assert feats["gated"] is True
    assert feats["on_segments"] == 0
    assert feats["on_ratio"] == pytest.approx(0.25, abs=0.01)


def test_classify_dummy_on_ratio_and_segment_count_values():
    """⑥ 门控披露数值锚：①输入 → on_ratio≈0.35±0.05、on_segments==构造段数 4
    （段长 770≥nfft 全入段表）。"""
    result = predict_style(_ladder_tone_iq(), model=_dummy_model())
    feats = result["features"]
    assert isinstance(feats["on_ratio"], float)
    assert feats["on_ratio"] == pytest.approx(0.35, abs=0.05)
    assert feats["on_segments"] == 4


def test_classify_dummy_nested_pulse_fragment_accumulation_still_pulse():
    """⑦ 负例锚（段内判据=最长单段而非拼接累计）：长驻留×脉内碎片两档几何——
    (a) 脉内 50/周期 200（碎片≪窗，段表空，累计口径也不达）；(b) 脉内 300/周期
    800（碎片≥nfft 但<3×nfft：40 片累计 12000≥3×nfft——旧累计判据下拼接谱=
    整数周期相位连续的连续载波，实证误判 tone@0.94）——两档均断言 pulse：最长
    单段（50/300）<3×nfft 自然回全段规则一兜底（相乘包络 duty 入窗+周期峰），
    长驻留×多脉冲不误判。"""
    for inner_on, inner_period, expect_segs in ((50, 200, 0), (300, 800, 40)):
        iq = _ladder_nested_pulse_iq(
            on=8000, off=4000, segments=4,
            inner_on=inner_on, inner_period=inner_period,
        )
        result = predict_style(iq, model=_dummy_model())
        assert result["status"] == "ok"
        assert result["label"] == "pulse", (inner_on, inner_period)
        feats = result["features"]
        assert feats["gated"] is True
        # (a) 碎片<nfft 不入段表；(b) 碎片≥nfft 入段表（如实计数）但判据取
        # 最长单段（300<768）——段表非空也正确兜底。
        assert feats["on_segments"] == expect_segs, (inner_on, inner_period)


# --- B47 _predict_one 模板路分流（R92）：模板命中/门控 scope/形状回退/规则路回归/两层门控兜底 ---

#: 模板路用例小 nfft：谱向量 nfft//2+1=33 维，模板构造更简洁（①②⑤）
_TEMPLATE_NFFT = 64
_TEMPLATE_NBINS = _TEMPLATE_NFFT // 2 + 1


def _template_model(templates):
    """含模板的 cnn_dummy 模型：weights.class_mean_spectra={label: 模板向量}
    （模板路分流形态——与规则路裸 _dummy_model 互为镜像）。"""
    return {
        "kind": "cnn_dummy",
        "labels": list(_LABELS),
        "weights": {"class_mean_spectra": templates},
    }


def _seven_class_templates(n_bins, pulse=None, flat_db=-90.0):
    """七类模板库缺省形：tone=单峰向量（bin6≈0.1fs 折合峰 0dB、裙底 -60dB——
    nfft=64 时 tone 时间平均谱为 hann 裙形，裙底均值实测≈-64dB），其余类平铺
    flat_db；pulse 可传入覆写（⑤ 用平铺+单峰近似脉冲串全段谱形）。"""
    templates = {label: np.full(n_bins, flat_db) for label in _LABELS}
    tone = np.full(n_bins, -60.0)
    tone[6] = 0.0
    templates["tone"] = tone
    if pulse is not None:
        templates["pulse"] = pulse
    return templates


def test_predict_one_template_path_tone_hit_with_seven_templates():
    """① 模板路命中：连续 tone IQ+七类模板库（tone 单峰、其余平铺）→ label='tone'、
    features 含 confidence_note/template_path（模板路标识，键集恰四键）、
    model_version 带 weights sha256 指纹（有模板自然非 dummy）。"""
    result = predict_style(
        _tone_iq(),
        model=_template_model(_seven_class_templates(_TEMPLATE_NBINS)),
        nfft=_TEMPLATE_NFFT,
    )
    assert result["status"] == "ok"
    assert result["recognized"] is True
    assert result["label"] == "tone"
    assert result["confidence"] > 0.5
    feats = result["features"]
    assert set(feats) == {
        "centroid_hz",
        "bandwidth_3db",
        "confidence_note",
        "template_path",
    }
    assert feats["template_path"] is True
    assert "未校准" in feats["confidence_note"]
    assert re.fullmatch(r"cnn_dummy-[0-9a-f]{8}", result["model_version"])


def test_predict_one_template_path_gated_ladder_tone_scope_switch():
    """② 门控录音模板路：阶梯 tone 录音型 IQ（占空≈0.356 落脉冲窗，规则路曾被
    劫持判 pulse）+tone 模板 → 模板路门控感知生效：scope=段长≥nfft 长段拼接谱、
    label='tone'、features 含 gated/on_ratio/on_segments 三键+template_path
    （门控披露与规则路同口径）。"""
    result = predict_style(
        _ladder_tone_iq(),
        model=_template_model(_seven_class_templates(_TEMPLATE_NBINS)),
        nfft=_TEMPLATE_NFFT,
    )
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    feats = result["features"]
    assert feats["template_path"] is True
    assert feats["gated"] is True
    assert feats["on_segments"] == 4  # 四段 770 样本全 ≥nfft 入段表
    assert feats["on_ratio"] == pytest.approx(0.356, abs=0.05)


def test_predict_one_template_dimension_mismatch_falls_back_to_rule_path():
    """③ 形状回退：模板维度与谱不一致（128 维模板 vs 缺省 nfft=256 谱 129 维）→
    回退规则路：label 与规则路判定一致（阶梯构造→tone）、features 附回退标注
    note、无 template_path 键（R92 口径：不新增错误类型）。"""
    mismatched = _template_model(_seven_class_templates(256 // 2))
    ladder = _ladder_tone_iq()
    result = predict_style(ladder, model=mismatched)  # 缺省 nfft=256 → 谱 129 维
    rule = predict_style(ladder, model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    assert result["label"] == rule["label"]  # 回退=规则路判定一致
    assert "模板路形状异常回退规则路" in result["features"]["note"]
    assert "维度不一致" in result["features"]["note"]
    assert "template_path" not in result["features"]


def test_predict_one_bare_model_rule_path_regression_no_template_keys():
    """④ 无 weights 模型走规则路回归锚：裸 cnn_dummy → 结果与改造前一致（连续
    tone→tone、model_version 'cnn_dummy-dummy'、features 无模板路键——分流
    不污染规则路）。"""
    result = predict_style(_tone_iq(), model=_dummy_model())
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    assert result["model_version"] == "cnn_dummy-dummy"
    assert "template_path" not in result["features"]
    assert "confidence_note" not in result["features"]


def test_predict_one_two_layer_gating_template_scope_full_segment_not_tone():
    """⑤ 两层门控模板路：阶梯×短脉冲 IQ（脉内碎片 50<nfft，最长单段判据不切换
    scope）+七类模板库（pulse 模板=平铺+单峰近似脉冲串全段谱形）→ 兜底 scope=
    全段模板匹配：label∈七类且不误判 tone（碎片拼接谱=连续载波的误判路径封
    死）；无门控扩键（gated 三键只在 scope 实际切换时披露——如实口径）。"""
    pulse_template = np.full(_TEMPLATE_NBINS, -114.0)
    pulse_template[6] = -109.0  # 全段谱实测：基座≈-114dB+bin6 单峰≈-110dB
    model = _template_model(
        _seven_class_templates(_TEMPLATE_NBINS, pulse=pulse_template)
    )
    result = predict_style(
        _ladder_nested_pulse_iq(), model=model, nfft=_TEMPLATE_NFFT
    )
    assert result["status"] == "ok"
    assert result["label"] in _LABELS
    assert result["label"] != "tone"
    assert result["features"]["template_path"] is True
    assert "gated" not in result["features"]


def test_predict_one_train_classifier_product_model_template_path():
    """⑥ train_classifier(local) 产物形态模型（顶层 class_mean_spectra、无
    weights 键）经 _load_model 规整进 weights → 模板路：label='tone'、features
    含 template_path、model_version 带指纹（非 '-dummy'——模型内容变指纹就该
    变；train_meta 顶层键不入 weights 不入哈希——有无 train_meta 指纹不变）。"""
    product = {
        "kind": "cnn_dummy",
        "labels": list(_LABELS),
        "class_mean_spectra": _seven_class_templates(_TEMPLATE_NBINS),
        "train_meta": {"n_samples": 12, "nfft": _TEMPLATE_NFFT, "per_class": {}},
    }
    result = predict_style(_tone_iq(), model=product, nfft=_TEMPLATE_NFFT)
    assert result["status"] == "ok"
    assert result["label"] == "tone"
    assert result["features"]["template_path"] is True
    assert re.fullmatch(r"cnn_dummy-[0-9a-f]{8}", result["model_version"])
    assert result["model_version"] != "cnn_dummy-dummy"
    no_meta = predict_style(
        _tone_iq(),
        model={k: v for k, v in product.items() if k != "train_meta"},
        nfft=_TEMPLATE_NFFT,
    )
    assert no_meta["model_version"] == result["model_version"]  # train_meta 不入哈希
