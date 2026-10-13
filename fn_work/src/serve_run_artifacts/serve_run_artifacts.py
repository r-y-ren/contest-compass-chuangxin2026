"""运行产物服务端点：report（markdown 渲染 HTML）/plots（PNG）/files（原始数据下载）+溯源结论回显+路径穿越拒绝——重写规约与签名意图详见 fn_docs/responsibility.md。

本文件为 fn-scaffold 骨架桩：签名已定，实现由 fn-implement 对应批次填充。
"""


def serve_run_artifacts(run_root: str, run_id: str, kind: str, name: str | None = None) -> dict:
    """运行产物服务端点：report（markdown 渲染 HTML）/plots（PNG）/files（原始数据下载）+溯源结论回显+路径穿越拒绝（详见 fn_docs/responsibility.md 功能块）。"""
    raise NotImplementedError("unimplemented:fn:serve_run_artifacts")
