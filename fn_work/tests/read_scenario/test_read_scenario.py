"""scaffold 占位——read_scenario（R87 修复轮）实现期启用。"""
from __future__ import annotations

import pytest

from src.read_scenario.read_scenario import read_scenario

pytestmark = pytest.mark.skip(reason="scaffold 占位——实现期启用")


def test_stub_placeholder():
    assert callable(read_scenario)
