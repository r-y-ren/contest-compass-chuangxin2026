"""三路原始数据→三图数据帧纯计算（含失效档标注）——B13 叶子，R25。

职责口径（供 plot_triple_curves 绘三图；本函数只算不画）：

- 输入 ``data = {'kpi': [归一行…], 'events': [事件…], 'failure_levels':
  [失效条目…]（可空）}``。时间取值口径：事件/失效优先 ``ts_ms``、缺则 ``ts``
  （append_event 权威盖戳键兜底）；KPI 行优先 ``ts_ms``、依次 ``timestamp_ms``
  （normalize_kpi 归一行键）、``ts``。时间非有限实数（bool 不算）的行/事件
  不参与任何时间轴计算（不抛，纯计算降级）。
- 帧A（PER–电平）：``x`` = power_step 事件的 ``target_db`` 序（按事件时间升序，
  事件序而非数组索引）；每个 power_step 开一窗（窗口 i = 该事件时刻起至下一
  power_step 事件时刻前，末窗无上界，首事件之前的 KPI 行不属任何窗），
  ``y`` = 窗内 KPI 行 ``judge_per`` 均值（缺键/None/非有限实数的行不计入），
  窗内无判据样本 → ``None``（绘图断点）；``window_sizes`` = 各窗计入均值的
  判据样本数。失效档红点：``failure_x`` = 失效条目 ``step`` 对位窗口的 x 值
  （优先按事件自带 ``step`` 字段对位，缺则按窗口序号；越界/不可解析跳过）。
- 帧B（吞吐–误码）：``x`` = 帧A各窗 PER（``None`` 窗剔除），``y`` = 1−PER
  **等效近似**——无真实业务流时的代理口径，非实测业务吞吐。
- 帧C（事件时间线）：KPI/事件/失效三类点合并同一时间轴（``t`` 时间升序，
  同刻按 事件→KPI→失效 排定），``kind``: 0=事件/1=KPI/2=失效，``labels``
  为逐点标注串。
- 输出：``{'frame_a': {'x','y','failure_x','window_sizes'},
  'frame_b': {'x','y'}, 'frame_c': {'t','kind','labels'},
  'n_windows'（=power_step 窗数）, 'n_kpi_rows'（=kpi 行总数）}``；
  三路全空 → 三帧空列表 + n=0，不抛。
- 错误：``data`` 非 dict、三键缺失或非 list、任一元素非 dict →
  :class:`ValueError`（元素错误消息含来源键+索引）。
"""
from __future__ import annotations

import math

#: 三路数据的必需键（均必须为 list）。
_REQUIRED_KEYS = ("kpi", "events", "failure_levels")

#: 帧C类别码：0=事件 / 1=KPI / 2=失效。
KIND_EVENT, KIND_KPI, KIND_FAILURE = 0, 1, 2


