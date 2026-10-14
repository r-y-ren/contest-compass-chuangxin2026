"""dataset_view_e2e / replay_run：真服务+真跑一次 record:true 最小 sim 运行→建
索引→数据页卡片可见→过滤→一键回放→回放运行 exit 0 端到端（R63+R64 决定性防回归）。

- 用例名统一 ``test_dataset_view_e2e_`` 前缀（`pytest -k dataset_view_e2e` 发现）；
  模块名 ``test_replay_run_e2e``（`pytest -k replay_run` 经模块关键字发现）——
  R64 核验命令 ``replay_run`` 的真身（回放运行 exit 0 端到端）。

验收链（数据与回放垂直切片）：
- 真运行：serve_console dry_run **缺省 runner**（真跑 sim 场景，抄
  test_report_view_e2e 的真运行模式）→POST /api/run record:true 薄载荷→轮询至
  done→report_root 下真实 run 目录（recordings/ SigMF 真值对+scenario.yaml）；
- 建索引：浏览器数据页「重建索引」按钮（初始未建索引提示态）→POST
  /api/dataset/rebuild→卡片可见（样式/功率/时长/批次/运行来源真值）；
- 过滤：样式不命中→空态；样式命中+日期区间→单卡；
- 一键回放：卡片「回放此条」→POST /api/run/replay→202→GET /api/runs/{id}
  轮询至 done→result.exit_code==0（回放运行 completed——R64 验收原文）。

环境缺 playwright/uvicorn/fastapi 时整族 skip。
"""
import json
import socket
import threading
import time
import urllib.request

import pytest

try:  # uvicorn+fastapi 同源依赖——任一缺失即整族 skip
    import uvicorn

    from src.serve_console.serve_console import serve_console

    _HAS_SERVER = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_SERVER = False

try:  # playwright 浏览器侧证据——缺失即整族 skip
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_PLAYWRIGHT = False

needs_e2e = pytest.mark.skipif(
    not (_HAS_PLAYWRIGHT and _HAS_SERVER),
    reason="环境缺 playwright/uvicorn/fastapi——e2e 不可用",
)

#: 最小 record:true sim 场景（gb42590 快路径：dwell 0/judge 2/baseline 10——秒级
#: 完成；sim 事件缺省 jsr=-20 恒不触发判据 → completed；record:true 产出 SigMF）。
_REC_FAST_YAML = """\
style: tone
fs: 1.0e6
freq_hz: 2.4e9
power_dbm: -10
duration_s: 0.005
backend: sim
scenario_type: gb42590
judge_min_samples: 2
dwell_s: 0.0
baseline_samples: 10
record: true
bands:
  - [2400.0, 2483.5]
shielded_box: true
dut_scope: self_built
"""


