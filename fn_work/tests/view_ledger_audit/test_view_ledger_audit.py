"""view_ledger_audit 单测（R71）：audit_ledger 上页字段（done/total 明细+锚点失效
清单+注释率）+缺省路径仓库根锚定（对齐 update_ledger/locate_ledger_row）+只读
（无任何写清单入口，清单字节前后一致）+LedgerError/ValueError 上抛口径+端点合约
（GET /api/ledger/audit）+页区静态资产零外链。用例名统一 ``test_ledger_audit_view_``
前缀（`pytest -k ledger_audit_view` 发现——R71 核验命令真身：审计结果字段断言）。

B29 对抗中1低2 转 B30 随批①②补测：⑧⑨ 仓库根 realpath 围栏（拒 /etc/passwd、
code_root=/、仓外 tmp 清单；放行仓内与 ../ 归一后仓内路径）、⑩ 空白 ledger_path
→field='ledger_path'（错标修正）、⑪ /api/calibration demo 域错→field='demo'
（映射处姊妹修正）。

被测实现口径见 src/view_ledger_audit/view_ledger_audit.py 模块 docstring
（audit_ledger 同源复用/仓库根锚定/只读基注契约）。
"""
from pathlib import Path

import pytest

try:  # 端点合约用——fastapi 缺库环境整组端点用例 skip
    from fastapi.testclient import TestClient

    from src.serve_console.create_console_app import create_console_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

from src.update_ledger.locate_ledger_row import (
    DEFAULT_LEDGER_PATH,
    LedgerError,
)
from src.view_ledger_audit.audit_area import (
    AUDIT_ISSUE_CLASS,
    build_ledger_audit_area,
)
from src.view_ledger_audit.view_ledger_audit import (
    DEFAULT_AUDIT_CODE_ROOT,
    DEFAULT_AUDIT_LEDGER_PATH,
    view_ledger_audit,
)

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LEDGER = REPO_ROOT / "docs" / "全功能实现清单-技术支持版.md"


def _make_code_root(tmp_path: Path) -> str:
    """样板代码树：锚点核验以内容命中（locate_ledger_row/count_comment_ratio）。"""
    pkg = tmp_path / "src"
    pkg.mkdir(exist_ok=True)
    (pkg / "ledger_core.py").write_text(
        "# 注释行\ndef locate_ledger_row(entry_id, ledger_path):\n    return {}\n",
        encoding="utf-8",
    )
    (pkg / "count_comment_ratio.py").write_text(
        "def count_comment_ratio(root):\n    return {}\n", encoding="utf-8"
    )
    return str(tmp_path)


def _write_ledger(tmp_path: Path, text: str) -> str:
    p = tmp_path / "ledger.md"
    p.write_text(text, encoding="utf-8")
    return str(p)


_CLEAN_LEDGER = """# 台账样板
| 编号 | 功能 | 状态 | 备注 |
| --- | --- | --- | --- |
| A1 | 定位 | ✅ 10-11 fn(locate_ledger_row) commit 111aaa | r1 |
| A2 | 注释率 | ✅ 10-11 fn(count_comment_ratio) | r2 |
| A3 | 未完成 | 待开 | r3 |
"""


# ---- 审计结果字段（R71 验收真身） ----


def test_ledger_audit_view_clean_report_fields(tmp_path):
    """① 干净台账：summary done/total/remaining 明细+空锚点失效清单+注释率
    （target/gap/meets_target）+read_only 基注齐备。"""
    ledger = _write_ledger(tmp_path, _CLEAN_LEDGER)
    code_root = _make_code_root(tmp_path)

    view = view_ledger_audit(ledger, code_root)
    assert view["ok"] is True and view["read_only"] is True
    assert view["ledger_path"] == ledger and view["code_root"] == code_root
    assert view["summary"] == {"done": 2, "total": 3, "remaining": 1}
    assert view["anchor_failures"] == [] and view["issues"] == []
    assert view["issue_kinds"] == {} and view["clean"] is True
    ratio = view["comment_ratio"]
    assert ratio["target"] == 0.2 and "gap" in ratio and "meets_target" in ratio
    assert "只读" in view["note"] and "写清单入口" in view["note"]


def test_ledger_audit_view_dead_anchor_listing(tmp_path):
    """② 锚点失效清单：✅ 锚点函数在代码树不存在→anchor_failures 单列（entry_id/
    kind/detail），issue_kinds 计数同源。"""
    ledger = _write_ledger(
        tmp_path,
        _CLEAN_LEDGER.replace(
            "fn(count_comment_ratio)",
            "fn(ghost_function_missing)",
        ),
    )
    code_root = _make_code_root(tmp_path)

    view = view_ledger_audit(ledger, code_root)
    assert view["clean"] is False
    assert len(view["anchor_failures"]) == 1
    item = view["anchor_failures"][0]
    assert item["entry_id"] == "A2" and item["kind"] == "dead_anchor"
    assert "ghost_function_missing" in item["detail"]
    assert view["issue_kinds"] == {"dead_anchor": 1}
    assert view["anchor_failures"][0] in view["issues"]  # issues 原样保留


