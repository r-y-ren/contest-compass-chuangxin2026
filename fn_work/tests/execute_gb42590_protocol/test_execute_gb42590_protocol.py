"""execute_gb42590_protocol 对抗用例：B13 顶层（GB 42590 §5.11 编排，slug=gb42590_executor）。

全 mock（DUT lines/sim 注入 + FakeJamBackend 假后端 + tmp run_dir + dwell 0）：
- 基线窗口经 record_run_streams 采无干扰段（backend 不发射——start_tx 计数见证）；
- 阶梯判据路本函数自管 DUT 采集：sim 事件流/esp32 lines 行流注入（lines 须可重复
  迭代——基线与判据路各起一份驱动）；
- 失效档电平口径：ladder 组合 achieved_db 为衰减量，条目 failure_level_db 取负
  （满增益 0dBm 口径），target_db/achieved 两值入 kpi_snapshot 溯源。
"""
from __future__ import annotations

import json
import os

import pytest

from src.execute_gb42590_protocol.execute_gb42590_protocol import (
    ProtocolError,
    execute_gb42590_protocol,
)

RESULT_KEYS = {
    "status",
    "plan",
    "failure_levels",
    "steps_executed",
    "baseline",
    "stopped_at",
    "note",
}
BASELINE_KEYS = {
    "passed",
    "per_mean",
    "n_samples",
    "n_judged",
    "violations",
    "stop_reason",
    "advice",
}
PLAN_KEYS = {"steps", "truncated_at", "redline_hit", "note"}
MONITOR_PARAMS = {"target_band": (2400.0, 2440.0), "nfft": 64, "max_bins": 4}


class FakeJamBackend:
    """发射/衰减/采集假后端：read_samples 遵真实 list[块] 契约（耗尽恒 []）。"""

    def __init__(self, blocks=None, fail_set_attenuation=False):
        self._blocks = list(blocks or [])
        self._fail = fail_set_attenuation
        self.log = []
        self.start_tx_calls = 0

    def start_tx(self, iq_blocks, effects=None):
        self.start_tx_calls += 1
        self.log.append("start_tx")

    def read_samples(self, max_blocks=1):
        self.log.append("read")
        if self._blocks:
            return [self._blocks.pop(0)]
        return []

    def set_attenuation(self, db):
        self.log.append(f"set_attenuation:{db}")
        if self._fail:
            raise RuntimeError("boom: attenuator lost")

    def stop_tx(self):
        self.log.append("stop_tx")
        return {"status": "stopped"}

    def set_tx_gain(self, gain):
        self.log.append(f"set_tx_gain:{gain}")
        return {"status": "stopped"}


def iq_block(ts, n=8, seed=0):
    """监测原始 IQ 块：n 个复样本 + 块时间戳 ts（ms）。"""
    return {"samples": [complex(seed + 0.1 * i, -0.05 * i) for i in range(n)], "ts": float(ts)}


def make_backend():
    return FakeJamBackend([iq_block(60 + 100 * i, seed=i) for i in range(3)])


def sim_events(n, jsr=-40.0):
    """sim 注入事件流（jsr_db 直给口径，每事件 spe 个样本）。"""
    return [{"type": "power_step", "jsr_db": jsr, "ts": float(i)} for i in range(n)]


def sim_scenario(**over):
    """噪声样式三档低电平场景（dwell 0，判据永不触发）。"""
    scenario = {
        "style": "noise",
        "fs": 1e6,
        "victim_bw_hz": 1e3,
        "freq_mhz": 2420.0,
        "signal_power_db": -20.0,
        "dwell_s": 0.0,
        "ladder": {"start_db": -25.0, "step_db": 5.0, "max_steps": 3},
    }
    scenario.update(over)
    return scenario


def sim_ctx(tmp_path, backend=None, scenario=None, n_events=3, dut=None, **extra):
    ctx = {
        "run_dir": str(tmp_path),
        "backend": backend if backend is not None else make_backend(),
        "scenario": scenario if scenario is not None else sim_scenario(),
        "dut": dut
        if dut is not None
        else {"source": "sim", "samples_per_event": 10},
        "monitor": dict(MONITOR_PARAMS),
        "link_power_db": -20.0,
        "sim_events": sim_events(n_events),
    }
    ctx.update(extra)
    return ctx


