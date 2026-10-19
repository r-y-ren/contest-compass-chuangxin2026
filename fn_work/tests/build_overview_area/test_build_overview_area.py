"""scaffold 占位——build_overview_area（R87 修复轮）实现期启用。"""
from __future__ import annotations

import pytest

from src.build_overview_area.build_overview_area import build_overview_area

pytestmark = pytest.mark.skip(reason="scaffold 占位——实现期启用")


def test_stub_placeholder():
    assert callable(build_overview_area)
