"""execute_scenario 对抗用例：B21 单场景执行阶段分派器（slug=demo_pipeline 子路）。

全 mock tmp（FakeBackend 假后端 + sim 事件流注入 + tmp run_dir + dwell 0）：
- 四路分派（gb42590/distance/custom/emc）各就各位互不串台（monkeypatch 计数）；
- distance：真 map_distance_to_loss 档计划 + 每档 judge_min_samples 个样本拉取计数
  （sim 事件按 samples_per_event=1 精确配给，拉空即 n_samples 如实）；
- custom：ladder 参数/dwell 透传 + failure_cb 判据接线同 gb 口径（jsr=+10 →
  悬崖模型 per≈0.5 ≥ 0.10 判失效）；
- ScenarioError（ValueError 子类）域：未知/缺失 scenario_type、ctx 缺 scenario、
  非 dict 形状；统一返回键集 {'status','result','streams_note'} 与结果嵌套透传。
"""
from __future__ import annotations

import json

import pytest

import src.run_demo.execute_scenario as es_mod
from src.run_demo.execute_scenario import ScenarioError, execute_scenario

RESULT_KEYS = {"status", "result", "streams_note"}
DISTANCE_RESULT_KEYS = {"status", "distance_plan", "kpi_rows"}
#: 缺省衰减可达域顶 50dB（粗 30 + 细 20）——60dB 档即不可达见证点。
MODEL_PARAMS = {"d0_m": 1.0, "l0_db": 20.0, "n": 2.0, "x_sigma": 0.0}


class FakeBackend:
    """发射/衰减假后端：set_attenuation 记档值，stop_tx 供停发射链路。"""

    def __init__(self):
        self.att_calls: list[float] = []
        self.start_calls = 0
        self.stop_calls = 0

    def start_tx(self, iq_blocks, effects=None):
        self.start_calls += 1

    def set_attenuation(self, db):
        self.att_calls.append(float(db))

    def stop_tx(self):
        self.stop_calls += 1
        return {"status": "stopped"}


def sim_events(n, jsr=-20.0):
    """sim 注入事件流（jsr_db 直给口径；samples_per_event=1 时一事件一样本）。"""
    return [{"type": "power_step", "jsr_db": jsr, "ts": float(i)} for i in range(n)]


def make_ctx(tmp_path, scenario=None, backend=None, n_events=16, jsr=-20.0, **extra):
    ctx = {
        "run_dir": str(tmp_path),
        "backend": backend if backend is not None else FakeBackend(),
        "scenario": scenario,
        "dut": {"source": "sim", "samples_per_event": 1},
        "sim_events": sim_events(n_events, jsr=jsr),
        "link_power_db": -20.0,
    }
    ctx.update(extra)
    return ctx


def gb_scenario(**over):
    scenario = {"scenario_type": "gb42590", "style": "noise", "fs": 1e6}
    scenario.update(over)
    return scenario


def distance_scenario(distances, **over):
    scenario = {
        "scenario_type": "distance",
        "distances": list(distances),
        "model_params": dict(MODEL_PARAMS),
    }
    scenario.update(over)
    return scenario


def custom_scenario(**over):
    scenario = {
        "scenario_type": "custom",
        "ladder": {"start_db": -6.0, "step_db": 3.0, "max_steps": 2},
        "dwell_s": 0.0,
        "judge_min_samples": 2,
    }
    scenario.update(over)
    return scenario


# ---------- ① gb42590 分派：透传 + 键集 + ctx['scenario'] 回落 ----------


def test_gb42590_dispatch_passthrough(tmp_path, monkeypatch):
    sentinel = {
        "status": "failed",
        "plan": {"steps": [{"deep": [1, 2, 3]}]},
        "failure_levels": [{"k": "v"}],
        "steps_executed": 2,
        "baseline": {"passed": True},
        "stopped_at": 1,
        "note": "x",
    }
    calls = []

    def fake_gb(ctx, scenario):
        calls.append((ctx, scenario))
        return sentinel

    monkeypatch.setattr(es_mod, "execute_gb42590_protocol", fake_gb)
    scenario = gb_scenario()
    out = execute_scenario(make_ctx(tmp_path, scenario), scenario)

    assert len(calls) == 1
    assert calls[0][1] is scenario  # 分派入参即原 scenario 对象
    assert out["result"] is sentinel  # 结果原对象透传（嵌套完整）
    assert out["status"] == "failed"  # 外层状态取内层 status
    assert set(out) == RESULT_KEYS
    assert isinstance(out["streams_note"], str)
    assert "record_run_streams" in out["streams_note"]


