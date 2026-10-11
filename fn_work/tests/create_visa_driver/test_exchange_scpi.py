"""exchange_scpi 对抗测试：四类写读往返、布尔变体、解析失败→DriverError、Timeout 重试/耗尽
（__cause__ 与计数断言）、非 Timeout 不重试、参数校验（command/expect）、elapsed_ms、
空白 strip 后解析、非查询命令只写不读。"""
from __future__ import annotations

import time

import pytest

from src.create_visa_driver.exchange_scpi import DriverError, exchange_scpi


class VisaTimeout(Exception):
    """名字含 Timeout 的超时异常（类名规则路径）。"""


class StallMarker(Exception):
    """名字不含 Timeout 但带 timeout 属性的鸭子超时异常（属性规则路径）。"""

    timeout = 2.0


class InstrumentFault(Exception):
    """普通会话故障：不应触发重试。"""


class FakeSession:
    """鸭子仪器会话：write 记录命令；read 按脚本逐一返回 str 或抛异常（脚本耗尽返回 ''）。"""

    def __init__(self, script=()):
        self.written = []
        self.write_calls = 0
        self.read_calls = 0
        self._script = list(script)

    def write(self, cmd):
        self.write_calls += 1
        self.written.append(cmd)

    def read(self):
        self.read_calls += 1
        item = self._script.pop(0) if self._script else ""
        if isinstance(item, BaseException):
            raise item
        return item


def test_roundtrip_float():
    sess = FakeSession(["3.14\n"])
    out = exchange_scpi(sess, ":MEAS:VOLT?", "float")
    assert out["value"] == pytest.approx(3.14)
    assert out["raw"] == "3.14\n"
    assert sess.written == [":MEAS:VOLT?"]


def test_roundtrip_int_with_padding():
    sess = FakeSession(["  +42 \r\n"])
    out = exchange_scpi(sess, ":SENS:FREQ:CW?", "int")
    assert out["value"] == 42 and isinstance(out["value"], int)
    assert out["raw"] == "  +42 \r\n"


def test_roundtrip_str_default_expect():
    sess = FakeSession(["ACME,1433D,SN001,1.0.0\n"])
    out = exchange_scpi(sess, "*IDN?")  # expect 缺省 'str'
    assert out["value"] == "ACME,1433D,SN001,1.0.0"


@pytest.mark.parametrize(
    "answer,expected",
    [("ON", True), ("OFF", False), ("1", True), ("0", False)],
)
def test_bool_variants(answer, expected):
    sess = FakeSession([f" {answer}\n"])
    out = exchange_scpi(sess, ":OUTP?", "bool")
    assert out["value"] is expected


def test_float_parse_failure_driver_error():
    sess = FakeSession(["--not-a-number--\n"])
    with pytest.raises(DriverError):
        exchange_scpi(sess, ":MEAS:VOLT?", "float")


def test_bool_parse_failure_driver_error():
    sess = FakeSession(["MAYBE\n"])
    with pytest.raises(DriverError):
        exchange_scpi(sess, ":OUTP?", "bool")


