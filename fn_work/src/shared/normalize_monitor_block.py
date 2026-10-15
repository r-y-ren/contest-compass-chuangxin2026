"""监测块归一+主机单调钟盖戳（共享）——重写规约与签名意图详见 fn_docs/responsibility.md 共享函数节。

〔新上提·快速通道 2026-10-15（R88）：自 record_run_streams._as_monitor_block 上提为共享
实现（原私有函数改薄壳调用）——发射窗内拉取（tap_tx_window_blocks）与采集期拉取
（record_run_streams）两处同源归一+盖戳，防两套口径漂移。〕

盖戳语义=调用时刻：发射窗内拉取即窗内时间戳（R88 交窗判据的时间基础——块时间戳
必须落在 power_step 事件窗内，三元开窗/对齐才相交）。
"""
import time


def normalize_monitor_block(block: object) -> object:
    """后端块形状归一：dict 直通；(samples, meta) 元组（sim 契约）转块 dict。

    SimBackend.read_samples 的元素是 (rx_block, meta) 二元组（meta 含 'rx_ts'
    单调**块号**，非毫秒域），而 capture_monitor_spectrum / write_sigmf_recording
    只认块 dict（samples/ts/overflow）——在此归一。归一时 ts 以**主机单调钟
    盖戳**（time.monotonic()*1000，与 kpi 样本（drive_*）及 append_event 事件
    同一毫秒域：rx_ts 块号直接当 ts 用会让 monitor.csv/统计行/对齐配对错单位，
    块号降级为 'block_index' 附注保留溯源）；其余形状原样透传（由 capture 的
    块形状校验拒，走停发射路径）。

    :param block: 后端原始块——dict / (samples, meta) 二元组 / 其余形状。
    :return: 归一块 dict（或原样透传形状）。
    :raises: 不抛（形状拒归 capture 侧）。
    """
    if isinstance(block, dict):
        return block
    if isinstance(block, tuple) and len(block) == 2 and isinstance(block[1], dict):
        samples, meta = block
        return {
            "samples": samples,
            # 主机单调钟毫秒盖戳（B12 中#1）：块号非毫秒域，不得充当 ts；
            # 浮点毫秒保逐块严格递增（同毫秒内两块 int 会并列）。
            "ts": time.monotonic() * 1000.0,
            "block_index": meta.get("rx_ts"),  # sim 块号附注（溯源用，非时间戳）
            "overflow": bool(meta.get("overflow", False)),
        }
    return block
