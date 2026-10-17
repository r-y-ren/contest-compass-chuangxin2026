"""resolve_base_tx_gain 测试：缺省 60dB 锚、标定钩子替换位、(0, 80] 守卫（越界/非有限拒绝）、
sim/replay 后端不依赖本模块（纯 Python 文本扫描）、纯函数无副作用。
R95 验收继承：pytest -k b210_gain_mapping 族的上游件（run_demo._backend_params 与
set_channel_attenuation._dispatch_backend 消费本函数）。"""
from __future__ import annotations

from pathlib import Path

import pytest

import src.shared.resolve_base_tx_gain as gain_module
from src.shared.resolve_base_tx_gain import resolve_base_tx_gain

# fn_work 根（tests/shared/ 上两级），供 sim/replay 源码目录的文本扫描定位。
_FN_WORK_ROOT = Path(__file__).resolve().parents[2]


def test_default_anchor_is_60db_float():
    """① 缺省保守常量锚：60.0（C 相位实测锚），且返回类型为 float。"""
    value = resolve_base_tx_gain()
    assert value == 60.0
    assert isinstance(value, float)


def test_hook_value_used_when_provided(monkeypatch):
    """② 标定钩子命中：monkeypatch 返回 70 → 采用并归一为 float 70.0；
    上边界 80.0 本身合法（硬上限含边界）。"""
    monkeypatch.setattr(gain_module, "_resolve_from_calibration_hook", lambda: 70)
    assert resolve_base_tx_gain() == 70.0
    assert isinstance(resolve_base_tx_gain(), float)
    monkeypatch.setattr(gain_module, "_resolve_from_calibration_hook", lambda: 80.0)
    assert resolve_base_tx_gain() == 80.0


def test_hook_none_falls_back_to_default(monkeypatch):
    """②补 钩子显式 None（标定未落地占位形状）→ 回落缺省常量 60.0。"""
    monkeypatch.setattr(gain_module, "_resolve_from_calibration_hook", lambda: None)
    assert resolve_base_tx_gain() == 60.0


@pytest.mark.parametrize(
    "bad", [80.5, 0, -1, float("nan"), float("inf"), True, False]
)
def test_hook_out_of_range_rejected(monkeypatch, bad):
    """③ 越界即拒：>80、≤0、NaN/inf → ValueError，消息带原值与可达域 (0, 80]。
    对抗审查 M1（2026-10-17）：bool 拒——bool 是 int 子类，修前 True 被数学
    比较当作 1.0 落入可达域接受；对齐 _as_real 全仓口径（bool 先拒）。"""
    monkeypatch.setattr(gain_module, "_resolve_from_calibration_hook", lambda: bad)
    with pytest.raises(ValueError) as exc_info:
        resolve_base_tx_gain()
    message = str(exc_info.value)
    assert repr(bad) in message
    assert "(0, 80]" in message


def test_sim_and_replay_backends_do_not_import_this_module():
    """④ sim/replay 不受扰：src/open_sim_backend 与 src/open_replay_backend 下全部
    .py 文件（纯 Python 文本扫描，不调 shell）不得出现本模块名 resolve_base_tx_gain。"""
    targets = [
        _FN_WORK_ROOT / "src" / "open_sim_backend",
        _FN_WORK_ROOT / "src" / "open_replay_backend",
    ]
    scanned = 0
    for directory in targets:
        py_files = sorted(directory.rglob("*.py"))
        assert py_files, f"扫描目录意外为空: {directory}"
        for py_file in py_files:
            scanned += 1
            text = py_file.read_text(encoding="utf-8")
            assert "resolve_base_tx_gain" not in text, (
                f"{py_file} 引用了 resolve_base_tx_gain（sim/replay 不得依赖本模块）"
            )
    assert scanned >= 4  # 两目录各含 __init__.py 等至少两件，确认确已扫到源码


def test_pure_function_stable_across_calls():
    """⑤ 纯函数无副作用：两次调用同值；模块常量与钩子占位状态不被改动。"""
    first = resolve_base_tx_gain()
    second = resolve_base_tx_gain()
    assert first == second == 60.0
    assert gain_module._DEFAULT_BASE_TX_GAIN_DB == 60.0
    assert gain_module._resolve_from_calibration_hook() is None
