"""运行事实→SigMF v1.2 元数据标注段——重写规约与签名意图详见 fn_docs/responsibility.md。

把一次运行的真值事实（样式/参数/功率档序列/时间窗/后端/时钟口径/运行号）编成
SigMF v1.2 结构 dict：global 恒六键（core:datatype/core:sample_rate/core:version
三标准键 + jam:backend/jam:clock_ref/jam:run_id 三自定义命名空间键，jam 命名空间
=本项目）、captures 单捕获段（0 起样本+中心频点+窗口起始 ts）、annotations 每功率
档一条（档起样本由档 ts 相对窗口起点按采样率换算，窗样本数为计数）。真值标注是
训练/核对的 ground truth：facts 非 dict 或缺必填键（style/backend/freq_hz/
sample_rate/run_id，含键在而值为 None）一律显式 ValueError 附缺键清单，绝不静默
造"未知"标注；sample_rate 域校验（≤0 / NaN / ±Inf / 非数值 → ValueError 附值）
与 freq_hz 域校验（负值 → ValueError：载波频率非负——负频偏是频谱域参数不是
载波；非数值/NaN 同拒）在缺键检查后实施；可选事实（clock_ref/params/power_steps/
window）缺省时按空/无窗口径降级（标注 0 起+0 计数），不抛错。params 含不可
json 化对象（set/numpy 标量/自定义类等）逐值 str() 化并在标注上补
'jam:params_note': 'stringified'。
"""
from __future__ import annotations

import math

__all__ = ["annotate_truth_labels"]

#: SigMF 核心命名空间与本项目自定义命名空间前缀。
_CORE_NS = "core"
_JAM_NS = "jam"

#: 固定产出的 SigMF 版本与 IQ 数据类型（cf32_le=复 float32、小端）。
_SIGMF_VERSION = "1.2.0"
_DATATYPE = "cf32_le"

#: facts 必填键：缺失（键不存在或值为 None）→ValueError 附缺键清单。
_REQUIRED_KEYS = ("style", "backend", "freq_hz", "sample_rate", "run_id")

#: params 深序列化发生 str() 化时标注在 'jam:params_note' 上的记号。
_STRINGIFIED_NOTE = "stringified"