def test_ledger_audit_view_default_paths_repo_anchored():
    """③ 缺省路径仓库根锚定：ledger_path=locate_ledger_row.DEFAULT_LEDGER_PATH、
    code_root=仓库根/fn_work/src（cwd 无关）；真清单冒烟 total=100 结构不变量。"""
    view = view_ledger_audit()
    assert view["ledger_path"] == DEFAULT_AUDIT_LEDGER_PATH == DEFAULT_LEDGER_PATH
    assert Path(view["ledger_path"]).samefile(REAL_LEDGER)
    assert view["code_root"] == DEFAULT_AUDIT_CODE_ROOT
    assert DEFAULT_AUDIT_CODE_ROOT.endswith("fn_work/src")
    assert Path(DEFAULT_AUDIT_CODE_ROOT).is_dir()
    # 真清单冒烟（同 tests/audit_ledger 真身用例口径——只锁结构不变量）
    assert view["summary"]["total"] == 100
    assert 0 <= view["summary"]["done"] <= 100
    assert view["summary"]["remaining"] == 100 - view["summary"]["done"]
    assert isinstance(view["comment_ratio"]["ratio"], float)


def test_ledger_audit_view_missing_ledger_and_shape_errors(tmp_path):
    """④ 错误口径：清单不存在→LedgerError 原样上抛；ledger_path/code_root
    形状错→ValueError 先拒。"""
    with pytest.raises(LedgerError, match="不存在或不可读"):
        view_ledger_audit(str(tmp_path / "ghost.md"), _make_code_root(tmp_path))
    with pytest.raises(ValueError, match="ledger_path"):
        view_ledger_audit("  ", "x")
    with pytest.raises(ValueError, match="code_root"):
        view_ledger_audit(_write_ledger(tmp_path, _CLEAN_LEDGER), "  ")


def test_ledger_audit_view_read_only_ledger_bytes_unchanged(tmp_path):
    """⑤ 只读：审计前后清单字节一致（无任何写清单入口——网页运行 ledger=False
    现状不变的函数级侧写）。"""
    ledger = _write_ledger(tmp_path, _CLEAN_LEDGER)
    raw_before = Path(ledger).read_bytes()

    view_ledger_audit(ledger, _make_code_root(tmp_path))
    view_ledger_audit(ledger, _make_code_root(tmp_path))  # 重复审计亦不写

    assert Path(ledger).read_bytes() == raw_before


# ---- 端点合约：GET /api/ledger/audit ----


def _client(tmp_path):
    """装配真 app（deps 最小五键——端点注册经 create_console_app 内接线）。"""
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path),
        "report_root": str(tmp_path / "reports"),
        "static_pages": {},
    }
    return TestClient(create_console_app(deps))