def _finite(value) -> float | int | None:
    """有限实数透传（bool/非数/NaN/inf → None）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _time_of(item: dict, keys: tuple[str, ...]) -> float | int | None:
    """按优先键序取首个有限实数时间；全缺 → None。"""
    for key in keys:
        ts = _finite(item.get(key))
        if ts is not None:
            return ts
    return None


def _event_ts(item: dict):
    """事件/失效时间：ts_ms 优先，ts 兜底（对齐源口径，见 record_run_streams）。"""
    return _time_of(item, ("ts_ms", "ts"))


def _kpi_ts(row: dict):
    """KPI 行时间：ts_ms 优先，timestamp_ms（归一行键）/ts 兜底。"""
    return _time_of(row, ("ts_ms", "timestamp_ms", "ts"))


def _validate(data) -> None:
    """形状校验：data dict → 三键 list → 元素逐个 dict（消息含键+索引）。"""
    if not isinstance(data, dict):
        raise ValueError(
            f"data 必须为 dict（三路原始数据），实际类型 {type(data).__name__}: {data!r}"
        )
    for key in _REQUIRED_KEYS:
        if key not in data:
            raise ValueError(
                f"data 缺少三路数据键 {key!r}（kpi/events/failure_levels 均必须为 list）"
            )
        if not isinstance(data[key], list):
            raise ValueError(
                f"data[{key!r}] 必须为 list，实际类型 {type(data[key]).__name__}: "
                f"{data[key]!r}"
            )
    for key in _REQUIRED_KEYS:
        for index, item in enumerate(data[key]):
            if not isinstance(item, dict):
                raise ValueError(
                    f"data[{key!r}][{index}] 必须为 dict，实际类型 "
                    f"{type(item).__name__}: {item!r}"
                )


def build_curve_frames(data: dict) -> dict:
    """三路原始数据→三图数据帧（含失效档标注），纯计算。

    输入/输出/错误口径见模块 docstring；示例::

        frames = build_curve_frames({
            'kpi': [{'ts_ms': 150, 'judge_per': 0.08}, ...],
            'events': [{'type': 'power_step', 'ts_ms': 100,
                        'step': 0, 'target_db': -10.0}, ...],
            'failure_levels': [{'step': 1, 'ts_ms': 320}, ...],
        })
        # frames['frame_a']['y'] == [0.08, ...]  各档窗口 judge_per 均值
        # frames['frame_b']['y'] == [0.92, ...]  相对吞吐 1−PER 等效近似
    """
    _validate(data)

    events = data["events"]
    kpi_rows = data["kpi"]
    failure_levels = data["failure_levels"]

    # ---- 帧A：power_step 窗口（按事件时间升序；缺时间的 power_step 不开窗）----
    steps = [
        ev
        for ev in events
        if ev.get("type") == "power_step" and _event_ts(ev) is not None
    ]
    steps.sort(key=_event_ts)  # type: ignore[arg-type]
    x = [_finite(ev.get("target_db")) for ev in steps]
    bounds = [_event_ts(ev) for ev in steps]  # type: ignore[arg-type]

    # KPI 行按时间排序后开窗（乱序输入时间序为准）；首事件之前的行不属任何窗
    timed_rows = sorted(
        ((ts, row) for row in kpi_rows if (ts := _kpi_ts(row)) is not None),
        key=lambda pair: pair[0],
    )
    window_judge_per: list[list[float]] = [[] for _ in steps]
    if bounds:
        window_index = 0
        for ts, row in timed_rows:
            if ts < bounds[0]:
                continue  # 首个 power_step 之前的行：不进任何窗
            while window_index + 1 < len(bounds) and ts >= bounds[window_index + 1]:
                window_index += 1
            judge_per = _finite(row.get("judge_per"))
            if judge_per is not None:
                window_judge_per[window_index].append(judge_per)

    y: list = []
    window_sizes: list[int] = []
    for per_values in window_judge_per:
        window_sizes.append(len(per_values))
        y.append(sum(per_values) / len(per_values) if per_values else None)

    # 失效档红点：step 对位窗口（事件自带 step 字段优先，缺则按窗口序号兜底）
    step_to_pos: dict[int, int] = {}
    for pos, ev in enumerate(steps):
        step = ev.get("step")
        if isinstance(step, int) and not isinstance(step, bool):
            step_to_pos.setdefault(step, pos)
    failure_x: list = []
    for entry in failure_levels:
        step = entry.get("step")
        if not isinstance(step, int) or isinstance(step, bool):
            continue  # 不可解析档号：跳过（绘图降级，不抛）
        pos = step_to_pos.get(step, step if 0 <= step < len(steps) else None)
        if pos is not None:
            failure_x.append(x[pos])

    # ---- 帧B：吞吐–误码（1−PER 等效近似；None 窗剔除）----
    frame_b_x = [per for per in y if per is not None]
    frame_b_y = [1.0 - per for per in frame_b_x]

    # ---- 帧C：三类点合并时间轴（同刻 事件→KPI→失效）----
    points: list[tuple[float, int, str]] = []
    for ev in events:
        ts = _event_ts(ev)
        if ts is None:
            continue
        label = str(ev.get("type", "事件"))
        target = _finite(ev.get("target_db"))
        if target is not None:
            label += f"@{target}dB"
        points.append((ts, KIND_EVENT, label))
    for row in kpi_rows:
        ts = _kpi_ts(row)
        if ts is None:
            continue
        judge_per = _finite(row.get("judge_per"))
        points.append(
            (ts, KIND_KPI, f"PER={judge_per}" if judge_per is not None else "KPI")
        )
    for entry in failure_levels:
        ts = _event_ts(entry)
        if ts is None:
            continue
        points.append((ts, KIND_FAILURE, f"失效@档{entry.get('step')}"))
    points.sort(key=lambda point: (point[0], point[1]))

    return {
        "frame_a": {
            "x": x,
            "y": y,
            "failure_x": failure_x,
            "window_sizes": window_sizes,
        },
        "frame_b": {"x": frame_b_x, "y": frame_b_y},
        "frame_c": {
            "t": [point[0] for point in points],
            "kind": [point[1] for point in points],
            "labels": [point[2] for point in points],
        },
        "n_windows": len(steps),
        "n_kpi_rows": len(kpi_rows),
    }