def test_gb42590_scenario_falls_back_to_ctx(tmp_path, monkeypatch):
    count = {"n": 0}

    def fake_gb(ctx, scenario):
        count["n"] += 1
        assert scenario["scenario_type"] == "gb42590"
        return {"status": "completed"}

    monkeypatch.setattr(es_mod, "execute_gb42590_protocol", fake_gb)
    out = execute_scenario(make_ctx(tmp_path, gb_scenario()))  # scenario 参数缺省
    assert count["n"] == 1
    assert out["status"] == "completed"


# ---------- ② distance 分派：档计划 + 每档采样计数 ----------


def test_distance_dispatch_plan_and_per_step_sampling(tmp_path):
    backend = FakeBackend()
    # 2 个可达档 × 每档 3 样本 = 6 事件（samples_per_event=1，恰好配给不冗余）
    ctx = make_ctx(tmp_path, backend=backend, n_events=6)
    scenario = distance_scenario([1.0, 10.0], judge_min_samples=3)
    out = execute_scenario(ctx, scenario)

    assert out["status"] == "completed"
    res = out["result"]
    assert set(res) == DISTANCE_RESULT_KEYS
    plan = res["distance_plan"]
    assert [p["d_m"] for p in plan["points"]] == [1.0, 10.0]
    assert [p["loss_db"] for p in plan["points"]] == pytest.approx([20.0, 40.0])
    assert plan["unreachable_count"] == 0

    rows = res["kpi_rows"]
    assert len(rows) == 2  # 每可达档一行
    assert [r["n_samples"] for r in rows] == [3, 3]  # 每档恰拉 judge_min_samples 个样本
    assert [r["d_m"] for r in rows] == [1.0, 10.0]
    assert [r["judge_per_mean"] for r in rows] == pytest.approx([0.0, 0.0])  # jsr=-20 无退化
    assert backend.att_calls == [20.0, 40.0]  # 逐档衰减下发（实达值口径）
    assert "distance" in out["streams_note"]


def test_distance_unreachable_point_skipped(tmp_path):
    backend = FakeBackend()
    ctx = make_ctx(tmp_path, backend=backend, n_events=4)  # 仅够 1 可达档 × 4 样本
    scenario = distance_scenario([1.0, 100.0], judge_min_samples=4)  # 100m→60dB 超域
    out = execute_scenario(ctx, scenario)

    res = out["result"]
    plan = res["distance_plan"]
    assert plan["points"][1]["reachable"] is False
    assert plan["points"][1]["combo"] is None
    assert plan["unreachable_count"] == 1
    assert len(res["kpi_rows"]) == 1  # 不可达点不产 KPI 行
    assert res["kpi_rows"][0]["n_samples"] == 4
    assert backend.att_calls == [20.0]  # 不可达档不下发衰减
    assert out["status"] == "completed"  # 容忍口径：跳过不抛


def test_distance_sample_source_exhaustion_counted_honestly(tmp_path):
    backend = FakeBackend()
    ctx = make_ctx(tmp_path, backend=backend, n_events=2)  # 源仅 2 样本 < 每档 5
    scenario = distance_scenario([1.0], judge_min_samples=5)
    out = execute_scenario(ctx, scenario)
    row = out["result"]["kpi_rows"][0]
    assert row["n_samples"] == 2  # 耗尽如实计，不补不造


# ---------- ②b B21 中#2/低#3：distance 落盘 + 标定反杀跳档 ----------


