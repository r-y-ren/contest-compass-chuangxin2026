"""lookup_jsr 骨架占位：验收 slug=jsr_calibration；行为用例于 fn-implement 阶段填充。"""
from src.lookup_jsr.lookup_jsr import lookup_jsr


def test_jsr_calibration_skeleton():
    assert callable(lookup_jsr)
