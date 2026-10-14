"""固件 C++ encode_nrf24_frame 与 Python compose_nrf24_frame 跨语言逐字节等价（R86 host 侧）。

做法：g++ -std=c++17 -Wall -Wextra -Werror 把 firmware/nrf24_link/src/frame_encoder.cpp
与 fixtures/frame_encoder_harness.cpp 编译到 /tmp（不进仓库），stdin 喂样例行，断言
harness 每行输出与 compose_nrf24_frame 同输入输出逐字节一致；顺带用 parse_nrf24_frame
复核 C++ 帧可解析（固件→解析器同口径）。g++ 缺失或编译失败→fail（不 skip——本机 g++ 在位，
规格要求跨语言等价是硬验收）。测试文件与 esp32 批同构文件不同名（test_nrf24_host_equivalence）：
本仓库测试目录不带 __init__.py，模块 basename 须全局唯一。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.drive_nrf24_link.compose_nrf24_frame import compose_nrf24_frame
from src.drive_nrf24_link.parse_nrf24_frame import parse_nrf24_frame

_TESTS_DIR = Path(__file__).resolve().parent
_FW_DIR = _TESTS_DIR.parents[1] / "firmware" / "nrf24_link"
_HARNESS_SRC = _TESTS_DIR / "fixtures" / "frame_encoder_harness.cpp"

# ≥6 组跨语言样例：全零/大数（32 位 unsigned long 满值）/回绕近界（满值−1，锁
# unsigned 边界无符号格式化）/8 位 seq 上限/rpd 两态
CROSS_LANGUAGE_CASES = [
    (1, 100, 2, 3, 0),
    (7, 100, 2, 3, 1),
    (0, 0, 0, 0, 0),
    (4294967295, 4294967295, 4294967295, 4294967295, 1),
    (4294967294, 4294967295, 0, 15, 0),  # 回绕近界：ARC 单周期 4bit 满值场景
    (99999999, 99999999, 1, 2, 1),
    (128, 256, 512, 1024, 0),
    (42, 42, 0, 0, 1),
]


@pytest.fixture(scope="session")
def harness_bin(tmp_path_factory):
    """编译 host harness 到 /tmp；g++ 不在或编译失败（-Werror 口径）→直接 fail。"""
    gxx = shutil.which("g++")
    if not gxx:
        pytest.fail("g++ not found on PATH：host 等价测试依赖本机 g++ 编译（规格：不 skip）")
    binary = tmp_path_factory.mktemp("nrf24_host") / "frame_encoder_harness"
    proc = subprocess.run(
        [
            gxx,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(_FW_DIR / "src"),
            str(_HARNESS_SRC),
            str(_FW_DIR / "src" / "frame_encoder.cpp"),
            "-o",
            str(binary),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.fail(f"g++ 编译失败（-Wall -Wextra -Werror 口径）:\n{proc.stderr}")
    return binary


def _run_harness(binary, input_lines: list[str]) -> list[str]:
    proc = subprocess.run(
        [str(binary)],
        input="\n".join(input_lines) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.splitlines()


def test_host_encoder_byte_identical_to_python(harness_bin):
    """同一输入下 C++ 与 Python 输出逐字节一致（纯十进制六字段，无校验和后缀）。"""
    feed = [
        f"{seq},{sent},{lost},{retries},{rpd}"
        for seq, sent, lost, retries, rpd in CROSS_LANGUAGE_CASES
    ]
    got = _run_harness(harness_bin, feed)
    assert len(got) == len(CROSS_LANGUAGE_CASES)
    for (seq, sent, lost, retries, rpd), line in zip(CROSS_LANGUAGE_CASES, got):
        expected = compose_nrf24_frame(seq, sent, lost, retries, rpd)
        assert line == expected, f"C++ 帧与 Python 不一致: {line!r} != {expected!r}"
        # C++ 帧同时必须被解析器接受（固件→parse_nrf24_frame 同口径）
        out = parse_nrf24_frame(line)
        assert (out["seq"], out["sent"], out["lost"], out["retries"]) == (seq, sent, lost, retries)
        assert out["rpd"] is bool(rpd)


def test_host_encoder_normalizes_rpd_to_one_bit(harness_bin):
    """rpd 非 0/1（C++ 侧 unsigned 传宽）→归一到 1：防御性钳制路径与 Python 的 0/1 域互补。"""
    got = _run_harness(harness_bin, ["5,10,1,0,2", "5,10,1,0,255"])
    assert got[0] == compose_nrf24_frame(5, 10, 1, 0, 1)  # !=0 → 1
    assert got[1] == compose_nrf24_frame(5, 10, 1, 0, 1)
    assert parse_nrf24_frame(got[0])["rpd"] is True  # 钳制后仍为合法帧
