"""autodetect_backend 骨架占位：验收 slug=backend_autodetect；行为用例于 fn-implement 阶段填充。"""
from src.autodetect_backend.autodetect_backend import autodetect_backend


def test_backend_autodetect_skeleton():
    assert callable(autodetect_backend)
