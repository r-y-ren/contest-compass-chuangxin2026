"""list_run_summaries 单测（R61）：合成多运行目录→摘要行字段/排序/缺 result 降级
+ GET /api/runs/summaries 端点合约（路由序手术：字面路由先于 /api/runs/{run_id}）。

行契约（被测实现口径，详见 src/list_run_summaries/list_run_summaries.py 模块
docstring）：每行恒齐 run_id/started_at/scenario_name/style/backend/status/
failure_levels/report_relpath/exit_code 9 键——缺数据的键为 None/[]/'未知'，
降级行 status='no_result' 不虚构不剔除；排序新建在前（started_at‖目录 mtime）。
"""
import json
import os
import time

import pytest

try:  # 端点合约用——fastapi 缺库环境整组端点用例 skip
    from fastapi.testclient import TestClient

    from src.serve_console.create_console_app import create_console_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

from src.list_run_summaries.list_run_summaries import (
    list_run_summaries,
)
from src.list_run_summaries.run_list_area import build_run_list_area

needs_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="环境缺 fastapi")


def _make_run(
    root,
    run_id,
    *,
    result=None,
    scenario=None,
    report=True,
    mtime=None,
):
    """合成一个运行目录：result dict（None=不写 result.json）+场景副本+可选报告。

    mtime 显式控制目录修改时刻（no_result 行排序的 mtime 兜底用例）。
    """
    run_dir = os.path.join(root, run_id)
    os.makedirs(run_dir)
    if result is not None:
        with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    if scenario is not None:
        import yaml

        with open(os.path.join(run_dir, "scenario.yaml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump(scenario, fh, allow_unicode=True)
    if report:
        with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as fh:
            fh.write("# 合成报告\n")
    if mtime is not None:
        os.utime(run_dir, (mtime, mtime))
    return run_dir


def _gb_result(started_at, style, level_db, *, run_status="done", scen_status="failed"):
    """合成 result.json payload（真产物字段口径：finalize 顶层+scenario_result 内层）。"""
    return {
        "status": run_status,
        "started_at": started_at,
        "finished_at": started_at + 1.0,
        "duration_ms": 1000,
        "backend": "SimBackend",
        "clock_ref": "software",
        "scenario_result": {
            "status": scen_status,
            "result": {
                "status": scen_status,
                "failure_levels": [
                    {
                        "style": style,
                        "step": 2,
                        "failure_level_db": level_db,
                        "per_at_failure": 0.1,
                        "ts_ms": 12345,
                    }
                ],
            },
        },
    }


def _scenario(style, *, backend="sim", scenario_type="gb42590", freq_hz=2.4e9):
    """合成场景副本（normalize_scenario 落盘口径的字段子集）。"""
    return {
        "style": style,
        "backend": backend,
        "scenario_type": scenario_type,
        "freq_hz": freq_hz,
    }


# ---- 摘要行：字段与排序 ----


def test_rows_fields_and_newest_first_order(tmp_path):
    """正常行 9 键齐+字段取值（真 result.json 形状）+新建在前（started_at 降序）。"""
    root = str(tmp_path)
    _make_run(
        root,
        "20260101-000000",
        result=_gb_result(1000.0, "tone", -15.0),
        scenario=_scenario("tone"),
    )
    _make_run(
        root,
        "20260102-000000",
        result=_gb_result(2000.0, "bandlimited_noise", -20.0),
        scenario=_scenario("bandlimited_noise"),
    )
    rows = list_run_summaries(root)
    assert [row["run_id"] for row in rows] == ["20260102-000000", "20260101-000000"]
    assert set(rows[0]) == {
        "run_id",
        "started_at",
        "scenario_name",
        "style",
        "backend",
        "status",
        "failure_levels",
        "report_relpath",
        "exit_code",
    }

    newest = rows[0]
    assert newest["started_at"] == 2000.0
    assert newest["scenario_name"] == "gb42590"  # 副本无 name→scenario_type
    assert newest["style"] == "bandlimited_noise"
    assert newest["backend"] == "SimBackend"  # result.json 优先（类名口径如实）
    assert newest["status"] == "failed"  # 判据触发：场景 failed（双确认不过）
    assert newest["exit_code"] == 1
    assert newest["report_relpath"] == "report.md"
    assert newest["failure_levels"][0]["style"] == "bandlimited_noise"
    assert newest["failure_levels"][0]["failure_level_db"] == -20.0


def test_status_double_confirm_semantics(tmp_path):
    """状态双确认（run_demo 口径）：done+completed→completed/0；其余组合→failed/1。"""
    root = str(tmp_path)
    _make_run(
        root,
        "a-completed",
        result=_gb_result(10.0, "tone", -15.0, scen_status="completed"),
    )
    _make_run(root, "b-scen-failed", result=_gb_result(20.0, "tone", -15.0))
    _make_run(
        root,
        "c-run-failed",
        result=_gb_result(30.0, "tone", -15.0, run_status="failed", scen_status="completed"),
    )
    rows = {row["run_id"]: row for row in list_run_summaries(root)}
    assert rows["a-completed"]["status"] == "completed"
    assert rows["a-completed"]["exit_code"] == 0
    assert rows["b-scen-failed"]["status"] == "failed"
    assert rows["b-scen-failed"]["exit_code"] == 1
    assert rows["c-run-failed"]["status"] == "failed"
    assert rows["c-run-failed"]["exit_code"] == 1


def test_no_result_degraded_rows_kept_not_fabricated(tmp_path):
    """result.json 缺失/损坏/非对象→行保留 status='no_result'，不虚构不剔除；
    场景副本尽力补缺（style/backend/scenario_name）。"""
    root = str(tmp_path)
    _make_run(root, "a-missing", result=None, scenario=_scenario("tone"))
    corrupt = _make_run(root, "b-corrupt", scenario=_scenario("bandlimited_noise"))
    with open(os.path.join(corrupt, "result.json"), "w", encoding="utf-8") as fh:
        fh.write("{ not json !!")
    nonobj = _make_run(root, "c-nonobj", scenario=_scenario("chirp"))
    with open(os.path.join(nonobj, "result.json"), "w", encoding="utf-8") as fh:
        json.dump([1, 2, 3], fh)

    rows = {row["run_id"]: row for row in list_run_summaries(root)}
    assert set(rows) == {"a-missing", "b-corrupt", "c-nonobj"}  # 均在列（不剔除）
    for run_id, style in (
        ("a-missing", "tone"),
        ("b-corrupt", "bandlimited_noise"),
        ("c-nonobj", "chirp"),
    ):
        row = rows[run_id]
        assert row["status"] == "no_result"
        assert row["started_at"] is None
        assert row["exit_code"] is None
        assert row["failure_levels"] == []
        assert row["style"] == style  # 副本补缺（真实记录）
        assert row["backend"] == "sim"
        assert row["scenario_name"] == "gb42590"
        assert row["report_relpath"] == "report.md"  # 报告在位即给（目录事实）


def test_no_result_row_without_scenario_or_report(tmp_path):
    """全空运行目录（无 result/副本/报告）→no_result 行以 '未知' 占位不虚构。"""
    root = str(tmp_path)
    _make_run(root, "bare", result=None, scenario=None, report=False)
    rows = list_run_summaries(root)
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == "bare"
    assert row["status"] == "no_result"
    assert row["scenario_name"] == "未知"
    assert row["style"] == "未知"
    assert row["backend"] == "未知"
    assert row["report_relpath"] is None


def test_report_relpath_none_when_report_missing(tmp_path):
    """正常行缺 report.md→report_relpath=None（「查看报告」链接不给）。"""
    root = str(tmp_path)
    _make_run(
        root,
        "no-report",
        result=_gb_result(10.0, "tone", -15.0, scen_status="completed"),
        scenario=_scenario("tone"),
        report=False,
    )
    rows = list_run_summaries(root)
    assert rows[0]["report_relpath"] is None


def test_order_mtime_fallback_for_no_result_rows(tmp_path):
    """started_at 缺失的 no_result 行以目录 mtime 兜底排序（测试显式设定 mtime）。"""
    root = str(tmp_path)
    base = time.time() - 1000
    _make_run(
        root,
        "old-ok",
        result=_gb_result(base, "tone", -15.0, scen_status="completed"),
        scenario=_scenario("tone"),
    )
    _make_run(root, "mid-bare", result=None, scenario=None, report=False, mtime=base + 50)
    _make_run(
        root,
        "new-ok",
        result=_gb_result(base + 100, "tone", -15.0, scen_status="completed"),
        scenario=_scenario("tone"),
    )
    _make_run(
        root, "newest-bare", result=None, scenario=None, report=False, mtime=base + 200
    )
    rows = list_run_summaries(root)
    assert [row["run_id"] for row in rows] == [
        "newest-bare",
        "new-ok",
        "mid-bare",
        "old-ok",
    ]


def test_style_falls_back_to_failure_level_entry(tmp_path):
    """场景副本缺 style 时回落失效电平条目的样式记录（同为真实数据）。"""
    root = str(tmp_path)
    _make_run(root, "only-result", result=_gb_result(10.0, "partial_band", -12.0))
    rows = list_run_summaries(root)
    assert rows[0]["style"] == "partial_band"
    assert rows[0]["failure_levels"][0]["failure_level_db"] == -12.0


def test_empty_or_missing_root_returns_empty_list(tmp_path):
    """空根→[]；不存在的根→[]（空报告中心不报错拦页）。"""
    empty_root = str(tmp_path / "runs")
    os.makedirs(empty_root)
    assert list_run_summaries(empty_root) == []
    assert list_run_summaries(str(tmp_path / "no-such-root")) == []


def test_invalid_root_raises_valueerror():
    """report_root 非 str/PathLike→ValueError（编程错误早暴露）。"""
    with pytest.raises(ValueError, match="report_root"):
        list_run_summaries(None)
    with pytest.raises(ValueError, match="report_root"):
        list_run_summaries("")


# ---- GET /api/runs/summaries 端点合约（经 mount_console_extensions 注册） ----


def _client(tmp_path):
    """装配真 app（create_console_app→mount_console_extensions）+合成两个运行目录。"""
    root = tmp_path / "reports"
    root.mkdir()
    _make_run(
        str(root),
        "20260101-000000",
        result=_gb_result(1000.0, "tone", -15.0),
        scenario=_scenario("tone"),
    )
    _make_run(
        str(root),
        "20260102-000000",
        result=_gb_result(2000.0, "bandlimited_noise", -20.0),
        scenario=_scenario("bandlimited_noise"),
    )
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path),
        "report_root": str(root),
        "static_pages": {},
    }
    return TestClient(create_console_app(deps)), str(root)


