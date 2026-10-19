"""scaffold 占位——guard_scenario_update（R87 修复轮）实现期启用。"""
from __future__ import annotations

import pytest

from src.guard_scenario_update.guard_scenario_update import guard_scenario_update

pytestmark = pytest.mark.skip(reason="scaffold 占位——实现期启用")


def test_stub_placeholder():
    assert callable(guard_scenario_update)
