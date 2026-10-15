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