def _free_port() -> int:
    """取一个当前空闲的本地端口（bind(0) 后立即释放，随机端口化解占用冲突）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _post(base: str, path: str, payload: "dict | None" = None) -> dict:
    """真 HTTP POST（urllib——打真 uvicorn 端口，非 TestClient）。"""
    data = json.dumps(payload if payload is not None else {}).encode("utf-8")
    with urllib.request.urlopen(
        urllib.request.Request(
            base + path,
            method="POST",
            data=data,
            headers={"Content-Type": "application/json"},
        ),
        timeout=30,
    ) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


@pytest.fixture(scope="module")
def console_server(tmp_path_factory):
    """真服务（线程内 uvicorn.Server+config，随机端口）：serve_console dry_run
    **缺省 runner** 装配（POST /api/run 即真跑 sim；POST /api/run/replay 经同一
    runner 真跑 replay 后端）；scenario_dir 预置 rec_fast 场景。返回
    {'base': http://…}。"""
    tmp_path = tmp_path_factory.mktemp("replay_run_e2e")
    sdir = tmp_path / "scenarios"
    sdir.mkdir()
    (sdir / "rec_fast.yaml").write_text(_REC_FAST_YAML, encoding="utf-8")
    rroot = tmp_path / "reports"
    rroot.mkdir()
    result = serve_console(
        {
            "scenario_dir": str(sdir),
            "report_root": str(rroot),
            "port": 18132,  # dry_run 不真占用，仅形状合法
            "host": "127.0.0.1",
            "dry_run": True,
            "stop_flag": {"flag": False},
        }
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(result["app"], host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True, name="replay-run-e2e")
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not server.started:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        pytest.fail("uvicorn 未能在 10s 内启动（e2e 前置失败）")
    yield {"base": f"http://127.0.0.1:{port}"}
    server.should_exit = True  # 结束关服务
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def recorded_run(console_server):
    """真跑一次 record:true 最小 sim 运行至终态，返回 (run_name, result)——
    run_name 即 report_root 下运行目录名（数据页卡片/回放端点的 run_id 口径）。"""
    base = console_server["base"]
    run_uuid = _post(base, "/api/run", {"scenario": {"name": "rec_fast"}})["run_id"]
    entry = None
    deadline = time.monotonic() + 120  # sim 快路径秒级，120s 足够宽
    while time.monotonic() < deadline:
        entry = _get_json(base, f"/api/runs/{run_uuid}")
        if entry["status"] != "running":
            break
        time.sleep(0.2)
    assert entry is not None and entry["status"] == "done"
    result = entry["result"]
    assert result["status"] == "completed"  # 真跑完成（非校验失败回执）
    run_name = result["run_dir"].rstrip("/").split("/")[-1]
    return run_name, result


@needs_e2e
def test_dataset_view_e2e_rebuild_cards_filter_replay_exit_zero(
    console_server, recorded_run
):
    """R63+R64 主链路端到端：真录制运行→数据页（未建索引提示→浏览器点重建→
    卡片可见→样式/日期过滤）→一键回放（浏览器点「回放此条」）→回放运行
    exit 0。"""
    base = console_server["base"]
    run_name, _ = recorded_run

    # ---- ① 浏览器：数据页初始未建索引提示态 → 点「重建索引」→ 卡片可见 ----
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.goto(f"{base}/pages/data", timeout=15000)
            assert page.locator("#dataset-library-area").count() == 1  # 区块注入在位
            # 未建索引提示态（hint 文案+重建入口在位）
            page.wait_for_function(
                "() => document.getElementById('dsla-status') && "
                "document.getElementById('dsla-status').textContent.indexOf('未建') >= 0",
                timeout=10000,
            )
            page.click("#dsla-rebuild")  # 浏览器侧触发 POST /api/dataset/rebuild
            card = page.wait_for_selector(
                f"#dataset-grid .dataset-card[data-run='{run_name}']", timeout=15000
            )
            assert card is not None
            card_text = card.text_content()

            # ---- ② 卡片真值字段（样式/功率/时长/批次占位/运行来源） ----
            assert "tone" in card_text  # 样式（场景副本真值）
            assert "-10" in card_text  # 功率 dBm
            assert "0.005" in card_text  # 时长 s
            assert run_name in card_text  # 运行来源
            assert "回放此条" in card_text  # R64 一键回放按钮

            # ---- ③ 过滤：样式不命中→空态；命中+日期→单卡 ----
            page.fill("#dsla-style", "chirp")
            page.click("#dsla-apply")
            page.wait_for_function(
                "() => document.querySelectorAll('#dataset-grid .dataset-card').length === 0",
                timeout=10000,
            )
            page.fill("#dsla-style", "tone")
            today = time.strftime("%Y%m%d")
            page.fill("#dsla-date-from", today)
            page.fill("#dsla-date-to", today)
            page.click("#dsla-apply")
            page.wait_for_selector(
                f"#dataset-grid .dataset-card[data-run='{run_name}']", timeout=10000
            )
            # 日期不命中（明天区间）→空态
            page.fill("#dsla-date-from", "29991231")
            page.fill("#dsla-date-to", "29991231")
            page.click("#dsla-apply")
            page.wait_for_function(
                "() => document.querySelectorAll('#dataset-grid .dataset-card').length === 0",
                timeout=10000,
            )

            # ---- ④ 一键回放：点「回放此条」→202→轮询至 done → exit 0 ----
            page.fill("#dsla-style", "tone")
            page.fill("#dsla-date-from", "")
            page.fill("#dsla-date-to", "")
            page.click("#dsla-apply")
            replay_button = page.wait_for_selector(
                f"#dataset-grid .dataset-card[data-run='{run_name}'] button.replay-btn",
                timeout=10000,
            )
            with page.expect_response(
                lambda resp: resp.url.endswith("/api/run/replay")
                and resp.request.method == "POST"
            ) as response_info:
                replay_button.click()
            replay_resp = response_info.value
            assert replay_resp.status == 202
            replay_uuid = replay_resp.json()["run_id"]
            assert replay_resp.json()["replay_of"] == run_name

            # 浏览器状态行终态：回放完成 exit_code=0 上屏
            page.wait_for_function(
                "() => document.getElementById('dsla-status') && "
                "document.getElementById('dsla-status').textContent.indexOf('回放完成') >= 0"
                " && document.getElementById('dsla-status').textContent.indexOf('exit_code=0') >= 0",
                timeout=120000,
            )
        finally:
            browser.close()

    # ---- ⑤ API 侧终局证据：运行表 done + result.exit_code==0 + completed ----
    entry = None
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        entry = _get_json(base, f"/api/runs/{replay_uuid}")
        if entry["status"] != "running":
            break
        time.sleep(0.3)
    assert entry is not None and entry["status"] == "done"
    outcome = entry["result"]
    assert outcome["exit_code"] == 0  # R64 验收原文：回放运行 exit 0
    assert outcome["status"] == "completed"
    assert outcome["backend"] == "replay"
    assert outcome["scenario"]["sigmf_path"].endswith(".sigmf-meta")
    assert entry["replay_of"] == run_name  # 来源运行留痕


@needs_e2e
def test_dataset_view_e2e_replay_unknown_entry_error_in_response(console_server):
    """录音条目不在库→POST /api/run/replay 400 带指错（错误信息进响应上屏
    口径——损坏录音的同族装载期拒绝形状；文件级损坏分支由单测覆盖）。"""
    import urllib.error

    base = console_server["base"]
    rebuilt = _post(base, "/api/dataset/rebuild")  # 自足前置：索引在库
    assert rebuilt["index_status"] == "ready"
    try:
        _post(base, "/api/run/replay", {"run_id": "19700101-000000"})
        raise AssertionError("不在库条目应 400")
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        payload = json.loads(exc.read().decode("utf-8"))
        assert payload["detail"]["field"] == "run_id"  # 指错进响应
        assert "不在库" in payload["detail"]["error"]
