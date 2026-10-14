"""browse_dataset_library 单测（R63）：建库→卡片字段→过滤→未建索引提示+rebuild→
GET /api/dataset 与 POST /api/dataset/rebuild 端点合约+页区静态资产。

卡片契约（被测实现口径，详见 src/browse_dataset_library/browse_dataset_library.py
模块 docstring）：真值双源=索引条目+来源运行目录场景副本 scenario.yaml（真跑
运行的 result.json 常缺 style/freq 等卡片字段，副本补全）；样式过滤按卡片真值
判定，日期过滤经索引 date_range。
"""
import json
import os

import pytest

try:  # 端点合约用——fastapi 缺库环境整组端点用例 skip
    from fastapi.testclient import TestClient

    from src.serve_console.create_console_app import create_console_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

from src.browse_dataset_library.browse_dataset_library import (
    UNKNOWN_LABEL,
    browse_dataset_library,
    dataset_index_path,
)
from src.browse_dataset_library.dataset_area import build_dataset_area
from src.index_dataset.index_dataset import QueryError, index_dataset

needs_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="环境缺 fastapi")

#: 场景副本缺省内容（真值补全素材——声明齐全的规范化场景形状）。
_SCENARIO_BODY = """\
style: {style}
fs: 1.0e6
freq_hz: 2.4e9
power_dbm: {power_dbm}
duration_s: 0.005
backend: sim
bands:
  - [2400.0, 2483.5]
shielded_box: true
dut_scope: self_built
"""


def _make_run(
    runs_root,
    name,
    *,
    style="tone",
    power_dbm=-10.0,
    with_sigmf=True,
    with_scenario=True,
    result_extra=None,
):
    """在 runs_root 下造一个真运行目录（recordings SigMF 对+场景副本+result.json）。

    result.json 默认**不带** style/freq_mhz（真跑 finalize 口径——卡片真值须从
    场景副本补全）；result_extra 可显式补索引侧字段。
    """
    run_dir = os.path.join(str(runs_root), name)
    os.makedirs(os.path.join(run_dir, "recordings"))
    if with_scenario:
        with open(
            os.path.join(run_dir, "scenario.yaml"), "w", encoding="utf-8"
        ) as handle:
            handle.write(
                _SCENARIO_BODY.format(style=style, power_dbm=power_dbm)
            )
    if with_sigmf:
        stem = os.path.join(run_dir, "recordings", name)
        with open(stem + ".sigmf-meta", "w", encoding="utf-8") as handle:
            handle.write("{}")
        with open(stem + ".sigmf-data", "wb") as handle:
            handle.write(b"\x00" * 16)
    payload = {"status": "done", "backend": "sim"}
    if result_extra:
        payload.update(result_extra)
    with open(
        os.path.join(run_dir, "result.json"), "w", encoding="utf-8"
    ) as handle:
        json.dump(payload, handle)
    return run_dir


def _paths(tmp_path):
    """(index_path, runs_root) 测试落点（一律显式传，不触碰真实目录）。"""
    return (
        str(tmp_path / "dataset-index.json"),
        str(tmp_path / "runs"),
    )


# ---- 纯函数：未建索引→状态提示+重建入口（不报错拦页） ----


def test_browse_library_missing_index_status_hint_and_rebuild_flag(tmp_path):
    """索引文件不存在→missing 状态+hint 提示+rebuild_available=True，不抛。"""
    index_path, runs_root = _paths(tmp_path)
    out = browse_dataset_library(index_path=index_path, runs_root=runs_root)
    assert out["index_status"] == "missing"
    assert out["cards"] == [] and out["count"] == 0 and out["total"] == 0
    assert out["rebuild_available"] is True
    assert "重建" in out["hint"]  # 状态提示指向重建入口


