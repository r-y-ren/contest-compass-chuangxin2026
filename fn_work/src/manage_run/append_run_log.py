"""结构化日志行追加到 run.log——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations



def append_run_log(run_dir: str, level: str, message: str, context: dict | None = None) -> None:
    """结构化日志行追加到 run.log。"""
    raise NotImplementedError("unimplemented:fn:append_run_log")
