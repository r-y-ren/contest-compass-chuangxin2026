"""demo_emc_flows 单测（R68）：三流程分派（conduction/radiation/sweep 经
execute_scenario emc_flow 子类型分派真跑）+强制模拟口径声明字段（simulated/
disclaimer）+频率域越界裁剪标注并入（R33–R35）+负载收割三通道+端点合约
（POST /api/emc/{flow}——202+运行表轮询）+页区静态资产零外链。用例名统一
``test_emc_view_`` 前缀（`pytest -k emc_view` 发现——R68 核验命令真身：三流程
可达+声明字段）。

被测实现口径见 src/demo_emc_flows/demo_emc_flows.py 模块 docstring（flow 归一/
三通道收割/诚实基注契约）；emc 子类型分派（execute_scenario R68 快速通道改造点）
的用例另在 tests/run_demo/test_execute_scenario.py。
"""
import json
import time

import pytest

try:  # 端点合约用——fastapi 缺库环境整组端点用例 skip
    from fastapi.testclient import TestClient

    from src.serve_console.create_console_app import create_console_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

from src.demo_emc_flows.demo_emc_flows import EMC_FLOWS, demo_emc_flows
from src.demo_emc_flows.emc_area import EMC_CHART_CLASS, build_emc_area
from src.run_demo.execute_scenario import execute_scenario
from src.shared.make_disclaimer_block import make_disclaimer_block

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)

#: 三流程的合法场景参数（各 sim 编排的最小入参——真跑经 execute_scenario）。
_FLOW_SCENARIOS = {
    "conduction": {"freq_hz": [10e6, 30e6], "limit_line_dbmv": 60.0},
    "radiation": {"center_hz": 100e6, "span_hz": 1e6},
    "sweep": {"band": "cispr_b", "step_hz": 5e6},
}

#: 三流程图谱段 kind（页区渲染锚点——负载形态归一口径）。
_CHART_KINDS = {
    "conduction": "conduction_readings",
    "radiation": "radiation_spectrum",
    "sweep": "sweep_points",
}


def _pipeline_runner(scenario):
    """真跑 runner：execute_scenario 分派→emc_payload 直给契约通道（通道①）。"""
    outcome = execute_scenario({"scenario": scenario}, scenario)
    return {
        "run_id": "20260101-000000",
        "status": outcome["status"],
        "exit_code": 0,
        "emc_payload": outcome["result"],
    }


# ---- 纯函数：三流程分派可达+声明字段（R68 验收真身） ----


def test_emc_view_three_flows_reachable_with_disclaimer():
    """① 三流程各自可达：真跑 runner（execute_scenario 分派）→ok=True+图谱段
    （kind/平行列表非空）+simulated=True+disclaimer=make_disclaimer_block('emc')
    原文（强制模拟口径声明——读数绝不冒充实测）。"""
    for flow in EMC_FLOWS:
        view = demo_emc_flows(flow, _FLOW_SCENARIOS[flow], _pipeline_runner)
        assert view["ok"] is True
        assert view["flow"] == flow
        assert view["simulated"] is True  # 强制模拟口径声明
        assert view["disclaimer"] == make_disclaimer_block("emc")
        chart = view["chart"]
        assert chart["kind"] == _CHART_KINDS[flow]  # 图谱段形态归一
        assert chart["freq_hz"]  # 平行列表非空（图谱上屏有数据）
        if flow == "conduction":
            assert len(chart["power_dbuv"]) == len(chart["freq_hz"])
            assert len(chart["margin_db"]) == len(chart["freq_hz"])
        elif flow == "radiation":
            assert len(chart["power_db"]) == len(chart["freq_hz"])
        else:
            assert len(chart["power_dbm"]) == len(chart["freq_hz"])
            assert len(chart["spurious"]) == len(chart["freq_hz"])
        assert view["payload"]  # sim 编排结果原对象收割在案
        # 发起场景审计留痕：scenario_type='emc'+emc_flow=流程键+表单参数原样并入
        assert view["scenario"]["scenario_type"] == "emc"
        assert view["scenario"]["emc_flow"] == flow


