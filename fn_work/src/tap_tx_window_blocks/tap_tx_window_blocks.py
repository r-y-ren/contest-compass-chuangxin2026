"""发射窗监测采集装配（录音窗覆盖发射窗，R88）——重写规约与签名意图详见 fn_docs/responsibility.md R88 功能块。

交错缝=阶梯档间停留 dwell：dwell_cb 取代 time.sleep，切片睡眠间逐 tick 有界拉
backend.read_samples，块经 shared/normalize_monitor_block 归一（sim 元组块=拉取时刻盖戳、B210 dict 块=保留后端 ts 序号域——交窗时间基础 sim 侧成立，真机随 R87）入 ctx['tx_window_blocks'] 缓冲；采集阶段 record_run_streams
监测源前置消费该缓冲（预归一块 ts 不重盖）——SigMF 录音与 monitor.csv 因此含发射窗
内容（sim 下为环回块：含样式调制、meta 无 synthetic 标注），交窗硬判据落地。

启用白名单=backend capabilities kind ∈ {sim, b210}（统一编排用户裁决）；replay 回放
时间线自洽不启用（后置采集即其语义）。急停：dwell 分片停检置位→EmergencyStopRequested
（run_demo 定义，延迟导入防环导），沿 ladder「先停发射再透传」既有路径。
"""

import math
import time
from numbers import Real

from src.shared.normalize_monitor_block import normalize_monitor_block

# ---- 装配定桩常量（模块级单一事实源，可调）----
_DEFAULT_SLICE_S = 0.05  # dwell 切片时长上限（秒）：数十毫秒量级——够细不漏窗内块、够粗不空转。
_DEFAULT_BLOCKS_PER_TICK = 4  # 每 tick 拉取块数上限：有界防失控（发射窗内逐片拉取的预算）。
_ENABLED_KINDS = frozenset({"sim", "b210"})  # 启用白名单（统一编排用户裁决；replay 后置采集即其语义）。


def tap_tx_window_blocks(ctx: dict) -> "dict | None":
    """发射窗监测采集装配器（只装配不拉取——发射窗内拉取全部经 dwell_cb 承载）。

    :param ctx: 运行上下文——backend（能力探测对象）、停检凭据取 ctx.get('stop')
        （None=不停检口径）。
    :return: 启用（backend 在位+capabilities()['kind'] ∈ {sim, b210}+read_samples
        可调用）→ {'dwell_cb': 分片停留回调, 'blocks': 块缓冲引用}，且块缓冲挂
        ctx['tx_window_blocks']；不满足白名单（replay/无 backend/无 read_samples）
        → None 且不写 ctx 键（调用方不接线，后置采集语义保持）。
    :raises: 装配期不捕获（能力探测只读不试拉）。
    """
    if not isinstance(ctx, dict):
        # 宽松不抛：ctx 形状校验归 gb 协议调用方（execute_gb42590_protocol 已校验）。
        return None
    backend = ctx.get("backend")
    capabilities_getter = getattr(backend, "capabilities", None)
    if not callable(capabilities_getter):
        # 无 capabilities 方法（含 backend 缺失/None）→ 视为不启用（防御不抛）。
        return None
    caps = capabilities_getter()
    if not isinstance(caps, dict):
        # 能力元数据非 dict → 视为不启用（防御不抛——装配期只读探测）。
        return None
    if caps.get("kind") not in _ENABLED_KINDS:
        # replay/未知 kind：后置采集语义保持——不写 ctx 键，调用方不接线。
        return None
    if not callable(getattr(backend, "read_samples", None)):
        # 白名单 kind 但缺拉取契约 → 不接线（探测只读，不试拉验证）。
        return None
    blocks: list = []
    ctx["tx_window_blocks"] = blocks
    dwell_cb = _make_tick_dwell_cb(
        backend, blocks, ctx.get("stop"), _DEFAULT_SLICE_S, _DEFAULT_BLOCKS_PER_TICK
    )
    return {"dwell_cb": dwell_cb, "blocks": blocks}


