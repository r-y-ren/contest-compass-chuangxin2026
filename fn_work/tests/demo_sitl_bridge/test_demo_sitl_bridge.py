"""demo_sitl_bridge 单测（R72）：dry_run 映射预览（台阶提取+map_per_to_injection
独立复算一致）+SITL 不在位跳过标注（不报错不阻塞）+无 KPI 数据/形状错拒绝
+端点合约（POST /api/demo/sitl）+页区静态资产零外链。用例名统一
``test_sitl_view_`` 前缀（`pytest -k sitl_view` 发现——R72 核验命令真身：
dry_run 映射断言+缺席分支）。

被测实现口径见 src/demo_sitl_bridge/demo_sitl_bridge.py 模块 docstring
（build_curve_frames 帧A 台阶提取/bridge_to_sitl dry_run 语义/Sitl 不在位标注）。
"""
import json
import os
import sys

import pytest

try:  # 端点合约用——fastapi 缺库环境整组端点用例 skip
    from fastapi.testclient import TestClient

    from src.serve_console.create_console_app import create_console_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

from src.bridge_to_sitl.map_per_to_injection import map_per_to_injection
from src.demo_sitl_bridge.demo_sitl_bridge import demo_sitl_bridge
from src.demo_sitl_bridge.sitl_area import SITL_INJECTION_CLASS, build_sitl_bridge_area

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)


def _make_run(root: str, run_id: str = "run-001") -> "tuple[str, str]":
    """两档 power_step+两窗 judge_per 样板的运行目录（帧A：−5dB→0.10、0dB→0.70）。"""
    run_dir = os.path.join(root, run_id)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "events.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {"type": "power_step", "step": 0, "target_db": -5.0, "ts": 100}
            )
            + "\n"
        )
        fh.write(
            json.dumps({"type": "power_step", "step": 1, "target_db": 0.0, "ts": 500})
            + "\n"
        )
    with open(os.path.join(run_dir, "kpi.csv"), "w", encoding="utf-8") as fh:
        fh.write("timestamp_ms,link,source,per,judge_per,rssi_dbm,retries,per_note\n")
        fh.write("150,sim,sim,0.05,0.05,-60,0,\n")
        fh.write("250,sim,sim,0.15,0.15,-60,0,\n")
        fh.write("600,sim,sim,0.6,0.6,-60,0,\n")
        fh.write("700,sim,sim,0.8,0.8,-60,0,\n")
    return run_dir, root


# ---- dry_run 映射预览（R72 验收真身①） ----


def test_sitl_view_dry_run_mapping_preview(tmp_path):
    """① dry_run 映射预览：帧A 提取台阶（窗均 judge_per）→injections 与
    map_per_to_injection 独立复算一致；bridge 返回 dry_run 口径。"""
    _make_run(str(tmp_path))
    view = demo_sitl_bridge("run-001", str(tmp_path))
    assert view["ok"] is True and view["read_only"] is True
    assert view["steps"] == [
        {"per": 0.1, "level_db": -5.0},
        {"per": 0.7, "level_db": 0.0},
    ]
    assert view["n_steps"] == 2
    bridge = view["bridge"]
    assert bridge["bridged"] is True and bridge["dry_run"] is True
    assert view["injections"] == map_per_to_injection(view["steps"], {})
    # 末档 per=0.7<0.95 未饱和、时延=5+2*|0-(-5)|=15（缺省映射参数口径）
    assert view["injections"][-1]["packet_loss"] == pytest.approx(0.7)
    assert view["injections"][-1]["latency_ms"] == pytest.approx(15.0)
    assert view["injections"][-1]["saturated"] is False
    assert "dry_run" in view["note"] and "只读" in view["note"]