def esp32_lines(healthy=10, high=10, tail=10):
    """esp32 帧行：healthy 帧低错包（per 0）→ high 帧高错包（per 0.5）→ tail 帧回落。

    帧给累计 sent/err：healthy 段 err 恒 0（增量 per_raw=0），high 段 err 每帧 +5
    （sent +10 → per_raw=0.5），tail 段 err 持平（per_raw=0）。
    """
    lines = []
    total = healthy + high + tail
    for i in range(1, total + 1):
        if i <= healthy:
            err = 0
        elif i <= healthy + high:
            err = 5 * (i - healthy)
        else:
            err = 5 * high
        lines.append(f"ESP,{i},{i * 10},{err},0,-55")
    return lines


def esp32_ctx(tmp_path, backend=None, lines=None, scenario=None, **extra):
    ctx = {
        "run_dir": str(tmp_path),
        "backend": backend if backend is not None else make_backend(),
        "scenario": scenario if scenario is not None else sim_scenario(),
        "dut": {
            "source": "esp32",
            "serial_config": {"source": "lines", "lines": lines if lines is not None else esp32_lines()},
        },
        "monitor": dict(MONITOR_PARAMS),
        "link_power_db": -20.0,
    }
    ctx.update(extra)
    return ctx


def read_events(tmp_path):
    """events.jsonl 逐行解析（坏行即测试失败——事件是测量真值须严格可解析）。"""
    path = os.path.join(str(tmp_path), "events.jsonl")
    assert os.path.isfile(path), f"events.jsonl 未生成: {path}"
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def event_types(events):
    return [event["type"] for event in events]


# ---------------------------------------------------------------------------
# ① 全流程 sim：三档低电平不失效 → completed + 空失效表 + 每档事件
# ---------------------------------------------------------------------------
def test_gb42590_executor_full_flow_sim_completed(tmp_path):
    result = execute_gb42590_protocol(sim_ctx(tmp_path, n_events=3))

    assert result["status"] == "completed"
    assert result["failure_levels"] == []
    assert result["steps_executed"] == 3
    assert result["stopped_at"] is None
    assert result["baseline"]["passed"] is True
    assert result["plan"]["note"] == "custom"

    events = read_events(tmp_path)
    steps = [e for e in events if e["type"] == "power_step"]
    assert len(steps) == 3
    assert [s["step"] for s in steps] == [0, 1, 2]
    assert [s["target_db"] for s in steps] == [-25.0, -20.0, -15.0]
    assert event_types(events)[-1] == "protocol_stop"


# ---------------------------------------------------------------------------
# ② 第 2 档 PER 超 0.1（lines 注入高错包）→ failed + stopped_at=1 + 条目含 target/achieved
# ---------------------------------------------------------------------------
def test_gb42590_executor_step2_per_failure_records_level(tmp_path):
    backend = make_backend()
    result = execute_gb42590_protocol(esp32_ctx(tmp_path, backend=backend))

    assert result["status"] == "failed"
    assert result["stopped_at"] == 1
    assert result["steps_executed"] == 2

    entry = result["failure_levels"][0]
    # 第 2 档 target −20dBm → 请求衰减 20dB → 实达衰减 20 → 实达电平 −20（满增益 0dBm 口径）
    assert entry["failure_level_db"] == pytest.approx(-20.0)
    assert entry["level_basis"] == "achieved"
    assert entry["step"] == 1
    snapshot = entry["kpi_snapshot"]
    assert snapshot["target_db"] == pytest.approx(-20.0)
    assert snapshot["achieved_attenuation_db"] == pytest.approx(20.0)
    assert entry["per_at_failure"] == pytest.approx(0.5)
    assert backend.start_tx_calls == 1


# ---------------------------------------------------------------------------
# ③ 基线 PER 高 → baseline_rejected 不进阶梯（start_tx 未调）
# ---------------------------------------------------------------------------
def test_gb42590_executor_baseline_high_per_rejected_no_tx(tmp_path):
    backend = make_backend()
    # 全程高错包：基线窗口（首 10 行 per=0.5）均值超 0.05 阈
    lines = [f"ESP,{i},{i * 10},{5 * i},0,-55" for i in range(1, 31)]
    result = execute_gb42590_protocol(esp32_ctx(tmp_path, backend=backend, lines=lines))

    assert result["status"] == "baseline_rejected"
    assert result["baseline"]["passed"] is False
    assert result["baseline"]["stop_reason"] == "baseline_per_exceeded"
    assert result["steps_executed"] == 0
    assert result["failure_levels"] == []
    assert backend.start_tx_calls == 0  # 不进阶梯：干扰发射从未起
    types = event_types(read_events(tmp_path))
    assert "power_step" not in types
    assert types[-1] == "protocol_stop"


