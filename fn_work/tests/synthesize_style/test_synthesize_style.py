"""synthesize_style 骨架占位：验收 slug=styles_synth；行为用例于 fn-implement 阶段填充。"""
from src.synthesize_style.synthesize_style import synthesize_style


def test_styles_synth_skeleton():
    assert callable(synthesize_style)