def test_timeout_retry_then_success(monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    # 第 1 次类名含 Timeout，第 2 次 timeout 属性鸭子判定：两条路径都应重试
    sess = FakeSession([VisaTimeout("t/o"), StallMarker("stall"), "2.5\n"])
    out = exchange_scpi(sess, ":READ:VOLT?", "float", retry=2)
    assert out["value"] == pytest.approx(2.5)
    assert sess.write_calls == 3 and sess.read_calls == 3  # 整个 write+read 重来
    assert sleeps == [pytest.approx(0.05), pytest.approx(0.1)]  # 指数退避 0.05*2^n


def test_timeout_retry_exhausted_cause(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    last = StallMarker("still stalling")
    sess = FakeSession([VisaTimeout("t/o"), last])
    with pytest.raises(DriverError) as ei:
        exchange_scpi(sess, ":READ:VOLT?", "float", retry=1)
    assert ei.value.__cause__ is last
    assert sess.write_calls == 2 and sess.read_calls == 2


def test_non_timeout_exception_no_retry():
    fault = InstrumentFault("io fault")
    sess = FakeSession([fault])
    with pytest.raises(DriverError) as ei:
        exchange_scpi(sess, ":READ:VOLT?", "float", retry=3)
    assert ei.value.__cause__ is fault
    assert sess.write_calls == 1 and sess.read_calls == 1  # 一次即抛，不重试


@pytest.mark.parametrize("bad", ["", "   ", None, 123])
def test_command_validation(bad):
    sess = FakeSession(["1\n"])
    with pytest.raises(ValueError):
        exchange_scpi(sess, bad)
    assert sess.write_calls == 0  # 校验先于任何会话调用


def test_expect_unknown_value_error():
    sess = FakeSession(["{}"])
    with pytest.raises(ValueError):
        exchange_scpi(sess, ":SYST:JSON?", "json")


def test_elapsed_ms_nonnegative_int():
    sess = FakeSession(["5\n"])
    out = exchange_scpi(sess, ":VOLT?", "int")
    assert isinstance(out["elapsed_ms"], int) and out["elapsed_ms"] >= 0


def test_whitespace_newline_stripped_before_parse():
    sess = FakeSession(["\t 7.25 \r\n"])
    out = exchange_scpi(sess, ":VOLT?", "float")
    assert out["value"] == pytest.approx(7.25)
    assert out["raw"] == "\t 7.25 \r\n"  # raw 保留原文，value 用 strip 后解析


def test_set_command_skips_read():
    sess = FakeSession(["不应被读取"])
    out = exchange_scpi(sess, ":OUTP ON")  # 非 '?' 结尾：可选读回应答=不读
    assert sess.read_calls == 0
    assert sess.written == [":OUTP ON"]
    assert out["raw"] == "" and out["value"] == ""


# ---- B5 对抗审查缺陷回归（低#10 retry 参数校验 / 低#11 read None 与空应答标注）----


@pytest.mark.parametrize("bad", [-1, 1.5, True, "2", None])
def test_defect_b5_10_retry_validation_eager_before_session(bad):
    """低#10：retry 负数/非 int/bool → ValueError（调用即抛，先于任何会话调用）。"""
    sess = FakeSession(["1\n"])
    with pytest.raises(ValueError, match="retry"):
        exchange_scpi(sess, ":VOLT?", "int", retry=bad)
    assert sess.write_calls == 0
    # 边界：0 与正 int 合法
    assert exchange_scpi(FakeSession(["7\n"]), ":VOLT?", "int", retry=0)["value"] == 7


def test_defect_b5_11_read_none_driver_error_instrument_no_answer():
    """低#11：read() 返回 None → DriverError（'仪器无应答'），不把 None 解析成 'None'。"""

    class NoneReadSession(FakeSession):
        def read(self):
            self.read_calls += 1
            return None

    sess = NoneReadSession()
    with pytest.raises(DriverError, match="仪器无应答"):
        exchange_scpi(sess, "*IDN?", "str")
    assert sess.write_calls == 1 and sess.read_calls == 1  # 写读都发生过，失败定性在应答


def test_defect_b5_11_empty_str_response_annotated_empty_response():
    """低#11：expect='str' 空应答返回 '' 且附 empty_response=True 标注；其余口径不动。"""
    sess = FakeSession([""])
    out = exchange_scpi(sess, "*IDN?", "str")
    assert out["raw"] == "" and out["value"] == ""
    assert out["empty_response"] is True
    # 纯空白应答同样视为无内容：标注照附
    blank = exchange_scpi(FakeSession(["   \n"]), "*IDN?", "str")
    assert blank["value"] == "" and blank["empty_response"] is True
    # 有内容的查询不带标注
    assert "empty_response" not in exchange_scpi(FakeSession(["ACME\n"]), "*IDN?", "str")
    # 非查询命令（不读回，raw 本就 ''）不带标注
    assert "empty_response" not in exchange_scpi(FakeSession(), ":OUTP ON")
    # float/int/bool 空应答仍走解析失败 DriverError（既有拒收口径不动）
    for expect in ("float", "int", "bool"):
        with pytest.raises(DriverError):
            exchange_scpi(FakeSession([""]), ":VOLT?", expect)
