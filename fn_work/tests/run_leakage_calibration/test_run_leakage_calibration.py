"""scaffold 占位——run_leakage_calibration（R87 修复轮）实现期启用。"""
from __future__ import annotations

import pytest

from src.run_leakage_calibration.run_leakage_calibration import run_leakage_calibration

pytestmark = pytest.mark.skip(reason="scaffold 占位——实现期启用")


def test_stub_placeholder():
    assert callable(run_leakage_calibration)
