"""demo_rl_policy 单测（R73）：sim 小闭环冒烟一轮（动作序列/回报上屏+固定种子
复现）+不收敛回退固定策略如实标注（rounds=1 前后半同轮必不收敛——确定性回退
分支）+rounds 域错拒绝+端点合约（POST /api/demo/rl）+页区静态资产零外链。
用例名统一 ``test_rl_view_`` 前缀（`pytest -k rl_view` 发现——R73 核验命令
真身：冒烟一轮+回退分支）。

被测实现口径见 src/demo_rl_policy/demo_rl_policy.py 模块 docstring
（run_rl_policy 短轮次固定参数/fallback_fixed_strategy 回退兜底）。
"""
import tempfile

import pytest

try:  # 端点合约用——fastapi 缺库环境整组端点用例 skip
    from fastapi.testclient import TestClient

    from src.serve_console.create_console_app import create_console_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

from src.demo_rl_policy.demo_rl_policy import (
    DEMO_ACTIONS,
    DEMO_JS_LEVELS_DB,
    DEMO_MAX_STEPS,
    DEMO_ROUNDS,
    demo_rl_policy,
)
from src.demo_rl_policy.rl_area import RL_FALLBACK_CLASS, build_rl_policy_area

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)


# ---- 冒烟一轮（R73 验收真身①） ----


def test_rl_view_smoke_round_default_converges():
    """① 缺省冒烟：sim 小闭环 8 轮——动作序列/回报曲线上屏字段齐备；固定
    种子下缺省参数收敛（policy=ql_table，末半程平均回报改善）。"""
    view = demo_rl_policy()
    assert view["ok"] is True and view["simulated"] is True
    assert view["rounds"] == DEMO_ROUNDS == 8
    assert view["action_space"] == DEMO_ACTIONS == len(DEMO_JS_LEVELS_DB)
    assert view["max_steps"] == DEMO_MAX_STEPS
    assert len(view["reward_history"]) == DEMO_ROUNDS
    assert all(isinstance(r, float) for r in view["reward_history"])
    assert len(view["action_sequence"]) == DEMO_MAX_STEPS
    assert all(isinstance(a, int) and 0 <= a < DEMO_ACTIONS for a in view["action_sequence"])
    assert view["converged"] is True and view["fallback_used"] is False
    assert view["policy"] == "ql_table" and view["fallback_note"] is None
    assert view["n_states"] > 0 and len(view["q_table_shape"]) == 2
    assert "sim" in view["note"] and "不开放辐射" in view["note"]


def test_rl_view_fixed_seed_reproducible():
    """② 固定种子复现：同参数两次演示 reward_history/动作序列一致。"""
    first = demo_rl_policy(4)
    second = demo_rl_policy(4)
    assert first["reward_history"] == second["reward_history"]
    assert first["action_sequence"] == second["action_sequence"]


def test_rl_view_rounds_override():
    """③ rounds 透传：rounds=3 → episodes=3、曲线 3 点。"""
    view = demo_rl_policy(3)
    assert view["rounds"] == 3 and len(view["reward_history"]) == 3


# ---- 回退分支（R73 验收真身②——R54 口径如实标注） ----


def test_rl_view_fallback_branch_single_round():
    """④ 回退分支：rounds=1 时前后半同轮必不收敛→fallback_used=True、
    policy='fallback_fixed'、fallback_plan 非空（固定样式×GB 阶梯）+回退原因
    注明（不粉饰）。"""
    view = demo_rl_policy(1)
    assert view["rounds"] == 1
    assert view["converged"] is False and view["fallback_used"] is True
    assert view["policy"] == "fallback_fixed"
    assert isinstance(view["fallback_plan"], list) and view["fallback_plan"]
    first = view["fallback_plan"][0]
    assert first["action"] == "emit" and "style" in first and "target_db" in first
    assert view["fallback_note"] is not None
    assert "未收敛" in view["fallback_note"] and "回退" in view["fallback_note"]


# ---- 参数域错 ----


def test_rl_view_rounds_domain_errors():
    """⑤ rounds 域错：bool/非 int/非正/超 64 上限→ValueError 先拒。"""
    for bad in (True, 0, -3, "8", 2.0, 65):
        with pytest.raises(ValueError, match="rounds"):
            demo_rl_policy(bad)


# ---- 端点合约：POST /api/demo/rl ----


def _client():
    """装配真 app（deps 最小五键——端点注册经 create_console_app 内接线）。"""
    tmp = tempfile.mkdtemp()
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": tmp,
        "report_root": tmp,
        "static_pages": {},
    }
    return TestClient(create_console_app(deps))


@needs_fastapi
def test_rl_view_endpoint_contract():
    """⑥ 端点合约：POST /api/demo/rl（body 可空/{'rounds'}）→200 演示视图；
    rounds 域错→400 field='rounds'（失败原因上屏不静默）。"""
    client = _client()

    resp = client.post("/api/demo/rl", json={})
    assert resp.status_code == 200
    view = resp.json()
    assert view["ok"] is True and view["rounds"] == DEMO_ROUNDS

    resp = client.post("/api/demo/rl", json={"rounds": 1})
    assert resp.status_code == 200
    assert resp.json()["fallback_used"] is True  # 单轮回退分支经端点可达

    resp = client.post("/api/demo/rl", json={"rounds": "eight"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "rounds"

    resp = client.post(
        "/api/demo/rl", content=b"", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 200  # 空 body 容忍（rounds 缺省）

    resp = client.post("/api/demo/rl", json=[1, 2])
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "rounds"


# ---- 页区静态资产（serve_console instruments 页注入的 RL 策略演示页区） ----


def test_rl_view_area_zero_external_links_and_anchors():
    """⑦ 页区资产：零外链+同源 fetch 端点字面（/api/demo/rl）+区块锚点+
    回退标注 class 锚点+回报曲线/动作序列渲染锚点。"""
    block = build_rl_policy_area()
    assert "http://" not in block and "https://" not in block
    assert 'id="rl-policy-area"' in block  # 挂载区块锚点
    assert "'/api/demo/rl'" in block  # 同源相对路径 fetch
    assert "reward_history" in block and "action_sequence" in block  # 两上屏锚点
    assert RL_FALLBACK_CLASS in block and "fallback_plan" in block  # 回退如实标注
