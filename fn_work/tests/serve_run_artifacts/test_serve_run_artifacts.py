"""serve_run_artifacts 对抗测试：三 kind 合约（report=HTML+溯源徽标+traceability
键、plots=PNG 字节、files=白名单字节+Content-Type）+路径穿越/run_id 穿越/白名单外/
未知 kind 的拒绝型标记（400）+运行/文件不存在的 NotFound 型标记（404）+叶子渲染
错误原样上抛（端点转 500 口径）+wired 三端点经 create_console_app 的路由合约。

标记 dict 形状（父函数 docstring 登记）：
- 拒绝型 {'ok': False, 'error': 'rejected', 'status': 400, 'detail': …}
- NotFound 型 {'ok': False, 'error': 'not_found', 'status': 404, 'detail': …}
"""
import json
import os
from pathlib import Path

import pytest

from src.serve_run_artifacts.serve_run_artifacts import (
    FILES_WHITELIST,
    TRACEABILITY_BADGE_ID,
    serve_run_artifacts,
)

try:  # TestClient 同源依赖 fastapi+httpx——任一缺失即 wired 族 skip
    from fastapi.testclient import TestClient

    from src.serve_console.serve_console import serve_console

    _HAS_TESTCLIENT = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_TESTCLIENT = False

needs_fastapi = pytest.mark.skipif(
    not _HAS_TESTCLIENT, reason="环境缺 fastapi/httpx——TestClient 不可用"
)

_RUN_ID = "20261013-120000"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PNG_NAMES = (
    "curve_a_per_vs_level.png",
    "curve_b_throughput_vs_per.png",
    "curve_c_event_timeline.png",
)
_REPORT_MD = (
    "# Run Report（" + _RUN_ID + "）\n\n"
    "## 运行概要\n\n| 项 | 值 |\n| --- | --- |\n| 后端 | sim |\n\n"
    "## 三元曲线\n\n"
    + "\n\n".join(f"![图](plots/{n})" for n in _PNG_NAMES)
    + "\n"
)