def test_sitl_view_deterministic_and_no_kpi_runs_rejected(tmp_path):
    """② 无 KPI 数据拒绝：目录不存在/无 power_step 事件/全窗无判据样本→
    ValueError 提示选择其他运行；run_id/report_root 形状错先拒。"""
    _make_run(str(tmp_path))
    with pytest.raises(ValueError, match="请选择其他运行"):
        demo_sitl_bridge("ghost", str(tmp_path))
    empty = os.path.join(str(tmp_path), "run-empty")
    os.makedirs(empty)
    with pytest.raises(ValueError, match="无 KPI 数据"):
        demo_sitl_bridge("run-empty", str(tmp_path))  # 无 events/kpi 文件
    with open(os.path.join(empty, "kpi.csv"), "w", encoding="utf-8") as fh:
        fh.write("timestamp_ms,link,source,per,judge_per,rssi_dbm,retries,per_note\n")
        fh.write("150,sim,sim,0.05,0.05,-60,0,\n")  # 有 KPI 行但无台阶事件
    with pytest.raises(ValueError, match="无 KPI 数据"):
        demo_sitl_bridge("run-empty", str(tmp_path))
    with pytest.raises(ValueError, match="run_id"):
        demo_sitl_bridge("  ", str(tmp_path))
    with pytest.raises(ValueError, match="report_root"):
        demo_sitl_bridge("run-001", "")


# ---- SITL 不在位跳过标注（R72 验收真身②——R53 口径） ----


def test_sitl_view_sitl_absent_skip_annotation_not_error(tmp_path, monkeypatch):
    """③ SITL 不在位：pymavlink 缺（sys.modules 置 None）→sitl_available=False
    +skip_note 跳过标注，dry_run 预览照常产出（不报错不阻塞）。"""
    _make_run(str(tmp_path))
    monkeypatch.setitem(sys.modules, "pymavlink", None)
    view = demo_sitl_bridge("run-001", str(tmp_path))
    assert view["ok"] is True
    assert view["sitl_available"] is False
    assert view["skip_note"] is not None
    assert "SITL 不在位" in view["skip_note"] and "跳过" in view["skip_note"]
    assert "pip install pymavlink" in view["skip_note"]
    assert view["bridge"]["bridged"] is True and view["bridge"]["dry_run"] is True
    assert len(view["injections"]) == 2  # 预览不因缺席丢失


def test_sitl_view_sitl_present_no_skip_note(tmp_path, monkeypatch):
    """④ SITL 库在位（注入假模块）→sitl_available=True、skip_note=None（不
    虚构跳过——预览与真连可用性两口径分明）。"""
    _make_run(str(tmp_path))

    class _FakeMav:  # 最小假模块：只探 import 在位性，绝不真连
        pass

    monkeypatch.setitem(sys.modules, "pymavlink", _FakeMav)
    view = demo_sitl_bridge("run-001", str(tmp_path))
    assert view["sitl_available"] is True and view["skip_note"] is None


# ---- 端点合约：POST /api/demo/sitl ----


def _client(tmp_path):
    """装配真 app（deps 最小五键——端点注册经 create_console_app 内接线）。"""
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path / "scenarios"),
        "report_root": str(tmp_path / "reports"),
        "static_pages": {},
    }
    return TestClient(create_console_app(deps))


@needs_fastapi
def test_sitl_view_endpoint_contract(tmp_path):
    """⑤ 端点合约：POST /api/demo/sitl（body {'run_id'}）→200 演示视图；缺
    run_id/坏 body→400 字段级指错；运行不存在→400 提示选其他运行。"""
    root = str(tmp_path / "reports")
    _make_run(root)
    client = _client(tmp_path)

    resp = client.post("/api/demo/sitl", json={"run_id": "run-001"})
    assert resp.status_code == 200
    view = resp.json()
    assert view["ok"] is True and view["bridge"]["dry_run"] is True
    assert view["n_steps"] == 2

    resp = client.post("/api/demo/sitl", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "run_id"

    resp = client.post(
        "/api/demo/sitl", data="not-json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "body"

    resp = client.post("/api/demo/sitl", json={"run_id": "ghost"})
    assert resp.status_code == 400
    assert "请选择其他运行" in resp.json()["detail"]["error"]


# ---- 页区静态资产（serve_console instruments 页注入的 SITL 桥演示页区） ----


def test_sitl_view_area_zero_external_links_and_anchors():
    """⑥ 页区资产：零外链+同源 fetch 端点字面（/api/demo/sitl）+区块锚点+
    注入映射行 class 锚点+SITL 不在位标注文案。"""
    block = build_sitl_bridge_area()
    assert "http://" not in block and "https://" not in block
    assert 'id="sitl-bridge-area"' in block  # 挂载区块锚点
    assert "'/api/demo/sitl'" in block  # 同源相对路径 fetch
    assert "run_id" in block and "映射预览" in block
    assert SITL_INJECTION_CLASS in block  # 注入映射表条目 class 锚点
    assert "skip_note" in block  # 不在位跳过标注渲染在位
