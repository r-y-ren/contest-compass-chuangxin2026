"""scaffold 占位——shared build_recording_facts（R87 修复轮）实现期启用。"""
from __future__ import annotations

import pytest

from src.shared.build_recording_facts import build_recording_facts

pytestmark = pytest.mark.skip(reason="scaffold 占位——实现期启用")


def test_stub_placeholder():
    assert callable(build_recording_facts)