# ---------------------------------------------------------------------------
# ④ 带宽不足 → ProtocolError（附两值），未起发射未落事件
# ---------------------------------------------------------------------------
def test_gb42590_executor_bandwidth_insufficient_protocol_error(tmp_path):
    backend = make_backend()
    scenario = sim_scenario(bandwidth_hz=500.0)  # 干扰带宽 500 < 链路带宽 1000
    with pytest.raises(ProtocolError) as excinfo:
        execute_gb42590_protocol(sim_ctx(tmp_path, backend=backend, scenario=scenario))
    assert excinfo.value.jam_bw_hz == pytest.approx(500.0)
    assert excinfo.value.victim_bw_hz == pytest.approx(1000.0)
    assert "500" in str(excinfo.value) and "1000" in str(excinfo.value)
    assert backend.start_tx_calls == 0
    assert not os.path.isfile(os.path.join(str(tmp_path), "events.jsonl"))


# ---------------------------------------------------------------------------
# ⑤ 多音 composite 合成 + 带宽两倍校验过
# ---------------------------------------------------------------------------
def test_gb42590_executor_multitone_composite_double_bandwidth_passes(tmp_path):
    scenario = sim_scenario(style="multi_tone", tone_separation_hz=2e3)
    result = execute_gb42590_protocol(
        sim_ctx(tmp_path, scenario=scenario, n_events=3)
    )

    assert result["status"] == "completed"
    events = read_events(tmp_path)
    assert events[0]["type"] == "protocol_start"
    assert events[0]["style"] == "composite"  # 多音=composite 两单音
    assert events[0]["jam_bw_hz"] == pytest.approx(2e3)  # 两倍链路带宽校验过
    assert events[0]["victim_bw_hz"] == pytest.approx(1e3)
    assert result["steps_executed"] == 3


# ---------------------------------------------------------------------------
# ⑥ jsr 缺（无 jsr_est / 无标定表）→ 条目 jsr unknown
# ---------------------------------------------------------------------------
def test_gb42590_executor_jsr_missing_entry_unknown(tmp_path):
    # 第 2 档高 JSR → 失效；ctx 无 jsr_est / gain_calibration → 条目 jsr_db unknown
    events = sim_events(2, jsr=-40.0)
    events[1] = {"type": "power_step", "jsr_db": 20.0, "ts": 1.0}
    ctx = sim_ctx(tmp_path, n_events=2)
    ctx["sim_events"] = events
    result = execute_gb42590_protocol(ctx)

    assert result["status"] == "failed"
    entry = result["failure_levels"][0]
    assert entry["jsr_db"] == "unknown"
    assert "jsr_db" in entry["missing_fields"]
    assert entry["per_at_failure"] >= 0.9  # 悬崖右端高 PER


# ---------------------------------------------------------------------------
# ⑦ 下发异常（set_attenuation 抛）→ 先停发射（stop_tx 序）再透传
# ---------------------------------------------------------------------------
def test_gb42590_executor_exception_stops_tx_first_then_propagates(tmp_path):
    backend = FakeJamBackend(fail_set_attenuation=True)
    with pytest.raises(RuntimeError, match="boom"):
        execute_gb42590_protocol(sim_ctx(tmp_path, backend=backend, n_events=3))

    log = backend.log
    att_calls = [entry for entry in log if entry.startswith("set_attenuation:")]
    assert att_calls == ["set_attenuation:30.0"]  # 第 1 档（target 25 → 实达组合 30）即炸
    assert "stop_tx" in log
    assert log.index("stop_tx") > log.index("set_attenuation:30.0")  # 先停发射
    assert log.index("start_tx") < log.index("set_attenuation:30.0")
    types = event_types(read_events(tmp_path))
    assert set(types) == {"protocol_start", "baseline"}  # 异常路径不补终止事件
    assert "protocol_stop" not in types


