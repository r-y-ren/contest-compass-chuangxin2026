"""firmware/nrf24_link 工程镜像自证（R86）：断言 platformio.ini（含 RF24 lib_deps）与
src 四文件、README 在位、两构建环境（reporter/peer）定桩完好。对应 responsibility.md
核验命令「测试: firmware_nrf24」。"""
from __future__ import annotations

from pathlib import Path

_FW_DIR = Path(__file__).resolve().parents[2] / "firmware" / "nrf24_link"

# 工程交付物清单（platformio.ini + src 四文件 + 构建/烧录/接线说明 README）
_EXPECTED_FILES = [
    "platformio.ini",
    "src/main.cpp",
    "src/tasks.cpp",
    "src/tasks.h",
    "src/frame_encoder.cpp",
    "src/frame_encoder.h",
    "README.md",
]


def test_firmware_project_files_present():
    missing = [rel for rel in _EXPECTED_FILES if not (_FW_DIR / rel).is_file()]
    assert not missing, f"firmware/nrf24_link 缺交付文件: {missing}"


def test_platformio_envs_pinned_reporter_peer():
    """两角色环境（reporter=NODE_ROLE 1 / peer=NODE_ROLE 2）与串口波特率定桩在位。"""
    ini = (_FW_DIR / "platformio.ini").read_text(encoding="utf-8")
    assert "default_envs = reporter, peer" in ini
    assert "[env:reporter]" in ini and "-DNODE_ROLE=1" in ini
    assert "[env:peer]" in ini and "-DNODE_ROLE=2" in ini
    assert "monitor_speed = 115200" in ini


def test_platformio_libdeps_rf24_pinned():
    """lib_deps 携带 nrf24/RF24 库依赖（版本以 registry 可解析为准，工程级锁定）。"""
    ini = (_FW_DIR / "platformio.ini").read_text(encoding="utf-8")
    assert "lib_deps" in ini
    assert "nrf24/RF24" in ini