def _make_tick_dwell_cb(
    backend: object,
    blocks: list,
    stop: object,
    slice_s: float,
    max_blocks_per_tick: int,
):
    """dwell 分片停留回调工厂（纯编排：切片睡眠/停检/tick 三步均已定桩或下探）。

    工厂期即参数域校验（发射前拒绝口径，与 run_power_ladder._dwell_seconds 风格
    一致）：slice_s 须正有限实数（拒 bool/非实数/NaN/±inf/非正）、max_blocks_per_tick
    须正整数（拒 bool/非整数/非正）——非法 ValueError。产出的 dwell_cb 闭包持有
    backend/blocks/stop/slice_s/max_blocks_per_tick。

    :param backend: 具备 read_samples 的监测后端。
    :param blocks: 块缓冲列表（_pull_tick 的追加目标）。
    :param stop: 停检凭据容器（形如 {'flag': bool}；None=不停检）。
    :param slice_s: 切片时长上限（秒，正数；dwell 实际切片 ≤ min(dwell, slice_s)）。
    :param max_blocks_per_tick: 每 tick 拉取块数上限（正整数）。
    :return: dwell_cb(dwell_s) 回调——每次调用执行「dwell 切片逐片：停检→tick→
        sleep」；dwell_s=0（或宽松归一后为 0）保底一次「停检→tick」（发射窗极短
        也须采到窗内容——交窗硬判据兜底），返回 None。dwell_s 域校验归
        run_power_ladder 发射前拒绝，此处宽松：不可转/非有限/负数一律按 0 处理
        （保底一 tick），不引入新异常类型。
    :raises ValueError: 工厂期参数域拒绝（slice_s/max_blocks_per_tick 非法）。
    :raises EmergencyStopRequested: 经产出回调：停旗置位（函数体内延迟导入
        src.run_demo.run_demo——tap 模块不得顶层 import run_demo，防环导）。
    :raises Exception: 经产出回调：read_samples 异常原样上抛（由 ladder 停发射后透传）。
    """
    if isinstance(slice_s, bool) or not isinstance(slice_s, Real):
        raise ValueError(f"slice_s 必须为实数（bool/非数值一律拒绝）：{slice_s!r}")
    slice_seconds = float(slice_s)
    if not math.isfinite(slice_seconds):
        raise ValueError(f"slice_s 必须为有限数（拒 NaN/±inf）：{slice_s!r}")
    if slice_seconds <= 0.0:
        raise ValueError(f"slice_s 必须为正数（切片时长上限），实际: {slice_seconds}")
    if isinstance(max_blocks_per_tick, bool) or not isinstance(max_blocks_per_tick, int):
        raise ValueError(
            f"max_blocks_per_tick 必须为整数（bool 一律拒绝）：{max_blocks_per_tick!r}"
        )
    if max_blocks_per_tick <= 0:
        raise ValueError(f"max_blocks_per_tick 必须为正整数，实际: {max_blocks_per_tick}")

    def _raise_if_stopped_at_slice() -> None:
        # 停检口径同 run_demo._stop_requested：仅 dict 形状认停旗（None/非 dict 忽略）。
        if isinstance(stop, dict) and bool(stop.get("flag")):
            # 延迟导入防环导：run_demo 装配链（后续批次）将引用本模块，本模块
            # 顶层 import run_demo 会成环——仅停旗命中才付这笔导入成本。
            from src.run_demo.run_demo import EmergencyStopRequested

            raise EmergencyStopRequested(
                "急停旗已置位（stop['flag']=True，dwell 分片停检——协作中止）"
            )

    def dwell_cb(dwell_s: float) -> None:
        # 宽松归一（域校验归 run_power_ladder 发射前拒绝）：不可转 float/非有限/
        # 负数一律按 0 处理——保底一 tick，不抛新类型。
        try:
            total = float(dwell_s)
        except (TypeError, ValueError):
            total = 0.0
        if not math.isfinite(total) or total < 0.0:
            total = 0.0
        remaining = total
        while True:
            _raise_if_stopped_at_slice()
            _pull_tick(backend, blocks, max_blocks_per_tick)
            if remaining <= 0.0:
                break  # dwell=0 场景：进入循环首片即保底（停检→tick 已执行）
            nap = min(remaining, slice_seconds)
            time.sleep(nap)
            remaining -= nap

    return dwell_cb


def _pull_tick(backend: object, blocks: list, max_blocks: int) -> None:
    """单次有界拉取：read_samples 返回块列表逐块归一盖戳入缓冲；空读静默返回。

    返回值非 list（含 None/单块）按空读静默——sim/B210 契约为 list，宽松容错与
    _tee_backend_stream 的空读口径一致（发射尚未泵出/源耗尽皆非错误）。

    :param backend: 具备 read_samples(max_blocks) 契约的监测后端。
    :param blocks: 块缓冲列表（副作用=追加归一块 dict；ts=拉取时刻盖戳（sim 元组块；B210 dict 块保留后端 ts 序号域））。
    :param max_blocks: 本次拉取块数上限（正整数）。
    :raises: read_samples 异常原样上抛（停发射路径归调用链上层）。
    """
    result = backend.read_samples(max_blocks)
    if not isinstance(result, list):
        # 非 list（None/单块）按空读：不追加不抛（空读口径见 docstring）。
        return
    for raw in result:
        blocks.append(normalize_monitor_block(raw))

def _start_b210_capture_thread(backend, blocks, stop, max_blocks):
    """B210 采集线程主体：循环 read_samples(1)→归一→append；停旗/到顶退出；异常暂存。

    输入: backend+缓冲+stop+上限 / 输出: 线程句柄/错误槽 / 错误: 读异常存入错误槽由 close 重抛。
    """
    raise NotImplementedError("unimplemented:fn:_start_b210_capture_thread")


def _stop_capture_thread(handle, timeout_s=1.0):
    """置停止旗→join（≤timeout）→超时注记→错误槽非空则重抛；幂等。

    输入: 线程句柄/错误槽 / 输出: 无 / 错误: 线程异常重抛；join 超时不抛只注记。
    """
    raise NotImplementedError("unimplemented:fn:_stop_capture_thread")
