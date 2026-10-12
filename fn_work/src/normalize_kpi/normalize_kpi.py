"""三源 KPI 归一为统一行+口径元数据（异源冲突拒）——B11 顶层，R21。

把 ESP32/NRF24/sim 三源原始样本归一为统一 KPI 行，供 record_run_streams（DUT 路
出口）与 execute_gb42590_protocol（判据输入）消费：

- ``per`` 恒为样本 ``per_raw`` 透传；``judge_per`` 为判据用 PER（EN 300 328
  判据 PER≤10% 口径）：样本含 ``n_error``/``n_total`` 时经 compute_per 重算并附
  样本量警告（``meta['judge_note']``），仅有 ``per_raw`` 时直用并标
  ``'per_raw_only'``；
- ``rssi_dbm``：esp32/sim 透传（缺则 None）；nrf24 无 RSSI 口径，恒 None；
- ``rpd``：nrf24 透传否则 None；``jsr_db``：sim 透传否则 None；
- ``meta`` 附口径声明（BER→PER 以口径声明实现、F13 分辨率数字【待实测】）与
  原样本键集 ``source_fields``。

异源字段冲突（如 nrf24 样本带 ``rssi_dbm`` 键）抛 :class:`KpiError`，消息指明
源与字段；未知 source、sample 非 dict、缺 ``per_raw`` 同样抛 KpiError。
"""
from __future__ import annotations

from .compute_per import compute_per

#: 合法源清单（未知 source 的 KpiError 消息附此清单）。
VALID_SOURCES = ("esp32", "nrf24", "sim")

#: 样本缺 ``link`` 时按源映射的默认链路名。
_LINK_BY_SOURCE = {
    "esp32": "dut_esp32",
    "nrf24": "dut_nrf24",
    "sim": "dut_sim",
}

#: 各口径字段的合法携带源：字段 → 允许出现的源集合。
#: 出现在其余源的样本里即为异源字段冲突（如 nrf24 带 rssi_dbm——nrf24 无 RSSI 口径）。
_SOURCE_OF_FIELD = {
    "rssi_dbm": frozenset({"esp32", "sim"}),
    "rpd": frozenset({"nrf24"}),
    "jsr_db": frozenset({"sim"}),
    "per_model": frozenset({"sim"}),
}

#: 口径声明（R21/F13）：BER 比特级以口径声明实现，分辨率数字【待实测】后定。
_STYLE_STATEMENT = (
    "PER 包级（EN 300 328 判据 PER≤10%）——BER 比特级以口径声明实现，"
    "分辨率数字实测后定（requirements R21/F13）"
)


class KpiError(ValueError):
    """normalize_kpi 拒收样本；消息指明源与字段（或原因）。"""


def _check_conflicts(sample: dict, source: str) -> None:
    """异源口径字段冲突检测：消息指明源与字段。"""
    for field, allowed in _SOURCE_OF_FIELD.items():
        if field in sample and source not in allowed:
            raise KpiError(
                f"cross-source field conflict: source {source!r} sample carries "
                f"field {field!r} (allowed only for sources {sorted(allowed)})"
            )


def _judge_from_counts(sample: dict, source: str) -> tuple[float | None, str, str]:
    """由 n_error/n_total 经 compute_per 重算判据 PER，返回 (judge_per, note, basis)。"""
    try:
        result = compute_per(sample["n_error"], sample["n_total"])
    except ValueError as exc:
        raise KpiError(
            f"sample from source {source!r} invalid n_error/n_total: {exc}"
        ) from None
    return result["per"], result["samples_note"], "compute_per(n_error,n_total)"


def normalize_kpi(sample: dict, source: str) -> dict:
    """三源 KPI 归一为统一行+口径元数据（异源冲突拒）。

    Args:
        sample: 任一源原始样本 dict——esp32（per_raw/retries/rssi_dbm/seq…）、
            nrf24（per_raw/retries/rpd…）、sim（per_raw/per_model/jsr_db…）；
            可选 ``timestamp_ms``/``link`` 透传，含 ``n_error``/``n_total`` 时
            判据 PER 经 compute_per 重算。
        source: 样本来源，'esp32' | 'nrf24' | 'sim'。

    Returns:
        统一 KPI 行 dict::

            {'timestamp_ms': 透传, 'link': 透传或按源映射, 'source',
             'per': 样本 per_raw, 'retries': 透传缺 0,
             'rssi_dbm': esp32/sim 透传（nrf24 恒 None）,
             'judge_per': 判据用 PER, 'rpd': nrf24 透传否则 None,
             'jsr_db': sim 透传否则 None,
             'meta': {'style': 口径声明, 'source_fields': 原样本键集,
                      'judge_note': 样本量警告|'per_raw_only',
                      'judge_basis': 重算依据, ['per_model': sim 模型 PER]}]}

    Raises:
        KpiError: 未知 source（消息附三源清单）、sample 非 dict、缺 per_raw、
            异源口径字段冲突（指明源与字段）、n_error/n_total 非法。
    """
    if source not in VALID_SOURCES:
        raise KpiError(
            f"unknown source {source!r}; expected one of {list(VALID_SOURCES)}"
        )
    if not isinstance(sample, dict):
        raise KpiError(
            f"sample must be dict, got {type(sample).__name__}: {sample!r}"
        )
    if "per_raw" not in sample:
        raise KpiError(
            f"sample from source {source!r} missing required field 'per_raw' "
            f"(fields: {sorted(sample)})"
        )
    _check_conflicts(sample, source)

    if "n_error" in sample and "n_total" in sample:
        judge_per, judge_note, judge_basis = _judge_from_counts(sample, source)
    else:
        judge_per = sample["per_raw"]
        judge_note = "per_raw_only"
        judge_basis = "per_raw"

    meta: dict = {
        "style": _STYLE_STATEMENT,
        "source_fields": sorted(sample),
        "judge_note": judge_note,
        "judge_basis": judge_basis,
    }
    if "per_model" in sample:
        meta["per_model"] = sample["per_model"]

    return {
        "timestamp_ms": sample.get("timestamp_ms"),
        "link": sample["link"] if "link" in sample else _LINK_BY_SOURCE[source],
        "source": source,
        "per": sample["per_raw"],
        "retries": sample.get("retries", 0),
        "rssi_dbm": sample.get("rssi_dbm") if source in ("esp32", "sim") else None,
        "judge_per": judge_per,
        "rpd": sample.get("rpd") if source == "nrf24" else None,
        "jsr_db": sample.get("jsr_db") if source == "sim" else None,
        "meta": meta,
    }
