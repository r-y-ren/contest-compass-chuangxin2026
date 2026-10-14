"""view_calibration_status 单测（R70）：标定三件（增益标定/自漏标定/全链路补偿）
只读看板字段（在位/【待实测】占位如实/损坏 error 如实）+合成数据演示分支
（建表成功+loader 回读/非单调拒用/样本不足拒用）+只读红线（真实表零写）+section
过滤+端点合约（GET /api/calibration——query section/demo）+页区静态资产零外链。
用例名统一 ``test_calibration_view_`` 前缀（`pytest -k calibration_view` 发现
——R70 核验命令真身：看板字段+合成演示分支）。

被测实现口径见 src/view_calibration_status/view_calibration_status.py 模块
docstring（loader 口径/leakage 轻解析/演示临时目录红线契约）。
"""
import json

import pytest

try:  # 端点合约用——fastapi 缺库环境整组端点用例 skip
    from fastapi.testclient import TestClient

    from src.serve_console.create_console_app import create_console_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

import src.view_calibration_status.view_calibration_status as calib_mod
from src.view_calibration_status.calibration_area import (
    CALIBRATION_CARD_CLASS,
    build_calibration_status_area,
)
from src.view_calibration_status.view_calibration_status import view_calibration_status

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)


@pytest.fixture()
def calib_dir(tmp_path, monkeypatch):
    """看板标定目录指向 tmp（模块全局名 monkeypatch——cwd 无关锚定不受测试污染）。"""
    cdir = tmp_path / "calibrations"
    cdir.mkdir()
    monkeypatch.setattr(calib_mod, "_CALIBRATION_DIR", str(cdir))
    return cdir


def _write_loader_table(cdir, name, entries):
    (cdir / f"{name}.json").write_text(
        json.dumps(entries, ensure_ascii=False), encoding="utf-8"
    )


