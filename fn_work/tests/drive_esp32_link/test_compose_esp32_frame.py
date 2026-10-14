"""compose_esp32_frame 单测（R85，验收 slug=dut_esp32 的往返用例族）。

四族：①compose→parse 往返全字段一致（校验和两态）；②NA 路径 parse 回 None；
③非法值族拒（负数/非整数/rssi NaN/inf）；④与解析器同口径——生成的帧全数可被
parse_esp32_frame 接受（参数化 10 组）。规约见 fn_docs/responsibility.md。
"""
from __future__ import annotations

import math

import pytest

from src.drive_esp32_link.compose_esp32_frame import compose_esp32_frame
from src.drive_esp32_link.parse_esp32_frame import parse_esp32_frame

# 往返样本（覆盖零值/大数/seq 8 位上限/小数 rssi/整 dBm）
_ROUNDTRIP_CASES = [
    (0, 0, 0, 0, None),
    (1, 100, 2, 3, -60.0),
    (7, 100, 2, 3, -92.5),
    (9, 500, 4, 7, None),
    (99999999, 99999999, 12345, 6789, -87.5),
    (4294967295, 4294967295, 0, 0, 0.0),
]


@pytest.mark.parametrize("seq,sent,err,retries,rssi", _ROUNDTRIP_CASES)
@pytest.mark.parametrize("checksum", [True, False])
def test_dut_esp32_compose_parse_roundtrip_all_fields(seq, sent, err, retries, rssi, checksum):
    frame = compose_esp32_frame(seq, sent, err, retries, rssi, checksum=checksum)
    out = parse_esp32_frame(frame)
    assert out["seq"] == seq
    assert out["sent"] == sent
    assert out["err"] == err
    assert out["retries"] == retries
    if rssi is None:
        assert out["rssi_dbm"] is None
    else:
        assert out["rssi_dbm"] == pytest.approx(rssi)
    # 校验和两态：有后缀→True（compose 生成必符），无后缀→None
    assert out["checksum_ok"] is (True if checksum else None)
    assert out["raw"] == frame


def test_dut_esp32_rssi_na_path_roundtrips_to_none():
    frame = compose_esp32_frame(5, 50, 1, 0, None, checksum=True)
    assert frame.endswith(",NA*") or ",NA*" in frame
    assert parse_esp32_frame(frame)["rssi_dbm"] is None
    # int 型 rssi（真机 WiFi.RSSI() 为整 dBm）也走同一数值路径
    assert parse_esp32_frame(compose_esp32_frame(5, 50, 1, 0, -63))["rssi_dbm"] == -63.0


def test_dut_esp32_golden_frames_exact_text():
    # 锁死帧体格式与校验和（帧体 sum&0xFF 两位小写十六进制；rssi 定 1 位小数）
    assert compose_esp32_frame(1, 100, 2, 3, -60.0) == "ESP,1,100,2,3,-60.0*dc"
    assert compose_esp32_frame(0, 0, 0, 0, None) == "ESP,0,0,0,0,NA*13"
    assert compose_esp32_frame(42, 42, 0, 0, -12.5, checksum=False) == "ESP,42,42,0,0,-12.5"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"seq": -1},
        {"sent": -100},
        {"err": -2},
        {"retries": -3},
        {"seq": 3.5},  # 非整数（float）
        {"sent": 100.0},  # 整值 float 也拒——与解析侧严格 [0-9]+ 对称
        {"err": "7"},  # 字符串数字拒
        {"retries": True},  # bool 拒（不是十进制计数）
        {"rssi": math.nan},
        {"rssi": math.inf},
        {"rssi": -math.inf},
        {"rssi": "abc"},
        {"rssi": True},
    ],
)
def test_dut_esp32_invalid_value_families_rejected(kwargs):
    base = {"seq": 1, "sent": 10, "err": 0, "retries": 0, "rssi": -60.0}
    base.update(kwargs)
    with pytest.raises(ValueError):
        compose_esp32_frame(**base)


# 与解析器同口径的生成样本（10 组：计数域边界 × rssi 两态 × 校验和两态）
_PARSE_ACCEPT_CASES = [
    (0, 0, 0, 0, None, False),
    (1, 1, 0, 0, -60.0, True),
    (7, 100, 2, 3, -92.5, True),
    (9, 500, 4, 7, None, True),
    (255, 256, 257, 258, 0.0, True),
    (65535, 65536, 0, 1, -0.5, False),
    (99999999, 99999999, 12345, 6789, -87.5, True),
    (4294967295, 4294967295, 0, 0, -30.0, True),
    (12, 34, 56, 78, None, False),
    (3, 3, 0, 0, -104.0, True),
]


@pytest.mark.parametrize("seq,sent,err,retries,rssi,checksum", _PARSE_ACCEPT_CASES)
def test_dut_esp32_generated_frames_all_accepted_by_parser(seq, sent, err, retries, rssi, checksum):
    frame = compose_esp32_frame(seq, sent, err, retries, rssi, checksum=checksum)
    out = parse_esp32_frame(frame)  # 任何一条生成帧被解析器拒收即本用例失败
    assert (out["seq"], out["sent"], out["err"], out["retries"]) == (seq, sent, err, retries)
