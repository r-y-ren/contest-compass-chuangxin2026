"""时基决策：GPS/10MHz/PPS 探测→驯服或软件钟降级+口径——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

from .probe_gpsdo_status import probe_gpsdo_status

_DISCIPLINE_SOURCE = "gpsdo"
_SETTER_NAMES: tuple[str, ...] = ("set_clock_source", "set_time_source")


def _callable_attr(obj: object, name: str):
    """取对象属性并确认可调用；缺失、不可调用或取属性即抛异常时返回 None。"""
    try:
        attr = getattr(obj, name, None)
    except Exception:
        return None
    return attr if callable(attr) else None


def _probe_safe(backend) -> dict:
    """probe_gpsdo_status 包装：依赖其“永不抛出”承诺，另加兜底以防万一。"""
    try:
        return probe_gpsdo_status(backend)
    except Exception as exc:  # 双保险：探测意外失败也只降级、不向上抛
        return {
            "available": False,
            "gps_locked": None,
            "clock_source": None,
            "time_source": None,
            "sensors_read": [],
            "reason": f"probe failed: {type(exc).__name__}: {exc}",
        }


def resolve_clock_reference(backend=None) -> dict:
    """初始化时决定时基（永不抛出）：探测→驯服或降级，输出 ClockReference 口径。

    - probe_gpsdo_status(backend) available（GPS 锁定）→尝试启用驯服：backend 有
      set_clock_source/set_time_source 则调 'gpsdo'；任一调用异常→降级 software，
      失败原因逐条累积进 warnings。
    - 不可用→basis.clock_source 已 'external'（外接 10MHz）→external 时基。
    - 其余（含 backend=None）→software 时基，降级原因记入 warnings，不阻塞。
    """
    warnings: list[str] = []
    status = _probe_safe(backend)

    clock_ref = "software"
    discipline_applied = False

    if status["available"]:
        clock_ref = "gpsdo"
        setters = [(name, _callable_attr(backend, name)) for name in _SETTER_NAMES]
        applicable = [(name, method) for name, method in setters if method is not None]
        if not applicable:
            warnings.append(
                "gps locked but set_clock_source/set_time_source missing; "
                "assuming pre-configured gpsdo reference, discipline not applied"
            )
        else:
            setup_failed = False
            for name, method in applicable:
                try:
                    method(_DISCIPLINE_SOURCE)
                except Exception as exc:  # 驯服调用失败：记原因，随后整体降级
                    setup_failed = True
                    warnings.append(
                        f"{name}('{_DISCIPLINE_SOURCE}') failed: {type(exc).__name__}: {exc}"
                    )
            if setup_failed:
                clock_ref = "software"
                warnings.append("clock reference degraded to software: discipline setup failed")
            else:
                discipline_applied = True
    elif status["clock_source"] == "external":
        clock_ref = "external"  # 外接 10MHz：后端已配置外部参考，无需驯服
    else:
        reason = status["reason"] or "gpsdo unavailable"
        warnings.append(f"clock reference degraded to software: {reason}")

    return {
        "clock_ref": clock_ref,
        "basis": status,
        "discipline_applied": discipline_applied,
        "warnings": warnings,
    }
