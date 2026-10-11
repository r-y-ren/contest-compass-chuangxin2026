"""读取后端/GPSDO 状态：GPS 锁定传感器序列探测 + 时钟/时间源汇总，永不抛出——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

_GPS_SENSOR_NAMES: tuple[str, ...] = ("gps_locked", "gps_gpgga", "gps_time")
_TRUE_STRINGS: frozenset = frozenset({"true", "locked", "1", "yes", "ok"})
_FALSE_STRINGS: frozenset = frozenset({"false", "unlocked", "0", "no", "none", ""})


def _callable_attr(obj: object, name: str):
    """取对象属性并确认可调用；缺失、不可调用或取属性即抛异常时返回 None。"""
    try:
        attr = getattr(obj, name, None)
    except Exception:
        return None
    return attr if callable(attr) else None


def _parse_sensor_value(raw: object) -> bool:
    """传感器原始读数→布尔：bool 原样；字符串按 'true'/'locked'/'1'（大小写不敏感）词汇表解析，未识别字符串按真值处理；其余按 bool(raw)。"""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in _TRUE_STRINGS:
            return True
        if text in _FALSE_STRINGS:
            return False
        return bool(text)
    return bool(raw)


def probe_gpsdo_status(backend=None) -> dict:
    """读取鸭子 backend 的 GPSDO/参考源状态（永不抛出）。

    - backend=None → available False, reason 'no_backend'。
    - GPS 传感器按 gps_locked → gps_gpgga → gps_time 序列调用 get_mboard_sensor，
      首个可读传感器给出 gps_locked 真值并决定 available；某传感器抛异常仅记入
      reason 并继续探测下一个。
    - get_clock_source()/get_time_source() 缺方法跳过（对应输出 None），抛异常记入 reason。
    - 缺 get_mboard_sensor（即无 GPS 能力，含完全无相关方法的后端）→ reason 'no_gps_support'。
    - 传感器可读但值为假 → reason 'gps_not_locked'；全部顺利且锁定 → reason None。
    """
    status: dict = {
        "available": False,
        "gps_locked": None,
        "clock_source": None,
        "time_source": None,
        "sensors_read": [],
        "reason": None,
    }
    if backend is None:
        status["reason"] = "no_backend"
        return status

    failures: list[str] = []

    read_sensor = _callable_attr(backend, "get_mboard_sensor")
    if read_sensor is not None:
        for name in _GPS_SENSOR_NAMES:
            try:
                raw = read_sensor(name)
            except Exception as exc:  # 单传感器失败：记录后继续探测下一个，不向上抛
                failures.append(f"sensor {name} read failed: {type(exc).__name__}: {exc}")
                continue
            locked = _parse_sensor_value(raw)
            status["sensors_read"].append(name)
            status["gps_locked"] = locked
            status["available"] = locked
            break  # 序列探测：首个可读传感器即结论

    for method_name, key in (("get_clock_source", "clock_source"), ("get_time_source", "time_source")):
        method = _callable_attr(backend, method_name)
        if method is None:
            continue
        try:
            status[key] = method()
        except Exception as exc:  # 源读取失败：记录不抛
            failures.append(f"{method_name} read failed: {type(exc).__name__}: {exc}")

    if failures:
        status["reason"] = "; ".join(failures)
    elif read_sensor is None:
        status["reason"] = "no_gps_support"
    elif not status["available"]:
        status["reason"] = "gps_not_locked"
    return status