def _is_number(value) -> bool:
    """ts/时间戳换算入参的可算性：int/float（bool 是 int 子类但语义非时间数值，拒）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _stringify_params(params):
    """递归把 params 重建为可直接 json.dumps 的结构，不改动入参。

    None/bool/int/float/str 标量原样保留（bool 为 int 子类天然覆盖）；dict/list/tuple
    逐层拷贝（tuple→数组口径）；其余复杂对象（set、numpy 标量、自定义类等不可直接
    json 化的值，以及 tuple 等非法 JSON 键）一律 str() 化。返回 (新结构, 是否发生过
    str() 化)；发生过→调用方在该标注上补 'jam:params_note': 'stringified'，提醒
    消费者 params 是字符串化降级而非原生结构。
    """
    stringified = False

    def convert(value):
        nonlocal stringified
        if isinstance(value, dict):
            out = {}
            for key, sub in value.items():
                if not isinstance(key, (str, int, float, bool)) and key is not None:
                    key = str(key)  # tuple 等非法 JSON 键 str 化（json 本身也强制字符串化键）
                    stringified = True
                out[key] = convert(sub)
            return out
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        if value is None or isinstance(value, (str, int, float)):
            return value
        stringified = True
        return str(value)

    return convert(params), stringified


def _ms_to_samples(delta_ms, sample_rate) -> int:
    """毫秒时长→样本数：四舍五入取整、负值截 0（SigMF 起点与计数均为非负整数）。"""
    if not _is_number(delta_ms):
        return 0
    return max(0, int(round(delta_ms * sample_rate / 1000.0)))


def _validate_domain(facts: dict) -> tuple[float, float]:
    """freq_hz / sample_rate 域校验（B12 中#3），返回 (freq_hz, sample_rate)。

    - sample_rate：须为有限正数值——≤0 / NaN / ±Inf / 非数值（bool 不算）→
      ValueError 附值（采样率≤0 使 ts→样本换算无意义/除零，NaN 会污染每条
      标注的起点与计数）；
    - freq_hz：须为有限非负数值——负值 ValueError 附值（载波频率非负：负频偏
      是频谱域参数不是载波中心频点），NaN/±Inf/非数值同拒。
    """
    sample_rate = facts["sample_rate"]
    if not _is_number(sample_rate) or not math.isfinite(sample_rate):
        raise ValueError(
            f"facts['sample_rate'] 非法（须为有限正数值：≤0/NaN/±Inf/非数值均拒），"
            f"实际为 {sample_rate!r}"
        )
    if sample_rate <= 0:
        raise ValueError(
            f"facts['sample_rate'] 非法（须为有限正数值：≤0/NaN/±Inf/非数值均拒），"
            f"实际为 {sample_rate!r}"
        )
    freq_hz = facts["freq_hz"]
    if not _is_number(freq_hz) or not math.isfinite(freq_hz) or freq_hz < 0:
        raise ValueError(
            f"facts['freq_hz'] 非法（须为有限非负数值：负值=负频偏是频谱域参数"
            f"不是载波；NaN/±Inf/非数值均拒），实际为 {freq_hz!r}"
        )
    return freq_hz, sample_rate


def annotate_truth_labels(facts: dict) -> dict:
    """运行事实→SigMF 元数据标注段。

    输入 facts: {'style': str, 'params': dict, 'power_steps': [{'step','target_db',
    'ts', ...}], 'backend': str, 'clock_ref': str, 'freq_hz': float, 'sample_rate':
    float, 'run_id': str, 'window': {'start_ts', 'end_ts'}|None}（ts 毫秒口径）。
    输出: SigMF v1.2 结构 dict（global 六键/captures 单段/annotations 每功率档一条）。
    错误: facts 非 dict、必填键缺失、sample_rate 域非法（≤0/NaN/±Inf/非数值）、
    freq_hz 负值（NaN/±Inf/非数值同拒）、power_steps 形状非法→ValueError（附
    缺键/值/原因，不抛其他类型）；可选事实缺省按空/无窗口径降级，不抛错。
    """
    if not isinstance(facts, dict):
        raise ValueError(f"facts 必须为 dict，实际为 {type(facts).__name__}")

    missing = [key for key in _REQUIRED_KEYS if facts.get(key) is None]
    if missing:
        raise ValueError(f"facts 缺少必填键: {missing}")

    style = facts["style"]
    backend = facts["backend"]
    # 域校验（B12 中#3）：sample_rate 有限正数值 / freq_hz 有限非负——非法即
    # ValueError 附值，先于任何标注构建。
    freq_hz, sample_rate = _validate_domain(facts)
    run_id = facts["run_id"]
    clock_ref = facts.get("clock_ref")  # 可选事实：缺省 None（JSON null 口径）

    window = facts.get("window")
    if not (
        isinstance(window, dict)
        and _is_number(window.get("start_ts"))
        and _is_number(window.get("end_ts"))
    ):
        window = None  # 窗是可选事实：缺/字段不全/非数值→按无窗口径（全 0 起+0 计数）

    power_steps = facts.get("power_steps")
    if power_steps is None:
        power_steps = []
    if not isinstance(power_steps, (list, tuple)):
        raise ValueError(
            f"power_steps 必须为 list，实际为 {type(power_steps).__name__}"
        )

    serialized_params, stringified = _stringify_params(facts.get("params") or {})
    window_samples = (
        _ms_to_samples(window["end_ts"] - window["start_ts"], sample_rate)
        if window is not None
        else 0
    )

    annotations = []
    for step in power_steps:
        if not isinstance(step, dict):
            raise ValueError(
                f"power_steps 条目必须为 dict，实际为 {type(step).__name__}"
            )
        sample_start = (
            _ms_to_samples(step.get("ts") - window["start_ts"], sample_rate)
            if window is not None and _is_number(step.get("ts"))
            else 0  # 无窗或档缺 ts→该档从 0 号样本起标注
        )
        annotation = {
            "core:sample_start": sample_start,
            "core:sample_count": window_samples,
            "jam:style": style,
            "jam:power_db": step.get("target_db"),
            "jam:params": serialized_params,
        }
        if stringified:
            annotation["jam:params_note"] = _STRINGIFIED_NOTE
        annotations.append(annotation)

    return {
        "global": {
            "core:datatype": _DATATYPE,
            "core:sample_rate": sample_rate,
            "core:version": _SIGMF_VERSION,
            "jam:backend": backend,
            "jam:clock_ref": clock_ref,
            "jam:run_id": run_id,
        },
        "captures": [
            {
                "core:sample_start": 0,
                "core:frequency": freq_hz,
                "jam:window_start_ts": window["start_ts"] if window is not None else None,
            }
        ],
        "annotations": annotations,
    }
