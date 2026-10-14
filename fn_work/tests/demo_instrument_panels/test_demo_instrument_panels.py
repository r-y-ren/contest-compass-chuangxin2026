"""demo_instrument_panels 单测（R69）：五台远期仪表 sim（open_sim_* 工厂）面板
状态机 open/read-demo/close 全周期+别名归一+读数超模型域裁剪标注（R39–R43 口径
不拒）+未打开先读/先关 IllegalStateError+VISA 槽位状态总览+端点合约（POST
/api/instruments/{instrument}/{action}+GET /api/instruments）+页区静态资产零
外链。用例名统一 ``test_instruments_view_`` 前缀（`pytest -k instruments_view`
发现——R69 核验命令真身：五仪表开关+读数合约）。

被测实现口径见 src/demo_instrument_panels/demo_instrument_panels.py 模块
docstring（canonical/别名表/会话表/动作归一契约）。
"""
import pytest

try:  # 端点合约用——fastapi 缺库环境整组端点用例 skip
    from fastapi.testclient import TestClient

    from src.serve_console.create_console_app import create_console_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_FASTAPI = False

import src.demo_instrument_panels.demo_instrument_panels as panels_mod
from src.demo_instrument_panels.demo_instrument_panels import (
    INSTRUMENTS,
    IllegalStateError,
    demo_instrument_panels,
    list_instrument_panels,
)
from src.demo_instrument_panels.panels_area import (
    PANEL_CARD_CLASS,
    build_instrument_panels_area,
)

needs_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="环境缺 fastapi/httpx——TestClient 不可用"
)


@pytest.fixture(autouse=True)
def _fresh_sessions():
    """会话表隔离：每用例前后清空模块级 _SESSIONS（进程内演示态——不串台）。"""
    panels_mod._SESSIONS.clear()
    yield
    panels_mod._SESSIONS.clear()


# ---- 纯函数：五仪表 open/read/close 全周期（R69 验收真身） ----


def test_instruments_view_five_instruments_open_read_close_cycle():
    """① 五台仪表各自走 open→read-demo→close 全周期：open 附 capabilities+
    registry；read 附 readings/readback_note；close 状态 closed——simulated
    恒 True+诚实基注（模拟读数非实测）。"""
    for canonical in INSTRUMENTS:
        opened = demo_instrument_panels(canonical, "open")
        assert opened["instrument"] == canonical
        assert opened["state"] == "open" and opened["action"] == "open"
        assert opened["simulated"] is True and opened["note"]
        assert opened["capabilities"]  # 工厂实例能力自述
        assert opened["registry"]["name"]  # 注册名在案
        assert opened["reopened"] is False  # 首开非重开
        read = demo_instrument_panels(canonical, "read-demo")
        assert read["action"] == "read" and read["state"] == "open"
        assert read["readings"] is not None  # 仿真读数
        assert read["readback_note"]  # 读数口径注
        assert read["warnings"] == []  # 缺省参数无越域
        closed = demo_instrument_panels(canonical, "close")
        assert closed["state"] == "closed" and closed["closed_at"]
        assert closed["simulated"] is True


def test_instruments_view_read_config_and_out_of_domain_clipping():
    """② 读数超模型域如实标注不拒（R39–R43 口径）：siggen freq_hz 30GHz（域顶
    20GHz）裁剪至 20GHz+warnings 标注；attenuator 100dB（域顶 75dB）同口径；
    域内配置（attenuator 10dB）无 warnings。"""
    demo_instrument_panels("siggen_1433d", "open")
    read = demo_instrument_panels(
        "siggen_1433d", "read", {"freq_hz": 30e9, "power_dbm": -5.0}
    )
    assert read["readings"]["freq_hz_set"] == 20e9  # 裁剪到最近域边界
    assert read["warnings"] and "裁剪" in read["warnings"][0]
    assert "超出仿真域" in read["warnings"][0]
    assert read["readings"]["power"]["power_dbm"] == -5.0  # 域内参数不受牵连
    demo_instrument_panels("attenuator", "open")
    read = demo_instrument_panels("attenuator", "read", {"attenuation_db": 100.0})
    assert read["readings"]["attenuation_db"] == 75.0  # 域顶 75dB
    assert read["warnings"] and any("裁剪" in w for w in read["warnings"])
    read = demo_instrument_panels("attenuator", "read", {"attenuation_db": 10.0})
    assert read["warnings"] == []  # 域内配置零标注


