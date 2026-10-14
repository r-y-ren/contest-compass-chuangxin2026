"""dataset_view_e2e / replay_run：真服务+真跑一次 record:true 最小 sim 运行→建
索引→数据页卡片可见→过滤→一键回放→回放运行 exit 0 端到端（R63+R64 决定性防回归）。

- 用例名统一 ``test_dataset_view_e2e_`` 前缀（`pytest -k dataset_view_e2e` 发现）；
  模块名 ``test_replay_run_e2e``（`pytest -k replay_run` 经模块关键字发现）——
  R64 核验命令 ``replay_run`` 的真身（回放运行 exit 0 端到端）。

B26 对抗中2 转 B27 随批整改①（e2e 录制场景 num_samples>0）：sim 管线
record:true **结构性出空录音**——execute 阶段收发射后采集阶段监测路恒空读
（read_samples 无发射流）熔断收尾，录制恒 num_samples=0（实测 monitor.csv 仅
表头行），空录音使回放空转也绿。整改：recorded_run 落地后**预置一段合成
SigMF 对**（tone IQ 8192 样本）覆盖空对——回放链消费真实 IQ，终局断言回放
运行 monitor.csv 数据行>0（空转恒仅表头）+源录音 num_samples>0。申报：录音
内容为合成预置（非 sim 采集实录），录制链本身仍走真 record:true 运行。

验收链（数据与回放垂直切片）：
- 真运行：serve_console dry_run **缺省 runner**（真跑 sim 场景，抄
  test_report_view_e2e 的真运行模式）→POST /api/run record:true 薄载荷→轮询至
  done→report_root 下真实 run 目录（recordings/ SigMF 真值对+scenario.yaml）
  →合成 SigMF 对覆盖空录音（整改①）；
- 建索引：浏览器数据页「重建索引」按钮（初始未建索引提示态）→POST
  /api/dataset/rebuild→卡片可见（样式/功率/时长/批次/运行来源真值）；
- 过滤：样式不命中→空态；样式命中+日期区间→单卡；
- 一键回放：卡片「回放此条」→POST /api/run/replay→202→GET /api/runs/{id}
  轮询至 done→result.exit_code==0（回放运行 completed——R64 验收原文）
  →回放消费真实 IQ（monitor 数据行>0——整改①终局证据）。

环境缺 playwright/uvicorn/fastapi 时整族 skip。
"""
import json
import os
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
    run_name 即 report_root 下运行目录名（数据页卡片/回放端点的 run_id 口径）。

    整改①：运行落地后预置一段合成 SigMF 对（tone IQ 8192 样本）覆盖空录音
    ——sim 管线 record:true 结构性出空录音（采集阶段发射已收，监测路恒空读
    熔断），空对让回放空转也绿；合成对使「录制→入库→回放」链消费真实 IQ。"""
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
    run_dir = result["run_dir"]
    _overlay_synthetic_recording(run_dir)  # 整改①：合成对覆盖空录音
    run_name = run_dir.rstrip("/").split("/")[-1]
    return run_name, result


#: 合成录音参数：tone IQ（0.05fs 单音，8192 样本 ≥ nfft 与回放窗），fs/中心频点
#: 与 rec_fast 场景一致（卡片真值/回放沿用不受覆盖影响）。
_SYNTH_N = 8192
_SYNTH_FS = 1.0e6
_SYNTH_FREQ = 2.4e9


def _overlay_synthetic_recording(run_dir: str) -> str:
    """预置合成 SigMF 对（num_samples>0）覆盖 run 的空录音，返回 meta 路径。

    整改①申报口径：录音内容为合成 tone IQ（非 sim 采集实录）——sim 管线
    record:true 结构性出空录音，此处以合成对保住「入库→回放」链的真实 IQ 消费；
    覆盖而非追加（recordings 内仅一对，最早 meta 解析无歧义）。"""
    import numpy as np

    rec_dir = os.path.join(run_dir, "recordings")
    metas = sorted(n for n in os.listdir(rec_dir) if n.endswith(".sigmf-meta"))
    assert metas, "record:true 运行未产出 SigMF 对（录制链前置失败）"
    stem = os.path.join(rec_dir, metas[0][: -len(".sigmf-meta")])
    t = np.arange(_SYNTH_N) / _SYNTH_FS
    iq = (0.5 * np.exp(2j * np.pi * 0.05 * _SYNTH_FS * t)).astype(np.complex64)
    iq.tofile(stem + ".sigmf-data")
    meta = {
        "global": {
            "core:datatype": "cf32_le",
            "core:sample_rate": _SYNTH_FS,
            "core:version": "1.2.0",
            "jam:backend": "sim",
            "jam:run_id": os.path.basename(run_dir.rstrip(os.sep)),
            "core:num_samples": _SYNTH_N,
        },
        "captures": [{"core:sample_start": 0, "core:frequency": _SYNTH_FREQ}],
        "annotations": [
            {
                "core:sample_start": 0,
                "core:sample_count": _SYNTH_N,
                "jam:style": "tone",  # 真值标注（与场景副本 style 一致）
            }
        ],
    }
    with open(stem + ".sigmf-meta", "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    return stem + ".sigmf-meta"


@needs_e2e
def test_dataset_view_e2e_rebuild_cards_filter_replay_exit_zero(
    console_server, recorded_run
):
    """R63+R64 主链路端到端：真录制运行→数据页（未建索引提示→浏览器点重建→
    卡片可见→样式/日期过滤）→一键回放（浏览器点「回放此条」）→回放运行
    exit 0（整改①：回放消费真实 IQ——源录音 num_samples>0+monitor 数据行>0）。"""
    base = console_server["base"]
    run_name, recorded_result = recorded_run

    # ---- 整改①源侧证据：合成对在位且 num_samples>0（空录音不可再漏网） ----
    rec_dir = os.path.join(recorded_result["run_dir"], "recordings")
    src_meta = sorted(n for n in os.listdir(rec_dir) if n.endswith(".sigmf-meta"))[0]
    with open(os.path.join(rec_dir, src_meta), encoding="utf-8") as fh:
        assert json.load(fh)["global"]["core:num_samples"] > 0

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

    # ---- 整改①终局证据：回放消费真实 IQ（非空转）——回放运行 monitor 路有
    # 数据行（空录音回放恒仅表头——监测路读不到任何块）。
    with open(
        os.path.join(outcome["run_dir"], "monitor.csv"), encoding="utf-8"
    ) as fh:
        monitor_rows = sum(1 for _ in fh)
    assert monitor_rows > 1  # 表头+至少一块——真实 IQ 时间轴被回放


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
