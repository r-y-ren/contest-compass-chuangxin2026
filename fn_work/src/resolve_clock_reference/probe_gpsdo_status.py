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


def _match_vocabulary(text: str) -> tuple[bool, bool]:
    """字符串按真/假词汇表匹配（大小写不敏感、去空白）→ (locked, recognized)。"""
    lowered = text.strip().lower()
    if lowered in _TRUE_STRINGS:
        return True, True
    if lowered in _FALSE_STRINGS:
        return False, True
    return False, False


def _parse_sensor_value(raw: object) -> tuple[bool, bool]:
    """传感器原始读数→(locked, recognized)，fail-closed 口径（B6 中#6）。

    - bool 原样（recognized）；
    - 传感器对象有 to_bool()（uhd sensor_value 口径）→ 用之（调用异常按未识别）；
    - 字符串按 'true'/'locked'/'1'（大小写不敏感）词汇表解析；其余无 to_bool 的
      非布尔对象 str() 后走同一词汇表；
    - 未识别 → (False, False)：不再按真值回退——bool(raw) 对默认对象恒真，
      未识别读数按真值处理会假报 GPS 锁定（fail-open），现在一律记假。
    """
    if isinstance(raw, bool):
        return raw, True
    to_bool = _callable_attr(raw, "to_bool")
    if to_bool is not None:
        try:
            return bool(to_bool()), True
        except Exception:
            return False, False
    if isinstance(raw, str):
        return _match_vocabulary(raw)
    try:
        return _match_vocabulary(str(raw))
    except Exception:  # str() 也炸的敌意对象：按未识别 fail-closed
        return False, False


def probe_gpsdo_status(backend=None) -> dict:
    """读取鸭子 backend 的 GPSDO/参考源状态（永不抛出）。

    - backend=None → available False, reason 'no_backend'。
    - GPS 传感器按 gps_locked → gps_gpgga → gps_time 序列调用 get_mboard_sensor，
      首个可读传感器给出 gps_locked 真值并决定 available；某传感器抛异常仅记入
      reason 并继续探测下一个。真值解析 fail-closed（B6 中#6）：传感器对象有
      to_bool() 用之；否则字符串/对象 str() 后按词汇表解析；未识别读数一律记
      False 并在 reason 标注 'unrecognized_sensor_value'（不按真值回退）。
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
            locked, recognized = _parse_sensor_value(raw)
            status["sensors_read"].append(name)
            status["gps_locked"] = locked
            status["available"] = locked
            if not recognized:
                failures.append(
                    f"sensor {name} value not recognized "
                    f"(unrecognized_sensor_value): {raw!r}"
                )
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
