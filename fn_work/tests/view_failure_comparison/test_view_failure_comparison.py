"""view_failure_comparison 单测（R62）：合成多轮→compare_failure_boundaries 对比表/
薄弱环节结论/单样式降级标注 + 无失效数据行标注 + POST /api/runs/compare 端点合约。

对比表用例族名统一 test_boundary_view_ 前缀——R62 验收通道 ``pytest -k
boundary_view``（合成多轮→对比表断言）经名发现本族（B25 I-1：验收命令不再
零选集空转）。

视图契约（被测实现口径，详见 src/view_failure_comparison/view_failure_comparison.py
模块 docstring）：run_ids/entries/comparison(R26 原样)/weakest_style/weakest_freq_mhz/
tie/n_unknown/n_freq_invalid/conclusion/degraded/runs_without_failure/missing_runs。
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

from src.view_failure_comparison.comparison_area import build_comparison_area
from src.view_failure_comparison.view_failure_comparison import (
    view_failure_comparison,
)

needs_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="环境缺 fastapi")


def _make_run(root, run_id, *, levels=None, corrupt=False, freq_hz=None, no_result=False):
    """合成一个运行目录：levels=[(style, level_db), …] 写入 scenario_result 内层；
    corrupt=True 写损坏 result.json；no_result=True 不写 result.json。"""
    run_dir = os.path.join(root, run_id)
    os.makedirs(run_dir)
    if not no_result:
        payload = {
            "status": "done",
            "started_at": 1000.0,
            "backend": "SimBackend",
            "scenario_result": {
                "status": "failed",
                "result": {
                    "status": "failed",
                    "failure_levels": [
                        {"style": style, "failure_level_db": level}
                        for style, level in (levels or [])
                    ],
                },
            },
        }
        with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as fh:
            if corrupt:
                fh.write("{ broken json !!")
            else:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
    if freq_hz is not None:
        import yaml

        with open(os.path.join(run_dir, "scenario.yaml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump({"style": "tone", "freq_hz": freq_hz}, fh)
    return run_dir


# ---- 对比表与薄弱环节结论 ----


def test_boundary_view_multi_style_comparison_table_and_weakest(tmp_path):
    """两轮两样式→对比表升序两行+最薄弱样式=电平中位数最低者+结论含定位。"""
    root = str(tmp_path)
    _make_run(root, "run-a", levels=[("tone", -15.0)])
    _make_run(root, "run-b", levels=[("bandlimited_noise", -20.0)])
    view = view_failure_comparison(["run-a", "run-b"], root)
    assert view["comparison"] == [
        {
            "style": "bandlimited_noise",
            "median_level_db": -20.0,
            "n_runs": 1,
            "min_db": -20.0,
            "max_db": -20.0,
        },
        {
            "style": "tone",
            "median_level_db": -15.0,
            "n_runs": 1,
            "min_db": -15.0,
            "max_db": -15.0,
        },
    ]
    assert view["weakest_style"] == "bandlimited_noise"
    assert view["degraded"] is False
    assert view["entries"][0]["run_id"] == "run-a"  # 条目携来源运行键
    assert "最薄弱样式为 bandlimited_noise" in view["conclusion"]
    assert view["runs_without_failure"] == []
    assert view["missing_runs"] == []


def test_boundary_view_median_across_multiple_entries_per_style(tmp_path):
    """同样式多条目（一轮可产多条）→中位数聚合+按条目计数（R26 口径，非轮次数）。"""
    root = str(tmp_path)
    _make_run(root, "run-a", levels=[("tone", -10.0), ("tone", -20.0), ("tone", -17.0)])
    _make_run(root, "run-b", levels=[("bandlimited_noise", -15.0), ("bandlimited_noise", -25.0)])
    view = view_failure_comparison(["run-a", "run-b"], root)
    assert len(view["entries"]) == 5
    assert [row["style"] for row in view["comparison"]] == [
        "bandlimited_noise",
        "tone",
    ]
    tone_row = view["comparison"][1]
    assert tone_row["n_runs"] == 3  # 有效条目数（按条目计，非轮次数）
    assert tone_row["median_level_db"] == -17.0  # median(-20, -17, -10)
    assert tone_row["min_db"] == -20.0 and tone_row["max_db"] == -10.0


def test_boundary_view_single_style_degraded_annotation(tmp_path):
    """样本不足降级：两轮同一有效样式→comparison 置空+degraded=True+结论注明单样式
    （R26 口径结构化透出）。"""
    root = str(tmp_path)
    _make_run(root, "run-a", levels=[("tone", -15.0)])
    _make_run(root, "run-b", levels=[("tone", -18.0)])
    view = view_failure_comparison(["run-a", "run-b"], root)
    assert view["comparison"] == []
    assert view["weakest_style"] is None
    assert view["degraded"] is True
    assert "单样式数据" in view["conclusion"]
    assert "有效 2 条（按条目计）" in view["conclusion"]


def test_boundary_view_runs_without_failure_and_missing_runs(tmp_path):
    """在位运行无失效数据→标注行（未失效/无结果）；不存在运行→missing_runs。"""
    root = str(tmp_path)
    _make_run(root, "ok", levels=[("tone", -15.0)])
    _make_run(root, "no-failure", levels=[])  # result 可读但零失效条目
    _make_run(root, "broken", corrupt=True)  # result.json 损坏
    _make_run(root, "gone", no_result=True)  # 无 result.json
    view = view_failure_comparison(
        ["ok", "no-failure", "broken", "gone", "no-such-run"], root
    )
    assert view["missing_runs"] == ["no-such-run"]
    notes = {row["run_id"]: row["note"] for row in view["runs_without_failure"]}
    assert notes["no-failure"].startswith("未失效")
    assert notes["broken"].startswith("无结果")
    assert notes["gone"].startswith("无结果")
    # ok 轮不进任何标注清单
    assert "ok" not in notes and "ok" not in view["missing_runs"]
    assert len(view["entries"]) == 1


def test_boundary_view_all_runs_lack_data_hint_to_pick_others(tmp_path):
    """全缺→R26「无数据」结论追加「请选择其他运行」提示（R62 签名意图）。"""
    root = str(tmp_path)
    _make_run(root, "no-failure", levels=[])
    _make_run(root, "gone", no_result=True)
    view = view_failure_comparison(["no-failure", "gone"], root)
    assert view["entries"] == []
    assert view["conclusion"].startswith("无数据")
    assert "请选择其他运行" in view["conclusion"]


def test_boundary_view_unknown_levels_counted_not_compared(tmp_path):
    """unknown 电平条目不进数值统计（R26 口径）——n_unknown 计数、该样式不出现于
    对比表（表中只有数值电平样式）。"""
    root = str(tmp_path)
    _make_run(root, "run-a", levels=[("tone", "unknown")])
    _make_run(root, "run-b", levels=[("bandlimited_noise", -20.0)])
    _make_run(root, "run-c", levels=[("sweep", -12.0)])
    view = view_failure_comparison(["run-a", "run-b", "run-c"], root)
    assert view["n_unknown"] == 1
    assert [row["style"] for row in view["comparison"]] == [
        "bandlimited_noise",
        "sweep",
    ]  # tone（unknown 电平）不出现于表——无从求中位数
    assert view["degraded"] is False
    assert "另有 1 条 unknown 电平条目未纳入数值统计" in view["conclusion"]


def test_boundary_view_freq_enrichment_from_scenario_freq_hz(tmp_path):
    """条目缺 freq_mhz 时由场景副本 freq_hz 换算补充（真实数据来源）→两频点可出
    最薄弱频点。"""
    root = str(tmp_path)
    _make_run(root, "run-a", levels=[("tone", -15.0)], freq_hz=2.4e9)
    _make_run(root, "run-b", levels=[("tone", -25.0), ("tone", -18.0)], freq_hz=5.8e9)
    view = view_failure_comparison(["run-a", "run-b"], root)
    freqs = sorted(entry["freq_mhz"] for entry in view["entries"])
    assert freqs == [2400.0, 5800.0, 5800.0]
    assert view["weakest_freq_mhz"] == 5800.0  # 5800 组中位 -21.5 < 2400 组 -15
    assert "最薄弱频点为 5800.0 MHz" in view["conclusion"]


def test_boundary_view_entry_native_freq_mhz_wins(tmp_path):
    """条目自带 freq_mhz 优先（不被场景副本换算覆盖）。"""
    root = str(tmp_path)
    _make_run(root, "run-a", levels=[("tone", -15.0)], freq_hz=2.4e9)
    run_dir = os.path.join(root, "run-a")
    with open(os.path.join(run_dir, "result.json"), encoding="utf-8") as fh:
        payload = json.load(fh)
    payload["scenario_result"]["result"]["failure_levels"][0]["freq_mhz"] = 2480.0
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    view = view_failure_comparison(["run-a"], root)
    assert view["entries"][0]["freq_mhz"] == 2480.0


# ---- 入参形状纪律 ----


def test_invalid_run_ids_raise_valueerror(tmp_path):
    """run_ids 非 list/元素非 str/穿越形态→ValueError（端点转 400）；
    穿越判定与 serve_run_artifacts 同口径（空白名不属穿越，走 missing_runs）。"""
    root = str(tmp_path)
    with pytest.raises(ValueError, match="run_ids"):
        view_failure_comparison("run-a", root)  # 非 list
    with pytest.raises(ValueError, match="run_ids"):
        view_failure_comparison([123], root)  # 元素非 str
    with pytest.raises(ValueError, match="非法运行名"):
        view_failure_comparison(["../etc/passwd"], root)  # 穿越形态早拒
    with pytest.raises(ValueError, match="非法运行名"):
        view_failure_comparison(["a/b"], root)


@pytest.mark.parametrize(
    "evil_name",
    [
        "run\x00a",  # NUL（早拒主形态——路径拼接/日志行欺篡载体）
        "run\na",  # 换行（日志注入）
        "run\ra",  # CR
        "run\x1fa",  # US（\x1f 上边界）
        "run\x7fa",  # DEL
        "run\tb\x0b",  # TAB/VT 混杂
    ],
)
def test_control_chars_in_run_ids_rejected(tmp_path, evil_name):
    """B25 M-1：run_id 含控制字符（\x00-\x1f、\x7f）→ValueError 按非法运行名早拒
    （端点转 400——非打印字符不入路径拼接）。"""
    with pytest.raises(ValueError, match="非法运行名"):
        view_failure_comparison([evil_name], str(tmp_path))


def test_empty_run_ids_selection_gets_pick_others_hint(tmp_path):
    """B25 M-2：空 run_ids 选择集→conclusion 同样追加「请选择其他运行」提示
    （与 docstring「全缺（entries 空——含空选择集）」口径对齐——空选不再静默）。"""
    view = view_failure_comparison([], str(tmp_path))
    assert view["entries"] == []
    assert view["runs_without_failure"] == []
    assert view["missing_runs"] == []
    assert view["conclusion"].startswith("无数据")
    assert "请选择其他运行" in view["conclusion"]


def test_invalid_report_root_raises_valueerror():
    """report_root 非 str/PathLike→ValueError（编程错误早暴露）。"""
    with pytest.raises(ValueError, match="report_root"):
        view_failure_comparison(["run-a"], None)


# ---- POST /api/runs/compare 端点合约（经 mount_console_extensions 注册） ----


def _client(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    _make_run(str(root), "run-a", levels=[("tone", -15.0)])
    _make_run(str(root), "run-b", levels=[("bandlimited_noise", -20.0)])
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path),
        "report_root": str(root),
        "static_pages": {},
    }
    return TestClient(create_console_app(deps))


@needs_fastapi
def test_endpoint_compare_ok(tmp_path):
    """POST /api/runs/compare body {'run_ids'}→200 视图 dict（对比表+结论透传）。"""
    client = _client(tmp_path)
    resp = client.post("/api/runs/compare", json={"run_ids": ["run-a", "run-b"]})
    assert resp.status_code == 200
    view = resp.json()
    assert view["weakest_style"] == "bandlimited_noise"
    assert [row["style"] for row in view["comparison"]] == [
        "bandlimited_noise",
        "tone",
    ]
    assert "最薄弱样式" in view["conclusion"]


@needs_fastapi
def test_endpoint_compare_bad_body_400(tmp_path):
    """body 非 JSON 对象/缺 run_ids/形状错/穿越名→400 字段级指错（R47 口径）。"""
    client = _client(tmp_path)
    bad = client.post("/api/runs/compare", content=b"{ broken", headers={
        "Content-Type": "application/json"})
    assert bad.status_code == 400 and bad.json()["detail"]["field"] == "body"
    missing = client.post("/api/runs/compare", json={})
    assert missing.status_code == 400 and missing.json()["detail"]["field"] == "run_ids"
    shape = client.post("/api/runs/compare", json={"run_ids": "run-a"})
    assert shape.status_code == 400 and shape.json()["detail"]["field"] == "run_ids"
    traversal = client.post("/api/runs/compare", json={"run_ids": ["../etc"]})
    assert traversal.status_code == 400
    assert traversal.json()["detail"]["field"] == "run_ids"


# ---- 页区静态资产（零外链红线） ----


def test_comparison_area_zero_external_links():
    """comparison 页区零外链（R56/R62 断网全可用红线）+挂载点/端点/run-list 勾选协作。"""
    block = build_comparison_area()
    assert "http://" not in block and "https://" not in block
    assert "'comparison'" in block  # 填充 reports 骨架页挂载点
    assert "/api/runs/compare" in block  # 数据源端点
    assert "run-select" in block  # 从 R61 run-list 行勾选取运行集
