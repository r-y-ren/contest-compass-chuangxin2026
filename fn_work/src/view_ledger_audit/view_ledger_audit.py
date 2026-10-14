"""台账审计页：audit_ledger 上页（done/total 明细+锚点失效清单+注释率）；只读，无任何写清单入口——重写规约与签名意图详见 fn_docs/responsibility.md（R71 view_ledger_audit L0；调用方 mount_console_extensions）。

落地口径（R71）：

- audit_ledger 原样复用（同源口径不重算）：total_entries/done_entries→summary
  done/total/remaining 明细；issues 按 kind 分类清单（dead_anchor=锚点失效清单
  单列，false_negative/ambiguous 保留原样）；comment_ratio 透传（含 target/gap/
  meets_target）；
- 缺省路径仓库根锚定：ledger_path=None → locate_ledger_row.DEFAULT_LEDGER_PATH
  （仓库根/docs/全功能实现清单-技术支持版.md——与 update_ledger/locate_ledger_row
  现有锚定方式同源，cwd 无关）；code_root=None → 仓库根/fn_work/src
  （DEFAULT_LEDGER_PATH 上两级即仓库根，与 scripts/probes/probe_b17 冒烟同落点）；
- 只读：本函数不写任何文件（audit_ledger 自身只读），输出恒带 read_only=True
  与防误写基注——网页运行 ledger=False 现状不变，无任何写清单入口；
- 清单路径不存在/不可读→LedgerError、code_root 不存在→ValueError 原样上抛
  （端点层转 400 错误信息上屏——「AuditError 上屏」口径）。
"""
from pathlib import Path

from src.audit_ledger.audit_ledger import audit_ledger
from src.update_ledger.locate_ledger_row import DEFAULT_LEDGER_PATH

__all__ = ["DEFAULT_AUDIT_LEDGER_PATH", "DEFAULT_AUDIT_CODE_ROOT", "view_ledger_audit"]

#: 缺省台账路径（仓库根锚定——与 update_ledger/locate_ledger_row 同源常量再导出，
#: 便于端点/测试引用同一锚定点）。
DEFAULT_AUDIT_LEDGER_PATH = DEFAULT_LEDGER_PATH

#: 缺省代码树根：DEFAULT_LEDGER_PATH 的 parents[1] 即仓库根→fn_work/src
#: （锚点核验+注释率统计共用，与 probe_b17 冒烟同落点）。
DEFAULT_AUDIT_CODE_ROOT = str(
    Path(DEFAULT_LEDGER_PATH).resolve().parents[1] / "fn_work" / "src"
)

#: 审计页只读基注（演示现场防误写——网页运行 ledger=False 现状不变）。
_READ_ONLY_NOTE = (
    "台账审计为只读——无任何写清单入口（update_ledger 仍走 CLI/ledger=True 路径，"
    "网页运行 ledger=False 现状不变，演示现场防误写）"
)


def view_ledger_audit(ledger_path: str | None = None, code_root: str | None = None) -> dict:
    """台账审计页：audit_ledger 上页（done/total 明细+锚点失效清单+注释率）；只读，无任何写清单入口（详见 fn_docs/responsibility.md 功能块）。

    输入:
        ledger_path: 台账 md 路径|None（缺省 None=仓库根锚定清单
            DEFAULT_LEDGER_PATH——与 update_ledger/locate_ledger_row 同锚定，
            cwd 无关；非空 str 以外形状 ValueError 先拒）。
        code_root: 源码树根目录|None（锚点核验+注释率统计共用；缺省 None=
            仓库根/fn_work/src；非空 str 以外形状 ValueError 先拒）。

    输出:
        审计结果页数据 dict：{'ok': True, 'ledger_path', 'code_root',
        'read_only': True, 'summary': {'done', 'total', 'remaining'},
        'issues': 审计差异清单原样（entry_id/kind/detail——kind ∈
        dead_anchor/false_negative/ambiguous）, 'anchor_failures':
        [kind='dead_anchor' 的锚点失效子清单], 'issue_kinds': {kind: 条数},
        'comment_ratio': 注释率报告（含 target 0.20/gap/meets_target）,
        'clean': issues 为空, 'note': 只读基注}。

    错误:
        LedgerError: 台账文件不存在或不可读（audit_ledger 原样上抛——端点层
            转 400 错误信息上屏）。
        ValueError: ledger_path/code_root 形状不符，或 code_root 不存在/非目录
            （count_comment_ratio 口径透传）。
    """
    if ledger_path is None:
        ledger_path = DEFAULT_AUDIT_LEDGER_PATH
    if not isinstance(ledger_path, str) or not ledger_path.strip():
        raise ValueError(
            f"ledger_path 须为非空 str 路径|None（缺省仓库根锚定清单），"
            f"实际: {ledger_path!r}"
        )
    if code_root is None:
        code_root = DEFAULT_AUDIT_CODE_ROOT
    if not isinstance(code_root, str) or not code_root.strip():
        raise ValueError(
            f"code_root 须为非空 str 目录|None（缺省仓库根 fn_work/src），"
            f"实际: {code_root!r}"
        )

    report = audit_ledger(ledger_path, code_root)  # LedgerError/ValueError 原样上抛

    issues = report["issues"]
    anchor_failures = [item for item in issues if item.get("kind") == "dead_anchor"]
    issue_kinds: dict = {}
    for item in issues:
        issue_kinds[item.get("kind", "?")] = issue_kinds.get(item.get("kind", "?"), 0) + 1

    total = report["total_entries"]
    done = report["done_entries"]
    return {
        "ok": True,
        "ledger_path": ledger_path,
        "code_root": code_root,
        "read_only": True,
        "summary": {"done": done, "total": total, "remaining": total - done},
        "issues": issues,
        "anchor_failures": anchor_failures,
        "issue_kinds": issue_kinds,
        "comment_ratio": report["comment_ratio"],
        "clean": report["clean"],
        "note": _READ_ONLY_NOTE,
    }
