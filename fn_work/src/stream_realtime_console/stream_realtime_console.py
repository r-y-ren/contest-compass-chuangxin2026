"""实时流接通：运行期三路帧（KPI/监测谱/事件）经 push_realtime_kpi 推入操控台 /ws hub+延迟统计入结果 JSON——重写规约与签名意图详见 fn_docs/responsibility.md。

本文件为 fn-scaffold 骨架桩：签名已定，实现由 fn-implement 对应批次填充。
"""


def stream_realtime_console(run_ctx: dict, hub: dict) -> dict:
    """实时流接通：运行期三路帧（KPI/监测谱/事件）经 push_realtime_kpi 推入操控台 /ws hub+延迟统计入结果 JSON（详见 fn_docs/responsibility.md 功能块）。"""
    raise NotImplementedError("unimplemented:fn:stream_realtime_console")