@needs_fastapi
def test_endpoint_summaries_shape_and_order(tmp_path):
    """GET /api/runs/summaries→200 {'summaries','count'}，行同纯函数口径（新建在前）。"""
    client, _ = _client(tmp_path)
    resp = client.get("/api/runs/summaries")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] == 2
    assert [row["run_id"] for row in payload["summaries"]] == [
        "20260102-000000",
        "20260101-000000",
    ]
    row = payload["summaries"][0]
    assert row["style"] == "bandlimited_noise"
    assert row["status"] == "failed"
    assert row["failure_levels"][0]["failure_level_db"] == -20.0


@needs_fastapi
def test_endpoint_literal_route_beats_param_route(tmp_path):
    """路由序手术防回归：/api/runs/summaries 不被 GET /api/runs/{run_id} 吞掉
    （后者仍按自身语义工作——运行表未知 id 404）。"""
    client, _ = _client(tmp_path)
    resp = client.get("/api/runs/summaries")
    assert resp.status_code == 200
    assert "summaries" in resp.json()  # 非 {'detail': '运行不存在: summaries'}
    param_resp = client.get("/api/runs/unknown-uuid")
    assert param_resp.status_code == 404


@needs_fastapi
def test_endpoint_missing_report_root_dir_400(tmp_path):
    """report_root 路径不存在→400 field='report_root'（与 GET /api/runs 同语义）。"""
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path),
        "report_root": str(tmp_path / "no-such-root"),
        "static_pages": {},
    }
    client = TestClient(create_console_app(deps))
    resp = client.get("/api/runs/summaries")
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "report_root"


# ---- 页区静态资产（零外链红线） ----


def test_run_list_area_zero_external_links():
    """run-list 页区零外链（R56/R61 断网全可用红线）+消费挂载点与数据源接线。"""
    block = build_run_list_area()
    assert "http://" not in block and "https://" not in block
    assert "'run-list'" in block  # 填充 reports 骨架页挂载点
    assert "/api/runs/summaries" in block  # 数据源端点
    assert "run-select" in block  # R62 对比勾选协作锚点
    assert "run-summary-table" in block
