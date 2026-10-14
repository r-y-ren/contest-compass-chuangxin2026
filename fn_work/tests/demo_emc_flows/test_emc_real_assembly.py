"""EMC 三流程**真装配**集成测试（走查环 F1 修复，2026-10-14）：TestClient 起
serve_console **缺省 runner** 的真 app（不注入 runner——POST /api/emc/{flow}
走 _make_default_runner→run_scenario 真跑），缺省表单参数 {'params': {}} → 202 →
轮询 done 且 status 非 failed——此前 demo_emc_flows 构造的场景恒无 'style'，必落
缺省 runner 薄载荷分支报「薄载荷缺 'style' 时须携 'name'」（tests 单测经
_pipeline_runner 旁路直调 execute_scenario 掩盖该缺口；本文件以真装配路径为
唯一集成证据）。用例名统一 ``test_emc_view_real_`` 前缀（`pytest -k emc_view`
发现——随 R68 核验命令族）。

依赖 fastapi/httpx（缺库整组 skip）；真跑三流程共 ~7s（sim 秒级快路径）。
"""
import time

import pytest

try:  # 端点合约用——fastapi 缺库环境整组 skip
    from fastapi.testclient import TestClient

    from src.serve_console.serve_console import serve_console

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

from src.demo_emc_flows.demo_emc_flows import EMC_FLOWS
from src.shared.make_disclaimer_block import make_disclaimer_block

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)

#: 各流程图谱段 kind（真跑负载形态归一——sweep_points/conduction_readings/
#: radiation_spectrum）。
_CHART_KINDS = {
    "conduction": "conduction_readings",
    "radiation": "radiation_spectrum",
    "sweep": "sweep_points",
}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """真 app+**缺省 runner**（dry_run 装配不注入 runner——/api/emc/{flow} 与
    /api/run 同款真实执行器；report_root=tmp 落真实运行目录与报告）。"""
    tmp_path = tmp_path_factory.mktemp("emc_real_assembly")
    reports = tmp_path / "reports"
    reports.mkdir()
    result = serve_console(
        {
            "scenario_dir": str(tmp_path / "scenarios"),
            "report_root": str(reports),
            "port": 18126,  # dry_run 不真占用，仅形状合法
            "host": "127.0.0.1",
            "dry_run": True,
            "stop_flag": {"flag": False},
        }
    )
    return TestClient(result["app"]), str(reports)


def _poll_done(client, run_id: str, timeout_s: float = 60.0) -> dict:
    """轮询 GET /api/runs/{id} 至终态（done/failed），返回终态条目。"""
    deadline = time.monotonic() + timeout_s
    entry = client.get(f"/api/runs/{run_id}").json()
    while entry["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.1)
        entry = client.get(f"/api/runs/{run_id}").json()
    return entry


@needs_fastapi
@pytest.mark.parametrize("flow", EMC_FLOWS)
def test_emc_view_real_assembly_default_params_completed(client, flow):
    """① 真装配主链路（F1 验收真身）：POST /api/emc/{flow} {'params': {}}（表单
    占位符引导的缺省载荷）→ 202 → 轮询 done 且运行 status='completed'（非
    failed——旧口径此载荷必报「薄载荷缺 'style' 时须携 'name'」）。"""
    test_client, _ = client
    resp = test_client.post(f"/api/emc/{flow}", json={"params": {}})
    assert resp.status_code == 202
    body = resp.json()
    assert body["flow"] == flow and body["run_id"]
    entry = _poll_done(test_client, body["run_id"])
    assert entry["status"] == "done", f"真装配运行失败: {entry.get('error')}"
    view = entry["result"]
    assert view["ok"] is True and view["simulated"] is True
    assert view["run"]["status"] == "completed"  # run_scenario 真跑结果（非旁路）
    assert view["run"]["exit_code"] == 0


@needs_fastapi
@pytest.mark.parametrize("flow", EMC_FLOWS)
def test_emc_view_real_assembly_chart_harvested_from_run_dir(client, flow):
    """② 真装配负载收割：演示视图 chart 非空（kind 形态归一+平行列表有数据）+
    声明字段（disclaimer 原文）——负载经 run_dir/result.json 的 scenario_result
    通道（操控台缺省 runner 真跑落点，收割通道③）。"""
    test_client, _ = client
    resp = test_client.post(f"/api/emc/{flow}", json={"params": {}})
    assert resp.status_code == 202
    entry = _poll_done(test_client, resp.json()["run_id"])
    assert entry["status"] == "done", f"真装配运行失败: {entry.get('error')}"
    view = entry["result"]
    assert view["disclaimer"] == make_disclaimer_block("emc")
    chart = view["chart"]
    assert chart is not None and chart["kind"] == _CHART_KINDS[flow]
    assert chart["freq_hz"]  # 平行列表非空（图谱上屏有数据）


@needs_fastapi
def test_emc_view_real_assembly_scenario_run_lands_in_report_root(client):
    """③ 真装配落盘：run 目录真实生成于 report_root（result.json/报告中心可
    见——与 /api/run 同一运行表与目录结构，非旁路无痕）。"""
    import os

    test_client, report_root = client
    before = set(os.listdir(report_root))
    resp = test_client.post("/api/emc/sweep", json={"params": {}})
    entry = _poll_done(test_client, resp.json()["run_id"])
    assert entry["status"] == "done"
    run_dir = entry["result"]["run"]["run_dir"]
    assert run_dir and os.path.isdir(run_dir)
    assert os.path.basename(run_dir) not in before  # 本次真跑新建
    assert os.path.isfile(os.path.join(run_dir, "result.json"))
