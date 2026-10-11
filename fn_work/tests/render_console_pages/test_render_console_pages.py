"""render_console_pages 骨架占位：验收 slug=console_ui；行为用例于 fn-implement 阶段填充。"""
from src.render_console_pages.render_console_pages import render_console_pages


def test_console_ui_skeleton():
    assert callable(render_console_pages)
