"""scaffold 占位——get_status_backend（R87 修复轮）实现期启用。"""
from __future__ import annotations

import pytest

from src.get_status_backend.get_status_backend import get_status_backend

pytestmark = pytest.mark.skip(reason="scaffold 占位——实现期启用")


def test_stub_placeholder():
    assert callable(get_status_backend)
