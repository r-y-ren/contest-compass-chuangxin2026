"""calibrate_leakage 骨架占位：验收 slug=leak_calibration；行为用例于 fn-implement 阶段填充。"""
from src.calibrate_leakage.calibrate_leakage import calibrate_leakage


def test_leak_calibration_skeleton():
    assert callable(calibrate_leakage)