def test_emc_view_scenario_passed_verbatim_to_runner():
    """② 表单参数原样并入场景交 runner（params dict → scenario dict，不经
    篡改）：runner 捕获到的场景即 {'scenario_type','emc_flow', **params}。"""
    captured = {}

    def _runner(scenario):
        captured.update(scenario)
        return {"emc_payload": {"points": [{"freq_hz": 1e6, "power_dbm": -100.0}]}}

    view = demo_emc_flows("sweep", {"band": "cispr_a", "step_hz": 1e6}, _runner)
    assert view["ok"] is True
    assert captured == {
        "scenario_type": "emc",
        "emc_flow": "sweep",
        "band": "cispr_a",
        "step_hz": 1e6,
    }


def test_emc_view_clipping_warnings_merged_not_rejected():
    """③ 频率域越界裁剪并标注（沿用 R33–R35）：conduction 请求 5GHz（超出模拟
    接收机域 3GHz 顶）→不拒，sim warnings 原文并入演示视图+图谱仍上屏。"""
    view = demo_emc_flows("conduction", {"freq_hz": 5e9}, _pipeline_runner)
    assert view["ok"] is True  # 裁剪标注不拒
    assert view["warnings"], "越域 warnings 须并入演示视图"
    assert any("裁剪" in item for item in view["warnings"])
    assert view["chart"] is not None  # 裁剪后图谱照常上屏
    assert view["chart"]["freq_hz"][0] == 3e9  # 裁剪到最近域边界


def test_emc_view_flow_normalization_and_shape_errors():
    """④ flow 归一（strip().lower()，大小写不敏感）+形状错先拒：未知 flow/
    params 非 dict|None/runner 不可调用/runner 返回非 dict → ValueError。"""
    view = demo_emc_flows("  CONDUCTION  ", {"freq_hz": 10e6}, _pipeline_runner)
    assert view["flow"] == "conduction"  # 大小写+空白归一
    with pytest.raises(ValueError, match="flow 必须为"):
        demo_emc_flows("bogus", {}, _pipeline_runner)
    with pytest.raises(ValueError, match="params 必须为 dict"):
        demo_emc_flows("sweep", ["band"], _pipeline_runner)
    with pytest.raises(ValueError, match="runner 必须可调用"):
        demo_emc_flows("sweep", {}, "not-callable")
    with pytest.raises(ValueError, match="runner 返回值必须为结果 dict"):
        demo_emc_flows("sweep", {}, lambda scenario: "oops")


def test_emc_view_harvest_channels_result_and_run_dir(tmp_path):
    """⑤ 负载收割通道②③：result['result'] 直给负载 / run_dir 下 result.json
    的 scenario_result（run_scenario 形态——操控台缺省 runner 真跑落点）。"""
    payload = {
        "points": [{"freq_hz": 1e6, "power_dbm": -100.0}],
        "warnings": ["w1"],
    }
    # 通道②：result['result'] 即负载形态（携带 points 标记键）
    view = demo_emc_flows(
        "sweep", {}, lambda sc: {"status": "done", "exit_code": 0, "result": payload}
    )
    assert view["payload"] is payload
    assert view["chart"]["kind"] == "sweep_points"
    assert view["warnings"] == ["w1"]  # 负载 warnings 原样并入
    # 通道③：run_dir/result.json 的 scenario_result.result（内层即 sim 编排结果）
    run_dir = tmp_path / "20260101-000001"
    run_dir.mkdir()
    with open(run_dir / "result.json", "w", encoding="utf-8") as fh:
        json.dump(
            {
                "run_id": "20260101-000001",
                "scenario_result": {"status": "completed", "result": payload},
            },
            fh,
        )
    view = demo_emc_flows(
        "sweep",
        {},
        lambda sc: {"status": "done", "exit_code": 0, "run_dir": str(run_dir)},
    )
    assert view["payload"] == payload
    assert view["run"]["run_id"] == "20260101-000001"  # run_dir 尾段即运行号
    assert view["chart"]["freq_hz"] == [1e6]


