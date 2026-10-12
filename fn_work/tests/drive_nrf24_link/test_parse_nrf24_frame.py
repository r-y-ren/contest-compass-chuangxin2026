"""parse_nrf24_frame 对抗单测：帧格式/校验拒绝路径/无 RSSI 键口径（slug 上游覆盖: dut_nrf24）。"""
from __future__ import annotations

import pytest

from src.drive_nrf24_link.parse_nrf24_frame import FrameError, parse_nrf24_frame


def test_normal_frame_parses_all_counters():
    result = parse_nrf24_frame("NRF,7,100,3,12,0")
    assert result == {
        "seq": 7,
        "sent": 100,
        "lost": 3,
        "retries": 12,
        "rpd": False,
        "raw": "NRF,7,100,3,12,0",
    }


def test_rpd_bit_maps_to_bool():
    low = parse_nrf24_frame("NRF,1,10,0,0,0")
    high = parse_nrf24_frame("NRF,2,10,1,1,1")
    assert low["rpd"] is False
    assert high["rpd"] is True
    assert isinstance(high["rpd"], bool)  # 1bit 门限标志按 bool 口径产出


def test_rpd_out_of_range_rejected():
    with pytest.raises(FrameError) as exc:
        parse_nrf24_frame("NRF,1,10,0,0,2")
    assert "rpd" in str(exc.value)  # 拒因需点名 rpd


def test_field_count_mismatch_rejected():
    for bad in ("NRF,1,10,0,0", "NRF,1,10,0,0,0,9"):
        with pytest.raises(FrameError):
            parse_nrf24_frame(bad)


def test_wrong_prefix_rejected():
    for bad in ("ESP,1,10,0,0,0", "nrf,1,10,0,0,0", "NRF24,1,10,0,0,0"):
        with pytest.raises(FrameError):
            parse_nrf24_frame(bad)


def test_negative_number_rejected():
    for bad in ("NRF,-1,10,0,0,0", "NRF,1,-10,0,0,0", "NRF,1,10,0,0,-1"):
        with pytest.raises(FrameError):
            parse_nrf24_frame(bad)


def test_non_numeric_field_rejected():
    for bad in (
        "NRF,abc,10,0,0,0",
        "NRF,1,10,0.5,0,0",
        "NRF,,10,0,0,0",  # 空字段
        "NRF, 1,10,0,0,0",  # 字段内空白
        "NRF,+1,10,0,0,0",  # 正负号非纯数字口径
    ):
        with pytest.raises(FrameError):
            parse_nrf24_frame(bad)


def test_bytes_input_parses_like_str():
    result = parse_nrf24_frame(b"NRF,3,50,2,4,1")
    assert result["seq"] == 3
    assert result["sent"] == 50
    assert result["lost"] == 2
    assert result["retries"] == 4
    assert result["rpd"] is True
    assert result["raw"] == "NRF,3,50,2,4,1"
    with pytest.raises(FrameError):  # 非 ASCII 字节→解码失败拒收
        parse_nrf24_frame(b"NRF,1,\xff,0,0,0")


def test_crlf_and_outer_whitespace_tolerated():
    assert parse_nrf24_frame("NRF,1,10,0,0,1\r\n")["seq"] == 1
    assert parse_nrf24_frame(b"NRF,2,20,1,1,0\n")["retries"] == 1
    assert parse_nrf24_frame("  NRF,3,30,2,2,0  \r\n")["rpd"] is False


def test_empty_and_multiline_rejected():
    for bad in (
        "",
        "   ",
        b"",
        "NRF,1,2,3,4,0\nNRF,5,6,7,8,1",  # 多行拼帧
        "NRF,1,2,3,4,0\rGARBAGE",  # 内嵌 \r 同样按多行拒
    ):
        with pytest.raises(FrameError):
            parse_nrf24_frame(bad)


def test_non_frame_type_rejected():
    for bad in (123, None, ["NRF,1,2,3,4,0"]):
        with pytest.raises(FrameError):
            parse_nrf24_frame(bad)


def test_no_rssi_key_in_output():
    result = parse_nrf24_frame("NRF,9,99,9,9,1")
    assert "rssi" not in result  # NRF24 无 RSSI，指标口径只丢包/重传
    assert set(result) == {"seq", "sent", "lost", "retries", "rpd", "raw"}


def test_frame_error_carries_reason_and_is_value_error():
    assert issubclass(FrameError, ValueError)
    with pytest.raises(FrameError) as exc:
        parse_nrf24_frame("XRF,1,2,3,4,0")
    assert str(exc.value).strip()  # FrameError 消息含原因（非空）
