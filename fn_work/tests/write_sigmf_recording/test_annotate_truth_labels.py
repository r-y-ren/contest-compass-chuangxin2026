"""annotate_truth_labels 对抗测试：完整事实→SigMF v1.2 结构（global 六键/单捕获段/
annotations 数=档数）；两档各自 sample_start/count；window 缺→全 0 起+0 计数；
params 含 set/numpy 标量→str 化+jam:params_note；缺各必填键参数化拒附清单；
facts 非 dict 拒；ts→样本换算（1e6 采样率、1000ms 差→1e6 样本）；jam: 命名空间键
正确；json.dumps(default=str) 可序列化往返；run_id 透传；入参不被原地改动。"""
from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from src.write_sigmf_recording.annotate_truth_labels import annotate_truth_labels

#: 完整合法事实样本：窗口 [500, 4500] ms（4000ms→4e6 样本 @1e6），两档 ts 差
#: 500ms/2500ms→起点 5e5/2.5e6。
_FULL_FACTS = {
    "style": "pulsed",
    "params": {"duty": 0.3, "hop_hz": 1200},
    "power_steps": [
        {"step": 1, "target_db": -10.0, "ts": 1_000},
        {"step": 2, "target_db": -4.0, "ts": 3_000},
    ],
    "backend": "sim",
    "clock_ref": "internal",
    "freq_hz": 2_400_000_000.0,
    "sample_rate": 1_000_000.0,
    "run_id": "run-20261011-0001",
    "window": {"start_ts": 500, "end_ts": 4_500},
}

_ANNOTATION_KEYS = {
    "core:sample_start",
    "core:sample_count",
    "jam:style",
    "jam:power_db",
    "jam:params",
}


def test_full_facts_produces_canonical_sigmf_structure():
    """① 完整 facts→顶层三段；global 恰六键且逐键等值（三 core 标准+jam 三自定义）；
    captures 单段（0 起+中心频点+窗口起始 ts）；annotations 数=档数；干净 params 的
    标注恰五键（无 params_note）。"""
    meta = annotate_truth_labels(copy.deepcopy(_FULL_FACTS))
    assert set(meta) == {"global", "captures", "annotations"}
    assert meta["global"] == {
        "core:datatype": "cf32_le",
        "core:sample_rate": 1_000_000.0,
        "core:version": "1.2.0",
        "jam:backend": "sim",
        "jam:clock_ref": "internal",
        "jam:run_id": "run-20261011-0001",
    }
    assert len(meta["global"]) == 6
    assert meta["captures"] == [
        {
            "core:sample_start": 0,
            "core:frequency": 2_400_000_000.0,
            "jam:window_start_ts": 500,
        }
    ]
    assert len(meta["annotations"]) == len(_FULL_FACTS["power_steps"]) == 2
    for annotation in meta["annotations"]:
        assert set(annotation) == _ANNOTATION_KEYS
        assert annotation["jam:style"] == "pulsed"
        assert annotation["jam:params"] == {"duty": 0.3, "hop_hz": 1200}


def test_two_steps_each_annotation_own_bounds():
    """② 两档→两条标注按 power_steps 顺序，各自携带 sample_start/count：
    ts=1000→(1000-500)ms@1e6→5e5，ts=3000→2.5e6；计数同为窗 4000ms→4e6；
    jam:power_db 对应各档 target_db；起/计数均为 int。"""
    meta = annotate_truth_labels(copy.deepcopy(_FULL_FACTS))
    first, second = meta["annotations"]
    assert [a["core:sample_start"] for a in (first, second)] == [500_000, 2_500_000]
    assert first["core:sample_count"] == second["core:sample_count"] == 4_000_000
    assert [a["jam:power_db"] for a in (first, second)] == [-10.0, -4.0]
    assert isinstance(first["core:sample_start"], int)
    assert isinstance(first["core:sample_count"], int)


def test_window_missing_annotations_start_zero_count_zero():
    """③ window 缺（键不存在/显式 None/字段不全）→各标注全 0 起+0 计数，
    captures 的 jam:window_start_ts 落 None，global 六键不受影响。"""
    for dropped in ({"window": None}, {}):
        facts = copy.deepcopy(_FULL_FACTS)
        facts.pop("window")
        facts.update(dropped)
        meta = annotate_truth_labels(facts)
        assert len(meta["annotations"]) == 2
        for annotation in meta["annotations"]:
            assert annotation["core:sample_start"] == 0
            assert annotation["core:sample_count"] == 0
        assert meta["captures"][0]["jam:window_start_ts"] is None
        assert len(meta["global"]) == 6
    partial = copy.deepcopy(_FULL_FACTS)
    partial["window"] = {"start_ts": 500}  # 缺 end_ts：字段不全视同无窗
    meta = annotate_truth_labels(partial)
    assert meta["annotations"][0]["core:sample_count"] == 0


