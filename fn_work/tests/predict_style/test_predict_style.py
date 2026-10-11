"""predict_style 骨架占位：验收 slug=infer_service；行为用例于 fn-implement 阶段填充。"""
from src.predict_style.predict_style import predict_style


def test_infer_service_skeleton():
    assert callable(predict_style)
