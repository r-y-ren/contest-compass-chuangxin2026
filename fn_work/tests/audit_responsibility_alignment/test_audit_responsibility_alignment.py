"""audit_responsibility_alignment 单测（R75）：真文档全过（对账项 8 件全 registered
+代码锚点动态实测）+构造漏登副本逐项检出（旧块补注删除/键数漂移/域二十缺口/
快速通道缺一处/资产件缺名）+文档或锚点缺失上抛。用例名统一
``test_responsibility_alignment_`` 前缀（`pytest -k responsibility_alignment`
发现——R75 核验命令真身）。

被测实现口径见 src/audit_responsibility_alignment/audit_responsibility_alignment.py
模块 docstring（七对账项+代码锚点交叉；只读不写，漏登不抛、缺文件上抛）。
"""
from pathlib import Path

import pytest

from src.audit_responsibility_alignment.audit_responsibility_alignment import (
    audit_responsibility_alignment,
)

#: 真文档/真代码根锚点（tests/audit_responsibility_alignment/ → 仓库根）。
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_DOC = _REPO_ROOT / "fn_docs" / "responsibility.md"
_REAL_CODE_ROOT = _REPO_ROOT / "fn_work"

#: 全量对账项 id（registered 完备性断言锚）。
_ALL_ITEMS = [
    "run_scenario_public_entry",
    "serve_console_dual_payload",
    "scenario_whitelist_keys",
    "r48_page_elements_enum",
    "domain_twenty_new_blocks",
    "fast_track_change_notes",
    "asset_area_inventory",
    "code_anchor_run_scenario_export",
]


def _copy_doc(tmp_path, mutate=None):
    """真文档副本落 tmp（可选逐行变换）——构造漏登/漂移场景（不动真文档）。"""
    lines = _REAL_DOC.read_text(encoding="utf-8").splitlines(keepends=True)
    if mutate is not None:
        lines = mutate(lines)
    path = tmp_path / "responsibility.md"
    path.write_text("".join(lines), encoding="utf-8")
    return str(path)


def test_responsibility_alignment_real_doc_all_registered():
    """① 真文档+真代码根：对账项 8 件全 registered、missing 空、ok=True；
    代码锚点动态实测——_KNOWN_KEYS 键数与 run_demo `__all__` 导出真值一致。"""
    result = audit_responsibility_alignment(str(_REAL_DOC), str(_REAL_CODE_ROOT))
    assert result["ok"] is True
    assert result["missing"] == []
    assert result["registered"] == _ALL_ITEMS
    anchors = result["code_anchors"]
    # 键数锚=代码实测（与直接 import 同源对拍，防对账函数自带假数）；
    # 2026-10-17 R95：_KNOWN_KEYS 增顶层键 tx_gain_db（双白名单改造点①）→ 63→64。
    from src.load_scenario.validate_scenario_schema import _KNOWN_KEYS

    assert anchors["known_keys_len"] == len(_KNOWN_KEYS) == 64
    assert anchors["whitelist_keys_needle"] == f"{len(_KNOWN_KEYS)} 键"
    assert anchors["run_scenario_exported"] is True
    assert "run_scenario" in anchors["run_demo___all__"]
    assert anchors["domain_blocks_present"] == 20
    assert anchors["fast_track_notes"] >= 6
    assert anchors["doc_path"] == str(_REAL_DOC.resolve())


def test_responsibility_alignment_stripped_r75_notes_detected(tmp_path):
    """② 构造漏登副本：剥掉全部 R75 演进补注行（模拟"改了代码不回文档"）→
    四旧块对账项逐项检出（R44 入口/R47 双载荷/R1 键域/R48 元素枚举）。"""
    doc = _copy_doc(
        tmp_path,
        lambda lines: [
            line for line in lines if "演进补注（2026-10-14，R75）" not in line
        ],
    )
    result = audit_responsibility_alignment(doc, str(_REAL_CODE_ROOT))
    assert result["ok"] is False
    joined = "\n".join(result["missing"])
    for item in (
        "run_scenario_public_entry",
        "serve_console_dual_payload",
        "scenario_whitelist_keys",
        "r48_page_elements_enum",
    ):
        assert item in joined
    # 漏登不抛：registered 仍有未受影响的项（域二十/快速通道/资产件/代码锚点）
    assert "domain_twenty_new_blocks" in result["registered"]
    assert "code_anchor_run_scenario_export" in result["registered"]


