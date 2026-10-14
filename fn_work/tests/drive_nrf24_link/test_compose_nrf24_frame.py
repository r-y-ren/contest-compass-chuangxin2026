"""compose_nrf24_frame 单测（R86，验收 slug=dut_nrf24 的往返用例族）。

四族：①compose→parse 往返全字段一致（rpd 两态）；②rpd 0/1 两态与 bool 样本口径；
③非法值族拒（负数/非整数/rpd=2/rpd=bool 等）；④与解析器同口径——生成的帧全数可被
parse_nrf24_frame 接受（参数化 10 组）。规约见 fn_docs/responsibility.md。
"""
from __future__ import annotations

import pytest

from src.drive_nrf24_link.compose_nrf24_frame import compose_nrf24_frame
from src.drive_nrf24_link.parse_nrf24_frame import parse_nrf24_frame

# 往返样本（覆盖零值/大数/32 位 unsigned long 满值/回绕近界）
_ROUNDTRIP_CASES = [
    (0, 0, 0, 0, 0),
    (1, 100, 2, 3, 1),
    (7, 100, 2, 3, 0),
    (9, 500, 4, 7, 1),
    (99999999, 99999999, 12345, 6789, 0),
    (4294967295, 4294967295, 4294967295, 4294967295, 1),
]


@pytest.mark.parametrize("seq,sent,lost,retries,rpd", _ROUNDTRIP_CASES)
def test_dut_nrf24_compose_parse_roundtrip_all_fields(seq, sent, lost, retries, rpd):
    frame = compose_nrf24_frame(seq, sent, lost, retries, rpd)
    out = parse_nrf24_frame(frame)
    assert out["seq"] == seq
    assert out["sent"] == sent
    assert out["lost"] == lost
    assert out["retries"] == retries
    assert out["rpd"] is bool(rpd)  # 解析侧 1bit 门限位 → bool
    assert out["raw"] == frame


def test_dut_nrf24_rpd_two_states_roundtrip():
    """rpd 0/1 两态各自往返成功（1bit 门限位仅此两值合法）。"""
    for rpd in (0, 1):
        out = parse_nrf24_frame(compose_nrf24_frame(3, 30, 1, 2, rpd))
        assert out["rpd"] is bool(rpd)
        assert out["raw"].endswith(f",{rpd}")


def test_dut_nrf24_golden_frames_exact_text():
    # 锁死帧体格式：无校验和后缀，六字段纯十进制（NRF 协议与 ESP 的差异点）
    assert compose_nrf24_frame(1, 100, 2, 3, 0) == "NRF,1,100,2,3,0"
    assert compose_nrf24_frame(0, 0, 0, 0, 1) == "NRF,0,0,0,0,1"
    assert compose_nrf24_frame(42, 42, 0, 0, 1) == "NRF,42,42,0,0,1"
    assert compose_nrf24_frame(4294967295, 4294967295, 1, 2, 0) == "NRF,4294967295,4294967295,1,2,0"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"seq": -1},
        {"sent": -100},
        {"lost": -2},
        {"retries": -3},
        {"rpd": -1},
        {"seq": 3.5},  # 非整数（float）
        {"sent": 100.0},  # 整值 float 也拒——与解析侧严格 [0-9]+ 对称
        {"lost": "7"},  # 字符串数字拒
        {"retries": True},  # bool 拒（不是十进制计数）
        {"rpd": 2},  # rpd 超 1bit 值域
        {"rpd": True},  # rpd=bool 拒（bool 是 int 子类，须显式排除）
        {"rpd": 0.0},  # rpd=float 拒（即使数值合法）
        {"rpd": "1"},  # rpd=字符串拒
    ],
)
def test_dut_nrf24_invalid_value_families_rejected(kwargs):
    base = {"seq": 1, "sent": 10, "lost": 0, "retries": 0, "rpd": 0}
    base.update(kwargs)
    with pytest.raises(ValueError):
        compose_nrf24_frame(**base)


# 与解析器同口径的生成样本（10 组：计数域边界 × rpd 两态）
_PARSE_ACCEPT_CASES = [
    (0, 0, 0, 0, 0),
    (1, 1, 0, 0, 1),
    (7, 100, 2, 3, 0),
    (9, 500, 4, 7, 1),
    (255, 256, 257, 258, 0),
    (65535, 65536, 0, 1, 1),
    (99999999, 99999999, 12345, 6789, 0),
    (4294967295, 4294967295, 0, 0, 1),
    (12, 34, 56, 78, 0),
    (3, 3, 0, 0, 1),
]


@pytest.mark.parametrize("seq,sent,lost,retries,rpd", _PARSE_ACCEPT_CASES)
def test_dut_nrf24_generated_frames_all_accepted_by_parser(seq, sent, lost, retries, rpd):
    frame = compose_nrf24_frame(seq, sent, lost, retries, rpd)
    out = parse_nrf24_frame(frame)  # 任何一条生成帧被解析器拒收即本用例失败
    assert (out["seq"], out["sent"], out["lost"], out["retries"]) == (seq, sent, lost, retries)
