"""总览页区块（R104）——重写规约与签名意图详见 fn_docs/responsibility.md 域二十六。"""
from __future__ import annotations

__all__ = ["build_overview_area"]


def build_overview_area():
    """生成总览页四块（后端/时钟/清单完成度/近期运行）的 HTML+JS 区块。"""
    raise NotImplementedError("unimplemented:fn:build_overview_area")


def _render_backend_block():
    """后端链路状态块（GET /api/status/backend）。"""
    raise NotImplementedError("unimplemented:fn:_render_backend_block")


def _render_clock_block():
    """时钟状态块（GET /api/status/clock）。"""
    raise NotImplementedError("unimplemented:fn:_render_clock_block")


def _render_ledger_block():
    """清单完成度块（GET /api/ledger）。"""
    raise NotImplementedError("unimplemented:fn:_render_ledger_block")


def _render_recent_runs_block():
    """近期运行块（GET /api/runs/summaries）。"""
    raise NotImplementedError("unimplemented:fn:_render_recent_runs_block")
