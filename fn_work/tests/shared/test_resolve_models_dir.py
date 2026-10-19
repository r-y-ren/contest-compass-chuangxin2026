"""scaffold 占位——shared resolve_models_dir（R87 修复轮）实现期启用。"""
from __future__ import annotations

import pytest

from src.shared.resolve_models_dir import resolve_models_dir

pytestmark = pytest.mark.skip(reason="scaffold 占位——实现期启用")


def test_stub_placeholder():
    assert callable(resolve_models_dir)
