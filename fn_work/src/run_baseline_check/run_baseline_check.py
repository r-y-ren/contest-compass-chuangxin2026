"""无干扰对照段：基线异常即中止防误报——B12 顶层，R24；重写规约与签名意图详见 fn_docs/responsibility.md。

正式注入干扰前的对照段判据（R24：每轮先跑无干扰基线，异常即中止防误报）：

- 输入为**收归一行流**的 ``samples``：normalize_kpi（B11）已归一的统一 KPI 行
  ——判据口径 ``judge_per``、``rssi_dbm`` 等字段沿用归一产出，本函数不收原始
  样本、不做二次归一；
- 聚合窗口健康判据（``min_samples`` 默认 10，按 ``judge_per`` 非 None 的判据
  样本计）：
  - PER 均值 < ``baseline_per_threshold``（默认 0.05——基线比 EN 300 328 判据
    0.10 更严：无干扰段对环境噪声敏感）→ 基线健康放行；健康要求**严格低于**
    阈值，均值恰等于阈值按超阈处理；
  - 判据样本不足（判据样本数 < ``min_samples``，含 ``judge_per`` 全 None 的
    不可比窗）→ **保守拒绝**——无法判健康即不放行；
  - RSSI 稳定性（有 ``rssi_dbm`` 样本时极差 < ``rssi_range_db``，默认 20dB）：
    超限仅记 ``warning:`` 前缀违例条目，不中止、不影响放行；
- 聚合为顺序无关统计（均值/极差/计数），时间戳乱序容忍。

调用方：execute_gb42590_protocol（前置）；run_demo。
"""
from __future__ import annotations

from collections.abc import Iterable

#: 基线 PER 放行阈（比判据 0.10 更严：基线段对环境噪声敏感）。
DEFAULT_BASELINE_PER_THRESHOLD = 0.05

#: 判基线健康所需最小判据样本数（``judge_per`` 非 None 的样本数下限）。
DEFAULT_MIN_SAMPLES = 10

#: RSSI 稳定性极差阈（dB）。
DEFAULT_RSSI_RANGE_DB = 20.0

_ADVICE_PASS = "基线健康，放行正式干扰注入"
_ADVICE_PASS_RSSI_UNSTABLE = "基线健康，放行正式干扰注入；RSSI 波动大，建议关注环境稳定性"
_ADVICE_PER_EXCEEDED = "排查环境噪声或链路自身故障后再测"
_ADVICE_INSUFFICIENT = "延长基线采集窗口"


def _resolve_threshold(threshold: dict | None) -> tuple[float, int, float]:
    """解析阈值覆盖，返回 (baseline_per_threshold, min_samples, rssi_range_db)。"""
    if threshold is None:
        return (
            DEFAULT_BASELINE_PER_THRESHOLD,
            DEFAULT_MIN_SAMPLES,
            DEFAULT_RSSI_RANGE_DB,
        )
    if not isinstance(threshold, dict):
        raise ValueError(
            f"threshold must be dict or None, got {type(threshold).__name__}: {threshold!r}"
        )
    return (
        threshold.get("baseline_per_threshold", DEFAULT_BASELINE_PER_THRESHOLD),
        threshold.get("min_samples", DEFAULT_MIN_SAMPLES),
        threshold.get("rssi_range_db", DEFAULT_RSSI_RANGE_DB),
    )


def run_baseline_check(samples: Iterable[dict], threshold: dict | None = None) -> dict:
    """无干扰对照段：基线 KPI 聚合判健康，异常即中止防误报。

    Args:
        samples: normalize_kpi 已归一的基线 KPI 行流（单遍消费，迭代器亦可）；
            逐行读取 ``judge_per``（判据 PER，None=不可比窗不计入判据）与
            ``rssi_dbm``（None=该样本无 RSSI，跳过稳定性统计）。
        threshold: 阈值覆盖 dict，可选项 ``baseline_per_threshold``（默认 0.05）、
            ``min_samples``（默认 10）、``rssi_range_db``（默认 20.0）；
            None 用全默认。

    Returns:
        基线报告 dict::

            {'passed': bool,                # 放行与否（RSSI 警告不影响）
             'per_mean': float | None,      # 判据样本 PER 均值（无可判样本时 None）
             'n_samples': int,              # 消费行总数（含不可判行）
             'n_judged': int,               # judge_per 非 None 的判据样本数
             'violations': [str],           # 拒绝原因 + 'warning:rssi_unstable' 等警告条目
             'stop_reason': str | None,     # 'baseline_per_exceeded' |
                                           # 'insufficient_baseline_samples' | None
             'advice': str}                 # 排查提示（超阈→查环境噪声/链路；
                                           # 样本不足→延长采集窗口；健康→放行）

    Raises:
        ValueError: samples 非可迭代对象；或流中行非 dict（指明行号与类型，消费
            即中止）；或 threshold 非 dict 且非 None。
    """
    per_threshold, min_samples, rssi_range_db = _resolve_threshold(threshold)

    try:
        rows = iter(samples)
    except TypeError:
        raise ValueError(
            f"samples must be an iterable of normalize_kpi rows, "
            f"got {type(samples).__name__}: {samples!r}"
        ) from None

    n_samples = 0
    n_judged = 0
    per_sum = 0.0
    rssi_values: list[float] = []

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(
                f"samples[{index}] must be a dict (normalize_kpi row), "
                f"got {type(row).__name__}: {row!r}"
            )
        n_samples += 1
        judge_per = row.get("judge_per")
        if judge_per is not None:
            n_judged += 1
            per_sum += judge_per
        rssi = row.get("rssi_dbm")
        if rssi is not None:
            rssi_values.append(rssi)

    per_mean = per_sum / n_judged if n_judged else None

    violations: list[str] = []
    if per_mean is None or n_judged < min_samples:
        # 保守拒绝：判据样本不足（含 judge_per 全 None 的不可比窗）——无法判健康
        # 即不放行；已可判的少数样本均值仍随报告透出供对照。
        passed = False
        stop_reason = "insufficient_baseline_samples"
        advice = _ADVICE_INSUFFICIENT
        violations.append(stop_reason)
    elif per_mean >= per_threshold:
        passed = False
        stop_reason = "baseline_per_exceeded"
        advice = _ADVICE_PER_EXCEEDED
        violations.append(stop_reason)
    else:
        passed = True
        stop_reason = None
        advice = _ADVICE_PASS

    rssi_unstable = bool(rssi_values) and (
        max(rssi_values) - min(rssi_values)
    ) >= rssi_range_db
    if rssi_unstable:
        # RSSI 不稳仅警告：violations 记 warning 前缀条目，不中止、不影响放行。
        violations.append("warning:rssi_unstable")
        if passed:
            advice = _ADVICE_PASS_RSSI_UNSTABLE

    return {
        "passed": passed,
        "per_mean": per_mean,
        "n_samples": n_samples,
        "n_judged": n_judged,
        "violations": violations,
        "stop_reason": stop_reason,
        "advice": advice,
    }