def test_unserializable_params_stringified_with_note():
    """④ params 含 set 与 numpy 标量→对应值 str() 化，其余原生保留，标注补
    'jam:params_note': 'stringified'；jam:params 与全局可再被 json.dumps 化。"""
    peak = np.float32(1.5)
    facts = copy.deepcopy(_FULL_FACTS)
    facts["params"] = {"tags": {"a", "b"}, "peak": peak, "plain": 7, "nest": [{"z": {1, 2}}]}
    meta = annotate_truth_labels(facts)
    annotation = meta["annotations"][0]
    assert annotation["jam:params_note"] == "stringified"
    params = annotation["jam:params"]
    assert isinstance(params["tags"], str) and "a" in params["tags"] and "b" in params["tags"]
    assert params["peak"] == str(peak)  # numpy 标量→str 化（不逃 TypeError）
    assert params["plain"] == 7  # 原生可序列化值不动
    assert isinstance(params["nest"][0]["z"], str)  # 嵌套层同口径
    assert "jam:params_note" not in annotate_truth_labels(copy.deepcopy(_FULL_FACTS))["annotations"][0]


@pytest.mark.parametrize(
    "missing_key", ["style", "backend", "freq_hz", "sample_rate", "run_id"]
)
def test_missing_each_required_key_raises_with_key_list(missing_key):
    """⑤ 缺各必填键（参数化）→ValueError 且消息附该键名；键在而值为 None 同判缺失。"""
    facts = copy.deepcopy(_FULL_FACTS)
    del facts[missing_key]
    with pytest.raises(ValueError) as ei:
        annotate_truth_labels(facts)
    assert missing_key in str(ei.value)
    facts[missing_key] = None  # 值 None 与缺键同口径
    with pytest.raises(ValueError) as ei_none:
        annotate_truth_labels(facts)
    assert missing_key in str(ei_none.value)


def test_multiple_missing_keys_all_listed():
    """⑥ 多键同缺→一张清单全列（backend/freq_hz/sample_rate 三名俱现）。"""
    facts = copy.deepcopy(_FULL_FACTS)
    for key in ("backend", "freq_hz", "sample_rate"):
        del facts[key]
    with pytest.raises(ValueError) as ei:
        annotate_truth_labels(facts)
    message = str(ei.value)
    assert all(key in message for key in ("backend", "freq_hz", "sample_rate"))


@pytest.mark.parametrize("bad_facts", [[("style", "x")], "facts", 42, None])
def test_non_dict_facts_rejected(bad_facts):
    """⑦ facts 非 dict（list/str/int/None）→ValueError，不逃 TypeError。"""
    with pytest.raises(ValueError):
        annotate_truth_labels(bad_facts)


def test_ts_to_sample_conversion_exact():
    """⑧ 换算正确性：sample_rate 1e6、ts 差 1000ms→sample_start 恰 1e6；半程
    500ms→5e5；窗 1000ms→count 1e6；ts 早于窗起点→截 0（SigMF 非负不变式）。"""
    facts = copy.deepcopy(_FULL_FACTS)
    facts["window"] = {"start_ts": 0, "end_ts": 1_000}
    facts["power_steps"] = [
        {"step": 1, "target_db": 0.0, "ts": 1_000},
        {"step": 2, "target_db": 3.0, "ts": 500},
    ]
    meta = annotate_truth_labels(facts)
    assert meta["annotations"][0]["core:sample_start"] == 1_000_000
    assert meta["annotations"][1]["core:sample_start"] == 500_000
    assert meta["annotations"][0]["core:sample_count"] == 1_000_000
    early = copy.deepcopy(facts)
    early["window"] = {"start_ts": 500, "end_ts": 1_000}  # ts 早于窗起点
    early["power_steps"] = [{"step": 1, "target_db": 0.0, "ts": 100}]
    assert annotate_truth_labels(early)["annotations"][0]["core:sample_start"] == 0


def test_jam_namespace_and_core_key_partition():
    """⑨ 命名空间键正确：global 恰三 core:+三 jam:；captures/annotations 自定义键
    全在 jam: 下，core 键全以 core: 起；params_note 也走 jam 命名空间。"""
    facts = copy.deepcopy(_FULL_FACTS)
    facts["params"] = {"tags": {"a"}}  # 触发 params_note
    meta = annotate_truth_labels(facts)
    global_keys = set(meta["global"])
    assert {k for k in global_keys if k.startswith("core:")} == {
        "core:datatype", "core:sample_rate", "core:version"
    }
    assert {k for k in global_keys if k.startswith("jam:")} == {
        "jam:backend", "jam:clock_ref", "jam:run_id"
    }
    custom_keys = set()
    core_keys = set()
    for section in (meta["captures"], meta["annotations"]):
        for record in section:
            for key in record:
                (custom_keys if key.startswith("jam:") else core_keys).add(key)
    assert core_keys <= {"core:sample_start", "core:sample_count", "core:frequency"}
    assert custom_keys == {
        "jam:window_start_ts", "jam:style", "jam:power_db", "jam:params", "jam:params_note"
    }
    assert not any(":" in k and not k.startswith(("core:", "jam:")) for k in global_keys)