@needs_fastapi
def test_ledger_audit_view_endpoint_contract(tmp_path):
    """⑥ 端点合约：GET /api/ledger/audit（query ledger_path/code_root）→200
    审计页数据；清单不存在→400 field='ledger_path'（AuditError 上屏口径）。

    B30 随批①围栏后端点只收仓内路径：200 例改用真清单+真代码树（仓库根锚定
    同 test③ 真身口径——total=100 结构不变量）；错误例均落在仓库根内。"""
    client = _client(tmp_path)

    # 仓内 200：真清单+真代码树（与缺省锚定同一对象——围栏放行）
    resp = client.get(
        "/api/ledger/audit",
        params={
            "ledger_path": str(REAL_LEDGER),
            "code_root": DEFAULT_AUDIT_CODE_ROOT,
        },
    )
    assert resp.status_code == 200
    view = resp.json()
    assert view["ok"] is True and view["read_only"] is True
    assert view["summary"]["total"] == 100

    # 仓内不存在清单：过围栏后 LedgerError→400 field='ledger_path'
    resp = client.get(
        "/api/ledger/audit",
        params={
            "ledger_path": str(REPO_ROOT / "docs" / "ghost-ledger.md"),
            "code_root": DEFAULT_AUDIT_CODE_ROOT,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "ledger_path"
    assert "不存在或不可读" in resp.json()["detail"]["error"]

    # 仓内不存在代码树：过围栏后 count_comment_ratio ValueError→400 field='code_root'
    resp = client.get(
        "/api/ledger/audit",
        params={
            "ledger_path": str(REAL_LEDGER),
            "code_root": str(REPO_ROOT / "fn_work" / "ghost-code-root"),
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "code_root"


# ---- B29 对抗中1低2 转 B30 随批①②：仓库根围栏+field 错标修正 ----


@needs_fastapi
def test_ledger_audit_view_repo_fence_rejects_outside_paths(tmp_path):
    """⑧ 围栏拒界（B30 随批①，realpath 对齐 replay 口径）：ledger_path=/etc/
    passwd、code_root=/（全盘扫 DoS 面）、tmp 仓外清单——一律 400 带指错
    field=对应字段；/etc/passwd 此前经审计读回 200 的面在此收口。"""
    client = _client(tmp_path)

    resp = client.get("/api/ledger/audit", params={"ledger_path": "/etc/passwd"})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["field"] == "ledger_path" and "越界" in detail["error"]

    resp = client.get("/api/ledger/audit", params={"code_root": "/"})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["field"] == "code_root" and "越界" in detail["error"]

    # 仓外真实存在的清单（tmp 样板）同样拦下——不因「文件存在可读」放行
    outside = _write_ledger(tmp_path, _CLEAN_LEDGER)
    resp = client.get("/api/ledger/audit", params={"ledger_path": outside})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "ledger_path"


@needs_fastapi
def test_ledger_audit_view_repo_fence_allows_inside_paths(tmp_path):
    """⑨ 围栏放行（B30 随批①）：仓内绝对路径/带 ../ 归一后仍仓内的路径→
    200（realpath 归一口径——软链/穿越链解析后落仓库根内即放行）。"""
    client = _client(tmp_path)
    inside_via_parent = str(
        REPO_ROOT / "docs" / ".." / "docs" / REAL_LEDGER.name
    )
    resp = client.get(
        "/api/ledger/audit", params={"ledger_path": inside_via_parent}
    )
    assert resp.status_code == 200
    assert resp.json()["summary"]["total"] == 100


@needs_fastapi
def test_ledger_audit_view_blank_field_mislabel_fixed(tmp_path):
    """⑩ field 错标修正（B30 随批②）：空白 ledger_path→ValueError 消息前缀
    分流 field='ledger_path'（此前一律错标 code_root）；空白 code_root 仍
    field='code_root'。"""
    client = _client(tmp_path)

    resp = client.get("/api/ledger/audit", params={"ledger_path": "  "})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "ledger_path"
    assert "ledger_path" in resp.json()["detail"]["error"]

    resp = client.get("/api/ledger/audit", params={"code_root": "  "})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "code_root"


@needs_fastapi
def test_ledger_audit_view_calibration_demo_field_mislabel_fixed(tmp_path, monkeypatch):
    """⑪ 同批②姊妹修正（R70 /api/calibration 映射处）：demo 非 bool 的
    ValueError→field='demo'（不再错标 section）；section 未知仍 field='section'。

    HTTP 层 bool 形参由 FastAPI 先行 422 拦下，此处 monkeypatch 服务函数
    直发两条域错——验证端点映射的前缀分流分支两向。"""
    from src.view_calibration_status import view_calibration_status as vcs_module

    def _fake(section, demo):  # 与真实签名同形（section, demo）——两域错分流
        if section is not None:
            raise ValueError(
                f"section 必须为 gain|leakage|compensation 之一或 None，实际: {section!r}"
            )
        raise ValueError("demo 必须为 bool（合成数据演示触发），实际: 'yes'")

    monkeypatch.setattr(vcs_module, "view_calibration_status", _fake)
    client = _client(tmp_path)
    resp = client.get("/api/calibration")
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "demo"

    resp = client.get("/api/calibration", params={"section": "ghost"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "section"


# ---- 页区静态资产（serve_console ledger 页注入的审计页区） ----


def test_ledger_audit_view_area_zero_external_links_and_anchors():
    """⑦ 页区资产：零外链（无 http(s):// 字面）+同源 fetch 端点字面
    （/api/ledger/audit）+两挂载点（audit-report/ledger-detail）+差异清单
    class 锚点（GET 无 POST 写口）。"""
    block = build_ledger_audit_area()
    assert "http://" not in block and "https://" not in block
    assert 'id="ledger-audit-area"' in block  # 挂载区块锚点
    assert "/api/ledger/audit" in block  # 同源相对路径 fetch
    assert "ledger-detail" in block and "audit-report" in block  # 两挂载点
    assert AUDIT_ISSUE_CLASS in block  # 差异清单条目 class 锚点
    assert "只读" in block and "锚点失效" in block
    assert "method: 'POST'" not in block and "method: 'PUT'" not in block  # 无写口