def _make_run(tmp_path, traceability=True, with_report=True):
    """造一个最小 run 目录（plots 三 PNG+report.md+kpi.csv+result.json）。

    traceability：True→passed 结论在案；False→未通过结论；None→result.json 不含
    该字段（无结论口径）。返回 run_root（run 目录的父）。"""
    run_root = tmp_path / "reports"
    run_dir = run_root / _RUN_ID
    (run_dir / "plots").mkdir(parents=True)
    for name in _PNG_NAMES:
        (run_dir / "plots" / name).write_bytes(_PNG_MAGIC + b"fake-" + name.encode())
    if with_report:
        (run_dir / "report.md").write_text(_REPORT_MD, encoding="utf-8")
    (run_dir / "kpi.csv").write_text(
        "timestamp_ms,link,per,retries,rssi,source\n", encoding="utf-8"
    )
    payload = {"status": "completed"}
    if traceability is True:
        payload["traceability"] = {
            "passed": True,
            "n_numbers": 8,
            "n_traced": 8,
            "n_contextual": 0,
            "mismatches": [],
        }
    elif traceability is False:
        payload["traceability"] = {
            "passed": False,
            "n_numbers": 8,
            "n_traced": 6,
            "n_contextual": 0,
            "mismatches": [{"value": 1.5, "unit": "dB", "line_no": 9, "context": "…"}],
        }
    (run_dir / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return str(run_root)


# ---- kind='report'：HTML+溯源结论回显 ----


def test_report_kind_returns_html_with_passed_badge(tmp_path):
    """① report 合约：{'ok',kind,content_type='text/html',body,traceability}——
    body 含已改写的 plots 端点引用+溯源徽标（passed→data-passed="true"，文本附
    可溯计数）；traceability 键=result.json 原对象。"""
    out = serve_run_artifacts(_make_run(tmp_path, traceability=True), _RUN_ID, "report")
    assert out["ok"] is True and out["kind"] == "report"
    assert out["content_type"] == "text/html"
    assert f'src="/api/runs/{_RUN_ID}/plots/curve_a_per_vs_level.png"' in out["body"]
    badge = f'id="{TRACEABILITY_BADGE_ID}"'
    assert badge in out["body"] and 'data-passed="true"' in out["body"]
    assert "可溯 8/8" in out["body"] and "差异 0 条" in out["body"]
    assert out["traceability"] == {
        "passed": True,
        "n_numbers": 8,
        "n_traced": 8,
        "n_contextual": 0,
        "mismatches": [],
    }


def test_report_kind_failed_traceability_badge_false(tmp_path):
    """② 溯源未通过：徽标 data-passed="false"（不虚报通过）+差异条数回显。"""
    out = serve_run_artifacts(
        _make_run(tmp_path, traceability=False), _RUN_ID, "report"
    )
    assert out["ok"] is True
    assert 'data-passed="false"' in out["body"] and "差异 1 条" in out["body"]
    assert out["traceability"]["passed"] is False


@pytest.mark.parametrize("mode", ["no_field", "no_file", "corrupt"])
def test_report_kind_without_traceability_shows_none(tmp_path, mode):
    """③ 无结论三态（result.json 无字段/文件缺失/损坏 JSON）→徽标
    data-passed="none" 说明原因、traceability 键 None——不虚构、不反杀报告服务。"""
    run_root = _make_run(tmp_path, traceability=None)
    run_dir = os.path.join(run_root, _RUN_ID)
    if mode == "no_field":  # _make_run(traceability=None) 已是无字段形态
        pass
    elif mode == "no_file":
        os.remove(os.path.join(run_dir, "result.json"))
    else:  # corrupt
        with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as fh:
            fh.write("{broken json")
    out = serve_run_artifacts(run_root, _RUN_ID, "report")
    assert out["ok"] is True  # 报告照常服务
    assert out["traceability"] is None
    assert 'data-passed="none"' in out["body"] and "无结论" in out["body"]


def test_report_kind_missing_report_md_not_found(tmp_path):
    """④ run 目录在而 report.md 缺失→NotFound 型标记（404，detail 点名）。"""
    run_root = _make_run(tmp_path, with_report=False)
    out = serve_run_artifacts(run_root, _RUN_ID, "report")
    assert out == {
        "ok": False,
        "error": "not_found",
        "status": 404,
        "detail": out["detail"],
    }
    assert "report.md" in out["detail"]


def test_report_kind_render_error_propagates(tmp_path, monkeypatch):
    """⑤ 叶子渲染错误（文件损坏等 ValueError）原样上抛不捕获——端点转 500 口径
    （父函数对渲染错误不做标记降级）。"""
    import src.serve_run_artifacts.serve_run_artifacts as sra

    def boom(report_path, run_id):
        raise ValueError("boom: 损坏")

    run_root = _make_run(tmp_path)
    monkeypatch.setattr(sra, "render_report_html", boom)
    with pytest.raises(ValueError, match="boom"):
        serve_run_artifacts(run_root, _RUN_ID, "report")


# ---- kind='plots'：PNG 字节合约+穿越拒绝 ----


def test_plots_kind_serves_png_bytes(tmp_path):
    """⑥ plots 合约：{'ok',kind,content_type='image/png',body=文件字节,name}。"""
    run_root = _make_run(tmp_path)
    out = serve_run_artifacts(run_root, _RUN_ID, "plots", "curve_b_throughput_vs_per.png")
    assert out["ok"] is True and out["content_type"] == "image/png"
    assert out["body"].startswith(_PNG_MAGIC)
    with open(os.path.join(run_root, _RUN_ID, "plots", "curve_b_throughput_vs_per.png"), "rb") as fh:
        assert out["body"] == fh.read()  # 逐字节对拍
    assert out["name"] == "curve_b_throughput_vs_per.png"


@pytest.mark.parametrize(
    "bad_name",
    ["../report.md", "..", "a/b.png", "a\\b.png", "/abs/x.png", "x.png/../y.png", None, ""],
)
def test_plots_kind_traversal_rejected(tmp_path, bad_name):
    """⑦ 路径穿越/非法名（..、/、\\\\、绝对路径、空）→拒绝型标记（400，
    detail 点名穿越口径）——不抛异常。"""
    out = serve_run_artifacts(_make_run(tmp_path), _RUN_ID, "plots", bad_name)
    assert out["ok"] is False and out["error"] == "rejected" and out["status"] == 400
    assert "非法" in out["detail"] or "穿越" in out["detail"]


def test_plots_kind_non_png_rejected(tmp_path):
    """⑧ 非 .png 后缀（plots 仅服务 PNG 曲线图）→拒绝型标记。"""
    out = serve_run_artifacts(_make_run(tmp_path), _RUN_ID, "plots", "notes.txt")
    assert out["error"] == "rejected" and out["status"] == 400
    assert "PNG" in out["detail"]


def test_plots_kind_missing_png_not_found(tmp_path):
    """⑨ 合法名但文件不存在→NotFound 型标记（404）。"""
    out = serve_run_artifacts(_make_run(tmp_path), _RUN_ID, "plots", "missing.png")
    assert out["error"] == "not_found" and out["status"] == 404


# ---- kind='files'：白名单合约+白名单外拒 ----


def test_files_kind_serves_whitelisted_bytes(tmp_path):
    """⑩ files 合约：白名单内逐文件字节+Content-Type 映射（result.json→
    application/json、kpi.csv→text/csv、events.jsonl→ndjson）。"""
    run_root = _make_run(tmp_path)
    run_dir = os.path.join(run_root, _RUN_ID)
    for name in ("kpi.csv", "result.json"):
        with open(os.path.join(run_dir, name), "rb") as fh:
            raw = fh.read()
        out = serve_run_artifacts(run_root, _RUN_ID, "files", name)
        assert out["ok"] is True and out["kind"] == "files"
        assert out["body"] == raw and out["name"] == name
        assert out["content_type"] == FILES_WHITELIST[name]
    assert FILES_WHITELIST["result.json"] == "application/json"


@pytest.mark.parametrize(
    "bad_name",
    ["evil.txt", "plots/curve_a_per_vs_level.png", "../result.json", "result.json.bak", None],
)
def test_files_kind_outside_whitelist_rejected(tmp_path, bad_name):
    """⑪ 白名单外（未知名/子路径/穿越/伪造后缀）→拒绝型标记（400，detail 列
    白名单）——plots 子路径也不经 files 端点旁路。"""
    out = serve_run_artifacts(_make_run(tmp_path), _RUN_ID, "files", bad_name)
    assert out["error"] == "rejected" and out["status"] == 400
    assert "白名单" in out["detail"] or "非法" in out["detail"]


def test_files_kind_missing_whitelisted_not_found(tmp_path):
    """⑫ 白名单内但文件不存在（该 run 未产此文件）→NotFound 型标记。"""
    out = serve_run_artifacts(_make_run(tmp_path), _RUN_ID, "files", "run.log")
    assert out["error"] == "not_found" and out["status"] == 404


# ---- 通用：未知 kind / run 不存在 / run_id 穿越 / run_root 形状 ----


def test_unknown_kind_rejected(tmp_path):
    """⑬ kind 未知→拒绝型标记（400）。"""
    out = serve_run_artifacts(_make_run(tmp_path), _RUN_ID, "videos", "x.mp4")
    assert out["error"] == "rejected" and out["status"] == 400
    assert "kind" in out["detail"]


def test_run_not_found_marker(tmp_path):
    """⑭ run_root 下无该 run 目录→NotFound 型标记（404，detail 含 run_id）。"""
    out = serve_run_artifacts(_make_run(tmp_path), "20990101-000000", "report")
    assert out["error"] == "not_found" and out["status"] == 404
    assert "20990101-000000" in out["detail"]


@pytest.mark.parametrize("bad_run_id", ["../runs", "a/b", "/abs", "..", ".", "a\\b"])
def test_run_id_traversal_rejected(tmp_path, bad_run_id):
    """⑮ run_id 穿越形态（嵌入 URL——一律早拒）→拒绝型标记（400）。"""
    out = serve_run_artifacts(_make_run(tmp_path), bad_run_id, "report")
    assert out["error"] == "rejected" and out["status"] == 400
    assert "run_id" in out["detail"]


@pytest.mark.parametrize("bad_root", [None, 42, "", ["runs"]])
def test_run_root_shape_error_raises(bad_root):
    """⑯ run_root 非 str/PathLike/空→ValueError（编程错误早暴露，非标记）。"""
    with pytest.raises(ValueError, match="run_root"):
        serve_run_artifacts(bad_root, _RUN_ID, "report")


def test_run_root_accepts_pathlike(tmp_path):
    """⑰ PathLike run_root（pathlib.Path）透传合法。"""
    run_root = _make_run(tmp_path)
    out = serve_run_artifacts(
        Path(run_root), _RUN_ID, "plots", "curve_a_per_vs_level.png"
    )
    assert out["ok"] is True


# ---- wired：三端点经 serve_console/create_console_app 的路由合约 ----


@needs_fastapi
def test_wired_three_endpoints_contract(tmp_path):
    """⑱ wired 接线：mount_console_extensions 注册的三路由在 serve_console 缺省
    装配 app 上直达——report 200 HTML（徽标+端点图引用）、plots 200 image/png
    逐字节对拍、files 200 字节对拍；与既有 GET /api/runs、/api/runs/{run_id}
    路由不冲突（三段以上路径形态）。"""
    run_root = _make_run(tmp_path)
    cfg = {
        "scenario_dir": str(tmp_path / "scenarios"),
        "report_root": run_root,
        "port": 18130,
        "host": "127.0.0.1",
        "dry_run": True,
        "stop_flag": {"flag": False},
    }
    os.makedirs(cfg["scenario_dir"], exist_ok=True)
    result = serve_console(cfg)
    with TestClient(result["app"]) as client:
        report = client.get(f"/api/runs/{_RUN_ID}/report")
        plot = client.get(f"/api/runs/{_RUN_ID}/plots/curve_a_per_vs_level.png")
        data = client.get(f"/api/runs/{_RUN_ID}/files/kpi.csv")
        runs_list = client.get("/api/runs")
        run_entry = client.get(f"/api/runs/{_RUN_ID}")  # 既有路由：fs 目录≠运行表项
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/html")
    assert f'id="{TRACEABILITY_BADGE_ID}"' in report.text
    assert f"/api/runs/{_RUN_ID}/plots/curve_a_per_vs_level.png" in report.text
    assert plot.status_code == 200 and plot.headers["content-type"] == "image/png"
    assert plot.content.startswith(_PNG_MAGIC)
    assert data.status_code == 200 and data.text.startswith("timestamp_ms")
    assert runs_list.status_code == 200  # 既有 /api/runs 不回归
    assert run_entry.status_code == 404  # 既有 /api/runs/{id} 查运行表（非 fs）不回归


@needs_fastapi
def test_wired_error_status_mapping(tmp_path):
    """⑱b wired 错误映射：标记→HTTP 状态（穿越/白名单外→400；运行/文件不存在
    →404）；路由层对穿越名（URL 编码点号形态）防线实测。"""
    run_root = _make_run(tmp_path)
    cfg = {
        "scenario_dir": str(tmp_path / "scenarios"),
        "report_root": run_root,
        "port": 18131,
        "host": "127.0.0.1",
        "dry_run": True,
        "stop_flag": {"flag": False},
    }
    os.makedirs(cfg["scenario_dir"], exist_ok=True)
    result = serve_console(cfg)
    with TestClient(result["app"]) as client:
        no_run = client.get("/api/runs/20990101-000000/report")
        no_file = client.get(f"/api/runs/{_RUN_ID}/files/run.log")
        outside = client.get(f"/api/runs/{_RUN_ID}/files/evil.txt")
        dots = client.get(f"/api/runs/{_RUN_ID}/plots/%2E%2Ex.png")  # 编码 ..x.png
    assert no_run.status_code == 404 and "运行不存在" in no_run.json()["detail"]
    assert no_file.status_code == 404
    assert outside.status_code == 400 and "白名单" in outside.json()["detail"]
    assert dots.status_code == 400  # 穿越名抵达处理器即拒（%2F 形态则路由层 404 拦）