def test_instruments_view_mixer_beyond_model_note_passed_through():
    """③ 混频超模型域：if_freq_hz 30GHz→RF 越过 20GHz 仿真域——后端自带
    rf_domain_note='beyond_model' 透传进 warnings（超模型域如实标注，不拒）。"""
    demo_instrument_panels("mixer_13g", "open")
    read = demo_instrument_panels(
        "mixer_13g", "read", {"if_freq_hz": 30e9, "if_power_dbm": -10.0}
    )
    assert read["readings"]["rf_domain_note"] == "beyond_model"  # 后端原文透传
    assert read["warnings"] and any("beyond_model" in w for w in read["warnings"])
    assert read["readings"]["rf_freq_hz"] > 20e9  # RF 越域读数照给


def test_instruments_view_illegal_state_rejected():
    """④ 面板状态机非法状态拒：未打开先读/未打开先关→IllegalStateError
    （ValueError 子类——端点层转 400）；重复 open 替换会话（reopened=True）。"""
    with pytest.raises(IllegalStateError, match="面板未打开"):
        demo_instrument_panels("emi_receiver", "read-demo")
    with pytest.raises(IllegalStateError, match="面板未打开"):
        demo_instrument_panels("emi_receiver", "close")
    with pytest.raises(ValueError):  # isinstance 口径：子类关系在案
        demo_instrument_panels("emi_receiver", "read", params={})
    demo_instrument_panels("emi_receiver", "open")
    reopened = demo_instrument_panels("emi_receiver", "open")  # 重复 open 替换
    assert reopened["reopened"] is True and reopened["state"] == "open"


def test_instruments_view_alias_case_and_unknown_rejected():
    """⑤ 仪表名归一：短名别名+大小写不敏感（' RSA513A '/1433d/mixer/emi/att）
    →canonical；未在册仪表/未知动作/params 非 dict → ValueError。"""
    alias = {
        " RSA513A ": "analyzer_rsa513a",
        "1433d": "siggen_1433d",
        "Mixer": "mixer_13g",
        "emi": "emi_receiver",
        "att": "attenuator",
    }
    for name, canonical in alias.items():
        opened = demo_instrument_panels(name, "open")
        assert opened["instrument"] == canonical
    with pytest.raises(ValueError, match="未在册仪表"):
        demo_instrument_panels("spectrum_analyzer_x", "open")
    with pytest.raises(ValueError, match="未知面板动作"):
        demo_instrument_panels("siggen_1433d", "reset")
    with pytest.raises(ValueError, match="params 必须为 dict"):
        demo_instrument_panels("siggen_1433d", "open", params=["freq_hz"])


def test_instruments_view_open_domain_error_passthrough_and_bad_values():
    """⑥ 工厂/配置域错透传：open params 域错（siggen freq_hz=0）ValueError
    原样；read 配置形状错（freq_hz 非 bool 非数值/字符串）ValueError 先拒。"""
    with pytest.raises(ValueError, match="freq"):
        demo_instrument_panels("siggen_1433d", "open", {"freq_hz": 0})
    assert "siggen_1433d" not in panels_mod._SESSIONS  # 域错不建会话
    demo_instrument_panels("siggen_1433d", "open")
    with pytest.raises(ValueError, match="必须为实数"):
        demo_instrument_panels("siggen_1433d", "read", {"freq_hz": True})
    with pytest.raises(ValueError, match="必须为实数"):
        demo_instrument_panels("siggen_1433d", "read", {"freq_hz": "10GHz"})