def test_output_json_serializable_with_default_str():
    """⑩ 产物 json.dumps(default=str) 成功且 loads 往返保真（含 set/numpy 标量
    params 的降级形态与 None 时钟口径）。"""
    facts = copy.deepcopy(_FULL_FACTS)
    facts["params"] = {"tags": {"x"}, "peak": np.float32(2.5)}
    meta = annotate_truth_labels(facts)
    dumped = json.dumps(meta, default=str)  # 不抛即过
    assert json.loads(dumped)["global"]["jam:run_id"] == facts["run_id"]
    assert json.loads(dumped)["annotations"][0]["jam:params_note"] == "stringified"
    no_clock = copy.deepcopy(_FULL_FACTS)
    no_clock.pop("clock_ref")  # 可选缺省→None（null）仍可序列化
    json.dumps(annotate_truth_labels(no_clock), default=str)


def test_run_id_passthrough_verbatim():
    """⑪ run_id 原样透传到 global['jam:run_id']（含分隔符/Unicode/长串不改写）。"""
    weird = "run:2026-10-11T00:00:00Z/ uuid-ƒäke-0123456789abcdef"
    facts = copy.deepcopy(_FULL_FACTS)
    facts["run_id"] = weird
    assert annotate_truth_labels(facts)["global"]["jam:run_id"] == weird


def test_input_facts_not_mutated():
    """⑫ 入参 facts（含 params 中的 set/numpy 标量）不被原地 str 化或盖写。"""
    facts = copy.deepcopy(_FULL_FACTS)
    facts["params"] = {"tags": {"a", "b"}, "peak": np.float32(1.5), "deep": [{"z": 1}]}
    snapshot = copy.deepcopy(facts)
    annotate_truth_labels(facts)
    assert facts == snapshot
    assert isinstance(facts["params"]["tags"], set)
    assert facts["params"]["peak"] is snapshot["params"]["peak"]


def test_optional_defaults_keep_global_six_keys():
    """⑬ clock_ref/params/power_steps 全缺→global 仍六键（clock_ref=None），
    annotations=[]，captures 结构完整——可选事实缺省不抛错。"""
    facts = copy.deepcopy(_FULL_FACTS)
    for key in ("clock_ref", "params", "power_steps"):
        facts.pop(key)
    meta = annotate_truth_labels(facts)
    assert len(meta["global"]) == 6
    assert meta["global"]["jam:clock_ref"] is None
    assert meta["annotations"] == []
    assert meta["captures"][0]["core:frequency"] == facts["freq_hz"]


def test_malformed_power_steps_shape_rejected_as_valueerror():
    """⑭ power_steps 非 list/条目非 dict→ValueError（形状错误仍走 ValueError 家族，
    不逃 TypeError）。"""
    facts = copy.deepcopy(_FULL_FACTS)
    facts["power_steps"] = "not-a-list"
    with pytest.raises(ValueError):
        annotate_truth_labels(facts)
    facts["power_steps"] = [{"step": 1, "target_db": 0.0, "ts": 1_000}, "bogus"]
    with pytest.raises(ValueError):
        annotate_truth_labels(facts)


@pytest.mark.parametrize(
    "bad_rate",
    [0.0, -1_000_000.0, float("nan"), float("inf"), float("-inf"), "1e6", True],
)
def test_sample_rate_domain_rejected_with_value(bad_rate):
    """⑮ B12 中#3：sample_rate ≤0/NaN/±Inf/非数值（bool 不算）→ValueError 附值。"""
    facts = copy.deepcopy(_FULL_FACTS)
    facts["sample_rate"] = bad_rate
    with pytest.raises(ValueError) as ei:
        annotate_truth_labels(facts)
    assert "sample_rate" in str(ei.value)
    assert repr(bad_rate) in str(ei.value) or str(bad_rate) in str(ei.value)


@pytest.mark.parametrize("bad_freq", [-2_400_000_000.0, -0.1, float("nan"), "2.4e9"])
def test_negative_freq_hz_rejected_with_value(bad_freq):
    """⑯ B12 中#3：freq_hz 负值→ValueError 附值（载波非负——负频偏是频谱域
    参数不是载波）；NaN/非数值同拒。"""
    facts = copy.deepcopy(_FULL_FACTS)
    facts["freq_hz"] = bad_freq
    with pytest.raises(ValueError) as ei:
        annotate_truth_labels(facts)
    assert "freq_hz" in str(ei.value)


def test_zero_freq_hz_and_positive_sample_rate_legal():
    """⑰ 域下界合法：freq_hz=0（DC，非负即收）与正常正采样率→正常标注不抛。"""
    facts = copy.deepcopy(_FULL_FACTS)
    facts["freq_hz"] = 0.0
    meta = annotate_truth_labels(facts)
    assert meta["captures"][0]["core:frequency"] == 0.0