def test_emc_view_missing_payload_chart_none_honest_note():
    """⑥ 三通道皆无（runner 结果无负载形态键且 run_dir 不可得）→chart=None
    +payload=None+如实标注（note 含说明）——不虚构不抛。"""
    view = demo_emc_flows(
        "radiation", {}, lambda sc: {"status": "done", "exit_code": 0}
    )
    assert view["ok"] is True  # 演示态继续（不抛）
    assert view["chart"] is None and view["payload"] is None
    assert "未读到 EMC 结果负载" in view["note"]  # 如实标注
    assert view["simulated"] is True  # 声明仍恒带
    assert view["disclaimer"] == make_disclaimer_block("emc")


def test_emc_view_scenario_error_propagates():
    """⑦ 场景非法→校验错误原样上抛（runner 内部 ValueError 族不吞不换——端点
    层落运行表 failed 附原文）。"""
    with pytest.raises(ValueError, match="缺 'freq_hz'"):
        demo_emc_flows("conduction", {}, _pipeline_runner)


# ---- 端点合约：POST /api/emc/{flow}（202+运行表轮询终态） ----


def _client(tmp_path):
    """装配真 app+真跑 runner（execute_scenario 分派——tmp report_root 落运行）。"""
    reports = tmp_path / "reports"
    deps = {
        "runner": _pipeline_runner,
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path),
        "report_root": str(reports),
        "static_pages": {},
    }
    return TestClient(create_console_app(deps))


def _poll_done(client, run_id, timeout_s=10.0) -> dict:
    """轮询 GET /api/runs/{id} 至终态（done/failed），返回终态条目。"""
    deadline = time.monotonic() + timeout_s
    entry = client.get(f"/api/runs/{run_id}").json()
    while entry["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        entry = client.get(f"/api/runs/{run_id}").json()
    return entry


@needs_fastapi
def test_emc_view_endpoint_submit_and_poll_done(tmp_path):
    """⑧ 端点：POST /api/emc/sweep {'params'}→202 运行句柄（run_id/poll）→
    轮询 done 附演示视图（图谱+声明字段上屏口径同纯函数）。"""
    client = _client(tmp_path)
    resp = client.post(
        "/api/emc/sweep", json={"params": {"band": "cispr_b", "step_hz": 5e6}}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["flow"] == "sweep" and body["run_id"]
    entry = _poll_done(client, body["run_id"])
    assert entry["status"] == "done"
    view = entry["result"]
    assert view["ok"] is True and view["simulated"] is True
    assert view["disclaimer"] == make_disclaimer_block("emc")
    assert view["chart"]["kind"] == "sweep_points"


@needs_fastapi
def test_emc_view_endpoint_unknown_flow_and_bad_params_rejected(tmp_path):
    """⑨ 端点形状错→400 字段级指错：未知 flow→field='flow'；params 非 dict→
    field='params'；请求体非 JSON 对象→field='params'（错误信息上屏）。"""
    client = _client(tmp_path)
    resp = client.post("/api/emc/bogus", json={"params": {}})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "flow"
    resp = client.post("/api/emc/sweep", json={"params": ["band"]})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "params"
    resp = client.post(
        "/api/emc/sweep",
        content=b"[1,2]",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "params"


# ---- 页区静态资产（serve_console instruments 页注入的 EMC 表单区） ----


def test_emc_view_emc_area_zero_external_links_and_anchors():
    """⑩ 页区资产：零外链（无 http(s):// 字面——R56 断网全可用口径）+同源
    fetch 端点字面（/api/emc/、/api/runs/）+三流程选项+图谱 class 锚点。"""
    block = build_emc_area()
    assert "http://" not in block and "https://" not in block
    assert 'id="emc-flows-area"' in block  # 挂载区块锚点
    assert "/api/emc/" in block and "/api/runs/" in block  # 同源相对路径 fetch
    for flow in EMC_FLOWS:
        assert f"'{flow}'" in block  # 三流程下拉选项
    assert EMC_CHART_CLASS in block  # 图谱折线 class 锚点（canvas）
    assert "发起 EMC 演示" in block