def test_b21_mid2_distance_step_events_and_kpi_csv_written(tmp_path):
    """中#2 回归：每可达档一条 distance_step 事件 + kpi.csv 逐档追加行。

    kpi.csv 列映射 record_run_streams 表头：per/judge_per 两列填 judge_per_mean，
    link='distance'，per_note 携档位溯源（d/loss/att/n）。
    """
    backend = FakeBackend()
    ctx = make_ctx(tmp_path, backend=backend, n_events=6)
    scenario = distance_scenario([1.0, 10.0], judge_min_samples=3)
    execute_scenario(ctx, scenario)

    # a) events.jsonl：每档一条 distance_step（d_m/loss_db/attenuation/judge_per_mean）
    with open(tmp_path / "events.jsonl", encoding="utf-8") as handle:
        events = [json.loads(line) for line in handle if line.strip()]
    steps = [e for e in events if e.get("type") == "distance_step"]
    assert [e["d_m"] for e in steps] == [1.0, 10.0]
    assert [e["loss_db"] for e in steps] == pytest.approx([20.0, 40.0])
    assert all(
        set(("d_m", "loss_db", "attenuation", "judge_per_mean")) <= set(e) for e in steps
    )
    assert steps[0]["attenuation"]["achieved_db"] == pytest.approx(20.0)

    # b) kpi.csv：表头（裸目录自动补）+ 逐档行，列映射到 KPI_HEADER
    with open(tmp_path / "kpi.csv", encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line]
    assert lines[0].split(",")[:3] == ["timestamp_ms", "link", "source"]
    rows = [line.split(",") for line in lines[1:]]
    assert len(rows) == 2
    header = lines[0].split(",")
    assert all(r[header.index("link")] == "distance" for r in rows)
    assert all(
        r[header.index("per")] == r[header.index("judge_per")] for r in rows
    )  # per/judge_per 列同填 judge_per_mean
    assert all("distance_step" in r[header.index("per_note")] for r in rows)


def test_b21_low3_attenuator_cal_shrunk_domain_skips_step_not_raises(tmp_path):
    """低#3 回归：ctx['attenuator_cal'] 缩域致下发超域 → 跳档+skipped 事件，不抛。

    计划按标称口径（model_params 无 cal_table）：d=20m→46.02dB 可达（≤50）；
    下发回落 ctx['attenuator_cal']（细档实际值钳 10dB → 可达域顶 40dB）→
    46.02dB 超域 → AttenuationError 被 _run_distance 消化为跳档：事件
    type='distance_step_skipped'（reason 含可达域），后续档继续执行。
    """
    backend = FakeBackend()
    shrunk_cal = {float(step): float(min(step, 10)) for step in range(0, 21)}
    ctx = make_ctx(
        tmp_path, backend=backend, n_events=6, attenuator_cal=shrunk_cal
    )
    scenario = distance_scenario([1.0, 20.0], judge_min_samples=3)
    out = execute_scenario(ctx, scenario)  # 修复前此处 AttenuationError 反杀整跑

    assert out["status"] == "completed"
    rows = out["result"]["kpi_rows"]
    assert [r["d_m"] for r in rows] == [1.0]  # 缩域档跳过不产 KPI 行
    assert backend.att_calls == [30.0]  # 20dB 档按缩域标定择粗档接入（|20-30| 最小残差）

    with open(tmp_path / "events.jsonl", encoding="utf-8") as handle:
        events = [json.loads(line) for line in handle if line.strip()]
    skipped = [e for e in events if e.get("type") == "distance_step_skipped"]
    assert len(skipped) == 1
    assert skipped[0]["d_m"] == 20.0
    assert "可达域" in skipped[0]["reason"]  # reason 含可达域
    assert skipped[0]["reachable_max_db"] == pytest.approx(40.0)
    assert [e["d_m"] for e in events if e.get("type") == "distance_step"] == [1.0]


# ---------- ③ custom 分派：ladder 透传（dwell/参数）+ 判据接线同 gb 口径 ----------


def test_custom_dispatch_ladder_passthrough_and_failure_cb_wiring(
    tmp_path, monkeypatch
):
    captured = {}

    def fake_ladder(ctx, ladder_params, failure_cb=None, dwell_s=1.0, link_power_db=0.0):
        captured.update(
            ladder_params=ladder_params,
            failure_cb=failure_cb,
            dwell_s=dwell_s,
            link_power_db=link_power_db,
        )
        return {
            "executed": [],
            "stopped_at": None,
            "reason": "complete",
            "plan": {"steps": []},
            "stop_result": {"status": "stopped"},
        }

    monkeypatch.setattr(es_mod, "run_power_ladder", fake_ladder)
    scenario = custom_scenario(dwell_s=0.25, judge_min_samples=4)
    # jsr=+10 → 悬崖模型 per≈0.5 ≥ 0.10：判据回调应判失效（gb 同口径见证）
    ctx = make_ctx(tmp_path, scenario=scenario, n_events=4, jsr=10.0)
    out = execute_scenario(ctx, scenario)

    assert captured["dwell_s"] == 0.25  # dwell 透传
    assert captured["ladder_params"] == scenario["ladder"]  # ladder 参数透传
    assert captured["link_power_db"] == -20.0  # ctx 阶梯基准透传
    assert callable(captured["failure_cb"])
    verdict = captured["failure_cb"]({"step": 0, "target_db": -6.0})
    assert verdict["failed"] is True  # 判据接线同 gb：拉样→归一聚合→check_failure
    assert out["status"] == "completed"  # fake reason=complete
    assert out["result"]["reason"] == "complete"