def test_browse_library_missing_index_then_rebuild_flips_to_ready(tmp_path):
    """rebuild（index_dataset 口径）后同查询转 ready——状态提示→重建→浏览闭环。"""
    index_path, runs_root = _paths(tmp_path)
    os.makedirs(runs_root)
    _make_run(runs_root, "20260101-120000")
    index_dataset("rebuild", index_path=index_path, runs_root=runs_root)
    out = browse_dataset_library(index_path=index_path, runs_root=runs_root)
    assert out["index_status"] == "ready"
    assert out["count"] == 1 and out["total"] == 1
    assert out["rebuild_available"] is False and out["hint"] is None


# ---- 纯函数：卡片字段（真值双源：索引条目+场景副本） ----


def test_browse_library_card_fields_from_scenario_copy(tmp_path):
    """真跑运行（result.json 缺 style/freq）→卡片样式/功率/时长/频点从场景副本
    补全；批次/运行来源/日期取索引条目；SigMF 对在位→replayable=True。"""
    index_path, runs_root = _paths(tmp_path)
    os.makedirs(runs_root)
    run_dir = _make_run(
        runs_root,
        "20260102-080000",
        style="chirp",
        power_dbm=-20.0,
        result_extra={"date": "20260102", "batch_key": "batch-b"},
    )
    index_dataset(
        "rebuild", index_path=index_path, runs_root=runs_root
    )  # rebuild 条目：path=run_dir/recordings
    out = browse_dataset_library(index_path=index_path, runs_root=runs_root)
    card = out["cards"][0]
    assert card["style"] == "chirp"  # 副本真值（result.json 无 style）
    assert card["power_dbm"] == -20.0  # 副本功率
    assert card["duration_s"] == 0.005  # 副本时长
    assert card["freq_mhz"] == 2400.0  # 副本 freq_hz→MHz
    assert card["backend"] == "sim"  # 副本后端注册名（result.json 为类名口径）
    assert card["batch_key"] == "batch-b"  # 索引批次
    assert card["source_run"] == "20260102-080000" == card["run_id"]  # 运行来源
    assert card["date"] == "20260102"
    assert card["path"] == os.path.join(run_dir, "recordings")
    assert card["sigmf_path"] == os.path.join(
        run_dir, "recordings", "20260102-080000.sigmf-meta"
    )
    assert card["replayable"] is True  # meta+data 成对


def test_browse_library_card_falls_back_to_index_fields_without_copy(tmp_path):
    """副本/SigMF 对缺失（登记型条目指向假路径）→索引字段兜底+不可回放，不虚构。"""
    index_path, runs_root = _paths(tmp_path)
    record = {
        "run_id": "20260101-000000",
        "path": "/data/nowhere/recordings",  # 不存在的目录→副本/meta 均不可得
        "style": "partial_band",
        "freq_mhz": 5800.0,
        "date": "20260101",
        "backend": "b210",
        "batch_key": None,
        "failed": False,
    }
    index_dataset("register", record=record, index_path=index_path)
    out = browse_dataset_library(index_path=index_path, runs_root=runs_root)
    card = out["cards"][0]
    assert card["style"] == "partial_band"  # 索引兜底
    assert card["freq_mhz"] == 5800.0
    assert card["power_dbm"] is None and card["duration_s"] is None  # 副本缺→不虚构
    assert card["sigmf_path"] is None and card["replayable"] is False
    assert card["batch_key"] is None
    assert card["backend"] == "b210"


def test_browse_library_card_unknown_style_when_both_sources_lack(tmp_path):
    """索引与副本均无有效 style→'未知'占位（明示不可考，不虚构）。"""
    index_path, runs_root = _paths(tmp_path)
    os.makedirs(runs_root)
    _make_run(runs_root, "20260103-000000", with_scenario=False)
    # register 必填非空 style——直接手写索引文件模拟「rebuild 条目缺 style」形状
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "version": 1,
                "entries": [
                    {
                        "run_id": "20260103-000000",
                        "path": os.path.join(
                            str(runs_root), "20260103-000000", "recordings"
                        ),
                        "style": None,  # 缺失口径（list 读路径不做必填校验）
                        "freq_mhz": None,
                        "date": "20260103",
                        "backend": "sim",
                    }
                ],
            },
            handle,
        )
    out = browse_dataset_library(index_path=index_path, runs_root=runs_root)
    assert out["cards"][0]["style"] == UNKNOWN_LABEL


