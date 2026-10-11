"""normalize_kpi 骨架占位：验收 slug=kpi_model；行为用例于 fn-implement 阶段填充。"""
from src.normalize_kpi.normalize_kpi import normalize_kpi


def test_kpi_model_skeleton():
    assert callable(normalize_kpi)
