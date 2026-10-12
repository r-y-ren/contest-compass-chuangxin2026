"""parse_esp32_frame 对抗测试（验收 slug 见 fn_docs）。

规约：帧 `ESP,<seq>,<sent>,<err>,<retries>,<rssi>`，可选 `*<hex>` 校验和
（帧体 sum & 0xFF，hex 大小写均可）；rssi 可为 'NA'→None；错误统一 FrameError。
"""
from __future__ import annotations

import pytest

from src.drive_esp32_link.parse_esp32_frame import FrameError, parse_esp32_frame

# 预计算的 sum & 0xFF 校验和（帧体，不含 '*' 与后缀）
CK_1 = "7E"  # ESP,1,100,2,3,-60
CK_2 = "8C"  # ESP,9,500,4,7,NA
CK_3 = "bb"  # ESP,3,42,1,2,-92.5（小写 hex）


def test_normal_frame_all_fields():
    out = parse_esp32_frame("ESP,7,100,2,3,-60")
    assert out == {
        "seq": 7,
        "sent": 100,
        "err": 2,
        "retries": 3,
        "rssi_dbm": -60.0,
        "checksum_ok": None,
        "raw": "ESP,7,100,2,3,-60",
    }
    assert all(isinstance(out[k], int) for k in ("seq", "sent", "err", "retries"))


def test_rssi_na_maps_to_none():
    out = parse_esp32_frame("ESP,1,5,0,0,NA")
    assert out["rssi_dbm"] is None
    assert out["seq"] == 1 and out["sent"] == 5


def test_rssi_float_value():
    assert parse_esp32_frame("ESP,3,42,1,2,-92.5")["rssi_dbm"] == -92.5


def test_checksum_correct_uppercase():
    out = parse_esp32_frame(f"ESP,1,100,2,3,-60*{CK_1}")
    assert out["checksum_ok"] is True
    assert out["seq"] == 1 and out["raw"].endswith("*" + CK_1)


def test_checksum_correct_lowercase_hex():
    out = parse_esp32_frame(f"ESP,3,42,1,2,-92.5*{CK_3}")
    assert out["checksum_ok"] is True


def test_checksum_case_insensitive_on_na_frame():
    out = parse_esp32_frame(f"ESP,9,500,4,7,NA*{CK_2.lower()}")
    assert out["checksum_ok"] is True and out["rssi_dbm"] is None


def test_checksum_mismatch_rejected():
    with pytest.raises(FrameError, match="checksum mismatch"):
        parse_esp32_frame(f"ESP,1,100,2,3,-60*{(int(CK_1, 16) ^ 0x01):02X}")


def test_checksum_invalid_hex_rejected():
    with pytest.raises(FrameError, match="invalid checksum hex"):
        parse_esp32_frame("ESP,1,100,2,3,-60*ZZ")


def test_checksum_empty_suffix_rejected():
    with pytest.raises(FrameError, match="empty checksum"):
        parse_esp32_frame("ESP,1,100,2,3,-60*")


@pytest.mark.parametrize(
    ("frame", "field"),
    [
        ("ESP,-1,100,2,3,-60", "seq"),
        ("ESP,1,-100,2,3,-60", "sent"),
        ("ESP,1,100,-2,3,-60", "err"),
        ("ESP,1,100,2,-3,-60", "retries"),
    ],
)
def test_negative_fields_rejected(frame, field):
    with pytest.raises(FrameError, match=rf"field '{field}' must be >= 0"):
        parse_esp32_frame(frame)


@pytest.mark.parametrize(
    "frame",
    [
        "ESP,1,100,2,-60",  # 5 字段
        "ESP,1,100,2,3,4,-60",  # 7 字段
        "ESP,1,100,2,3,-60,extra*CE",  # 校验和正确，仍因 7 字段拒绝
    ],
)
def test_wrong_field_count_rejected(frame):
    with pytest.raises(FrameError, match="expected 6 comma fields"):
        parse_esp32_frame(frame)


@pytest.mark.parametrize(
    "frame",
    [
        "NRF,1,100,2,3,-60",
        "esp,1,100,2,3,-60",  # 前缀大小写敏感
        "ESPN,1,100,2,3,-60",
        "1,2,3,4,5,6",
        "",
    ],
)
def test_bad_prefix_or_empty_rejected(frame):
    with pytest.raises(FrameError):
        parse_esp32_frame(frame)


def test_non_numeric_integer_field_rejected():
    with pytest.raises(FrameError, match="'seq' is not an integer"):
        parse_esp32_frame("ESP,abc,100,2,3,-60")


def test_non_numeric_rssi_rejected():
    with pytest.raises(FrameError, match="'rssi' is not a number"):
        parse_esp32_frame("ESP,1,100,2,3,foo")


def test_bytes_input_utf8():
    out = parse_esp32_frame(b"ESP,1,100,2,3,-60")
    assert out["seq"] == 1 and out["rssi_dbm"] == -60.0
    assert out["raw"] == "ESP,1,100,2,3,-60"


def test_bytes_bad_utf8_rejected():
    with pytest.raises(FrameError, match="utf-8 decode failed"):
        parse_esp32_frame(b"ESP,\xff,2,3,4,-60")


def test_crlf_and_outer_whitespace_tolerated():
    out = parse_esp32_frame("  ESP,1,100,2,3,-60\r\n")
    assert out["seq"] == 1
    assert out["raw"] == "ESP,1,100,2,3,-60"
    assert parse_esp32_frame("\tESP,1,100,2,3,-60\n")["sent"] == 100


def test_multiline_rejected():
    with pytest.raises(FrameError, match="multiline"):
        parse_esp32_frame("ESP,1,100,2,3,-60\nESP,2,200,0,0,-70")


@pytest.mark.parametrize("frame", ["", "   ", " \r\n\t ", b""])
def test_empty_input_rejected(frame):
    with pytest.raises(FrameError, match="empty frame"):
        parse_esp32_frame(frame)


def test_wrong_type_rejected():
    with pytest.raises(FrameError, match="must be bytes or str"):
        parse_esp32_frame(12345)


def test_error_message_contains_reason_and_truncated_raw():
    long_frame = "ESP," + ",".join(["1"] * 200)
    with pytest.raises(FrameError) as exc_info:
        parse_esp32_frame(long_frame)
    msg = str(exc_info.value)
    assert "expected 6 comma fields" in msg
    assert "raw=" in msg and "..." in msg and len(msg) < 200
    assert isinstance(exc_info.value, ValueError)  # FrameError 是 ValueError 子类
    assert exc_info.value.reason == "expected 6 comma fields, got 201"


def test_checksum_computed_over_body_before_star():
    # 对 "ESP,1,100,2,3,-60" 的帧体校验和应为 0x7E；改动任一字段即失配
    with pytest.raises(FrameError, match="checksum mismatch"):
        parse_esp32_frame("ESP,1,101,2,3,-60*7E")
