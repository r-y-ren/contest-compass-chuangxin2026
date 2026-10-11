"""create_visa_driver 对抗测试：注入会话+命令映射格式化往返、query_id 往返、未知型号回退
generic+warning（caplog）、model 非法类型→ValueError、pyvisa 缺失→DriverError 含安装提示、
资源打开失败含仪器原文、pyvisa 成功路径接线、close 幂等透传+共享会话 warning、
raw_exchange 透传、模板缺参/格式化全类异常→DriverError 指明参数、emi_receiver 映射存在性、
expect=float 透传、未知命令键、model/resource 只读。"""
from __future__ import annotations

import builtins
import logging
import sys
import types

import pytest

from src.create_visa_driver.create_visa_driver import (
    MODELS,
    VisaDriver,
    create_visa_driver,
)
from src.create_visa_driver.exchange_scpi import DriverError


class FakeSession:
    """鸭子仪器会话：write 记录命令；read 按脚本逐一返回 str（脚本耗尽返回 ''）。"""

    def __init__(self, script=()):
        self.written = []
        self.read_calls = 0
        self._script = list(script)

    def write(self, cmd):
        self.written.append(cmd)

    def read(self):
        self.read_calls += 1
        return self._script.pop(0) if self._script else ""


class CloseSpySession(FakeSession):
    """带 close 的会话：记录 close 调用次数（验证 close 透传）。"""

    def __init__(self, script=()):
        super().__init__(script)
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


def install_fake_pyvisa(monkeypatch, resource_manager):
    """把假 pyvisa 模块塞进 sys.modules：ResourceManager 工厂返回给定实例。"""
    fake = types.ModuleType("pyvisa")
    fake.ResourceManager = lambda *a, **k: resource_manager
    monkeypatch.setitem(sys.modules, "pyvisa", fake)


