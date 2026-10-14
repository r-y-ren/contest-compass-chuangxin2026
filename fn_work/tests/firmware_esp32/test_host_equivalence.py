"""固件 C++ encode_esp32_frame 与 Python compose_esp32_frame 跨语言逐字节等价（R85 host 侧）。

做法：g++ -std=c++17 -Wall -Wextra -Werror 把 firmware/esp32_wifi/src/frame_encoder.cpp
与 fixtures/frame_encoder_harness.cpp 编译到 /tmp（不进仓库），stdin 喂样例行，断言
harness 每行输出与 compose_esp32_frame 同输入输出逐字节一致；顺带用 parse_esp32_frame
复核 C++ 帧可解析（固件→解析器同口径）。g++ 缺失或编译失败→fail（不 skip——本机 g++ 在位，
规格要求跨语言等价是硬验收）。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.drive_esp32_link.compose_esp32_frame import compose_esp32_frame
from src.drive_esp32_link.parse_esp32_frame import parse_esp32_frame

_TESTS_DIR = Path(__file__).resolve().parent
_FW_DIR = _TESTS_DIR.parents[1] / "firmware" / "esp32_wifi"
_HARNESS_SRC = _TESTS_DIR / "fixtures" / "frame_encoder_harness.cpp"

# ≥6 组跨语言样例：NA/大数（32 位 unsigned long 满值）/全零/校验和进位（帧体字节和远超
# 0xFF，锁定掩码口径）/小数 rssi/无校验和两态/语义域边界（±1000.0 合法——域内极值，
# B33 对抗 F1 后 Python 侧同域收窄，边界仍须逐字节一致）
CROSS_LANGUAGE_CASES = [
    (1, 100, 2, 3, -60.0, True),
    (7, 100, 2, 3, -60.0, False),
    (9, 500, 4, 7, None, True),
    (0, 0, 0, 0, None, False),
    (4294967295, 4294967295, 4294967295, 4294967295, -92.5, True),
    (99999999, 99999999, 1, 2, -87.5, True),
    (128, 256, 512, 1024, 0.0, True),
    (42, 42, 0, 0, -12.5, False),
    (11, 20, 1, 0, 1000.0, True),
    (12, 21, 2, 1, -1000.0, False),
]


def _rssi_text(rssi: float | None) -> str:
    return "NA" if rssi is None else repr(float(rssi))


@pytest.fixture(scope="session")
def harness_bin(tmp_path_factory):
    """编译 host harness 到 /tmp；g++ 不在或编译失败（-Werror 口径）→直接 fail。"""
    gxx = shutil.which("g++")
    if not gxx:
        pytest.fail("g++ not found on PATH：host 等价测试依赖本机 g++ 编译（规格：不 skip）")
    binary = tmp_path_factory.mktemp("esp32_host") / "frame_encoder_harness"
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
    """同一输入下 C++ 与 Python 输出逐字节一致（含校验和 hex 小写与 %.1f 小数位）。"""
    feed = [
        f"{seq},{sent},{err},{retries},{_rssi_text(rssi)},{1 if ck else 0}"
        for seq, sent, err, retries, rssi, ck in CROSS_LANGUAGE_CASES
    ]
    got = _run_harness(harness_bin, feed)
    assert len(got) == len(CROSS_LANGUAGE_CASES)
    for (seq, sent, err, retries, rssi, ck), line in zip(CROSS_LANGUAGE_CASES, got):
        expected = compose_esp32_frame(seq, sent, err, retries, rssi, checksum=ck)
        assert line == expected, f"C++ 帧与 Python 不一致: {line!r} != {expected!r}"
        # C++ 帧同时必须被解析器接受（固件→parse_esp32_frame 同口径）
        out = parse_esp32_frame(line)
        assert (out["seq"], out["sent"], out["err"], out["retries"]) == (seq, sent, err, retries)


def test_host_encoder_clamps_nonfinite_rssi_to_na(harness_bin):
    """rssi NaN/±inf→NA 钳制路径：C++ 输出与 Python 的 NA 帧逐字节一致（不吐非法帧）。"""
    got = _run_harness(
        harness_bin, ["5,10,1,0,nan,1", "5,10,1,0,inf,0", "5,10,1,0,-inf,1"]
    )
    assert got[0] == compose_esp32_frame(5, 10, 1, 0, None, checksum=True)
    assert got[1] == compose_esp32_frame(5, 10, 1, 0, None, checksum=False)
    assert got[2] == compose_esp32_frame(5, 10, 1, 0, None, checksum=True)


def test_host_encoder_out_of_domain_finite_rssi_clamps_to_na(harness_bin):
    """B33 对抗 F1：大有限 rssi 域外样例（1e300/1e150/±1000.1）→ C++ 一律 NA 帧。

    对抗实证回归锚：旧口径 1e300 经 %.1f 溢出 body 缓冲→162B 截断帧且校验和
    自洽=可解析的合法错帧（跨语言等价宣称破）；修复后语义域 [-1000.0,1000.0]
    dBm 检查先行于编码，域外不吐数值帧。Python 侧对称口径=域外 ValueError
    （tests/drive_esp32_link 域界用例钉）；本测只钉 C++ 侧——NA 输出与 Python
    NA 路径 compose(..., None, ...) 逐字节一致。
    """
    got = _run_harness(
        harness_bin,
        [
            "5,10,1,0,1e300,1",
            "6,11,2,1,1e150,0",
            "7,12,3,2,-1e300,1",
            "8,13,0,1,1000.1,0",
            "9,14,1,0,-1000.1,1",
        ],
    )
    assert got[0] == compose_esp32_frame(5, 10, 1, 0, None, checksum=True)
    assert got[1] == compose_esp32_frame(6, 11, 2, 1, None, checksum=False)
    assert got[2] == compose_esp32_frame(7, 12, 3, 2, None, checksum=True)
    assert got[3] == compose_esp32_frame(8, 13, 0, 1, None, checksum=False)
    assert got[4] == compose_esp32_frame(9, 14, 1, 0, None, checksum=True)
    for line in got:
        # 域外不吐数值帧：rssi 字段（末逗号后、* 校验和前）必须是 NA。
        assert line.rsplit(",", 1)[1].split("*")[0] == "NA", line