def test_instruments_view_list_overview_and_visa_slots():
    """⑦ 总览+VISA 槽位状态：五台面板行（state/registry/caps——关闭态 caps
    None 如实）+visa.slots 五行（builtin/generic 命令映射）+pyvisa 可用性
    bool——一切如实回显，不虚构连接。"""
    demo_instrument_panels("siggen_1433d", "open")
    overview = list_instrument_panels()
    assert len(overview["instruments"]) == 5
    assert [row["instrument"] for row in overview["instruments"]] == list(INSTRUMENTS)
    by_key = {row["instrument"]: row for row in overview["instruments"]}
    assert by_key["siggen_1433d"]["state"] == "open"
    assert by_key["siggen_1433d"]["capabilities"]  # open 时附实例 caps
    assert by_key["analyzer_rsa513a"]["state"] == "closed"
    assert by_key["analyzer_rsa513a"]["capabilities"] is None  # 关闭态如实 None
    assert all(row["simulated"] is True for row in overview["instruments"])
    visa = overview["visa"]
    assert isinstance(visa["pyvisa_available"], bool)  # 探测值如实（不虚构）
    assert len(visa["slots"]) == 5
    slot_map = {slot["instrument"]: slot for slot in visa["slots"]}
    assert slot_map["siggen_1433d"]["command_map"] == "builtin"  # 1433D 命令映射
    assert slot_map["emi_receiver"]["command_map"] == "builtin"  # EMI 接收机
    assert slot_map["analyzer_rsa513a"]["command_map"] == "generic"
    assert all(slot["visa_driver"] for slot in visa["slots"])  # 接入层说明在案
    assert overview["simulated"] is True and overview["note"]


# ---- 端点合约：POST /api/instruments/{instrument}/{action}+GET /api/instruments ----


def _client(tmp_path):
    """装配真 app（真面板模块——模块级会话表由 autouse fixture 隔离）。"""
    deps = {
        "runner": lambda scenario: {},
        "stop_flag": {"flag": False},
        "scenario_dir": str(tmp_path),
        "report_root": str(tmp_path / "reports"),
        "static_pages": {},
    }
    return TestClient(create_console_app(deps))


@needs_fastapi
def test_instruments_view_endpoint_open_read_close_and_overview(tmp_path):
    """⑧ 端点合约：POST open→200 state=open→POST read-demo（body 配置透传）
    →200 readings→POST close→200 closed；GET /api/instruments→200 总览（五行
    +visa 槽位）——读数合约与纯函数同构。"""
    client = _client(tmp_path)
    resp = client.post("/api/instruments/attenuator/open", json={})
    assert resp.status_code == 200
    assert resp.json()["state"] == "open"
    resp = client.post(
        "/api/instruments/attenuator/read-demo", json={"attenuation_db": 10.0}
    )
    assert resp.status_code == 200
    view = resp.json()
    assert view["action"] == "read" and view["readings"]["attenuation_db"] == 10.0
    resp = client.post("/api/instruments/attenuator/close", json={})
    assert resp.status_code == 200
    assert resp.json()["state"] == "closed"
    resp = client.get("/api/instruments")
    assert resp.status_code == 200
    overview = resp.json()
    assert len(overview["instruments"]) == 5 and len(overview["visa"]["slots"]) == 5


@needs_fastapi
def test_instruments_view_endpoint_errors_400(tmp_path):
    """⑨ 端点错误→400 错误信息上屏：未打开先读（IllegalStateError）/未在册
    仪表/未知动作/非 JSON 对象 body→400 field='instrument'（不静默不 500）。"""
    client = _client(tmp_path)
    resp = client.post("/api/instruments/siggen_1433d/read-demo", json={})
    assert resp.status_code == 400  # 未打开先读
    assert "面板未打开" in resp.json()["detail"]["error"]
    resp = client.post("/api/instruments/ghost-meter/open", json={})
    assert resp.status_code == 400 and "未在册仪表" in resp.json()["detail"]["error"]
    resp = client.post("/api/instruments/siggen_1433d/reset", json={})
    assert resp.status_code == 400 and "未知面板动作" in resp.json()["detail"]["error"]
    resp = client.post(
        "/api/instruments/siggen_1433d/open",
        content=b"[1,2]",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["field"] == "instrument"


# ---- 页区静态资产（serve_console instruments 页注入的面板区） ----


def test_instruments_view_panels_area_zero_external_links_and_anchors():
    """⑩ 页区资产：零外链（无 http(s):// 字面）+同源 fetch 端点字面
    （/api/instruments）+五卡 class 锚点+VISA 槽位挂载。"""
    block = build_instrument_panels_area()
    assert "http://" not in block and "https://" not in block
    assert 'id="instrument-panels-area"' in block  # 挂载区块锚点
    assert "/api/instruments" in block  # 同源相对路径 fetch
    assert PANEL_CARD_CLASS in block  # 五卡 class 锚点
    assert "visa-status" in block  # VISA 槽位状态挂载点
    assert "读数演示" in block and "打开" in block and "关闭" in block