def _write_leakage_table(cdir, points):
    payload = {
        "kind": "leakage_coupling_table",
        "status": "ok" if len(points) >= 3 else "insufficient",
        "points": len(points),
        "freq_unit": "MHz",
        "coupling_unit": "dB",
        "table": [
            {"freq_mhz": f, "coupling_db": c} for f, c in points
        ],
    }
    (cdir / "leakage.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# ---- 看板字段：三件状态（R70 验收真身） ----


def test_calibration_view_dashboard_fields_all_pieces_present(calib_dir):
    """① 三件在位：gain/link_loss/antenna 经 loader 口径 status=ok 附条目数；
    leakage 轻解析 ok；compensation 件两表嵌套。"""
    _write_loader_table(calib_dir, "gain", {"10": {"power_dbm": -12.0}, "20": {"power_dbm": -6.0}})
    _write_loader_table(calib_dir, "link_loss", {"100": 1.5, "200": 2.0})
    _write_loader_table(calib_dir, "antenna", {"100": 0.8})
    _write_leakage_table(calib_dir, [(100.0, -40.0), (200.0, -42.0), (300.0, -43.0)])

    view = view_calibration_status()
    assert view["ok"] is True and view["read_only"] is True
    assert view["section"] is None
    assert set(view["calibrations"]) == {"gain", "leakage", "compensation"}

    gain = view["calibrations"]["gain"]
    assert gain["status"] == "ok" and gain["present"] is True
    assert gain["placeholder"] is False and gain["entry_count"] == 2
    assert gain["source"].endswith("gain.json")

    leak = view["calibrations"]["leakage"]
    assert leak["status"] == "ok" and leak["entry_count"] == 3
    assert leak["source"].endswith("leakage.json")

    comp = view["calibrations"]["compensation"]
    assert set(comp) == {"link_loss", "antenna"}
    assert comp["link_loss"]["status"] == "ok" and comp["link_loss"]["entry_count"] == 2
    assert comp["antenna"]["status"] == "ok" and comp["antenna"]["entry_count"] == 1


def test_calibration_view_placeholder_honest_when_missing(calib_dir, monkeypatch, tmp_path):
    """② 全缺：四表【待实测】占位如实——status=placeholder、present=False、
    entry_count=0、note 含约定路径（禁止预写数字）；标定目录整体不存在（尚未
    标定）同样按缺失→占位（不误报 error）。"""
    view = view_calibration_status()
    pieces = [
        view["calibrations"]["gain"],
        view["calibrations"]["leakage"],
        view["calibrations"]["compensation"]["link_loss"],
        view["calibrations"]["compensation"]["antenna"],
    ]
    for table in pieces:
        assert table["status"] == "placeholder"
        assert table["present"] is False and table["placeholder"] is True
        assert table["entry_count"] == 0 and table["source"] is None
        assert "【待实测】" in table["note"]
    assert view["calibrations"]["gain"]["note"].endswith("gain.json）")

    monkeypatch.setattr(
        calib_mod, "_CALIBRATION_DIR", str(tmp_path / "no-such-calibrations")
    )
    fresh = view_calibration_status()
    gain = fresh["calibrations"]["gain"]
    assert gain["status"] == "placeholder" and gain["entry_count"] == 0
    assert "标定目录不存在" in gain["note"]


def test_calibration_view_corrupt_and_insufficient_honest(calib_dir):
    """③ 损坏/样本不足如实：坏 JSON→status=error 原文上屏；leakage 表
    insufficient 照实标注（不虚构不静默）。"""
    (calib_dir / "gain.json").write_text("{ 不是 JSON", encoding="utf-8")
    _write_leakage_table(calib_dir, [(100.0, -40.0), (200.0, -42.0)])

    view = view_calibration_status()
    gain = view["calibrations"]["gain"]
    assert gain["status"] == "error" and gain["present"] is True
    assert "load_calibration_table" in gain["note"] or "损坏" in gain["note"]
    leak = view["calibrations"]["leakage"]
    assert leak["status"] == "insufficient" and leak["entry_count"] == 2
    assert "样本不足" in leak["note"]


def test_calibration_view_section_filter_and_shape_errors(calib_dir):
    """④ section 过滤（归一+单件）与形状错 ValueError（未知件/非 bool demo）。"""
    view = view_calibration_status(section="COMPENSATION ")
    assert view["section"] == "compensation"
    assert set(view["calibrations"]) == {"compensation"}

    view = view_calibration_status(section="gain")
    assert set(view["calibrations"]) == {"gain"}

    with pytest.raises(ValueError, match="section"):
        view_calibration_status(section="ghost")
    with pytest.raises(ValueError, match="demo"):
        view_calibration_status(demo="yes")


# ---- 合成数据演示分支 + 只读红线 ----


def _branch(view, name):
    return next(b for b in view["demo"]["branches"] if b["branch"] == name)


def test_calibration_view_demo_branches(calib_dir):
    """⑤ 演示三分支：合成建表成功（points=3+loader 回读 entry_count=3）→
    非单调拒用（CalibrationError 原文+未落盘）→样本不足拒用（原文）。"""
    view = view_calibration_status(demo=True)
    demo = view["demo"]
    assert demo["ok"] is True and demo["kind"] == "synthetic"
    assert demo["wrote_real_table"] is False
    assert len(demo["branches"]) == 3

    ok_branch = _branch(view, "synthetic_build")
    assert ok_branch["ok"] is True and ok_branch["rejected"] is False
    assert ok_branch["result"]["points"] == 3 and ok_branch["result"]["placeholder"] is False
    assert ok_branch["reload"]["entry_count"] == 3

    bad_branch = _branch(view, "non_monotonic_reject")
    assert bad_branch["ok"] is True and bad_branch["rejected"] is True
    assert bad_branch["error"] == "CalibrationError"
    assert "非单调" in bad_branch["message"] and "拒用" in bad_branch["message"]
    assert bad_branch["wrote_table"] is False  # 拒用发生在写表之前

    thin_branch = _branch(view, "insufficient_reject")
    assert thin_branch["ok"] is True and thin_branch["rejected"] is True
    assert "样本不足" in thin_branch["message"]


def test_calibration_view_read_only_real_table_untouched(calib_dir):
    """⑥ 只读红线：真实表零写——在位 gain.json 内容/字节前后一致，看板+演示
    跑完目录无新增文件（演示仅写临时目录）。"""
    real = {"10": {"power_dbm": -12.0}, "20": {"power_dbm": -6.0}}
    (calib_dir / "gain.json").write_text(
        json.dumps(real, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    before = sorted(p.name for p in calib_dir.iterdir())
    raw_before = (calib_dir / "gain.json").read_bytes()

    view = view_calibration_status(demo=True)
    assert view["demo"]["ok"] is True

    assert sorted(p.name for p in calib_dir.iterdir()) == before
    assert (calib_dir / "gain.json").read_bytes() == raw_before


# ---- 端点合约：GET /api/calibration ----


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
def test_calibration_view_endpoint_contract(tmp_path, monkeypatch):
    """⑦ 端点合约：GET /api/calibration→200 看板视图；?demo=1 附演示块；
    ?section=ghost→400 field='section'（错误信息上屏）。"""
    cdir = tmp_path / "calibrations"
    cdir.mkdir()
    monkeypatch.setattr(calib_mod, "_CALIBRATION_DIR", str(cdir))
    client = _client(tmp_path)

    resp = client.get("/api/calibration")
    assert resp.status_code == 200
    view = resp.json()
    assert view["ok"] is True and "demo" not in view
    assert view["calibrations"]["gain"]["status"] == "placeholder"

    resp = client.get("/api/calibration", params={"demo": 1})
    assert resp.status_code == 200
    demo = resp.json()["demo"]
    assert demo["wrote_real_table"] is False and len(demo["branches"]) == 3

    resp = client.get("/api/calibration", params={"section": "ghost"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "section"
    assert "ghost" in resp.json()["detail"]["error"]

    resp = client.get("/api/calibration", params={"section": "gain"})
    assert resp.status_code == 200
    assert set(resp.json()["calibrations"]) == {"gain"}


# ---- 页区静态资产（serve_console instruments 页注入的标定看板区） ----


def test_calibration_view_area_zero_external_links_and_anchors():
    """⑧ 页区资产：零外链（无 http(s):// 字面）+同源 fetch 端点字面
    （/api/calibration）+看板卡 class 锚点+演示按钮（GET 无 POST 写口）。"""
    block = build_calibration_status_area()
    assert "http://" not in block and "https://" not in block
    assert 'id="calibration-status-area"' in block  # 挂载区块锚点
    assert "/api/calibration" in block  # 同源相对路径 fetch
    assert CALIBRATION_CARD_CLASS in block  # 看板卡 class 锚点
    assert "合成数据演示" in block and "只读" in block
    assert "method: 'POST'" not in block and "method: 'PUT'" not in block  # 无写口