def test_custom_real_ladder_end_to_end(tmp_path):
    backend = FakeBackend()
    ctx = make_ctx(tmp_path, backend=backend, n_events=4)  # jsr=-20 永不失效
    out = execute_scenario(ctx, custom_scenario())

    res = out["result"]
    assert set(res) == {"executed", "stopped_at", "reason", "plan", "stop_result"}
    assert res["reason"] == "max_steps"
    assert len(res["executed"]) == 2
    assert res["executed"][0]["target_db"] == -6.0
    assert res["executed"][0]["dwell_s"] == 0.0  # dwell 透传进档记录
    assert backend.att_calls == [6.0, 3.0]  # |target| 衰减逐档下发
    assert out["status"] == "completed"
    assert "custom" in out["streams_note"]


def test_custom_failure_reason_maps_to_failed_status(tmp_path, monkeypatch):
    def fake_ladder(ctx, ladder_params, failure_cb=None, dwell_s=1.0, link_power_db=0.0):
        return {"executed": [{}], "stopped_at": 0, "reason": "failure",
                "plan": {}, "stop_result": {}}

    monkeypatch.setattr(es_mod, "run_power_ladder", fake_ladder)
    out = execute_scenario(
        make_ctx(tmp_path), custom_scenario()
    )
    assert out["status"] == "failed"


def test_custom_invalid_threshold_rejected_before_ladder(tmp_path, monkeypatch):
    count = {"n": 0}

    def fake_ladder(*args, **kwargs):
        count["n"] += 1
        return {}

    monkeypatch.setattr(es_mod, "run_power_ladder", fake_ladder)
    with pytest.raises(ValueError):  # check_failure 发射前预检（per_threshold 域 (0,1]）
        execute_scenario(
            make_ctx(tmp_path), custom_scenario(per_threshold=0)
        )
    assert count["n"] == 0  # 预检即拒：ladder 未被触达


def test_custom_dwell_falls_back_to_ctx(tmp_path, monkeypatch):
    captured = {}

    def fake_ladder(ctx, ladder_params, failure_cb=None, dwell_s=1.0, link_power_db=0.0):
        captured["dwell_s"] = dwell_s
        return {"reason": "complete"}

    monkeypatch.setattr(es_mod, "run_power_ladder", fake_ladder)
    scenario = custom_scenario()  # scenario 不给 dwell_s
    del scenario["dwell_s"]
    execute_scenario(make_ctx(tmp_path, dwell_s=0.5), scenario)
    assert captured["dwell_s"] == 0.5  # 两级回落 scenario > ctx > 缺省


# ---------- ④ emc 分派：透传 ----------


def test_emc_dispatch_passthrough(tmp_path, monkeypatch):
    sentinel = {
        "points": [{"freq_hz": 1e6, "power_dbm": -120.0, "nested": {"deep": [1]}}],
        "n_points": 1,
        "n_spurious": 0,
        "simulated": True,
    }
    calls = []

    def fake_emc(ctx, scenario):
        calls.append((ctx, scenario))
        return sentinel

    monkeypatch.setattr(es_mod, "run_emc_sweep", fake_emc)
    scenario = {"scenario_type": "emc", "band": "cispr_a"}
    out = execute_scenario(make_ctx(tmp_path, scenario), scenario)

    assert len(calls) == 1
    assert out["result"] is sentinel  # 嵌套透传完整
    assert out["status"] == "completed"
    assert set(out) == RESULT_KEYS
    assert "emc" in out["streams_note"]


# ---------- ⑤ ScenarioError 域：未知类型 / 缺类型 / 缺 scenario / 形状错 ----------