# ---- 纯函数：过滤（样式按卡片真值/日期经索引） ----


def test_browse_library_style_filter_matches_copy_truth(tmp_path):
    """样式过滤按卡片真值（副本补全后的 style）判定——rebuild 条目索引无 style
    也能命中；未知样式 0 卡。"""
    index_path, runs_root = _paths(tmp_path)
    os.makedirs(runs_root)
    _make_run(runs_root, "20260101-000000", style="tone")
    _make_run(runs_root, "20260102-000000", style="chirp")
    index_dataset("rebuild", index_path=index_path, runs_root=runs_root)
    hit = browse_dataset_library(
        {"style": "tone"}, index_path=index_path, runs_root=runs_root
    )
    assert hit["count"] == 1 and hit["cards"][0]["style"] == "tone"
    assert hit["total"] == 2  # 索引全量计数不受卡片级过滤影响
    miss = browse_dataset_library(
        {"style": "pulse"}, index_path=index_path, runs_root=runs_root
    )
    assert miss["count"] == 0 and miss["cards"] == []


def test_browse_library_date_filters_via_index(tmp_path):
    """日期过滤经索引 date_range（闭区间字典序）：命中区间/单边界开放/反序拒绝。"""
    index_path, runs_root = _paths(tmp_path)
    os.makedirs(runs_root)
    _make_run(runs_root, "20260101-000000")
    _make_run(runs_root, "20260102-000000")
    index_dataset("rebuild", index_path=index_path, runs_root=runs_root)
    both = browse_dataset_library(
        {"date_from": "20260101", "date_to": "20260102"},
        index_path=index_path,
        runs_root=runs_root,
    )
    assert both["count"] == 2
    later = browse_dataset_library(
        {"date_from": "20260102"},
        index_path=index_path,
        runs_root=runs_root,
    )
    assert later["count"] == 1
    assert later["cards"][0]["run_id"] == "20260102-000000"
    earlier = browse_dataset_library(
        {"date_to": "20260101"},
        index_path=index_path,
        runs_root=runs_root,
    )
    assert earlier["count"] == 1
    assert earlier["cards"][0]["run_id"] == "20260101-000000"
    with pytest.raises(QueryError):  # 反序区间→索引侧 QueryError 透传
        browse_dataset_library(
            {"date_from": "20260102", "date_to": "20260101"},
            index_path=index_path,
            runs_root=runs_root,
        )


def test_browse_library_style_and_date_combined(tmp_path):
    """样式+日期组合过滤（多条件 AND）。"""
    index_path, runs_root = _paths(tmp_path)
    os.makedirs(runs_root)
    _make_run(runs_root, "20260101-000000", style="tone")
    _make_run(runs_root, "20260102-000000", style="tone")
    _make_run(runs_root, "20260102-120000", style="chirp")
    index_dataset("rebuild", index_path=index_path, runs_root=runs_root)
    out = browse_dataset_library(
        {"style": "tone", "date_from": "20260102"},
        index_path=index_path,
        runs_root=runs_root,
    )
    assert out["count"] == 1
    assert out["cards"][0]["run_id"] == "20260102-000000"


def test_browse_library_bad_query_shapes_rejected(tmp_path):
    """未知条件键/非 dict/空串值→QueryError（附支持清单口径）。"""
    index_path, runs_root = _paths(tmp_path)
    with pytest.raises(QueryError, match="style"):
        browse_dataset_library(
            {"nope": 1}, index_path=index_path, runs_root=runs_root
        )
    with pytest.raises(QueryError):
        browse_dataset_library(
            "tone", index_path=index_path, runs_root=runs_root
        )
    with pytest.raises(QueryError):
        browse_dataset_library(
            {"style": "  "}, index_path=index_path, runs_root=runs_root
        )


# ---- GET /api/dataset + POST /api/dataset/rebuild 端点合约 ----


