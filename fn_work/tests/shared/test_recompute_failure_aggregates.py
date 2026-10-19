"""scaffold 占位——shared recompute_failure_aggregates（R87 修复轮）实现期启用。"""
from __future__ import annotations

import pytest

from src.shared.recompute_failure_aggregates import recompute_failure_aggregates

pytestmark = pytest.mark.skip(reason="scaffold 占位——实现期启用")


def test_stub_placeholder():
    assert callable(recompute_failure_aggregates)