def test_unknown_scenario_type_rejected(tmp_path):
    ctx = make_ctx(tmp_path)
    with pytest.raises(ScenarioError) as excinfo:
        execute_scenario(ctx, {"scenario_type": "quantum"})
    assert "quantum" in str(excinfo.value)
    assert isinstance(excinfo.value, ValueError)  # ScenarioError 是 ValueError 子类


def test_missing_scenario_type_rejected(tmp_path):
    with pytest.raises(ScenarioError):
        execute_scenario(make_ctx(tmp_path), {"style": "noise"})


def test_ctx_missing_scenario_rejected(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.pop("scenario")
    with pytest.raises(ScenarioError):
        execute_scenario(ctx)  # 两路皆缺（参数缺省 + ctx 缺键）
    with pytest.raises(ScenarioError):
        execute_scenario(ctx, None)


def test_non_dict_shapes_rejected(tmp_path):
    with pytest.raises(ScenarioError):
        execute_scenario("not-a-ctx", gb_scenario())  # ctx 非 dict
    with pytest.raises(ScenarioError):
        execute_scenario(make_ctx(tmp_path), "not-a-scenario")  # scenario 非 dict
    with pytest.raises(ScenarioError):
        execute_scenario(
            make_ctx(tmp_path), {"scenario_type": 42}
        )  # scenario_type 非 str


# ---------- ⑥ 分派不串台 + 入参优先级 ----------


def test_dispatch_no_crosstalk(tmp_path, monkeypatch):
    counters = {"gb": 0, "ladder": 0, "emc": 0}
    monkeypatch.setattr(
        es_mod, "execute_gb42590_protocol",
        lambda ctx, scenario: counters.__setitem__("gb", counters["gb"] + 1)
        or {"status": "completed"},
    )
    monkeypatch.setattr(
        es_mod, "run_power_ladder",
        lambda ctx, p, failure_cb=None, dwell_s=1.0, link_power_db=0.0:
        counters.__setitem__("ladder", counters["ladder"] + 1) or {"reason": "complete"},
    )
    monkeypatch.setattr(
        es_mod, "run_emc_sweep",
        lambda ctx, scenario: counters.__setitem__("emc", counters["emc"] + 1)
        or {"points": []},
    )

    # a) gb42590 场景：只触 gb 编排器
    execute_scenario(make_ctx(tmp_path), gb_scenario())
    assert counters == {"gb": 1, "ladder": 0, "emc": 0}

    # b) distance 场景（真 map 路径）：三个兄弟编排器零调用
    execute_scenario(make_ctx(tmp_path, n_events=4), distance_scenario([1.0, 10.0]))
    assert counters == {"gb": 1, "ladder": 0, "emc": 0}

    # c) custom 场景：只触 ladder
    execute_scenario(make_ctx(tmp_path), custom_scenario())
    assert counters == {"gb": 1, "ladder": 1, "emc": 0}

    # d) emc 场景：只触 emc
    execute_scenario(make_ctx(tmp_path), {"scenario_type": "emc"})
    assert counters == {"gb": 1, "ladder": 1, "emc": 1}


def test_direct_scenario_param_overrides_ctx_scenario(tmp_path, monkeypatch):
    counters = {"gb": 0, "emc": 0}
    monkeypatch.setattr(
        es_mod, "execute_gb42590_protocol",
        lambda ctx, scenario: counters.__setitem__("gb", counters["gb"] + 1)
        or {"status": "completed"},
    )
    monkeypatch.setattr(
        es_mod, "run_emc_sweep",
        lambda ctx, scenario: counters.__setitem__("emc", counters["emc"] + 1)
        or {"points": []},
    )
    ctx = make_ctx(tmp_path, scenario={"scenario_type": "emc"})  # ctx 里是 emc
    execute_scenario(ctx, gb_scenario())  # 直给 gb —— 直给优先
    assert counters == {"gb": 1, "emc": 0}


def test_scenario_type_normalization(tmp_path, monkeypatch):
    count = {"n": 0}

    def fake_gb(ctx, scenario):
        count["n"] += 1
        return {"status": "completed"}

    monkeypatch.setattr(es_mod, "execute_gb42590_protocol", fake_gb)
    scenario = gb_scenario()
    scenario["scenario_type"] = "  GB42590  "  # strip+lower 归一
    out = execute_scenario(make_ctx(tmp_path, scenario), scenario)
    assert count["n"] == 1
    assert out["status"] == "completed"
