"""台账审计页：audit_ledger 上页（done/total 明细+锚点失效清单+注释率）；只读，无任何写清单入口——重写规约与签名意图详见 fn_docs/responsibility.md。

本文件为 fn-scaffold 骨架桩：签名已定，实现由 fn-implement 对应批次填充。
"""


def view_ledger_audit(ledger_path: str | None = None, code_root: str | None = None) -> dict:
    """台账审计页：audit_ledger 上页（done/total 明细+锚点失效清单+注释率）；只读，无任何写清单入口（详见 fn_docs/responsibility.md 功能块）。"""
    raise NotImplementedError("unimplemented:fn:view_ledger_audit")