def test_responsibility_alignment_whitelist_count_drift_detected(tmp_path):
    """③ 键数漂移：副本把「64 键」改口「999 键」（模拟代码键数演进后文档
    静态数失配）→ scenario_whitelist_keys 检出；键数锚仍报代码真值 64。
    （2026-10-17 R95：tx_gain_db 顶层键入册 _KNOWN_KEYS，代码真值 63→64，
    漂移针与锚同步更新。）"""
    doc = _copy_doc(tmp_path, lambda lines: [line.replace("64 键", "999 键") for line in lines])
    result = audit_responsibility_alignment(doc, str(_REAL_CODE_ROOT))
    assert result["ok"] is False
    assert any("scenario_whitelist_keys" in item for item in result["missing"])
    assert result["code_anchors"]["whitelist_keys_needle"] == "64 键"
    assert result["code_anchors"]["known_keys_len"] == 64


def test_responsibility_alignment_domain_gap_and_assets_detected(tmp_path):
    """④ 域二十块缺口+资产件缺名：副本抽走 R73 块头（19/20 块在册）并删
    资产件清单注行→domain_twenty_new_blocks 与 asset_area_inventory 双检出。"""

    def mutate(lines):
        return [
            line
            for line in lines
            if "## 功能块 demo_rl_policy ← R73" not in line  # 抽一块头（降格为正文）
            and "资产件清单注" not in line
        ]

    doc = _copy_doc(tmp_path, mutate)
    result = audit_responsibility_alignment(doc, str(_REAL_CODE_ROOT))
    assert result["ok"] is False
    joined = "\n".join(result["missing"])
    assert "domain_twenty_new_blocks" in joined and "19" in joined
    assert result["code_anchors"]["domain_blocks_present"] == 19
    assert "asset_area_inventory" in joined


def test_responsibility_alignment_fast_track_note_shortfall_detected(tmp_path):
    """⑤ 快速通道短缺检出：把足量「改造点·快速通道：」降格为无冒号引用，
    使计数降到 _FAST_TRACK_MIN 之下 → fast_track_change_notes 检出。
    降格数按真文档实况动态计算（文档合法增长后 6→5 硬编码会失效——R90 B43 红#1 修复）。"""
    from src.audit_responsibility_alignment.audit_responsibility_alignment import _FAST_TRACK_MIN
    doc_text = _REAL_DOC.read_text(encoding="utf-8")
    total = doc_text.count("改造点·快速通道：")
    assert total >= _FAST_TRACK_MIN, "真文档快速通道说明数应不低于下限"
    to_drop = total - _FAST_TRACK_MIN + 1  # 降到 下限-1，恰好触发短缺
    mutated = doc_text
    for _ in range(to_drop):
        mutated = mutated.replace("改造点·快速通道：", "改造点·快速通道", 1)
    doc_path = tmp_path / "responsibility.md"
    doc_path.write_text(mutated, encoding="utf-8")
    result = audit_responsibility_alignment(str(doc_path), str(_REAL_CODE_ROOT))
    assert result["ok"] is False
    assert result["code_anchors"]["fast_track_notes"] == _FAST_TRACK_MIN - 1
    assert any("fast_track_change_notes" in item for item in result["missing"])


def test_responsibility_alignment_missing_doc_or_anchor_raises(tmp_path):
    """⑥ 对账失败上抛口径：责任文档缺失/代码锚点文件缺失→FileNotFoundError
    （区别于漏登——缺文件无从对账）；真文档字节不被改写（只读自证）。"""
    before = _REAL_DOC.read_bytes()
    with pytest.raises(FileNotFoundError, match="责任文档"):
        audit_responsibility_alignment(str(tmp_path / "ghost.md"), str(_REAL_CODE_ROOT))
    doc = _copy_doc(tmp_path)  # 文档在，代码根指向空目录（锚点文件缺）
    empty_root = tmp_path / "empty_root"
    empty_root.mkdir()
    with pytest.raises(FileNotFoundError, match="锚点文件"):
        audit_responsibility_alignment(doc, str(empty_root))
    assert _REAL_DOC.read_bytes() == before  # 只读不写：真文档原样