def _client(tmp_path):
    """装配真 app（create_console_app→mount_console_extensions）+合成运行目录。"""
    root = tmp_path / "reports"
    root.mkdir()
    _make_run(root, "20260101-000000", style="tone", result_extra={"date": "20260101"})
    _make_run(root, "20260102-000000", style="chirp", result_extra={"date": "20260102"})
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path),
        "report_root": str(root),
        "static_pages": {},
    }
    return TestClient(create_console_app(deps)), str(root)


@needs_fastapi
def test_endpoint_dataset_missing_index_is_status_not_error(tmp_path):
    """索引未建→GET /api/dataset 200 missing（状态提示+重建标志，不 400 拦页）。"""
    client, _ = _client(tmp_path)
    resp = client.get("/api/dataset")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["index_status"] == "missing"
    assert payload["rebuild_available"] is True
    assert "重建" in payload["hint"]


@needs_fastapi
def test_endpoint_dataset_rebuild_then_cards_and_filters(tmp_path):
    """POST /api/dataset/rebuild→GET /api/dataset 出卡片；style/date 查询参数过滤；
    反序日期→400 field='query'（QueryError 转译）。"""
    client, _ = _client(tmp_path)
    rebuilt = client.post("/api/dataset/rebuild")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["rebuilt"] == 2
    assert rebuilt.json()["index_status"] == "ready"

    resp = client.get("/api/dataset")
    payload = resp.json()
    assert payload["index_status"] == "ready"
    assert payload["count"] == 2 and payload["total"] == 2
    card = payload["cards"][0]
    for key in (
        "run_id",
        "source_run",
        "path",
        "sigmf_path",
        "replayable",
        "style",
        "freq_mhz",
        "power_dbm",
        "duration_s",
        "batch_key",
        "backend",
        "date",
        "failed",
    ):
        assert key in card  # 卡片契约键齐备

    tone = client.get("/api/dataset", params={"style": "tone"}).json()
    assert tone["count"] == 1 and tone["cards"][0]["style"] == "tone"
    none_hit = client.get("/api/dataset", params={"style": "pulse"}).json()
    assert none_hit["count"] == 0
    dated = client.get(
        "/api/dataset", params={"date_from": "20260102"}
    ).json()
    assert dated["count"] == 1
    assert dated["cards"][0]["run_id"] == "20260102-000000"

    bad = client.get(
        "/api/dataset", params={"date_from": "20260102", "date_to": "20260101"}
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["field"] == "query"


@needs_fastapi
def test_endpoint_rebuild_skips_broken_runs(tmp_path):
    """损坏运行（result.json 非法 JSON）→skipped 计数不短路（index_dataset 口径）。"""
    client, root = _client(tmp_path)
    broken = os.path.join(root, "20260103-000000")
    os.makedirs(broken)
    with open(os.path.join(broken, "result.json"), "w", encoding="utf-8") as handle:
        handle.write("{not-json")
    resp = client.post("/api/dataset/rebuild")
    payload = resp.json()
    assert payload["rebuilt"] == 2 and payload["skipped"] == 1
    assert "dataset-index.json" in payload["index_path"]  # report_root 派生落点


def test_dataset_index_path_helper():
    """dataset_index_path：report_root→索引落点唯一派生口径。"""
    assert dataset_index_path("/tmp/reports") == os.path.join(
        "/tmp/reports", "dataset-index.json"
    )


# ---- 页区静态资产（零外链红线+挂载点/端点接线） ----


def test_dataset_area_zero_external_links_and_wiring():
    """dataset 页区零外链（R56/R63 断网全可用红线）+消费挂载点与端点接线。"""
    block = build_dataset_area()
    assert "http://" not in block and "https://" not in block
    assert "'dataset-grid'" in block  # 卡片挂载点
    assert "'filters'" in block  # 筛选器挂载点
    assert "'/api/dataset'" in block  # 浏览数据源
    assert "'/api/dataset/rebuild'" in block  # 重建入口
    assert "'/api/run/replay'" in block  # R64 一键回放接线
    assert "dataset-card" in block  # 卡片元素锚点
    assert "回放此条" in block  # 卡片回放按钮
