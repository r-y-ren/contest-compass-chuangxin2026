"""bridge_to_sitl 骨架占位：验收 slug=sitl_bridge；行为用例于 fn-implement 阶段填充。"""
from src.bridge_to_sitl.bridge_to_sitl import bridge_to_sitl


def test_sitl_bridge_skeleton():
    assert callable(bridge_to_sitl)
