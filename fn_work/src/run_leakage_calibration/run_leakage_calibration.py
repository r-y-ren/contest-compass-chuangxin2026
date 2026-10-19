"""自漏标定入口（R100）——重写规约与签名意图详见 fn_docs/responsibility.md 域二十六。"""
from __future__ import annotations

__all__ = ["run_leakage_calibration"]


def run_leakage_calibration(target_band, out_path, backend=None, dwell_s=1.0):
    """自漏标定编排：两相位采集→逐频点耦合→写 leakage.json。

    输入: target_band=(lo,hi) MHz / out_path 表路径 / backend 可选实例 / dwell_s 相位采集时长
    输出: {'table_path','points','status'} / 错误: 后端不可用→BackendError；点数不足→insufficient。
    """
    raise NotImplementedError("unimplemented:fn:run_leakage_calibration")


def _capture_leakage_phase(backend, phase, dwell_s):
    """单相位 RX 谱采集（纯采集+统计，不下发标定逻辑）。"""
    raise NotImplementedError("unimplemented:fn:_capture_leakage_phase")


def _compute_coupling_db(off_points, on_points):
    """TX 关/开两相位逐频点差 ΔdB→coupling_db（升序）。"""
    raise NotImplementedError("unimplemented:fn:_compute_coupling_db")


def _write_leakage_table(points, out_path):
    """按 calibrate_leakage session 格式落盘 leakage.json。"""
    raise NotImplementedError("unimplemented:fn:_write_leakage_table")