# ---------------------------------------------------------------------------
# ⑧ dwell 透传 ladder（power_step 事件 dwell_s 见证）
# ---------------------------------------------------------------------------
def test_gb42590_executor_dwell_passthrough_to_ladder(tmp_path):
    result = execute_gb42590_protocol(
        sim_ctx(
            tmp_path,
            scenario=sim_scenario(dwell_s=0.25, ladder={"max_steps": 2}),
            n_events=2,
        )
    )
    assert result["status"] == "completed"
    steps = [e for e in read_events(tmp_path) if e["type"] == "power_step"]
    assert len(steps) == 2
    assert all(s["dwell_s"] == 0.25 for s in steps)


# ---------------------------------------------------------------------------
# ⑨ scenario=None 取 ctx['scenario']
# ---------------------------------------------------------------------------
def test_gb42590_executor_scenario_none_falls_back_to_ctx(tmp_path):
    ctx = sim_ctx(tmp_path, scenario=sim_scenario(ladder={"max_steps": 2}), n_events=2)
    assert "scenario" in ctx
    result = execute_gb42590_protocol(ctx)  # scenario 参数缺省
    assert result["status"] == "completed"
    assert result["steps_executed"] == 2


# ---------------------------------------------------------------------------
# ⑩ 返回键集（精确口径）+ plan/baseline 形状
# ---------------------------------------------------------------------------
def test_gb42590_executor_result_key_set(tmp_path):
    result = execute_gb42590_protocol(sim_ctx(tmp_path, n_events=3))
    assert set(result) == RESULT_KEYS
    assert set(result["plan"]) == PLAN_KEYS
    assert set(result["baseline"]) == BASELINE_KEYS
    assert isinstance(result["failure_levels"], list)
    assert isinstance(result["steps_executed"], int)


# ---------------------------------------------------------------------------
# ⑪ 基线 insufficient（判据样本 < min_samples）→ 保守拒绝
# ---------------------------------------------------------------------------
def test_gb42590_executor_baseline_insufficient_rejected(tmp_path):
    backend = make_backend()
    # 基线窗口 3 行 < run_baseline_check min_samples=10 → 保守拒绝不进阶梯
    scenario = sim_scenario(baseline_samples=3)
    result = execute_gb42590_protocol(
        sim_ctx(tmp_path, backend=backend, scenario=scenario, n_events=3)
    )
    assert result["status"] == "baseline_rejected"
    assert result["baseline"]["stop_reason"] == "insufficient_baseline_samples"
    assert result["baseline"]["n_judged"] == 3
    assert backend.start_tx_calls == 0


# ---------------------------------------------------------------------------
# ⑫ ladder truncated 红线 → completed + note truncated
# ---------------------------------------------------------------------------
def test_gb42590_executor_ladder_truncated_redline_completed(tmp_path):
    scenario = sim_scenario()  # 无 'ladder' 键 → GB 缺省：link −20 → −25 起 5dB 步
    scenario.pop("ladder")
    result = execute_gb42590_protocol(
        sim_ctx(tmp_path, scenario=scenario, n_events=6)  # 6 档 × 10 样本
    )
    assert result["status"] == "completed"
    assert "truncated" in result["note"]
    assert result["stopped_at"] is None
    assert result["steps_executed"] == 6
    assert result["plan"]["truncated_at"] == 6
    assert result["plan"]["redline_hit"] is True
    assert result["failure_levels"] == []


# ---------------------------------------------------------------------------
# ⑬ 事件序 baseline→steps→failure→stop，JSONL 逐行可解析
# ---------------------------------------------------------------------------
def test_gb42590_executor_event_order_jsonl_parseable(tmp_path):
    result = execute_gb42590_protocol(esp32_ctx(tmp_path))  # 第 2 档失效流
    assert result["status"] == "failed"

    events = read_events(tmp_path)  # 逐行 json.loads（read_events 内断言）
    types = event_types(events)
    assert types.index("protocol_start") < types.index("baseline")
    assert types.index("baseline") < types.index("power_step")
    assert types.index("power_step") < types.index("ladder_stop")
    assert types.index("ladder_stop") < types.index("failure_level")
    assert types.index("failure_level") < types.index("protocol_stop")
    assert types[-1] == "protocol_stop"