def refuse_pyvisa_import(monkeypatch):
    """让 'import pyvisa' 确定性地 ImportError（无论本机是否装了 pyvisa）。"""
    monkeypatch.delitem(sys.modules, "pyvisa", raising=False)
    real_import = builtins.__import__

    def _refuse(name, *args, **kwargs):
        if name == "pyvisa":
            raise ImportError("No module named 'pyvisa'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _refuse)


def test_visa_slot_injected_session_set_freq_formats_template():
    sess = FakeSession()
    drv = create_visa_driver("sim://siggen-0", "1433d", session=sess)
    out = drv.exchange("set_freq", args={"mhz": 2450})
    assert sess.written == ["FREQ 2450 MHz"]
    assert out["value"] == "" and sess.read_calls == 0  # 设置类命令只写不读


def test_visa_slot_query_id_roundtrip():
    sess = CloseSpySession(["SilverRocket,1433D,SR00123,1.0.7\n"])
    drv = create_visa_driver("TCPIP::192.0.2.10::INSTR", "1433d", session=sess)
    out = drv.exchange("query_id")
    assert sess.written == ["*IDN?"]
    assert out["value"] == "SilverRocket,1433D,SR00123,1.0.7"
    assert out["raw"] == "SilverRocket,1433D,SR00123,1.0.7\n"


def test_visa_slot_unknown_model_falls_back_generic_with_warning(caplog):
    sess = FakeSession(["GENERIC,DEV,0,0\n"])
    with caplog.at_level(logging.WARNING):
        drv = create_visa_driver("GPIB::5::INSTR", "totally-unknown", session=sess)
    assert drv.model == "generic"
    assert any(
        "totally-unknown" in rec.getMessage() and "generic" in rec.getMessage()
        for rec in caplog.records
    )
    assert drv.exchange("query_id")["value"] == "GENERIC,DEV,0,0"  # 回退后仍可用


def test_visa_slot_non_str_model_raises_value_error():
    with pytest.raises(ValueError, match="model 必须为 str"):
        create_visa_driver("TCPIP::x::INSTR", 1433, session=FakeSession())


def test_visa_slot_non_str_resource_raises_value_error():
    with pytest.raises(ValueError, match="resource 必须为 str"):
        create_visa_driver(None, "1433d", session=FakeSession())


def test_visa_slot_missing_pyvisa_without_session_raises_driver_error(monkeypatch):
    refuse_pyvisa_import(monkeypatch)
    with pytest.raises(DriverError) as excinfo:
        create_visa_driver("TCPIP::192.0.2.10::INSTR", "1433d")
    msg = str(excinfo.value)
    assert "pip install pyvisa" in msg and "session" in msg  # 安装提示 + 注入绕行提示
    assert isinstance(excinfo.value.__cause__, ImportError)


def test_visa_slot_pyvisa_open_failure_includes_instrument_text(monkeypatch):
    class RmOpenFail:
        def open_resource(self, resource):
            raise RuntimeError(f"VI_ERROR_RESOURCE_NOT_FOUND: {resource} 无法打开")

    install_fake_pyvisa(monkeypatch, RmOpenFail())
    with pytest.raises(DriverError) as excinfo:
        create_visa_driver("TCPIP::192.0.2.99::INSTR", "1433d")
    msg = str(excinfo.value)
    assert "TCPIP::192.0.2.99::INSTR" in msg
    assert "VI_ERROR_RESOURCE_NOT_FOUND" in msg  # 仪器/底层原文必须保留
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_visa_slot_pyvisa_path_uses_open_resource_session(monkeypatch):
    sess = FakeSession(["PyVISA,1433D,PV1,9.9\n"])

    class Rm:
        def __init__(self):
            self.opened = []

        def open_resource(self, resource):
            self.opened.append(resource)
            return sess

    rm = Rm()
    install_fake_pyvisa(monkeypatch, rm)
    drv = create_visa_driver("TCPIP::192.0.2.10::INSTR", "1433d")  # 不注入 session
    assert rm.opened == ["TCPIP::192.0.2.10::INSTR"]
    assert isinstance(drv, VisaDriver) and drv.resource == "TCPIP::192.0.2.10::INSTR"
    assert drv.exchange("query_id")["value"] == "PyVISA,1433D,PV1,9.9"


def test_visa_slot_close_passthrough_and_safe_without_close():
    spied = CloseSpySession()
    drv = create_visa_driver("sim://a", "1433d", session=spied)
    drv.close()
    drv.close()
    assert spied.close_calls == 1  # 幂等（_closed 守卫）：会话 close 只打一次（B5 低#9 新口径）
    create_visa_driver("sim://b", "generic", session=FakeSession()).close()  # 无 close 不炸


# ---- B5 对抗审查缺陷回归（低#8 format 全类异常 / 低#9 close 幂等+共享会话 warning）----


def test_defect_b5_8_format_full_exception_classes_wrapped_driver_error(monkeypatch):
    """低#8：str.format IndexError/ValueError/TypeError 全类 → DriverError（含模板与 args 键）。"""
    sess = FakeSession()
    drv = create_visa_driver("sim://x", "1433d", session=sess)
    cases = [
        ("FREQ {0} MHz", {"mhz": 2450}),  # IndexError：位置占位但只给了关键字参数
        ("FREQ {mhz:z} MHz", {"mhz": 2450}),  # ValueError：非法格式说明符 'z'
        ("FREQ {mhz:>s} MHz", {"mhz": 2450}),  # TypeError：int 不支持 's' 说明符
    ]
    for idx, (template, args) in enumerate(cases):
        key = f"bad_spec_{idx}"
        monkeypatch.setitem(MODELS["1433d"], key, template)
        with pytest.raises(DriverError) as excinfo:
            drv.exchange(key, args=args)
        msg = str(excinfo.value)
        assert template in msg, template  # 模板原文入消息
        assert "mhz" in msg, template  # args 键入消息
        assert sess.written == []  # 格式化失败不得碰会话


def test_defect_b5_9_close_idempotent_guard_and_shared_session_warning(caplog):
    """低#9：close 幂等（重复调用只关一次）且关闭共享会话前记 warning 提示。"""
    spied = CloseSpySession(["IDN\n"])
    drv = create_visa_driver("sim://shared", "1433d", session=spied)
    with caplog.at_level(logging.WARNING):
        drv.close()
        drv.close()
        drv.close()
    assert spied.close_calls == 1  # _closed 守卫：只第一次真正作用到会话
    shared_warnings = [r for r in caplog.records if "共享" in r.getMessage()]
    assert len(shared_warnings) == 1  # warning 恰一条（幂等下不重复打扰）
    assert "sim://shared" in shared_warnings[0].getMessage()
    # 无 close 方法的会话：幂等同样成立、不炸、无 warning
    plain = create_visa_driver("sim://plain", "generic", session=FakeSession())
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        plain.close()
        plain.close()
    assert not [r for r in caplog.records if "共享" in r.getMessage()]


def test_visa_slot_raw_exchange_passthrough():
    sess = FakeSession(["0,\"No error\"\n"])
    drv = create_visa_driver("GPIB::1::INSTR", "1433d", session=sess)
    out = drv.raw_exchange(":SYST:ERR?", expect="str")
    assert sess.written == [":SYST:ERR?"]  # 原句透传，不经命令映射
    assert out["value"] == '0,"No error"'


def test_visa_slot_template_missing_param_raises_clear_driver_error():
    sess = FakeSession()
    drv = create_visa_driver("sim://siggen-0", "1433d", session=sess)
    with pytest.raises(DriverError) as excinfo:
        drv.exchange("set_power", args={"mhz": 5})  # 给错参数：模板要 dbm
    msg = str(excinfo.value)
    assert "set_power" in msg and "dbm" in msg and "POW {dbm} dBm" in msg
    assert sess.written == []  # 格式化失败不得碰会话


def test_visa_slot_unknown_command_key_lists_available():
    sess = FakeSession()
    drv = create_visa_driver("sim://x", "1433d", session=sess)
    with pytest.raises(DriverError, match="set_freq"):
        drv.exchange("nonsense_key")
    assert sess.written == []


def test_visa_slot_models_registry_contains_required_mappings():
    assert MODELS["1433d"] == {
        "set_freq": "FREQ {mhz} MHz",
        "set_power": "POW {dbm} dBm",
        "output_on": "OUTP ON",
        "output_off": "OUTP OFF",
        "query_id": "*IDN?",
    }
    assert {"set_freq", "query_level"} <= set(MODELS["emi_receiver"])  # EMI 接收机映射存在
    assert {"query_id", "set_freq"} <= set(MODELS["generic"])


def test_visa_slot_emi_receiver_query_level_expect_float_passthrough():
    sess = FakeSession(["  -42.5 \n"])
    drv = create_visa_driver("TCPIP::192.0.2.20::INSTR", "emi_receiver", session=sess)
    out = drv.exchange("query_level", "float", args={"mhz": 30})
    assert sess.written == ["MEAS:LEV 30 MHz?"]
    assert out["value"] == pytest.approx(-42.5) and isinstance(out["value"], float)


@pytest.mark.parametrize(
    "key,args,expected",
    [
        ("set_freq", {"mhz": 2450}, "FREQ 2450 MHz"),
        ("set_power", {"dbm": -10}, "POW -10 dBm"),
        ("output_on", None, "OUTP ON"),
        ("output_off", None, "OUTP OFF"),
    ],
)
def test_visa_slot_1433d_command_set_pins_templates(key, args, expected):
    sess = FakeSession()
    drv = create_visa_driver("sim://1433d", "1433d", session=sess)
    drv.exchange(key, args=args)
    assert sess.written == [expected]


def test_visa_slot_model_and_resource_readonly():
    drv = create_visa_driver("sim://ro", "emi_receiver", session=FakeSession())
    assert drv.model == "emi_receiver" and drv.resource == "sim://ro"
    with pytest.raises(AttributeError):
        drv.model = "generic"
    with pytest.raises(AttributeError):
        drv.resource = "sim://other"
